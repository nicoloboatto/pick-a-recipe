"""
Shared video-to-recipe extraction pipeline used by the web UI and CLI.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from config import config
from image_extractor import extract_dish_image_candidates
from recipe_link_extractor import find_and_fetch_linked_recipe
from transcriber import Transcriber
from video_downloader import VideoDownloader


class ProgressReporter(Protocol):
    def is_cancelled(self) -> bool: ...
    def update(self, stage: str, message: str, percent: int, video_title: str | None = None) -> None: ...
    # set_dish_dir is optional - implemented by the web UI's reporter (so a
    # still-in-progress job's cache folder can be resolved for a live
    # "re-run structuring" call) and safely absent from the CLI's.


@dataclass
class PipelineResult:
    recipe_data: dict | None = None
    image_path: str | None = None
    output_target: str = ""
    mela_file_path: str | None = None
    structuring_prompt_used: str | None = None
    llm_tokens_estimate: int = 0
    error: str | None = None


@dataclass
class PipelineStats:
    llm_tokens_estimate: int = 0

    def add_text(self, text: str) -> None:
        # Rough token estimate (~4 chars per token) for cost tracking
        self.llm_tokens_estimate += max(1, len(text) // 4)


def _build_combined_source_text(transcription: str, visual_text: str, linked_text: str = "") -> str:
    """Combine audio transcript, on-screen text, and (if read) linked recipe
    page text into one labeled blob for the structuring LLM.

    Shared between the live pipeline and re-run structuring so both build
    the exact same input from cached source material.
    """
    sections = [f"=== AUDIO TRANSCRIPTION ===\n{transcription}"]
    if visual_text:
        sections.append(f"=== ON-SCREEN TEXT (ingredients, instructions, etc.) ===\n{visual_text}")
    if linked_text:
        sections.append(f"=== LINKED RECIPE PAGE ===\n{linked_text}")
    if len(sections) == 1:
        return transcription
    return "\n\n".join(sections)


def _annotate_linked_recipe(recipe_data: dict, linked_meta: dict) -> None:
    """Record the linked-page fetch result on the recipe dict, in place."""
    if not linked_meta.get("status"):
        return
    recipe_data["linkedRecipeUrl"] = linked_meta.get("url")
    recipe_data["linkedRecipeStatus"] = linked_meta.get("status")
    if linked_meta.get("status") == "unavailable":
        recipe_data["linkedRecipeReason"] = linked_meta.get("reason")


_NO_SOURCE_MATERIAL_MSG = (
    "Source material for this recipe is no longer available (it may predate "
    "this feature or its cache was cleared) - re-run the full extraction instead."
)


def rerun_structuring(dish_dir: str, source_url: str) -> dict:
    """Re-run only the LLM structuring step from cached source material.

    No re-download, no re-transcription: reuses the transcript/on-screen-text/
    caption/linked-page caches written by run_extraction_pipeline(). Raises
    FileNotFoundError (caught by callers and turned into a clear user-facing
    message) if that cache is gone.

    Returns {"recipe_data": ..., "structuring_prompt_used": ...}.
    """
    if not dish_dir or not os.path.isdir(dish_dir):
        raise FileNotFoundError(_NO_SOURCE_MATERIAL_MSG)

    lang = config.TARGET_LANGUAGE

    def _read(filename: str) -> str:
        path = os.path.join(dish_dir, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    transcription = _read(f"transcription_{lang}.txt")
    if not transcription:
        raise FileNotFoundError(_NO_SOURCE_MATERIAL_MSG)

    visual_text = _read(f"visual_{lang}.txt")
    caption = _read("caption.txt")
    linked_text = _read("linked_page.txt")
    combined_transcription = _build_combined_source_text(transcription, visual_text, linked_text)

    from chef import Chef
    from helpers import get_recipe_system_prompt

    chef = Chef(source_url=source_url, description=caption, transcription=combined_transcription)
    structuring_prompt_used = get_recipe_system_prompt()
    recipe_data = chef.create_recipe()

    linked_meta_path = os.path.join(dish_dir, "linked_page_meta.json")
    if os.path.exists(linked_meta_path):
        with open(linked_meta_path, "r", encoding="utf-8") as f:
            linked_meta = json.load(f)
        _annotate_linked_recipe(recipe_data, linked_meta)

    return {"recipe_data": recipe_data, "structuring_prompt_used": structuring_prompt_used}


@dataclass
class PreviewWaiter:
    """Handles optional confirm-before-upload flow."""

    job_id: str
    recipe_data: dict
    image_path: str | None
    image_candidates: list
    best_image_index: int
    output_target: str
    export_to_both: bool
    emit_preview: Callable[[dict], None]
    wait_for_confirmation: Callable[[str, threading.Event, int], tuple[bool, int]]
    pending_uploads: dict
    create_pending_upload_fn: Callable
    get_pending_upload_fn: Callable
    delete_pending_upload_fn: Callable
    is_cancelled: Callable[[], bool]
    socketio_emit_cancelled: Callable[[], None]


def run_extraction_pipeline(
    url: str,
    reporter: ProgressReporter,
    *,
    work_dir: str = "/tmp",
    stats: PipelineStats | None = None,
    preview: PreviewWaiter | None = None,
    skip_upload: bool = False,
) -> PipelineResult:
    """Run the full download → transcribe → recipe pipeline."""
    stats = stats or PipelineStats()

    try:
        config.reload()

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        reporter.update("info", "Fetching video information...", 10)
        downloader = VideoDownloader(url)
        item = downloader._get_info()
        description = item.get("description", "No description available.")
        title = item.get("title", "Untitled")
        reporter.update("info", f"Video: {title}", 15, video_title=title)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        reporter.update("download", "Downloading video...", 20)
        vid_id, video_path = downloader._download_video()
        if vid_id is None:
            return PipelineResult(error="Failed to download video")

        dish_dir = os.path.join(work_dir, vid_id)
        reporter.update("download", "Video downloaded successfully", 30)
        if hasattr(reporter, "set_dish_dir"):
            reporter.set_dish_dir(dish_dir)

        # Cache the caption so a later "re-run structuring" doesn't need to
        # re-fetch video info to get it back.
        with open(os.path.join(dish_dir, "caption.txt"), "w", encoding="utf-8") as f:
            f.write(description)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        linked_text = ""
        linked_meta = {"url": None, "status": None, "reason": None}
        linked_meta_cache = os.path.join(dish_dir, "linked_page_meta.json")
        linked_text_cache = os.path.join(dish_dir, "linked_page.txt")

        if config.FOLLOW_RECIPE_LINKS:
            if os.path.exists(linked_meta_cache):
                reporter.update("download", "Using cached linked-recipe-page result", 32)
                with open(linked_meta_cache, "r", encoding="utf-8") as f:
                    linked_meta = json.load(f)
                if os.path.exists(linked_text_cache):
                    with open(linked_text_cache, "r", encoding="utf-8") as f:
                        linked_text = f.read()
            else:
                reporter.update("download", "Checking recipe links in description...", 32)
                link_result = find_and_fetch_linked_recipe(description)
                if link_result is not None:
                    linked_meta = {
                        "url": link_result.url,
                        "status": link_result.status,
                        "reason": link_result.reason,
                    }
                    if link_result.status == "ok":
                        linked_text = link_result.text
                with open(linked_meta_cache, "w", encoding="utf-8") as f:
                    json.dump(linked_meta, f)
                with open(linked_text_cache, "w", encoding="utf-8") as f:
                    f.write(linked_text)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        reporter.update("transcribe", "Transcribing audio...", 35)
        transcriber = Transcriber(video_path)
        lang = config.TARGET_LANGUAGE
        audio_cache = os.path.join(dish_dir, f"transcription_{lang}.txt")

        if os.path.exists(audio_cache):
            reporter.update("transcribe", "Using cached transcription", 40)
            with open(audio_cache, "r", encoding="utf-8") as f:
                transcription = f.read()
        else:
            transcription = transcriber.transcribe()
            with open(audio_cache, "w", encoding="utf-8") as f:
                f.write(transcription)
        stats.add_text(transcription)
        reporter.update("transcribe", "Audio transcribed", 50)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        reporter.update("visual", "Extracting on-screen text...", 55)
        visual_text = ""
        visual_cache = os.path.join(dish_dir, f"visual_{lang}.txt")
        if os.path.exists(visual_cache):
            reporter.update("visual", "Using cached visual text", 60)
            with open(visual_cache, "r", encoding="utf-8") as f:
                visual_text = f.read()
        else:
            try:
                visual_text = transcriber.extract_visual_text()
                with open(visual_cache, "w", encoding="utf-8") as f:
                    f.write(visual_text)
                stats.add_text(visual_text)
            except Exception as exc:
                reporter.update("visual", f"Warning: Could not extract visual text: {exc}", 60)
        reporter.update("visual", "Visual text extracted", 65)

        combined_transcription = _build_combined_source_text(transcription, visual_text, linked_text)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        reporter.update("image", "Extracting dish image candidates...", 70)
        image_path = None
        image_candidates: list[str] = []
        best_image_index = 0
        image_cache = os.path.join(dish_dir, "dish.jpg")
        frames_dir = os.path.join(dish_dir, "dish_frames")

        if os.path.exists(frames_dir) and os.path.exists(image_cache):
            reporter.update("image", "Using cached dish images", 75)
            image_path = image_cache
            image_candidates = sorted(
                os.path.join(frames_dir, f)
                for f in os.listdir(frames_dir)
                if f.startswith("dish_candidate_") and f.endswith(".jpg")
            )
        else:
            try:
                result = extract_dish_image_candidates(video_path)
                image_path = result.get("best_image")
                image_candidates = result.get("candidates", [])
                best_image_index = result.get("best_index", 0)
            except Exception as exc:
                reporter.update("image", f"Warning: Could not extract image: {exc}", 75)
        reporter.update("image", "Image candidates extracted", 80)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        reporter.update("evaluate", "Creating recipe with AI...", 85)
        from chef import Chef
        from helpers import get_recipe_system_prompt

        chef = Chef(source_url=url, description=description, transcription=combined_transcription)
        stats.add_text(combined_transcription)
        structuring_prompt_used = get_recipe_system_prompt()
        recipe_data = chef.create_recipe()
        if not recipe_data:
            return PipelineResult(error="Failed to create recipe", llm_tokens_estimate=stats.llm_tokens_estimate)

        _annotate_linked_recipe(recipe_data, linked_meta)

        reporter.update("evaluate", "Recipe created successfully", 90)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled")

        is_mela_only = config.OUTPUT_TARGET == "mela" and not config.EXPORT_TO_BOTH
        upload_message = "Saving Mela recipe file..." if is_mela_only else f"Uploading to {config.OUTPUT_TARGET}..."

        if config.CONFIRM_BEFORE_UPLOAD and preview is not None:
            selected_idx = _handle_preview_confirmation(preview, recipe_data, image_path,
                                                        image_candidates, best_image_index, reporter)
            if selected_idx is None:
                return PipelineResult(error="cancelled", llm_tokens_estimate=stats.llm_tokens_estimate)
            if image_candidates and 0 <= selected_idx < len(image_candidates):
                image_path = image_candidates[selected_idx]
            reporter.update("upload", upload_message, 95)
        else:
            reporter.update("upload", upload_message, 95)

        if reporter.is_cancelled():
            return PipelineResult(error="cancelled", recipe_data=recipe_data, image_path=image_path,
                                  llm_tokens_estimate=stats.llm_tokens_estimate)

        if skip_upload:
            reporter.update("complete", "Recipe created (upload skipped)", 100)
            return PipelineResult(
                recipe_data=recipe_data,
                image_path=image_path,
                output_target="none",
                llm_tokens_estimate=stats.llm_tokens_estimate,
            )

        upload_targets = ["tandoor", "mealie"] if config.EXPORT_TO_BOTH else [config.OUTPUT_TARGET]
        if config.EXPORT_TO_BOTH:
            reporter.update("upload", "Uploading to Tandoor and Mealie...", 95)

        upload_results = []
        mela_file_path = None
        for target in upload_targets:
            try:
                if target == "tandoor":
                    from tandoor import Tandoor
                    tandoor = Tandoor()
                    result = tandoor.create_recipe(recipe_data)
                    if image_path and result.get("id"):
                        tandoor.upload_image(result["id"], image_path)
                    upload_results.append((target, True, None))
                elif target == "mealie":
                    from mealie import Mealie
                    mealie = Mealie()
                    result = mealie.create_recipe(recipe_data)
                    recipe_slug = result.get("slug") or result.get("id")
                    if image_path and recipe_slug:
                        mealie.upload_image(recipe_slug, image_path)
                    upload_results.append((target, True, None))
                elif target == "mela":
                    from mela import Mela
                    mela = Mela()
                    result = mela.create_recipe(recipe_data, image_path)
                    mela_file_path = result.get("file_path")
                    upload_results.append((target, True, None))
            except Exception as upload_error:
                upload_results.append((target, False, str(upload_error)))

        final_target = ", ".join(upload_targets) if config.EXPORT_TO_BOTH else config.OUTPUT_TARGET
        failed = [r for r in upload_results if not r[1]]
        if failed and len(failed) == len(upload_targets):
            msgs = "; ".join(f"{r[0]}: {r[2]}" for r in failed)
            return PipelineResult(error=f"All uploads failed: {msgs}", recipe_data=recipe_data,
                                  image_path=image_path, llm_tokens_estimate=stats.llm_tokens_estimate)

        if failed:
            success = [r[0] for r in upload_results if r[1]]
            final_target = ", ".join(success)
            failed_msgs = "; ".join(f"{r[0]}: {r[2]}" for r in failed)
            reporter.update(
                "complete",
                f"Uploaded to {final_target}. Failed: {failed_msgs}",
                100,
            )
        elif is_mela_only:
            reporter.update("complete", "Recipe saved as a Mela file!", 100)
        else:
            reporter.update("complete", f"Recipe uploaded successfully to {final_target}!", 100)
        return PipelineResult(
            recipe_data=recipe_data,
            image_path=image_path,
            output_target=final_target,
            mela_file_path=mela_file_path,
            structuring_prompt_used=structuring_prompt_used,
            llm_tokens_estimate=stats.llm_tokens_estimate,
        )

    except Exception as exc:
        return PipelineResult(error=f"Error: {exc}", llm_tokens_estimate=stats.llm_tokens_estimate)


def _handle_preview_confirmation(
    preview: PreviewWaiter,
    recipe_data: dict,
    image_path: str | None,
    image_candidates: list,
    best_image_index: int,
    reporter: ProgressReporter,
) -> int | None:
    """Show preview and wait for user confirmation. Returns selected index or None if cancelled."""
    reporter.update("preview", "Waiting for your confirmation...", 90)

    image_data = None
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

    candidate_images_data = []
    for idx, candidate_path in enumerate(image_candidates):
        if os.path.exists(candidate_path):
            with open(candidate_path, "rb") as f:
                candidate_images_data.append({
                    "index": idx,
                    "data": base64.b64encode(f.read()).decode("utf-8"),
                    "path": candidate_path,
                    "is_best": idx == best_image_index,
                })

    display_target = "Tandoor & Mealie" if preview.export_to_both else preview.output_target.capitalize()
    confirm_event = threading.Event()
    upload_id = secrets.token_hex(16)

    preview.pending_uploads[upload_id] = {
        "recipe": recipe_data,
        "image_path": image_path,
        "image_candidates": image_candidates,
        "output_target": preview.output_target,
        "event": confirm_event,
        "confirmed": None,
        "selected_image_index": best_image_index,
        "job_id": preview.job_id,
    }

    preview.create_pending_upload_fn(
        upload_id=upload_id,
        job_id=preview.job_id,
        recipe_data=recipe_data,
        image_path=image_path,
        image_candidates=image_candidates,
        output_target=preview.output_target,
        best_image_index=best_image_index,
        timeout_minutes=5,
    )

    preview.emit_preview({
        "job_id": preview.job_id,
        "upload_id": upload_id,
        "recipe": recipe_data,
        "image_data": image_data,
        "candidate_images": candidate_images_data,
        "best_image_index": best_image_index,
        "output_target": display_target,
        "export_to_both": preview.export_to_both,
    })

    timeout_seconds = 300
    poll_interval = 1
    elapsed = 0
    confirmed = False
    db_confirmed = False
    selected_idx = best_image_index

    while elapsed < timeout_seconds:
        if confirm_event.wait(timeout=poll_interval):
            confirmed = True
            break

        db_upload = preview.get_pending_upload_fn(upload_id)
        if db_upload:
            if db_upload["status"] == "confirmed":
                db_confirmed = True
                confirmed = True
                selected_idx = db_upload.get("selected_image_index", best_image_index)
                break
            if db_upload["status"] in ("cancelled", "expired"):
                break

        elapsed += poll_interval
        if preview.is_cancelled():
            preview.delete_pending_upload_fn(upload_id)
            preview.pending_uploads.pop(upload_id, None)
            return None

    db_upload = preview.get_pending_upload_fn(upload_id)
    preview.delete_pending_upload_fn(upload_id)
    pending_data = preview.pending_uploads.pop(upload_id, None)

    if not confirmed and elapsed >= timeout_seconds:
        return None

    was_confirmed = False
    if db_confirmed:
        was_confirmed = db_upload and db_upload["status"] == "confirmed"
    elif pending_data:
        was_confirmed = pending_data.get("confirmed", False)

    if not was_confirmed:
        preview.socketio_emit_cancelled()
        return None

    if not db_confirmed and pending_data:
        selected_idx = pending_data.get("selected_image_index", best_image_index)
    return selected_idx
