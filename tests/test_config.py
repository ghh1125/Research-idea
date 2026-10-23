"""Provider routing and configurable API limits survive project round trips."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_agent.backends.api import APIBackend
from research_agent.config import load_config, write_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_raw(self, values):
        lines = [f"{key} = {json.dumps(value)}" for key, value in values.items()]
        (self.project / "research.toml").write_text("\n".join(lines), encoding="utf-8")

    def test_missing_config_keeps_openai_defaults(self):
        config = load_config(self.project)
        self.assertEqual(config["api_key_env"], "OPENAI_API_KEY")
        self.assertEqual(APIBackend(config, self.project).url,
                         "https://api.openai.com/v1/chat/completions")

    def test_provider_only_switch_uses_native_anthropic_defaults(self):
        self.write_raw({"backend": "api", "api_provider": "anthropic"})
        config = load_config(self.project)
        self.assertEqual(config["api_key_env"], "ANTHROPIC_API_KEY")
        self.assertEqual(APIBackend(config, self.project).url,
                         "https://api.anthropic.com/v1/messages")

    def test_explicit_endpoint_and_key_are_preserved(self):
        for key_env in ["CUSTOM_RESEARCH_KEY", ""]:
            with self.subTest(key_env=key_env):
                self.write_raw({"api_provider": "anthropic",
                                "base_url": "http://127.0.0.1:9000/v1",
                                "api_key_env": key_env})
                config = load_config(self.project)
                self.assertEqual(config["base_url"], "http://127.0.0.1:9000/v1")
                self.assertEqual(config["api_key_env"], key_env)

    def test_write_anthropic_config_resolves_defaults_before_round_trip(self):
        write_config(self.project, {"backend": "api", "api_provider": "anthropic"})
        config = load_config(self.project)
        self.assertEqual(config["base_url"], "https://api.anthropic.com/v1")
        self.assertEqual(config["api_key_env"], "ANTHROPIC_API_KEY")

    def test_api_limits_and_compatibility_token_field_are_configurable(self):
        write_config(self.project, {"max_output_tokens": 1024,
                                    "api_max_tokens_field": "max_tokens"})
        config = load_config(self.project)
        self.assertEqual(config["max_output_tokens"], 1024)
        self.assertEqual(config["api_max_tokens_field"], "max_tokens")

    def test_invalid_api_settings_fail_before_network_or_file_creation(self):
        bad_settings = [
            {"max_output_tokens": 0}, {"max_output_tokens": True},
            {"max_output_tokens": 1.5}, {"api_max_tokens_field": "tokens"},
            {"api_max_tokens_field": 8}, {"api_provider": "unknown"},
            {"base_url": 10}, {"api_key_env": False}, {"unknown_setting": "x"},
        ]
        for values in bad_settings:
            with self.subTest(values=values):
                self.write_raw(values)
                with self.assertRaises(ValueError):
                    load_config(self.project)
                (self.project / "research.toml").unlink()
                with self.assertRaises(ValueError):
                    write_config(self.project, values)
                self.assertFalse((self.project / "research.toml").exists())


if __name__ == "__main__":
    unittest.main()
