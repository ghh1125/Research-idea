"""Full transcript plus incremental, source-linked user decisions.

History is never condensed in storage. Only the model-facing view is shortened;
replaced decisions stay in the ledger with their original message provenance.
"""
from copy import deepcopy
from collections import Counter
from itertools import zip_longest
import math
import re
import unicodedata
from .schema import CHAT as CHAT_SCHEMA
from .memory_scope import resolve_scope
from .store import now

MEMORY_INSTRUCTIONS = """
同时维护用户研究要点。memory_updates 只提取用户明确表达的目标、纠正、选择、约束和偏好，
不要把你的建议、推测或论文内容写成用户决定。每项引用 supplied user message 的 id。
每项只记录一个可单独修订的意思。scope=research 保存持续的研究目标、范围、资源与表达要求；
scope=discussion 保存只在当前讨论阶段生效的要求，例如先不提出方案、等 /continue 后再推进。
scope=turn 保存仅约束本轮答复的要求，例如最多250字、用三句话、列成表格、本轮不查文献；答复成功后自动结束。
研究目标、范围、资源约束可以持续保留；局部回复的长度、格式、详略不能默认升级为长期偏好。
“请简短回答”“最多250字”默认 turn；“以后每次简短回答”“最终报告最多250字”才是 research。
不要把临时要求和持续的跨任务范围、整个研究不要实验计划合并成一条。
/continue 会结束 discussion 要求，保留 research 要点；turn 不延续到下一轮，也不限制最终研究报告。
不要把一句“先不提出方案”的时限扩展到后续所有要求，也不要给原话无时限的要求添加“当前讨论”等限制。
已有 active_memory 缺少 scope 时，本轮整理其原话已完整供应的旧记录：replace 为单项明确范围的要点，
其余意思分别 add，或 remove 已失效项。原话只有节选时不要据此删除尚未读到的要求；未供应的旧项留到后续。
add 使用空 entry_id；replace/remove 指向 active_memory 中的 id。用户更改主意时替换或移除旧项。
本轮临时覆盖已有长期偏好时新增 turn 项，不撤销长期项；只有明确永久改口才 replace/remove 原偏好。
保留其他仍有效的要点；没有变化返回 []。避免把普通问句自动升级为选择，内容要保留条件和否定。
unreviewed_user_messages 是本轮选出的有限待整理原话，兼顾最新消息、最早未处理纠正和相关历史；
unreviewed_deferred_count 是未放入本轮的数量，它们仍完整保留，不代表已处理。最新明确纠正优先。
active_memory 是现行要点，memory_sources 给出其用户原话。retrieved_history 是按本轮问题从完整
历史找回的相关原话，不是新增指令；其中普通问句、假设和已被更改的旧选择不能直接恢复成决定。
retired_memory 说明这些原话中哪些要点已经替换或结束；最新明确纠正优先，但保留同一句中其他有效要求。
其中 turn_expired 表示仅对历史那次答复有效，即使在 recent_history 再次看到，也不要恢复为现行要求。
retrieval_hints 是来自当前问题和最近助手回复的查找线索，仅帮助理解“之前那个”等指代，不是用户决定。
recent_history 中的 assistant 回复只是讨论内容，不代表用户认可。需要追问更早内容时使用消息出处核对。
discussion 要求只属于产生时的 discussion_key/kind，不能把前一阶段的临时要求带进新阶段。
discussion_state=confirmed 表示本次 /continue 已结束本次讨论的临时要求，长期研究要求继续保留。
若原话标有 content_truncated，它只是所标字符范围的节选，不要猜测省略部分或据此删除其他要求。
answer 通俗、直接回应当前问题，并说清本轮实际改了什么；不要假装执行检索或实验。
"""


def transcript(store):
    # Stable IDs for pre-feature transcripts, without changing original text.
    return [{**m, 'id': m.get('id', f'msg_{i + 1:06d}')}
            for i, m in enumerate(store.get('chat_messages', []))]


def append_message(store, role, content, **metadata):
    history = transcript(store)
    checkpoint = store.get('problem_checkpoint') or {}
    metadata = {'discussion_key': discussion_key(checkpoint),
                'discussion_kind': checkpoint.get('kind', 'problem') if checkpoint else 'chat',
                **metadata}
    message = dict(id=f'msg_{len(history) + 1:06d}', role=role, content=content,
                   time=now(), **metadata)
    store.set('chat_messages', history + [message])
    return message


def discussion_key(checkpoint):
    """Identity belongs to the checkpoint instance, not its editable revision."""
    if not checkpoint:
        return 'chat:before-research'
    identity = checkpoint.get('checkpoint_id') or checkpoint.get('id') or checkpoint.get('created_at') or 'legacy'
    return f"{checkpoint.get('kind', 'problem')}:{identity}"


def _ledger(store):
    """Normalize reply lifetimes and bind old discussion entries on a copy."""
    ledger = deepcopy(store.get('conversation_memory', []))
    history = transcript(store)
    users = {m['id']: m for m in history if m['role'] == 'user'}
    last_reply = next((i for i in range(len(history) - 1, -1, -1) if history[i]['role'] == 'assistant'), -1)
    answered = {m['id'] for m in history[:max(0, last_reply)] if m['role'] == 'user'}
    checkpoint = store.get('problem_checkpoint') or {}
    for entry in ledger:
        source = users.get(entry.get('source_message_id'), {})
        if entry.get('active') and entry.get('scope'):
            scope = resolve_scope(entry['content'], entry['scope'], source.get('content', ''))
            if scope != entry['scope']:
                entry['scope_corrected_from'] = entry['scope']
                entry['scope'] = scope
            if scope == 'turn' and entry['source_message_id'] in answered:
                entry.update(active=False, expired_after_reply=history[last_reply]['id'])
        # Unscoped legacy entries may mix durable and temporary requirements;
        # preserve ownership now so a later split cannot bind the old pause to a new stage.
        if entry.get('scope') not in (None, 'discussion') or entry.get('discussion_key'):
            continue
        entry['discussion_key'] = source.get('discussion_key', discussion_key(checkpoint))
        entry['discussion_kind'] = source.get('discussion_kind', checkpoint.get('kind', 'problem') if checkpoint else 'chat')
    return ledger


def bind_discussion_memory(store):
    """Freeze legacy ownership before replacing a checkpoint; no semantic edits.

    The caller persists this returned ledger with the new checkpoint atomically.
    Unscoped legacy entries keep ownership but still need source-based splitting.
    """
    return _ledger(store)


_QUERY_STOP_WORDS = {'这个', '那个', '我们', '可以', '就是', '什么', '目前', '一个', '一下',
                     '觉得', '是否', '怎么', '如何', '需要', '还有', '现在', '继续',
                     '之前', '刚才', '前面', '上面', '那条', '这次', '先前',
                     'the', 'and', 'for', 'with', 'this', 'that', 'what', 'does', 'from',
                     'earlier', 'previous', 'above', 'again', 'it'}


def _normalized(text):
    return unicodedata.normalize('NFKC', text).casefold()


def _terms(text):
    text = _normalized(text)
    terms = set(re.findall(r'[a-z0-9][a-z0-9_+.-]*', text))
    # Character bigrams work for Chinese without a tokenizer or extra model call.
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        terms.update(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return terms - _QUERY_STOP_WORDS


def _ranked_history(history, query):
    terms = _terms(query)
    documents = [_terms(m.get('content', '')) for m in history]
    frequencies = Counter(term for document in documents for term in document)
    phrase = _normalized(query).strip()
    ranked = []
    for position, (message, document) in enumerate(zip(history, documents)):
        overlap = terms & document
        exact = bool(phrase and phrase in _normalized(message.get('content', '')))
        if not overlap and not exact:
            continue
        score = sum(1 + math.log((len(history) + 1) / (frequencies[t] + 1)) for t in overlap)
        score /= math.sqrt(max(1, len(document)))
        if exact:
            score += 2
        ranked.append((score, position, message))
    # The latest correction wins a tie; the original date/role stays visible.
    return [message for _, _, message in sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True)]


def _retrieval_hints(history, checkpoint):
    """Small, labelled cues; assistant text is never turned into a user source."""
    current = checkpoint.get('current') or {}
    cases = {item['id']: item for item in current.get('opportunities', [])}
    questions = [cases[choice['opportunity_id']]['question']
                 for choice in current.get('selected_problems', []) if choice['opportunity_id'] in cases]
    if not questions and current.get('problem'):
        questions = [current['problem']]
    if not questions:
        questions = [item['question'] for item in current.get('problem_seeds', [])[:4]]
    hints = []
    if questions:
        hints.append({'source': 'current_problem', 'text': '\n'.join(q[:300] for q in questions)[:1200]})
    recent_reply = next((m for m in reversed(history[-12:]) if m['role'] == 'assistant'), None)
    if recent_reply:
        view = _message_view(recent_reply, hints[0]['text'] if hints else '', max_chars=1200)
        hints.append({'source': 'assistant_reply', 'message_id': recent_reply['id'], 'text': view['content']})
    return hints


def _ranked_with_context(history, query, hints):
    """Keep explicit matches first, then reserve room for contextual recall."""
    direct = _ranked_history(history, query)
    if not hints:
        return direct
    ordered = direct[:3]
    rankings = [_ranked_history(history, hint['text']) for hint in hints] + [direct[3:]]
    for row in zip_longest(*rankings):
        ordered.extend(message for message in row if message is not None)
    return list({message['id']: message for message in ordered}.values())


def _excerpt_query(message, query, hints):
    """Keep explicit matches; use context to locate a passage for an unmatched follow-up."""
    terms = _terms(message.get('content', ''))
    if terms & _terms(query):
        return query
    queries = [query, *(hint['text'] for hint in hints)]
    return max(queries, key=lambda q: len(terms & _terms(q)) / math.sqrt(max(1, len(_terms(q)))))


def _message_view(message, query='', max_chars=1800):
    """A bounded, contiguous source excerpt; the stored message is never edited."""
    text = message.get('content', '')
    view = deepcopy(message)
    if len(text) <= max_chars:
        return view
    normalized = _normalized(text)
    matches = [normalized.find(term) for term in _terms(query) if term in normalized]
    # Keep enough preceding text to avoid displaying only the conclusion of a correction.
    start = max(0, min(matches) - max_chars // 3) if matches else 0
    start = min(start, max(0, len(text) - max_chars))
    view.update(content=text[start:start + max_chars], content_truncated=True,
                content_start=start, content_end=start + max_chars, content_length=len(text))
    return view


def _pending_selection(messages, query, legacy_sources, limit=12, hints=()):
    """Make progress on an old backlog while keeping the current turn first."""
    if not messages:
        return []
    ordered = [messages[-1], *messages[:3]]
    legacy = [message for message in messages if message['id'] in legacy_sources]
    ordered += (_ranked_with_context(legacy, query, hints) + legacy)[:3]
    ordered += _ranked_with_context(messages, query, hints) + messages
    selected = list({message['id']: message for message in ordered}.values())[:limit]
    selected_ids = {message['id'] for message in selected}
    # Priority determines inclusion; chronological order preserves corrections.
    return [message for message in messages if message['id'] in selected_ids]


class SuppliedUserIds(set):
    """Citation eligibility and complete-message review are separate facts."""
    def __init__(self, messages, legacy_entries=()):
        super().__init__(message['id'] for message in messages)
        self.complete_ids = {message['id'] for message in messages if not message.get('content_truncated')}
        self.legacy_entry_ids = {entry['id'] for entry in legacy_entries
                                 if entry['source_message_id'] in self.complete_ids}


def memory_context(store, query=''):
    history = transcript(store)
    reviewed = set(store.get('memory_reviewed_messages', []))
    checkpoint = store.get('problem_checkpoint') or {}
    current_key = discussion_key(checkpoint)
    ledger = _ledger(store)
    active = [item for item in ledger if item['active'] and
              (item.get('scope') != 'discussion' or
               (item['discussion_key'] == current_key and checkpoint.get('state') != 'confirmed'))]
    legacy_sources = {item['source_message_id'] for item in active if 'scope' not in item}
    recent = history[-12:]
    query = query or next((m['content'] for m in reversed(history) if m['role'] == 'user'), '')
    hints = _retrieval_hints(history, checkpoint)
    pending = [m for m in history if m['role'] == 'user'
               and (m['id'] not in reviewed or m['id'] in legacy_sources)]
    selected = _pending_selection(pending, query, legacy_sources, hints=hints)
    unreviewed = [_message_view(m, _excerpt_query(m, query, hints)) for m in selected]
    pending_ids = {m['id'] for m in selected}
    # Old mixed summaries also consume context; expose only the migration batch.
    deferred_legacy = [item for item in active if 'scope' not in item and item['source_message_id'] not in pending_ids]
    active = [item for item in active if item not in deferred_legacy]
    source_ids = {item['source_message_id'] for item in active}
    source_messages = [m for m in history if m['id'] in source_ids and m['role'] == 'user']
    source_messages = list({m['id']: m for m in _ranked_with_context(source_messages, query, hints) + source_messages}.values())[:12]
    sources = [_message_view(m, ' '.join(item['content'] for item in active if item['source_message_id'] == m['id']))
               for m in source_messages]
    visible = {m['id'] for m in recent + unreviewed + sources}
    earlier = [m for m in history if m['role'] == 'user' and m['id'] not in visible]
    retrieved = [_message_view(m, _excerpt_query(m, query, hints))
                 for m in _ranked_with_context(earlier, query, hints)[:6]]
    historical_sources = {m['id'] for m in recent + sources + retrieved}
    active_ids = {item['id'] for item in active}
    active_view = [{**item, 'content': item['content'][:1200], 'content_truncated': True,
                    'content_length': len(item['content'])} if len(item['content']) > 1200 else item
                   for item in active]
    return {
        'discussion_state': checkpoint.get('state', 'not_started'),
        'discussion_kind': checkpoint.get('kind', 'problem') if checkpoint else 'chat',
        'discussion_key': current_key,
        'active_memory': active_view,
        'memory_sources': sources,
        'recent_history': [_message_view(m, query, max_chars=3000) for m in recent],
        'unreviewed_user_messages': unreviewed,
        'unreviewed_message_count': len(pending),
        'unreviewed_deferred_count': len(pending) - len(unreviewed),
        'unreviewed_partial_count': sum(bool(m.get('content_truncated')) for m in unreviewed),
        'legacy_memory_deferred_count': len(deferred_legacy),
        'memory_sources_deferred_count': len(source_ids) - len(sources),
        'retrieved_history': retrieved,
        'retired_memory': [{**item, 'context_status': ('turn_expired' if item.get('scope') == 'turn'
                            else 'retired') if not item['active'] else 'earlier_discussion'}
                          for item in ledger if (not item['active'] or
                           (item.get('scope') == 'discussion' and item['id'] not in active_ids))
                           and item['source_message_id'] in historical_sources],
        'history_message_count': len(history),
        'retrieval_query': query[:600],
        'retrieval_query_truncated': len(query) > 600,
        'retrieval_hints': hints,
    }


def supplied_user_ids(context):
    """All user sources actually supplied to this model call, including retrieval."""
    return SuppliedUserIds([message for key in ('recent_history', 'unreviewed_user_messages',
                                              'memory_sources', 'retrieved_history')
                           for message in context.get(key, []) if message['role'] == 'user'],
                          [entry for entry in context.get('active_memory', []) if 'scope' not in entry])


def research_notes(store):
    context = memory_context(store)
    confirmed = (store.get('problem_checkpoint') or {}).get('state') == 'confirmed'
    notes = [f"{m['content']}（用户消息 {m['source_message_id']}）" for m in context['active_memory']
             if not confirmed or m.get('scope', 'research') == 'research']
    # Legacy history and unsuccessful turns remain available until processed.
    notes += [m['content'] + (f"（用户消息 {m['id']} 的连续原话节选，其余仍保存在历史中。）"
                             if m.get('content_truncated') else '')
              for m in context['unreviewed_user_messages']]
    if context['unreviewed_deferred_count']:
        notes.append(f"另有 {context['unreviewed_deferred_count']} 条未整理原话保存在历史中，本轮未全部供应。")
    return list(dict.fromkeys(notes))


def revised_memory(store, updates, supplied_user_ids):
    """Validate on a copy; no partially applied replacement on malformed output."""
    ledger = _ledger(store)
    users = {m['id']: m for m in transcript(store) if m['role'] == 'user'}
    touched = set()
    for change in updates:
        source = change['source_message_id']
        if source not in users or source not in supplied_user_ids:
            raise ValueError('Memory must cite a supplied user message, never an assistant claim')
        action, key = change['action'], change['entry_id']
        if action not in {'add', 'replace', 'remove'} or change.get('scope') not in {'research', 'discussion', 'turn'}:
            raise ValueError('Memory needs a valid action and scope')
        if action != 'remove' and not change['content'].strip():
            raise ValueError('A memory entry needs content')
        scope = resolve_scope(change['content'], change['scope'], users[source]['content']) if action != 'remove' else None
        temporary_override = False
        if key in touched and key:
            raise ValueError('Update each memory entry once per turn')
        if action == 'add':
            if key:
                raise ValueError('New memory has no existing entry_id')
        else:
            old = next((m for m in ledger if m['id'] == key and m['active']), None)
            if old is None:
                raise ValueError('Replace/remove an active memory entry')
            touched.add(key)
            temporary_override = action == 'replace' and scope == 'turn' and old.get('scope') == 'research'
            if not temporary_override:
                old.update(active=False, retired_by_message=source, retired_at=now())
        if action != 'remove':
            entry = dict(id=f'memory_{len(ledger) + 1:06d}', content=change['content'].strip(),
                         source_message_id=source, scope=scope, active=True, created_at=now())
            if scope != change['scope']:
                entry['scope_corrected_from'] = change['scope']
            if scope == 'discussion':
                message = users[source]
                checkpoint = store.get('problem_checkpoint') or {}
                earlier = next((item for item in ledger if item.get('source_message_id') == source
                                and item.get('discussion_key')), {})
                entry['discussion_key'] = message.get('discussion_key', earlier.get('discussion_key', discussion_key(checkpoint)))
                entry['discussion_kind'] = message.get('discussion_kind', earlier.get('discussion_kind',
                    checkpoint.get('kind', 'problem') if checkpoint else 'chat'))
            if action == 'replace':
                if temporary_override:
                    entry['overrides'] = key
                else:
                    entry['replaces'] = key
                    old['replaced_by'] = entry['id']
            ledger.append(entry)
    complete_ids = getattr(supplied_user_ids, 'complete_ids', supplied_user_ids)
    legacy_ids = getattr(supplied_user_ids, 'legacy_entry_ids', None)
    if any(entry['active'] and 'scope' not in entry and entry['source_message_id'] in complete_ids
           and (legacy_ids is None or entry['id'] in legacy_ids)
           for entry in ledger):
        raise ValueError('Split legacy active memory into atomic research/discussion/turn entries with explicit scope')
    return ledger


def after_continue(store):
    """End temporary discussion instructions, retaining their original provenance."""
    ledger = _ledger(store)
    current_key = discussion_key(store.get('problem_checkpoint') or {})
    for entry in ledger:
        if entry['active'] and entry.get('scope') == 'discussion' and entry.get('discussion_key') == current_key:
            entry.update(active=False, retired_by_command='/continue', retired_at=now())
    return ledger


def finish_turn(store, output, supplied_user_ids, *, model=None, reasoning_effort=None, **changes):
    ledger = revised_memory(store, output['memory_updates'], supplied_user_ids)
    history = transcript(store)
    reply_id = f'msg_{len(history) + 1:06d}'
    for entry in ledger:
        if entry['active'] and entry.get('scope') == 'turn':
            entry.update(active=False, expired_after_reply=reply_id)
    checkpoint = store.get('problem_checkpoint') or {}
    from .discussion_changes import saved_changes
    old_reasons = store.get('reasoning_notes', [])
    record = saved_changes(checkpoint, changes.get('problem_checkpoint') or checkpoint,
        _ledger(store), ledger, old_reasons, changes.get('reasoning_notes', old_reasons))
    record['source_message_id'] = next((m['id'] for m in reversed(history) if m['role'] == 'user'), None)
    record['assistant_message_id'] = f'msg_{len(history) + 1:06d}'
    history.append(dict(id=f'msg_{len(history) + 1:06d}', role='assistant',
                        content=output['answer'], time=now(), model=model,
                        reasoning_effort=reasoning_effort, discussion_key=discussion_key(checkpoint),
                        discussion_kind=checkpoint.get('kind', 'problem') if checkpoint else 'chat'))
    store.set_many({**changes, 'chat_messages': history, 'conversation_memory': ledger,
        'last_turn_changes': record,
        'memory_reviewed_messages': sorted(set(store.get('memory_reviewed_messages', [])) |
                                          set(getattr(supplied_user_ids, 'complete_ids', supplied_user_ids))),
        'pending_chat_message': None})


def memory_text(store):
    context = memory_context(store)
    lines = ['当前研究要点（用户纠正后会更新；原始对话完整保留）：']
    users = {m['id']: m for m in transcript(store)}
    for item in context['active_memory']:
        source = users.get(item['source_message_id'], {})
        scope = {'discussion': '本次讨论期间', 'turn': '仅本轮答复'}.get(item.get('scope'), '后续研究持续使用')
        lines += [f"\n• {item['content']}（{scope}）", f"  出处：{source.get('content', item['source_message_id'])}"]
    if len(lines) == 1:
        lines.append('尚无提炼的要点。')
    intent = store.get('research_intent')
    if intent:
        lines.extend(['', '研究主线：' + intent['goal'], '当前理解：' + intent['interpretation']])
        for concern in intent['concerns']:
            label = '待讨论的假设' if concern['kind'] == 'hypothesis' else '希望解决的需要'
            lines.append('• ' + label + '：' + concern['statement'])
            for source in concern['sources']:
                lines.append('  用户原话：' + source['quote'])
        for link in intent['relationships']:
            lines.append('• 这些需要的关系：' + link['reason'])
    from .reasoning_memory import reasoning_context
    for note in reasoning_context(store):
        label = {'user_objection': '用户提出的疑问', 'analysis_revision': '研究判断的调整',
                 'open_question': '继续讨论的问题'}[note['kind']]
        lines += [f"\n• {label}：{note['judgment']}", f"  理由：{note['reason']}"]
        if note['user_quote']:
            lines.append('  用户原话：' + note['user_quote'])
        if note['revisit_when']:
            lines.append('  何时再看：' + note['revisit_when'])
    if context['unreviewed_user_messages']:
        lines.append('\n尚待处理的用户原话会分批带入后续讨论。')
    if context['unreviewed_deferred_count']:
        lines.append(f"另有 {context['unreviewed_deferred_count']} 条未整理原话保存在历史中，后续按相关性及顺序带入。")
    if store.get('last_turn_changes'):
        from .discussion_changes import changes_text
        lines.extend(['', '最近一轮实际保存的改动：', changes_text(store.get('last_turn_changes'), full=True)])
    return '\n'.join(lines)


def history_text(store, query=''):
    """Readable original-message lookup, including turns older than model context."""
    history = transcript(store)
    matches = _ranked_history(history, query) if query.strip() else history
    selected = matches[:20] if query.strip() else matches[-20:]
    heading = (f'完整会话中与「{query}」相关的 {len(matches)} 条消息（显示前 {len(selected)} 条）：'
               if query.strip() else f'原始会话 · 共 {len(history)} 条，显示最近 {len(selected)} 条：')
    lines = [heading]
    if not selected:
        lines.append('没有找到相关原话。' if query.strip() else '还没有会话记录。')
    for message in selected:
        view = _message_view(message, query, max_chars=1000)
        role = {'user': '你', 'assistant': '研究助手', 'system': '系统'}.get(message['role'], message['role'])
        kind = {'direction': '研究方向', 'problem': '问题讨论', 'idea': 'Idea 讨论'}.get(message.get('discussion_kind'), '')
        label = ' · '.join(filter(None, [message['id'], role, message.get('time', ''), kind]))
        lines.extend(['', label, view['content']])
        if view.get('content_truncated'):
            lines.append(f"（原文节选，第 {view['content_start'] + 1}–{view['content_end']} 字符；完整消息仍保存在项目中。）")
    lines.append('\n历史原话用于追溯；当前有效要求请用 /memory 查看。')
    return '\n'.join(lines)
