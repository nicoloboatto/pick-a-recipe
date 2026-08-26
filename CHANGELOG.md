# Changelog

## [Unreleased]

### New Features

- **Editable Prompts**: Settings → Prompts exposes the structuring and on-screen-text prompts as editable guidance with a fixed, read-only output-format suffix that can't be broken by customization, persisted in the existing config store, with a "Reset to default" that clears the override rather than freezing today's text. The structuring guidance also now explicitly states how to weigh a linked recipe page (when present) against the caption and transcript — see the upcoming recipe-link-extraction feature for where that section comes from. A JSON-parse failure while a custom prompt is active now names it as the likely cause instead of a generic error. (Re-run Structuring, the other half of the original feature, is ported separately alongside the caching it depends on.)

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
