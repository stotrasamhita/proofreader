"""Extracting proofreadable text from the corpus, and normalizing words.

A source file becomes a list of Units. A unit is either one verse (the
arguments of a `\\...shloka` macro, one line per argument) or a run of prose
(everything outside verse macros: `\\uvacha`, gadya, titles). Each line keeps
its 1-based source line number so findings point back into the file.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# Verse macros -> (number of brace args, number of those that are verse text).
# The anno* variants carry a trailing citation argument that is not verse.
VERSE_MACROS = {
    'onelineshloka': (1, 1),
    'twolineshloka': (2, 2),
    'threelineshloka': (3, 3),
    'THREElineshloka': (3, 3),
    'fourlineshloka': (4, 4),
    'fourlineindentedshloka': (4, 4),
    'sixlineindentedshloka': (6, 6),
    'onelineindentedshloka': (2, 2),
    'annotwolineshloka': (3, 2),
    'annofourlineindentedshloka': (5, 4),
}

# Characters that make up a Devanagari word: letters, signs, vowel marks,
# Vedic svaras and ZWJ/ZWNJ. Dandas (U+0964/5) and digits (U+0966-F) split.
_WORD_CHARS = '\u0900-\u0963\u0970-\u097F\u1CD0-\u1CFF\uA8E0-\uA8FF\u200C\u200D'
WORD_RE = re.compile(f'[{_WORD_CHARS}]+')

_SVARA_RE = re.compile('[\u0951-\u0954\u1CD0-\u1CFF\uA8E0-\uA8F1]')
_ZW_RE = re.compile('[\u200C\u200D]')

# A nasal consonant + virama before a stop of its own class is spelled
# interchangeably with anusvara (शङ्कर / शंकर). Keys collapse both to anusvara
# so that spelling convention never looks like a novel word.
_PARASAVARNA_RE = re.compile(
    '(?:ङ्(?=[कखगघङ])|ञ्(?=[चछजझञ])|ण्(?=[टठडढण])|न्(?=[तथदधन])|म्(?=[पफबभम]))')


def clean(word):
    """Surface form used for display and orthography rules."""
    word = unicodedata.normalize('NFC', word)
    word = _SVARA_RE.sub('', word)
    return _ZW_RE.sub('', word)


def key(word):
    """Canonical form used for all lexicon and n-gram lookups."""
    word = clean(word).replace('ऽ', '')
    if word.endswith('म्'):            # वधम् / वधं: same word, house style differs
        word = word[:-2] + 'ं'
    return _PARASAVARNA_RE.sub('ं', word)


def char_ngrams(k, n):
    """Character n-grams of a key, with ^ and $ marking the word boundaries."""
    s = f'^{k}$'
    return [s[i:i + n] for i in range(len(s) - n + 1)]


@dataclass
class Line:
    lineno: int
    text: str


@dataclass
class Unit:
    kind: str                  # 'verse' or 'prose'
    lines: list = field(default_factory=list)
    macro: str = ''
    starred: bool = False

    def words(self):
        """Yield (word, Line). A pada ending in '-' continues into the next
        line, so the split halves are rejoined into one word."""
        out, join_next = [], False
        for line in self.lines:
            for j, t in enumerate(WORD_RE.findall(line.text)):
                if j == 0 and join_next and out:
                    out[-1] = (out[-1][0] + t, out[-1][1])
                else:
                    out.append((t, line))
            join_next = self.kind == 'verse' and line.text.rstrip().endswith('-')
        return out


def _strip_comments(text):
    """Blank out TeX comments, keeping line structure intact."""
    return re.sub(r'(?<!\\)%[^\n]*', '', text)


def _read_group(text, i):
    """Read a {...} group starting at or after i (skipping whitespace).
    Returns (content, start_offset_of_content, end_index) or None."""
    n = len(text)
    while i < n and text[i] in ' \t\r\n':
        i += 1
    if i >= n or text[i] != '{':
        return None
    depth, j = 0, i
    while j < n:
        c = text[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[i + 1:j], i + 1, j + 1
        j += 1
    return None


_MACRO_RE = re.compile(r'\\([A-Za-z]+)(\*?)')
# Macros whose arguments are layout or references, never text.
_DROP_ARG_MACROS = ('hspace', 'vspace', 'label', 'ref', 'input', 'include',
                    'addtocounter', 'setcounter', 'setlength', 'addtolength',
                    'index', 'idxref', 'phantomsection', 'addcontentsline',
                    'newcommand', 'renewcommand', 'usepackage', 'begin', 'end')
_DROP_ARG_RE = re.compile(r'\\(?:%s)\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*' % '|'.join(_DROP_ARG_MACROS))


def clean_tex_fragment(s):
    """Reduce a TeX fragment to its visible text."""
    s = _DROP_ARG_RE.sub(' ', s)
    s = re.sub(r'\\[A-Za-z]+\*?(?:\[[^\]]*\])?', ' ', s)
    s = re.sub(r'\\.', ' ', s)
    s = s.replace('{', '').replace('}', '')
    return re.sub(r'[ \t]+', ' ', s).strip()


def parse_tex(text):
    """Split a .tex source into verse and prose Units."""
    text = _strip_comments(text)
    line_starts = [0] + [m.end() for m in re.finditer('\n', text)]

    def lineno(off):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    units, prose_spans, pos = [], [], 0
    for m in _MACRO_RE.finditer(text):
        if m.start() < pos:
            continue
        name = m.group(1)
        if name not in VERSE_MACROS:
            continue
        nargs, ntext = VERSE_MACROS[name]
        args, i = [], m.end()
        for _ in range(nargs):
            g = _read_group(text, i)
            if g is None:
                break
            args.append(g)
            i = g[2]
        if len(args) != nargs:
            continue
        prose_spans.append((pos, m.start()))
        lines = [Line(lineno(start), clean_tex_fragment(content))
                 for content, start, _ in args[:ntext]]
        units.append((m.start(), Unit('verse', lines, name, m.group(2) == '*')))
        pos = i
    prose_spans.append((pos, len(text)))

    for a, b in prose_spans:
        chunk = text[a:b]
        lines = []
        for k, raw in enumerate(chunk.split('\n')):
            t = clean_tex_fragment(raw)
            if WORD_RE.search(t):
                lines.append(Line(lineno(a) + k, t))
        if lines:
            units.append((a, Unit('prose', lines)))
    units.sort(key=lambda u: u[0])
    return [u for _, u in units]


def parse_plain(text):
    """Plain .txt/.md sources: every non-empty line is prose."""
    lines = [Line(i + 1, l.strip()) for i, l in enumerate(text.split('\n'))
             if WORD_RE.search(l)]
    return [Unit('prose', lines)] if lines else []


def parse_file(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    return parse_tex(text) if str(path).endswith('.tex') else parse_plain(text)
