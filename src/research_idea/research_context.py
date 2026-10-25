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
              ('source', 'scope', 'filters', 'requested_venues', 'selected_counts', 'matched_counts', 'conference_editions')
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


def _references_removed_evidence(value, removed_ids):
    if isinstance(value, dict):
        return any(_references_removed_evidence(child, removed_ids) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_references_removed_evidence(child, removed_ids) for child in value)
    return isinstance(value, str) and value in removed_ids


def problem_discovery_context(context, selected_ids=None):
    """Give ideation source analysis without the reader's ready-made proposals.

    Paper-local suggestions remain in the stored cards and technical-design
    context. Removing them here changes the starting point of map/propose, not
    the underlying evidence or the user's explicitly chosen research scope.
    An explicit cohort also excludes candidate-directed readings and analyses
    that depend on them. Neutral source quotes remain available independently.
    """
    result = deepcopy(context)
    if selected_ids is not None:
        selected_ids = set(selected_ids)
        original_evidence = result.get('evidence', [])
        result['evidence'] = [item for item in original_evidence
                              if item.get('paper_id') in selected_ids
                              and item.get('extraction_stage') != 'inspect_source']
        retained_refs = {item['id'] for item in result['evidence']}
        removed_refs = {item['id'] for item in original_evidence} - retained_refs
        result['papers'] = [paper for paper in result.get('papers', [])
                            if paper.get('id') in selected_ids]
        for field in ('paper_cards', 'paper_claim_audits'):
            # A derived analysis can blend neutral and candidate-directed
            # interpretations. Do not silently relabel that analysis or remove
            # only its citations; leave it intact in storage, outside this view.
            result[field] = [item for item in result.get(field, [])
                             if item.get('paper_id') in selected_ids
                             and not _references_removed_evidence(item, removed_refs)]
        if isinstance(result.get('quote_gaps'), dict):
            result['quote_gaps'] = {key: gap for key, gap in result['quote_gaps'].items()
                                    if gap.get('paper_id') in selected_ids}
        elif 'quote_gaps' in result:
            result['quote_gaps'] = [gap for gap in result['quote_gaps']
                                    if gap.get('paper_id') in selected_ids]
        if 'retrieval_gaps' in result:
            result['retrieval_gaps'] = [gap for gap in result['retrieval_gaps']
                                        if gap.get('paper_id') in selected_ids]
        result.setdefault('context_summary', {})['discovery_sources'] = {
            'paper_ids': sorted(selected_ids),
            'evidence_records': len(result['evidence']),
            'scope': 'Initial discovery cohort; candidate-directed readings remain in storage for technical design.',
        }
    for card in result.get('paper_cards', []):
        card.pop('opportunities', None)
        # Critiques of a source's causal attribution are not ready-made research
        # needs. Keep methods, results and scope, while leaving these critiques
        # in the complete source card for evidence inspection.
        card.pop('analyst_concerns', None)
        if 'framework' in card:
            card['framework'] = [item for item in card['framework']
                                 if item.get('dimension') != 'idea_relevance']
    for audit in result.get('paper_claim_audits', []):
        audit['claims'] = [{key: deepcopy(claim[key]) for key in (
            'claim', 'claim_evidence_ids', 'tested_scope', 'result_evidence_ids', 'warranted_conclusion')
            if key in claim} for claim in audit.get('claims', [])]
        audit.pop('warnings', None)
    result.setdefault('context_summary', {})['ideation_view'] = (
        'Source methods, reported progress, tested conditions, scoped conclusions and original evidence are retained. '
        'Reader-generated proposals and critiques of source contributions remain in the complete stored cards and audits. '
        'Develop research needs beyond the progress already achieved: reason about what matters when existing methods '
        'work as intended, rather than using an audit disagreement as the new problem.')
    return result
