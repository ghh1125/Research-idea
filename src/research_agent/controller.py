"""Evidence checks, bounded hypothesis development, and resumable task execution."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .backend_types import Backend, BackendError, TaskSpec
from .prompts import make_prompt, PROMPT_VERSION
from .schema import SCHEMAS, validate
from .store import Store, digest, now
from .novelty import assess_novelty, validate_comparisons
from .feasibility import assess_feasibility
from .motivation import assess_motivation


class BudgetExhausted(RuntimeError):
    pass


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


def locate_quote(text: str, quote: str):
    """Allow whitespace changes, but never paraphrased or stitched quotations."""
    if len(quote.strip()) < 15:
        raise ValueError("Evidence quote is too short to ground a claim")
    words = re.split(r"\s+", quote.strip())
    match = re.search(r"\s+".join(re.escape(w) for w in words), text)
    if not match:
        raise ValueError("Evidence quote does not appear verbatim in supplied source")
    return match.start(), match.end()


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
    """Select bounded source spans, prioritizing methods/results over prefix-only reading.

    This is a transparent heuristic, not a claim of full-paper understanding.
    Original offsets are recovered when validating each evidence quotation.
    """
    if len(text) <= limit:
        return text
    headings = list(re.finditer(r"(?im)^\s*(?:\d+(?:\.\d+)*[ .]*)?(?:methods?|approach|experiments?|results?|limitations?|discussion|appendix|方法|实验|结果|局限)\b[^\n]*", text))
    positions = [0]
    for match in headings:
        if all(abs(match.start() - p) > max(200, limit // 8) for p in positions):
            positions.append(match.start())
        if len(positions) >= 5:
            break
    if len(positions) < 3:
        positions.extend([len(text) // 2, max(0, len(text) - limit // 3)])
    width = max(1, limit // len(positions))
    spans = sorted((p, min(len(text), p + width)) for p in set(positions))
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
    def __init__(self, store: Store, backend: Backend, config: dict, progress=None):
        self.store, self.backend, self.config = store, backend, config
        self.progress = progress or (lambda message: None)
        self.started = time.monotonic()
        self.previous_elapsed = float(store.get("elapsed_s", 0))

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
        fingerprint = [PROMPT_VERSION, stage, payload, self.config["backend"], self.config.get("model"), self.config.get("api_provider"), self.config.get("base_url")]
        task_id = stage + "_" + digest(fingerprint)[:20]
        previous = self.store.task(task_id)
        if previous and previous["status"] == "succeeded":
            result = json.loads(previous["output"])
            validate(result, SCHEMAS[stage])
            if checker:
                checker(result)
            self.progress(f"cached {stage}")
            return result
        prompt = make_prompt(stage, payload)
        # A single bounded repair for invalid structured outputs or citations.
        for attempt in range(2):
            remaining = self.check_budget()
            self.checkpoint_time()
            self.store.begin_task(task_id, stage)
            self.store.set("calls_used", self.store.get("calls_used", 0) + 1)
            self.progress(f"{stage} (call {self.store.get('calls_used')}/{self.config['max_calls']})")
            spec = TaskSpec(task_id=task_id, stage=stage, prompt=prompt, output_schema=SCHEMAS[stage], workspace=self.store.project,
                            timeout_s=min(float(self.config["timeout_s"]), remaining), model=self.config.get("model") or None)
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
                return result.output
            except ValueError as exc:
                self.store.fail_task(task_id, str(exc))
                if attempt:
                    raise BackendError(f"{stage} failed output/evidence validation after one repair: {exc}") from exc
                prompt = make_prompt(stage, payload) + "\nYour previous output failed local validation: " + str(exc) + ". Produce a corrected complete JSON object. Do not invent evidence.\n"
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
        return {"topic": self.store.get("topic"), "constraints": self.config["constraints"],
                "papers": [{k: p.get(k) for k in ("id", "title", "url", "year", "content_kind")} for p in papers], "evidence": evidence}

    def extract_papers(self):
        for paper in self.store.rows("papers"):
            text = paper.get("text") or paper.get("abstract") or ""
            excerpt = select_excerpt(text, self.config["source_chars"])
            if not excerpt.strip():
                self.store.replace_evidence(paper["id"], [])
                continue
            payload = {"paper_id": paper["id"], "title": paper["title"], "content_kind": paper.get("content_kind", "abstract"),
                       "reading_coverage": "complete_supplied_text" if excerpt == text else "partial", "excerpt": excerpt}
            result = self.task("extract", payload, lambda x: make_evidence(paper, x["observations"], excerpt))
            retained = [e for e in self.store.rows("evidence") if e["paper_id"] == paper["id"]
                and e.get("source_hash") == digest(text) and e.get("source_kind") == paper.get("content_kind", "abstract")]
            generated = make_evidence(paper, result["observations"], excerpt)
            self.store.replace_evidence(paper["id"], list({e["id"]: e for e in retained + generated}.values()))

    def focus_sources(self, candidate):
        """Re-read methods for this hypothesis; related titles only select reading targets."""
        closest = candidate["proposal"].get("closest_work_ids", [])
        papers = {p["id"]: p for p in self.store.rows("papers")}
        selected = [papers[p] for p in closest if p in papers and papers[p].get("content_kind") == "full_text"][:3]
        for paper in selected:
            text = paper.get("text") or paper.get("abstract") or ""
            if not text.strip():
                continue
            excerpt = select_excerpt(text, self.config["source_chars"])
            payload = {"paper_id": paper["id"], "title": paper["title"], "content_kind": "full_text",
                "candidate": candidate["proposal"], "excerpt": excerpt,
                "reading_coverage": "complete_supplied_text" if excerpt == text else "partial"}
            result = self.task("inspect_source", payload, lambda x: make_evidence(paper, x["observations"], excerpt))
            retained = [e for e in self.store.rows("evidence") if e["paper_id"] == paper["id"]]
            generated = make_evidence(paper, result["observations"], excerpt)
            self.store.replace_evidence(paper["id"], list({e["id"]: e for e in retained + generated}.values()))

    def search_once(self, query, reason):
        from .literature import discover, deduplicate
        if not self.config["auto_search"] or self.config["backend"] == "demo":
            return False
        # Successful searches are cached; interrupted/transient failures get one retry.
        key = digest([query, self.config["search_source"]])
        ledger = self.store.get("search_ledger", {})
        previous = ledger.get(key, {})
        if previous.get("status") == "completed" or previous.get("attempts", 0) >= 2:
            return False
        papers = self.store.rows("papers")
        room = self.config["max_papers"] - len(papers)
        if room <= 0:
            return False
        self.check_budget()
        ledger[key] = {"query": query, "reason": reason, "status": "started", "time": now(), "attempts": previous.get("attempts", 0) + 1}
        self.store.set("search_ledger", ledger)
        try:
            found = discover(query, source=self.config["search_source"], limit=min(room, 5), timeout_s=min(30, self.check_budget()), api_key_env=self.config.get("search_api_key_env") or None)
            all_papers = deduplicate(papers + found)
            existing = {p["id"] for p in papers}
            added = [p for p in all_papers if p["id"] not in existing][:room]
            for paper in added:
                paper.setdefault("content_kind", "abstract")
                self.store.put("papers", paper)
            ledger[key].update(status="completed", added=len(added))
            self.store.event("search", ledger[key])
            self.store.set("search_ledger", ledger)
            return bool(added)
        except Exception as exc:
            ledger[key].update(status="failed", error=type(exc).__name__)
            self.store.set("search_ledger", ledger)
            self.store.event("search_failed", ledger[key])
            self.progress("search unavailable; retaining explicit retrieval gap")
            return False

    def run(self):
        self.store.set("status", "running")
        try:
            if not self.store.rows("papers"):
                self.search_once(self.store.get("topic"), "initial discovery")
            if not self.store.rows("papers"):
                raise ValueError("No source material. Import papers with 'research add' or configure a reachable search source.")
            self.extract_papers()
            if not self.store.rows("evidence"):
                raise ValueError("No source-grounded evidence could be extracted. Add substantive paper text.")
            cohort = self.store.get("cohort")
            cohort_key = digest([PROMPT_VERSION, self.store.get("topic"), self.config["constraints"], self.config["max_candidates"]])
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
                        if not candidate["evidence_ids"] or any(not candidate[k].strip() for k in ("hypothesis", "mechanism", "prediction", "falsifier")):
                            raise ValueError("Candidate needs evidence, a mechanism, prediction and falsifier")
                        motive = candidate["motivation"]
                        if not motive["evidence_ids"] or any(not str(v).strip() for k, v in motive.items() if k != "evidence_ids"):
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
        development_key = digest([PROMPT_VERSION, self.config["backend"], self.config.get("model"), self.config.get("api_provider"), self.config.get("base_url"), self.config["constraints"], self.config["max_rounds"]])
        if candidate.get("development_key") not in {None, development_key}:
            self.store.event("candidate_versions_archived", {"candidate_id": candidate["id"], "versions": candidate.get("versions", [])})
            candidate.update(versions=[], development_complete=False)
            candidate.pop("spec", None)
            candidate.pop("review", None)
        candidate["development_key"] = development_key
        versions = list(candidate.get("versions", []))
        current = candidate.get("spec")
        review = candidate.get("review")
        if candidate.get("development_complete"):
            self.progress(f"cached candidate {candidate['id']}")
            return
        self.focus_sources(candidate)
        for round_index in range(len(versions), self.config["max_rounds"]):
            context = self.context()
            evidence_ids = {e["id"] for e in context["evidence"]}
            paper_ids = {p["id"] for p in context["papers"]}
            def spec_check(value):
                check_references(value, evidence_ids, paper_ids)
                motive = value["motivation"]
                if not motive["evidence_ids"] or any(not str(v).strip() for k, v in motive.items() if k != "evidence_ids"):
                    raise ValueError("Method needs a complete, evidence-grounded motivation chain")
                validate_comparisons(value["prior_art"]["overlaps"])
                evidence_gate(value, context["evidence"])
                assess_feasibility(value, context["evidence"])
                if not value["method"]["changes"] or not value["validation"]["first_test"].strip():
                    raise ValueError("Missing concrete change or first test")
            payload = {**context, "candidate": candidate["proposal"], "round": round_index + 1}
            if current is not None:
                payload.update(previous_spec=current, review=review)
            current = self.task("develop" if round_index == 0 else "refine", payload, spec_check)
            novelty, warnings = evidence_gate(current, context["evidence"])
            comparison = assess_novelty(current, context["evidence"])
            feasibility = assess_feasibility(current, context["evidence"])
            warnings.extend(feasibility["warnings"])
            def review_check(value):
                check_references(value, evidence_ids, paper_ids)
                assess_motivation({**candidate["proposal"], "motivation": current["motivation"]}, value, context["evidence"])
            review = self.task("review", {**context, "candidate": candidate["proposal"], "method_spec": current}, review_check)
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
            pending = feasibility["blocking_checks"] or feasibility["unverified_checks"]
            if pending:
                item = pending[0]
                candidate["recommended_action"] = {"kind": "resolve_prerequisite",
                    "description": item.get("verification_plan") or item.get("acquisition_plan") or str(item),
                    "decision_impact": "Resolve this execution prerequisite before treating the method as runnable."}
            else:
                candidate.pop("recommended_action", None)
            versions.append({"round": round_index + 1, "spec": current, "review": review, "novelty_status": novelty, "feasibility_status": feasibility["status"]})
            candidate["versions"] = list(versions)
            self.store.put("candidates", candidate)
            self.store.event("candidate_updated", {"id": candidate["id"], "round": round_index + 1, "novelty_status": novelty, "review_verdict": review["verdict"]})
            action = review["next_action"]
            added_evidence = False
            if round_index + 1 < self.config["max_rounds"] and action["kind"] == "search":
                if self.search_once(action["description"], action["decision_impact"]):
                    self.extract_papers()
                    self.focus_sources(candidate)
                    added_evidence = True
            # Code/experiment actions are proposed, never silently executed.
            if review["verdict"] != "refine" and motivation["status"] != "needs_revision" and not critical and not added_evidence:
                break
        if candidate.get("research_status") == "needs_revision" and len(versions) >= self.config["max_rounds"]:
            candidate["research_status"] = "round_limit_reached"
        candidate["development_complete"] = True
        self.store.put("candidates", candidate)
