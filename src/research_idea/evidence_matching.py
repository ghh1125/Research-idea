"""Typography-tolerant source alignment with offsets into the untouched source."""
import difflib
import re


def current_quote_gaps(store):
    from .store import digest
    sources = {p['id']: digest(p.get('text') or p.get('abstract', '')) for p in store.rows('papers')}
    return {key: gap for key, gap in store.get('quote_gaps', {}).items()
            if gap.get('source_hash') == sources.get(gap['paper_id'])}


class QuoteMatchError(ValueError):
    def __init__(self, message, quote):
        super().__init__(message)
        self.quote = quote


_TRANSLATE = {'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl',
              '‘': "'", '’': "'", '“': '"', '”': '"', '‑': '-'}


def normalized(text, dehyphenate=False):
    out, offsets = [], []
    skip = set()
    pattern = r'(?<=[^\W\d_])[-\u00ad][ \t]*\r?\n[ \t]*(?=[^\W\d_])'
    for match in re.finditer(pattern, text):
        start = match.start() if dehyphenate else match.start() + 1
        skip.update(range(start, match.end()))
    for i, character in enumerate(text):
        if i in skip or character == '\u00ad':
            continue
        chars = _TRANSLATE.get(character, character)
        for c in chars:
            if c.isspace():
                if out and out[-1] == ' ':
                    offsets[-1] = (offsets[-1][0], i + 1)
                    continue
                c = ' '
            out.append(c)
            offsets.append((i, i + 1))
    return ''.join(out), offsets


def locate_quote(text, quote):
    if len(quote.strip()) < 15:
        raise QuoteMatchError('Evidence quote is too short to ground a claim', quote)
    words = re.split(r'\s+', quote.strip())
    match = re.search(r'\s+'.join(re.escape(w) for w in words), text)
    if match:
        return match.start(), match.end()
    for dehyphenate in (False, True):
        source, offsets = normalized(text, dehyphenate)
        target, _ = normalized(quote.strip(), dehyphenate)
        start = source.find(target)
        if start >= 0 and target:
            return offsets[start][0], offsets[start + len(target) - 1][1]
    raise QuoteMatchError('Evidence quote cannot be located in supplied source after typography normalization', quote)


def repair_hint(text, quote):
    # Approximate location is only repair context, never accepted evidence.
    anchor = difflib.SequenceMatcher(None, quote[:2000], text, autojunk=False).find_longest_match()
    start = max(0, anchor.b - 160)
    return {'rejected_quote': quote, 'nearby_source': text[start:start + min(1800, len(quote) + 500)],
            'instruction': 'Copy a short contiguous passage from the supplied source, preserving words, numbers and negation. '
                           'The nearby passage is only a location hint, not evidence for the statement. '
                           'Narrow the statement to what the passage actually supports, or omit this observation.'}
