"""Find the same verse in two places with different readings.

Each verse line is reduced to its key text with spaces removed, so word
division, anusvara/class-nasal and avagraha differences vanish and only
substantive differences remain. Lines are bucketed by a few fixed anchors
(start, middle, end of the key text); lines sharing an anchor are compared,
and a verse pair is reported when at least two of its lines match closely
and at least one differs. Requiring two matched lines keeps stock half-lines
(एवमुक्तस्तु राजेन्द्र …) from pairing unrelated verses.
"""

import difflib
import glob
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .text import WORD_RE, key, parse_file

ANCHOR = 9            # characters per anchor
MIN_LEN = 14          # shortest line (in key characters) considered
MAX_BUCKET = 60       # anchors shared by more lines than this are formulaic
MIN_RATIO = 0.80      # lines this similar are the same line


_MATRA = {'अ': '', 'आ': 'ा', 'इ': 'ि', 'ई': 'ी', 'उ': 'ु', 'ऊ': 'ू', 'ऋ': 'ृ', 'ॠ': 'ॄ',
          'ए': 'े', 'ऐ': 'ै', 'ओ': 'ो', 'औ': 'ौ'}
_FUSE_RE = re.compile('्([अआइईउऊऋॠएऐओऔ])')
# pāda-final sandhi varies (पुराणः / पुराण, दुष्टाः / दुष्टास्, -भिः / -भिर्)
_LINE_END_RE = re.compile('(?:ः|[कगटडतदनमरसशष]्)$')

# Derived copies, not independent texts
EXCLUDE = ('/verse-checker/', '/proofreader/', 'vedamantra-book-grantha', '-orig', '.orig.',
           '/SARIT-corpus/', '/gita/words/', '/stotras-pdf/', '-kindle-pdf/', '-kindle-scribe-pdf/')


def corpus_files(root):
    return sorted(p for p in glob.glob(os.path.join(root, '**', '*.tex'), recursive=True)
                  if not any(x in p for x in EXCLUDE))


def signature(text):
    """Key text with spaces, word-junction and pāda-end sandhi normalized."""
    sig = ''.join(key(w) for w in WORD_RE.findall(text))
    sig = _FUSE_RE.sub(lambda m: _MATRA[m.group(1)], sig)
    return _LINE_END_RE.sub('', sig)


@dataclass
class VLine:
    path: str
    unit: int
    lineno: int
    text: str
    sig: str


@dataclass
class VersePair:
    a_path: str
    b_path: str
    a_unit: int
    b_unit: int
    lines: list = field(default_factory=list)   # (VLine a, VLine b, ratio)

    @property
    def differing(self):
        return [t for t in self.lines if t[2] < 1.0]


def verse_lines(path, rel_path):
    out = []
    for n, u in enumerate(parse_file(path)):
        if u.kind != 'verse':
            continue
        for l in u.lines:
            sig = signature(l.text)
            if len(sig) >= MIN_LEN:
                out.append(VLine(rel_path, n, l.lineno, l.text.rstrip('-').strip(), sig))
    return out


def _anchors(sig):
    mid = len(sig) // 2 - ANCHOR // 2
    return {('s', sig[:ANCHOR]), ('e', sig[-ANCHOR:]), ('m', sig[mid:mid + ANCHOR])}


def find(files, rel, within_file=False, log=None):
    """files: absolute paths. Returns VersePairs, most differing first."""
    lines = []
    for i, p in enumerate(files):
        lines += verse_lines(p, rel(p))
        if log and i % 200 == 199:
            log(f'  read {i + 1}/{len(files)} files')
    buckets = defaultdict(list)
    for i, vl in enumerate(lines):
        for a in _anchors(vl.sig):
            buckets[a].append(i)

    best = {}             # (line a, line b) -> ratio
    for members in buckets.values():
        if len(members) < 2 or len(members) > MAX_BUCKET:
            continue
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                i, j = members[x], members[y]
                a, b = lines[i], lines[j]
                if a.path == b.path and (not within_file or a.unit == b.unit):
                    continue
                pair = (i, j) if (a.path, a.lineno) < (b.path, b.lineno) else (j, i)
                if pair in best:
                    continue
                if abs(len(a.sig) - len(b.sig)) > 0.25 * max(len(a.sig), len(b.sig)):
                    best[pair] = 0
                    continue
                r = 1.0 if a.sig == b.sig else difflib.SequenceMatcher(None, a.sig, b.sig, autojunk=False).ratio()
                best[pair] = r

    verses = {}
    for (i, j), r in best.items():
        if r < MIN_RATIO:
            continue
        a, b = lines[i], lines[j]
        k = (a.path, a.unit, b.path, b.unit)
        vp = verses.get(k) or verses.setdefault(k, VersePair(a.path, b.path, a.unit, b.unit))
        vp.lines.append((a, b, r))

    out = []
    for vp in verses.values():
        # one best partner per line on each side
        vp.lines.sort(key=lambda t: -t[2])
        used_a, used_b, keep = set(), set(), []
        for a, b, r in vp.lines:
            if a.lineno in used_a or b.lineno in used_b:
                continue
            used_a.add(a.lineno)
            used_b.add(b.lineno)
            keep.append((a, b, r))
        vp.lines = sorted(keep, key=lambda t: t[0].lineno)
        if len(vp.lines) >= 2 and vp.differing:
            out.append(vp)
    out.sort(key=lambda vp: (vp.a_path, vp.b_path, vp.lines[0][0].lineno))
    return out


def word_diff(a, b):
    """Mark differing words: (a with «», b with «»)."""
    wa, wb = a.split(), b.split()
    ka, kb = [key(w) for w in wa], [key(w) for w in wb]
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    oa, ob = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            oa += wa[i1:i2]
            ob += wb[j1:j2]
        else:
            if i2 > i1:
                oa.append('«' + ' '.join(wa[i1:i2]) + '»')
            if j2 > j1:
                ob.append('«' + ' '.join(wb[j1:j2]) + '»')
    return ' '.join(oa), ' '.join(ob)
