import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp())

from mela import build_melarecipes_archive


class TestBuildMelarecipesArchive(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def _write_recipe(self, filename, title):
        path = os.path.join(self.tmp_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"title": title, "id": filename}, f)
        return path

    def test_bundles_multiple_recipes_into_one_zip(self):
        p1 = self._write_recipe("one.melarecipe", "Recipe One")
        p2 = self._write_recipe("two.melarecipe", "Recipe Two")

        archive_bytes = build_melarecipes_archive([p1, p2])

        buffer_path = os.path.join(self.tmp_dir, "out.melarecipes")
        with open(buffer_path, "wb") as f:
            f.write(archive_bytes)

        with zipfile.ZipFile(buffer_path) as zf:
            names = zf.namelist()
            self.assertEqual(set(names), {"one.melarecipe", "two.melarecipe"})
            self.assertEqual(json.loads(zf.read("one.melarecipe"))["title"], "Recipe One")
            self.assertEqual(json.loads(zf.read("two.melarecipe"))["title"], "Recipe Two")

    def test_returns_bytes_not_a_file_path(self):
        p1 = self._write_recipe("solo.melarecipe", "Solo")
        result = build_melarecipes_archive([p1])
        self.assertIsInstance(result, bytes)


if __name__ == "__main__":
    unittest.main()
