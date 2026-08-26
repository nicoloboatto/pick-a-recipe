import unittest
from unittest.mock import patch, MagicMock

from recipe_link_extractor import (
    extract_candidate_urls,
    fetch_recipe_page,
    find_and_fetch_linked_recipe,
    _is_noise_host,
    _looks_blocked,
    _extract_json_ld_recipe,
)
from bs4 import BeautifulSoup


class TestExtractCandidateUrls(unittest.TestCase):
    def test_finds_plain_url(self):
        caption = "Full recipe on my blog: https://cooking.example.com/best-pasta"
        self.assertEqual(
            extract_candidate_urls(caption),
            ["https://cooking.example.com/best-pasta"],
        )

    def test_skips_social_platform_links(self):
        caption = (
            "Check my other reel https://www.instagram.com/reel/xyz "
            "and my blog https://cooking.example.com/pasta"
        )
        self.assertEqual(
            extract_candidate_urls(caption),
            ["https://cooking.example.com/pasta"],
        )

    def test_skips_link_in_bio_profile_pages(self):
        caption = "Everything here: https://linktr.ee/somechef"
        self.assertEqual(extract_candidate_urls(caption), [])

    def test_no_urls_returns_empty(self):
        self.assertEqual(extract_candidate_urls("Just a caption, no links!"), [])

    def test_trailing_punctuation_stripped(self):
        caption = "Recipe here (https://cooking.example.com/pasta)."
        self.assertEqual(
            extract_candidate_urls(caption),
            ["https://cooking.example.com/pasta"],
        )

    def test_deduplicates(self):
        caption = (
            "https://cooking.example.com/pasta and again "
            "https://cooking.example.com/pasta"
        )
        self.assertEqual(
            extract_candidate_urls(caption),
            ["https://cooking.example.com/pasta"],
        )

    @patch("recipe_link_extractor._resolve_shortener")
    def test_shortener_resolved_and_reclassified(self, mock_resolve):
        mock_resolve.return_value = "https://cooking.example.com/pasta"
        caption = "Recipe: https://bit.ly/abc123"
        self.assertEqual(
            extract_candidate_urls(caption),
            ["https://cooking.example.com/pasta"],
        )

    @patch("recipe_link_extractor._resolve_shortener")
    def test_shortener_resolving_to_profile_page_is_noise(self, mock_resolve):
        mock_resolve.return_value = "https://linktr.ee/somechef"
        caption = "Recipe: https://bit.ly/abc123"
        self.assertEqual(extract_candidate_urls(caption), [])


class TestIsNoiseHost(unittest.TestCase):
    def test_known_social_hosts(self):
        for host in ("instagram.com", "www.tiktok.com", "youtu.be"):
            self.assertTrue(_is_noise_host(host))

    def test_subdomain_of_noise_host(self):
        self.assertTrue(_is_noise_host("m.instagram.com"))

    def test_ordinary_blog_host_not_noise(self):
        self.assertFalse(_is_noise_host("cooking.example.com"))

    def test_empty_host_is_noise(self):
        self.assertTrue(_is_noise_host(""))


class TestLooksBlocked(unittest.TestCase):
    def test_detects_captcha_marker(self):
        html = "<html><body>Please complete the CAPTCHA to continue</body></html>"
        self.assertIsNotNone(_looks_blocked(BeautifulSoup(html, "html.parser")))

    def test_detects_paywall_marker(self):
        html = "<html><body>Subscribe to continue reading this article</body></html>"
        self.assertIsNotNone(_looks_blocked(BeautifulSoup(html, "html.parser")))

    def test_normal_page_not_blocked(self):
        html = "<html><body>Here is a lovely pasta recipe with lots of steps.</body></html>"
        self.assertIsNone(_looks_blocked(BeautifulSoup(html, "html.parser")))

    def test_recaptcha_badge_css_is_not_a_false_positive(self):
        # Real-world regression: ordinary WordPress recipe blogs routinely ship
        # an invisible reCAPTCHA badge for spam protection - "captcha" shows up
        # in CSS class names and script boilerplate on perfectly normal pages.
        html = (
            "<html><head><style>.grecaptcha-badge{visibility:collapse}</style>"
            "<script>grecaptcha.render('captcha-box');</script></head>"
            "<body>Here is a lovely pasta recipe with lots of steps.</body></html>"
        )
        self.assertIsNone(_looks_blocked(BeautifulSoup(html, "html.parser")))


class TestJsonLdRecipeExtraction(unittest.TestCase):
    def test_parses_recipe_json_ld(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "Best Pasta",
            "recipeIngredient": ["400g spaghetti", "2 cloves garlic"],
            "recipeInstructions": [
                {"@type": "HowToStep", "text": "Boil the pasta."},
                {"@type": "HowToStep", "text": "Fry the garlic."}
            ]
        }
        </script>
        </head><body>irrelevant boilerplate</body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        text = _extract_json_ld_recipe(soup)
        self.assertIn("Best Pasta", text)
        self.assertIn("400g spaghetti", text)
        self.assertIn("Boil the pasta.", text)

    def test_parses_recipe_inside_graph(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@graph": [
            {"@type": "WebPage", "name": "irrelevant"},
            {"@type": "Recipe", "name": "Graph Recipe",
             "recipeIngredient": ["1 egg"],
             "recipeInstructions": "Crack the egg.\\nCook it."}
        ]}
        </script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        text = _extract_json_ld_recipe(soup)
        self.assertIn("Graph Recipe", text)
        self.assertIn("1 egg", text)

    def test_returns_none_when_no_recipe_present(self):
        html = """
        <html><head>
        <script type="application/ld+json">{"@type": "WebPage", "name": "Home"}</script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(_extract_json_ld_recipe(soup))

    def test_malformed_json_ld_does_not_raise(self):
        html = """
        <html><head>
        <script type="application/ld+json">{not valid json,,,}</script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(_extract_json_ld_recipe(soup))


def _long_recipe_html():
    ingredients = "".join(f"<li>Ingredient {i}</li>" for i in range(10))
    return f"""
    <html><body>
    <h1>Best Pasta Recipe</h1>
    <p>{'This is a wonderful recipe with a long story. ' * 15}</p>
    <ul>{ingredients}</ul>
    <p>{'Full cooking instructions go here in detail. ' * 15}</p>
    </body></html>
    """


class TestFetchRecipePage(unittest.TestCase):
    @patch("recipe_link_extractor._fetch_html")
    def test_unavailable_when_fetch_fails(self, mock_fetch):
        mock_fetch.return_value = None
        result = fetch_recipe_page("https://cooking.example.com/pasta")
        self.assertEqual(result.status, "unavailable")

    @patch("recipe_link_extractor._fetch_html")
    def test_unavailable_on_paywall_marker(self, mock_fetch):
        mock_fetch.return_value = "<html><body>Subscribe to continue reading</body></html>"
        result = fetch_recipe_page("https://cooking.example.com/pasta")
        self.assertEqual(result.status, "unavailable")
        self.assertIn("blocked", result.reason)

    @patch("recipe_link_extractor._fetch_html")
    def test_unavailable_when_text_too_short(self, mock_fetch):
        mock_fetch.return_value = "<html><body>Hi</body></html>"
        result = fetch_recipe_page("https://cooking.example.com/pasta")
        self.assertEqual(result.status, "unavailable")
        self.assertIn("too short", result.reason)

    @patch("recipe_link_extractor._fetch_html")
    def test_ok_via_json_ld(self, mock_fetch):
        mock_fetch.return_value = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Recipe", "name": "Best Pasta",
         "recipeIngredient": ["400g spaghetti", "2 cloves garlic", "olive oil", "salt"],
         "recipeInstructions": [
            {"@type": "HowToStep", "text": "Boil a large pot of salted water."},
            {"@type": "HowToStep", "text": "Cook the spaghetti until al dente."},
            {"@type": "HowToStep", "text": "Fry the garlic gently in olive oil."},
            {"@type": "HowToStep", "text": "Toss the pasta with the garlic oil."}
         ]}
        </script>
        </head><body>short boilerplate</body></html>
        """
        result = fetch_recipe_page("https://cooking.example.com/pasta")
        self.assertEqual(result.status, "ok")
        self.assertIn("Best Pasta", result.text)

    @patch("recipe_link_extractor._fetch_html")
    def test_ok_via_readability_fallback(self, mock_fetch):
        mock_fetch.return_value = _long_recipe_html()
        result = fetch_recipe_page("https://cooking.example.com/pasta")
        self.assertEqual(result.status, "ok")
        self.assertGreater(len(result.text), 300)


class TestFindAndFetchLinkedRecipe(unittest.TestCase):
    def test_returns_none_when_no_candidates(self):
        self.assertIsNone(find_and_fetch_linked_recipe("no links here"))

    @patch("recipe_link_extractor.fetch_recipe_page")
    def test_uses_first_successful_candidate(self, mock_fetch):
        def side_effect(url):
            from recipe_link_extractor import LinkResult
            if "first" in url:
                return LinkResult(url=url, status="unavailable", reason="paywall")
            return LinkResult(url=url, status="ok", text="great recipe text")

        mock_fetch.side_effect = side_effect
        caption = (
            "Try https://first.example.com/pasta or "
            "https://second.example.com/pasta"
        )
        result = find_and_fetch_linked_recipe(caption)
        self.assertEqual(result.status, "ok")
        self.assertIn("second.example.com", result.url)

    @patch("recipe_link_extractor.fetch_recipe_page")
    def test_records_first_failure_when_all_unavailable(self, mock_fetch):
        from recipe_link_extractor import LinkResult
        mock_fetch.return_value = LinkResult(
            url="unused", status="unavailable", reason="paywall"
        )
        caption = "Try https://first.example.com/pasta"
        result = find_and_fetch_linked_recipe(caption)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.reason, "paywall")

    @patch("recipe_link_extractor.fetch_recipe_page")
    def test_never_raises_on_unexpected_error(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("boom")
        caption = "Try https://first.example.com/pasta"
        result = find_and_fetch_linked_recipe(caption)
        self.assertEqual(result.status, "unavailable")

    @patch("recipe_link_extractor.fetch_recipe_page")
    def test_caps_at_three_candidates(self, mock_fetch):
        from recipe_link_extractor import LinkResult
        mock_fetch.return_value = LinkResult(url="x", status="unavailable", reason="x")
        caption = " ".join(
            f"https://site{i}.example.com/pasta" for i in range(5)
        )
        find_and_fetch_linked_recipe(caption)
        self.assertEqual(mock_fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()
