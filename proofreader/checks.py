"""Checks run over a file. Each check produces Findings with a score;
higher scores are more likely to be real errors.

Layers, per word:
  ortho   impossible or near-impossible character sequences (no corpus needed)
  known   word key is in the gold lexicon: passes
  ngram   character 3/4-grams never seen in gold
  near    one edit away from a gold word, with that word as the suggestion
Per verse:
  meter   lines don't match any known metre (verse-checker)
Separately, 'style' findings flag house-convention issues (not errors).
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .text import char_ngrams, clean, key, parse_file

_M = 'ा-ौॢॣॕ-ॗ'      # dependent vowel signs
_S = 'ऀ-ः'                                # candrabindu, anusvara, visarga
_V = '्'                                       # virama
_IV = 'ऄ-औ'                               # independent vowels
_C = 'क-हक़-य़'                   # consonants

# (name, regex, weight, message). Calibrated against the gold corpus:
# each fires on at most a handful of its 150K words, and those are errors.
ORTHO_RULES = [
    ('starts-with-sign', f'^[{_M}{_S}{_V}़]', 8, 'word starts with a dependent sign'),
    ('two-vowel-signs', f'[{_M}][{_M}]', 10, 'two vowel signs in a row'),
    ('virama-then-sign', f'{_V}[{_M}{_S}{_V}़ऽ]', 10, 'virama followed by a sign'),
    ('sign-then-vowel-sign', f'[{_S}][{_M}{_V}़]', 10, 'anusvara/visarga followed by a vowel sign'),
    ('anusvara-then-vowel', f'[ंः][{_IV}]', 6, 'anusvara/visarga followed by a vowel'),
    ('visarga-mid-word', f'ः(?=[{_C}])(?![कखपफशषस])', 6, 'visarga before a consonant other than k/kh/p/ph/ś/ṣ/s'),
    ('nukta', '़', 6, 'nukta (not used in Sanskrit)'),
    ('avagraha-then-sign', f'ऽ[{_M}{_S}{_V}]', 8, 'avagraha followed by a sign'),
    ('m-before-stop', 'म्[कखगघचछजझटठडढतथदध]', 5, 'म् before a non-labial stop inside a word'),
    ('nasal-mismatch', 'ङ्[चछजझटठडढतथदधपफबभ]|ञ्[कखगघटठडढतथदधपफबभ]|ण्[कखगघचछजझतथदधपफबभ]',
     6, 'nasal does not match the class of the following stop'),
    ('vowel-after-consonant', f'[{_C}{_M}][{_IV}]', 1.5, 'independent vowel inside a word (hiatus)'),
]
_ORTHO = [(n, re.compile(p), w, m) for n, p, w, m in ORTHO_RULES]

STYLE_RULES = [
    ('anusvara-before-stop', re.compile('ं(?!ज्ञ)[कखगघचछजझटठडढतथदधपफबभ]'),
     'anusvara before a stop; house style uses the class nasal (शङ्कर, not शंकर)'),
]

REPORT_THRESHOLD = 3.0

# Edits that OCR and typists commonly make in Devanagari: visually similar
# letters, and marks that get dropped or added. Applied in both directions to
# generate candidate corrections, which the character LM then ranks.
CONFUSIONS = [
    ('प', 'ष'), ('व', 'ब'), ('म', 'भ'), ('ग', 'म'), ('य', 'थ'), ('घ', 'ध'),
    ('ध', 'थ'), ('द', 'ढ'), ('ट', 'ढ'), ('ड', 'ङ'), ('ङ्ग', 'ड्ग'), ('ञ', 'ज'),
    ('न', 'त'), ('न', 'ण'), ('श', 'स'), ('च', 'ज'), ('ह', 'ड'), ('ख', 'रव'),
    ('ु', 'ू'), ('ि', 'ी'), ('े', 'ै'), ('ो', 'ौ'), ('ृ', 'ू'), ('ा', 'ो'),
    ('र', 'त्र'), ('्', '्र'), ('ए', 'ऐ'),
    ('ं', ''), ('ः', ''), ('्', ''), ('ा', ''), ('ि', ''), ('े', ''), ('ु', ''),
    ('र्', ''), ('त्', ''), ('द्', ''),
]
_EDITS = [(a, b) for a, b in CONFUSIONS] + [(b, a) for a, b in CONFUSIONS]
EDIT_COST_BITS = 6.0     # prior against assuming an error at all
MIN_GAIN_BITS = 4.0      # smaller LM gains are noise, not evidence


@dataclass
class Finding:
    path: str
    line: int
    kind: str                 # 'word', 'meter' or 'style'
    text: str                 # the word, or the verse for meter findings
    score: float
    reasons: list = field(default_factory=list)
    suggestion: str = ''
    context: str = ''


def _edit_near_end(a, b):
    """True if the single edit between a and b lies in the last two
    characters -- typically a different inflection, not a typo."""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i >= max(len(a), len(b)) - 2


def channel_best(w, idx):
    """Best single look-alike edit of the surface word w by character-LM
    gain, net of the edit prior. Returns (bits, candidate surface form);
    bits < MIN_GAIN_BITS means keep w."""
    k = key(w)
    base = idx.logprob(k)
    best = (0.0, '')
    seen = {k}
    for a, b in _EDITS:
        start = w.find(a)
        while start != -1:
            cand = w[:start] + b + w[start + len(a):]
            ck = key(cand)
            if ck and ck not in seen:
                seen.add(ck)
                gain = idx.logprob(ck) - base - EDIT_COST_BITS
                if gain > best[0]:
                    best = (gain, cand)
            start = w.find(a, start + 1)
    return best if best[0] >= MIN_GAIN_BITS else (0.0, '')


class DocContext:
    """Evidence from the document being checked. Typos are idiosyncratic;
    a word or trigram that recurs across the document is more likely a name
    or term of that text than an error."""

    def __init__(self, words):
        self.words = Counter(key(w) for w in words)
        self.tri_types = {}
        for k in self.words:
            for g in set(char_ngrams(k, 3)):
                self.tri_types.setdefault(g, set()).add(k)

    def trigram_elsewhere(self, g, k, min_types=2):
        return len(self.tri_types.get(g, ()) - {k}) >= min_types


def score_word(word, idx, accepted=frozenset(), doc=None):
    """Returns (score, reasons, suggestion) for one word."""
    w = clean(word)
    k = key(word)
    if k in accepted:
        return 0.0, [], ''
    ortho, score, reasons = 0.0, 0.0, []
    for name, rx, weight, msg in _ORTHO:
        m = rx.search(w)
        if m:
            ortho += weight
            reasons.append(f'{name}: {msg} «{m.group(0)}»')
    if idx.words.get(k, 0) > 0:
        return ortho, reasons, ''

    unseen = {n: [g for g in char_ngrams(k, n) if idx.ngrams[n].get(g, 0) <= 0]
              for n in (3, 4)}
    if doc:
        unseen[3] = [g for g in unseen[3] if not doc.trigram_elsewhere(g, k)]
    u3, u4 = len(unseen[3]), len(unseen[4])
    # A typo leaves one or two novel trigrams; a long valid compound in a
    # small corpus leaves many spread out. So novelty saturates.
    if u3:
        score += 3 * min(u3, 2) + 0.5 * max(0, u3 - 2)
        reasons.append('unseen trigram ' + ' '.join(g.strip('^$') or g for g in unseen[3]))
    if u4:
        score += 0.75 * min(u4, 3)

    suggestion = ''
    best_bits, best_cand = channel_best(w, idx)
    if best_bits > 0:
        in_gold = idx.words.get(key(best_cand), 0) > 0
        gain = min(best_bits, 24) / 3 + (3 if in_gold else 0)
        score += gain / 2 if _edit_near_end(w, best_cand) else gain
        suggestion = best_cand
        reasons.append(f'{suggestion} is {best_bits:.0f} bits likelier'
                       + (' (gold word)' if in_gold else ''))

    nb = idx.neighbours(k)
    if nb:
        best, cnt = nb[0]
        suggestion = suggestion or idx.forms.get(best, best)
        if _edit_near_end(k, best):
            score += 0.5
        else:
            score += 1.5 + 0.5 * min(math.log2(1 + cnt), 4)
            reasons.append(f'one edit from {suggestion} (×{cnt})')
    if doc and doc.words[k] > 1:
        score /= min(1 + 0.5 * (doc.words[k] - 1), 3)
        reasons.append(f'(occurs {doc.words[k]}× in this file)')
    return ortho + score, reasons, suggestion


def check_file(path, idx, meter=None, accepted=frozenset(), display_path=None,
               threshold=REPORT_THRESHOLD, style=False):
    """All findings for one file at or above the threshold."""
    display_path = display_path or path
    out = []
    units = parse_file(path)
    doc = DocContext(w for u in units for w, _ in u.words())
    for unit in units:
        for word, line in unit.words():
            s, reasons, sugg = score_word(word, idx, accepted, doc)
            if s >= threshold:
                out.append(Finding(display_path, line.lineno, 'word', word, round(s, 1),
                                   reasons, sugg, line.text))
            if style:
                for name, rx, msg in STYLE_RULES:
                    if rx.search(clean(word)):
                        out.append(Finding(display_path, line.lineno, 'style', word, 0,
                                           [f'{name}: {msg}'], '', line.text))
        if meter and unit.kind == 'verse':
            out.extend(_meter_findings(unit, meter, display_path, accepted))
    return out


def verse_id(lines):
    """How accepted.txt names a verse: 'meter: ' + its first line's key."""
    first = next((l for l in lines if l.strip()), '')
    return 'meter: ' + ' '.join(key(w) for w in first.split())


def verse_ok(lines, meter):
    """(ok, result) for one verse. Anuṣṭup-shaped verses (any number of
    16-syllable lines) are judged by the anuṣṭup rules directly; verse-checker
    only knows the 2-line form. Everything else goes to verse-checker."""
    from .meter import structural_check
    r = meter.check(lines)
    if r['ok']:
        return True, r
    ok, hint = structural_check(r['patterns'])
    return ok, dict(r, hint=hint)


def _meter_findings(unit, meter, display_path, accepted=frozenset()):
    from .meter import anushtup_like, severity
    lines = [l.text for l in unit.lines]
    if not any(l.strip() for l in lines) or verse_id(lines) in accepted:
        return []
    ok, r = verse_ok(lines, meter)
    if ok:
        return []
    pats = r['patterns']
    if anushtup_like(pats):
        reasons = ['anuṣṭup: ' + r['hint']]
    else:
        reasons = [f'{r["hint"]} (closest known metre: {r["metre"] or "none"})']
    reasons.append('pattern: ' + ' | '.join(f'{p} ({len(p)})' for p in pats))
    score = severity(r['hint'])
    return [Finding(display_path, unit.lines[0].lineno, 'meter', ' / '.join(lines),
                    score, reasons)]
