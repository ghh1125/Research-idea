"""Opt-in live dialogue check; curated hypotheses, not a literature/novelty benchmark.

Run from an installed checkout:
  python tools/evaluate_discussion.py --live --project /tmp/research-dialogue-check
The six normal calls use the configured local Codex account. Outputs stay local.
Review actual replies and saved revisions using docs/discussion-evaluation.md.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from research_idea.backends import make_backend
from research_idea.config import DEFAULTS, write_config
from research_idea.controller import Controller
from research_idea.conversation import append_message
from research_idea.problem_dialogue import discuss, open_checkpoint
from research_idea.store import Store

TOPIC = '个人助理如何理解用户偏好随情境变化，而不是把一次选择永久当成偏好？'
TURNS = [
    '这个问题我还没想清楚，你帮我找一个关键点问我。本次讨论先不查论文，也不展开技术或实验。',
    '我不知道怎么判断。先把刚才问的区别解释得容易懂一点，不要换成一堆算法名。',
    '我不是说旧偏好过时了。一个人平时喜欢便宜的，招待朋友时愿意选贵的，两种偏好都还有效。我关心的是系统把有条件的选择误当成普遍要求。',
    '如果已有个性化推荐也研究情境，那我们只看周二午餐、两个人、两百元以内，是不是就新颖了？先不要查文献。',
    '不要继续问我，也不采用刚才那几个任意限制。直接整理当前背景、现有思路、问题和动机，说明纠正后究竟在研究什么。不要技术方案和实验计划。',
]


def setup(controller):
    """A transparent reasoning fixture, with no invented paper or empirical claim."""
    store = controller.store
    store.set_many({'topic': TOPIC, 'workflow': 'question', 'research_intent': dict(
        mode='refine', goal=TOPIC, goal_sources=[dict(message_id='topic', quote=TOPIC)],
        concerns=[], relationships=[], interpretation='讨论偏好变化背后的原因，允许用户纠正初始猜想。')})
    case = dict(id='preference', question='旧偏好过时后，助理为什么还会继续使用？',
        problem_origin='emerging_problem', basis='research_hypothesis',
        derivation='初始猜想是持续使用历史记录可能无法跟上需求变化；需要讨论它是否准确表达用户困难。',
        bottleneck_hypothesis='助理可能把过去选择当作持续有效的偏好。',
        why_it_matters='个人助理要利用过去经验减少用户重复解释，又要理解当前需要。',
        prior_art_delta='本测试的概念对照：历史记录支持复用，近期记录支持更新；没有提供论文，不作覆盖或新颖性结论。',
        research_need='弄清历史选择什么时候仍可指导当前服务。',
        evidence_ids=[], closest_work_ids=[], research_route_ids=[])
    frame = dict(user_goal=TOPIC, literature_logic='个人助理需要理解用户当前需要，同时利用过往经验。',
                 research_question=case['question'], scope_connection='从长期使用中的理解偏差讨论问题。')
    problem = dict(research_frame=frame, approach_landscape=[dict(name='概念对照，尚非文献综述',
        principle='考虑利用历史选择或近期选择理解用户。', achieved_progress='这是讨论设定，不是已验证研究结论。',
        paper_ids=[], evidence_ids=[])], problem=case['question'],
        observations=[], competing_explanations=[], unresolved_questions=[],
        opportunities=[case], opportunity_types=['emerging_problem'], evidence_ids=[],
        problem_comparisons=[], formulation=[], selected_problems=[dict(opportunity_id=case['id'],
        selection_reason='先讨论这个初始猜想，允许纠正其原因。')])
    store.set('problem_model', problem)
    open_checkpoint(controller, problem, kind='problem')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly enable paid/account model calls')
    parser.add_argument('--project', type=Path, required=True, help='A new output directory')
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--reasoning-effort', default='high')
    args = parser.parse_args()
    if not args.live:
        parser.error('Pass --live to run actual model calls; this is not part of the unit suite.')
    project = args.project.resolve()
    project.mkdir(parents=True, exist_ok=True)
    if any(project.iterdir()):
        parser.error('Use an empty project directory to keep independent runs separate.')
    config = dict(DEFAULTS, backend='codex', model=args.model, reasoning_effort=args.reasoning_effort,
                  auto_search=False, fetch_full_text=False, max_candidates=1, timeout_s=240,
                  max_calls=8, max_seconds=1200,
                  constraints='对话行为测试：使用给定的概念设定，不查文献，不声称已完成新颖性判断；不展开技术与实验。')
    write_config(project, config)
    store = Store(project)
    backend = make_backend(config, project)
    record = dict(started_at=datetime.now(timezone.utc).isoformat(), model=args.model,
                  reasoning_effort=args.reasoning_effort, fixture='curated hypotheses; no source retrieval', turns=[])
    start = time.monotonic()
    try:
        setup(Controller(store, backend, config))
        for i, text in enumerate(TURNS, 1):
            controller = Controller(store, backend, config, progress=lambda s: print(s, flush=True))
            message = append_message(store, 'user', text)
            answer = discuss(controller, message)
            record['turns'].append(dict(user=text, answer=answer,
                checkpoint=deepcopy(store.get('problem_checkpoint')),
                memory=deepcopy(store.get('conversation_memory')),
                reasoning_notes=deepcopy(store.get('reasoning_notes'))))
            print(f'\nTURN {i}\n{answer}\n', flush=True)
            (project / 'dialogue.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            # Reopen after every reply to exercise persistent handoff.
            store.close()
            store = Store(project)
        controller = Controller(store, backend, config, progress=lambda s: print(s, flush=True))
        controller.run_questions(interactive=True, continue_problem=True)
        record['final_brief'] = store.get('research_brief')
        record['status'] = store.get('status')
    finally:
        record.update(calls=store.get('calls_used', 0), elapsed_seconds=round(time.monotonic()-start, 1))
        (project / 'dialogue.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        store.close()
    print(json.dumps({k: record[k] for k in ('status', 'calls', 'elapsed_seconds')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
