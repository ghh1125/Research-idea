"""Local reply instructions expire without losing durable research decisions."""
from pathlib import Path
import tempfile
import unittest

from research_idea.conversation import (after_continue, append_message, finish_turn,
    memory_context, research_notes, transcript)
from research_idea.discussion_changes import changes_text
from research_idea.memory_scope import resolve_scope
from research_idea.store import Store


class MemoryScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def turn(self, source, entries):
        user = append_message(self.store, 'user', source)
        updates = [dict(action='add', entry_id='', content=content, scope=scope,
                        source_message_id=user['id']) for content, scope in entries]
        finish_turn(self.store, {'answer': '已答复。', 'memory_updates': updates}, {user['id']})
        return user

    def test_local_length_default_overrides_model_research_scope_and_survives_reopen(self):
        self.turn('整个研究不展开实验计划。请解释当前问题，最多250字。',
                  [('整个研究不展开实验计划。', 'research'), ('回答最多250字。', 'research')])
        ledger = self.store.get('conversation_memory')
        self.assertEqual(ledger[1]['scope'], 'turn')
        self.assertFalse(ledger[1]['active'])
        self.assertEqual(ledger[1]['expired_after_reply'], 'msg_000002')
        self.assertIn('仅本轮采用', changes_text(self.store.get('last_turn_changes'), full=True))
        self.assertIn('整个研究不展开实验计划', self.store.get('last_turn_changes')['changed'][0])
        reopened = Store(self.path, readonly=True)
        try:
            self.assertEqual([m['content'] for m in memory_context(reopened)['active_memory']],
                             ['整个研究不展开实验计划。'])
            self.assertNotIn('250', '\n'.join(research_notes(reopened)))
        finally:
            reopened.close()

    def test_explicit_turn_and_discussion_have_different_expiry(self):
        self.store.set('problem_checkpoint', dict(kind='problem', state='discussing', checkpoint_id='one'))
        self.turn('这轮不查文献；讨论期间先不定稿；始终保留跨任务目标。',
                  [('这轮不查文献。', 'turn'), ('讨论期间先不定稿。', 'discussion'),
                   ('始终保留跨任务目标。', 'research')])
        self.assertEqual([m['scope'] for m in memory_context(self.store)['active_memory']], ['discussion', 'research'])
        self.store.set('conversation_memory', after_continue(self.store))
        self.assertEqual([m['scope'] for m in memory_context(self.store)['active_memory']], ['research'])

    def test_old_turn_cannot_be_revived_as_a_permanent_preference(self):
        old = self.turn('最多250字。', [('最多250字。', 'turn')])
        user = append_message(self.store, 'user', '继续完整说明背景与问题。')
        finish_turn(self.store, {'answer': '完整说明。', 'memory_updates': [dict(action='add',
            entry_id='', scope='research', content='最多250字。', source_message_id=old['id'])]},
            {old['id'], user['id']})
        context = memory_context(self.store)
        self.assertEqual(context['active_memory'], [])
        self.assertTrue(all(m['context_status'] == 'turn_expired' for m in context['retired_memory']))

    def test_old_misclassified_record_is_corrected_from_original_words(self):
        user = append_message(self.store, 'user', '回答最多250字。')
        append_message(self.store, 'assistant', '已经回答。')
        self.store.set('memory_reviewed_messages', [user['id']])
        self.store.set('conversation_memory', [dict(id='memory_000001', active=True, scope='research',
            content='回答最多250字。', source_message_id=user['id'])])
        original = transcript(self.store)
        self.assertEqual(memory_context(self.store)['active_memory'], [])
        self.turn('后续请继续围绕多任务协作。', [('后续围绕多任务协作。', 'research')])
        ledger = self.store.get('conversation_memory')
        self.assertEqual(ledger[0]['scope'], 'turn')
        self.assertFalse(ledger[0]['active'])
        self.assertEqual(transcript(self.store)[:2], original)

    def test_failed_output_does_not_partially_change_memory(self):
        self.turn('以后每次回答最多250字。', [('回答最多250字。', 'research')])
        before = self.store.get('conversation_memory')
        user = append_message(self.store, 'user', '这次用三句话。')
        with self.assertRaises(ValueError):
            finish_turn(self.store, {'answer': '答复', 'memory_updates': [dict(action='add',
                entry_id='', scope='turn', content='三句话', source_message_id='not-a-user')]}, {user['id']})
        self.assertEqual(self.store.get('conversation_memory'), before)

    def test_one_reply_exception_does_not_erase_standing_preference(self):
        self.turn('以后每次回答最多250字。', [('回答最多250字。', 'research')])
        user = append_message(self.store, 'user', '这次回答可以写到500字。')
        # Even if the model emits replace instead of add, this is a local exception.
        finish_turn(self.store, {'answer': '较长的本轮答复。', 'memory_updates': [dict(action='replace',
            entry_id='memory_000001', scope='research', content='回答可以写到500字。',
            source_message_id=user['id'])]}, {user['id']})
        active = memory_context(self.store)['active_memory']
        self.assertEqual([item['content'] for item in active], ['回答最多250字。'])
        ledger = self.store.get('conversation_memory')
        self.assertEqual(ledger[1]['scope'], 'turn')
        self.assertEqual(ledger[1]['overrides'], 'memory_000001')
        self.assertFalse(ledger[1]['active'])

    def test_scope_markers_belong_to_the_matching_request(self):
        cases = [
            ('回答最多250字。', '整个研究不要实验计划。最多250字。', 'turn'),
            ('回答最多250字。', '以后每次回答最多250字。', 'research'),
            ('最多250字。', '最终报告最多250字。', 'research'),
            ('回答最多250字。', '以后每次用通俗语言。最多250字。', 'turn'),
            ('用通俗语言回答。', '以后每次用通俗语言。最多250字。', 'research'),
            ('用通俗语言回答。', '以后都用通俗语言，这次最多250字。', 'research'),
            ('回答最多250字。', '以后都用通俗语言，这次最多250字。', 'turn'),
            ('回答最多250字。', '以后所有回答，最多250字。', 'research'),
            ('用通俗语言回答。', '这次不查文献，以后用通俗语言回答。', 'research'),
            ('以后回答最多250字。', '这次回答最多250字。', 'turn'),
            ('用表格回答。', '讨论期间用表格回答。', 'discussion'),
            ('用表格回答。', '本次讨论期间用表格回答。', 'discussion'),
            ('Answer in 3 sentences.', 'Keep this reply to 3 sentences.', 'turn'),
            ('Answer in 3 sentences.', 'From now on, answer in 3 sentences.', 'research'),
            ('解释得详细一点。', '解释得详细一点。', 'turn'),
            ('研究模型处理250字上下文的能力。', '研究模型处理250字上下文的能力。', 'research'),
            ('整个研究不要实验计划。', '整个研究不要实验计划。请简短回答。', 'research'),
        ]
        for content, source, expected in cases:
            with self.subTest(source=source, content=content):
                self.assertEqual(resolve_scope(content, 'research', source), expected)

    def test_pending_turn_is_not_expired_before_any_reply(self):
        user = append_message(self.store, 'user', '最多250字。')
        self.store.set('conversation_memory', [dict(id='memory_000001', active=True, scope='turn',
            content='最多250字。', source_message_id=user['id'])])
        self.assertEqual(len(memory_context(self.store)['active_memory']), 1)
