"""Chandas checking via StotraSamhita/verse-checker.

A verse whose lines exactly match a known metre passes. Anything else is
flagged with the per-line laghu/guru pattern so the offending pada is easy
to spot. Results are cached by verse text, since the corpus rarely changes.
"""

import contextlib
import gzip
import io
import logging
import os
import pickle
import sys

from .index import root_dir, tool_dir

VERSE_CHECKER = os.path.join(root_dir(), 'verse-checker')
_CACHE_PATH = os.path.join(tool_dir(), 'index', 'meter-cache.pkl.gz')


class MeterChecker:
    def __init__(self):
        if not os.path.isdir(VERSE_CHECKER):
            raise SystemExit(f'verse-checker not found at {VERSE_CHECKER}')
        sys.path.insert(0, VERSE_CHECKER)
        cwd = os.getcwd()
        os.chdir(VERSE_CHECKER)          # it loads data/*.json relative to cwd
        logging.disable(logging.CRITICAL)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                from data import metrical_data
                from identify import identifier
                from read import read
                import scan
                metrical_data.InitializeData()
                self._identifier = identifier.Identifier(metrical_data)
        finally:
            os.chdir(cwd)
        self._read, self._scan = read, scan
        self._cache = {}
        if os.path.exists(_CACHE_PATH):
            with gzip.open(_CACHE_PATH, 'rb') as f:
                self._cache = pickle.load(f)
        self._dirty = False

    def save_cache(self):
        if self._dirty:
            os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
            with gzip.open(_CACHE_PATH, 'wb') as f:
                pickle.dump(self._cache, f)

    def check(self, lines):
        """lines: list of pada-line strings (Devanagari).
        Returns dict(ok, metre, patterns) where metre is the best guess."""
        text = '\n'.join(l.rstrip('-').strip() for l in lines)
        hit = self._cache.get(text)
        if hit is not None:
            return hit
        with contextlib.redirect_stdout(io.StringIO()):
            cleaned, _ = self._read.read_text(text)
            patterns = self._scan.ScanVerse(cleaned)
            self._identifier._Reset()
            results = self._identifier.IdentifyFromPatternLines(patterns) if patterns else {}
        guess = None
        for kind in ('exact', 'partial', 'accidental'):
            if results and results.get(kind):
                guess = sorted(results[kind])[0]
                break
        out = {'ok': bool(results and results.get('exact')), 'metre': guess,
               'patterns': list(patterns or [])}
        self._cache[text] = out
        self._dirty = True
        return out


# Odd-pāda syllables 5-7: pathyā (LGG) and the four vipulās (na, bha, ma, ra).
_ODD_OK = {'LGG', 'LLL', 'GLL', 'GGG', 'GLG'}


def anushtup_line_ok(p):
    """One 16-syllable anuṣṭup half-verse (two pādas)."""
    return (len(p) == 16 and p[12:15] == 'LGL' and p[4:7] in _ODD_OK
            and p[9:11] != 'LL' and p[1:3] != 'LL')


def anushtup_like(patterns):
    """Lines are 16-syllable half-verses, give or take the one being wrong.
    Not when the lines share one fixed pattern that breaks the śloka rules:
    that is a 16-syllable vṛtta such as pañcacāmara (LG ×8)."""
    if not (bool(patterns) and all(15 <= len(p) <= 17 for p in patterns)
            and sum(len(p) == 16 for p in patterns) * 2 >= len(patterns)):
        return False
    from collections import Counter
    full = [p for p in patterns if len(p) == 16]
    if len(full) >= 3:            # a 16-syllable vṛtta has four lines; a śloka two (or three)
        ref = ''.join(Counter(p[k] for p in full).most_common(1)[0][0] for k in range(16))
        if (not anushtup_line_ok(ref)
                and all(sum(a != b for a, b in zip(p[:15], ref[:15])) <= 2 for p in full)):
            return False
    return True


def _matras(p):
    return sum(2 if c == 'G' else 1 for c in p[:-1])


def severity(hint):
    """Score for a metre finding: a wrong syllable count is the strongest
    sign of a dropped or extra akṣara."""
    if 'syllables (' in hint or 'unequal lengths' in hint or 'mātrās (' in hint:
        return 5.0
    if 'pāda syllables' in hint:
        return 4.0
    return 3.0


def structural_check(patterns):
    """Metre-agnostic check for verses verse-checker could not match exactly.
    Returns (ok, hint). Anuṣṭup verses are judged by the śloka rules. Other
    verses must be internally consistent: every line the same length and the
    same laghu/guru pattern, except at pāda-final syllables (anceps) and at
    the first syllable of 11/12-syllable pādas (upajāti mixes). Lines with
    equal mātrā counts also pass, for mātrā metres."""
    from collections import Counter
    pats = [p for p in patterns if p]
    if not pats:
        return False, 'no syllables found'
    if anushtup_like(pats):
        hint = anushtup_hint(pats)
        return not hint, hint
    if len(pats) < 2:
        return True, ''               # a lone non-śloka line: nothing to compare
    L = Counter(len(p) for p in pats).most_common(1)[0][0]
    odd = [(i, len(p)) for i, p in enumerate(pats) if len(p) != L]
    if odd:
        # Mātrā metres (e.g. Bhaja Govindam's 16 mātrās) vary the syllable
        # count but not the mātrā count; the line-final syllable is anceps.
        m = [_matras(p) + 2 for p in pats]
        M, n = Counter(m).most_common(1)[0]
        if n == len(m):
            return True, ''
        if n * 2 > len(m) and n >= 2 and all(abs(x - M) <= 2 for x in m):
            return False, '; '.join(f'line {i + 1} has {x} mātrās (the others have {M})'
                                    for i, x in enumerate(m) if x != M)
    if odd and len(odd) * 2 < len(pats):
        return False, '; '.join(f'line {i + 1} has {n} syllables (the others have {L})'
                                for i, n in odd)
    if odd:
        return False, 'lines have unequal lengths: ' + ' '.join(str(len(p)) for p in pats)
    free = {L - 1}
    if L % 2 == 0:
        free.add(L // 2 - 1)          # two pādas per line: mid-line pāda end
    pada = L // 2 if L in (22, 24) else L
    if pada in (11, 12):
        # upajāti mixes vary the 1st syllable; epic triṣṭubh/jagatī the 3rd too
        free |= {o + d for o in range(0, L, pada) for d in (0, 2)}
    ref = ''.join(Counter(p[j] for p in pats).most_common(1)[0][0] for j in range(L))
    devs = [(i, [j for j in range(L) if j not in free and p[j] != ref[j]])
            for i, p in enumerate(pats)]
    devs = [(i, js) for i, js in devs if js]
    if not devs:
        return True, ''
    if len({_matras(p) for p in pats}) == 1:
        return True, ''
    return False, '; '.join(
        f'line {i + 1} differs from the other lines at syllable '
        + ', '.join(str(j + 1) for j in js[:4]) for i, js in devs)


def anushtup_hint(patterns):
    """For a 2-line anuṣṭup, point at the line that breaks the rules."""
    hints = []
    for i, p in enumerate(patterns):
        if len(p) != 16:
            hints.append(f'line {i + 1} has {len(p)} syllables (expected 16)')
            continue
        if p[12:15] != 'LGL':
            hints.append(f'line {i + 1}: even pāda syllables 5–7 are {p[12:15]} (expected LGL)')
        if p[4:7] not in _ODD_OK:
            hints.append(f'line {i + 1}: odd pāda syllables 5–7 are {p[4:7]} '
                         '(expected pathyā LGG or a vipulā)')
        for half, off in (('odd', 0), ('even', 8)):
            if p[off + 1:off + 3] == 'LL':
                hints.append(f'line {i + 1}: {half} pāda syllables 2–3 are both laghu')
    return '; '.join(hints)


# --- pointing at the syllable a hint is about -------------------------------
import re as _re

_C = '[क-हक़-य़]़?'
_AKSHARA = _re.compile(
    f'(?:{_C}्‍?‌?)*(?:{_C}[ा-ौॢॣ]?|[अ-औॠ-ॣ])'
    f'[ँ-ः]?(?:{_C}्(?![क-हक़-य़]))*')


def syllables(text):
    """The syllables of a pāda as written, one per vowel (as verse-checker
    counts them): a trailing half-consonant joins the syllable before it."""
    return _AKSHARA.findall(text.replace('ऽ', ''))


def _majority(pats, i):
    same = [p for j, p in enumerate(pats) if j != i and len(p) == len(pats[i])]
    if not same:
        return None
    from collections import Counter
    return ''.join(Counter(p[k] for p in same).most_common(1)[0][0] for k in range(len(pats[i])))


def _ref(pats, i):
    """Majority pattern of the other lines at their most common length."""
    from collections import Counter
    others = [p for j, p in enumerate(pats) if j != i and p]
    if not others:
        return None
    L = Counter(len(p) for p in others).most_common(1)[0][0]
    same = [p for p in others if len(p) == L]
    return ''.join(Counter(p[k] for p in same).most_common(1)[0][0] for k in range(L))


def _free(L):
    """Positions where lines may differ: line-final, a mid-line pāda end, and
    the 1st/3rd syllable of 11/12-syllable pādas (upajāti, epic triṣṭubh)."""
    free = {L - 1}
    if L % 2 == 0:
        free.add(L // 2 - 1)
    pada = L // 2 if L in (22, 24) else L
    if pada in (11, 12):
        free |= {o + d for o in range(0, L, pada) for d in (0, 2)}
    return free


def _misses(a, b):
    return sum(x != y for x, y in zip(a[:-1], b[:-1]))      # last syllable is anceps


def _length_slip(p, ok):
    """Syllables near where one was added or dropped: for an extra syllable,
    those whose removal makes the line fit; for a missing one, the two either
    side of the gap. `ok(q)` scores a repaired line (lower is better)."""
    if not p:
        return set()
    if len(p) > 1:
        tries = []
        for k in range(len(p)):
            tries.append((ok(p[:k] + p[k + 1:]), {k}, 'extra'))
        for k in range(len(p) + 1):
            for w in 'LG':
                tries.append((ok(p[:k] + w + p[k:]), {k - 1, k} - {-1, len(p)}, 'gap'))
        tries = [t for t in tries if t[0] is not None]
        if not tries:
            return set()
        best = min(t[0] for t in tries)
        hits = [t for t in tries if t[0] == best]
        out = set().union(*(t[1] for t in hits))
        # a run of like syllables gives several equal places: keep a short stretch
        return out if max(out) - min(out) < 8 and len(out) == max(out) - min(out) + 1 or len(out) <= 3 else set()
    return set()


def offending(patterns, hint):
    """{line index: set of syllable indices} that a hint from anushtup_hint or
    structural_check is about."""
    out = {}
    for part in hint.split('; '):
        m = _re.match(r'(?:anuṣṭup: )?line (\d+)', part)
        if not m:
            continue
        i = int(m.group(1)) - 1
        if i >= len(patterns):
            continue
        p, s = patterns[i], out.setdefault(i, set())
        if m := _re.search(r'even pāda syllables 5–7 are (\w{3})', part):
            s |= {12 + k for k in range(3) if m.group(1)[k] != 'LGL'[k]}
        elif 'odd pāda syllables 5–7' in part:
            s |= {4, 5, 6}
        elif m := _re.search(r'(odd|even) pāda syllables 2–3', part):
            o = 0 if m.group(1) == 'odd' else 8
            s |= {o + 1, o + 2}
        elif m := _re.search(r'at syllable ([\d, ]+)', part):
            s |= {int(x) - 1 for x in m.group(1).split(',') if x.strip()}
        elif 'syllables (expected 16)' in part:
            if len(p) in (15, 17):
                s |= _length_slip(p, lambda q: 0 if anushtup_line_ok(q) else None)
        elif 'mātrās (' in part or 'syllables (the others' in part:
            ref = _ref(patterns, i)
            if ref and len(ref) == len(p):
                s |= {k for k in range(len(p)) if k not in _free(len(p)) and p[k] != ref[k]}
                if not s:                 # only allowed variation here: the slip is a line of another length
                    for j, q in enumerate(patterns):
                        rj = _ref(patterns, j)
                        if rj and abs(len(rj) - len(q)) == 1:
                            out.setdefault(j, set()).update(
                                _length_slip(q, lambda x, rj=rj: _misses(x, rj) if len(x) == len(rj) else None))
            elif ref and abs(len(ref) - len(p)) == 1:
                s |= _length_slip(p, lambda q: _misses(q, ref) if len(q) == len(ref) else None)
    return {i: s for i, s in out.items() if s}


def mark(lines, patterns, hint, left='[', right=']', soft=None, sleft='(', sright=')'):
    """The pādas with the syllables the hint is about bracketed. A line whose
    syllable count does not match its pattern is left as it is. Syllables in
    `soft` ({line: {syllable}}, e.g. from by_position) get sleft/sright."""
    off = offending(patterns, hint)
    soft = soft or {}
    out = []
    for i, l in enumerate(lines):
        sy = syllables(l)
        if i not in off or i >= len(patterns) or len(sy) != len(patterns[i]):
            out.append(l)
            continue
        res, pos, n = '', 0, 0
        for m in _AKSHARA.finditer(l.replace('ऽ', '\x00')):
            a = m.group(0)
            if n in soft.get(i, ()):
                a = sleft + a + sright
            elif n in off[i]:
                a = left + a + right
            res += l[pos:m.start()] + a
            pos, n = m.end(), n + 1
        out.append((res + l[pos:]).replace('\x00', 'ऽ').replace(right + left, '').replace(sright + sleft, ''))
    return out


_LONG = _re.compile('[ाीूॄेैोौॣआईऊॠएऐओऔँ-ः]|्$')
_CONJ = _re.compile(f'^{_C}्')


def by_position(lines, patterns, hint):
    """Marked syllables that are heavy only because a conjunct follows: a short
    vowel with no ं/ः or final consonant of its own (नमा«मि» श्रीविहारिणम्).
    The ārṣa licence often lets such a syllable count as light, so a verse
    whose every mark is of this kind is likely correct.
    Returns {line: {syllable: 'word' (conjunct starts the next word) or 'inner'}}.
    Hints about a wrong syllable count are skipped (their marks are guesses)."""
    if 'syllables (' in hint or 'unequal' in hint:
        return {}
    out = {}
    for i, ks in offending(patterns, hint).items():
        if i >= len(lines) or i >= len(patterns):
            continue
        ms = list(_AKSHARA.finditer(lines[i].replace('ऽ', '\x00')))
        if len(ms) != len(patterns[i]):
            continue
        for k in ks:
            if patterns[i][k] != 'G' or k + 1 >= len(ms):
                continue
            a, b = ms[k].group(0), ms[k + 1].group(0)
            if _LONG.search(a) or not _CONJ.match(b):
                continue
            gap = lines[i][ms[k].end():ms[k + 1].start()]
            out.setdefault(i, {})[k] = 'word' if gap.strip(' -') == '' and gap else 'inner'
    return out
