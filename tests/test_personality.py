import re
import unittest
from pathlib import Path


class NexoPersonalityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nexo_source = Path("src/agent/nexo.py").read_text(encoding="utf-8")
        cls.api_source = Path("src/api.py").read_text(encoding="utf-8")
        cls.mobile_source = Path("mobile/app.js").read_text(encoding="utf-8")
        cls.mobile_html = Path("mobile/index.html").read_text(encoding="utf-8")

    def test_four_personalities_are_defined(self):
        from agent.nexo import NexoCore

        self.assertEqual(
            {NexoCore.normalize_personality(value) for value in (
                "neutral", "aggressive", "comic", "conspiranoic",
            )},
            {"neutral", "aggressive", "comic", "conspiranoic"},
        )

    def test_neutral_is_default_and_legacy_base_alias(self):
        from agent.nexo import NexoCore

        self.assertEqual(NexoCore.normalize_personality(None), "neutral")
        self.assertEqual(NexoCore.normalize_personality("base"), "neutral")
        self.assertEqual(NexoCore.normalize_personality("normal"), "neutral")
        self.assertEqual(NexoCore.normalize_personality("natural"), "neutral")
        self.assertIn("independent judgment", NexoCore.personality_guidance("neutral"))

    def test_core_rejects_servile_behavior(self):
        from agent.nexo import NexoCore

        prompt = NexoCore.system_prompt("neutral")
        self.assertIn("does not simply mirror the user's opinion", prompt)
        self.assertIn("may disagree", prompt)
        self.assertIn("not a servile assistant", prompt)
        self.assertIn("must never invent certainty merely to please", prompt)

    def test_all_personalities_preserve_core_directive(self):
        from agent.nexo import NexoCore

        for mode in ("neutral", "aggressive", "comic", "conspiranoic"):
            prompt = NexoCore.system_prompt(mode)
            self.assertIn("NEXO is an independent AI assistant.", prompt)
            self.assertIn("must never invent certainty merely to please", prompt)

    def test_api_defaults_to_neutral(self):
        match = re.search(r'personality:\s*str\s*=\s*Field\(default="([^"]+)"', self.api_source)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "neutral")

    def test_mobile_defaults_to_neutral(self):
        match = re.search(r'personality:\s*"([^"]+)"', self.mobile_source)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "neutral")

    def test_mobile_exposes_all_four_choices(self):
        for value in ("neutral", "aggressive", "comic", "conspiranoic"):
            self.assertIn(f'data-personality="{value}"', self.mobile_html)

    def test_mobile_labels_neutral_explicitly(self):
        self.assertIn(">Neutral</button>", self.mobile_html)


if __name__ == "__main__":
    unittest.main()
