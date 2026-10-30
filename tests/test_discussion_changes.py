"""A notice describes the saved result, including no-op and interrupted turns."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from research_idea.conversation import append_message, finish_turn, memory_text
from research_idea.discussion_changes import changes_text
from research_idea.store import Store


class DiscussionChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.store = Store(self.project)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def turn(self, text, updates, **changes):
        user = append_message(self.store, 'user', text)
        patch = [{**update, 'source_message_id': user['id']} for update in updates]
        finish_turn(self.store, {'answer': '讨论答复', 'memory_updates': patch}, {user['id']}, **changes)

    def test_memory_add_replace_remove_and_scope_are_visible_and_survive_reopen(self):
        self.turn('先聚焦单个任务。', [dict(action='add', entry_id='', scope='discussion', content='聚焦单个任务。')])
        self.assertIn('已记住（本次讨论）：聚焦单个任务。', changes_text(self.store.get('last_turn_changes')))
        self.turn('以后都保留跨任务的目标。', [dict(action='replace', entry_id='memory_000001',
            scope='research', content='保留跨任务的目标。')])
        self.assertIn('聚焦单个任务。（本次讨论） → 保留跨任务的目标。（持续研究）',
                      changes_text(self.store.get('last_turn_changes')))
        self.assertIn('最近一轮实际保存的改动', memory_text(self.store))
        reopened = Store(self.project, readonly=True)
        try:
            self.assertEqual(reopened.get('last_turn_changes'), self.store.get('last_turn_changes'))
        finally:
            reopened.close()
        self.turn('取消这个范围约束。', [dict(action='remove', entry_id='memory_000002', scope='research', content='')])
        self.assertIn('已取消要点：保留跨任务的目标。', changes_text(self.store.get('last_turn_changes')))

    def test_same_memory_content_is_not_reported_as_a_new_decision(self):
        self.turn('保留跨任务目标。', [dict(action='add', entry_id='', scope='research', content='跨任务目标')])
        self.turn('仍然保持这个目标。', [dict(action='replace', entry_id='memory_000001', scope='research', content='跨任务目标')])
        self.assertEqual(self.store.get('last_turn_changes')['changed'], [])

    def test_failed_memory_patch_does_not_publish_new_notice_or_partial_changes(self):
        self.turn('保留范围。', [dict(action='add', entry_id='', scope='research', content='保留范围')])
        previous = deepcopy(self.store.get('last_turn_changes'))
        with self.assertRaises(ValueError):
            self.turn('改成别的范围', [dict(action='replace', entry_id='missing', scope='research', content='另一个范围')])
        self.assertEqual(self.store.get('last_turn_changes'), previous)
        self.assertEqual(self.store.get('conversation_memory')[0]['content'], '保留范围')

    def test_changes_in_direction_pool_show_actual_add_remove_and_revision(self):
        old = {'kind': 'direction', 'revision': 1, 'current': {'background_logic': '研究协作',
               'problem_seeds': [{'id': 'a', 'question': '原问题甲', 'entry_reason': '原原因'},
                                 {'id': 'b', 'question': '原问题乙', 'entry_reason': '原因'}]}}
        self.store.set('problem_checkpoint', old)
        new = deepcopy(old)
        new['revision'] = 2
        new['current']['problem_seeds'] = [dict(id='a', question='修订问题甲', entry_reason='新的重要原因'),
                                          dict(id='c', question='新问题丙', entry_reason='另一个原因')]
        self.turn('修订这些方向。', [], problem_checkpoint=new)
        notice = changes_text(self.store.get('last_turn_changes'), full=True)
        self.assertIn('已修改方向「修订问题甲」的表述、成因与动机', notice)
        self.assertIn('新增方向：新问题丙', notice)
        self.assertIn('移出本轮讨论的方向：原问题乙', notice)
        self.assertIn('保持：背景与研究范围', notice)

    def test_compact_notice_keeps_both_sides_of_a_long_replacement(self):
        record = {'changed': ['已修改要点：旧要求' + '细节' * 150 + ' → 新要求' + '内容' * 150,
                              '第二项改动', '第三项改动'], 'unchanged': [], 'focus': ''}
        text = changes_text(record)
        self.assertIn('旧要求', text)
        self.assertIn('新要求', text)
        self.assertIn('/memory', text)
        self.assertNotIn('第三项改动', text)
        self.assertIn('第三项改动', changes_text(record, full=True))
