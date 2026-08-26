"""Tests for re-run structuring: dish_dir persistence and rerun_structuring()."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'ui'))

_test_dir = tempfile.mkdtemp()
os.environ['DATA_DIR'] = _test_dir

from database import (  # noqa: E402
    init_db, create_job, update_job_dish_dir, get_job,
    create_history_entry, get_history_entry, update_history_recipe_data,
)
from pipeline import rerun_structuring  # noqa: E402

init_db()


class DishDirPersistenceTests(unittest.TestCase):
    def test_job_dish_dir_roundtrip(self):
        job_id = create_job('https://example.com/dish-dir-test')
        update_job_dish_dir(job_id, '/tmp/some-video-id')
        self.assertEqual(get_job(job_id)['dish_dir'], '/tmp/some-video-id')

    def test_history_entry_stores_dish_dir_and_prompt(self):
        job_id = create_job('https://example.com/history-dish-dir-test')
        history_id = create_history_entry(
            job_id=job_id, url='https://example.com/history-dish-dir-test',
            video_title='Vid', recipe_name='Name', recipe_data={'name': 'Name'},
            thumbnail_path=None, thumbnail_data=None, status='success',
            dish_dir='/tmp/abc', structuring_prompt_used='PROMPT TEXT',
        )
        item = get_history_entry(history_id)
        self.assertEqual(item['dish_dir'], '/tmp/abc')
        self.assertEqual(item['structuring_prompt_used'], 'PROMPT TEXT')

    def test_update_history_recipe_data_keeps_previous_version(self):
        job_id = create_job('https://example.com/undo-test')
        history_id = create_history_entry(
            job_id=job_id, url='https://example.com/undo-test',
            video_title='Vid', recipe_name='Old', recipe_data={'name': 'Old'},
            thumbnail_path=None, thumbnail_data=None, status='success',
        )
        update_history_recipe_data(history_id, {'name': 'New'}, 'NEW PROMPT')
        item = get_history_entry(history_id)
        self.assertEqual(item['recipe_data']['name'], 'New')
        self.assertIn('Old', item['previous_recipe_data'])
        self.assertEqual(item['structuring_prompt_used'], 'NEW PROMPT')


class RerunStructuringTests(unittest.TestCase):
    def test_missing_dish_dir_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            rerun_structuring('/tmp/definitely-does-not-exist-xyz', 'https://x.test')

    def test_missing_transcript_cache_raises_file_not_found(self):
        empty_dir = tempfile.mkdtemp()
        with self.assertRaises(FileNotFoundError):
            rerun_structuring(empty_dir, 'https://x.test')

    def test_rerun_uses_cached_material(self):
        dish_dir = tempfile.mkdtemp()
        with open(os.path.join(dish_dir, 'transcription_he.txt'), 'w') as f:
            f.write('cached transcript')
        with open(os.path.join(dish_dir, 'caption.txt'), 'w') as f:
            f.write('cached caption')

        import chef as chef_module
        original_chef = chef_module.Chef

        class FakeChef:
            def __init__(self, source_url, description, transcription, **kw):
                self.description = description
                self.transcription = transcription

            def create_recipe(self, **kw):
                return {'name': 'fake', 'recipeIngredients': [], 'recipeIngredient': []}

        chef_module.Chef = FakeChef
        try:
            result = rerun_structuring(dish_dir, 'https://x.test')
        finally:
            chef_module.Chef = original_chef

        self.assertEqual(result['recipe_data']['name'], 'fake')
        self.assertIn('structuring_prompt_used', result)


if __name__ == "__main__":
    unittest.main()
