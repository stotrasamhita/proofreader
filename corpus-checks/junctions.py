"""junctions.py TARGETS [EXCLUDE] — four word-junction checks learnt from the editor's hand fixes.

TARGETS is a comma-separated list of .tex paths; EXCLUDE (optional) is a path fragment
left out of the gold counts (to score a file against the rest of gold). Output, by kind:

  A  a compound written apart: a bare stem (or a feminine -ā/-ī before a masc./neut.
     -aḥ/-am word) that gold uses mainly as a first member, before a word gold uses
     mainly as a last member (ब्रह्महत्यादि पापघ्नी, भक्त कारणात्). Only pairs with a
     space between them; vocatives (देव, कर्ण, रावण) are most of the noise.
  B  a word run together with the next: a free word that ends in a vowel (अद्य,
     शतं, यत्र, येन; अपि/अत्र/अद्य/अथ after ऽ), and any ablative/aorist/optative in
     -आत्/-आद् fused to the next word (वेगात्सुग्रीव, संसाराद्गमिष्यामि, शक्नुयाद्वक्तुं).
  C  an avagraha missing at a word boundary under the house rule: ā+a → ाऽ,
     a+ā and ā+ā → ाऽऽ, a+a unmarked (tried first, so एव+अस्ति is never flagged).
  D  a bare i/u stem ending a pāda where gold writes the nominative (कृताञ्जलि).

All four are candidate lists, to be read: on gold (2026-10-19) A gave 5 real in 54,
B about 160 in 189, C about 60 in 219, D 3 in 5. The readings that are not slips:
imperatives (प्रविश्यताम्, पालयस्व), fixed compounds (परात्पर, आत्मसात्कृ,
अद्यप्रभृति, सुखीभूत्वा, एवंवीर्य), अद्वय after -आ (अथाद्वयो), त् + ह = द्ध
(अभ्यगाद्धरिः), genitives in -आः before त (कृष्णायास्तु), a+a read as a+ā
(the right word starts with अ: अनु-, असुर, अर्जुन, अर्घ्य).
"""
import sys, os, re, collections
import corpus
from proofreader.text import clean, WORD_RE

TARGETS = sys.argv[1].split(',')
EXCL = sys.argv[2] if len(sys.argv) > 2 else None
V = 'ािीुूृॄेैोौ'
CONS = lambda c: 'क' <= c <= 'ह'


def lines(path):
    for n, l in enumerate(open(path, encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = re.sub(r'\\-|\\footnotemark(\{\})?', '', t)
        yield n, t, l.strip()


def words(t):
    return [w for w in (clean(m.group(0)) for m in WORD_RE.finditer(t)) if w]


G = collections.Counter()          # gold tokens
PAIR = collections.Counter()       # gold adjacent pairs inside a pāda
for f in corpus.gold():
    if EXCL and EXCL in f:
        continue
    for n, t, _ in lines(os.path.join(corpus.ROOT, f)):
        for seg in re.split(r'[{}।॥|]', t):
            ws = words(seg)
            for w in ws:
                G[w] += 1
            for a, b in zip(ws, ws[1:]):
                PAIR[a, b] += 1

# compound membership: T = X + Y with X, Y both gold words or stems
TAIL = collections.Counter()       # Y as the last member of a longer token
HEAD = collections.Counter()       # X as a first member
STEMS = set()
for w, c in G.items():
    for i in range(2, len(w) - 2):
        x, y = w[:i], w[i:]
        if not CONS(y[0]) or w[i - 1] == '्':
            continue
        if G[y] + 0 >= 1 and len(y) >= 3:
            TAIL[y] += c
        if len(x) >= 2:
            HEAD[x] += c

PREF = collections.Counter(w[:3] for w in G.elements())
out = collections.defaultdict(list)
for TARGET in TARGETS:
 for n, t, raw in lines(TARGET):
    if '॥इति' in raw or 'इति श्री' in raw:
        continue
    for seg in re.split(r'[{}।॥|]', t):
        ws = words(seg)
        spaced = {(clean(m1.group(0)), clean(m2.group(0))) for m1, m2 in zip(WORD_RE.finditer(seg), list(WORD_RE.finditer(seg))[1:]) if seg[m1.end():m2.start()].strip() == ''}
        # A. compound written apart: X a bare stem (or a feminine -ā/-ī before a masc./neut. -aḥ/-am word)
        for a, b in zip(ws, ws[1:]):
            if (a, b) not in spaced or 'HanumanChalisa' in TARGET or len(b) < 3 or not CONS(b[0]) or a[-1] in 'ःं्ॆेैोौ' or len(a) < 3:
                continue
            bare = CONS(a[-1]) or a[-1] in 'िु'
            fem = a[-1] in 'ाी' and b[-1] in 'ःं' and b[-2] not in 'ाीूैौ' and not b.endswith(('या', 'यः'))
            if not (bare or fem):
                continue
            if a.endswith(('स्य', 'एन', 'ेन', 'त्वा', 'ाया', 'पि', 'च', 'श्च', 'ञ्च')):
                continue
            head = HEAD[a] / (G[a] + 1); tail = (TAIL[b] + 1) / (G[b] + 1)
            if (head >= 2 and tail >= 0.8 or G[a + b] >= 1) and PAIR[a, b] <= 2:
                out['A'].append((os.path.relpath(TARGET, corpus.ROOT) + ':' + str(n), f'{a} {b}', f'{a}{b}'))
        # D. bare i/u stem where gold writes the nominative
        for w in ws[-1:]:
            if w[-1] in 'िु' and G[w + 'ः'] >= 3 and G[w + 'ः'] >= 5 * G[w]:
                out['D'].append((os.path.relpath(TARGET, corpus.ROOT) + ':' + str(n), w, w + 'ः'))
        for w in ws:
            # B. a free vowel-final word run into the next (अद्य स्थित्वा, कुरु व्रतम्, अपि राजर्षिः)
            for i in range(2, len(w) - 2):
                x, y = w[:i], w[i:]
                if not CONS(y[0]) or w[i - 1] == '्' or G[w] > 2:
                    continue
                xs = ('अ' + x.split('ऽ')[-1]) if 'ऽ' in x else x
                if xs in ('अपि', 'अत्र', 'अद्य', 'अथ') and 'ऽ' in x or (
                        G[xs] >= 10 and HEAD[xs] <= 0.05 * G[xs] and len(xs) >= 2):
                    if G[y] >= 2:
                        out['B'].append((os.path.relpath(TARGET, corpus.ROOT) + ':' + str(n), w, f'{x} {y}'))
                        break
            # B2. an ablative in -आत्/-आद् run into the next word
            m = re.match(r'^(.{2,}ा[तद]्)([क-ह].{2,})$', w)
            if m and G[w] <= 2 and not m.group(2).startswith(('ताप', 'म', 'र', 'य', 'व्य', 'वा')) and not (m.group(1).endswith('द्') and m.group(2)[0] in 'यर') and (G[m.group(2)] >= 1 or any(G[m.group(2)[:k]] >= 3 for k in range(3, len(m.group(2))))):
                out['B'].append((os.path.relpath(TARGET, corpus.ROOT) + ':' + str(n), w, f'{m.group(1)} {m.group(2)}'))
            # C. avagraha missing after a free word: ā+a → ाऽ, a+ā → ाऽऽ
            for i in range(2, len(w) - 1):
                if w[i - 1] != 'ा' or G[w] > 2:
                    continue
                x0, rest = w[:i - 1], w[i:]      # w = x0 + ा + rest
                aa = G[x0] >= 5 and (G['अ' + rest] >= 2 or G['अ' + rest[:-1]] + G['अ' + rest + '्'] >= 2)
                if aa or x0.endswith(('स्य', 'स्या')):      # a+a, unmarked by the house rule; -स्याः genitives
                    continue
                for left, right, mark in ((x0 + 'ा', 'अ' + rest, 'ाऽ'), (x0, 'आ' + rest, 'ाऽऽ')):
                    known_r = G[right] >= 2 or (len(left) >= 3 and PREF[right[:3]] >= 5)
                    if G[left] >= 5 and HEAD[left] <= 0.1 * G[left] and known_r:
                        out['C'].append((os.path.relpath(TARGET, corpus.ROOT) + ':' + str(n), w, x0 + mark + rest))
                        break
for k in 'ABCD':
    print(f'== {k}: {len(out[k])}')
    for r in out[k]:
        print(*r, sep='\t')
