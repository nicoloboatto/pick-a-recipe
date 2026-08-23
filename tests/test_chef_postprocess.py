import os
import tempfile
import unittest

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp())

from chef import Chef


def _postprocess(ingredients):
    c = Chef.__new__(Chef)  # skip __init__ (no LLM client needed for postprocessing)
    c.source_url = "https://x.test"
    data = {"name": "Test", "recipeIngredients": ingredients}
    return c._postprocess_recipe(data, "https://x.test")


class TestIngredientGrouping(unittest.TestCase):
    def test_same_food_different_groups_not_merged(self):
        # Regression: "salt" in a marinade and "salt" in a sauce are two
        # distinct lines, not one merged "salt" entry with a lost group.
        result = _postprocess([
            {"group": "MARINADE", "food": "salt", "quantity": "1", "unit": "Tbsp", "notes": "", "raw": "1 Tbsp salt"},
            {"group": "SAUCE", "food": "salt", "quantity": "", "unit": "", "notes": "to taste", "raw": "salt to taste"},
        ])
        ings = result["recipeIngredients"]
        self.assertEqual(len(ings), 2)
        self.assertEqual(ings[0]["group"], "MARINADE")
        self.assertEqual(ings[1]["group"], "SAUCE")

    def test_same_food_same_group_still_merges(self):
        result = _postprocess([
            {"group": "SAUCE", "food": "salt", "quantity": "1", "unit": "tsp", "notes": "", "raw": "1 tsp salt"},
            {"group": "SAUCE", "food": "salt", "quantity": "1", "unit": "tsp", "notes": "fine", "raw": "1 tsp fine salt"},
        ])
        ings = result["recipeIngredients"]
        self.assertEqual(len(ings), 1)
        self.assertEqual(ings[0]["notes"], "fine")

    def test_group_normalized_to_uppercase(self):
        result = _postprocess([
            {"group": "sauce", "food": "salt", "quantity": "1", "unit": "tsp", "notes": "", "raw": "1 tsp salt"},
        ])
        self.assertEqual(result["recipeIngredients"][0]["group"], "SAUCE")

    def test_ungrouped_ingredient_has_empty_group(self):
        result = _postprocess([
            {"group": "", "food": "brioche bun", "quantity": "4", "unit": "piece", "notes": "", "raw": "4 buns"},
        ])
        self.assertEqual(result["recipeIngredients"][0]["group"], "")

    def test_flattened_list_includes_group_headings(self):
        result = _postprocess([
            {"group": "MARINADE", "food": "yogurt", "quantity": "80", "unit": "g", "notes": "", "raw": "80g yogurt"},
            {"group": "MARINADE", "food": "salt", "quantity": "1", "unit": "Tbsp", "notes": "", "raw": "1 Tbsp salt"},
            {"group": "SAUCE", "food": "yogurt", "quantity": "240", "unit": "g", "notes": "", "raw": "240g yogurt"},
        ])
        flattened = result["recipeIngredient"]
        self.assertEqual(flattened[0], "# MARINADE")
        self.assertIn("# SAUCE", flattened)
        # The heading appears once per group, not once per ingredient
        self.assertEqual(flattened.count("# MARINADE"), 1)

    def test_no_headings_when_single_ungrouped_component(self):
        result = _postprocess([
            {"group": "", "food": "flour", "quantity": "200", "unit": "g", "notes": "", "raw": "200g flour"},
            {"group": "", "food": "water", "quantity": "100", "unit": "ml", "notes": "", "raw": "100ml water"},
        ])
        flattened = result["recipeIngredient"]
        self.assertFalse(any(line.startswith("#") for line in flattened))


if __name__ == '__main__':
    unittest.main()
