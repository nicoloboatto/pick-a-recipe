from config import config
import logging
import os
import re
import threading
from collections import deque

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==============================================================================
# Logging Configuration
# ==============================================================================

# LOG_LEVEL in the environment. debug is what a bug report needs; info is the
# default. A change applies on the next start of the process.
LOG_LEVEL_NAMES = ('warning', 'info', 'debug')
_LEVEL_BY_NAME = {
    'warning': logging.WARNING,
    'info': logging.INFO,
    'debug': logging.DEBUG,
}

# Newest lines kept in the process, already redacted. The copy a reporter
# pastes comes from the container log, which is the same stream.
_LOG_RING_CAPACITY = 500

_LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# Assignment-style secrets: api_key=..., "token": "...", Authorization: Bearer.
_SECRET_ASSIGNMENT = re.compile(
    r'(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|'
    r'password|passwd|secret|authorization|cookie|vapid[_-]?private[_-]?key)'
    r'\b\s*[=:]\s*)([^\s,;]+)'
)
_BEARER = re.compile(r'(?i)\bBearer\s+\S+')
_URL_SECRET = re.compile(
    r'(?i)([?&](?:api[_-]?key|access[_-]?token|token|password|secret|key)=)[^&\s]+'
)
_WELL_KNOWN_SECRET = re.compile(
    r'\b(?:sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|'
    r'gh[pousr]_[A-Za-z0-9]{8,}|'
    r'eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)'
)

# Config values that are credentials. Hosts and model names stay visible:
# a bug report needs them, and they are not keys.
_SECRET_CONFIG_KEYS = (
    'openai_api_key',
    'gemini_api_key',
    'openrouter_api_key',
    'mealie_api_key',
    'tandoor_api_key',
    'hf_token',
    'vapid_private_key',
)

_level_override: str | None = None
_ring: '_RingHandler | None' = None
# Loggers this module configured. Level changes touch only these, so a
# library logger that already has a handler is left alone.
_managed_loggers: set[str] = set()


def normalize_log_level(raw: str | None) -> str:
    """Map LOG_LEVEL onto warning, info, or debug."""
    name = (raw or '').strip().lower()
    if name in ('debug', 'verbose'):
        return 'debug'
    if name in ('warning', 'warn', 'quiet'):
        return 'warning'
    return 'info'


def _active_level_name() -> str:
    if _level_override in _LEVEL_BY_NAME:
        return _level_override
    return normalize_log_level(os.environ.get('LOG_LEVEL'))


def _formatter() -> logging.Formatter:
    return _LOG_FORMAT


class _RingHandler(logging.Handler):
    """Keep the newest log lines so Settings can hand them to a bug report."""

    def __init__(self, capacity: int) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=capacity)
        self._lines_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            return
        with self._lines_lock:
            self._lines.append(line)

    def snapshot(self) -> list[str]:
        with self._lines_lock:
            return list(self._lines)

    def clear(self) -> None:
        with self._lines_lock:
            self._lines.clear()


def _ring_handler() -> _RingHandler:
    global _ring
    if _ring is None:
        _ring = _RingHandler(_LOG_RING_CAPACITY)
        _ring.setFormatter(_formatter())
        _ring.addFilter(_RedactFilter())
    return _ring


def _configured_secrets() -> list[str]:
    """Credential values currently stored for this instance.

    Read at format time so a key saved after startup is still stripped.
    Short values are skipped: replacing them would punch holes in ordinary words.
    The values are used only as search needles. They are never written to a log.
    """
    found: list[str] = []
    try:
        values = [getattr(config, key.upper(), '') for key in _SECRET_CONFIG_KEYS]
        raw_providers = config.AI_PROVIDERS
    except Exception:
        return found
    for value in values:
        if isinstance(value, str) and len(value) >= 8:
            found.append(value)
    if isinstance(raw_providers, str) and raw_providers:
        try:
            import json
            records = json.loads(raw_providers)
        except (TypeError, ValueError):
            records = []
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict):
                    continue
                api_key = record.get('api_key') or ''
                if isinstance(api_key, str) and len(api_key) >= 8:
                    found.append(api_key)
    return found


def redact_text(text: str) -> str:
    """Remove credentials from a log line before it is stored or shown.

    The copied log is what people paste into a public GitHub issue, so a key
    that reached a log message must not survive into that text. No credential
    is written here; values come from the instance config at format time.
    """
    cleaned = text.replace('\r', ' ').replace('\n', ' ')
    for secret in sorted(set(_configured_secrets()), key=len, reverse=True):
        cleaned = cleaned.replace(secret, '[redacted]')
    cleaned = _BEARER.sub('Bearer [redacted]', cleaned)
    cleaned = _URL_SECRET.sub(r'\1[redacted]', cleaned)
    cleaned = _SECRET_ASSIGNMENT.sub(r'\1[redacted]', cleaned)
    cleaned = _WELL_KNOWN_SECRET.sub('[redacted]', cleaned)
    return cleaned


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        cleaned = redact_text(record.getMessage())
        record.msg = cleaned
        record.args = None
        record.message = cleaned
        return True


def _attach(logger: logging.Logger, level: int) -> None:
    _managed_loggers.add(logger.name)
    logger.setLevel(level)
    # Each app logger owns its handlers. Propagating would print twice once
    # a root handler exists, and library loggers stay on their own.
    logger.propagate = False
    stream = next(
        (handler for handler in logger.handlers
         if isinstance(handler, logging.StreamHandler)
         and not isinstance(handler, _RingHandler)),
        None,
    )
    if stream is None:
        stream = logging.StreamHandler()
        stream.setFormatter(_formatter())
        stream.addFilter(_RedactFilter())
        logger.addHandler(stream)
    ring = _ring_handler()
    if ring not in logger.handlers:
        logger.addHandler(ring)
    for handler in logger.handlers:
        handler.setLevel(level)


def setup_logger(name: str) -> logging.Logger:
    """Create and configure a logger with time, function name, and severity.

    The level follows the LOG_LEVEL environment variable. debug is what a bug
    report asks for; info is the default.
    """
    logger = logging.getLogger(name)
    _attach(logger, _LEVEL_BY_NAME[_active_level_name()])
    return logger


def apply_log_level(raw: str | None = None) -> str:
    """Apply LOG_LEVEL from the environment, or an explicit value in tests.

    Called once at startup. Returns the canonical name (warning, info, or debug).
    """
    global _level_override
    if raw is None:
        name = normalize_log_level(os.environ.get('LOG_LEVEL'))
    else:
        name = normalize_log_level(raw)
    _level_override = name
    level = _LEVEL_BY_NAME[name]
    for logger_name in list(_managed_loggers):
        _attach(logging.getLogger(logger_name), level)
    return name


def recent_log_lines() -> list[str]:
    """Newest retained log lines, already redacted by the handler filter."""
    return _ring_handler().snapshot()


def recent_log_text() -> str:
    """Text block for the clipboard and for a GitHub bug report."""
    lines = recent_log_lines()
    header = [
        'pick-a-recipe diagnostic log',
        f'log_level: {_active_level_name()}',
        f'lines: {len(lines)}',
        'Credentials are removed before this text is shown. Read it once before posting.',
        '---',
    ]
    return '\n'.join(header + lines)


def clear_recent_logs() -> None:
    """Drop the retained lines. Used by tests."""
    _ring_handler().clear()


# ==============================================================================
# HTTP Utilities
# ==============================================================================

def create_http_session() -> requests.Session:
    """Create a requests session with retry logic and proper timeouts."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# ==============================================================================
# Parsing Utilities
# ==============================================================================

def coerce_num(val: str) -> float:
    """Convert string quantity to float, handling ranges and locales.
    
    Examples:
        >>> coerce_num("2.5")
        2.5
        >>> coerce_num("3-4")
        3.0
        >>> coerce_num("1,5")
        1.5
    """
    if not val:
        return 0
    v = str(val).strip()
    # Handle range -> take first number
    if "-" in v:
        v = v.split("-")[0].strip()
    v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0


_TITLE_CASE_MINOR_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "en", "for", "if", "in",
    "nor", "of", "on", "or", "per", "the", "to", "v", "via", "vs", "with",
}


def _title_case_word(word: str) -> str:
    """Capitalize a single hyphen-free word: uppercase the first letter,
    lowercase the rest. Avoids str.title()'s mishandling of apostrophes
    (e.g. "chicken's" -> "Chicken'S")."""
    if not word:
        return word
    return word[0].upper() + word[1:].lower()


def to_title_case(text: str) -> str:
    """Title-case a recipe title deterministically - no LLM inference needed.

    Capitalizes each word (each side of a hyphen too, e.g. "stir-fry" ->
    "Stir-Fry"), keeping short English connector words lowercase unless
    they're the first or last word ("Chicken and Rice", not "Chicken And
    Rice"). Safe on non-Latin scripts (Hebrew, Arabic, etc.): they have no
    case distinction, so this passes through unchanged.

    Examples:
        >>> to_title_case("crispy curry chicken sandwiches")
        'Crispy Curry Chicken Sandwiches'
        >>> to_title_case("mac and cheese")
        'Mac and Cheese'
    """
    if not text or not text.strip():
        return text

    words = text.split(" ")
    last_index = len(words) - 1
    result = []
    for idx, word in enumerate(words):
        if not word:
            result.append(word)
            continue
        core = word.lower().strip(".,!?;:'\"()[]")
        if idx not in (0, last_index) and core in _TITLE_CASE_MINOR_WORDS:
            result.append(word.lower())
        else:
            result.append("-".join(_title_case_word(part) for part in word.split("-")))
    return " ".join(result)


def parse_nutrition_value(value: str | None) -> float:
    """Extract numeric value from nutrition string like '450 kcal' or '20 g'.

    Examples:
        >>> parse_nutrition_value("450 kcal")
        450.0
        >>> parse_nutrition_value("20 g")
        20.0
        >>> parse_nutrition_value(None)
        0
    """
    if not value:
        return 0
    # Extract the first number from the string
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value))
    if match:
        return float(match.group(1).replace(",", "."))
    return 0


def extract_servings(recipe_data: dict) -> int:
    """Extract numeric servings from recipeYield field.
    
    Args:
        recipe_data: Recipe dictionary containing 'recipeYield' field.
        
    Returns:
        Integer number of servings, defaults to 1 if not found.
    """
    ry = recipe_data.get("recipeYield") or ""
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(ry))
    if m:
        try:
            return int(float(m.group(1).replace(",", ".")))
        except ValueError:
            pass
    return 1


def parse_iso_duration(duration: str) -> int:
    """Parse ISO 8601 duration (e.g., PT30M, PT1H30M) to minutes.
    
    Examples:
        >>> parse_iso_duration("PT30M")
        30
        >>> parse_iso_duration("PT1H30M")
        90
        >>> parse_iso_duration("PT2H")
        120
        
    Returns:
        Minutes as integer, 0 if parsing fails.
    """
    if not duration:
        return 0
    # Match patterns like PT1H30M, PT45M, PT2H
    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(duration).upper()
    )
    if not match:
        # Try simple numeric (assume minutes)
        try:
            return int(duration)
        except (ValueError, TypeError):
            return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 60 + minutes + (1 if seconds >= 30 else 0)


# ==============================================================================
# Language Utilities
# ==============================================================================

# Map language codes to full names
_LANG_NAMES = {
    "he": "Hebrew",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ar": "Arabic",
    "ru": "Russian",
}


def _get_target_lang() -> str:
    return _LANG_NAMES.get(config.TARGET_LANGUAGE, config.TARGET_LANGUAGE)


# The editable half of the structuring prompt: culinary/style guidance that
# is safe to customize per-user via Settings -> Prompts. Kept separate from
# the JSON output contract below, which a custom prompt can never touch -
# see get_structuring_fixed_suffix().
DEFAULT_STRUCTURING_GUIDANCE = """You are a culinary data normalizer.

General rules:
- Keep instructions chronological; one step per object.
- Do NOT invent quantities. If missing/unclear, leave quantity and unit empty.
- A quantity that appears in no source MUST stay empty.
- Preserve numeric ranges literally, e.g., "3-4".
- Put quick prep modifiers (e.g., chopped, melted, room temperature, diced) into notes,
  not the ingredient name - but only modifiers that do NOT already have their own
  instruction step (see "Ingredients must be raw" below).
- Merge true duplicates (identical group+food+quantity+unit+notes). Never merge
  ingredients that belong to different groups, even if the food name is identical
  (e.g. salt used in both a marinade and a sauce is two separate lines).

Ingredients must be raw, not pre-prepared: every ingredient must describe the item
in the state it's in BEFORE the instructions touch it - the way it would appear on a
shopping list. If the instructions describe transforming an ingredient (roasting,
pureeing, melting, marinating, cooking down, infusing, reducing, etc.), that
transformation belongs only in the instructions text - never pre-applied to the
ingredient's food name or notes. For example, if a step says "roast the pumpkin until
tender, then puree it", the ingredient is "pumpkin" (raw), not "roasted pumpkin" or
"pumpkin puree". Check every ingredient against the instructions: if an ingredient's
wording already assumes a transformation that a later step performs, rewrite the
ingredient to its pre-transformation, raw form instead.

Never list a prepared component as if it were itself a single purchasable ingredient
(e.g. "bechamel", "marinade", "dough", "batter", "sauce") - decompose it into its own
raw base ingredients under a component group instead (see grouping below), and
describe how they're combined in the instructions. If the source material only names
a prepared component generically without listing its own ingredients (e.g. "a simple
bechamel"), decompose it into that preparation's standard base ingredients (bechamel:
butter, flour, milk; a basic dough: flour, water, salt, yeast; etc.), leaving quantity
and unit empty when the source doesn't specify amounts, rather than listing the
prepared item itself as one line.

Group ingredients by component: when a recipe has more than one distinct component
(e.g. a marinade, a sauce, a coating, a filling, a dough, a topping), set each
ingredient's "group" to a short label for its component, in capitals (e.g.
"MARINADE", "SAUCE", "FILLING", "COATING", "DOUGH", "TOPPING"). Use the same group
label consistently for every ingredient that belongs to that component. If the recipe
has only one component, leave "group" as an empty string for every ingredient rather
than inventing a label.

Source material priority, highest first:
1. The "linked_recipe_page" field, when present - text scraped from a blog post the
   creator linked to. This is the creator's own written recipe and outranks every
   other source, including the caption: use its quantities, ingredients, and steps as
   the primary basis for the recipe whenever it's present, even where it conflicts
   with the caption or the video.
2. The "description" field (the post's caption) - often contains the creator's own
   written ingredient list, a high-quality signal since it wasn't spoken under time
   pressure.
3. The "on_screen_text" field - on-screen overlays are usually deliberately written
   out. If it and the audio disagree, trust on_screen_text for ingredients and amounts.
4. The "audio_transcript" field - spoken narration, prone to vague approximations
   ("a good glug of olive oil"); use it to fill gaps the higher sources leave, not to
   override them.
"""


def get_structuring_fixed_suffix() -> str:
    """The non-editable half of the structuring prompt: the output format and
    JSON schema the rest of the app (postprocessing, exporters) depends on.

    Always appended after the (possibly customized) guidance section, and
    never exposed for editing - see the "Prompts" section in Settings.
    """
    target_lang = _get_target_lang()
    return f"""Return a single valid JSON object.
MUST be strictly valid JSON (no comments, no trailing commas).
ALL text content MUST be in {target_lang}. Translate any content that is not already in {target_lang}.

If the input is not a recipe (no dish, no ingredients, no cooking steps — e.g. a vlog, ad, music video, or unrelated clip), set "is_recipe" to false, put a short reason in "rejection_reason", and leave the recipe fields empty. Do NOT invent a recipe.

If it is a recipe, set "is_recipe" to true and "rejection_reason" to "".

Required fields:
- "is_recipe" (boolean)
- "rejection_reason" (string; empty when is_recipe is true)
- "name"
- "description" (1–2 short sentences)
- "datePublished" (ISO 8601)
- "recipeYield" (string; empty if unknown)
- "recipeInstructions" (array of objects: {{ "text": "<step>" }})

Ingredients:
- "recipeIngredients" (array of objects). Each item MUST be:
  {{
    "group": "<component label in capitals, e.g. 'SAUCE', or empty string if the recipe has one component>",
    "food": "<base ingredient noun in {target_lang}>",
    "quantity": "<number or range as string, or empty string if unknown>",
    "unit": "<unit abbreviation or name in {target_lang}, or empty string if none>",
    "notes": "<prep/brand/extra notes in {target_lang}, or empty string>",
    "raw": "<full ingredient line as shown in recipe, for display fallback>"
  }}
  Rules:
  - "food" MUST be the core ingredient name only (e.g., "flour", "chicken breast", "olive oil").
  - "unit" MUST be a measurement unit only (e.g., "g", "kg", "ml", "cup", "tbsp", "tsp", "piece").
  - Do NOT include modifiers or prep instructions in "food" or "unit" - put them in "notes".
  - "raw" should be the complete ingredient line for display purposes.

Only output the JSON object (no explanations).
ALL TEXT MUST BE IN {target_lang}.
"""


def get_recipe_system_prompt() -> str:
    """The full structuring prompt sent to the LLM: the current guidance
    (custom if the user has saved an override in Settings, else the in-code
    default) followed by the fixed output-format contract.
    """
    guidance = config.CUSTOM_STRUCTURING_PROMPT.strip() or DEFAULT_STRUCTURING_GUIDANCE.strip()
    return f"{guidance}\n\n{get_structuring_fixed_suffix()}"


def get_web_recipe_system_prompt() -> str:
    target_lang = _get_target_lang()
    return f"""You are a culinary data normalizer.
You will receive either:
  (a) a Schema.org Recipe JSON object already extracted from the page, or
  (b) raw visible text scraped from a recipe web page.

Return a single valid JSON object.
MUST be strictly valid JSON (no comments, no trailing commas).
ALL text content MUST be in {target_lang}. Translate any content that is not already in {target_lang}.

If the input is not a recipe (no dish, no ingredients, no cooking steps — e.g. a homepage, blog post, or shop page), set "is_recipe" to false, put a short reason in "rejection_reason", and leave the recipe fields empty. Do NOT invent a recipe.

If it is a recipe, set "is_recipe" to true and "rejection_reason" to "".

Required fields:
- "is_recipe" (boolean)
- "rejection_reason" (string; empty when is_recipe is true)
- "name"
- "description" (1–2 short sentences)
- "datePublished" (ISO 8601)
- "recipeYield" (string; empty if unknown)
- "recipeInstructions" (array of objects: {{ "text": "<step>" }})

Ingredients:
- "recipeIngredients" (array of objects). Each item MUST be:
  {{
    "group": "<component label in capitals, e.g. 'SAUCE', or empty string if the recipe has one component>",
    "food": "<base ingredient noun in {target_lang}>",
    "quantity": "<number or range as string, or empty string if unknown>",
    "unit": "<unit abbreviation or name in {target_lang}, or empty string if none>",
    "notes": "<prep/brand/extra notes in {target_lang}, or empty string>",
    "raw": "<full ingredient line as shown in recipe, for display fallback>"
  }}
  Rules:
  - "food" MUST be the core ingredient name only (e.g., "flour", "chicken breast", "olive oil").
  - "unit" MUST be a measurement unit only (e.g., "g", "kg", "ml", "cup", "tbsp", "tsp", "piece").
  - Do NOT include modifiers or prep instructions in "food" or "unit" - put them in "notes".
  - Do NOT invent quantities. If missing/unclear → "quantity": "" and "unit": "".
  - Preserve numeric ranges literally, e.g., "3-4".
  - Put prep words (e.g., chopped, melted, room temperature) into "notes".
  - "raw" should be the complete ingredient line for display purposes.
  - Merge true duplicates (identical food+quantity+unit+notes).

General rules:
- Keep instructions chronological; one step per object.
- Only output the JSON object (no explanations).
- ALL TEXT MUST BE IN {target_lang}.
- If the input already contains Schema.org data, preserve accurate numeric quantities — do not invent or alter them.
- Never guess a missing amount to make the recipe look complete.
"""


def get_yield_nutrition_prompt() -> str:
    target_lang = _get_target_lang()
    return f"""You are a culinary timing assistant.
Given a recipe's ingredients and instructions, estimate:
- servings (number of portions; if unclear, infer a reasonable integer based on ingredient amounts)
- prepTime, cookTime, totalTime as ISO-8601 durations
Leave every nutrition field as "". Do not guess macros; another step looks those up from ingredients.
Assumptions must be realistic; if an item is truly unclear, leave it out.
Return a single valid JSON object with:
{{
  "servings": <int>,
  "recipeYield": "<string in {target_lang}, e.g., '4 מנות' for Hebrew or '4 servings' for English>",
  "prepTime": "PT15M",
  "cookTime": "PT30M",
  "totalTime": "PT45M",
  "nutrition": {{
    "@type": "NutritionInformation",
    "calories": "",
    "proteinContent": "",
    "fatContent": "",
    "carbohydrateContent": "",
    "fiberContent": "",
    "sugarContent": "",
    "sodiumContent": "",
    "cholesterolContent": ""
  }}
}}
Time values must be in ISO 8601 duration format (e.g., "PT30M" for 30 minutes, "PT1H" for 1 hour, "PT1H30M" for 1 hour 30 minutes). Use "" if unknown.
Servings 1–50 only. Output recipeYield in {target_lang}.
"""
