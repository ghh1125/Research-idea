"""Cheap, inspectable metadata screening before any full-text/model reading."""
from __future__ import annotations

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
