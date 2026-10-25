"""Bounded, candidate-directed reading before the first-phase idea is delivered.

The draft names its method family and missing comparisons. Retrieval and source
reading enrich that same reasoning task; they do not approve or reject an idea.
"""
from __future__ import annotations

from copy import deepcopy
from .search_planning import normalize_search_plan
from .search_scope import config_scope
from .store import digest


def normalize_comparison_search(search):
    plan = normalize_search_plan({
        'research_question': search['comparison_need'], 'scope': search['method_family'],
        'queries': [{'query': item['query'], 'rationale': item['rationale'], 'purpose': 'mechanism'}
                    for item in search['queries']], 'assumptions': []}) if search['queries'] else None
    if plan:
        scopes = {}
        for item in search['queries']:
            scopes.setdefault(' '.join(item['query'].split()).casefold(), item['time_scope'])
        search['queries'] = [{'query': item['query'], 'rationale': item['rationale'],
                             'time_scope': scopes.get(item['query'].casefold(), 'recent')}
                            for item in plan['queries']]
    return search


def validate_information_path(core):
    for key in ('concrete_target', 'construction_path', 'capability_bridge', 'essential_difference'):
        if not core[key].strip():
            raise ValueError('Explain the target, information construction, capability bridge and substantive difference')
    if len(core['information_path']) > 3:
        raise ValueError('Describe at most three central information dependencies')
    for item in core['information_path']:
        if any(not value.strip() for key, value in item.items() if key != 'evidence_ids'):
            raise ValueError('Connect each critical input to its source, construction, reliability and use')


def read_neighborhoods(controller, draft, problem):
    """Return only this draft's additional sources; preserve resumable checkpoints."""
    if not controller.config['auto_search'] or controller.config['backend'] == 'demo':
        return []
    store = controller.store
    states = store.get('idea_neighborhoods', {})
    results = []
    opportunities = {item['id']: item for item in problem['opportunities']}
    for proposal in draft['candidates']:
        search = proposal['comparison_search']
        if not search['queries']:
            continue
        key = digest([proposal, {purpose: config_scope(controller.config, purpose)
                                for purpose in ('strategy', 'lineage')},
                      controller.config['search_source'], controller.config.get('search_venues'),
                      controller.config.get('search_results_per_query'), controller.config['max_papers'],
                      controller.guidance_keys['inspect_source']])
        state = states.setdefault(key, {'opportunity_id': proposal['opportunity_id'],
                                      'search': deepcopy(search), 'paper_ids': []})
        candidate = {'id': key, 'proposal': proposal, 'retrieved_work_ids': list(state['paper_ids']),
                     'selected_opportunity': opportunities[proposal['opportunity_id']]}
        controller.phase = 'neighbor'
        controller.progress('[search] 围绕核心操作寻找更接近的方法：' + search['method_family'])
        if not state.get('selection_complete'):
            keys = [controller.search_once(item['query'], item['rationale'], max_new=0,
                       purpose='lineage' if item['time_scope'] == 'lineage' else 'strategy')
                    for item in search['queries']]
            state['search_keys'] = keys
            states[key] = state
            store.set('idea_neighborhoods', states)
            before = store.get('paper_selections', [])[-1:]
            try:
                controller.select_search_results(keys, 2, candidate=candidate, selection_phase='neighbor')
            finally:
                after = store.get('paper_selections', [])[-1:]
                if (after != before and after and after[0].get('phase') == 'neighbor'
                        and after[0].get('queries') == [item['query'] for item in search['queries']]):
                    # Selection is saved before downloads, so a stopped download
                    # does not allocate a second reading batch on resume.
                    state.update(selection_complete=True, paper_ids=candidate['retrieved_work_ids'])
                    states[key] = state
                    store.set('idea_neighborhoods', states)
        controller.retrieve_full_texts(state['paper_ids'])
        # Existing neutral evidence is already in the discovery context. Read
        # the selected new sources for their closest-method and acquisition role.
        initial_ids = set(controller.initial_paper_ids())
        focused_ids = [pid for pid in state['paper_ids'] if pid not in initial_ids][:2]
        candidate['retrieved_work_ids'] = focused_ids
        controller.focus_sources(candidate, selected_ids=focused_ids)
        scope = digest([proposal, None])
        full = controller.context()
        paper_ids = set(state['paper_ids'])
        evidence = [item for item in full['evidence'] if item['paper_id'] in paper_ids
                    and (item.get('extraction_stage') != 'inspect_source' or item.get('extraction_scope') == scope)]
        stored = {paper['id']: paper for paper in store.rows('papers')}
        papers = [{**paper, 'abstract': (stored[paper['id']].get('abstract') or '')[:1800]}
                  for paper in full['papers'] if paper['id'] in paper_ids]
        ledger = store.get('search_ledger', {})
        metadata = {paper['id']: {field: paper.get(field) for field in ('id', 'title', 'url', 'abstract', 'year')}
                    for search_key in state.get('search_keys', [])
                    for paper in ledger.get(search_key, {}).get('metadata', [])}
        for item in metadata.values():
            item['abstract'] = (item.get('abstract') or '')[:1800]
        state['evidence_ids'] = [item['id'] for item in evidence]
        states[key] = state
        store.set('idea_neighborhoods', states)
        results.append({'opportunity_id': proposal['opportunity_id'], 'search': search,
                        'papers': papers, 'evidence': evidence,
                        'metadata_only': [item for pid, item in metadata.items() if pid not in paper_ids][:12]})
    controller.phase = 'ideation'
    return results


def with_neighborhoods(context, neighborhoods):
    result = deepcopy(context)
    for field in ('papers', 'evidence'):
        records = {item['id']: item for item in result[field]}
        for neighborhood in neighborhoods:
            records.update({item['id']: item for item in neighborhood[field]})
        result[field] = list(records.values())
    result['idea_neighborhoods'] = [{key: value for key, value in item.items() if key not in {'papers', 'evidence'}}
                                    for item in neighborhoods]
    return result
