"""
Recipe link extractor.

When a post's caption links out to the creator's blog, that page usually
has the properly written recipe with exact quantities - far better source
material than a transcript of someone saying "a good glug of olive oil".
This module finds such links in a caption, filters out noise (the social
platforms themselves, link-in-bio landing pages, shorteners that resolve
to a profile rather than an article), fetches the most promising
candidates, and extracts clean recipe text from them.

Every failure mode (timeout, non-200, paywall, bot-check, thin content)
is treated as "unavailable", never raised - the caller always gets a
result object back and continues with video-derived content only.
"""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from helpers import setup_logger

logger = setup_logger(__name__)

_REQUEST_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
_MAX_REDIRECTS = 5
_MAX_CANDIDATES = 3
_MIN_TEXT_LENGTH = 300

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

# Social platforms themselves - never the "linked recipe", always noise.
_SOCIAL_HOSTS = {
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com",
    "facebook.com", "www.facebook.com", "fb.com", "m.facebook.com",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "threads.net", "www.threads.net",
    "pinterest.com", "www.pinterest.com",
}

# Link-in-bio / profile-aggregator tools: even after following a
# shortener, landing here means "a profile page", not an article.
_PROFILE_AGGREGATOR_HOSTS = {
    "linktr.ee", "linkin.bio", "campsite.bio", "beacons.ai",
    "msha.ke", "lnk.bio", "bio.link", "solo.to", "milkshake.app",
}

_NOISE_HOSTS = _SOCIAL_HOSTS | _PROFILE_AGGREGATOR_HOSTS

# Shorteners worth following through to their real destination.
_SHORTENER_HOSTS = {
    "bit.ly", "tinyurl.com", "t.co", "ow.ly", "rebrand.ly",
    "is.gd", "buff.ly", "shorturl.at", "cutt.ly", "rb.gy",
}

# Specific challenge/paywall phrasing only - deliberately not bare words like
# "captcha", which shows up harmlessly in reCAPTCHA badge CSS/JS on huge
# numbers of ordinary WordPress recipe blogs and would false-positive constantly.
_UNAVAILABLE_MARKERS = (
    "solve the captcha",
    "complete the captcha",
    "verify you are human",
    "are you a robot",
    "please enable javascript to continue",
    "enable javascript and cookies",
    "checking your browser before accessing",
    "access denied",
    "subscribe to continue reading",
    "this article is for subscribers",
)


@dataclass
class LinkResult:
    url: str
    status: str  # "ok" or "unavailable"
    text: str = ""
    reason: str = ""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_noise_host(host: str) -> bool:
    if not host:
        return True
    if host in _NOISE_HOSTS:
        return True
    return any(host.endswith("." + noise) for noise in _NOISE_HOSTS)


def _is_shortener_host(host: str) -> bool:
    return host in _SHORTENER_HOSTS


def extract_candidate_urls(caption: str) -> list[str]:
    """Find and rank candidate recipe-page URLs in a caption.

    Resolves shorteners (following redirects) and drops anything that
    lands on a social platform or a link-in-bio profile page. Order is
    preserved from the caption; de-duplicated.
    """
    if not caption:
        return []

    seen: set[str] = set()
    candidates: list[str] = []

    for raw_url in _URL_RE.findall(caption):
        url = raw_url.rstrip(".,;:!?)")
        host = _host(url)
        if not host:
            continue

        if _is_shortener_host(host):
            resolved = _resolve_shortener(url)
            if resolved is None:
                continue
            url = resolved
            host = _host(url)

        if _is_noise_host(host):
            logger.debug(f"[LinkExtractor] Skipping noise URL: {url}")
            continue

        if url not in seen:
            seen.add(url)
            candidates.append(url)

    return candidates


def _resolve_shortener(url: str) -> str | None:
    """Follow a shortener's redirect chain (capped) and return the final URL."""
    try:
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        if len(resp.history) > _MAX_REDIRECTS:
            logger.debug(f"[LinkExtractor] Too many redirects resolving {url}")
            return None
        return resp.url
    except requests.RequestException as e:
        logger.debug(f"[LinkExtractor] Failed to resolve shortener {url}: {e}")
        return None


def _fetch_html(url: str) -> str | None:
    """Fetch a URL with a timeout, browser UA, and a hard cap on response size."""
    try:
        resp = requests.get(
            url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            stream=True,
        )
    except requests.RequestException as e:
        logger.debug(f"[LinkExtractor] Fetch failed for {url}: {e}")
        return None

    if resp.status_code != 200:
        logger.debug(f"[LinkExtractor] Non-200 ({resp.status_code}) for {url}")
        resp.close()
        return None

    chunks = []
    total = 0
    try:
        for chunk in resp.iter_content(chunk_size=65536, decode_unicode=False):
            total += len(chunk)
            if total > _MAX_RESPONSE_BYTES:
                logger.debug(f"[LinkExtractor] Response too large, truncating: {url}")
                break
            chunks.append(chunk)
    except requests.RequestException as e:
        logger.debug(f"[LinkExtractor] Error reading response body for {url}: {e}")
        return None
    finally:
        resp.close()

    encoding = resp.encoding or "utf-8"
    try:
        return b"".join(chunks).decode(encoding, errors="replace")
    except (LookupError, TypeError):
        return b"".join(chunks).decode("utf-8", errors="replace")


def _visible_text(soup: BeautifulSoup) -> str:
    """Extract visible text only, skipping <script>/<style> contents.

    Doesn't decompose anything - the same soup is reused afterward for
    JSON-LD extraction, which lives inside <script> tags.
    """
    parts = [
        str(node) for node in soup.find_all(string=True)
        if not node.parent or node.parent.name not in ("script", "style")
    ]
    return " ".join(parts)


def _looks_blocked(soup: BeautifulSoup) -> str | None:
    """Return a reason string if the page looks like a paywall/bot-check interstitial.

    Scans visible body text rather than raw HTML: CSS class names and script
    boilerplate for things like reCAPTCHA badges routinely contain words like
    "captcha" on ordinary, perfectly-readable pages.
    """
    text = _visible_text(soup).lower()
    for marker in _UNAVAILABLE_MARKERS:
        if marker in text:
            return f"blocked (page text contains '{marker}')"
    return None


def _extract_json_ld_recipe(soup: BeautifulSoup) -> str | None:
    """Parse schema.org Recipe JSON-LD if present. Preferred: exact ingredient
    and instruction lists with no guessing."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        for node in _flatten_ld_json(data):
            types = node.get("@type")
            types = [types] if isinstance(types, str) else (types or [])
            if any("recipe" in str(t).lower() for t in types):
                return _render_recipe_ld(node)

    return None


def _flatten_ld_json(data) -> list[dict]:
    """Flatten @graph wrappers and top-level lists into a flat list of dicts."""
    nodes = []
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        if "@graph" in item and isinstance(item["@graph"], list):
            nodes.extend(n for n in item["@graph"] if isinstance(n, dict))
        else:
            nodes.append(item)
    return nodes


def _render_recipe_ld(node: dict) -> str:
    """Render a schema.org Recipe JSON-LD node into clean plain text."""
    lines = []

    name = node.get("name")
    if name:
        lines.append(f"Recipe: {name}")

    description = node.get("description")
    if description:
        lines.append(str(description).strip())

    ingredients = node.get("recipeIngredient") or node.get("ingredients") or []
    if isinstance(ingredients, list) and ingredients:
        lines.append("\nIngredients:")
        for ing in ingredients:
            lines.append(f"- {ing}")

    instructions = node.get("recipeInstructions") or []
    steps = _flatten_instructions(instructions)
    if steps:
        lines.append("\nInstructions:")
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")

    return "\n".join(lines).strip()


def _flatten_instructions(instructions) -> list[str]:
    """schema.org recipeInstructions can be a string, a list of strings, a
    list of HowToStep objects, or HowToSection objects nesting HowToSteps."""
    if isinstance(instructions, str):
        return [s.strip() for s in instructions.split("\n") if s.strip()]

    steps = []
    if not isinstance(instructions, list):
        return steps

    for item in instructions:
        if isinstance(item, str):
            if item.strip():
                steps.append(item.strip())
        elif isinstance(item, dict):
            item_type = str(item.get("@type", "")).lower()
            if item_type == "howtosection":
                steps.extend(_flatten_instructions(item.get("itemListElement", [])))
            else:
                text = item.get("text") or item.get("name") or ""
                if text.strip():
                    steps.append(text.strip())
    return steps


def _extract_readable_text(html: str, url: str) -> str | None:
    """Fallback article-text extraction when no structured data is present."""
    import trafilatura
    return trafilatura.extract(html, url=url, include_comments=False, include_tables=False)


def fetch_recipe_page(url: str) -> LinkResult:
    """Fetch a single candidate URL and try to extract recipe text from it."""
    html = _fetch_html(url)
    if html is None:
        return LinkResult(url=url, status="unavailable", reason="fetch failed or non-200")

    soup = BeautifulSoup(html, "html.parser")

    blocked_reason = _looks_blocked(soup)
    if blocked_reason:
        return LinkResult(url=url, status="unavailable", reason=blocked_reason)

    text = _extract_json_ld_recipe(soup)

    if text:
        # Structured data is trusted on its own terms: a short-but-genuine
        # recipe (few ingredients/steps) is still valid, unlike thin
        # readability output, which usually means a paywall/consent wall.
        if len(text.strip()) < 20:
            return LinkResult(url=url, status="unavailable", reason="recipe JSON-LD had no usable content")
        logger.debug(f"[LinkExtractor] Extracted {len(text)} chars from {url} via json-ld")
        return LinkResult(url=url, status="ok", text=text.strip())

    text = _extract_readable_text(html, url)
    if not text or len(text.strip()) < _MIN_TEXT_LENGTH:
        return LinkResult(
            url=url, status="unavailable",
            reason=f"extracted text too short ({len(text.strip()) if text else 0} chars)",
        )

    logger.debug(f"[LinkExtractor] Extracted {len(text)} chars from {url} via readability")
    return LinkResult(url=url, status="ok", text=text.strip())


def find_and_fetch_linked_recipe(caption: str) -> LinkResult | None:
    """Scan a caption for recipe links and return the first usable result.

    Tries up to _MAX_CANDIDATES candidates in order. Never raises - every
    failure mode becomes a LinkResult with status="unavailable". Returns
    None only when the caption contained no candidate URLs at all.
    """
    candidates = extract_candidate_urls(caption)[:_MAX_CANDIDATES]
    if not candidates:
        return None

    first_failure = None
    for url in candidates:
        try:
            result = fetch_recipe_page(url)
        except Exception as e:
            # Belt and suspenders: a linked page must never fail the job.
            logger.debug(f"[LinkExtractor] Unexpected error fetching {url}: {e}")
            result = LinkResult(url=url, status="unavailable", reason=str(e))

        if result.status == "ok":
            return result
        if first_failure is None:
            first_failure = result
        logger.debug(f"[LinkExtractor] {url} unavailable: {result.reason}")

    return first_failure
