"""Locate bounded continuous source passages for an explicit reading question.

This is a lexical locator, not a relevance judge. It neither rewrites source
text nor treats an unmatched term as evidence that a technique is absent.
"""
from __future__ import annotations

import re


_STOP_WORDS = frozenset("a an and are as at be by for from how in is it of on or the to was what which with".split())
_REFERENCE_HEADING = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\d+(?:\.\d+)*[.)]?[ \t]+)?"
    r"(?:references|bibliography|参考文献)[ \t]*[:：]?[ \t]*\r?$")
_AFTER_REFERENCES = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\d+(?:\.\d+)*[.)]?[ \t]+)?"
    r"(?:appendi(?:x|ces)\b|supplement(?:ary)?\b|附录|补充材料)[^\n\r]{0,110}\r?$")


def _normalize_terms(search_terms):
    if isinstance(search_terms, str):
        search_terms = [search_terms]
    result = []
    for raw in search_terms or []:
        if not isinstance(raw, str):
            continue
        term = " ".join(raw.split())
        words = re.findall(r"[A-Za-z]+", term.casefold())
        if not term or len(term) > 120 or not any(len(w) > 1 and w not in _STOP_WORDS for w in words):
            continue
        if term.casefold() not in {item.casefold() for item in result}:
            result.append(term)
        if len(result) == 16:
            break
    return result


def _pattern(term):
    # Permit line wrapping and a hyphen between phrase words; never run a
    # model-provided string as a regular expression.
    return re.compile(r"(?<!\w)" + r"[\s-]+".join(re.escape(word) for word in term.split()) + r"(?!\w)", re.I)


def _body_ranges(text):
    references = []
    for heading in _REFERENCE_HEADING.finditer(text):
        following = _AFTER_REFERENCES.search(text, heading.end())
        end = following.start() if following else len(text)
        if references and heading.start() < references[-1][1]:
            continue
        references.append((heading.start(), end))
    body, start = [], 0
    for left, right in references:
        if start < left:
            body.append((start, left))
        start = right
    if start < len(text):
        body.append((start, len(text)))
    return body


def _window(text, hit_start, hit_end, width, body_start, body_end):
    """Keep the complete hit paragraph when it fits, with nearby context."""
    preceding = text.rfind("\n\n", body_start, hit_start)
    paragraph_start = preceding + 2 if preceding >= 0 else body_start
    following = text.find("\n\n", hit_end, body_end)
    paragraph_end = following if following >= 0 else body_end
    anchor_start, anchor_end = hit_start, hit_end
    if paragraph_end - paragraph_start <= width:
        anchor_start, anchor_end = paragraph_start, paragraph_end
    start = max(body_start, anchor_start - max(0, width - (anchor_end - anchor_start)) // 2)
    end = min(body_end, start + width)
    start = max(body_start, end - width)
    # Prefer complete paragraphs at the edges without discarding the anchor.
    boundary = text.find("\n\n", start, anchor_start)
    if boundary >= 0:
        start = boundary + 2
    boundary = text.rfind("\n\n", anchor_end, end)
    if boundary >= 0:
        end = boundary
    return start, end


def _merge(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _render(text, spans):
    return "\n\n".join(f"[SOURCE SPAN {start}:{end}]\n{text[start:end]}" for start, end in spans)


def _operative_sections(text, body_ranges):
    """Find a few operative headings, including PDF headings missed by inventory.

    A short prose line beginning with 'model' is not an operative heading.
    Methodology and Implementation can be separate unnumbered lines after a
    PDF puts the section number on the preceding line.
    """
    from .paper_reading import NUMBERING
    families = {
        "method": r"(?:(?:our|proposed)\s+)?(?:methods?|methodology|approach|framework)\b|(?:overall|system)\s+(?:architecture|overview)\b|(?:研究)?方法|模型架构",
        "algorithm": r"algorithms?\b|算法",
        "implementation": r"implementations?\b|implementation\s+details\b|实现细节|实现方法",
    }
    choices = {}
    for line in re.finditer(r"(?m)^[ \t]*[^\n\r]{1,120}\r?$", text):
        title = line.group().strip()
        clean = re.sub(r"^#{1,6}\s*", "", title)
        explicit = bool(NUMBERING.match(clean) or title.startswith("#"))
        clean = NUMBERING.sub("", clean).strip()
        family = next((name for name, pattern in families.items() if re.match(pattern, clean, re.I)), None)
        if not family or len(clean.split()) > 10 or re.search(r"[.!?。！？]$", clean):
            continue
        canonical = bool(re.fullmatch(r"(?:(?:our|proposed)\s+)?(?:methods?|methodology|approach|framework|algorithms?|implementations?(?:\s+details)?)", clean, re.I))
        separated = line.start() == 0 or text[max(0, line.start() - 4):line.start()].endswith(("\n\n", "\r\n\r\n"))
        if not (explicit or canonical or separated):
            continue
        body = next(((start, end) for start, end in body_ranges if start <= line.start() < end), None)
        if body is None:
            continue
        item = {"title": title, "start": line.start(), "heading_end": line.end(), "family": family,
                "body_start": body[0], "body_end": body[1]}
        rank = (not canonical, line.start())
        if family not in choices or rank < choices[family][0]:
            choices[family] = (rank, item)
    return [choices[family][1] for family in families if family in choices]


def _operative_window(text, section, width):
    # Include some input/problem definitions before the method, but spend most
    # of the window on its operations and subsequent subsections.
    start = max(section['body_start'], section['start'] - min(2000, width // 4))
    end = min(section['body_end'], start + width)
    boundary = text.find("\n\n", start, section['start'])
    if boundary >= 0:
        start = boundary + 2
    boundary = text.rfind("\n\n", section['heading_end'], end)
    # Do not throw away a long final paragraph merely because its beginning is
    # the last blank line. A bounded continuous partial paragraph is useful;
    # an entire section ending at the body boundary needs no trimming at all.
    if end < section['body_end'] and boundary >= 0 and end - boundary <= min(512, width // 4):
        end = boundary
    return start, end


def select_focused_excerpt(text: str, limit: int, search_terms, reading_question: str = "") -> dict | None:
    """Return exact source spans plus audit metadata, or None for generic fallback.

    Explicit English terms locate candidates. English words in the reading
    question only break ties between those candidates; they cannot create a
    match. After a lexical match, method/algorithm/implementation context can
    expose operations absent from an introductory mention. Up to four windows
    are selected, counting span markers in ``limit``. Bibliography-only matches
    never consume the allowance. A match or heading is a location hint, not
    proof of scientific relevance.
    """
    terms = _normalize_terms(search_terms)
    if not text or not terms or limit <= 0:
        return None
    marker_allowance = len(f"[SOURCE SPAN {len(text)}:{len(text)}]\n") + 2
    available = limit - marker_allowance
    if available <= 0:
        return None
    # A fixed 2400-character window left most of a 24000-character allowance
    # unused while broad terms repeatedly selected the introduction.
    width = min(available, max(512, available // 3))
    patterns = [_pattern(term) for term in terms]
    question_words = sorted({word.casefold() for word in re.findall(r"[A-Za-z]{3,}", reading_question)
                             if word.casefold() not in _STOP_WORDS})[:32]
    question_patterns = [_pattern(word) for word in question_words]
    candidates = set()
    body_ranges = _body_ranges(text)
    for body_start, body_end in body_ranges:
        for pattern in patterns:
            # Repeated occurrences in one small neighborhood need only one
            # window. Scan every body range so late unique details remain eligible.
            seen_buckets = set()
            for hit in pattern.finditer(text, body_start, body_end):
                bucket = hit.start() // max(32, width // 2)
                if bucket in seen_buckets or hit.end() - hit.start() > width:
                    continue
                seen_buckets.add(bucket)
                candidates.add(_window(text, hit.start(), hit.end(), width, body_start, body_end))
    if not candidates:
        return None
    ranked = []
    for start, end in candidates:
        passage = text[start:end]
        matched = tuple(index for index, pattern in enumerate(patterns) if pattern.search(passage))
        question_hits = sum(bool(pattern.search(passage)) for pattern in question_patterns)
        ranked.append((start, end, matched, question_hits))
    selected, covered, section_context = [], set(), []
    windows_used = 0
    for _ in range(4):
        if not ranked:
            break
        # Distinct requested terms outrank repetition. The question then helps
        # locate an acquisition paragraph instead of another broad mention.
        ranked.sort(key=lambda item: (len(set(item[2]) - covered), len(item[2]), item[3],
                                      sum(len(terms[i].split()) for i in item[2]), -item[0], -item[1]), reverse=True)
        accepted = False
        for index, (start, end, matched, _) in enumerate(ranked):
            merged = _merge(selected + [(start, end)])
            if merged == selected or len(_render(text, merged)) > limit:
                continue
            selected = merged
            covered.update(matched)
            ranked.pop(index)
            windows_used += 1
            accepted = True
            break
        if not accepted:
            break
        if windows_used == 1:
            # Keep the strongest actual keyword passage. Before spending the
            # rest on repeated broad mentions, reserve context for real method
            # and implementation sections, even if they use different terms.
            sections = _operative_sections(text, body_ranges)
            for section_index, section in enumerate(sections):
                remaining = limit - len(_render(text, selected))
                section_width = remaining // (len(sections) - section_index) - marker_allowance
                if section_width < 256:
                    continue
                start, end = _operative_window(text, section, section_width)
                merged = _merge(selected + [(start, end)])
                if merged == selected or len(_render(text, merged)) > limit:
                    continue
                selected = merged
                covered.update(index for index, pattern in enumerate(patterns) if pattern.search(text[start:end]))
                section_context.append({"title": section['title'], "family": section['family'],
                                        "start": start, "end": end})
                windows_used += 1
        if windows_used >= 4:
            break
    if not selected:
        return None
    return {
        "excerpt": _render(text, selected),
        "spans": [{"start": start, "end": end} for start, end in selected],
        "matched_terms": [term for index, term in enumerate(terms)
                          if any(patterns[index].search(text[start:end]) for start, end in selected)],
        "reading_question": reading_question,
        "section_context": section_context,
        "selection_note": "Continuous source windows located by explicit terms; question words only rank matching windows. "
                          "Method, algorithm and implementation heading context supplements repeated introductory mentions. "
                          "Offsets refer to untouched source text. Bibliography-only matches are excluded. "
                          "Lexical matching does not establish scientific relevance, correctness or exhaustive reading.",
    }
