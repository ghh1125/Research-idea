"""Bounded, resumable source work driven by a concrete research question."""
from .store import digest


def _reading_scope(controller):
    """Explicit settings invalidate saved work; incidental new papers do not."""
    return [controller.store.get('source_revision', 0), controller.guidance_keys.get('inspect_source'),
            controller.guidance_keys.get('read_problem_source'), controller.store.get('research_intent'),
            {name: controller.config.get(name) for name in ('auto_search', 'search_source',
                'search_venues', 'fetch_full_text', 'source_chars', 'deep_reading',
                'max_paper_read_chunks', 'max_followup_reads')},
            controller.config.get('backend') == 'demo', controller.context()['search_windows']]


def _search_status(store, keys, *, enabled, requested):
    if not requested:
        return 'not_requested'
    if not enabled:
        return 'disabled'
    if not keys:
        return 'not_performed'
    searches = store.get('search_ledger', {})
    states = [searches.get(key, {}).get('status') for key in keys]
    completed = [key for key, state in zip(keys, states) if state == 'completed']
    if len(completed) == len(keys):
        return 'completed' if any(searches[key].get('metadata') for key in completed) else 'no_results'
    if completed:
        return 'partial'
    return 'failed' if all(state == 'failed' for state in states) else 'incomplete'


def validate_requests(requests, paper_ids):
    if len(requests) > 2:
        raise ValueError('At most two focused reading questions per turn')
    for item in requests:
        if not item['question'].strip() or not (item['query'].strip() or item['paper_ids']):
            raise ValueError('A reading request needs a question and search terms or existing papers')
        if len(item['query']) > 300 or len(item['paper_ids']) > 2:
            raise ValueError('Keep each request to a focused query and at most two papers')
        if not set(item['paper_ids']) <= paper_ids:
            raise ValueError('Read only supplied paper IDs; use a query to find new papers')


def research_requests(controller, requests, *, key, reading_context=None):
    """Search metadata, select up to two sources total, then read relevant text.

    Selection is persisted before downloading. A retry reuses its exact papers
    and successful task results, rather than picking another pair each time.
    """
    store = controller.store
    validate_requests(requests, {p['id'] for p in store.rows('papers')})
    ledger = store.get('problem_research_ledger', {})
    fingerprint_parts = [key, requests, _reading_scope(controller)]
    if reading_context:
        fingerprint_parts.append(reading_context)
    fingerprint = digest(fingerprint_parts)
    entry = ledger.get(fingerprint, {})
    if entry.get('completed'):
        return entry
    if not requests:
        return {'completed': True, 'requests': [], 'selected_ids': [], 'readings': [],
                'performed': False, 'search_performed': False, 'reading_performed': False,
                'search_status': 'not_requested', 'reading_status': 'not_requested'}
    previous_phase = controller.phase
    controller.phase = 'problem'
    try:
        question = '\n'.join(r['question'] for r in requests)
        candidate = {'id': 'question_' + fingerprint[:12], 'proposal': {
            'title': question, 'problem': question, 'closest_work_ids': [],
            'comparison_search': {'comparison_need': question,
                                  'questions': [{'question': r['question'], 'query': r['query']} for r in requests]}},
            'retrieved_work_ids': []}
        if reading_context:
            candidate['reading_context'] = reading_context
        if 'selected_ids' not in entry:
            selected = list(dict.fromkeys(pid for r in requests for pid in r['paper_ids']))[:2]
            keys = []
            enabled = bool(controller.config['auto_search'] and controller.config['backend'] != 'demo')
            if enabled:
                for request in requests:
                    if request.get('existing_search_keys'):
                        keys.extend(request['existing_search_keys'])
                        continue
                    if request.get('citation_target') and request['paper_ids']:
                        continue
                    if request['query'].strip():
                        controller.progress('[search] 围绕当前问题补查：' + request['question'])
                        keys.append(controller.search_once(request['query'], request['question'], candidate=candidate,
                                                           max_new=0, purpose=request.get('time_scope', 'novelty')))
            if keys and len(selected) < 2:
                controller.select_search_results(keys, 2 - len(selected), candidate=candidate,
                                                  selection_phase='problem')
                selected = list(dict.fromkeys(selected + candidate['retrieved_work_ids']))[:2]
            entry = {'requests': requests, 'selected_ids': selected, 'search_keys': keys,
                     'search_enabled': enabled, 'completed': False, 'search_performed': bool(keys),
                     'search_status': _search_status(store, keys, enabled=enabled,
                        requested=any(r['query'].strip() for r in requests))}
            ledger[fingerprint] = entry
            store.set('problem_research_ledger', ledger)
        selected = entry['selected_ids']
        candidate['retrieved_work_ids'] = selected
        controller.retrieve_full_texts(selected)
        readings = controller.focus_sources(candidate, selected, reading_question=question,
            acquisition_requests=[{'information': r['question'], 'question': r['question'],
                                   'paper_ids': r['paper_ids'], 'search_terms': r['query'].split()}
                                  for r in requests]) if selected else []
        refs = set(store.get('question_source_evidence', []))
        refs.update(eid for reading in readings for eid in reading['evidence_ids'])
        store.set('question_source_evidence', sorted(refs))
        entry.update(readings=readings, completed=True, performed=bool(entry['search_keys'] or readings),
            reading_performed=bool(readings),
            reading_status=('completed' if len(readings) == len(selected) else 'partial' if readings else 'unavailable')
                if selected else 'not_requested')
        ledger[fingerprint] = entry
        store.set('problem_research_ledger', ledger)
        return entry
    finally:
        controller.phase = previous_phase


def investigate_problem(controller, seed):
    if not controller.config['auto_search'] or controller.config['backend'] == 'demo':
        return
    store = controller.store
    plans = store.get('problem_reading_plans', {})
    fingerprint = digest([seed, _reading_scope(controller), controller.config.get('constraints'),
                          getattr(controller, 'skill_key', '')])
    if fingerprint not in plans:
        from .citation_discovery import reference_passages, validate_targets
        context = controller.ideation_context()
        relevant_ids = {p['id'] for p in context['papers']}
        passages = reference_passages([p for p in store.rows('papers') if p['id'] in relevant_ids])
        def check_plan(value):
            validate_requests(value['requests'], {p['id'] for p in context['papers']})
            validate_targets(value.get('citation_targets', []), passages)
        plan = controller.task('plan_problem_reading', {**context, 'problem_seed': seed,
            'reference_passages': passages}, check_plan, publish=False)
        plans[fingerprint] = plan
        store.set('problem_reading_plans', plans)
    from .citation_discovery import target_requests
    # Citation targets and conceptual searches share the existing two-source budget.
    if 'resolved_requests' not in plans[fingerprint]:
        targets = plans[fingerprint].get('citation_targets', [])
        requests = target_requests(controller, targets) + plans[fingerprint]['requests']
        plans[fingerprint]['resolved_requests'] = requests[:2]
        store.set('problem_reading_plans', plans)
    return research_requests(controller, plans[fingerprint]['resolved_requests'], key=['problem', fingerprint])
