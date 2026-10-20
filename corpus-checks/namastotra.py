"""namastotra.py NAMAVALI.tex STOTRAM.tex [OUT.tsv] — a nāmāvalī checked name by name against its stotram.

Each name of the nāmāvalī (dative, ending in नमः) is reduced to a stem by
stripping the dative ending (रामाय → राम, तुलस्यै → तुलसि, हरये → हर, विष्णवे →
विष्ण), and the stem is looked for, in order, in the stotram's text with spaces,
dandas and TeX removed (so names inside compounds and sandhi are found too).
The search starts where the previous name was found and looks a little ahead.
A name whose stem is not there is reported with the nearest stretch of the
stotram (edit distance), the place in the nāmāvalī, and the verse line.

The stotram is proofread gold, so a mismatch is most often a slip in the
nāmāvalī; sometimes a real variant, or a slip in the stotram itself.
Columns: n, name, stem, distance, stotram stretch, nāmāvalī file:line, stotram line.
"""
import sys, os, re
import corpus

NAM, STO = sys.argv[1], sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else None
DEV = re.compile('[\u0900-\u0963\u0970-\u097f]')
ENDINGS = ['ाय', '्यै', 'ायै', 'वे', 'ये', 'त्रे', 'णे', 'ने', 'ते', 'से', 'षे', 'शे', 'जे', 'चे', 'दे', 'मे', 'हे', 'ञे', 'के', 'पे', 'रे', 'ले', 'वे', 'ै', 'े']


def names(path):
    out = []
    for n, l in enumerate(open(path, encoding='utf-8'), 1):
        if l.lstrip().startswith('%') or 'नमः' not in l:
            continue
        t = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})?', ' ', l).replace('~', ' ')
        t = re.sub(r'ॐ|ओं', ' ', t)
        for chunk in re.split(r'नमः', t)[:-1]:
            w = ''.join(DEV.findall(chunk.split('॥')[-1]))
            if w:
                out.append((n, w))
    return out


def stem(w):
    for e in sorted(set(ENDINGS), key=len, reverse=True):
        if w.endswith(e) and len(w) - len(e) >= 2:
            s = w[:-len(e)]
            break
    else:
        s = w
    while s and s[-1] in 'ािीुूृेैोौंः्':
        s = s[:-1]
    return s


def stream(path):
    chars, where = [], []
    for n, l in enumerate(open(path, encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
        for ch in t:
            if DEV.match(ch) and ch not in '।॥ऽ':
                chars.append(ch)
                where.append(n)
    return ''.join(chars), where


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


text, where = stream(STO)
lines = open(STO, encoding='utf-8').read().split('\n')
pos, rows, moved = 0, [], 0
for k, (n, w) in enumerate(names(NAM), 1):
    s = stem(w)
    if s[:1] in 'अआइईउऊऋएऐओऔ' and len(s) >= 4:
        s = s[1:]             # the vowel merges with the word before it in the stotram (सुगन्धिन्यमृतोद्भवा)
    window = 400 if k == 1 else 90
    j = text.find(s, pos, pos + window + len(s))
    if j >= 0:
        pos = j + len(s)
        continue
    if len(s) >= 3 and text.find(s) >= 0:   # the nāmāvalī keeps another order here
        moved += 1
        continue
    best = None
    for i in range(pos, min(len(text), pos + window)):
        for L in (len(s) - 1, len(s), len(s) + 1):
            d = lev(s, text[i:i + L])
            if best is None or d < best[0]:
                best = (d, i, L)
    d, i, L = best
    if d <= max(1, len(s) // 4):
        pos = i + L
    rows.append((str(k), w, s, str(d), text[i:i + L], f'{os.path.relpath(NAM, corpus.ROOT)}:{n}',
                 lines[where[min(i, len(where) - 1)] - 1].strip() if where else ''))
if OUT:
    with open(OUT, 'w', encoding='utf-8') as o:
        for r in rows:
            o.write('\t'.join(r) + '\n')
else:
    for r in rows:
        print('\t'.join(r))
print(f'{len(names(NAM))} names, {len(rows)} not found as written, {moved} found out of order', file=sys.stderr)
