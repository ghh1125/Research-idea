"""Bounded section reading, source inventories and grounded paper analysis cards.

Text coverage means supplied to a successful extraction task, not comprehension.
Caption/equation detection is heuristic; PDF images are never claimed inspected.
"""
from __future__ import annotations

import re
from .store import digest

FACETS = ("problem", "motivation", "insight", "method", "prior_work_delta",
          "experiment_design", "results", "conclusion_boundary", "idea_relevance")
FACET_LABELS = dict(zip(FACETS, ("研究问题", "研究动机", "核心洞见", "具体方法", "已有工作差异",
                               "实验设计", "结果与解释", "结论边界", "对研究方向的启发")))
FAMILIES = {
    "introduction": r"abstract\b|introduction\b|摘要|引言|介绍",
    "related_work": r"related\s+work\b|background\b|preliminar|相关工作|背景|预备",
    "method": r"(?:(?:our|proposed)\s+)?(?:methods?|methodology|approach|framework|algorithm|model)\b|方法|算法|模型",
    "experiments": r"experiment|evaluation|setup\b|implementation|实验|评测|评估|实现细节",
    "results": r"(?:(?:main|additional)\s+)?results?\b|ablation|analysis\b|结果|消融|分析",
    "limitations": r"limitation|discussion|conclusion|局限|讨论|结论",
    "appendix": r"appendi(?:x|ces)|supplement|附录|补充",
    "references": r"(?:references?|bibliography|参考文献)\s*[:：]?$",
}
NUMBERING = re.compile(r"^(?:\d+(?:\.\d+)*(?:[.)、．:]\s*|\s+)|[A-Z](?:\.\d+)*(?:[.)、:]\s*|\s+)|第[一二三四五六七八九十0-9]+[章节]\s*|[一二三四五六七八九十]+、\s*)")
CAPTION = re.compile(r"^(Figure|Fig\.|Table|图|表)\s*([A-Z]?\d+(?:\.\d+)*)(?:\s*[:：.]\s*|\s*$)", re.I)


def heading_text(title):
    clean = re.sub(r'^#{1,6}\s*', '', title)
    clean = re.sub(r'\b([A-Z])\s+(?=[A-Z]{2,}\b)', r'\1', clean)
    return NUMBERING.sub('', clean)


def source_text(paper):
    return paper.get("text") or paper.get("abstract") or ""


def inventory(paper):
    text = source_text(paper)
    fingerprint = digest(text)
    headings, assets = [], []
    for line in re.finditer(r"(?m)^[^\n\r]+", text):
        title = line.group().strip()
        if not title:
            continue
        caption = CAPTION.match(title)
        equation = re.search(r"\\tag\{([^}]+)\}|\((\d+)\)\s*$", title) if re.search(r"[=∑∂∇]|\\(?:frac|sum|math)", title) else None
        if caption or equation:
            kind = ("table" if caption.group(1).lower() in {"table", "表"} else "figure") if caption else "equation"
            label = caption.group(0).rstrip(":：. ") if caption else "Equation " + (equation.group(1) or equation.group(2))
            assets.append({"id": "asset_" + digest([fingerprint, line.start(), kind])[:12], "kind": kind,
                "label": label, "start": line.start(), "end": line.end(), "text_preview": title[:300],
                "visual_status": "not_inspected"})
            continue
        clean = re.sub(r"^#{1,6}\s*", "", title)
        clean = re.sub(r'\b([A-Z])\s+(?=[A-Z]{2,}\b)', r'\1', clean)
        numbered = NUMBERING.match(clean)
        clean = NUMBERING.sub("", clean)
        # Common PDF small-cap extraction: I NTRODUCTION / M ETHODOLOGY.
        family = next((name for name, pattern in FAMILIES.items() if re.match(pattern, clean, re.I)), None)
        prose = bool(re.search(r'[.!?。！？;=∑∂∇]|\\(?:frac|sum|math)', clean)
                     or re.match(r'\d{4}\b', title)
                     or re.search(r'\b(?:we|they|show|shows|is|are|was|were|can|that)\b', clean, re.I))
        named = bool(clean and (clean[0].isupper() or re.search(r'[\u4e00-\u9fff]', clean)))
        explicit = bool((numbered and named and len(clean.split()) <= 12 and not prose)
                        or title.startswith('#'))
        # Plain prose that starts with 'Results show ...' is not a known heading.
        if len(title) <= 120 and ((family and (named or len(clean.split()) == 1) and len(clean.split()) <= 9 and not prose) or explicit):
            headings.append((line.start(), title, family or "other"))
    if not headings or headings[0][0] != 0:
        headings.insert(0, (0, "Opening text / unclassified", "other"))
    # A caption can be supplied while the adjacent table text remains unread.
    # Keep its exact span separate from a bounded follow-up context window.
    boundaries = sorted({start for start, _, _ in headings} | {a["start"] for a in assets})
    for asset in assets:
        next_boundary = next((start for start in boundaries if start > asset["start"]), len(text))
        asset["context_end"] = min(next_boundary, asset["end"] + 4000, len(text))
    sections = [{"id": "section_" + digest([fingerprint, start])[:12], "title": title, "family": family,
                 "start": start, "end": headings[i + 1][0] if i + 1 < len(headings) else len(text)}
                for i, (start, title, family) in enumerate(headings)]
    gaps = ["Section, caption and equation discovery is heuristic; undetected items are not evidence of absence.",
            "Only extracted text is available. Figure pixels, table layout and formula rendering have not been visually inspected."]
    if len(sections) > 200 or len(assets) > 200:
        gaps.append("Inventory is truncated to 200 sections and 200 assets; remaining items require manual inspection.")
    if not assets:
        gaps.append("No anchored caption/equation markers were detected; do not claim that the paper has no figures, tables or formulas.")
    return {"paper_id": paper["id"], "source_hash": fingerprint, "characters": len(text),
            "sections": sections[:200], "assets": assets[:200], "inventory_gaps": gaps}


def chunks(text, limit):
    """Contiguous, nonoverlapping chunks, capped at 2000; caller reports truncation."""
    if limit < 256:
        raise ValueError("Section reading requires source_chars >= 256")
    result, start = [], 0
    fingerprint = digest(text)
    while start < len(text) and len(result) < 2000:
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + limit // 2, end)
            if boundary > start:
                end = boundary + 1
        result.append({"id": "chunk_" + digest([fingerprint, start, end])[:12], "start": start, "end": end})
        start = end
    return result


def initial_chunks(parts, source_inventory, count, reading_role="method"):
    # A landscape source supplies the broader approaches, including discussion
    # late in Related Work. Method readings retain their original priorities.
    # Neither role changes the number of chunks or establishes comprehension.
    families = ("introduction", "method", "experiments", "results", "appendix", "limitations")
    if reading_role == "landscape":
        families = ("introduction", "related_work", "method", "experiments", "results", "appendix", "limitations")
    selected = []
    for family in families:
        sections = [s for s in source_inventory["sections"] if s["family"] == family]
        if reading_role == "landscape" and family in {"introduction", "related_work"}:
            # Abstract and Introduction share an inventory family. Prefer the
            # actual introduction; similarly prefer Related Work/Background to
            # a preliminaries section when both are available.
            pattern = r"introduction\b|引言|介绍" if family == "introduction" else r"related\s+work\b|background\b|相关工作|背景"
            preferred = [s for s in sections if re.match(pattern,
                heading_text(s["title"]), re.I)]
            sections = preferred or sections
        section = sections[0] if sections else None
        if section:
            part = next((p for p in parts if p["start"] <= section["start"] < p["end"]), None)
            if part and part not in selected:
                selected.append(part)
    selected.extend(p for p in parts if p not in selected)
    return selected[:count]


def with_coverage(source_inventory, read_parts):
    intervals = sorted((p["start"], p["end"]) for p in read_parts)
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    def covered(start, end):
        return sum(max(0, min(end, b) - max(start, a)) for a, b in merged)
    result = {**source_inventory}
    for key in ("sections", "assets"):
        result[key] = []
        for item in source_inventory[key]:
            size = item["end"] - item["start"]
            seen = covered(item["start"], item["end"])
            result[key].append({**item, "text_coverage": "complete" if size and seen == size else "partial" if seen else "unread",
                                "characters_supplied": seen})
    seen = covered(0, result["characters"])
    result.update(characters_supplied=seen,
                  text_coverage="complete_supplied_text" if seen == result["characters"] and seen else "partial",
                  coverage_meaning="Text supplied to successful reading tasks; not proof of comprehension, exhaustive evidence extraction or visual inspection.")
    return result


def validate_card(card, paper, evidence, source_inventory):
    """Check citations and inventory identities; semantic adequacy stays explicit."""
    from .schema import SCHEMAS, validate
    validate(card, SCHEMAS["paper_card"])
    if card["paper_id"] != paper["id"]:
        raise ValueError("Paper card refers to a different paper")
    facets = [x["dimension"] for x in card["framework"]]
    if len(facets) != len(FACETS) or set(facets) != set(FACETS):
        raise ValueError("Paper card requires each of the nine framework dimensions exactly once")
    indexed = {e["id"]: e for e in evidence}
    locations = {x["id"] for key in ("sections", "assets") for x in source_inventory[key]}
    assets = {x["id"] for x in source_inventory["assets"]}
    text = source_text(paper)
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_ids":
                    for ref in child:
                        e = indexed.get(ref)
                        if not e or e.get("paper_id") != paper["id"] or e.get("source_hash") != digest(text):
                            raise ValueError("Paper card uses unknown, cross-paper or stale evidence")
                        start, end = e.get("start"), e.get("end")
                        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or " ".join(text[start:end].split()) != " ".join(e.get("quote", "").split()):
                            raise ValueError("Paper card evidence has invalid source offsets")
                elif key == "asset_ids" and any(ref not in assets for ref in child):
                    raise ValueError("Paper card references an unknown figure, table or equation")
                elif key == "target_id" and child not in locations:
                    raise ValueError("Follow-up reading must target an existing section or asset ID")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(card)
    for item in card["framework"]:
        if not item["summary"].strip():
            raise ValueError("Each framework dimension needs an explanation, including missing evidence")
        if item["status"] in {"source_supported", "analysis"} and not item["evidence_ids"]:
            raise ValueError("Assessed framework fields require source evidence")
    for field in ("components", "experiments", "author_limitations", "analyst_concerns", "opportunities"):
        if len(card[field]) > 12:
            raise ValueError("Limit each paper-card detail list to twelve entries")
        for item in card[field]:
            if not item["evidence_ids"]:
                raise ValueError("Paper-card details require evidence; put unavailable details in reading gaps")
    for experiment in card["experiments"]:
        if not any(indexed[ref].get("kind") == "reported_result" for ref in experiment["evidence_ids"]):
            raise ValueError("An experiment result needs reported_result evidence, not only author claims")
    for limitation in card["author_limitations"]:
        if not any(indexed[ref].get("kind") == "limitation" for ref in limitation["evidence_ids"]):
            raise ValueError("Author limitations require explicit limitation evidence; analyst doubts belong in analyst_concerns")
    if len(card["followup_requests"]) > 3:
        raise ValueError("Request at most three targeted follow-up readings")
    return card


def read_paper(controller, paper):
    """Replay cached reading, synthesize a card, then perform bounded gap-driven reads."""
    from .controller import make_evidence
    from .evidence_matching import current_quote_gaps
    selection = paper.get("selection") or {}
    route_ids = list(selection.get("route_ids") or [])
    initial_plan = controller.store.get("search_plans", {}).get("initial", {})
    routes = selection.get("research_routes", initial_plan.get("research_routes", []))
    reading_intent = {
        "reading_role": "landscape" if selection.get("reading_role") == "landscape" else "method",
        "reading_question": selection.get("reading_question", ""),
        "reason": selection.get("reason", ""),
        "route_ids": route_ids,
        "research_routes": [route for route in routes
                            if route.get("id") in route_ids],
    }
    text = source_text(paper)
    source_inventory = inventory(paper)
    parts = chunks(text, controller.config["source_chars"])
    if parts and parts[-1]["end"] < len(text):
        source_inventory["inventory_gaps"].append("Reading index capped at 2000 chunks; remaining source characters cannot be read in this run.")
    read_parts, collected, attempts = [], {}, []
    cards = controller.store.get("paper_cards", {})
    readings = controller.store.get("paper_readings", {})
    cards.pop(paper["id"], None)
    controller.store.set("paper_cards", cards)

    def save():
        retained = [e for e in controller.store.rows("evidence") if e["paper_id"] == paper["id"]
            and e.get("source_hash") == source_inventory["source_hash"] and e.get("source_kind") == "full_text"
            and e.get("extraction_stage") == "inspect_source"
            and e.get("guidance_key") == controller.guidance_keys["inspect_source"]]
        controller.store.replace_evidence(paper["id"], list({e["id"]: e for e in retained + list(collected.values())}.values()))
        readings[paper["id"]] = {"inventory": with_coverage(source_inventory, read_parts),
            "read_chunks": list(read_parts), "followup_attempts": list(attempts),
            "guidance_key": controller.guidance_keys["read_section"]}
        controller.store.set("paper_readings", readings)

    save()

    def read(part, question="", target_id=""):
        excerpt = text[part["start"]:part["end"]]
        payload = {"paper_id": paper["id"], "title": paper["title"], "content_kind": "full_text",
            "excerpt": excerpt, "source_span": part,
            "sections": [s for s in source_inventory["sections"] if s["start"] < part["end"] and s["end"] > part["start"]],
            "assets": [a for a in source_inventory["assets"] if a["start"] < part["end"] and a["end"] > part["start"]],
            "question": question, "reading_intent": reading_intent, "target_id": target_id,
            "reading_coverage": "complete_supplied_text" if excerpt == text else "partial"}
        def records(value):
            records = make_evidence(paper, value["observations"], excerpt)
            # Match within this exact span, even when identical wording recurs elsewhere.
            from .controller import locate_quote
            for record in records:
                local_start, local_end = locate_quote(excerpt, record["quote"])
                start, end = part["start"] + local_start, part["start"] + local_end
                record.update(quote=text[start:end], start=start, end=end, line=text[:start].count("\n") + 1, page=text[:start].count("\f") + 1,
                    extraction_stage="read_section", guidance_key=controller.guidance_keys["read_section"], chunk_id=part["id"])
                record["id"] = "ev_" + digest([record["id"], start, end])[:12]
            return records
        result = controller.task("read_section", payload, records)
        # New evidence invalidates a previous synthesis until it is rebuilt.
        cards.pop(paper["id"], None)
        controller.store.set("paper_cards", cards)
        collected.update({e["id"]: e for e in records(result)})
        read_parts.append(part)
        save()

    for part in initial_chunks(parts, source_inventory, controller.config["max_paper_read_chunks"],
                               reading_intent["reading_role"]):
        read(part, reading_intent["reading_question"])

    def synthesize():
        if not collected:
            return None
        coverage = with_coverage(source_inventory, read_parts)
        payload = {"paper_id": paper["id"], "title": paper["title"], "topic": controller.store.get("topic"),
                   "user_notes": controller.user_notes(), "reading_intent": reading_intent,
                   "quote_gaps": [g for g in current_quote_gaps(controller.store).values() if g['paper_id'] == paper['id']],
                   "inventory": coverage, "evidence": list(collected.values()), "followup_attempts": attempts}
        payload['citation_groups'] = {
            'reported_result_ids': [e['id'] for e in collected.values() if e['kind'] == 'reported_result'],
            'author_limitation_ids': [e['id'] for e in collected.values() if e['kind'] == 'limitation'],
        }
        from .controller import OutputValidationError
        try:
            result = controller.task("paper_card", payload, lambda value: validate_card(value, paper, list(collected.values()), coverage))
        except OutputValidationError as exc:
            controller.store.event('paper_card_skipped', {'paper_id': paper['id'], 'reason': str(exc)})
            controller.progress('[read] 继续使用这篇论文已定位的原文进行构思，其他论文照常分析。')
            return None
        cards[paper["id"]] = {**result, "source_hash": source_inventory["source_hash"], "inventory": coverage,
            "status": "analyzed", "followup_attempts": list(attempts), "evidence_ids": sorted(collected),
            "assessment_boundary": "Source-grounded model interpretation; no independent reproduction or global novelty verification."}
        controller.store.set("paper_cards", cards)
        return result

    card = synthesize()
    if not card:
        return
    targets = {item["id"]: item for key in ("sections", "assets") for item in source_inventory[key]}
    extra_reads = 0
    for request in card["followup_requests"]:
        target = targets[request["target_id"]]
        available = [p for p in parts if p not in read_parts and p["start"] < target.get("context_end", target["end"]) and p["end"] > target["start"]]
        if extra_reads >= controller.config["max_followup_reads"]:
            attempts.append({**request, "status": "reading_limit_reached"})
        elif not available:
            attempts.append({**request, "status": "no_unread_target_text", "note": "Already supplied text or unavailable visual/supplementary content; the question remains unresolved."})
        else:
            # One additional chunk per request; a long section remains partial.
            read(available[0], request["question"], request["target_id"])
            extra_reads += 1
            attempts.append({**request, "status": "additional_text_supplied", "chunk_id": available[0]["id"]})
        save()
    if extra_reads:
        synthesize()
    elif attempts:
        # A request can target text already supplied, or exceed the reading
        # limit. Record that outcome without paying for an identical synthesis.
        cards[paper["id"]]["followup_attempts"] = list(attempts)
        controller.store.set("paper_cards", cards)


def current_cards(papers, evidence, saved, readings):
    refs = {e["id"] for e in evidence}
    result = {}
    for paper in papers:
        text_hash = digest(source_text(paper))
        card = saved.get(paper["id"])
        def cited(value):
            if isinstance(value, dict):
                return set(value.get("evidence_ids", [])) | set().union(*(cited(v) for v in value.values()))
            if isinstance(value, list):
                return set().union(*(cited(v) for v in value))
            return set()
        if paper.get("content_kind") == "full_text" and card and card.get("status") == "analyzed" and card.get("source_hash") == text_hash and cited(card) <= refs:
            result[paper["id"]] = card
        else:
            reading = readings.get(paper["id"], {}).get("inventory", {})
            result[paper["id"]] = {"paper_id": paper["id"], "status": "pending" if paper.get("content_kind") == "full_text" else "source_limited",
                "inventory": reading if reading.get("source_hash") == text_hash else None,
                "reason": "No current grounded analysis card; unavailable sections must not be inferred."}
    return result
