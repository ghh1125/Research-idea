"""Use cited representative works to calibrate recall, without exhaustive reading."""
import re
from .paper_reading import inventory
from .store import digest


def title_key(value):
    return ' '.join(re.findall(r'\w+', value.casefold()))


def reference_passages(papers, budget=12000):
    selected = [p for p in papers if p.get('content_kind') == 'full_text']
    result = []
    for index, paper in enumerate(selected):
        text = paper.get('text', '')
        sections = inventory(paper)['sections']
        parts = []
        room = budget // max(1, len(selected) - index)
        for family in ('references', 'related_work'):
            section = next((s for s in sections if s['family'] == family), None)
            if section:
                start = section['start']
                end = min(section['end'], start + room // 2)
                parts.append({'start': start, 'end': end, 'text': text[start:end]})
        used = sum(len(p['text']) for p in parts)
        budget -= used
        if parts:
            result.append({'paper_id': paper['id'], 'title': paper['title'], 'passages': parts})
    return result


def validate_targets(targets, passages):
    if len(targets) > 2:
        raise ValueError('Trace at most two representative works per reading plan')
    for target in targets:
        sources = [s for p in passages if p['paper_id'] == target['source_paper_id'] for s in p['passages']]
        quote = target['source_quote']
        if len(quote) < 15 or not any(quote in s['text'] for s in sources):
            raise ValueError('A citation target must have a verbatim location in the supplied source')
        if not title_key(target['title']) or title_key(target['title']) not in title_key(quote):
            raise ValueError('The original paper title must appear in the cited passage')


def target_requests(controller, targets):
    store = controller.store
    searches = store.get('search_ledger', {})
    papers = store.rows('papers')
    journal = store.get('citation_calibration', {})
    requests = []
    for target in targets:
        title = title_key(target['title'])
        known = [p['id'] for p in papers if title_key(p.get('title', '')) == title]
        keys = [key for key, entry in searches.items() if entry.get('status') == 'completed'
                and any(title_key(p.get('title', '')) == title for p in entry.get('metadata', []))]
        journal[digest(target)] = {**target, 'already_read_or_selected': known,
                                  'existing_search_keys': keys, 'missing_from_recall': not (known or keys)}
        controller.progress('[search] 追踪代表工作：' + target['title'] +
                            (' · 复用已有检索记录' if known or keys else ' · 按原题补查'))
        requests.append({'question': target['question'], 'query': '"' + target['title'].replace('"', '') + '"',
                         'paper_ids': known[:1], 'time_scope': 'lineage', 'existing_search_keys': keys,
                         'citation_target': target})
    store.set('citation_calibration', journal)
    return requests
