"""Deterministic prerequisite gates; no model opinion establishes executability.

The assessment verifies completeness, reference identity and declared blockers.
It cannot establish that a citation entails a claim or that a planned method
will work. Only execution and subsequent evidence analysis can address those.
"""
from __future__ import annotations

from collections import Counter


DIMENSIONS = (
    "data_access", "inference_signal", "interface", "learning_signal",
    "compute", "evaluation", "minimal_test",
)
CHECK_STATUSES = {"source_supported", "unverified", "blocked", "not_applicable"}
SIGNAL_AVAILABILITIES = {"source_supported", "unverified", "unavailable"}
SIGNAL_STAGES = {"training", "inference", "evaluation"}
_EMPTY_REASONS = {"n/a", "na", "none", "not applicable", "not_applicable",
                  "不适用", "无", "无需", "不需要"}


def _text(record: dict, field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{field} must contain a concrete nonempty explanation")
    return value


def _references(record: dict, evidence_ids: set[str], label: str, supported: bool) -> list[str]:
    refs = record.get("evidence_ids")
    if not isinstance(refs, list) or any(not isinstance(x, str) or x not in evidence_ids for x in refs):
        raise ValueError(f"{label} contains an unknown evidence ID")
    if supported and not refs:
        raise ValueError(f"{label}: source_supported requires evidence IDs")
    return list(refs)


def assess_feasibility(spec: dict, evidence: list[dict]) -> dict:
    """Assess an entire method spec's ``feasibility`` field without execution.

    Required but unavailable signals always block, at any lifecycle stage.
    Every dimension must appear exactly once; malformed outputs raise
    ValueError so the controller can request a bounded structured repair.
    ``specified_not_executed`` is the strongest possible result here.
    """
    feasibility = spec.get("feasibility") if isinstance(spec, dict) else None
    if not isinstance(feasibility, dict):
        raise ValueError("Method specification requires a feasibility object")
    checks = feasibility.get("checks")
    signals = feasibility.get("required_signals")
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise ValueError("feasibility.checks must be a list of prerequisite checks")
    if not isinstance(signals, list) or any(not isinstance(s, dict) for s in signals):
        raise ValueError("feasibility.required_signals must be a list")
    if any(not isinstance(c.get("dimension"), str) for c in checks):
        raise ValueError("Every feasibility check requires a dimension")
    counts = Counter(c["dimension"] for c in checks)
    missing = sorted(set(DIMENSIONS) - set(counts))
    unexpected = sorted(set(counts) - set(DIMENSIONS))
    duplicate = sorted(name for name, count in counts.items() if count > 1)
    if missing or unexpected or duplicate:
        raise ValueError("Feasibility needs each of the seven dimensions exactly once: "
                         f"missing={missing}, unexpected={unexpected}, duplicate={duplicate}")
    if not isinstance(evidence, list) or any(
        not isinstance(e, dict) or not isinstance(e.get("id"), str) for e in evidence
    ):
        raise ValueError("Evidence must contain records with string IDs")
    evidence_ids = {e["id"] for e in evidence}
    blocking_checks = []
    unverified_checks = []

    for check in checks:
        dimension = check["dimension"]
        label = f"feasibility.checks.{dimension}"
        status = check.get("status")
        if not isinstance(status, str) or status not in CHECK_STATUSES:
            raise ValueError(f"{label} has an invalid status")
        requirement = _text(check, "requirement", label)
        verification_plan = _text(check, "verification_plan", label)
        failure_action = _text(check, "failure_action", label)
        refs = _references(check, evidence_ids, label, status == "source_supported")
        if status == "not_applicable" and requirement.strip().lower().rstrip(".。") in _EMPTY_REASONS:
            raise ValueError(f"{label}: not_applicable requires a specific reason")
        item = {"kind": "check", "dimension": dimension, "status": status,
                "requirement": requirement, "evidence_ids": refs,
                "verification_plan": verification_plan, "failure_action": failure_action}
        if status == "blocked":
            blocking_checks.append(item)
        elif status == "unverified":
            unverified_checks.append(item)

    for index, signal in enumerate(signals):
        label = f"feasibility.required_signals[{index}]"
        name = _text(signal, "name", label)
        stage = signal.get("needed_at")
        availability = signal.get("availability")
        if not isinstance(stage, str) or stage not in SIGNAL_STAGES:
            raise ValueError(f"{label} has an invalid needed_at stage")
        if not isinstance(availability, str) or availability not in SIGNAL_AVAILABILITIES:
            raise ValueError(f"{label} has an invalid availability")
        refs = _references(signal, evidence_ids, label, availability == "source_supported")
        for field in ("acquisition_plan", "substitute"):
            _text(signal, field, label)
        item = {"kind": "required_signal", "name": name, "needed_at": stage,
                "availability": availability, "evidence_ids": refs,
                "acquisition_plan": signal["acquisition_plan"], "substitute": signal["substitute"]}
        if availability == "unavailable":
            item["reason"] = f"Required signal {name!r} is unavailable at {stage}; a proposed substitute does not resolve this prerequisite."
            blocking_checks.append(item)
        elif availability == "unverified":
            item["reason"] = f"Availability of required signal {name!r} at {stage} has not been verified."
            unverified_checks.append(item)

    status = "blocked" if blocking_checks else "prerequisites_unverified" if unverified_checks else "specified_not_executed"
    warnings = ["Prerequisite assessment only: no code, data access, training, or evaluation was executed or verified.",
                "Source references are checked for identity, not whether they establish the claimed prerequisite under this project's conditions."]
    if blocking_checks:
        warnings.append("At least one required prerequisite is blocked. An optimistic review or an untested substitute cannot clear it.")
    if unverified_checks:
        warnings.append("Unverified prerequisites need the stated checks before implementation feasibility can be established.")
    return {"status": status, "warnings": warnings,
            "blocking_checks": blocking_checks, "unverified_checks": unverified_checks}
