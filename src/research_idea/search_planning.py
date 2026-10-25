"""Normalize a bounded search plan before any paper evidence is available.

A plan contains search intentions, never paper metadata or evidence. Structural
checks cannot establish that a query is useful, that a paper exists, or that an
assumption is true; those decisions require retrieved sources and later reading.
"""
from __future__ import annotations

import unicodedata


MAX_QUERIES = 3
MAX_DISCOVERY_QUERIES = 6
MAX_RESEARCH_ROUTES = 4
MAX_QUERY_CHARS = 300
MAX_QUERY_WORDS = 40
MAX_INPUT_QUERIES = 200
PURPOSES = {"background", "motivation", "mechanism", "implementation", "evaluation", "counterevidence"}
PLAN_FIELDS = {"research_question", "scope", "queries", "assumptions"}
QUERY_FIELDS = {"query", "purpose", "rationale"}
AXIS_FIELDS = {'id', 'question', 'why_needed', 'required_function', 'search_directions'}
ROUTE_FIELDS = {'id', 'question', 'why_relevant'}


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


def normalize_design_axes(axes):
    """Keep two functional questions connected to the idea, without scoring them."""
    if not isinstance(axes, list) or len(axes) != 2:
        raise ValueError('Explain two complementary technical angles before choosing techniques')
    result = []
    for axis in axes:
        _object(axis, AXIS_FIELDS, 'design_axis')
        item = {key: _text(axis[key], 'design_axis.' + key)
                for key in AXIS_FIELDS - {'search_directions'}}
        directions = axis['search_directions']
        if not isinstance(directions, list) or not directions:
            raise ValueError('Each technical angle needs plausible method search directions')
        item['search_directions'] = [_text(d, 'search_direction') for d in directions]
        result.append(item)
    if len({axis['id'] for axis in result}) != 2:
        raise ValueError('Technical angle IDs must be distinct')
    return result


def check_axis_links(items, axes, *, require_all=False):
    allowed = {axis['id'] for axis in axes}
    linked = set()
    for item in items:
        ids = item.get('axis_ids')
        if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids)
                or len(set(ids)) != len(ids) or not set(ids) <= allowed):
            raise ValueError('Link each query or technical choice to supplied technical angle IDs')
        linked.update(ids)
    if require_all and linked != allowed:
        raise ValueError('Address both technical angles; do not lose one during selection')


def normalize_research_routes(routes):
    """Describe a few distinct lines of inquiry, without judging their merit."""
    if not isinstance(routes, list) or len(routes) > MAX_RESEARCH_ROUTES:
        raise ValueError('research_routes must contain at most four research routes')
    result = []
    for route in routes:
        _object(route, ROUTE_FIELDS, 'research_route')
        result.append({key: _text(route[key], 'research_route.' + key) for key in ROUTE_FIELDS})
    if len({route['id'] for route in result}) != len(result):
        raise ValueError('Research route IDs must be distinct')
    return result


def normalize_search_plan(plan: dict, *, technical=False) -> dict:
    """Normalize up to six discovery queries or three technical/legacy queries.

    Query deduplication is case-insensitive and keeps the first query's purpose
    and rationale. All supplied entries are validated before truncation, so an
    invalid item cannot be hidden after the retained queries. English academic terms
    belong in the prompt: the modest Latin-letter check only catches an entirely
    untranslated query, while allowing accents and non-Latin proper names.
    """
    # Older saved search plans can still be normalized and displayed.
    optional = {'design_axes', 'research_routes'} & set(plan) if isinstance(plan, dict) else set()
    _object(plan, PLAN_FIELDS | optional, "search_plan")
    axes = normalize_design_axes(plan.get('design_axes')) if technical else []
    if not technical and plan.get('design_axes') not in (None, []):
        raise ValueError('Strategy discovery precedes technical angles; use design_axes=[]')
    routes = normalize_research_routes(plan.get('research_routes', []))
    if technical and routes:
        raise ValueError('Technical design uses design_axes, with research_routes=[]')
    route_ids = {route['id'] for route in routes}
    max_queries = MAX_DISCOVERY_QUERIES if routes else MAX_QUERIES
    research_question = _text(plan["research_question"], "research_question")
    scope = _text(plan["scope"], "scope")
    raw_queries = plan["queries"]
    if not isinstance(raw_queries, list) or not 1 <= len(raw_queries) <= MAX_INPUT_QUERIES:
        raise ValueError(f"queries must contain 1–200 query objects; at most {max_queries} distinct queries are retained")
    queries, seen = [], set()
    for index, item in enumerate(raw_queries):
        label = f"queries[{index}]"
        optional = {'axis_ids', 'route_ids'} & set(item) if isinstance(item, dict) else set()
        _object(item, QUERY_FIELDS | optional, label)
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
        if technical:
            check_axis_links([item], axes)
        elif item.get('axis_ids') not in (None, []):
            raise ValueError('Strategy queries do not refer to technical angles')
        links = item.get('route_ids', [])
        if (not isinstance(links, list) or any(not isinstance(route, str) for route in links)
                or len(links) != len(set(links)) or not set(links) <= route_ids
                or (routes and not links)):
            raise ValueError(f'{label}.route_ids must link the query to its research routes')
        if key not in seen:
            seen.add(key)
            normalized = {"query": query, "purpose": purpose, "rationale": rationale}
            if 'axis_ids' in item:
                normalized['axis_ids'] = list(item['axis_ids'])
            if 'route_ids' in item:
                normalized['route_ids'] = list(links)
            queries.append(normalized)
        elif technical or routes:
            retained = next((q for q in queries if q['query'].casefold() == key), None)
            if retained is not None:
                field = 'axis_ids' if technical else 'route_ids'
                retained[field] = list(dict.fromkeys(retained[field] + item[field]))
    if routes:
        # Reserve one query for each planned route before filling spare slots.
        # Repeated queries can cover several routes without another request.
        retained_indices, covered = set(), set()
        for index, query in enumerate(queries):
            if set(query['route_ids']) - covered:
                retained_indices.add(index)
                covered.update(query['route_ids'])
        if covered != route_ids:
            raise ValueError('Give each research route a search query')
        for index in range(len(queries)):
            if len(retained_indices) >= max_queries:
                break
            retained_indices.add(index)
        queries = [query for index, query in enumerate(queries) if index in retained_indices]
    else:
        queries = queries[:max_queries]
    assumptions = plan["assumptions"]
    if not isinstance(assumptions, list):
        raise ValueError("assumptions must be a list of strings")
    assumptions = [_text(value, f"assumptions[{index}]") for index, value in enumerate(assumptions)]
    result = {"research_question": research_question, "scope": scope,
              "queries": queries, "assumptions": assumptions}
    if technical:
        check_axis_links(queries, axes, require_all=True)
    if 'design_axes' in plan:
        result['design_axes'] = axes
    if 'research_routes' in plan:
        result['research_routes'] = routes
    return result
