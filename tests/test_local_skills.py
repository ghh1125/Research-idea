import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.local_skills import (ALL_STAGES, BUILTIN_NAMES, discover_skills, discovery_roots,
                                      builtin_skill_paths, load_selected_skills, LocalSkillError)


class LocalSkillsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.home = self.root / "home"
        self.project.mkdir()
        self.home.mkdir()
        self.builtin = self.root / "builtins"
        self.builtin_patcher = patch("research_idea.local_skills.BUILTIN_ROOT", self.builtin)
        self.builtin_patcher.start()
        self.addCleanup(self.builtin_patcher.stop)
        self.patcher = patch("research_idea.local_skills.Path.home", return_value=self.home)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.env = patch.dict(os.environ, {"CODEX_HOME": str(self.home / ".codex")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def skill(self, folder, name="ccf-idea-optimizer", description="Useful", body="Read evidence."):
        path = folder / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8")
        return path

    def test_discover_known_roots_and_stage_mapping(self):
        path = self.skill(self.project / ".claude/skills/idea")
        found = discover_skills(self.project)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], str(path))
        self.assertEqual(found[0]["suggested_stages"], ["map", "propose", "develop", "refine"])

    def test_multiline_description(self):
        self.skill(self.home / ".agents/skills/a", description=">-\n  One line\n  and another.")
        self.assertEqual(discover_skills(self.project)[0]["description"], "One line and another.")

    def test_no_ambient_activation(self):
        self.skill(self.project / ".codex/skills/a")
        with patch("research_idea.local_skills.discover_skills", side_effect=AssertionError("should not scan")):
            self.assertEqual(load_selected_skills([], self.project, []), [])

    def test_builtin_discovery_and_explicit_selection(self):
        self.assertEqual(builtin_skill_paths(), [])
        path = self.skill(self.builtin / "research-idea-motivation", name="research-idea-motivation")
        found = discover_skills(self.project)
        self.assertEqual(found[0]["origin"], "builtin")
        self.assertEqual(builtin_skill_paths(), [str(path)])
        self.assertIn("review", found[0]["suggested_stages"])
        self.assertEqual(load_selected_skills(builtin_skill_paths(), self.project, [])[0]["origin"], "builtin")

    def test_eight_namespaced_builtins_include_claims_audit(self):
        self.assertEqual(len(BUILTIN_NAMES), 8)
        for name in BUILTIN_NAMES:
            self.assertTrue(name.startswith("research-idea-"))
            self.skill(self.builtin / name, name=name)
        found = discover_skills(self.project)
        self.assertEqual({row["name"] for row in found}, set(BUILTIN_NAMES))
        self.assertEqual(len(builtin_skill_paths()), 8)
        audit = load_selected_skills(["research-idea-audit-claims"], self.project, [])[0]
        self.assertEqual(audit["stages"], ["audit_claims", "extract", "inspect_source", "develop", "refine", "review"])
        self.assertNotIn("propose", audit["stages"])

    def test_unknown_explicit_skill_includes_claims_audit_stage(self):
        self.skill(self.project / "custom", name="custom-audit-guidance")
        loaded = load_selected_skills(["custom"], self.project, [])
        self.assertEqual(loaded[0]["stages"], list(ALL_STAGES))
        self.assertIn("audit_claims", loaded[0]["stages"])
        self.assertIn("plan_search", loaded[0]["stages"])

    def test_exact_name_and_hash(self):
        path = self.skill(self.home / ".claude/skills/a")
        result = load_selected_skills(["ccf-idea-optimizer"], self.project, [])
        self.assertEqual(result[0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("Read evidence", result[0]["content"])

    def test_relative_path_and_reference_file(self):
        path = self.skill(self.project / "custom/a", name="custom")
        ref = path.parent / "notes.md"
        ref.write_text("Reference content", encoding="utf-8")
        result = load_selected_skills(["custom/a", "custom/a/notes.md"], self.project, [])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["name"], "notes")
        self.assertIn("inspect_source", result[1]["stages"])

    def test_ambiguous_name_has_no_precedence(self):
        self.skill(self.home / ".codex/skills/a")
        self.skill(self.project / ".claude/skills/b")
        with self.assertRaisesRegex(LocalSkillError, "Ambiguous"):
            load_selected_skills(["ccf-idea-optimizer"], self.project, [])

    def test_size_and_total_limits_not_truncated(self):
        path = self.skill(self.project / "a", body="x" * 33000)
        with self.assertRaisesRegex(LocalSkillError, "32 KiB"):
            load_selected_skills([str(path)], self.project, [])
        self.skill(self.project / "a", body="x" * 100)
        with self.assertRaisesRegex(LocalSkillError, "max_chars"):
            load_selected_skills([str(path)], self.project, [], max_chars=30)

    def test_bad_encoding_and_missing(self):
        p = self.project / "bad.md"
        p.write_bytes(b"\xff")
        for selector in [str(p), "missing", "absent/SKILL.md"]:
            with self.assertRaises(LocalSkillError):
                load_selected_skills([selector], self.project, [])

    def test_depth_limit_and_symlinks(self):
        root = self.project / "custom"
        self.skill(root / "a/b/c", name="depth3")
        self.skill(root / "a/b/c/d", name="depth4")
        external = self.root / "external"
        self.skill(external, name="external")
        (root / "linked").symlink_to(external, target_is_directory=True)
        found = discover_skills(self.project, [str(root)])
        self.assertEqual([x["name"] for x in found], ["depth3", "external"])
        found = discover_skills(self.project, [str(root / "linked")])
        self.assertEqual([x["name"] for x in found], ["external"])

    def test_linked_skill_by_name_without_target_subtree_scan(self):
        root = self.project / ".agents/skills"
        root.mkdir(parents=True)
        external = self.root / "outside-tree"
        path = self.skill(external, name="linked-skill")
        self.skill(external / "nested/other", name="not-discovered")
        (root / "linked").symlink_to(external, target_is_directory=True)
        found = discover_skills(self.project)
        self.assertEqual([x["name"] for x in found], ["linked-skill"])
        loaded = load_selected_skills(["linked-skill"], self.project, [])
        self.assertEqual(loaded[0]["path"], str(path))

    def test_linked_skill_file(self):
        outside = self.root / "outside"
        source = self.skill(outside, name="linked-file")
        directory = self.project / ".claude/skills/alias"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").symlink_to(source)
        self.assertEqual([x["name"] for x in discover_skills(self.project)], ["linked-file"])
        self.assertEqual(load_selected_skills(["linked-file"], self.project, [])[0]["path"], str(source))

    def test_deduplicate_same_selected_path(self):
        path = self.skill(self.project / ".claude/skills/a")
        result = load_selected_skills(["ccf-idea-optimizer", str(path)], self.project, [])
        self.assertEqual(len(result), 1)

    def test_codex_home_and_relative_extra_root(self):
        custom_home = self.root / "codex-other"
        self.skill(custom_home / "skills/a", name="custom-codex")
        self.skill(self.project / "extra/b", name="extra")
        with patch.dict(os.environ, {"CODEX_HOME": str(custom_home)}):
            self.assertEqual([x["name"] for x in discover_skills(self.project, ["extra"])], ["custom-codex", "extra"])
            self.assertIn(str(custom_home / "skills"), discovery_roots(self.project))


if __name__ == "__main__":
    unittest.main()
