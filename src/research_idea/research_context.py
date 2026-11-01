"""Keep scientific material in reasoning calls, summarize operational history.

Full reading inventories and search diagnostics remain in SQLite/reports. This
is a deterministic view: it never paraphrases evidence or invents a token count.
"""
from __future__ import annotations

from copy import deepcopy
import json


COMPACT_TASK_STAGES = frozenset({
    'explore_problems', 'plan_problem_reading', 'deepen_problem', 'reconsider_problems',
    'map', 'discuss_direction', 'discuss_question', 'frame_question',
})


def expand_task_payload(payload):
    """Resolve the lossless view for the offline backend and verification tools."""
    def expand(value, trail=()):
        if isinstance(value, dict):
            if set(value) == {'$research_context_ref'}:
                pointer = value['$research_context_ref']
                if not isinstance(pointer, str) or not pointer.startswith('/') or pointer in trail:
                    raise ValueError('Invalid or cyclic research context reference')
                target = payload
                for part in pointer[1:].split('/'):
                    key = part.replace('~1', '/').replace('~0', '~')
                    target = target[int(key)] if isinstance(target, list) else target[key]
                return expand(target, trail + (pointer,))
            return {key: expand(item, trail) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item, trail) for item in value]
        return deepcopy(value)
    return expand(payload)


def compact_task_payload(stage, payload):
    """Share exact repeated research material in the model view, never in storage.

    Backward JSON-pointer references preserve content without a model summary,
    token-based truncation, or guessing which scientific argument matters.
    Evidence, current user input and memory stay inline, including duplicates.
    """
    if stage not in COMPACT_TASK_STAGES:
        return deepcopy(payload)
    protected = {'evidence', 'excerpt', 'topic', 'user_notes', 'constraints', 'research_intent',
                 'current_user_message', 'conversation', 'recent_messages', 'memory',
                 'conversation_memory', 'reasoning_notes', 'previous_discussion_focus',
                 'active_memory', 'memory_sources', 'recent_history', 'retrieved_history',
                 'unreviewed_user_messages'}
    seen = {}

    def visit(value, path):
        if isinstance(value, (str, dict, list)):
            signature = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
            if len(signature) >= 400:
                if signature in seen:
                    return {'$research_context_ref': seen[signature]}
                seen[signature] = path
        if isinstance(value, dict):
            return {key: deepcopy(item) if key in protected else visit(
                item, path + '/' + key.replace('~', '~0').replace('/', '~1'))
                for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item, path + '/' + str(index)) for index, item in enumerate(value)]
        return deepcopy(value)

    # The root is always an object, not a reference.
    return {key: deepcopy(value) if key in protected else visit(
        value, '/' + key.replace('~', '~0').replace('/', '~1')) for key, value in payload.items()}


def _coverage(value):
    if not isinstance(value, dict):
        return value
    result = {k: deepcopy(value[k]) for k in
              ('source', 'scope', 'filters', 'requested_venues', 'selected_counts', 'matched_counts', 'conference_editions')
              if k in value}
    gaps = list(dict.fromkeys(str(gap) for gap in value.get('gaps', [])))
    if gaps:
        result.update(gaps=[gap if len(gap) <= 240 else gap[:240] + '…' for gap in gaps[:3]],
                      gap_count=max(len(gaps), value.get('gap_count', 0)),
                      gaps_are_examples=value.get('gaps_are_examples', False) or len(gaps) > 3 or any(len(g) > 240 for g in gaps))
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
            items = inventory.pop(key, None)
            # Reasoning needs coverage, not hundreds of PDF headings. The
            # source reader still receives the full inventory when locating text.
            if items is not None:
                inventory[key + '_count'] = len(items)
                counts = {}
                for item in items:
                    status = item.get('text_coverage', 'unknown')
                    counts[status] = counts.get(status, 0) + 1
                inventory[key + '_coverage_counts'] = counts
            if key == 'sections':
                removed_sections += inventory.get(key + '_count', 0)
            else:
                removed_assets += inventory.get(key + '_count', 0)
        inventory['detail_location'] = 'Full inventory retained in the stored paper reading, available for targeted reading.'
    for evidence in result.get('evidence', []):
        for key in ('source_hash', 'guidance_key', 'chunk_id'):
            evidence.pop(key, None)
    for coverage in result.get('discovery_coverage', []):
        recalled = coverage.pop('recalled_paper_ids', None)
        if recalled is not None:
            coverage['recalled_paper_count'] = len(recalled)
    searches = result.get('search_coverage', [])
    result['search_coverage'] = [{**entry, 'coverage': _coverage(entry.get('coverage', {}))}
                                 for entry in searches[-12:]]
    result['context_summary'] = {
        'searches_recorded': max(len(searches), context.get('context_summary', {}).get('searches_recorded', 0)),
        'recent_searches_shown': min(12, len(searches)),
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
                              and item.get('extraction_stage') not in {'inspect_source', 'read_problem_source'}]
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
