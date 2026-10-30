"""Long conversations retain raw corrections without reviving expired choices."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from research_idea.conversation import (after_continue, append_message, bind_discussion_memory, discussion_key,
    finish_turn, history_text, memory_context, research_notes, revised_memory,
    supplied_user_ids, transcript)
from research_idea.store import Store


class ConversationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def checkpoint(self, kind, identity, state='discussing'):
        checkpoint = dict(kind=kind, checkpoint_id=identity, state=state, revision=1,
                          created_at=f'2026-10-25T12:{identity[-1]}0:00+00:00')
        self.store.set('problem_checkpoint', checkpoint)
        return checkpoint

    def turn(self, content, memories=()):
        user = append_message(self.store, 'user', content)
        updates = [dict(action='add', entry_id='', scope=scope, content=note,
                        source_message_id=user['id']) for scope, note in memories]
        finish_turn(self.store, dict(answer='讨论答复。', memory_updates=updates), {user['id']})
        return user

    def later_turns(self):
        for index in range(16):
            self.turn(f'讨论界面的文字排版 {index}')

    def test_reviewed_but_unsummarized_early_correction_is_retrieved(self):
        first = self.turn('不要把共享状态当成可靠的信息来源；需要考虑状态的更新时间。')
        self.later_turns()
        context = memory_context(self.store, '共享状态的更新时间')
        self.assertEqual(context['unreviewed_user_messages'], [])
        self.assertNotIn(first['id'], {m['id'] for m in context['recent_history']})
        self.assertIn(first, context['retrieved_history'])
        self.assertIn(first['id'], supplied_user_ids(context))
        self.assertEqual(transcript(self.store)[0]['content'], first['content'])

    def test_default_query_uses_latest_user_message(self):
        first = self.turn('我们的关键约束是不能访问模型梯度。')
        self.later_turns()
        self.turn('模型梯度这个约束你还记得吗？')
        context = memory_context(self.store)
        self.assertIn(first, context['retrieved_history'])
        self.assertEqual(context['retrieval_query'], '模型梯度这个约束你还记得吗？')

    def test_vague_followup_recalls_correction_from_current_selected_problem(self):
        early = self.turn('共享状态的更新时间必须考虑，不能把过期状态当成可靠依据。')
        self.later_turns()
        checkpoint = self.checkpoint('problem', 'stage2')
        checkpoint['current'] = {
            'opportunities': [{'id': 'p1', 'question': '共享状态的更新时间怎样影响协作？'}],
            'selected_problems': [{'opportunity_id': 'p1', 'selection_reason': '重要'}]}
        self.store.set('problem_checkpoint', checkpoint)
        context = memory_context(self.store, '之前那个解释不对，再想想')
        self.assertIn(early, context['retrieved_history'])
        self.assertEqual(context['retrieval_query'], '之前那个解释不对，再想想')
        self.assertEqual(context['retrieval_hints'][0]['source'], 'current_problem')
        self.assertEqual(context['active_memory'], [])
        self.assertIn(early['id'], supplied_user_ids(context))

    def test_recent_reply_helps_recall_but_is_not_a_user_decision(self):
        early = self.turn('Do not assume the feedback delay is fixed across environments.')
        self.later_turns()
        reply = append_message(self.store, 'assistant', 'We are discussing feedback delay across environments.')
        context = memory_context(self.store, 'That earlier explanation is wrong. Why?')
        self.assertIn(early, context['retrieved_history'])
        self.assertNotIn(reply['id'], supplied_user_ids(context))
        self.assertEqual(context['active_memory'], [])
        self.assertEqual(context['retrieval_hints'][-1]['message_id'], reply['id'])
        # Explicit /history searches stay literal, rather than silently expanding.
        self.assertIn('没有找到', history_text(self.store, 'unrelated-quasar'))

    def test_explicit_request_keeps_priority_over_contextual_matches(self):
        explicit = self.turn('GPU memory is limited to 24 GB; keep this resource constraint.')
        for index in range(12):
            self.turn(f'关于共享状态的更新时间，条件 {index} 不同。')
        self.later_turns()
        checkpoint = self.checkpoint('problem', 'stage2')
        checkpoint['current'] = {'problem': '共享状态的更新时间'}
        self.store.set('problem_checkpoint', checkpoint)
        context = memory_context(self.store, 'GPU memory resource constraint')
        self.assertEqual(context['retrieved_history'][0], explicit)
        self.assertLessEqual(len(context['retrieved_history']), 6)
        self.assertTrue(any('共享状态' in m['content'] for m in context['retrieved_history'][1:]))

    def test_contextual_long_excerpt_preserves_correction_and_retired_status(self):
        original = '排版说明。' * 600 + '取消固定反馈延迟的假设，要考虑反馈延迟随环境变化。' + '附注。' * 800
        early = self.turn(original)
        self.later_turns()
        checkpoint = self.checkpoint('problem', 'stage2')
        checkpoint['current'] = {'problem': '反馈延迟随环境变化'}
        self.store.set('problem_checkpoint', checkpoint)
        context = memory_context(self.store, '之前那个解释不对')
        recalled = next(m for m in context['retrieved_history'] if m['id'] == early['id'])
        self.assertIn('取消固定反馈延迟', recalled['content'])
        self.assertTrue(recalled['content_truncated'])
        self.assertLessEqual(len(recalled['content']), 1800)
        self.assertEqual(transcript(self.store)[0]['content'], original)
        self.assertNotIn(early['id'], supplied_user_ids(context).complete_ids)

    def test_explicit_excerpt_is_not_displaced_by_a_richer_problem_context(self):
        text = '共享状态的更新时间、反馈延迟、跨任务迁移与原因识别。' * 200
        early = self.turn(text + '设备只有一张 GPU，显存 24 GB。')
        self.later_turns()
        checkpoint = self.checkpoint('problem', 'stage2')
        checkpoint['current'] = {'problem': '共享状态的更新时间、反馈延迟、跨任务迁移与原因识别。'}
        self.store.set('problem_checkpoint', checkpoint)
        context = memory_context(self.store, 'GPU 24 GB')
        recalled = next(m for m in context['retrieved_history'] if m['id'] == early['id'])
        self.assertIn('显存 24 GB', recalled['content'])

    def test_contextual_recall_keeps_replaced_choices_retired_and_hints_bounded(self):
        early = self.turn('只研究固定反馈延迟。', [('research', '只研究固定反馈延迟。')])
        correction = append_message(self.store, 'user', '更正，要研究变化的反馈延迟。')
        finish_turn(self.store, dict(answer='已更正。', memory_updates=[dict(action='replace',
            entry_id='memory_000001', scope='research', content='研究变化的反馈延迟。',
            source_message_id=correction['id'])]), {correction['id']})
        self.later_turns()
        checkpoint = self.checkpoint('problem', 'stage2')
        checkpoint['current'] = {'problem': '固定反馈延迟的假设为什么不适用？' * 1000}
        self.store.set('problem_checkpoint', checkpoint)
        append_message(self.store, 'assistant', '固定反馈延迟的解释。' * 1000)
        context = memory_context(self.store, '之前那个解释')
        self.assertIn(early, context['retrieved_history'])
        self.assertEqual([m['content'] for m in context['active_memory']], ['研究变化的反馈延迟。'])
        self.assertTrue(any(m['context_status'] == 'retired' for m in context['retired_memory']))
        self.assertLessEqual(sum(len(h['text']) for h in context['retrieval_hints']), 2400)

    def test_active_memory_carries_original_source_outside_recent_window(self):
        first = self.turn('不是单个数据集的涨分，要讨论可跨任务使用的能力。',
                          [('research', '研究跨任务的能力。')])
        self.later_turns()
        context = memory_context(self.store, '技术路线')
        self.assertIn(first, context['memory_sources'])
        self.assertIn(first['id'], supplied_user_ids(context))
        self.assertNotIn(first, context['recent_history'])

    def test_retrieved_old_source_can_be_summarized_without_changing_original(self):
        first = self.turn('研究对象是连续变化的环境，不要固定任务规则。')
        self.later_turns()
        context = memory_context(self.store, '环境 任务规则')
        ledger = revised_memory(self.store, [dict(action='add', entry_id='', scope='research',
            content='研究持续变化的环境。', source_message_id=first['id'])], supplied_user_ids(context))
        self.assertEqual(ledger[0]['source_message_id'], first['id'])
        self.assertEqual(transcript(self.store)[0], first)

    def test_replaced_choice_has_retirement_context_and_does_not_revive(self):
        first = self.turn('只考虑公开权重模型。', [('research', '只考虑公开权重模型。')])
        newer = append_message(self.store, 'user', '更正：允许 API 模型，也不用再限制公开权重。')
        finish_turn(self.store, dict(answer='已更正。', memory_updates=[dict(action='replace',
            entry_id='memory_000001', scope='research', content='允许 API 模型。',
            source_message_id=newer['id'])]), {newer['id']})
        self.later_turns()
        context = memory_context(self.store, '公开权重模型')
        self.assertIn(first, context['retrieved_history'])
        self.assertEqual(context['retired_memory'][0]['replaced_by'], 'memory_000002')
        self.assertEqual(context['retired_memory'][0]['context_status'], 'retired')
        self.assertEqual([m['content'] for m in context['active_memory']], ['允许 API 模型。'])
        self.assertNotIn('只考虑公开权重模型', str(research_notes(self.store)))

    def test_removed_requirement_stays_removed_when_its_source_is_retrieved(self):
        first = self.turn('不要展开实验计划。', [('research', '不要展开实验计划。')])
        correction = append_message(self.store, 'user', '取消刚才不要实验计划的要求。')
        finish_turn(self.store, dict(answer='已取消。', memory_updates=[dict(action='remove',
            entry_id='memory_000001', scope='research', content='', source_message_id=correction['id'])]),
            {correction['id']})
        self.later_turns()
        context = memory_context(self.store, '实验计划')
        self.assertIn(first, context['retrieved_history'])
        self.assertEqual(context['active_memory'], [])
        self.assertEqual(context['retired_memory'][0]['retired_by_message'], correction['id'])
        self.assertEqual(research_notes(self.store), [])

    def test_continue_only_retires_current_discussion(self):
        direction = self.checkpoint('direction', 'stage1')
        self.turn('先比较方向，不要展开问题；始终关注多任务。', [
            ('discussion', '先比较方向，不展开问题。'), ('research', '关注多任务。')])
        problem = self.checkpoint('problem', 'stage2')
        self.turn('这次先解释关键困难，不给具体方法。', [('discussion', '先解释困难，不给方法。')])
        context = memory_context(self.store)
        self.assertEqual([m['content'] for m in context['active_memory']], ['关注多任务。', '先解释困难，不给方法。'])
        ledger = after_continue(self.store)
        self.assertTrue(ledger[0]['active'])  # An unrelated checkpoint is not modified.
        self.assertTrue(ledger[1]['active'])
        self.assertFalse(ledger[2]['active'])
        self.assertEqual(ledger[0]['discussion_key'], discussion_key(direction))
        self.assertEqual(ledger[2]['discussion_key'], discussion_key(problem))

    def test_same_kind_new_instance_does_not_inherit_temporary_requests(self):
        self.checkpoint('problem', 'stage1')
        self.turn('先不要讨论动机。', [('discussion', '先不要讨论动机。')])
        self.checkpoint('problem', 'stage2')
        self.assertEqual(memory_context(self.store)['active_memory'], [])
        self.assertTrue(after_continue(self.store)[0]['active'])

    def test_editing_checkpoint_revision_does_not_change_ownership(self):
        checkpoint = self.checkpoint('problem', 'stage1')
        self.turn('先解释问题。', [('discussion', '先解释问题。')])
        checkpoint['revision'] = 5
        self.store.set('problem_checkpoint', checkpoint)
        self.assertEqual(len(memory_context(self.store)['active_memory']), 1)
        self.assertFalse(after_continue(self.store)[0]['active'])

    def test_late_extraction_keeps_source_stage(self):
        direction = self.checkpoint('direction', 'stage1')
        user = self.turn('本次先比较方向。')
        self.checkpoint('problem', 'stage2')
        ledger = revised_memory(self.store, [dict(action='add', entry_id='', scope='discussion',
            content='本次先比较方向。', source_message_id=user['id'])], {user['id']})
        self.store.set('conversation_memory', ledger)
        self.assertEqual(ledger[0]['discussion_key'], discussion_key(direction))
        self.assertEqual(memory_context(self.store)['active_memory'], [])

    def test_confirmed_checkpoint_hides_temporary_entries_even_before_persisted_cleanup(self):
        self.checkpoint('idea', 'stage1')
        self.turn('先不要写技术方案。', [('discussion', '先不要写技术方案。')])
        self.checkpoint('idea', 'stage1', state='confirmed')
        self.assertEqual(memory_context(self.store)['active_memory'], [])
        self.assertEqual(research_notes(self.store), [])

    def test_old_scoped_ledger_is_migrated_without_text_rewriting(self):
        checkpoint = dict(state='discussing', revision=2, created_at='2026-10-24T12:00:00+00:00')
        self.store.set('problem_checkpoint', checkpoint)
        self.store.set('chat_messages', [dict(role='user', content='先别给方案，长期保持跨任务目标。')])
        self.store.set('conversation_memory', [dict(id='memory_000001', active=True, scope='discussion',
            content='先别给方案。', source_message_id='msg_000001'),
            dict(id='memory_000002', active=True, scope='research', content='长期保持跨任务目标。',
                 source_message_id='msg_000001')])
        self.store.set('memory_reviewed_messages', ['msg_000001'])
        before = self.store.get('chat_messages')
        ledger = after_continue(self.store)
        self.assertFalse(ledger[0]['active'])
        self.assertEqual(ledger[0]['discussion_key'], discussion_key(checkpoint))
        self.assertTrue(ledger[1]['active'])
        self.assertEqual(self.store.get('chat_messages'), before)

    def test_freeze_old_scope_before_replacing_checkpoint(self):
        old = self.checkpoint('problem', 'stage1')
        self.store.set('chat_messages', [dict(role='user', content='先不要讨论动机。')])
        self.store.set('conversation_memory', [dict(id='memory_000001', active=True, scope='discussion',
            content='先不要讨论动机。', source_message_id='msg_000001')])
        self.store.set('memory_reviewed_messages', ['msg_000001'])
        # A controller can persist ownership atomically while reopening a stage.
        self.store.set_many({'conversation_memory': bind_discussion_memory(self.store),
            'problem_checkpoint': dict(kind='problem', checkpoint_id='stage2', state='discussing')})
        self.assertEqual(self.store.get('conversation_memory')[0]['discussion_key'], discussion_key(old))
        self.assertEqual(memory_context(self.store)['active_memory'], [])
        self.assertTrue(after_continue(self.store)[0]['active'])

    def test_legacy_mixed_entry_split_after_stage_change_keeps_temporary_ownership(self):
        old = self.checkpoint('direction', 'stage1')
        self.store.set('chat_messages', [dict(role='user', content='先别写方案，始终保持通俗。')])
        self.store.set('conversation_memory', [dict(id='old', active=True,
            content='先别写方案，始终保持通俗。', source_message_id='msg_000001')])
        self.store.set('memory_reviewed_messages', ['msg_000001'])
        self.store.set_many({'conversation_memory': bind_discussion_memory(self.store),
            'problem_checkpoint': dict(kind='problem', checkpoint_id='stage2', state='discussing')})
        context = memory_context(self.store)
        ledger = revised_memory(self.store, [dict(action='replace', entry_id='old', scope='discussion',
            content='先别写方案。', source_message_id='msg_000001'),
            dict(action='add', entry_id='', scope='research', content='始终保持通俗。',
                 source_message_id='msg_000001')], supplied_user_ids(context))
        self.store.set('conversation_memory', ledger)
        self.assertEqual(ledger[1]['discussion_key'], discussion_key(old))
        self.assertEqual([m['content'] for m in memory_context(self.store)['active_memory']], ['始终保持通俗。'])

    def test_unscoped_legacy_entries_require_explicit_scope_and_keep_original(self):
        self.store.set('chat_messages', [dict(role='user', content='先别写方案，同时要通俗。')])
        self.store.set('conversation_memory', [dict(id='old', content='先别写方案，同时要通俗。',
            active=True, source_message_id='msg_000001')])
        self.store.set('memory_reviewed_messages', ['msg_000001'])
        self.later_turns_without_memory_review()
        context = memory_context(self.store)
        self.assertEqual(context['unreviewed_user_messages'][0]['id'], 'msg_000001')
        with self.assertRaisesRegex(ValueError, 'scope'):
            revised_memory(self.store, [], supplied_user_ids(context))

    def later_turns_without_memory_review(self):
        for _ in range(20):
            append_message(self.store, 'assistant', '继续讨论。')

    def test_assistant_suggestion_cannot_be_recorded_as_user_choice(self):
        user = append_message(self.store, 'user', '有哪些研究角度？')
        assistant = append_message(self.store, 'assistant', '建议研究压缩记忆。')
        context = memory_context(self.store, '记忆')
        self.assertIn(assistant, context['recent_history'])
        self.assertNotIn(assistant['id'], supplied_user_ids(context))
        with self.assertRaisesRegex(ValueError, 'user message'):
            revised_memory(self.store, [dict(action='add', entry_id='', scope='research',
                content='选择压缩记忆。', source_message_id=assistant['id'])], {user['id'], assistant['id']})

    def test_retrieval_is_bounded_and_does_not_copy_whole_transcript(self):
        for index in range(40):
            self.turn(f'环境记忆细节 {index} ' + '对状态更新时间的分析。' * 500)
        original = deepcopy(self.store.get('chat_messages'))
        context = memory_context(self.store, '环境记忆')
        self.assertEqual(len(context['retrieved_history']), 6)
        self.assertTrue(all(len(m['content']) <= 1800 for m in context['retrieved_history']))
        self.assertTrue(all(len(m['content']) <= 3000 for m in context['recent_history']))
        self.assertTrue(context['retrieved_history'][0]['content_truncated'])
        self.assertEqual(self.store.get('chat_messages'), original)

    def test_history_search_reaches_old_turns_and_labels_roles(self):
        self.turn('不允许在线训练，只能离线训练。')
        assistant = append_message(self.store, 'assistant', '在线训练可以作为未来研究设想。')
        self.later_turns()
        result = history_text(self.store, '在线训练')
        self.assertIn('不允许在线训练', result)
        self.assertIn('msg_000001 · 你', result)
        self.assertIn(f"{assistant['id']} · 研究助手", result)
        self.assertIn('/memory', result)
        self.assertNotIn('msg_000001 · 你', history_text(self.store))
        self.assertIn('显示最近 20 条', history_text(self.store))

    def test_english_history_search_is_case_insensitive_and_missing_is_clear(self):
        self.turn('Use BM25 for retrieval, not a new model call.')
        self.assertIn('Use BM25', history_text(self.store, 'bm25'))
        self.assertIn('没有找到相关原话', history_text(self.store, 'zyxwvuts'))

    def test_history_survives_reopening_store(self):
        first = self.turn('保留最早的多任务纠正。', [('research', '保留多任务范围。')])
        self.later_turns()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(transcript(self.store)[0], first)
        self.assertIn(first, memory_context(self.store)['memory_sources'])

    def test_large_unreviewed_backlog_uses_bounded_excerpts_and_keeps_raw(self):
        original = [dict(role='user', content=f'原始要求 {i}。' + '不要缩到单一场景。' * 1000)
                    for i in range(120)]
        original[50]['content'] = '关键纠正：共享状态更新时间必须成为讨论的一部分。'
        self.store.set('chat_messages', original)
        context = memory_context(self.store, '共享状态更新时间')
        selected = context['unreviewed_user_messages']
        self.assertEqual(len(selected), 12)
        self.assertEqual(context['unreviewed_deferred_count'], 108)
        self.assertTrue(all(len(message['content']) <= 1800 for message in selected))
        self.assertIn('msg_000001', {message['id'] for message in selected})
        self.assertIn('msg_000120', {message['id'] for message in selected})
        self.assertIn('msg_000051', {message['id'] for message in selected})
        self.assertLess(sum(len(note) for note in research_notes(self.store)), 23000)
        self.assertEqual(self.store.get('chat_messages'), original)

    def test_unsupplied_and_partially_supplied_messages_are_not_marked_reviewed(self):
        self.store.set('chat_messages', [dict(role='user', content=f'原始要求 {i}。' + '资料' * 2500)
                                       for i in range(70)])
        context = memory_context(self.store, '原始要求')
        supplied = supplied_user_ids(context)
        self.assertGreater(len(supplied), 0)
        finish_turn(self.store, dict(answer='已讨论当前提供的原话片段。', memory_updates=[]), supplied)
        self.assertEqual(self.store.get('memory_reviewed_messages'), [])
        self.assertEqual(memory_context(self.store)['unreviewed_message_count'], 70)

    def test_short_backlog_advances_without_marking_hidden_messages_reviewed(self):
        self.store.set('chat_messages', [dict(role='user', content=f'要求 {i}：保留不同研究角度。')
                                       for i in range(80)])
        context = memory_context(self.store, '研究角度')
        supplied = supplied_user_ids(context)
        not_supplied = {message['id'] for message in transcript(self.store)} - supplied
        finish_turn(self.store, dict(answer='已整理这批原话。', memory_updates=[]), supplied)
        reviewed = set(self.store.get('memory_reviewed_messages'))
        self.assertEqual(reviewed, supplied)
        self.assertTrue(not_supplied.isdisjoint(reviewed))
        remaining = memory_context(self.store, '研究角度')
        self.assertEqual(remaining['unreviewed_message_count'], 80 - len(supplied))
        self.assertTrue(not_supplied.intersection({m['id'] for m in remaining['unreviewed_user_messages']}))

    def test_legacy_scope_migration_only_requires_supplied_batch(self):
        self.store.set('chat_messages', [dict(role='user', content=f'要求 {i}：保留研究范围。')
                                       for i in range(60)])
        self.store.set('conversation_memory', [dict(id=f'old_{i}', active=True,
            content=f'要求 {i}：保留研究范围。', source_message_id=f'msg_{i + 1:06d}') for i in range(60)])
        self.store.set('memory_reviewed_messages', [f'msg_{i + 1:06d}' for i in range(60)])
        context = memory_context(self.store, '研究范围')
        self.assertLessEqual(len(context['active_memory']), 12)
        self.assertEqual(context['legacy_memory_deferred_count'], 48)
        supplied = supplied_user_ids(context)
        updates = [dict(action='replace', entry_id=entry['id'], scope='research',
            content=entry['content'], source_message_id=entry['source_message_id'])
            for entry in context['active_memory']]
        ledger = revised_memory(self.store, updates, supplied)
        self.assertEqual(sum(item['active'] and 'scope' not in item for item in ledger), 48)
        self.assertEqual(sum(item['active'] and item.get('scope') == 'research' for item in ledger), 12)

    def test_truncated_legacy_source_does_not_force_guessing_its_missing_requirements(self):
        self.store.set('chat_messages', [dict(role='user', content='先讨论背景。' * 1500)])
        self.store.set('conversation_memory', [dict(id='old', active=True,
            content='先讨论背景。' * 1500, source_message_id='msg_000001')])
        context = memory_context(self.store)
        self.assertEqual(len(context['active_memory'][0]['content']), 1200)
        supplied = supplied_user_ids(context)
        self.assertEqual(supplied.complete_ids, set())
        ledger = revised_memory(self.store, [], supplied)
        self.assertTrue(ledger[0]['active'])
        self.assertNotIn('scope', ledger[0])


if __name__ == '__main__':
    unittest.main()
