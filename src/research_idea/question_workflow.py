"""Research questions developed through durable, revisable discussions.

The workflow ends at the research claim. Technical routes and experiment plans
belong to a separate, explicitly requested workflow.
"""
from __future__ import annotations

from copy import deepcopy
import time

from .store import digest, now


def _kind(checkpoint):
    return checkpoint.get('kind', 'problem')


def _confirmation(checkpoint):
    snapshot = {key: deepcopy(checkpoint.get(key)) for key in (
        'kind', 'checkpoint_id', 'revision', 'confirmed_revision', 'confirmed_at',
        'confirmed_by', 'source_key', 'current', 'revisions')}
    snapshot['kind'] = _kind(checkpoint)
    return snapshot


def _confirm(controller, checkpoint, cycle, *, explicit):
    """Save the chosen version and consume only this discussion's temporary notes."""
    from .conversation import after_continue
    store = controller.store
    checkpoint = deepcopy(checkpoint)
    checkpoint.setdefault('kind', 'problem')  # v0.4 checkpoints discussed problems.
    checkpoint.update(state='confirmed', confirmed_revision=checkpoint['revision'],
                      confirmed_at=now(), confirmed_by='/continue' if explicit else 'batch')
    cycle = deepcopy(cycle)
    cycle.setdefault('confirmations', {})[_kind(checkpoint)] = _confirmation(checkpoint)
    cycle['stage'] = 'deepen' if _kind(checkpoint) == 'direction' else 'frame'
    changes = {'problem_checkpoint': checkpoint, 'question_cycle': cycle}
    if explicit:
        changes['conversation_memory'] = after_continue(store)
    if _kind(checkpoint) == 'direction':
        changes['problem_exploration'] = checkpoint['current']
    else:
        changes['problem_model'] = checkpoint['current']
    store.set_many(changes)
    return checkpoint, cycle


def _sync_sources(controller, cycle):
    """Account for papers this workflow itself obtained, including before failure."""
    from .problem_dialogue import source_key
    store = controller.store
    cycle = deepcopy(cycle)
    cycle['source_key'] = source_key(controller)
    changes = {'question_cycle': cycle}
    checkpoint = store.get('problem_checkpoint')
    if checkpoint:
        checkpoint = deepcopy(checkpoint)
        checkpoint['source_key'] = cycle['source_key']
        changes['problem_checkpoint'] = checkpoint
    store.set_many(changes)
    return cycle


def _fresh_cycle(controller, previous):
    store = controller.store
    if previous:
        store.event('question_cycle_archived', previous)
    brief = store.get('research_brief')
    if brief:
        store.event('research_brief_archived', {
            'research_brief': brief, 'provenance': store.get('question_brief_provenance')})
    from .problem_dialogue import source_key
    cycle = {'created_at': now(), 'source_key': source_key(controller),
             'stage': 'reading', 'confirmations': {}}
    store.set_many({'question_cycle': cycle, 'research_brief': None,
                    'question_brief_provenance': None, 'problem_model': None,
                    'problem_exploration': None, 'cohort': None})
    return cycle


def _confirmation_view(snapshot):
    """A compact model view; complete versions remain in cycle/provenance."""
    view = {key: deepcopy(snapshot.get(key)) for key in (
        'kind', 'checkpoint_id', 'revision', 'confirmed_revision',
        'confirmed_by', 'confirmed_at')}
    current = snapshot.get('current') or {}
    if snapshot.get('kind') == 'direction':
        view['directions'] = [{key: item.get(key, '') for key in ('id', 'question')}
                              for item in current.get('problem_seeds', [])]
    else:
        view['selected_problems'] = [{key: item.get(key, '') for key in
            ('opportunity_id', 'selection_reason')} for item in current.get('selected_problems', [])]
    return view


def _handoff(controller, cycle, checkpoint):
    """Carry current decisions without duplicating full historical snapshots."""
    from .conversation import memory_context
    memory = memory_context(controller.store)
    return {
        'confirmed_revision': checkpoint['confirmed_revision'],
        'confirmed_by': checkpoint.get('confirmed_by'),
        'discussion_kind': _kind(checkpoint),
        'selected_problems': deepcopy(checkpoint['current'].get('selected_problems', [])),
        'stage_confirmations': {kind: _confirmation_view(snapshot)
            for kind, snapshot in cycle.get('confirmations', {}).items()},
        'user_decisions': controller.user_notes(),
        'research_intent': controller.store.get('research_intent'),
        'formulation': deepcopy(checkpoint['current'].get('formulation', [])),
        'memory_sources': memory.get('memory_sources', []),
    }


def run_questions(controller, interactive=False, continue_problem=False):
    """Read → discuss directions → discuss problems → state the research claim."""
    from .controller import BudgetExhausted, check_references
    from .problem_dialogue import WAITING_BY_KIND, open_checkpoint, source_key
    from .problem_discovery import argument_handoff, explore_problem_pool

    store = controller.store
    recovered = store.interrupt_running_tasks()
    if recovered:
        store.event('interrupted_tasks_recovered', {'count': recovered})
    store.set('workflow', 'question')
    checkpoint = store.get('problem_checkpoint')
    current_source = source_key(controller)
    valid = bool(checkpoint and checkpoint.get('source_key') == current_source)

    # A saved human discussion is a real pause, even when resumed in batch mode.
    if valid and checkpoint['state'] == 'discussing' and not continue_problem:
        store.set('status', WAITING_BY_KIND[_kind(checkpoint)])
        return
    if continue_problem:
        if not checkpoint or checkpoint.get('state') not in {'discussing', 'confirmed'}:
            raise ValueError('当前没有待讨论的问题。使用 /run 开始或恢复研究。')
        if store.get('pending_chat_message'):
            raise ValueError('上一条讨论尚未成功处理，请重新发送或补充意见，再 /continue；原消息已保存。')
        if not valid:
            raise ValueError('论文或研究范围已变化，请 /run 更新问题后再讨论。原对话和要点已保留。')

    cycle = store.get('question_cycle')
    # Interactive intent survives process restart and source invalidation. A
    # batch-shaped /run must not silently consume a saved human discussion.
    interactive = bool(interactive or (cycle or {}).get('interactive') or
                       (checkpoint and (checkpoint.get('state') == 'discussing' or
                                        checkpoint.get('confirmed_by') == '/continue')))
    if checkpoint and not valid:
        from .conversation import bind_discussion_memory
        store.event('problem_checkpoint_invalidated', checkpoint)
        store.set_many({'conversation_memory': bind_discussion_memory(store),
                        'problem_checkpoint': None})
        checkpoint = None
    if not cycle or cycle.get('source_key') != current_source:
        if valid:
            # Discussion can obtain new papers and update its own checkpoint.
            # Preserve prior stage decisions, or adopt a v0.4 checkpoint when
            # this project has no question-cycle record yet.
            cycle = deepcopy(cycle) if cycle else {'created_at': now(), 'confirmations': {}}
            cycle.update(source_key=current_source,
                         stage='deepen' if _kind(checkpoint) == 'direction' else 'frame')
            store.set('question_cycle', cycle)
        else:
            cycle = _fresh_cycle(controller, cycle)
    cycle['interactive'] = interactive
    store.set('question_cycle', cycle)
    if valid and continue_problem and checkpoint['state'] == 'discussing':
        checkpoint, cycle = _confirm(controller, checkpoint, cycle, explicit=True)
    elif valid and checkpoint['state'] == 'confirmed':
        # Recovery never asks the user to confirm the same version twice.
        cycle.setdefault('confirmations', {})[_kind(checkpoint)] = _confirmation(checkpoint)
        store.set('question_cycle', cycle)

    store.set('status', 'running')
    try:
        controller.phase = 'ideation'
        if not checkpoint:
            if cycle['stage'] == 'reading':
                controller.progress('[concept] 调研背景与主要方法，寻找几个值得深入讨论的问题。')
                try:
                    from .research_intent import ensure_intent
                    ensure_intent(controller)
                    if not cycle.get('search_complete'):
                        controller.initial_search()
                        cycle['search_complete'] = True
                    initial_ids = controller.initial_paper_ids()
                    initial_ids = [paper['id'] for paper in controller.reading_papers()
                                   if paper['id'] in initial_ids]
                    controller.retrieve_full_texts(initial_ids)
                    controller.orient_papers(initial_ids)
                finally:
                    cycle = _sync_sources(controller, cycle)
                cycle['stage'] = 'explore'
                store.set('question_cycle', cycle)
            context = controller.ideation_context()
            refs = lambda value: check_references(value,
                {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
            pool = explore_problem_pool(controller, context, refs)
            checkpoint = open_checkpoint(controller, pool, kind='direction')
            cycle.update(stage='direction', source_key=checkpoint['source_key'])
            store.set('question_cycle', cycle)
            if interactive:
                return
            checkpoint, cycle = _confirm(controller, checkpoint, cycle, explicit=False)

        if _kind(checkpoint) == 'direction':
            controller.progress('[analysis] 按讨论后的方向逐个深入，比较为什么值得优先研究。')
            try:
                problem = controller.discover_problems(pool=deepcopy(checkpoint['current']))
            finally:
                cycle = _sync_sources(controller, cycle)
            checkpoint = open_checkpoint(controller, problem, kind='problem')
            cycle.update(stage='problem', source_key=checkpoint['source_key'])
            store.set('question_cycle', cycle)
            if interactive:
                return
            checkpoint, cycle = _confirm(controller, checkpoint, cycle, explicit=False)

        problem = deepcopy(checkpoint['current'])
        context = controller.ideation_context()
        handoff = _handoff(controller, cycle, checkpoint)
        from .prompts import stage_version
        brief_key = digest([cycle['source_key'], problem, handoff,
                            context.get('research_intent'), stage_version('frame_question'), getattr(controller, 'skill_key', None),
                            {key: controller.config.get(key) for key in (
                                'backend', 'model', 'reasoning_effort', 'api_provider',
                                'base_url', 'codex_bin', 'codex_profile')}])
        provenance = store.get('question_brief_provenance') or {}
        if not store.get('research_brief') or provenance.get('key') != brief_key:
            def check_brief(value):
                # Identity and citation checks only; scientific judgments stay
                # in the discussion and model task, not string-based gates.
                fields = ('title', 'background', 'existing_methods', 'problem',
                          'motivation', 'research_claim', 'why_priority')
                if any(not isinstance(value.get(field), str) for field in fields):
                    raise ValueError('Describe the research question using the required text fields')
                check_references(value, {e['id'] for e in context['evidence']},
                                 {p['id'] for p in context['papers']})
            controller.progress('[concept] 整理背景、现有方法、问题、动机与研究主张。')
            brief = controller.task('frame_question', {
                **context, 'problem_model': problem, 'discussion_handoff': handoff,
                'argument_handoff': argument_handoff(problem)}, check_brief)
            store.set_many({'research_brief': brief, 'problem_model': problem,
                'question_brief_provenance': {'key': brief_key, 'created_at': now(),
                    'source_key': cycle['source_key'], 'confirmed_revision': checkpoint['confirmed_revision'],
                    'confirmed_by': checkpoint.get('confirmed_by'),
                    'selected_problems': deepcopy(problem.get('selected_problems', [])),
                    'stage_confirmations': deepcopy(cycle.get('confirmations', {}))}})
        cycle['stage'] = 'completed'
        store.set_many({'question_cycle': cycle, 'status': 'completed'})
        store.event('run_completed', {'workflow': 'question'})
    except KeyboardInterrupt:
        store.interrupt_running_tasks()
        store.set('status', 'interrupted')
        store.event('run_interrupted', {})
        raise
    except BudgetExhausted:
        store.set('status', 'budget_exhausted')
        raise
    except Exception:
        store.set('status', 'blocked')
        raise
    finally:
        store.set('elapsed_s', controller.previous_elapsed + time.monotonic() - controller.started)
