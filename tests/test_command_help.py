"""Command help must cover the real interface without starting work or changing settings."""
import argparse
import ast
from contextlib import redirect_stdout
import inspect
import io
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import AsyncMock, patch

from research_idea.chat import Chat, initialize
from research_idea.cli import build_parser, main
from research_idea.command_help import COMMANDS, COMMAND_HELP, COMMAND_SUMMARIES, help_text
from research_idea.config import load_config
from research_idea.store import Store


class CommandHelpTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_for_every_chat_command_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            initialize(build_parser().parse_args(['chat', '--project', str(project)]))
            events = []
            chat = Chat(project, lambda tag, text: events.append(text))
            original = load_config(project)
            with patch.object(chat, 'start', new_callable=AsyncMock) as start, \
                    patch.object(chat, 'stop', new_callable=AsyncMock) as stop, \
                    patch.object(chat, 'pick', new_callable=AsyncMock) as pick:
                for name in COMMANDS:
                    for query in (f'/help {name[1:]}', f'/help {name}', f'{name} --help', f'{name} -h'):
                        with self.subTest(query=query):
                            self.assertTrue(await chat.handle(query))
                            self.assertIn('用法：', events[-1])
                            self.assertIn('示例：', events[-1])
                start.assert_not_awaited()
                stop.assert_not_awaited()
                pick.assert_not_awaited()
            self.assertEqual(load_config(project), original)
            store = Store(project, readonly=True)
            try:
                self.assertIsNone(store.get('topic'))
                self.assertEqual(store.get('calls_used', 0), 0)
                self.assertEqual(store.get('chat_messages', []), [])
            finally:
                store.close()

    def test_help_covers_dispatched_commands_and_completion(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(Chat.handle)))
        handled = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == 'command':
                for operand in node.comparators:
                    handled.update(child.value for child in ast.walk(operand)
                                   if isinstance(child, ast.Constant) and isinstance(child.value, str)
                                   and child.value.startswith('/'))
        self.assertEqual(set(COMMANDS), handled)
        self.assertEqual(set(COMMAND_SUMMARIES), handled)
        overview = help_text()
        for name in handled:
            self.assertIn(name, overview)
            self.assertTrue(COMMAND_SUMMARIES[name])

    def test_detail_includes_parameters_examples_and_aliases(self):
        date = help_text('date')
        for example in ('/date rolling 12 6', '/date fixed', '/date conference latest', '/date conference window'):
            self.assertIn(example, date)
        budget = help_text('budget')
        self.assertIn('max_seconds', budget)
        self.assertIn('单位是秒', budget)
        self.assertIn('max_candidates', budget)
        self.assertEqual(help_text('quit'), help_text('exit'))
        self.assertEqual(help_text('--help'), help_text('help'))
        self.assertEqual(help_text('all').count('示例：'), len(COMMAND_HELP))
        with self.assertRaisesRegex(ValueError, '/help budget'):
            help_text('budegt')

    def test_terminal_subcommands_have_descriptions_examples_and_argument_help(self):
        def visit(parser):
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for sub in action.choices.values():
                        self.assertTrue(sub.description, sub.prog)
                        self.assertIn('示例：', sub.format_help(), sub.prog)
                        visit(sub)
                else:
                    self.assertTrue(action.help, (parser.prog, action.dest))
        visit(build_parser())

    def test_terminal_help_exits_without_running_or_initializing_project(self):
        parser = build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        commands = [[name] for name in sub.choices]
        commands += [['skills', name] for name in ('list', 'show', 'use', 'clear')]
        with patch('research_idea.cli.execute') as execute:
            for command in commands:
                with self.subTest(command=command), redirect_stdout(io.StringIO()) as output:
                    with self.assertRaises(SystemExit) as exit:
                        main([*command, '--help'])
                    self.assertEqual(exit.exception.code, 0)
                    self.assertIn('示例：', output.getvalue())
            execute.assert_not_called()
