import unittest

from config import config, set_config_value


class TestStructuringPrompt(unittest.TestCase):
    def tearDown(self):
        set_config_value('custom_structuring_prompt', '')
        config.reload()

    def test_default_prompt_contains_guidance_and_fixed_suffix(self):
        from helpers import get_recipe_system_prompt, DEFAULT_STRUCTURING_GUIDANCE, get_structuring_fixed_suffix
        prompt = get_recipe_system_prompt()
        self.assertIn(DEFAULT_STRUCTURING_GUIDANCE.strip(), prompt)
        self.assertIn(get_structuring_fixed_suffix(), prompt)

    def test_custom_override_replaces_guidance_but_keeps_fixed_suffix(self):
        from helpers import get_recipe_system_prompt, DEFAULT_STRUCTURING_GUIDANCE, get_structuring_fixed_suffix
        set_config_value('custom_structuring_prompt', 'MY CUSTOM GUIDANCE')
        config.reload()
        prompt = get_recipe_system_prompt()
        self.assertIn('MY CUSTOM GUIDANCE', prompt)
        self.assertNotIn(DEFAULT_STRUCTURING_GUIDANCE.strip(), prompt)
        self.assertIn(get_structuring_fixed_suffix(), prompt)

    def test_whitespace_only_override_falls_back_to_default(self):
        from helpers import get_recipe_system_prompt, DEFAULT_STRUCTURING_GUIDANCE
        set_config_value('custom_structuring_prompt', '   \n  ')
        config.reload()
        prompt = get_recipe_system_prompt()
        self.assertIn(DEFAULT_STRUCTURING_GUIDANCE.strip(), prompt)


class TestVisionPrompt(unittest.TestCase):
    def tearDown(self):
        set_config_value('custom_vision_prompt', '')
        config.reload()

    def test_default_prompt_contains_guidance_and_fixed_suffix(self):
        from transcriber import Transcriber, DEFAULT_VISION_GUIDANCE, get_visual_text_fixed_suffix
        t = Transcriber.__new__(Transcriber)
        prompt = t._get_visual_text_prompt()
        self.assertIn(DEFAULT_VISION_GUIDANCE.strip(), prompt)
        self.assertIn(get_visual_text_fixed_suffix(), prompt)

    def test_custom_override_replaces_guidance_but_keeps_language_suffix(self):
        from transcriber import Transcriber, DEFAULT_VISION_GUIDANCE, get_visual_text_fixed_suffix
        set_config_value('custom_vision_prompt', 'MY CUSTOM VISION GUIDANCE')
        config.reload()
        t = Transcriber.__new__(Transcriber)
        prompt = t._get_visual_text_prompt()
        self.assertIn('MY CUSTOM VISION GUIDANCE', prompt)
        self.assertNotIn(DEFAULT_VISION_GUIDANCE.strip(), prompt)
        self.assertIn(get_visual_text_fixed_suffix(), prompt)


if __name__ == '__main__':
    unittest.main()
