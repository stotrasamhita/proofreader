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
    """Lines are 16-syllable half-verses, give or take the one being wrong."""
    return (bool(patterns) and all(15 <= len(p) <= 17 for p in patterns)
            and sum(len(p) == 16 for p in patterns) * 2 >= len(patterns))


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
