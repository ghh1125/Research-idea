"""Describe committed discussion changes from data, independently of the model's answer."""
from __future__ import annotations


def _short(text, limit=160):
    text = ' '.join(str(text).split())
    if len(text) > limit and ' → ' in text:
        before, after = text.split(' → ', 1)
        half = (limit - 3) // 2
        before = before if len(before) <= half else before[:half - 1] + '…'
        after = after if len(after) <= half else after[:half - 1] + '…'
        return before + ' → ' + after
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _questions(current):
    return {item['id']: item for item in current.get('opportunities', current.get('problem_seeds', []))}


def _focus(current):
    cases = _questions(current)
    return '；'.join(cases[item['opportunity_id']]['question']
                    for item in current.get('selected_problems', []) if item['opportunity_id'] in cases)


def _active(entries):
    return {item['id']: item for item in entries if item['active']}


def saved_changes(before, after, old_memory, new_memory, old_reasons, new_reasons):
    """Compare successful versions; no schema, model call, or approval gate is added."""
    old, new = before.get('current', {}), after.get('current', {})
    changed, unchanged = [], []
    if before.get('research_intent') != after.get('research_intent') and after.get('research_intent'):
        changed.append('研究主线已更新：' + after['research_intent']['goal'] + '；' + after['research_intent']['interpretation'])
    old_choices = old.get('selected_problems', [])
    new_choices = new.get('selected_problems', [])
    if [x['opportunity_id'] for x in old_choices] != [x['opportunity_id'] for x in new_choices]:
        changed.append(f'优先问题调整：{_focus(old) or "尚未选择"} → {_focus(new) or "尚未选择"}')
    elif old_choices != new_choices:
        changed.append('优先选择的理由已更新：' + '；'.join(x['selection_reason'] for x in new_choices))

    old_frame, new_frame = old.get('research_frame', {}), new.get('research_frame', {})
    old_background = [old.get('background_logic'), *(old_frame.get(k) for k in ('user_goal', 'literature_logic', 'scope_connection'))]
    new_background = [new.get('background_logic'), *(new_frame.get(k) for k in ('user_goal', 'literature_logic', 'scope_connection'))]
    for label, previous, current in (
        ('背景与研究范围', old_background, new_background),
        ('现有方法梳理', old.get('approach_landscape'), new.get('approach_landscape')),
        ('跨论文认识', old.get('cross_paper_synthesis'), new.get('cross_paper_synthesis')),
    ):
        if previous != current:
            changed.append('已更新：' + label + '。')
        elif current and (not isinstance(current, list) or any(current)):
            unchanged.append(label)

    old_cases, new_cases = _questions(old), _questions(new)
    label = '方向' if after.get('kind') == 'direction' else '问题'
    for key, case in new_cases.items():
        previous = old_cases.get(key)
        if previous is None:
            changed.append(f'新增{label}：{case["question"]}')
        elif previous != case:
            fields = []
            for name, keys in (
                ('表述', ('question',)),
                ('成因与动机', ('entry_reason', 'derivation', 'bottleneck_hypothesis', 'why_it_matters', 'research_need', 'problem_origin')),
                ('已有工作对照', ('prior_art_delta', 'closest_work_ids')),
                ('依据', ('evidence_ids', 'basis', 'research_route_ids')),
            ):
                if any(previous.get(k) != case.get(k) for k in keys):
                    fields.append(name)
            changed.append(f'已修改{label}「{case["question"]}」的' + '、'.join(fields or ['论证']) + '。')
    for key, case in old_cases.items():
        if key not in new_cases:
            changed.append(f'移出本轮讨论的{label}：{case["question"]}')
    if old != new and not changed:
        changed.append('当前讨论稿已更新；完整内容见 /problems detail。')

    old_active, new_active = _active(old_memory), _active(new_memory)
    replaced = {item.get('replaces') for item in new_active.values()}
    scopes = {'research': '持续研究', 'discussion': '本次讨论'}
    for key, item in new_active.items():
        previous = old_active.get(key) or old_active.get(item.get('replaces'))
        if previous and (previous['content'], previous.get('scope')) == (item['content'], item.get('scope')):
            continue
        scope = scopes.get(item.get('scope'), '研究')
        if previous:
            old_scope = scopes.get(previous.get('scope'), '研究')
            changed.append(f'已修改要点：{previous["content"]}（{old_scope}） → {item["content"]}（{scope}）')
        else:
            changed.append(f'已记住（{scope}）：{item["content"]}')
    for key, item in old_active.items():
        if key not in new_active and key not in replaced:
            changed.append('已取消要点：' + item['content'])

    old_notes = _active(old_reasons)
    for key, item in _active(new_reasons).items():
        if key not in old_notes:
            label = {'user_objection': '已记录你的异议', 'analysis_revision': '已更新研究判断',
                     'open_question': '已记录讨论中的疑问'}.get(item['kind'], '已记录讨论理由')
            changed.append(f'{label}：{item["judgment"]}；原因：{item["reason"]}')

    # Keep changes to the research ahead of local formatting in the short notice.
    old_ids = {item['id'] for item in old_memory}
    for item in new_memory:
        if item['id'] not in old_ids and item.get('scope') == 'turn':
            changed.append('仅本轮采用（不延续到后续）：' + item['content'])

    return {'changed': changed, 'unchanged': unchanged, 'focus': _focus(new),
            'kind': after.get('kind', 'chat'), 'revision': after.get('revision')}


def changes_text(record, *, full=False):
    """Keep the live notice short; /memory can show every recorded change."""
    if not record:
        return ''
    changes = record['changed']
    selected = changes if full else changes[:2]
    lines = ['• ' + (text if full else _short(text)) for text in selected]
    if not changes:
        lines.append('本轮仅答复，已保存的问题稿和研究要点未修改。')
    keep = '保持：' + '、'.join(record['unchanged']) + '。' if record['unchanged'] else ''
    focus = '当前重点：' + record['focus'] if record['focus'] else ''
    if keep or focus:
        lines.append('• ' + (keep + focus if full else _short(keep + focus, 220)))
    if len(changes) > len(selected) or (not full and any(len(' '.join(t.split())) > 160 for t in selected)):
        lines.append('完整改动用 /memory 查看，当前讨论稿用 /problems detail 查看。')
    return '\n'.join(lines)
