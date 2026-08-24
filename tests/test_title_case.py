import unittest

from helpers import to_title_case


class TestToTitleCase(unittest.TestCase):
    def test_basic_capitalization(self):
        self.assertEqual(to_title_case("crispy curry chicken sandwiches"), "Crispy Curry Chicken Sandwiches")

    def test_minor_words_lowercased_in_middle(self):
        self.assertEqual(to_title_case("mac and cheese"), "Mac and Cheese")
        self.assertEqual(to_title_case("chicken with rice"), "Chicken with Rice")

    def test_minor_word_capitalized_at_start_or_end(self):
        self.assertEqual(to_title_case("a tale of two cities"), "A Tale of Two Cities")
        self.assertEqual(to_title_case("recipe for the"), "Recipe for The")

    def test_apostrophes_not_mangled(self):
        # str.title() would produce "Chicken'S" - this must not.
        self.assertEqual(to_title_case("chicken's favorite soup"), "Chicken's Favorite Soup")

    def test_hyphenated_words(self):
        self.assertEqual(to_title_case("air-fried pumpkin shells"), "Air-Fried Pumpkin Shells")
        self.assertEqual(to_title_case("one-pot chicken and rice"), "One-Pot Chicken and Rice")

    def test_all_caps_input_normalized(self):
        self.assertEqual(to_title_case("THE BEST PASTA EVER"), "The Best Pasta Ever")

    def test_non_latin_script_passes_through(self):
        hebrew = "פסטה עם קמח"
        self.assertEqual(to_title_case(hebrew), hebrew)

    def test_empty_and_whitespace(self):
        self.assertEqual(to_title_case(""), "")
        self.assertEqual(to_title_case("   "), "   ")


if __name__ == "__main__":
    unittest.main()
