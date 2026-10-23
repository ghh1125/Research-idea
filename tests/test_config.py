"""Provider routing and configurable API limits survive project round trips."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_idea.backends.api import APIBackend
from research_idea.config import load_config, write_config


class ConfigTests(unittest.TestCase):
    def test_reasoning_effort_round_trip_and_explicit_backend_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            write_config(path, {"model": "gpt-6.1-sol", "reasoning_effort": "high"})
            self.assertEqual(load_config(path)["reasoning_effort"], "high")
            for bad in ["unknown", 1, None]:
                with self.subTest(value=bad), self.assertRaises(ValueError):
                    write_config(path, {"reasoning_effort": bad})
            for backend in ["claude", "api"]:
                with self.subTest(backend=backend), self.assertRaisesRegex(ValueError, "requires backend=codex"):
                    write_config(path, {"backend": backend, "reasoning_effort": "high"})
            write_config(path, {"backend": "claude", "reasoning_effort": ""})

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

    def test_codex_and_skill_settings_round_trip(self):
        values = {"codex_bin": "/tmp/Codex App/codex", "codex_profile": "research",
                  "skill_paths": ["/tmp/研究/SKILL.md"], "skill_roots": ["/tmp/研究"],
                  "skill_max_chars": 9000, "builtin_skills": False}
        write_config(self.project, values)
        config = load_config(self.project)
        for key, value in values.items():
            self.assertEqual(config[key], value)

    def test_search_venues_select_openalex_and_full_text_setting_round_trips(self):
        write_config(self.project, {"search_venues": ["ACL", "EMNLP", "NAACL", "COLM"],
                                    "fetch_full_text": False})
        cfg = load_config(self.project)
        self.assertEqual(cfg["search_source"], "openalex")
        self.assertEqual(cfg["search_venues"], ["ACL", "EMNLP", "NAACL", "COLM"])
        self.assertFalse(cfg["fetch_full_text"])

    def test_invalid_search_settings_fail_before_writing(self):
        for values in [
            {"search_venues": "ACL"}, {"search_venues": [1]}, {"search_venues": [""]},
            {"search_venues": ["ACL"], "search_source": "arxiv"},
            {"fetch_full_text": "true"}, {"fetch_full_text": 0},
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                write_config(self.project, values)
        self.assertFalse((self.project / "research.toml").exists())

    def test_new_defaults_are_safe_and_lists_are_not_shared(self):
        first = load_config(self.project)
        self.assertEqual(first["codex_bin"], "codex")
        self.assertEqual(first["codex_profile"], "")
        self.assertEqual(first["skill_max_chars"], 48000)
        self.assertTrue(first["builtin_skills"])
        self.assertTrue(first["fetch_full_text"])
        first["skill_paths"].append("/tmp/a.md")
        first["skill_roots"].append("/tmp/skills")
        first["search_venues"].append("ACL")
        second = load_config(self.project)
        self.assertEqual(second["skill_paths"], [])
        self.assertEqual(second["skill_roots"], [])
        self.assertEqual(second["search_venues"], [])

    def test_invalid_codex_and_skill_settings_are_rejected(self):
        for values in [
            {"codex_bin": ""}, {"codex_bin": False}, {"codex_bin": "bad\x00name"},
            {"codex_profile": 1}, {"codex_profile": "bad\x00profile"},
            {"skill_paths": "one.md"}, {"skill_paths": [1]}, {"skill_paths": [""]},
            {"skill_roots": [" "]}, {"skill_roots": ["bad\x00path"]},
            {"skill_max_chars": 0}, {"skill_max_chars": True}, {"skill_max_chars": 1.1},
            {"builtin_skills": "true"}, {"builtin_skills": 1},
        ]:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    write_config(self.project, values)
                self.assertFalse((self.project / "research.toml").exists())

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
