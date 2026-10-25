"""Full transcript plus incremental, source-linked user decisions.

History is never condensed in storage. Only the model-facing view is shortened;
replaced decisions stay in the ledger with their original message provenance.
"""
from copy import deepcopy
from .schema import CHAT as CHAT_SCHEMA
from .store import now

MEMORY_INSTRUCTIONS = """
同时维护用户研究要点。memory_updates 只提取用户明确表达的目标、纠正、选择、约束和偏好，
不要把你的建议、推测或论文内容写成用户决定。每项引用 supplied user message 的 id。
每项只记录一个可单独修订的意思。scope=research 保存持续的研究目标、范围、资源与表达要求；
scope=discussion 保存只在当前讨论期间生效的要求，例如先不提出方案。不要把临时暂停要求和
持续的跨任务范围、不要实验计划合并成一条。/continue 会结束 discussion 要求，保留 research 要点。
未限定时限的研究与输出要求默认 research；只有明确表示先不做、仅本次讨论或等继续后再做的要求才是 discussion。
不要把一句“先不提出方案”的时限扩展到后续所有要求，也不要给原话无时限的要求添加“当前讨论”等限制。
已有 active_memory 缺少 scope 时，本轮需要整理这些旧记录：replace 为单项明确范围的要点，
其余意思分别 add，或 remove 已失效项；不能因用户原意未变而跳过作用范围的整理。
add 使用空 entry_id；replace/remove 指向 active_memory 中的 id。用户更改主意时替换或移除旧项，
保留其他仍有效的要点；没有变化返回 []。避免把普通问句自动升级为选择，内容要保留条件和否定。
unreviewed_user_messages 包含尚未整理的早期消息，要一并考虑；最新明确纠正优先。
active_memory 是现行要点，recent_history 中被替换的旧决定只用于理解过程。
discussion_state=confirmed 表示用户已输入 /continue，历史中的“先不提出方案”等临时要求已经结束。
answer 通俗、直接回应当前问题，并说清本轮实际改了什么；不要假装执行检索或实验。
"""


def transcript(store):
    # Stable IDs for pre-feature transcripts, without changing original text.
    return [{**m, 'id': m.get('id', f'msg_{i + 1:06d}')}
            for i, m in enumerate(store.get('chat_messages', []))]


def append_message(store, role, content, **metadata):
    history = transcript(store)
    message = dict(id=f'msg_{len(history) + 1:06d}', role=role, content=content,
                   time=now(), **metadata)
    store.set('chat_messages', history + [message])
    return message


def memory_context(store):
    history = transcript(store)
    reviewed = set(store.get('memory_reviewed_messages', []))
    active = [item for item in store.get('conversation_memory', []) if item['active']]
    legacy_sources = {item['source_message_id'] for item in active if 'scope' not in item}
    return {
        'discussion_state': (store.get('problem_checkpoint') or {}).get('state', 'not_started'),
        'active_memory': active,
        'recent_history': history[-12:],
        'unreviewed_user_messages': [m for m in history if m['role'] == 'user'
                                     and (m['id'] not in reviewed or m['id'] in legacy_sources)],
    }


def research_notes(store):
    context = memory_context(store)
    confirmed = (store.get('problem_checkpoint') or {}).get('state') == 'confirmed'
    notes = [f"{m['content']}（用户消息 {m['source_message_id']}）" for m in context['active_memory']
             if not confirmed or m.get('scope', 'research') == 'research']
    # Legacy history and unsuccessful turns remain available until processed.
    notes += [m['content'] for m in context['unreviewed_user_messages']]
    return list(dict.fromkeys(notes))


def revised_memory(store, updates, supplied_user_ids):
    """Validate on a copy; no partially applied replacement on malformed output."""
    ledger = deepcopy(store.get('conversation_memory', []))
    users = {m['id']: m for m in transcript(store) if m['role'] == 'user'}
    touched = set()
    for change in updates:
        source = change['source_message_id']
        if source not in users or source not in supplied_user_ids:
            raise ValueError('Memory must cite a supplied user message, never an assistant claim')
        action, key = change['action'], change['entry_id']
        if action != 'remove' and not change['content'].strip():
            raise ValueError('A memory entry needs content')
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
            old.update(active=False, retired_by_message=source, retired_at=now())
        if action != 'remove':
            entry = dict(id=f'memory_{len(ledger) + 1:06d}', content=change['content'].strip(),
                         source_message_id=source, scope=change['scope'], active=True, created_at=now())
            if action == 'replace':
                entry['replaces'] = key
                old['replaced_by'] = entry['id']
            ledger.append(entry)
    if any(entry['active'] and 'scope' not in entry for entry in ledger):
        raise ValueError('Split legacy active memory into atomic research/discussion entries with explicit scope')
    return ledger


def after_continue(store):
    """End temporary discussion instructions, retaining their original provenance."""
    ledger = deepcopy(store.get('conversation_memory', []))
    for entry in ledger:
        if entry['active'] and entry.get('scope') == 'discussion':
            entry.update(active=False, retired_by_command='/continue', retired_at=now())
    return ledger


def finish_turn(store, output, supplied_user_ids, *, model=None, reasoning_effort=None, **changes):
    ledger = revised_memory(store, output['memory_updates'], supplied_user_ids)
    history = transcript(store)
    history.append(dict(id=f'msg_{len(history) + 1:06d}', role='assistant',
                        content=output['answer'], time=now(), model=model,
                        reasoning_effort=reasoning_effort))
    store.set_many({**changes, 'chat_messages': history, 'conversation_memory': ledger,
        'memory_reviewed_messages': sorted(set(store.get('memory_reviewed_messages', [])) | set(supplied_user_ids)),
        'pending_chat_message': None})


def memory_text(store):
    context = memory_context(store)
    lines = ['当前研究要点（用户纠正后会更新；原始对话完整保留）：']
    users = {m['id']: m for m in transcript(store)}
    for item in context['active_memory']:
        source = users.get(item['source_message_id'], {})
        scope = '本次讨论期间' if item.get('scope') == 'discussion' else '后续研究持续使用'
        lines += [f"\n• {item['content']}（{scope}）", f"  出处：{source.get('content', item['source_message_id'])}"]
    if len(lines) == 1:
        lines.append('尚无提炼的要点。')
    if context['unreviewed_user_messages']:
        lines.append('\n尚待处理的原始用户消息会原样传入后续讨论。')
    return '\n'.join(lines)
