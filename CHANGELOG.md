# Changelog

## [Unreleased]

### New Features

- **Mela Export**: Added `mela` as a new Output Target. Mela has no server or API, so instead of uploading, Pick-a-Recipe writes a `.melarecipe` JSON file (with embedded base64 thumbnail) and the web UI offers it as a download from the completed-job card, the job page, and History. Added a configurable Mela output directory setting, a `mela_file_path` history column, download endpoint, and automatic file cleanup when a history entry is deleted.
- **Follow Linked Recipe Pages**: New `recipe_link_extractor.py` scans the post caption for a linked recipe blog post, filters out social-platform/link-in-bio noise, follows shorteners, and extracts recipe text (preferring schema.org `Recipe` JSON-LD, falling back to readability-style extraction) to feed the structuring LLM as an additional, clearly-labeled source alongside the transcript and on-screen text. Paywalls, bot-checks, and thin content are treated as "unavailable," never as failures — the job continues with video content only, the link is preserved on the recipe and surfaced in Mela's notes, and the review screen/History show a small note. New "Follow recipe links found in captions" setting (default on).
- **Editable Prompts & Re-run Structuring**: Settings → Prompts exposes the structuring and on-screen-text prompts as editable guidance with a fixed, read-only output-format suffix that can't be broken by customization, persisted in the existing config store, with a "Reset to default" that clears the override rather than freezing today's text. Every completed recipe stores the exact prompt used (viewable in History, collapsed) and caches its source material, so a new "Re-run Structuring" action (on the preview modal and in History) regenerates just the structured recipe from cached transcript/caption/linked-page text in a couple of seconds — no re-download, no re-transcription — keeping one previous version for recovery. A JSON-parse failure while a custom prompt is active now names it as the likely cause instead of a generic error.

### Improvements

- **Needs-Confirmation Badge Instead of Browser Notifications**: Removed the browser `Notification.requestPermission()` prompt entirely — it fired on every new job and every job-progress page, and nobody wants a permission popup for a personal recipe tool. Replaced it with a persistent bell badge in the sidebar (visible on every page while any recipe is awaiting confirmation) showing a live count, backed by a new lightweight `/api/pending-uploads/count` endpoint so the badge doesn't have to pull every candidate image's base64 data just to show a number. Clicking it opens History pre-filtered to a new "Needs Confirmation" status, which required teaching the combined history/jobs query to recognize `awaiting_confirmation` as its own filter bucket (previously lumped in with generic "In Progress"). The preview modal also no longer pops itself open the moment a recipe becomes ready — it used to interrupt whatever else was on screen, including a different recipe you were already reviewing. The badge and the "Awaiting Confirmation" list are now the only notification; opening a recipe is always a deliberate click on "Review".
- **Grouped, Raw-State Ingredients**: The structuring prompt now requires ingredients in their raw, pre-instruction state (no "roasted pumpkin puree" when a step roasts and purees raw pumpkin) and decomposes generic prepared components (a bechamel, a marinade, a dough) into their own base ingredients. Added a `group` field to the ingredient schema so multi-component recipes (marinade + sauce + coating, filling + bechamel, etc.) get labeled sections (`MARINADE`, `SAUCE`, ...) instead of one flat list, and the same ingredient name used in two components (e.g. salt) no longer incorrectly merges into a single line. Tandoor (`is_header` rows), Mealie (inline `title` headers), and Mela (`#` headings) all render the groups natively. The linked-recipe-page priority language was also sharpened: when present, it now explicitly outranks the caption and on-screen text, not just the spoken transcript.

### Bug Fixes

- **Duplicate "Recently Completed" Cards**: Every job/preview socket event (`job_progress`, `job_complete`, `job_failed`, `job_cancelled`, `recipe_preview`, `recipe_cancelled`) was emitted twice — once scoped to the job's room, once as a global broadcast. Since a plain `socketio.emit()` with no room already reaches every connected client (room membership included), the room-scoped emit was pure redundancy: a client that also joined the room (as the main page always does) received each event twice, producing a duplicate completed-recipe card, duplicate notifications, etc. Removed the redundant room-scoped emits, keeping only the broadcast.
- **`/api/pending-uploads` 500 when a job had no image candidates**: `upload.get('image_candidates', [])` only falls back to `[]` when the key is *missing*, not when it's `None` — and a pending upload created with no candidate images stores exactly that. Normalized `image_candidates` to always be a list in `database.py`'s getters, at the source.
- **Bulk-download temp files never cleaned up**: an earlier version of the multi-recipe download below wrote a temp `.melarecipes` zip and relied on `response.call_on_close` to delete it afterwards — confirmed against a real running server that this callback never fires for `send_file()` responses (Werkzeug's direct-passthrough file responses bypass it). Fixed by building the archive in memory instead, so there's no temp file to leak in the first place.
- **Stale `main.js` served indefinitely**: `main.js` was cache-busted with a hardcoded `?v=5` that had to be bumped by hand on every change — and wasn't, through several rewrites (Re-run Structuring, then the Awaiting Confirmation list), so browsers kept serving pre-those-features code. Reloading looked like it "worked" only because the *old* code's own reconnect handler re-ran, not because anything new loaded. `notifications.js` and `job-page.js` had no cache-busting at all. Replaced the manual counter with a token derived from process start time (`static_version`, already used by `style.css`), applied consistently to every script tag — a container restart now always busts the cache with no bump-it-by-hand step to forget.
- **OpenAI default model retiring**: `gpt-5-mini-2025-08-07` (the previous default) has an official shutdown date of 2026-12-11 per OpenAI's deprecations page, which names `gpt-5.6-terra` as its replacement. Updated the default and the resilience fallback chain (`gpt-5.6-terra` → `gpt-5.6-sol` → `gpt-4o`), and added a one-time DB migration so existing installs still pointing at the old model get moved over automatically, the same way the earlier Gemini model retirement was handled.

### Improvements

- **Deterministic Title Case**: Recipe titles are now normalized to title case in code (`helpers.to_title_case()`), not left to the LLM — mechanical formatting isn't inference material. Handles apostrophes correctly (unlike `str.title()`), hyphenated words ("Air-Fried"), and common connector words ("Chicken with Rice", not "Chicken With Rice"). Applied once in `chef.py`'s postprocessing, so it covers both the initial extraction and Re-run Structuring.
- **Awaiting Confirmation List**: Recipes waiting on confirm-before-upload no longer only ever pop a single modal — a persistent "Awaiting Confirmation" section lists every pending recipe, so a second one finishing while the first is still open (or arriving after you navigated away) doesn't get silently stuck until a page reload. The confirm modal gained a non-destructive close (✕) that returns a recipe to the list instead of deciding for you.
- **Bulk Download from History**: Selecting multiple Mela recipes in History now offers a "Download Selected" action alongside bulk delete. A single selection downloads its plain `.melarecipe` file; two or more get merged into one `.melarecipes` archive (Mela's own multi-recipe format, built in-memory) so they import into Mela in one action. Non-Mela or missing-file selections are skipped with a note.

## [1.4.0] - 2026-01-21

### New Features

- **History Page & Navigation**: Added History page with navigation link, job tracking, and completed results display
- **Bulk Delete Functionality**: Implemented bulk delete for history and job entries with new status indicators
- **Dual Export Support**: Added ability to export recipes to both Tandoor and Mealie simultaneously with dual export badge and preview updates
- **Export/Import Settings**: Added export/import settings functionality for easier configuration management
- **Unit & Food Management**: Implemented unit and food management in Mealie exporter with fetching and creation logic
- **Nutrition Display**: Enabled nutrition display in Mealie settings with enhanced logging for nutrition updates
- **URL Retry Functionality**: Added URL data attribute to history items for improved retry functionality
- **Source URL Handling**: Added source URL handling in recipe update payload for Mealie integration
- **Multi-architecture Docker**: Added build-and-push script for multi-architecture Docker image support

### Improvements

- **Ingredient Structure**: Updated ingredient structure to include 'notes' and 'raw' fields for improved recipe export compatibility
- **Enhanced Logging**: Improved logging for ingredient and nutrition processing across Chef, Mealie, and Tandoor exporters
- **Error Handling**: Improved error handling and logging for recipe update requests in Mealie exporter
- **History Filtering**: Exclude failed recipe history entries if a successful entry exists for the same URL
- **Code Refactoring**: Moved video URL input declaration for improved readability

### Technical Changes

- Upgraded yt-dlp on startup with modified CMD to run Flask application
- Updated main.js version to 4 for script consistency

## [1.3.0] - 2026-01-14

### New Features

- Centralized logging system across all modules for better debugging and traceability
- HuggingFace token configuration for authenticated model downloads
- Added `ingredientReferences` field to Mealie recipe instructions

### Bug Fixes

- Fixed database file path consistency with `ui/database.py`
- Updated Dockerfile to install curl and unzip dependencies
- Fixed PWA share_target to use POST method with proper enctype
