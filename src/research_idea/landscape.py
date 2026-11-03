"""Persistent abstract readings, distinct from downloaded papers and quote evidence."""
from copy import deepcopy

from .store import digest
from .selection import discovery_pool, rank_metadata
from .literature import deduplicate

VERSION = '2'
BATCH_SIZE = 8
INITIAL_LIMIT = 40
SUPPLEMENT_LIMIT = 16


def research_mode(intent):
    """One question may have several explanations; these are not rival topics."""
    specific = (intent or {}).get('mode') in {'refine', 'assess'}
    return {'kind': 'focused_question' if specific else 'open_exploration',
            'goal': (intent or {}).get('goal', ''),
            'compare': 'explanations_and_existing_responses' if specific else 'important_problems'}


def source_records(store):
    current = store.get('literature_landscape') or {}
    return current.get('sources', [])


def reference_papers(store):
    """A bibliographic reference can be cited without pretending its body was read."""
    papers = {p['id']: deepcopy(p) for p in source_records(store)}
    papers.update({p['id']: p for p in store.rows('papers')})
    return list(papers.values())


def context_view(store, focus=''):
    current = store.get('literature_landscape') or {}
    if not current:
        return {}
    summaries = []
    sources = {p['id']: p for p in current['sources']}
    for note in current['notes']:
        p = sources[note['paper_id']]
        summaries.append({**note, 'title': p['title'], 'url': p.get('url', ''),
                          'year': p.get('year'), 'basis': 'abstract' if p.get('abstract') else 'title_only'})
    relevant = [p for p in sources.values() if p.get('abstract')]
    ranked = rank_metadata(relevant, [focus or store.get('topic') or ''])
    return {'overview': deepcopy(current['overview']), 'paper_notes': summaries,
            'coverage_basis': deepcopy(current.get('coverage_basis', {})),
            'focused_abstracts': [{'paper_id': p['id'], 'abstract': p['abstract'][:4000],
                                   'truncated': len(p['abstract']) > 4000} for p in ranked[:6]],
            'reading_counts': {'skimmed': sum(bool(p.get('abstract')) for p in sources.values()),
                               'title_only': sum(not p.get('abstract') for p in sources.values())},
            'scope': 'Abstracts describe author claims, not verified mechanisms or results. '
                     'Titles and shared names are retrieval cues, never overlap verdicts. '
                     'Request paper_ids to inspect a source body; all original abstracts remain stored.'}


def _pool(controller, keys, plan, limit):
    ledger = controller.store.get('search_ledger', {})
    entries = [ledger[k] for k in keys if k in ledger]
    records = deduplicate([p for entry in entries for p in entry.get('metadata', [])])
    return discovery_pool(records, entries, plan, limit=limit)


def _enrich(controller, papers):
    from .paper_metadata import enrich_screening_pool
    import time
    remaining = controller.config['max_seconds'] - controller.previous_elapsed - (time.monotonic() - controller.started)
    if not papers or remaining <= 0 or controller.store.get('calls_used', 0) >= controller.config['max_calls']:
        return papers
    enriched, audit = enrich_screening_pool(papers, timeout_s=min(12, remaining))
    controller.store.event('landscape_metadata_enrichment', audit)
    # Reuse resolved abstracts in screening and future searches as well.
    by_alias = {a: p for p in enriched if p.get('abstract') for a in p.get('aliases', [p['id']])}
    ledger = controller.store.get('search_ledger', {})
    for entry in ledger.values():
        for p in entry.get('metadata', []):
            match = next((by_alias[a] for a in p.get('aliases', [p['id']]) if a in by_alias), None)
            if match and not p.get('abstract'):
                p.update(abstract=match['abstract'], abstract_source=match.get('abstract_source', ''))
    controller.store.set('search_ledger', ledger)
    return enriched


def _skim(controller, papers):
    notes = []
    readable = [p for p in papers if p.get('abstract')]
    for offset in range(0, len(readable), BATCH_SIZE):
        batch = readable[offset:offset + BATCH_SIZE]
        allowed = {p['id'] for p in batch}
        def check(value):
            ids = [n['paper_id'] for n in value['notes']]
            if len(ids) != len(allowed) or set(ids) != allowed:
                raise ValueError('Keep one abstract note for each supplied paper, including tangential papers')
        controller.progress(f'[read] 摘要泛读 {offset + 1}–{offset + len(batch)}/{len(readable)} · 保留不同思路供讨论')
        result = controller.task('skim_papers', {
            'topic': controller.store.get('topic'), 'research_intent': controller.store.get('research_intent'),
            'research_mode': research_mode(controller.store.get('research_intent')),
            'papers': [{k: p.get(k, '') for k in ('id', 'title', 'url', 'year', 'venue')}
                       | {'abstract': p['abstract'][:4000], 'truncated': len(p['abstract']) > 4000} for p in batch]},
            check, publish=False)
        notes.extend(result['notes'])
    for p in papers:
        if not p.get('abstract'):
            notes.append(dict(paper_id=p['id'], relevance='insufficient', problem='', approach='',
                              claimed_progress='', conditions='', connection='', reading_question='需要摘要或正文了解实际工作。'))
    return notes


def _synthesize(controller, papers, notes, plan, allow_supplement):
    allowed = {p['id'] for p in papers}
    def check(value):
        from .controller import check_references
        check_references(value, set(), allowed)
        if len(value['supplement_queries']) > 2:
            raise ValueError('At most two targeted coverage queries')
        if any(not q['query'].strip() or len(q['query']) > 300 or not q['reason'].strip()
               for q in value['supplement_queries']):
            raise ValueError('A coverage query needs concise search terms and a specific reason')
        if not allow_supplement and value['supplement_queries']:
            raise ValueError('Coverage supplement already used; describe remaining questions for discussion')
    return controller.task('synthesize_landscape', {
        'topic': controller.store.get('topic'), 'user_notes': controller.user_notes(),
        'research_intent': controller.store.get('research_intent'),
        'research_mode': research_mode(controller.store.get('research_intent')),
        'discovery_plan': plan, 'paper_notes': notes,
        'papers': [{k: p.get(k) for k in ('id', 'title', 'url', 'year')} for p in papers],
        'allow_supplement': allow_supplement}, check, publish=False)


def prepare_landscape(controller, keys, plan):
    """One broad pass and optional two-query supplement, all under task budgets.

    Successful batch tasks are cached by the normal controller. Save the enriched
    pool before reading so a resume does not change initial batch boundaries.
    """
    store = controller.store
    from .prompts import stage_version
    def scope_key():
        return digest([VERSION, keys, plan, store.get('research_intent'), controller.user_notes(),
                    stage_version('skim_papers'), stage_version('synthesize_landscape'),
                    controller.guidance_keys.get('skim_papers'), controller.guidance_keys.get('synthesize_landscape'),
                    {k: controller.config.get(k) for k in ('backend', 'model', 'reasoning_effort',
                        'api_provider', 'base_url', 'codex_bin', 'codex_profile')},
                    [{k: store.get('search_ledger', {}).get(key, {}).get(k) for k in ('query', 'status', 'metadata')}
                     for key in keys]])
    scope = scope_key()
    work = store.get('landscape_work') or {}
    if work.get('scope') != scope:
        papers = _enrich(controller, _pool(controller, keys, plan, INITIAL_LIMIT))
        # Enrichment updates the ledger; hash its resulting content on both paths.
        work = {'scope': scope_key(), 'sources': papers}
        store.set('landscape_work', work)
    if work.get('complete'):
        return list(dict.fromkeys(keys + work.get('extra_keys', [])))
    papers = work['sources']
    if not papers:
        store.set('literature_landscape', {})
        return keys
    notes = _skim(controller, papers)
    overview = _synthesize(controller, papers, notes, plan, True)
    extra_keys = []
    for query in overview['supplement_queries']:
        controller.progress('[search] 扩展文献视野：' + query['reason'])
        extra_keys.append(controller.search_once(query['query'], query['reason'], max_new=0,
                                                 purpose=query['purpose']))
    if extra_keys:
        extra = _enrich(controller, _pool(controller, extra_keys, plan, SUPPLEMENT_LIMIT))
        combined = deduplicate(papers + extra)
        old = {p['id']: p for p in papers}
        changed = [p for p in combined if p['id'] not in old or p.get('abstract') != old[p['id']].get('abstract')]
        updated_notes = {n['paper_id']: n for n in notes}
        updated_notes.update({n['paper_id']: n for n in _skim(controller, changed)})
        papers = combined
        notes = [updated_notes[p['id']] for p in papers]
        overview = _synthesize(controller, papers, notes, plan, False)
    all_keys = list(dict.fromkeys(keys + extra_keys))
    searches = store.get('search_ledger', {})
    basis = {'topic': store.get('topic'), 'research_intent': deepcopy(store.get('research_intent')),
             'queries': [searches[key].get('query', '') for key in all_keys if key in searches]}
    current = {'key': digest([papers, notes, overview, basis]), 'sources': papers, 'notes': notes,
               'overview': overview, 'coverage_basis': basis}
    store.set_many({'literature_landscape': current,
                    'landscape_work': {**work, 'complete': True, 'extra_keys': extra_keys}})
    controller.progress(f'[read] 已保留 {sum(bool(p.get("abstract")) for p in papers)} 篇摘要泛读记录 · '
                        f'{len(overview["approaches"])} 类主要思路；后续讨论继续参考')
    controller.activity('synthesize_landscape', overview, False)
    return list(dict.fromkeys(keys + extra_keys))
