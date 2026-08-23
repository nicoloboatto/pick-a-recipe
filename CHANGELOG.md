# Changelog

## [Unreleased]

### New Features

- **Mela Export**: Added `mela` as a new Output Target. Mela has no server or API, so instead of uploading, Pick-a-Recipe writes a `.melarecipe` JSON file (with embedded base64 thumbnail) and the web UI offers it as a download from the completed-job card, the job page, and History. Added a configurable Mela output directory setting, a `mela_file_path` history column, download endpoint, and automatic file cleanup when a history entry is deleted.
- **Follow Linked Recipe Pages**: New `recipe_link_extractor.py` scans the post caption for a linked recipe blog post, filters out social-platform/link-in-bio noise, follows shorteners, and extracts recipe text (preferring schema.org `Recipe` JSON-LD, falling back to readability-style extraction) to feed the structuring LLM as an additional, clearly-labeled source alongside the transcript and on-screen text. Paywalls, bot-checks, and thin content are treated as "unavailable," never as failures — the job continues with video content only, the link is preserved on the recipe and surfaced in Mela's notes, and the review screen/History show a small note. New "Follow recipe links found in captions" setting (default on).

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
