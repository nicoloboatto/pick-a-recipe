from config import config
import logging
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==============================================================================
# Logging Configuration
# ==============================================================================

def setup_logger(name: str) -> logging.Logger:
    """Create and configure a logger with time, function name, and severity.
    
    Args:
        name: Name of the logger (typically __name__).
        
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        
        # Create formatter with time, name, function, severity
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


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
- Keep instructions chronological; one step per step.
- Do NOT invent quantities. If missing/unclear, leave quantity and unit empty.
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
1. A "=== LINKED RECIPE PAGE ===" section inside "transcript", when present - text
   scraped from a blog post the creator linked to. This is the creator's own written
   recipe and outranks every other source, including the caption: use its quantities,
   ingredients, and steps as the primary basis for the recipe whenever it's present,
   even where it conflicts with the caption or transcript.
2. The "description" field (the post's caption) - often contains the creator's own
   written ingredient list, a high-quality signal since it wasn't spoken under time
   pressure.
3. The transcript's "=== ON-SCREEN TEXT ===" section - on-screen overlays are usually
   deliberately written out.
4. The transcript's "=== AUDIO TRANSCRIPTION ===" section - spoken narration, prone to
   vague approximations ("a good glug of olive oil"); use it to fill gaps the higher
   sources leave, not to override them.
"""


def get_structuring_fixed_suffix() -> str:
    """The non-editable half of the structuring prompt: the output format and
    JSON schema the rest of the app (postprocessing, exporters) depends on.

    Always appended after the (possibly customized) guidance section, and
    never exposed for editing - see the "Prompts" section in Settings.
    """
    target_lang = _get_target_lang()
    return f"""Return a single valid JSON object in Schema.org JSON-LD for a Recipe.
MUST be strictly valid JSON (no comments, no trailing commas).
ALL text content MUST be in {target_lang}. Translate any content that is not already in {target_lang}.

Required fields:
- "@context": "https://schema.org"
- "@type": "Recipe"
- "name"
- "description" (1–2 short sentences)
- "datePublished" (ISO 8601)
- "recipeYield" (string)
- "recipeInstructions" (array of HowToStep objects: {{ "@type": "HowToStep", "text": "<step>" }})

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


def get_yield_nutrition_prompt() -> str:
    target_lang = _get_target_lang()
    return f"""You are a registered-dietitian-style assistant.
Given a recipe's ingredients and instructions, estimate:
- servings (number of portions; if unclear, infer a reasonable integer based on ingredient amounts)
- prepTime (time to prepare ingredients, in minutes)
- cookTime (time to cook/bake, in minutes)
- totalTime (total time from start to finish, in minutes)
- per-serving nutrition (Schema.org NutritionInformation fields):
  calories (kcal), proteinContent (g), fatContent (g), carbohydrateContent (g),
  fiberContent (g), sugarContent (g), sodiumContent (mg), cholesterolContent (mg).
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
    "calories": "450 kcal",
    "proteinContent": "20 g",
    "fatContent": "18 g",
    "carbohydrateContent": "55 g",
    "fiberContent": "4 g",
    "sugarContent": "3 g",
    "sodiumContent": "680 mg",
    "cholesterolContent": "70 mg"
  }}
}}
Time values must be in ISO 8601 duration format (e.g., "PT30M" for 30 minutes, "PT1H" for 1 hour, "PT1H30M" for 1 hour 30 minutes).
All nutrition values are per serving.
Do not invent impossible numbers; keep them plausible.
Estimate times based on the complexity of the recipe and cooking methods described.
Output recipeYield in {target_lang}.
"""
