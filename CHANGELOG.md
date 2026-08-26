# Changelog

## [Unreleased]

### New Features (frontend)

- **Re-run Structuring & Mela Download in the React Tasks Page**: Wires the backend endpoints from earlier commits into the actual UI. A "Re-run Structuring" button appears both on a live pending-approval row (regenerates the draft in place) and in a completed recipe's detail modal (once dish_dir cache material exists), regenerating just the structured recipe without re-downloading or re-transcribing. Completed Mela recipes get a "Download .melarecipe" action (row dropdown menu and detail modal), and multi-selecting several Mela recipes in the task list surfaces a bulk-download button that merges them into one `.melarecipes` archive. `RecipeView` also now renders ingredient `group` headings (MARINADE, SAUCE, ...) instead of a flat list, matching how Tandoor/Mealie/Mela already render them. Also fixes a bug where a Mela-only setup's confirm-before-upload preview showed "no target" instead of "Mela" as the destination.

### Improvements

- **Grouped, Raw-State Ingredients**: The structuring prompt now requires ingredients in their raw, pre-instruction state (no "roasted pumpkin puree" when a step roasts and purees raw pumpkin) and decomposes generic prepared components (a bechamel, a marinade, a dough) into their own base ingredients. Added a `group` field to the ingredient schema so multi-component recipes (marinade + sauce + coating, filling + bechamel, etc.) get labeled sections (`MARINADE`, `SAUCE`, ...) instead of one flat list, and the same ingredient name used in two components (e.g. salt) no longer incorrectly merges into a single line. Tandoor (`is_header` rows) and Mealie (inline `title` headers) both render the groups natively. The linked-recipe-page priority language was also sharpened: when present, it now explicitly outranks the caption and on-screen text, not just the spoken transcript.

### New Features

- **GHCR Build + Unraid Docker Template**: Added `.github/workflows/docker-build.yml`, a GitHub-hosted workflow that builds and pushes the image to `ghcr.io/<owner>/<repo>` on every push to `main`, using the built-in `GITHUB_TOKEN` — no new secrets, no self-hosted runner, since upstream's own `deploy.yml` (Docker Hub via a self-hosted runner, deployed to their own Portainer server) isn't reachable from a fork. Coexists alongside upstream's workflow untouched. Added `unraid-template.xml` (a ready-made Unraid Docker Manager template) and `UNRAID.md` walking through making the GHCR package pullable and wiring up the template end to end.
- **Local Username/Password Login**: Restores local login as the primary sign-in path, with Authentik SSO as an optional alternative (set `AUTHENTIK_CLIENT_ID`/`AUTHENTIK_CLIENT_SECRET` to also enable it) — needed since a self-hosted Unraid deployment has no Authentik server. The `users` table supports both local accounts (bcrypt `password_hash`) and Authentik-provisioned ones (`oidc_sub`) side by side; a first-time OIDC sign-in still links to an existing local account by email rather than creating a duplicate. Critically, the migration that used to detect a `password_hash` column and respond by dropping the entire `users` table (to enforce "OIDC-only, no legacy local accounts") is now purely additive — any existing account, local or OIDC, survives re-running the schema migration. A brand-new install (or a DB an older OIDC-only build already emptied) seeds a default `admin`/`admin123` account that forces a password change on first login, which also auto-disables new registrations once completed. Settings gains a Users list (admin-only, with delete), an Allow Registration toggle (gates new OIDC sign-ins only), and a Change Password form. The `/login` page now always renders the local-login form rather than the React SPA's own login screen, since local auth has no home there yet.
- **Mela Export**: Added `mela` as a new Output Target. Mela has no server or API, so instead of uploading, Pick-a-Recipe writes a `.melarecipe` JSON file (with embedded base64 thumbnail, ingredient group headings, and the linked-recipe-page status/URL surfaced in the notes field) and offers it as a download from History. Enable it independently alongside Tandoor/Mealie via its own toggle in Settings → Recipe Export — since Mela is a local file write rather than a network upload, it's handled as its own step alongside `upload_recipe_to_targets()` rather than forced through that upload-shaped abstraction, so a Mela-only setup (nothing else enabled) still completes the job instead of hitting "no recipe manager enabled." Added a configurable output directory, a `mela_file_path` history column, a download endpoint, and automatic file cleanup when a history entry is deleted. Bulk-download-as-archive lands with the History UI it depends on.
- **Follow Linked Recipe Pages**: New `recipe_link_extractor.py` scans the post caption for a linked recipe blog post, filters out social-platform/link-in-bio noise, follows shorteners, and extracts recipe text (preferring schema.org `Recipe` JSON-LD, falling back to readability-style extraction) to feed the structuring LLM as an additional, clearly-labeled source alongside the transcript and on-screen text. Paywalls, bot-checks, and thin content are treated as "unavailable," never as failures — the job continues with video content only, and the attempted URL/status are recorded on the recipe for later surfacing in exporters/UI. New "Follow recipe links found in captions" setting (default on). (The preview/History note showing an "unavailable" link, and Mela's notes-field surfacing, land alongside the UI/exporter work they depend on.)
- **Editable Prompts**: Settings → Prompts exposes the structuring and on-screen-text prompts as editable guidance with a fixed, read-only output-format suffix that can't be broken by customization, persisted in the existing config store, with a "Reset to default" that clears the override rather than freezing today's text. The structuring guidance also now explicitly states how to weigh a linked recipe page (when present) against the caption and transcript — see the recipe-link-extraction feature for where that section comes from. A JSON-parse failure while a custom prompt is active now names it as the likely cause instead of a generic error.
- **Re-run Structuring (backend)**: A new `rerun_structuring()` in `pipeline.py` regenerates just the structured recipe from cached transcript/caption/linked-page text in a couple of seconds — no re-download, no re-transcription — reusing the same `dish_dir` cache convention the pipeline already writes to. New `recipe_jobs.dish_dir`/`recipe_history.{dish_dir,structuring_prompt_used,previous_recipe_data}` columns make this resolvable for both a still-in-progress job (the confirm-before-upload case) and a completed History entry, which also keeps one previous version for recovery. Two new endpoints — `/api/history/<id>/rerun-structuring` and `/api/pending-uploads/<id>/rerun-structuring` — expose it; a UI trigger for both lands with the frontend work it depends on.

### Improvements

- **Deterministic Title Case**: Recipe titles are now normalized to title case in code (`helpers.to_title_case()`), not left to the LLM — mechanical formatting isn't inference material. Handles apostrophes correctly (unlike `str.title()`), hyphenated words ("Air-Fried"), and common connector words ("Chicken with Rice", not "Chicken With Rice").

### Bug Fixes

- **OpenAI default model retiring**: `gpt-5-mini-2025-08-07` (the previous default) has an official shutdown date of 2026-12-11 per OpenAI's deprecations page, which names `gpt-5.6-terra` as its replacement. Updated the default and the resilience fallback chain (`gpt-5.6-terra` → `gpt-5.6-sol` → `gpt-4o`), and added a one-time DB migration so existing installs still pointing at the old model get moved over automatically, the same way the earlier Gemini model retirement was handled.

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
