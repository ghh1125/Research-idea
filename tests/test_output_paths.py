"""Stable result folders, relocation and legacy report access from the CLI."""
import asyncio
import io
import json
import tempfile
import unittest
from contextlib import chdir, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from research_idea.chat import Chat
from research_idea.chat_worker import idea_text
from research_idea.cli import main
from research_idea.config import load_config, write_config
from research_idea.output_paths import default_output_root, output_directory, saved_report
from research_idea.report import export_report
from research_idea.store import Store


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.store = Store(self.project)
        self.store.set('topic', '研究方向')
        write_config(self.project)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_default_is_source_checkout_not_launch_directory(self):
        checkout = Path(__file__).resolve().parents[1]
        with chdir(self.root):
            self.assertEqual(default_output_root(), checkout)
        with patch('research_idea.output_paths.default_output_root', return_value=self.root / 'code'):
            report, data = export_report(self.store)
        self.assertEqual(report.parent.parent, self.root / 'code')
        self.assertRegex(report.parent.name, r'^idea-\d{8}-\d{6}-\d{6}$')
        self.assertEqual(data.parent, report.parent)
        self.assertEqual(saved_report(self.store), report)

    def test_export_and_resume_reuse_folder_name_and_keep_old_copy_on_relocation(self):
        first, _ = export_report(self.store, self.root / 'first')
        self.store.close()
        self.store = Store(self.project)
        again, _ = export_report(self.store, self.root / 'first')
        moved, _ = export_report(self.store, self.root / 'second')
        self.assertEqual(first, again)
        self.assertEqual(first.parent.name, moved.parent.name)
        self.assertTrue(first.is_file())
        self.assertEqual(saved_report(self.store), moved)
        self.assertIn('研究方向', idea_text(self.project))

    def test_slash_output_moves_existing_report_without_model_calls(self):
        events = []
        chat = Chat(self.project, lambda tag, text: events.append((tag, text)))
        export_report(self.store, self.root / 'initial')
        name = self.store.get('output_folder')
        root = self.root / '结果 with spaces'
        with patch('research_idea.backends.make_backend') as backend:
            asyncio.run(chat.handle(f'/output "{root}"'))
            asyncio.run(chat.handle('/report'))
        backend.assert_not_called()
        self.assertEqual(load_config(self.project)['output_dir'], str(root))
        self.assertEqual(saved_report(self.store), root / name / 'report.md')
        self.assertTrue((root / name / 'report.json').is_file())
        self.assertIn('研究方向', events[-1][1])
        asyncio.run(chat.handle('/output'))
        self.assertIn(str(root / name), events[-1][1])

    def test_invalid_output_parent_does_not_change_config_or_saved_report(self):
        first, _ = export_report(self.store, self.root / 'initial')
        file = self.root / 'a file'
        file.write_text('keep this file')
        chat = Chat(self.project, lambda *_: None)
        with self.assertRaises(OSError):
            asyncio.run(chat.handle('/output ' + str(file)))
        self.assertEqual(load_config(self.project)['output_dir'], '')
        self.assertEqual(saved_report(self.store), first)

    def test_new_project_inherits_parent_but_gets_its_own_folder(self):
        chat = Chat(self.project, lambda *_: None)
        asyncio.run(chat.handle('/output ' + str(self.root / 'results')))
        chat.new_project('新的方向')
        fresh = Store(chat.project, readonly=True)
        try:
            self.assertNotEqual(fresh.get('output_folder'), self.store.get('output_folder'))
            self.assertEqual(load_config(chat.project)['output_dir'], str(self.root / 'results'))
            self.assertEqual(fresh.get('calls_used', 0), 0)
        finally:
            fresh.close()

    def test_legacy_report_remains_readable_before_export(self):
        old = self.project / 'outputs/report.md'
        old.parent.mkdir()
        old.write_text('旧项目的研究 Idea')
        self.assertEqual(idea_text(self.project), '旧项目的研究 Idea')
        modern, _ = export_report(self.store, self.root / 'modern')
        self.assertTrue(old.is_file())
        self.assertEqual(saved_report(self.store), modern)

    def test_cli_export_output_argument_is_a_parent_and_is_persisted(self):
        stdout = io.StringIO()
        root = self.root / 'chosen parent'
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(['export', '--project', str(self.project), '--output', str(root)])
        self.assertEqual(code, 0)
        report = Path(json.loads(stdout.getvalue())['markdown'])
        self.assertEqual(report.parent, root / self.store.get('output_folder'))
        self.assertEqual(load_config(self.project)['output_dir'], str(root))

    def test_relative_config_path_is_anchored_to_project(self):
        write_config(self.project, {'output_dir': '../results'})
        with chdir(self.root.parent):
            self.assertEqual(output_directory(self.store).parent, self.root / 'results')

    def test_reset_default_only_changes_parent(self):
        chat = Chat(self.project, lambda *_: None)
        name = self.store.get('output_folder')
        asyncio.run(chat.handle('/output ' + str(self.root / 'custom')))
        with patch('research_idea.output_paths.default_output_root', return_value=self.root / 'code'):
            asyncio.run(chat.handle('/output default'))
        self.assertEqual(load_config(self.project)['output_dir'], '')
        self.assertEqual(self.store.get('output_folder'), name)
