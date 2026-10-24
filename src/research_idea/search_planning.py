"""Normalize a bounded search plan before any paper evidence is available.

A plan contains search intentions, never paper metadata or evidence. Structural
checks cannot establish that a query is useful, that a paper exists, or that an
assumption is true; those decisions require retrieved sources and later reading.
"""
from __future__ import annotations

import unicodedata


MAX_QUERIES = 3
MAX_QUERY_CHARS = 300
MAX_QUERY_WORDS = 40
MAX_INPUT_QUERIES = 200
PURPOSES = {"background", "motivation", "mechanism", "implementation", "evaluation", "counterevidence"}
PLAN_FIELDS = {"research_question", "scope", "queries", "assumptions"}
QUERY_FIELDS = {"query", "purpose", "rationale"}


def _object(value, fields, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing, extra = fields - set(value), set(value) - fields
    if missing or extra:
        raise ValueError(f"{label}: missing={sorted(missing)}, unexpected={sorted(extra, key=str)}")


def _text(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a nonempty string")
    text = " ".join(value.split())
    if not text or any(unicodedata.category(char) == "Cc" for char in text):
        raise ValueError(f"{label} must be a nonempty string without control characters")
    return text


def normalize_search_plan(plan: dict) -> dict:
    """Validate shape, normalize whitespace, and retain at most three queries.

    Query deduplication is case-insensitive and keeps the first query's purpose
    and rationale. All supplied entries are validated before truncation, so an
    invalid item cannot be hidden after the third query. English academic terms
    belong in the prompt: the modest Latin-letter check only catches an entirely
    untranslated query, while allowing accents and non-Latin proper names.
    """
    _object(plan, PLAN_FIELDS, "search_plan")
    research_question = _text(plan["research_question"], "research_question")
    scope = _text(plan["scope"], "scope")
    raw_queries = plan["queries"]
    if not isinstance(raw_queries, list) or not 1 <= len(raw_queries) <= MAX_INPUT_QUERIES:
        raise ValueError("queries must contain 1–200 query objects; at most 3 distinct queries are retained")
    queries, seen = [], set()
    for index, item in enumerate(raw_queries):
        label = f"queries[{index}]"
        _object(item, QUERY_FIELDS, label)
        query = _text(item["query"], label + ".query")
        if len(query) > MAX_QUERY_CHARS or len(query.split()) > MAX_QUERY_WORDS:
            raise ValueError(f"{label}.query must use concise academic keywords: at most {MAX_QUERY_CHARS} characters and {MAX_QUERY_WORDS} words")
        if not any("LATIN" in unicodedata.name(char, "") for char in query):
            raise ValueError(f"{label}.query needs English academic keywords; non-Latin proper names may accompany them")
        purpose = _text(item["purpose"], label + ".purpose")
        if purpose not in PURPOSES:
            raise ValueError(f"{label}.purpose must be one of {', '.join(sorted(PURPOSES))}")
        rationale = _text(item["rationale"], label + ".rationale")
        key = query.casefold()
        if key not in seen:
            seen.add(key)
            if len(queries) < MAX_QUERIES:
                queries.append({"query": query, "purpose": purpose, "rationale": rationale})
    assumptions = plan["assumptions"]
    if not isinstance(assumptions, list):
        raise ValueError("assumptions must be a list of strings")
    assumptions = [_text(value, f"assumptions[{index}]") for index, value in enumerate(assumptions)]
    return {"research_question": research_question, "scope": scope,
            "queries": queries, "assumptions": assumptions}
