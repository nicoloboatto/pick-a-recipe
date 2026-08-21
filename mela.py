"""
Mela recipe exporter.

Unlike Tandoor and Mealie, Mela has no server or API: a recipe is a
`.melarecipe` JSON file that the user imports into the Mela app (macOS/iOS).
So instead of uploading anything, this module builds that file from the
internal recipe dict and writes it to disk for the web UI to offer as a
download.
"""

import base64
import json
import os
import re
import time

from config import config
from helpers import parse_iso_duration, setup_logger

logger = setup_logger(__name__)


def _slugify(text: str) -> str:
    """Turn a title into a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug or "recipe"


def _format_duration(iso_duration: str) -> str:
    """Convert an ISO 8601 duration (e.g. 'PT1H30M') to Mela's free-text style ('1 hour 30 minutes')."""
    minutes = parse_iso_duration(iso_duration)
    if not minutes:
        return ""
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if mins:
        parts.append(f"{mins} minute" + ("s" if mins != 1 else ""))
    return " ".join(parts)


def _format_ingredient_line(item: dict) -> str:
    """Flatten a structured {food, quantity, unit, notes, raw} ingredient into one display line."""
    raw = (item.get("raw") or "").strip()
    if raw:
        return raw
    parts = [item.get("quantity", ""), item.get("unit", ""), item.get("food", "")]
    line = " ".join(p for p in parts if p).strip()
    notes = (item.get("notes") or "").strip()
    if notes:
        line = f"{line} ({notes})" if line else notes
    return line


def _build_ingredients_text(recipe_data: dict) -> str:
    """Build Mela's newline-separated ingredients string.

    Prefers the structured `recipeIngredients`, falling back to the flattened
    `recipeIngredient` strings when structured data isn't available.
    """
    ing_struct = recipe_data.get("recipeIngredients") or []
    lines = []
    if ing_struct:
        for item in ing_struct:
            if not isinstance(item, dict):
                continue
            line = _format_ingredient_line(item)
            if line:
                lines.append(line)
    else:
        for line in recipe_data.get("recipeIngredient") or []:
            if isinstance(line, str) and line.strip():
                lines.append(line.strip())
    return "\n".join(lines)


def _build_instructions_text(recipe_data: dict) -> str:
    """Build Mela's newline-separated instructions string.

    Handles plain HowToStep text and HowToSection groups (rendered as a
    '#' heading, matching Mela's group syntax).
    """
    lines = []
    for step in recipe_data.get("recipeInstructions") or []:
        if isinstance(step, str):
            text = step.strip()
            if text:
                lines.append(text)
        elif isinstance(step, dict):
            if step.get("@type") == "HowToSection":
                name = (step.get("name") or "").strip()
                if name:
                    lines.append(f"# {name}")
                for nested in step.get("itemListElement", []):
                    text = (nested.get("text") or "").strip() if isinstance(nested, dict) else str(nested).strip()
                    if text:
                        lines.append(text)
            else:
                text = (step.get("text") or "").strip()
                if text:
                    lines.append(text)
    return "\n".join(lines)


def _build_nutrition_text(recipe_data: dict) -> str:
    """Render nutrition as free text, only if the pipeline already estimated it."""
    nutrition = recipe_data.get("nutrition")
    if not isinstance(nutrition, dict):
        return ""
    fields = [
        ("calories", "Calories"),
        ("proteinContent", "Protein"),
        ("fatContent", "Fat"),
        ("carbohydrateContent", "Carbohydrates"),
        ("fiberContent", "Fiber"),
        ("sugarContent", "Sugar"),
        ("sodiumContent", "Sodium"),
        ("cholesterolContent", "Cholesterol"),
    ]
    lines = [f"{label}: {nutrition[key]}" for key, label in fields if nutrition.get(key)]
    return "\n".join(lines)


def _build_categories(recipe_data: dict) -> list[str]:
    categories = recipe_data.get("recipeCategory") or []
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",") if c.strip()]
    elif not isinstance(categories, list):
        categories = []
    return [c for c in categories if isinstance(c, str) and c.strip()]


def _encode_image(image_path: str | None) -> list[str]:
    if not image_path or not os.path.exists(image_path):
        return []
    try:
        with open(image_path, "rb") as f:
            return [base64.b64encode(f.read()).decode("utf-8")]
    except OSError as e:
        logger.warning(f"[Mela] Failed to read image {image_path}: {e}")
        return []


class Mela:
    """Build and persist `.melarecipe` files.

    Mirrors the create_recipe() calling convention of Tandoor/Mealie so it
    plugs into the same pipeline branch, but returns a file path instead of
    a server-assigned recipe ID since there's nothing to upload to.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = output_dir or config.MELA_OUTPUT_DIR

    def _build_recipe(self, recipe_data: dict, image_path: str | None) -> dict:
        """Map the internal recipe dict into Mela's .melarecipe JSON schema."""
        source_url = recipe_data.get("url") or recipe_data.get("source_url") or ""
        recipe_id = re.sub(r"^https?://", "", source_url) if source_url else _slugify(recipe_data.get("name", ""))

        return {
            "id": recipe_id,
            "title": recipe_data.get("name") or recipe_data.get("title") or "Untitled",
            "text": recipe_data.get("description") or "",
            "images": _encode_image(image_path),
            "categories": _build_categories(recipe_data),
            "yield": recipe_data.get("recipeYield") or "",
            "prepTime": _format_duration(recipe_data.get("prepTime", "")),
            "cookTime": _format_duration(recipe_data.get("cookTime", "")),
            "totalTime": _format_duration(recipe_data.get("totalTime", "")),
            "ingredients": _build_ingredients_text(recipe_data),
            "instructions": _build_instructions_text(recipe_data),
            "notes": "",
            "nutrition": _build_nutrition_text(recipe_data),
            "link": source_url,
        }

    def create_recipe(self, recipe_data: dict, image_path: str | None = None) -> dict:
        """Build the .melarecipe file for recipe_data and write it to disk.

        Returns a dict with the written `file_path` (the pipeline stores this
        so the UI can offer it as a download later).
        """
        logger.info("[Mela] Building recipe file...")
        os.makedirs(self.output_dir, exist_ok=True)

        mela_recipe = self._build_recipe(recipe_data, image_path)
        title = mela_recipe.get("title") or "recipe"
        filename = f"{_slugify(title)}-{int(time.time())}.melarecipe"
        file_path = os.path.join(self.output_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(mela_recipe, f, ensure_ascii=False, indent=2)

        logger.info(f"[Mela] Recipe file written: {file_path}")
        return {"file_path": file_path, "title": mela_recipe["title"]}
