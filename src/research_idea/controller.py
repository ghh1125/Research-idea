"""Evidence checks, bounded hypothesis development, and resumable task execution."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .backend_types import Backend, BackendError, TaskSpec
from .evidence_matching import locate_quote, QuoteMatchError, repair_hint, current_quote_gaps
from .prompts import make_prompt, PROMPT_VERSION, stage_version
from .schema import SCHEMAS, validate
from .store import Store, digest, now
from .novelty import assess_novelty, validate_comparisons
from .feasibility import assess_feasibility
from .motivation import assess_motivation
from .local_skills import load_selected_skills, builtin_skill_paths, BUILTIN_NAMES
from .claims import assess_claims, current_claim_audits
from .search_planning import normalize_search_plan
from .search_scope import config_scope
from .selection import rank_metadata
from .paper_reading import read_paper, current_cards


class BudgetExhausted(RuntimeError):
    pass


class OutputValidationError(BackendError):
    """A structured result remained invalid after its one repair."""


def check_references(value, evidence_ids, paper_ids):
    """Reject dangling citations, including inside nested method assumptions."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence_ids":
                if not isinstance(child, list) or any(x not in evidence_ids for x in child):
                    raise ValueError("Unknown evidence ID in model output")
            elif key == "closest_work_ids":
                if not isinstance(child, list) or any(x not in paper_ids for x in child):
                    raise ValueError("Unknown closest-work paper ID")
            elif key == "paper_id" and child not in paper_ids:
                raise ValueError("Unknown paper ID in overlap comparison")
            check_references(child, evidence_ids, paper_ids)
    elif isinstance(value, list):
        for child in value:
            check_references(child, evidence_ids, paper_ids)


def make_evidence(paper: dict, observations: list, excerpt: str) -> list:
    if len(observations) > 6:
        raise ValueError("Extract at most 6 observations per source")
    records = []
    for obs in observations:
        locate_quote(excerpt, obs["quote"])
        original = paper.get("text") or paper.get("abstract", "")
        start, end = locate_quote(original, obs["quote"])
        if not obs["statement"].strip():
            raise ValueError("Empty evidence statement")
        record = dict(obs)
        record["quote"] = original[start:end]
        if record["quote"] != obs["quote"]:
            record["submitted_quote"] = obs["quote"]
        record.update({
            "paper_id": paper["id"], "source_kind": paper.get("content_kind", "abstract"),
            "source_hash": digest(paper.get("text") or paper.get("abstract", "")),
            "start": start, "end": end,
            "line": original[:start].count("\n") + 1,
            "page": original[:start].count("\f") + 1,
            "reading_coverage": "complete_supplied_text" if excerpt == original else "partial",
            "verification": "quote_matched_only",
        })
        record["id"] = "ev_" + digest([paper["id"], record["source_hash"], obs])[:12]
        records.append(record)
    return list({r["id"]: r for r in records}.values())


def select_excerpt(text: str, limit: int) -> str:
    """Sample bounded source spans from distinct section families where identifiable.

    This heading heuristic does not establish complete or semantic reading coverage.
    Original offsets are recovered when validating each evidence quotation.
    """
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    # Select one heading per family rather than the first N headings: many early
    # method subsections must not crowd late experiments, results, or appendices out.
    families = [
        r"(?:(?:proposed|our)\s+)?(?:methods?|methodology|approach|framework)\b|(?:研究)?方法|模型架构",
        r"experiments?\b|experimental\b|evaluation\s+(?:setup|settings?)\b|implementation\s+details\b|setup\b|实验|實驗|评估设置",
        r"(?:(?:main|experimental|evaluation|additional|quantitative|qualitative)\s+)?results?\b|findings\b|(?:主要|实验|评估)?结果",
        r"limitations?\b|discussion\b|局限|讨论|限制",
        r"appendi(?:x|ces)\b|supplementary\b|附录|补充材料",
    ]
    numbering = re.compile(
        r"^(?:\d+(?:\.\d+)*(?:[.)、．:：][ \t]*|[ \t]+)"
        r"|(?:[A-Z](?:\.\d+)*|[IVXLCDM]+)(?:[.)、:：][ \t]*|[ \t]+)"
        r"|第[一二三四五六七八九十百0-9]+[章节][ \t]*"
        r"|[一二三四五六七八九十百]+[、.)．][ \t]*)"
    )
    found = {}
    for match in re.finditer(r"(?m)^[ \t]*[^\n\r]{1,160}\r?$", text):
        heading = re.sub(r"^#{1,6}[ \t]*", "", match.group().strip())
        heading = numbering.sub("", heading).strip()
        for family, pattern in enumerate(families):
            if family not in found and re.match(pattern, heading, re.IGNORECASE):
                found[family] = match.start()
    positions = [0]
    positions.extend(found.values())
    positions = sorted(set(positions))
    if len(positions) < 3:
        # The end position is a tail anchor, converted after allocating the budget.
        positions = sorted(set(positions + [len(text) // 2, len(text)]))
    marker_budget = len(positions) * (len(f"[SOURCE SPAN {len(text)}:{len(text)}]\n") + 2)
    if limit <= marker_budget:
        # A tiny budget cannot hold multiple marked spans; never exceed it.
        return text[:limit]
    width = max(1, (limit - marker_budget) // len(positions))
    spans = sorted((min(p, len(text) - width), min(len(text), p + width))
                   for p in positions)
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return "\n\n".join(f"[SOURCE SPAN {start}:{end}]\n{text[start:end]}" for start, end in merged)


def evidence_gate(spec: dict, evidence: list) -> tuple[str, list[str]]:
    """Model novelty verdict is bounded by actual provenance, never global proof."""
    for assumption in spec["method"]["assumptions"]:
        if assumption["status"] == "source_supported" and not assumption["evidence_ids"]:
            raise ValueError("Source-supported assumption has no evidence")
    assessment = assess_novelty(spec, evidence)
    return assessment["status"], assessment["warnings"]


class Controller:
    def __init__(self, store: Store, backend: Backend, config: dict, progress=None, activity=None):
        self.store, self.backend, self.config = store, backend, config
        self.progress = progress or (lambda message: None)
        self.activity = activity or (lambda stage, result, cached: None)
        self.started = time.monotonic()
        self.previous_elapsed = float(store.get("elapsed_s", 0))
        self.full_text_attempted = set()
        builtins = builtin_skill_paths() if config.get("builtin_skills", True) else []
        if config.get("builtin_skills", True) and len(builtins) != len(BUILTIN_NAMES):
            raise ValueError("Built-in skill files are missing. Reinstall the package or explicitly disable builtin_skills.")
        self.skills = load_selected_skills(builtins + config.get("skill_paths", []), store.project,
            config.get("skill_roots", []), config.get("skill_max_chars", 48000))
        self.skill_manifest = [{k: s[k] for k in ("name", "path", "sha256", "stages", "origin")} for s in self.skills]
        self.skill_key = digest(self.skill_manifest)
        self.guidance_keys = {stage: digest([stage_version(stage), stage,
            [{k: s[k] for k in ("path", "sha256", "stages")} for s in self.skills if stage in s["stages"]]])
            for stage in ("extract", "inspect_source", "read_section")}
        self.reading_settings = [config.get(key) for key in ("deep_reading", "max_paper_read_chunks", "max_followup_reads", "source_chars")]
        self.store.set("active_search_scope", {"source": config["search_source"],
                       "venues": config.get("search_venues", []), **config_scope(config)})
        self.store.set('active_search_windows', {purpose: config_scope(config, purpose) for purpose in ('strategy', 'novelty')})
        if self.store.get("active_skills") != self.skill_manifest:
            self.store.set("active_skills", self.skill_manifest)
            self.store.event("skills_loaded", {"skills": self.skill_manifest})

    def checkpoint_time(self):
        self.store.set("elapsed_s", self.previous_elapsed + time.monotonic() - self.started)

    def check_budget(self):
        elapsed = self.previous_elapsed + time.monotonic() - self.started
        if self.store.get("calls_used", 0) >= self.config["max_calls"]:
            raise BudgetExhausted("Model-call budget exhausted. Increase max_calls in research.toml to continue.")
        if elapsed >= self.config["max_seconds"]:
            raise BudgetExhausted("Wall-time budget exhausted. Increase max_seconds in research.toml to continue.")
        return self.config["max_seconds"] - elapsed

    def task(self, stage, payload, checker=None):
        guidance = [s for s in self.skills if stage in s["stages"]]
        if guidance:
            self.progress('[skill] ' + stage + ' · ' + ', '.join(s['name'] for s in guidance))
        if payload.get('paper_id'):
            paper = next((p for p in self.store.rows('papers') if p['id'] == payload['paper_id']), {})
            self.progress(f"[paper] {paper.get('title', payload.get('title', ''))}\n{payload['paper_id']} · {paper.get('year', '')}\n{paper.get('url', '')}")
        manifest = [{k: s[k] for k in ("path", "sha256", "stages")} for s in guidance]
        fingerprint = [stage_version(stage), stage, payload, self.config["backend"], self.config.get("model"), self.config.get("api_provider"), self.config.get("base_url"), self.config.get("codex_bin"), self.config.get("codex_profile"), manifest]
        if self.config.get("reasoning_effort"):
            fingerprint.append({"reasoning_effort": self.config["reasoning_effort"]})
        task_id = stage + "_" + digest(fingerprint)[:20]
        previous = self.store.task(task_id)
        if (stage == 'paper_card' and previous and previous['status'] == 'failed'
                and (previous.get('error') or '').startswith('OutputValidationError:')):
            raise OutputValidationError(previous['error'])
        if previous and previous["status"] == "succeeded":
            result = json.loads(previous["output"])
            validate(result, SCHEMAS[stage])
            if checker:
                checker(result)
            self.progress(f"cached {stage}")
            self.activity(stage, result, True)
            return result
        prompt = make_prompt(stage, payload, guidance)
        # A single bounded repair for invalid structured outputs or citations.
        for attempt in range(2):
            remaining = self.check_budget()
            self.checkpoint_time()
            self.store.begin_task(task_id, stage)
            self.store.set("calls_used", self.store.get("calls_used", 0) + 1)
            self.progress(f"{stage} (call {self.store.get('calls_used')}/{self.config['max_calls']})" + (' · 修正输出格式或引用' if attempt else ''))
            spec = TaskSpec(task_id=task_id, stage=stage, prompt=prompt, output_schema=SCHEMAS[stage], workspace=self.store.project,
                            timeout_s=min(float(self.config["timeout_s"]), remaining), model=self.config.get("model") or None)
            result = None
            try:
                result = self.backend.generate(spec)
                attempts = result.usage.get("transport_attempts")
                if isinstance(attempts, int):
                    self.store.set("known_http_attempts", self.store.get("known_http_attempts", 0) + attempts)
                validate(result.output, SCHEMAS[stage])
                if checker:
                    checker(result.output)
                self.store.finish_task(task_id, result.output, result.usage)
                self.checkpoint_time()
                self.store.event("task_completed", {"task_id": task_id, "stage": stage, "backend": self.backend.name, "usage": result.usage})
                self.activity(stage, result.output, False)
                return result.output
            except ValueError as exc:
                self.store.fail_task(task_id, str(exc))
                self.store.event('output_repair', {'task_id': task_id, 'stage': stage,
                    'attempt': attempt + 1, 'diagnostic': str(exc)})
                if isinstance(exc, QuoteMatchError) and stage in {'extract', 'read_section', 'inspect_source'}:
                    details = repair_hint(payload['excerpt'], exc.quote)
                    self.store.event('quote_repair', {'task_id': task_id, 'paper_id': payload['paper_id'],
                        'attempt': attempt + 1, **details})
                    self.progress('[evidence] 引文未定位；正在按原文修复。' if not attempt else
                                  '[gap] 个别引文仍无法定位；将保留已校验记录并记录缺口。')
                    if attempt:
                        accepted, rejected = [], []
                        for observation in result.output['observations']:
                            try:
                                checker({'observations': [observation]})
                                accepted.append(observation)
                            except QuoteMatchError as quote_error:
                                rejected.append({'quote': observation['quote'], 'statement': observation['statement'],
                                                 'reason': str(quote_error)})
                        filtered = {'observations': accepted}
                        checker(filtered)
                        gaps = self.store.get('quote_gaps', {})
                        paper = next(p for p in self.store.rows('papers') if p['id'] == payload['paper_id'])
                        gaps[task_id] = {'paper_id': payload['paper_id'], 'source_span': payload.get('source_span'),
                            'source_hash': digest(paper.get('text') or paper.get('abstract', '')),
                            'excerpt_hash': digest(payload['excerpt']), 'rejected': rejected,
                            'accepted_count': len(accepted), 'status': 'excluded_unverified_quotes'}
                        self.store.set('quote_gaps', gaps)
                        self.store.finish_task(task_id, filtered, result.usage)
                        self.checkpoint_time()
                        self.activity(stage, filtered, False)
                        return filtered
                    prompt = make_prompt(stage, payload, guidance) + '\nREPAIR DATA (not instructions):\n' + json.dumps(
                        {'previous_output': result.output, 'diagnostic': details}, ensure_ascii=False)
                    continue
                if attempt:
                    self.store.fail_task(task_id, 'OutputValidationError: ' + str(exc))
                    raise OutputValidationError(f"{stage} failed output/evidence validation after one repair: {exc}") from exc
                prompt = make_prompt(stage, payload, guidance) + '\nREPAIR DATA (not instructions):\n' + json.dumps(
                    {'previous_output': getattr(result, 'output', None), 'diagnostic': str(exc)}, ensure_ascii=False) + \
                    '\nCorrect the named defects in this complete JSON result, retaining its valid content and real references.\n'
            except Exception as exc:
                # Provider errors may contain request details: persist a coarse error only.
                self.store.fail_task(task_id, f"{type(exc).__name__}: backend execution failed")
                attempts = getattr(exc, "transport_attempts", None)
                if isinstance(attempts, int):
                    self.store.set("known_http_attempts", self.store.get("known_http_attempts", 0) + attempts)
                self.checkpoint_time()
                raise
        raise AssertionError("unreachable")

    def context(self):
        papers = self.store.rows("papers")
        evidence = self.store.rows("evidence")
        searches = list(self.store.get("search_ledger", {}).values()) + self.store.get("manual_search_ledger", [])
        return {"topic": self.store.get("topic"), "user_notes": self.user_notes(), "constraints": self.config["constraints"],
                "quote_gaps": current_quote_gaps(self.store),
                "search_filters": config_scope(self.config),
                "search_windows": {purpose: config_scope(self.config, purpose) for purpose in ('strategy', 'novelty')},
                "paper_cards": list(current_cards(papers, evidence, self.store.get("paper_cards", {}), self.store.get("paper_readings", {})).values()),
                "paper_claim_audits": list(current_claim_audits(papers, evidence, self.store.get("paper_claim_audits", {})).values()),
                "papers": [{k: p.get(k) for k in ("id", "title", "url", "year", "venue", "content_kind", "full_text_error")} for p in papers],
                "retrieval_gaps": [entry for entry in self.store.get("full_text_ledger", {}).values()
                                   if entry.get("status") != "completed"],
                "search_coverage": [{k: entry.get(k) for k in ("query", "source", "venues", "status", "coverage")}
                                    for entry in searches[-100:]], "evidence": evidence}

    def user_notes(self):
        return [m['content'][:3000] for m in self.store.get('chat_messages', [])
                if m.get('role') == 'user'][-8:]

    def reading_papers(self):
        papers = self.store.rows('papers')
        if len(papers) <= self.config['max_papers']:
            return papers
        queries = [q['query'] for plan in self.store.get('search_plans', {}).values() for q in plan.get('queries', [])]
        ranked = rank_metadata(papers, queries or [self.store.get('topic', '')])
        return ranked[:self.config['max_papers']]

    def retrieve_full_texts(self, selected_ids=None):
        """Acquire bounded source text; a failed download remains an evidence gap."""
        from .literature import fetch_full_text, LiteratureError
        if (not self.config["auto_search"] or not self.config.get("fetch_full_text", True)
                or self.config["backend"] == "demo"):
            return False
        changed = False
        ledger = self.store.get("full_text_ledger", {})
        for paper in self.reading_papers():
            if selected_ids is not None and paper["id"] not in selected_ids:
                continue
            if paper.get("content_kind") != "abstract":
                continue
            key = digest([paper["id"], paper.get("url"), paper.get("pdf_url"), paper.get("locations")])
            previous = ledger.get(key, {})
            if key in self.full_text_attempted or previous.get("status") == "completed" or previous.get("attempts", 0) >= 2:
                continue
            self.check_budget()
            entry = {"paper_id": paper["id"], "status": "started", "time": now(),
                     "attempts": previous.get("attempts", 0) + 1}
            ledger[key] = entry
            self.store.set("full_text_ledger", ledger)
            self.full_text_attempted.add(key)
            try:
                if paper.get('source') == 'official_proceedings' and not paper.get('pdf_url'):
                    from .proceedings import enrich_selected
                    paper = enrich_selected(paper, timeout_s=min(15, self.check_budget()))
                    self.store.put('papers', paper)
                enriched = fetch_full_text(paper, timeout_s=min(30, self.check_budget()))
                if enriched.get("content_kind") != "full_text" or not enriched.get("text", "").strip():
                    raise LiteratureError(enriched.get("full_text_error") or "No full text was extracted")
                enriched["id"] = paper["id"]  # Keep existing evidence references stable.
                enriched.pop("full_text_error", None)
                self.store.put("papers", enriched)
                entry.update(status="completed", characters=len(enriched["text"]))
                changed = True
                self.progress(f"full text acquired: {paper['id']}")
            except LiteratureError as exc:
                entry.update(status="failed", error=str(exc))
                self.store.put("papers", dict(paper, full_text_error=str(exc)))
                self.progress(f"full text unavailable: {paper['id']}; keeping retrieval gap")
            finally:
                self.store.set("full_text_ledger", ledger)
                self.store.event("full_text_retrieval", entry)
                self.checkpoint_time()
        return changed

    def read_papers(self):
        deep = self.config.get("deep_reading", True) and self.config["backend"] != "demo"
        self.extract_papers(skip_full_text=deep)
        if deep:
            for paper in self.reading_papers():
                if paper.get("content_kind") == "full_text":
                    read_paper(self, paper)

    def extract_papers(self, skip_full_text=False):
        for paper in self.reading_papers():
            if skip_full_text and paper.get("content_kind") == "full_text":
                continue
            text = paper.get("text") or paper.get("abstract") or ""
            excerpt = select_excerpt(text, self.config["source_chars"])
            if not excerpt.strip():
                self.store.replace_evidence(paper["id"], [])
                continue
            payload = {"paper_id": paper["id"], "title": paper["title"], "content_kind": paper.get("content_kind", "abstract"),
                       "reading_coverage": "complete_supplied_text" if excerpt == text else "partial", "excerpt": excerpt}
            result = self.task("extract", payload, lambda x: make_evidence(paper, x["observations"], excerpt))
            # Ordinary extraction replaces its previous interpretation, including
            # when the new result is empty. Only compatible focused readings may
            # survive; legacy records have no trustworthy extraction provenance.
            retained = [e for e in self.store.rows("evidence") if e["paper_id"] == paper["id"]
                and e.get("source_hash") == digest(text) and e.get("source_kind") == paper.get("content_kind", "abstract")
                and e.get("extraction_stage") == "inspect_source"
                and e.get("guidance_key") == self.guidance_keys["inspect_source"]]
            generated = make_evidence(paper, result["observations"], excerpt)
            for record in generated:
                record.update(extraction_stage="extract", guidance_key=self.guidance_keys["extract"])
            self.store.replace_evidence(paper["id"], list({e["id"]: e for e in retained + generated}.values()))

    def audit_papers(self):
        """Interpret reported experiments without treating author claims as proof."""
        audits = {}
        self.store.set("paper_claim_audits", audits)
        evidence = self.store.rows("evidence")
        for paper in self.reading_papers():
            own_evidence = [e for e in evidence if e["paper_id"] == paper["id"]]
            if paper.get("content_kind") != "full_text" or not own_evidence:
                audits[paper["id"]] = {"paper_id": paper["id"], "status": "insufficient_evidence",
                    "source_hash": digest(paper.get("text") or paper.get("abstract", "")),
                    "claims": [], "warnings": ["No grounded full-text experiment evidence is available; author claims do not establish problem resolution."],
                    "reading_coverage": {"experiments": "unavailable", "appendix": "unavailable", "notes": "Full-text claim audit not performed."}}
                continue
            source_text = paper.get("text") or paper.get("abstract", "")
            excerpt = select_excerpt(source_text, self.config["source_chars"])
            payload = {"paper_id": paper["id"], "title": paper["title"], "content_kind": "full_text",
                "excerpt": excerpt, "evidence": own_evidence,
                "paper_card": current_cards([paper], own_evidence, self.store.get("paper_cards", {}), self.store.get("paper_readings", {}))[paper["id"]],
                "reading_coverage": "complete_supplied_text" if excerpt == source_text else "partial"}
            result = self.task("audit_claims", payload, lambda value: assess_claims(value, paper, own_evidence))
            audits[paper["id"]] = {**assess_claims(result, paper, own_evidence), "source_hash": digest(source_text)}
            # Persist each completed paper so a budget stop retains useful work.
            self.store.set("paper_claim_audits", audits)
        self.store.set("paper_claim_audits", audits)

    def plan_search(self, candidate=None):
        payload = {"topic": self.store.get("topic"), "constraints": self.config["constraints"],
                   "venues": self.config.get("search_venues", []), "source": self.config["search_source"],
                   "filters": config_scope(self.config, 'novelty' if candidate else 'strategy'),
                   "purpose": 'recent_candidate_overlap' if candidate else 'strategy_discovery'}
        if candidate is not None:
            payload["candidate"] = candidate["proposal"]
        result = self.task("plan_search", payload, normalize_search_plan)
        plan = normalize_search_plan(result)
        key = candidate["id"] if candidate else "initial"
        plans = self.store.get("search_plans", {})
        plans[key] = plan
        self.store.set("search_plans", plans)
        return plan

    def initial_search(self):
        if not self.config["auto_search"] or self.config["backend"] == "demo":
            return
        scope = config_scope(self.config)
        self.progress(f"[strategy] 寻找方法与值得研究的问题 · {scope['since']} → {scope['until']}")
        # Reserve corpus capacity for hypothesis-specific searches after brainstorming.
        target = max(1, self.config["max_papers"] // 2)
        if len(self.store.rows("papers")) >= target:
            return
        plan = self.plan_search()
        keys = []
        for query in plan["queries"]:
            keys.append(self.search_once(query["query"], "initial: " + query["rationale"], max_new=0))
        self.select_search_results(keys, target - len(self.store.rows("papers")))

    def search_for_candidate(self, candidate):
        if not self.config["auto_search"] or self.config["backend"] == "demo":
            return
        scope = config_scope(self.config, 'novelty')
        self.progress(f"[novelty] 对比候选的动机、解释与核心主张 · {scope['since']} → {scope['until']}")
        room = self.config["max_papers"] - len(self.store.rows("papers"))
        if room <= 0:
            return
        plan = self.plan_search(candidate)
        quota = max(1, self.config["max_papers"] // (2 * self.config["max_candidates"]))
        before_ids = {p["id"] for p in self.store.rows("papers")}
        keys = [self.search_once(query["query"], "candidate " + candidate["id"] + ": " + query["rationale"],
                                 max_new=0, purpose='novelty') for query in plan["queries"]]
        if self.select_search_results(keys, min(room, quota)):
            self.read_papers()
        new_ids = [p["id"] for p in self.store.rows("papers") if p["id"] not in before_ids]
        candidate["retrieved_work_ids"] = list(dict.fromkeys(candidate.get("retrieved_work_ids", []) + new_ids))

    def focus_sources(self, candidate):
        """Re-read methods for this hypothesis; related titles only select reading targets."""
        closest = list(dict.fromkeys(candidate.get("retrieved_work_ids", []) + candidate["proposal"].get("closest_work_ids", [])))
        self.progress('[novelty] 定向比较已知近邻：方法相似仅是阅读入口；重点检查问题动机、因果解释和可检验主张。')
        papers = {p["id"]: p for p in self.store.rows("papers")}
        selected = [papers[p] for p in closest if p in papers and papers[p].get("content_kind") == "full_text"][:3]
        scope = digest(candidate["proposal"])
        for paper in selected:
            text = paper.get("text") or paper.get("abstract") or ""
            if not text.strip():
                continue
            excerpt = select_excerpt(text, self.config["source_chars"])
            payload = {"paper_id": paper["id"], "title": paper["title"], "content_kind": "full_text",
                "candidate": candidate["proposal"], "excerpt": excerpt,
                "reading_coverage": "complete_supplied_text" if excerpt == text else "partial"}
            result = self.task("inspect_source", payload, lambda x: make_evidence(paper, x["observations"], excerpt))
            retained = [e for e in self.store.rows("evidence") if e["paper_id"] == paper["id"]
                and e.get("source_hash") == digest(text) and e.get("source_kind") == "full_text"
                and e.get("extraction_stage") in self.guidance_keys
                and e.get("guidance_key") == self.guidance_keys[e["extraction_stage"]]
                and not (e["extraction_stage"] == "inspect_source" and e.get("extraction_scope") == scope)]
            generated = make_evidence(paper, result["observations"], excerpt)
            for record in generated:
                record.update(extraction_stage="inspect_source", guidance_key=self.guidance_keys["inspect_source"],
                              extraction_scope=scope)
            self.store.replace_evidence(paper["id"], list({e["id"]: e for e in retained + generated}.values()))

    def select_search_results(self, keys, limit):
        from .literature import deduplicate
        ledger = self.store.get("search_ledger", {})
        entries = [ledger[key] for key in keys if key in ledger]
        records = deduplicate([paper for entry in entries for paper in entry.get("metadata", [])])
        ranked = rank_metadata(records, [entry["query"] for entry in entries])
        papers = self.store.rows("papers")
        selected, added, updated = set(), 0, 0
        for paper in ranked:
            aliases = set(paper['aliases'])
            existing = next((p for p in papers if aliases.intersection(p.get('aliases', [p['id']]))), None)
            if existing:
                merged = deduplicate([existing, paper])[0]
                merged['id'] = existing['id']
                selected.add(existing['id'])
                if merged != existing:
                    self.store.put('papers', merged)
                    updated += 1
            elif added < limit and len(papers) < self.config['max_papers']:
                self.store.put('papers', paper)
                papers.append(paper)
                selected.add(paper['id'])
                added += 1
        audit = {'time': now(), 'queries': [entry['query'] for entry in entries],
                 'screened': len(ranked), 'selected_ids': sorted(selected), 'limit': limit,
                 'ranking': [{'paper_id': p['id'], 'title': p['title'], **p['selection']} for p in ranked]}
        selections = self.store.get('paper_selections', [])
        self.store.set('paper_selections', (selections + [audit])[-100:])
        self.progress(f"[search] 摘要池 {len(ranked)} 篇；按相关度档位、日期排序，选入 {added} 篇；全文阅读上限 {self.config['max_papers']} 篇")
        for paper in papers:
            if paper['id'] in selected:
                self.progress(f"[paper] {paper['title']} · {paper.get('publication_date') or paper.get('year', '')}\n{paper['id']}\n{paper.get('url', '')}")
        hydrated = self.retrieve_full_texts(selected)
        return bool(added or updated or hydrated)

    def search_once(self, query, reason, max_new=None, purpose='strategy'):
        from .literature import discover, arxiv_query_expression
        if not self.config["auto_search"] or self.config["backend"] == "demo":
            return False
        venues = self.config.get("search_venues", [])
        expression = arxiv_query_expression(query) if self.config["search_source"] == "arxiv" else query
        scope = config_scope(self.config, purpose)
        recall = self.config.get('search_results_per_query', 20)
        key = digest([expression, self.config["search_source"], venues, scope, recall])
        ledger = self.store.get("search_ledger", {})
        previous = ledger.get(key, {})
        if previous.get("status") == "completed" or previous.get("attempts", 0) >= 2:
            return key if max_new == 0 else False
        self.check_budget()
        ledger[key] = {"query": query, "reason": reason, "source": self.config["search_source"], "purpose": purpose,
                       "venues": venues, "filters": scope, "status": "started", "time": now(), "attempts": previous.get("attempts", 0) + 1}
        self.store.set("search_ledger", ledger)
        self.progress(f"[search] {query}\n目的：{reason}\n日期：{scope['since']} → {scope['until']}\n会议：{'、'.join(venues) or '按主题检索'} · arXiv：{'、'.join(scope['arxiv_categories'])}")
        try:
            found = discover(query, source=self.config["search_source"], limit=recall,
                timeout_s=min(60, self.check_budget()), api_key_env=self.config.get("search_api_key_env") or None,
                venues=venues, cache_dir=self.store.project / "metadata-cache", **scope)
            ledger[key].update(status="completed", found=len(found), limit=recall,
                              metadata=list(found), coverage=getattr(found, "coverage", {}))
            self.store.set("search_ledger", ledger)
            self.store.event("search", {k: v for k, v in ledger[key].items() if k != 'metadata'})
            if max_new == 0:
                return key
            room = self.config['max_papers'] - len(self.store.rows('papers'))
            return self.select_search_results([key], min(room, max_new if max_new is not None else 3))
        except BudgetExhausted:
            raise
        except Exception as exc:
            ledger[key].update(status="failed", error=type(exc).__name__)
            self.store.set("search_ledger", ledger)
            self.store.event("search_failed", ledger[key])
            self.progress('[search] 这一路检索暂未返回结果，继续使用其他来源和已有资料。')
            return key if max_new == 0 else False

    def run(self):
        self.store.set("status", "running")
        try:
            self.initial_search()
            if not self.store.rows("papers"):
                self.progress('[analysis] 先根据研究方向构思问题假设，并给出具体方法；后续检索用于对比已有工作。')
            self.retrieve_full_texts()
            self.read_papers()
            self.audit_papers()
            cohort = self.store.get("cohort")
            cohort_key = digest([PROMPT_VERSION, self.skill_key, self.reading_settings, self.store.get("topic"), self.user_notes(), self.config["constraints"], self.config["max_candidates"]])
            cohort_key = digest([cohort_key, config_scope(self.config), config_scope(self.config, 'novelty')])
            if self.config.get("reasoning_effort"):
                cohort_key = digest([cohort_key, self.config["reasoning_effort"]])
            if cohort:
                try:
                    check_references(cohort["proposed"], {e["id"] for e in self.store.rows("evidence")}, {p["id"] for p in self.store.rows("papers")})
                except ValueError:
                    cohort = None
            cohort_created = False
            if not cohort or cohort.get("key") != cohort_key:
                context = self.context()
                refs = lambda value: check_references(value, {e["id"] for e in context["evidence"]}, {p["id"] for p in context["papers"]})
                problem = self.task("map", context, refs)
                self.store.set("problem_model", problem)
                proposal_payload = {**context, "problem_model": problem, "max_candidates": self.config["max_candidates"]}
                def validate_proposal(value):
                    refs(value)
                    if len(value["candidates"]) > self.config["max_candidates"]:
                        raise ValueError("Too many candidates")
                    for candidate in value["candidates"]:
                        if any(not candidate[k].strip() for k in ("hypothesis", "mechanism", "prediction", "falsifier")):
                            raise ValueError("Candidate needs evidence, a mechanism, prediction and falsifier")
                        motive = candidate["motivation"]
                        if (not motive["evidence_ids"] and motive['basis'] == 'source_observation') or any(not str(v).strip() for k, v in motive.items() if k != "evidence_ids"):
                            raise ValueError("Candidate needs a grounded problem-motivation-method chain and necessity test")
                    if not value["candidates"] and not value["no_candidate_reason"].strip():
                        raise ValueError("No-candidate outcome requires a reason")
                proposed = self.task("propose", proposal_payload, validate_proposal)
                if self.store.rows("candidates"):
                    self.store.event("cohort_archived", {"candidates": self.store.rows("candidates")})
                cohort = {"key": cohort_key, "proposed": proposed, "created_at": now()}
                self.store.set("cohort", cohort)
                self.store.set("no_candidate_reason", proposed["no_candidate_reason"])
                cohort_created = True
            else:
                proposed = cohort["proposed"]
            old = {} if cohort_created else {c["id"]: c for c in self.store.rows("candidates")}
            candidates = []
            for item in proposed["candidates"]:
                idea_id = "idea_" + digest(item)[:10]
                candidate = {"id": idea_id, "proposal": item, "versions": [], "execution_status": "pending", "research_status": "proposed", "empirical_status": "untested"}
                if idea_id in old:
                    candidate = old[idea_id]
                candidates.append(candidate)
            self.store.replace_candidates(candidates)
            for candidate in candidates:
                self.develop_candidate(candidate)
            self.store.set("status", "completed")
            self.store.event("run_completed", {"candidate_count": len(candidates)})
        except BudgetExhausted:
            self.store.set("status", "budget_exhausted")
            raise
        except Exception:
            self.store.set("status", "blocked")
            raise
        finally:
            self.store.set("elapsed_s", self.previous_elapsed + time.monotonic() - self.started)

    def develop_candidate(self, candidate):
        # Keep an immutable reference for the bounded revision task. This is a
        # record of the original proposal, not an automated semantic drift test.
        snapshot = lambda value: json.loads(json.dumps(value, ensure_ascii=False))
        candidate.setdefault("original_anchor", {
            field: candidate["proposal"].get(field, "")
            for field in ("problem", "hypothesis", "prediction")
        })
        original_anchor = snapshot(candidate["original_anchor"])
        anchored_proposal = {**candidate["proposal"], **original_anchor}
        substantive_sections = ("method", "motivation", "prior_art", "novelty_claim", "feasibility", "validation")
        progress_limitation = (
            "Exact structured-content and evidence-ID comparison only; wording changes may be counted "
            "as changes, and changed text does not establish that an objection was resolved."
        )

        def changed_fields(before, after, path=""):
            if isinstance(before, dict) and isinstance(after, dict):
                changes = []
                for key in sorted(set(before) | set(after)):
                    changes.extend(changed_fields(before.get(key), after.get(key), f"{path}.{key}" if path else key))
                return changes
            return [] if before == after else [{"field": path, "previous": snapshot(before), "current": snapshot(after)}]

        development_key = digest([PROMPT_VERSION, self.skill_key, self.config["backend"], self.config.get("model"), self.config.get("api_provider"), self.config.get("base_url"), self.config.get("codex_bin"), self.config.get("codex_profile"), self.config["constraints"], self.config["max_rounds"], self.reading_settings])
        if self.config.get("reasoning_effort"):
            development_key = digest([development_key, self.config["reasoning_effort"]])
        if candidate.get("development_key") not in {None, development_key}:
            self.store.event("candidate_versions_archived", {"candidate_id": candidate["id"], "versions": candidate.get("versions", [])})
            candidate.update(versions=[], dialogue=[], development_complete=False)
            candidate.pop("spec", None)
            candidate.pop("review", None)
        candidate["development_key"] = development_key
        versions = list(candidate.get("versions", []))
        # A spec may have been saved just before an interrupted review. Resume
        # from the last completed round so that the same task input hits cache.
        current = versions[-1]['spec'] if versions else None
        review = versions[-1]['review'] if versions else None
        if candidate.get("development_complete"):
            self.progress(f"cached candidate {candidate['id']}")
            return
        self.search_for_candidate(candidate)
        self.focus_sources(candidate)
        self.audit_papers()
        for round_index in range(len(versions), self.config["max_rounds"]):
            context = self.context()
            evidence_ids = {e["id"] for e in context["evidence"]}
            paper_ids = {p["id"] for p in context["papers"]}
            def spec_check(value):
                check_references(value, evidence_ids, paper_ids)
                motive = value["motivation"]
                if (not motive["evidence_ids"] and motive['basis'] == 'source_observation') or any(not str(v).strip() for k, v in motive.items() if k != "evidence_ids"):
                    raise ValueError("Method needs a complete, evidence-grounded motivation chain")
                validate_comparisons(value["prior_art"]["overlaps"])
                evidence_gate(value, context["evidence"])
                assess_feasibility(value, context["evidence"])
                if not value["method"]["changes"] or not value["validation"]["first_test"].strip():
                    raise ValueError("Missing concrete change or first test")
                if round_index:
                    requested = {item['issue'] for item in (review or {}).get('issues', [])}
                    responses = value['review_responses']
                    answered = [item['issue'] for item in responses]
                    if set(answered) != requested or len(answered) != len(set(answered)):
                        raise ValueError('Respond once to each review issue; adopt, adapt, decline with reasons, or turn it into a test')
                    if any(not r['change'].strip() or not r['reason'].strip() for r in responses):
                        raise ValueError('Every review response needs a concrete design choice and reason')
            previous_spec, previous_review = current, review
            previous_record = versions[-1].get("revision_record", {}) if versions else {}
            previous_evidence_ids = previous_record.get("evidence_ids")
            payload = {**context, "candidate": anchored_proposal, "round": round_index + 1}
            if current is not None:
                payload.update(previous_spec=current, review=review)
                if previous_record:
                    payload["previous_revision_record"] = previous_record
            current = self.task("develop" if round_index == 0 else "refine", payload, spec_check)
            candidate.update(spec=current, empirical_status='untested', execution_status='running')
            self.store.put('candidates', candidate)
            novelty, warnings = evidence_gate(current, context["evidence"])
            comparison = assess_novelty(current, context["evidence"])
            feasibility = assess_feasibility(current, context["evidence"])
            warnings.extend(feasibility["warnings"])
            def review_check(value):
                check_references(value, evidence_ids, paper_ids)
                assess_motivation({**candidate["proposal"], "motivation": current["motivation"]}, value, context["evidence"])
            review = self.task("review", {**context, "candidate": anchored_proposal, "method_spec": current}, review_check)
            motivation = assess_motivation({**candidate["proposal"], "motivation": current["motivation"]}, review, context["evidence"])
            warnings.extend(motivation["warnings"])
            # A review verdict alone cannot prove novelty coverage or empirical success.
            if review["verdict"] == "covered" and novelty != "covered":
                warnings.append("Reviewer coverage opinion is unconfirmed; retain candidate for targeted checking.")
            critical = any(i["severity"] == "critical" for i in review["issues"])
            research_status = "prerequisites_unverified" if feasibility["status"] == "prerequisites_unverified" else "specified_for_test"
            if review["verdict"] == "blocked":
                research_status = "implementation_blocked"
            elif review["verdict"] == "refine" or critical:
                research_status = "needs_revision"
            if motivation["status"] == "needs_revision":
                research_status = "needs_revision"
            elif motivation["status"] == "motivation_unresolved" and research_status == "specified_for_test":
                research_status = "motivation_unresolved"
            if novelty == "covered":
                research_status = "overlap_requires_confirmation"
            if feasibility["status"] == "blocked":
                research_status = "implementation_blocked"
            candidate.update(spec=current, review=review, novelty_status=novelty, warnings=warnings,
                comparison_gaps=comparison["comparison_gaps"], feasibility_status=feasibility["status"], feasibility_assessment=feasibility,
                motivation_status=motivation["status"], motivation_assessment=motivation,
                empirical_status="untested", research_status=research_status, execution_status="completed",
                review_scope="separate task using configured backend; not empirical validation")
            pending = feasibility["blocking_checks"]
            if pending:
                item = pending[0]
                candidate["recommended_action"] = {"kind": "resolve_prerequisite",
                    "description": item.get("verification_plan") or item.get("acquisition_plan") or str(item),
                    "decision_impact": "Choose an available implementation path for this design."}
            else:
                candidate.pop("recommended_action", None)
            changes = [] if previous_spec is None else changed_fields(
                {key: previous_spec.get(key) for key in substantive_sections},
                {key: current.get(key) for key in substantive_sections})
            same_evidence = previous_evidence_ids is not None and evidence_ids == set(previous_evidence_ids)
            exact_repeat = previous_spec is not None and not changes and same_evidence
            revision_record = {
                "original_anchor": snapshot(original_anchor),
                "previous_objections": snapshot((previous_review or {}).get("issues", [])),
                "previous_revision_instructions": (previous_review or {}).get("revision_instructions", ""),
                "changed_fields": changes,
                "evidence_ids": sorted(evidence_ids),
                "new_evidence_ids": sorted(evidence_ids - set(previous_evidence_ids or [])),
                "designer_responses": snapshot(current.get('review_responses', [])),
                "pending_concerns": {
                    "issues": snapshot(review["issues"]),
                    "unresolved_questions": snapshot(review["unresolved_questions"]),
                    "revision_instructions": review["revision_instructions"],
                },
                "progress_check": {
                    "method": "exact_structured_content_and_evidence_ids",
                    "outcome": ("initial" if previous_spec is None else "unchanged" if exact_repeat
                        else "baseline_unavailable" if not changes and previous_evidence_ids is None else "changed"),
                    "limitation": progress_limitation,
                },
            }
            versions.append({"round": round_index + 1, "spec": current, "review": review, "novelty_status": novelty,
                "feasibility_status": feasibility["status"], "revision_record": revision_record})
            candidate.setdefault('dialogue', []).extend([
                {'round': round_index + 1, 'from': 'designer', 'to': 'reviewer',
                 'method': snapshot(current['method']['changes']), 'responses': snapshot(current.get('review_responses', []))},
                {'round': round_index + 1, 'from': 'reviewer', 'to': 'designer',
                 'issues': snapshot(review['issues']), 'revision': review['revision_instructions']}])
            candidate["versions"] = list(versions)
            self.store.put("candidates", candidate)
            self.store.event("candidate_updated", {"id": candidate["id"], "round": round_index + 1, "novelty_status": novelty, "review_verdict": review["verdict"]})
            action = review["next_action"]
            added_evidence = False
            if round_index + 1 < self.config["max_rounds"] and action["kind"] == "search":
                if self.search_once(action["description"], action["decision_impact"], purpose='novelty'):
                    self.read_papers()
                    self.focus_sources(candidate)
                    self.audit_papers()
                    added_evidence = True
            # A search may still break an otherwise repeated revision. Compare
            # actual evidence IDs, not merely a successful retrieval response.
            after_action_ids = {e["id"] for e in self.store.rows("evidence")}
            revision_record["evidence_ids_after_action"] = sorted(after_action_ids)
            revision_record["new_evidence_ids_after_action"] = sorted(after_action_ids - evidence_ids)
            if exact_repeat and after_action_ids != evidence_ids:
                revision_record["progress_check"]["outcome"] = "evidence_changed_after_action"
            needs_more_revision = (review["verdict"] == 'refine' or novelty == 'covered'
                                   or motivation["status"] == "needs_revision" or critical or feasibility['status'] == 'blocked')
            if exact_repeat and after_action_ids == evidence_ids and needs_more_revision:
                candidate["research_status"] = "no_detectable_progress"
                revision_record["progress_check"]["outcome"] = "no_detectable_progress"
                candidate["warnings"].append("Repeated refinement changed neither the tracked content nor the evidence; candidate retained. " + progress_limitation)
                concern = next((issue["issue"] for issue in review["issues"]), None)
                concern = concern or next(iter(review["unresolved_questions"]), None) or review["revision_instructions"]
                candidate["recommended_action"] = {
                    "kind": "run_experiment",
                    "description": current['validation']['first_test'],
                    "decision_impact": "Use the planned test to distinguish the remaining design question: " + (concern or current['validation']['weakest_assumption']),
                }
                self.progress('[review] 本轮讨论已收束：保留完整方案，把剩余设计分歧放进第一步测试。')
                self.store.event("revision_stalled", {"candidate_id": candidate["id"], "round": round_index + 1,
                    "reason": "exact_repeat_without_new_evidence"})
                break
            # Code/experiment actions are proposed, never silently executed.
            if not needs_more_revision and not added_evidence:
                break
        if candidate.get("research_status") == "needs_revision" and len(versions) >= self.config["max_rounds"]:
            candidate["research_status"] = "round_limit_reached"
        candidate["development_complete"] = True
        self.store.put("candidates", candidate)
