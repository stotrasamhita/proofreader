"""sandhi.py OUT.tsv [TARGET.tex ...] — external sandhi left unmade between two words.

Looks at each pair of words written apart on one line of the target texts (default:
gold) and flags the junctions where the word-final sound should have changed:

  aH     -अः before a voiced consonant (रामः गच्छति → रामो गच्छति), before अ
         (→ रामोऽत्र), or before another vowel (→ राम आगतः)
  AH     -आः before a vowel or voiced consonant (देवाः गताः → देवा गताः)
  iH     -इः/-उः etc. before a vowel or voiced consonant (हरिः अपि → हरिरपि)
  saH    सः/एषः before any consonant (सः गच्छति → स गच्छति)
  Hc     a visarga before च छ त थ ट ठ (रामः च → रामश्च, ततः तत्र → ततस्तत्र)
  t      -त् (also -क्, -ट्, -प्) before a voiced consonant or vowel (तत् वाक्यं → तद् वाक्यं)
  m      -म् before a consonant inside a line (गृहम् यत्र → गृहं यत्र)

A space at a pāda break is not a junction (pausa is allowed there), so a space
within one syllable of the line's midpoint on lines of 14 or more syllables is
skipped. Comments, TeX commands and words in accepted.txt are skipped.

Columns: rule, junction, proposed, file:line, line.
"""
import sys, os, re
import corpus
from proofreader.meter import syllables

target = sys.argv[2:] or corpus.gold()
accepted = {l.split('#')[0].strip() for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt'), encoding='utf-8')}
VOW = 'अआइईउऊऋॠएऐओऔ'
SIGN = 'ािीुूृॄेैोौ'
VOICED = 'गघङजझञडढणदधनबभमयरलवह'
NASAL = 'ङञणनम'
CONS = '[क-ह]'
DEV = re.compile(r'[ऀ-ॿ‌‍]+')
SIGN_OF = dict(zip('आइईउऊऋॠएऐओऔ', 'ािीुूृॄेैोौ'))
SIGN_OF['अ'] = ''


def vowel_initial(w):
    return w[0] in VOW


def join_vowel(stem, w2):
    """stem ending in a consonant + w2 starting with an independent vowel."""
    if stem.endswith('्'):
        stem = stem[:-1]
    return stem + SIGN_OF.get(w2[0], w2[0]) + w2[1:]


def rule(w1, w2):
    """(rule, proposed text for 'w1 w2') or None."""
    a, b = w1[-1], w2[0]
    voiced = b in VOICED or vowel_initial(w2)
    if w1 in ('सः', 'एषः') and re.match(CONS, b):
        return 'saH', w1[:-1] + ' ' + w2
    if a == 'ः':
        p = w1[-2]
        if b in 'चछ':
            return 'Hc', w1[:-1] + 'श्' + w2
        if b in 'तथ':
            return 'Hc', w1[:-1] + 'स्' + w2
        if b in 'टठ':
            return 'Hc', w1[:-1] + 'ष्' + w2
        if not voiced:
            return None
        if p == 'ा':
            return 'AH', w1[:-1] + ' ' + w2
        if p in SIGN or p in VOW:
            if b == 'र':
                return 'iH', None
            return 'iH', (join_vowel(w1[:-1] + 'र्', w2) if vowel_initial(w2) else w1[:-1] + 'र्' + w2)
        if re.match(CONS, p):
            if b == 'अ':
                return 'aH', w1[:-1] + 'ोऽ' + w2[1:]
            if vowel_initial(w2):
                return 'aH', w1[:-1] + ' ' + w2
            return 'aH', w1[:-1] + 'ो ' + w2
        return None
    if w1.endswith('्') and len(w1) > 2 and w1[-2] in 'तकटप':
        soft = {'त': 'द', 'क': 'ग', 'ट': 'ड', 'प': 'ब'}[w1[-2]]
        if vowel_initial(w2):
            return 't', join_vowel(w1[:-2] + soft, w2)
        if b in NASAL or b in 'जल':
            return 't', None
        if b in VOICED:
            return 't', w1[:-2] + soft + '् ' + w2
        return None
    if w1.endswith('म्') and re.match(CONS, b):
        return 'm', w1[:-2] + 'ं ' + w2
    return None


def at_pada_break(text, pos):
    n = len(syllables(text))
    k = len(syllables(text[:pos]))
    return n >= 14 and abs(k - n / 2) <= 1


out = []
for f in target:
    for n, l in enumerate(open(os.path.join(corpus.ROOT, f), encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t).replace('{', ' ').replace('}', ' ')
        t = re.sub(r'[।॥०-९\d]+', ' | ', t)
        for seg in t.split('|'):
            words = list(DEV.finditer(seg))
            body = seg.strip()
            for m1, m2 in zip(words, words[1:]):
                if seg[m1.end():m2.start()] != ' ':
                    continue
                w1, w2 = m1.group(0).replace('‌', ''), m2.group(0).replace('‌', '')
                if len(w1) < 2 or not w2 or w1 in accepted or (w1 + ' ' + w2) in accepted:
                    continue
                r = rule(w1, w2)
                if not r:
                    continue
                if at_pada_break(body, len(seg[:m1.end()].lstrip())):
                    continue
                out.append((r[0], f'{w1} {w2}', r[1] or '?', f'{f}:{n}', l.strip()))
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in out:
        o.write('\t'.join(r) + '\n')
from collections import Counter
print(len(out), dict(Counter(r[0] for r in out)))
