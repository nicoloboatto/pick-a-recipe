"""Tests for the Mela exporter and its enable-gated write_mela_file() hook."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'ui'))

_test_dir = tempfile.mkdtemp()
os.environ['DATA_DIR'] = _test_dir

from config import config, set_config_value  # noqa: E402
from database import init_db  # noqa: E402
from mela import Mela  # noqa: E402
from uploaders import write_mela_file  # noqa: E402

init_db()


class MelaExporterTests(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()

    def test_writes_melarecipe_file(self):
        result = Mela(output_dir=self.output_dir).create_recipe({
            "name": "Test Cake",
            "description": "A cake",
            "recipeIngredients": [
                {"group": "", "food": "flour", "quantity": "200", "unit": "g", "notes": "", "raw": "200g flour"},
            ],
            "recipeInstructions": [{"@type": "HowToStep", "text": "Bake it"}],
        })
        self.assertTrue(os.path.exists(result['file_path']))
        with open(result['file_path']) as f:
            data = json.load(f)
        self.assertEqual(data['title'], 'Test Cake')
        self.assertIn('200g flour', data['ingredients'])

    def test_ingredient_groups_rendered_as_headings(self):
        result = Mela(output_dir=self.output_dir).create_recipe({
            "name": "Grouped",
            "recipeIngredients": [
                {"group": "SAUCE", "food": "salt", "quantity": "1", "unit": "tsp", "notes": "", "raw": "1 tsp salt"},
            ],
        })
        with open(result['file_path']) as f:
            data = json.load(f)
        self.assertTrue(data['ingredients'].startswith('# SAUCE'))

    def test_linked_recipe_status_surfaced_in_notes(self):
        result = Mela(output_dir=self.output_dir).create_recipe({
            "name": "Linked",
            "linkedRecipeStatus": "ok",
            "linkedRecipeUrl": "https://blog.example.com/recipe",
        })
        with open(result['file_path']) as f:
            data = json.load(f)
        self.assertIn('https://blog.example.com/recipe', data['notes'])

        result2 = Mela(output_dir=self.output_dir).create_recipe({
            "name": "Unavailable Link",
            "linkedRecipeStatus": "unavailable",
        })
        with open(result2['file_path']) as f:
            data2 = json.load(f)
        self.assertIn('could not be read', data2['notes'])


class WriteMelaFileGatingTests(unittest.TestCase):
    def tearDown(self):
        set_config_value('mela_enabled', 'false')
        config.reload()

    def test_returns_none_when_disabled(self):
        set_config_value('mela_enabled', 'false')
        config.reload()
        self.assertIsNone(write_mela_file({"name": "X"}, None))

    def test_writes_file_when_enabled(self):
        set_config_value('mela_enabled', 'true')
        set_config_value('mela_output_dir', tempfile.mkdtemp())
        config.reload()
        path = write_mela_file({"name": "Enabled Recipe"}, None)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
