"""Keep scientific material in reasoning calls, summarize operational history.

Full reading inventories and search diagnostics remain in SQLite/reports. This
is a deterministic view: it never paraphrases evidence or invents a token count.
"""
from __future__ import annotations

from copy import deepcopy


def _coverage(value):
    if not isinstance(value, dict):
        return value
    result = {k: deepcopy(value[k]) for k in
              ('source', 'scope', 'filters', 'requested_venues', 'selected_counts', 'matched_counts')
              if k in value}
    gaps = list(dict.fromkeys(str(gap) for gap in value.get('gaps', [])))
    if gaps:
        result.update(gaps=[gap if len(gap) <= 240 else gap[:240] + '…' for gap in gaps[:3]],
                      gap_count=len(gaps), gaps_are_examples=len(gaps) > 3 or any(len(g) > 240 for g in gaps))
    if isinstance(value.get('providers'), dict):
        result['providers'] = {name: _coverage(coverage) for name, coverage in value['providers'].items()}
    return result


def compact_research_context(context):
    """Preserve all evidence and substantive card/audit text, with fresh copies."""
    result = deepcopy(context)
    removed_sections = removed_assets = 0
    for card in result.get('paper_cards', []):
        inventory = card.get('inventory')
        if not isinstance(inventory, dict):
            continue
        for key in ('sections', 'assets'):
            items = inventory.get(key, [])
            # Keep section/asset identities and unread coverage, so a later
            # targeted reading can still name the missing source location.
            fields = ('id', 'title', 'family', 'text_coverage') if key == 'sections' else ('id', 'label', 'kind', 'text_coverage', 'visual_status')
            inventory[key] = [{field: item[field] for field in fields if field in item} for item in items]
            inventory[key + '_count'] = len(items)
            if key == 'sections':
                removed_sections += len(items)
            else:
                removed_assets += len(items)
        inventory['detail_location'] = 'Full inventory retained in the stored paper reading, available for targeted reading.'
    searches = result.get('search_coverage', [])
    result['search_coverage'] = [{**entry, 'coverage': _coverage(entry.get('coverage', {}))}
                                 for entry in searches[-12:]]
    result['context_summary'] = {
        'searches_recorded': len(searches), 'recent_searches_shown': min(12, len(searches)),
        'section_inventory_entries_stored': removed_sections,
        'asset_inventory_entries_stored': removed_assets,
        'evidence_quotes': 'All supplied evidence quotes and their conditions are preserved verbatim.',
        'source_records': 'Full search history and reading inventories remain in SQLite and the detailed report.',
    }
    return result
