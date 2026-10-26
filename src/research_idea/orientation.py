"""Read enough field context to discuss directions before detailed investigation."""
from .paper_reading import inventory, heading_text


def orientation_excerpt(paper, limit):
    """Select original introduction, related-work and conclusion spans once.

    This is an orientation, not a full-paper analysis. Offsets always address
    the untouched source; the usual quote validator rejects stitched quotes.
    """
    text = paper.get('text') or paper.get('abstract') or ''
    sections = inventory(paper)['sections']
    anchors = []
    for family in ('introduction', 'related_work', 'limitations'):
        matches = [s for s in sections if s['family'] == family]
        if matches:
            # Prefer Introduction over Abstract and Conclusion over Limitations.
            preferred = [s for s in matches if any(term in heading_text(s['title']).casefold()
                         for term in ('introduction', 'conclusion', '引言', '结论'))]
            anchors.append((preferred or matches)[0])
    if not anchors:
        anchors = [{'start': 0, 'end': len(text), 'title': 'Opening text', 'family': 'other'}]
    marker = '\n\n[Source gap: intervening text not supplied]\n\n'
    remaining = max(0, limit - len(marker) * (len(anchors) - 1))
    spans = []
    for index, section in enumerate(anchors):
        width = remaining // (len(anchors) - index)
        start, end = section['start'], min(section['end'], section['start'] + width)
        if end > start:
            spans.append({'start': start, 'end': end})
            remaining -= end - start
    spans.sort(key=lambda s: s['start'])
    return {'excerpt': marker.join(text[s['start']:s['end']] for s in spans),
            'spans': spans, 'section_context': [
                {k: s[k] for k in ('title', 'family')} for s in anchors],
            'selection_note': 'Background orientation only; selected introduction, related work and conclusion text. '
                              'Detailed mechanisms and results are read after direction discussion.'}


def orient_papers(controller, selected_ids):
    """One bounded reading per source; no full cards, audits or follow-up loop."""
    from .store import digest
    store = controller.store
    selected = set(selected_ids)
    papers = [p for p in controller.reading_papers() if p['id'] in selected]
    previous_phase = controller.phase
    controller.phase = 'orientation'
    try:
        if controller.config['backend'] == 'demo' or not controller.config.get('deep_reading', True):
            controller.extract_papers(selected_ids=selected_ids)
            return
        controller.extract_papers(skip_full_text=True, selected_ids=selected_ids)
        for paper in papers:
            if paper.get('content_kind') != 'full_text':
                continue
            # Preserve completed readings when upgrading/resuming an old project.
            existing = [e for e in store.rows('evidence') if e['paper_id'] == paper['id']
                        and e.get('source_hash') == digest(paper.get('text', ''))
                        and e.get('extraction_stage') in {'read_section', 'extract'}
                        and e.get('guidance_key') == controller.guidance_keys.get(e.get('extraction_stage'))]
            if existing:
                continue
            question = '这个领域希望实现什么，主要方法依靠什么取得了哪些进展？从引言、相关工作和结论建立方法版图，提出值得讨论的研究方向。'
            candidate = {'id': 'orientation', 'proposal': {'title': question,
                         'problem': question, 'closest_work_ids': [paper['id']]}}
            readings = controller.focus_sources(candidate, [paper['id']], reading_question=question)
            refs = set(store.get('question_source_evidence', []))
            refs.update(eid for reading in readings for eid in reading['evidence_ids'])
            store.set('question_source_evidence', sorted(refs))
    finally:
        controller.phase = previous_phase
