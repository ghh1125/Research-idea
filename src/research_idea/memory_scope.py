"""Conservative scope defaults for reply formatting, grounded in the user's words.

The model handles research semantics. This local rule prevents presentation
requests from silently becoming permanent, including records from older runs.
"""
from __future__ import annotations

import re


def _presentation_kinds(text):
    kinds = set()
    if re.search(r'(?:\d+|[一二三四五六七八九十两几]+)\s*(?:字|词|句话?|段|words?\b|characters?\b|sentences?\b|paragraphs?\b)', text, re.I):
        kinds.add('length')
    if re.search(r'简短|简洁|详细|长一点|短一点|brief|concise|in detail', text, re.I):
        kinds.add('detail')
    if re.search(r'表格|分点|列表|要点|bullet|table|markdown', text, re.I):
        kinds.add('format')
    if re.search(r'通俗|易懂|口语|人话|plain (?:language|English)|simple (?:language|terms)', text, re.I):
        kinds.add('language')
    return kinds


def _source_clauses(source):
    """Separate mixed instructions, retaining a bare duration prefix before a comma."""
    result = []
    for sentence in re.split(r'[。！？；;\n]|(?<=[.!?])\s+', source):
        prefix = ''
        for part in re.split(r'[,，]', sentence):
            part = part.strip()
            if _presentation_kinds(part):
                result.append(prefix + part)
                prefix = ''
            elif re.fullmatch(r'(?:以后|今后|从现在开始|本轮|本次|这次|当前讨论期间)'
                              r'(?:都|所有|每次|的|时候|回答|回复|答复|表达|输出|报告|请|\s)*'
                              r'|from now on|for this (?:reply|answer|turn)|during this discussion', part, re.I):
                prefix = part + ' '
            else:
                prefix = ''
    return result


def resolve_scope(content, requested, source):
    """Default local output requests to one reply; never infer duration elsewhere.

    Only presentation entries are normalized. A resource limit, research goal,
    or 'no experiment plan' is not a reply-format preference. Explicit duration
    is taken from matching source sentences, not from model-added wording.
    """
    kinds = _presentation_kinds(content)
    # Avoid treating a research question containing e.g. 'memory length' as a
    # formatting request. A standalone length/format constraint is also allowed.
    if not kinds or (re.search(r'研究|模型|数据|检索|上下文|训练|实验|research|model|training|dataset', content, re.I)
                     and not re.search(r'回复|回答|答复|表达|写作|报告|输出|reply|answer|response|writing|report', content, re.I)):
        return requested
    matching = [s for s in _source_clauses(source) if kinds & _presentation_kinds(s)]
    if not matching:
        return requested
    # A message may contain a standing preference and a different local limit.
    # Keep the scope marker attached to the matching number when available.
    numbers = set(re.findall(r'\d+', content))
    exact = [s for s in matching if numbers & set(re.findall(r'\d+', s))]
    relevant = exact or matching
    for sentence in relevant:
        if re.search(r'讨论期间|这一阶段|当前阶段|/continue|until (?:we|I)|during (?:this|the) discussion', sentence, re.I):
            return 'discussion'
    for sentence in relevant:
        if re.search(r'本轮|本次|这次|此轮|这条|这一条|这段|当前(?:回复|回答)|this (?:reply|answer|response|turn)|just (?:this|now)', sentence, re.I):
            return 'turn'
    for sentence in relevant:
        if re.search(r'以后|今后|始终|一直|长期|默认|每次|所有(?:回复|回答)|整个研究|后续|最终|正式|报告|全文|always|from now on|every (?:reply|answer|response)|for (?:the whole|all)|final|report', sentence, re.I):
            return 'research'
    return 'turn'
