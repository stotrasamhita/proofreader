"""ocrorder.py OCR.txt FIRST LAST STOTRAM.txt SFIRST SLAST OUT.tsv [SKIP_FROM-SKIP_TO]
— put an OCR'd nāmāvalī whose two-column pages were read out of order back
in the order of its stotram (plain text, verse lines SFIRST..SLAST, 1-based).
Written for the Gaṅgā-sahasranāmāvalī (review/ganga/order1000.py).

Each OCR item (a line with नमः in the sahasranāma pages) is reduced to a stem
(namastotra.stem) and located in the Kāśīkhaṇḍa stotram (verses 17-168, var
notes dropped) by its consonant skeleton (vowels dropped, so sandhi at the
name's edges — अतुला after ā, इष्टा after ī — does not hide it; nasal + virama
before a consonant = anusvāra). Of the exact skeleton hits, the one nearest
the item's expected place (its page's share of the stotram) wins; with no
hit, the nearest stretch by edit distance within ±2500 letters.
Columns: pos, ocr_line, ocr_name, note, stem, skeleton_dist, stotram_stretch, verse."""
import sys, re
sys.path.insert(0, '/data1/karthik_data/StotraSamhita/proofreader/corpus-checks')
_argv = sys.argv; sys.argv = ['x', '/dev/null', '/dev/null']
from namastotra import stem, lev
sys.argv = _argv
OCR, A, B, KK, SA, SB, OUT = sys.argv[1:8]
A, B, SA, SB = int(A), int(B), int(SA), int(SB)
SKIP = tuple(map(int, sys.argv[8].split('-'))) if len(sys.argv) > 8 else (0, -1)
DEV = re.compile('[ऀ-ॣ॰-ॿ]')
VOW = re.compile('[ऄ-औा-ौॠ-ॣँ]')


def norm(t):
    return re.sub('[ङञणनम]्(?=[क-म])', 'ं', t).replace('ॐ', 'ओं')


kk = open(KK, encoding='utf-8').read().split('\n')
S, verse, v = '', [], 1
for l in kk[SA - 1:SB]:
    l = norm(l.split(' var ')[0])
    for ch in l:
        if DEV.match(ch) and ch not in '।॥ऽ' and not '०' <= ch <= '९':
            S += ch; verse.append(v)
    if re.search(r'॥\s*[०-९]+॥', l):
        v += 1

items = []
lines = open(OCR, encoding='utf-8').read().split('\n')
for n in range(A, B + 1):
    l = lines[n - 1]
    if 'नमः' not in l or 'करिष्ये' in l or 'समर्पयामि' in l:
        continue
    note = ' '.join(re.findall(r'\(([^)]*)\)', l))
    t = re.sub(r'\([^)]*\)', ' ', l)
    for chunk in t.split('नमः')[:-1]:
        w = ''.join(DEV.findall(chunk.replace('ॐ', ' ')))
        w = re.sub(r'^[०-९]+', '', w)
        if w:
            items.append((n, w, note))

IND = dict(zip('अआइईउऊऋएऐओऔ', ['', 'ा', 'ि', 'ी', 'ु', 'ू', 'ृ', 'े', 'ै', 'ो', 'ौ']))
taken = [False] * len(S)


def pattern(st):
    if st and st[0] in IND:     # initial vowel: as written, as a sign after sandhi, or merged away
        return '(?:%s|[ािीुूृेैोौ]?)%s' % (st[0], re.escape(st[1:]))
    return re.escape(st)


out, rest = [], []
order = sorted(range(len(items)), key=lambda k: -len(items[k][1]))
free = lambda a, b: not any(taken[a:b])
for k in order:                  # pass 1: exact hits, longest names first
    n, w, note = items[k]
    if SKIP[0] <= n <= SKIP[1]:  # another list's names on the same page
        continue
    st = norm(stem(w))
    exp = (n - A) / (B - A) * len(S)
    hits = [m for m in re.finditer(pattern(st), S) if free(m.start(), m.end())] if len(st) >= 2 else []
    if not hits:
        rest.append(k); continue
    m = min(hits, key=lambda h: abs(h.start() - exp))
    for i in range(m.start(), m.end()):
        taken[i] = True
    out.append((m.start(), n, w, note, st, 0, S[max(0, m.start() - 1):m.end() + 1], verse[m.start()]))
# pass 2: names with no exact hit go into the free gaps the exact hits left,
# cheapest (edit distance at a gap's start) first, so near-misses don't swap.
cands = []
for k in rest:
    n, w, note = items[k]
    st = norm(stem(w))
    exp = (n - A) / (B - A) * len(S)
    for g in [i for i in range(max(0, int(exp) - 3000), min(len(S), int(exp) + 3000))
              if not taken[i] and (i == 0 or taken[i - 1])]:
        for L in range(max(1, len(st) - 2), len(st) + 3):
            if free(g, g + L):
                if g + L <= len(S): cands.append((lev(st, S[g:g + L]) / max(1, len(st)), abs(g - exp), k, g, g + L))
cands.sort()
done = set()
for c, _, k, p, e in cands:
    if k in done or not free(p, e):
        continue
    n, w, note = items[k]
    st = norm(stem(w))
    for i in range(p, e):
        taken[i] = True
    done.add(k)
    out.append((p, n, w, note, st, lev(st, S[p:e]), S[max(0, p - 1):e + 1], verse[p]))
for k in rest:
    if k not in done:
        n, w, note = items[k]
        out.append((len(S), n, w, note, '', 99, 'UNPLACED', 0))
out.sort()
with open(OUT, 'w', encoding='utf-8') as f:
    for r in out:
        f.write('\t'.join(map(str, r)) + '\n')
print(len(items), 'names;', sum(1 for r in out if r[5]), 'not found exactly')
