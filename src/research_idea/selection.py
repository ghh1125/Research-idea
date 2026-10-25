"""Cheap, inspectable metadata screening before any full-text/model reading."""
from __future__ import annotations

from collections import deque
from datetime import date
import re

STOPWORDS = set('a an the of for in on to and or with by from using via study approach method all ti abs cat'.split())


def terms(text):
    # English search plans bridge non-English user topics. Simple plural folding
    # helps agent/agents without introducing an embedding service or model call.
    return {word[:-1] if len(word) > 4 and word.endswith('s') else word
            for word in re.findall(r'[\w]+', text.casefold())
            if len(word) > 1 and word not in STOPWORDS}


def rank_metadata(records, queries):
    """Relevance bands first, newest conference edition/date next.

    Scores are lexical title/abstract matches, not model confidence. Bands keep
    a new tangential paper from replacing a substantially more relevant one.
    Query-match explanations are retained for the UI and selection audit.
    """
    query_terms = [(query, terms(query)) for query in queries if terms(query)]
    ranked = []
    for paper in records:
        title, abstract = terms(paper['title']), terms(paper.get('abstract', ''))
        matches = [(sum(1.25 if word in title else 1 if word in abstract else 0 for word in words)
                    / (1.25 * len(words)), query) for query, words in query_terms]
        score, query = max(matches, default=(0.0, ''), key=lambda item: item[0])
        published = paper.get('publication_date') or ''
        edition = paper.get('conference_year')
        if type(edition) is int and not published.startswith(str(edition)):
            published = f'{edition:04d}-00-00'
        try:
            date.fromisoformat(published)
        except (ValueError, TypeError):
            published = f"{edition or paper.get('year') or 0:04d}-00-00"
        selection = {'relevance': round(score, 4), 'relevance_band': int(score * 5),
                     'matched_query': query, 'date': published,
                     'basis': 'title/abstract lexical match; relevance band then newest conference edition/date; metadata only'}
        ranked.append(dict(paper, selection=selection))
    return sorted(ranked, key=lambda p: (-p['selection']['relevance_band'],
        tuple(-ord(c) for c in p['selection']['date']), -p['selection']['relevance'], p['id']))


def discovery_pool(records, entries, plan, limit=40):
    """Interleave actual route retrievals before bounded semantic screening.

    ``records`` are already deduplicated papers; ``entries`` are the search
    ledger entries containing query and metadata. Alias matches recover every
    query that actually returned a paper, independently of lexical ranking.
    Returned records add discovery_provenance and normal selection scores;
    inputs are unchanged. Legacy plans use the same global ranking as before.
    """
    if limit <= 0:
        return []
    routes = plan.get('research_routes', [])
    route_ids = {route['id'] for route in routes}
    query_key = lambda query: ' '.join(query.split()).casefold()
    planned_links = {}
    for query in plan.get('queries', []):
        linked = planned_links.setdefault(query_key(query['query']), [])
        linked.extend(route for route in query.get('route_ids', [])
                      if route in route_ids and route not in linked)
    provenance, alias_queries = {}, {}
    for entry in entries:
        query = entry.get('query', '')
        key = query_key(query)
        provenance.setdefault(key, {'query': query, 'route_ids': list(planned_links.get(key, []))})
        for paper in entry.get('metadata', []):
            aliases = set(paper.get('aliases', [])) | {paper['id']}
            for alias in aliases:
                alias_queries.setdefault(alias, set()).add(key)
    enriched = []
    for paper in records:
        aliases = set(paper.get('aliases', [])) | {paper['id']}
        found = set().union(*(alias_queries.get(alias, set()) for alias in aliases))
        hits = [{'query': item['query'], 'route_ids': list(item['route_ids'])}
                for key, item in provenance.items() if key in found]
        enriched.append(dict(paper, discovery_provenance=hits))
    all_queries = [entry.get('query', '') for entry in entries]
    ranked = rank_metadata(enriched, all_queries)
    pools = []
    for route in routes:
        own_queries = [item['query'] for item in provenance.values() if route['id'] in item['route_ids']]
        own_records = [paper for paper in enriched if any(
            route['id'] in hit['route_ids'] for hit in paper['discovery_provenance'])]
        pools.append(deque(rank_metadata(own_records, own_queries)))
    selected, seen = [], set()
    while len(selected) < limit:
        added = False
        for pool in pools:
            while pool and pool[0]['id'] in seen:
                pool.popleft()
            if pool:
                paper = pool.popleft()
                selected.append(paper)
                seen.add(paper['id'])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
    for paper in ranked:
        if len(selected) >= limit:
            break
        if paper['id'] not in seen:
            selected.append(paper)
            seen.add(paper['id'])
    return selected
