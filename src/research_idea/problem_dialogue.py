"""Durable pause between problem discovery and idea construction."""
from copy import deepcopy

from .conversation import MEMORY_INSTRUCTIONS, memory_context, revised_memory, finish_turn
from .store import digest, now

WAITING = 'awaiting_problem_discussion'
DISCUSSION_INSTRUCTIONS = """
研究停在问题讨论阶段，尚未提出 idea。围绕用户本轮消息，结合当前问题、已有方法和原文资料进行讨论。
先直接解释用户困惑的地方：到底什么事情做不到，为什么重要，现有方法正常发挥以后为什么仍可能留下它。
支持纠正原因、重新选择问题、提出新切口。只问问题不代表用户同意你的建议；保留其他候选的原论证。
合理猜想可以大胆推进，区分来源报告和推演。不能把“让模型准确判断/发现问题”当作解决难点的理由。
不要在此展开技术方案、实验计划或宣称检索已完成。引用事实使用提供的论文和 evidence IDs。
updated_problems 仅给出需要改动或新增的问题完整记录，未改动的留在原处；selected_problems
仅在实际调整重点时填写完整选择及理由，否则 []。追问需要解释时可以只答复，两者均为 []。
当前 problem_model 是正在讨论的工作版本，不代表用户已认可。你可以根据本轮讨论主动修改问题和
优先建议，无须用户逐字段批准；/continue 才会按当前版本推进。如果本轮分析改变了对原因或优先级的判断，
同步返回 updated_problems 或 selected_problems，不能只在 answer 口头否定旧论证、让后续仍沿用它。
answer 说明改了哪里、为什么，把自己的推荐标为当前建议，不伪装为用户已经选择。只解释而判断未变时可不改记录。
程序只在用户输入 /continue 后往下运行；普通对话即便提到“继续”也保持讨论状态。
""" + MEMORY_INSTRUCTIONS


def source_key(controller):
    ids = set(controller.initial_paper_ids())
    # Model/account changes do not erase the human's problem choice. Source or
    # scope changes do require updating the problem discussion on the new basis.
    return digest([controller.store.get('source_revision', 0), controller.store.get('topic'), controller.config['constraints'],
        controller.config['max_candidates'],
        {k: controller.config.get(k) for k in ('search_source', 'search_venues', 'max_papers',
            'search_date_mode', 'search_since', 'search_until', 'strategy_months', 'novelty_months',
            'conference_policy', 'search_cs_only', 'arxiv_categories', 'deep_reading',
            'source_chars', 'max_paper_read_chunks', 'max_followup_reads')},
        [{k: p.get(k) for k in ('id', 'text', 'abstract', 'content_kind')} for p in controller.store.rows('papers') if p['id'] in ids]])


def open_checkpoint(controller, problem):
    store = controller.store
    old = store.get('problem_checkpoint')
    if old:
        store.event('problem_checkpoint_archived', old)
    checkpoint = dict(state='discussing', revision=1, source_key=source_key(controller),
        original=deepcopy(problem), current=deepcopy(problem), revisions=[], created_at=now(),
        confirmed_revision=None, user_notes_at_open=controller.user_notes())
    store.set_many({'problem_checkpoint': checkpoint, 'status': WAITING})
    return checkpoint


def problem_text(store):
    checkpoint = store.get('problem_checkpoint') or {}
    problem = checkpoint.get('current', {})
    if not problem:
        return '还没有调研后的候选问题。输入 /run 开始。'
    from .citations import Citations
    citations = Citations.from_store(store)
    lines = ['## 调研后的问题 · 先讨论，再构思', '',
             '**背景：** ' + problem.get('research_frame', {}).get('literature_logic', '')]
    for route in problem.get('approach_landscape', []):
        lines += ['', '**现有方法 · ' + route['name'] + '**', route['principle'], route['achieved_progress']]
    chosen = {c['opportunity_id']: c['selection_reason'] for c in problem.get('selected_problems', [])}
    for i, case in enumerate(problem.get('opportunities', []), 1):
        lines += ['', f"### 问题 {i}：{case['question']}"]
        for field, label in [('prior_art_delta', '现有办法已经做了什么，为什么还会遇到困难'),
                             ('bottleneck_hypothesis', '我们对原因的判断'), ('derivation', '怎样影响原目标'),
                             ('why_it_matters', '为什么值得研究'), ('research_need', '由此需要推进什么')]:
            lines += ['', f'**{label}：** {case[field]}']
        if case.get('closest_work_ids'):
            lines += ['', '**相关论文：** ' + '；'.join(citations.paper(pid) for pid in case['closest_work_ids'])]
        if case['id'] in chosen:
            lines += ['', '**优先考虑这个问题的理由：** ' + chosen[case['id']]]
    lines += ['', '直接输入你的意见，可以追问、纠正或换一个问题。输入 /continue 后，按当前讨论结果继续构思动机、idea 和技术参考。']
    return citations.text('\n'.join(lines))


def discuss(controller, message):
    from .controller import check_references
    store = controller.store
    checkpoint = store.get('problem_checkpoint')
    context = controller.ideation_context()
    memory = memory_context(store)
    supplied = {m['id'] for m in memory['unreviewed_user_messages'] + memory['recent_history'] if m['role'] == 'user'}

    def revise(value):
        check_references(value, {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
        revised_memory(store, value['memory_updates'], supplied)
        working = deepcopy(checkpoint['current'])
        if not value['updated_problems'] and not value['selected_problems']:
            return working
        cases = {p['id']: p for p in working['opportunities']}
        updates = value['updated_problems']
        if len({p['id'] for p in updates}) != len(updates):
            raise ValueError('Update each problem once')
        routes = {r['id'] for r in context.get('discovery_plan', {}).get('research_routes', [])}
        for item in updates:
            if any(not item[k].strip() for k in ('id', 'question', 'prior_art_delta', 'bottleneck_hypothesis',
                    'derivation', 'why_it_matters', 'research_need')):
                raise ValueError('Explain the revised problem and why it matters')
            if not set(item['research_route_ids']) <= routes:
                raise ValueError('Use actual discovery route IDs')
            if item['basis'] == 'source_observation' and not item['evidence_ids']:
                raise ValueError('Observed problems need source evidence; inferred problems are hypotheses')
            cases[item['id']] = deepcopy(item)
        choices = value['selected_problems'] or working['selected_problems']
        ids = [c['opportunity_id'] for c in choices]
        if len(set(ids)) != len(ids) or not set(ids) <= set(cases) or len(ids) > controller.config['max_candidates']:
            raise ValueError('Choose existing problems within max_candidates')
        if not choices or any(not c['selection_reason'].strip() for c in choices):
            raise ValueError('Explain the current problem choice')
        working.update(opportunities=list(cases.values()), selected_problems=deepcopy(choices))
        working['problem'] = '；'.join(cases[c]['question'] for c in ids)
        working['research_frame']['research_question'] = working['problem']
        working['opportunity_types'] = list(dict.fromkeys(c['problem_origin'] for c in cases.values()))
        # Comparisons predate the dialogue; do not present them as re-evaluated.
        working['problem_comparisons'] = []
        return working

    result = controller.task('discuss_problem', {**context, **memory,
        'problem_model': checkpoint['current'], 'current_user_message': message}, revise, publish=False)
    working = revise(result)
    checkpoint = deepcopy(checkpoint)
    checkpoint['revision'] += 1
    checkpoint['current'] = working
    checkpoint['revisions'].append(dict(revision=checkpoint['revision'], source_message_id=message['id'],
        answer=result['answer'], updated_problems=result['updated_problems'],
        selected_problems=result['selected_problems'], time=now()))
    checkpoint['state'] = 'discussing'
    finish_turn(store, result, supplied, model=controller.config['model'],
        reasoning_effort=controller.config['reasoning_effort'],
        problem_checkpoint=checkpoint, problem_model=working, status=WAITING)
    return result['answer']
