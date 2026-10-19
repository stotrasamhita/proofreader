"""quotes.py OUT.tsv [REF.tex] [TARGET.tex ...] — a quoted line that differs from its source.

Every line of verse in the target texts (default: gold, minus the reference itself)
is compared with every line of the reference text (default: gita/gita.tex, the
super-gold Gītā). A line that is close to a reference line (similarity 0.85 or
more, spaces ignored) but not identical to it is reported: quotations of the Gītā
in the Māhātmyas, stotras and the epics should read as the Gītā does, unless the
difference is a deliberate variant (which the editor decides).

Columns: similarity, file:line, the line, reference file:line, the reference line.
"""
import sys, os, re, difflib, collections
import corpus

ref = sys.argv[2] if len(sys.argv) > 2 else 'gita/gita.tex'
target = sys.argv[3:] or [f for f in corpus.gold() if f != ref]
DEV = re.compile('[ऀ-ॿ]')


def lines(f):
    for n, l in enumerate(open(os.path.join(corpus.ROOT, f), encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
        t = re.sub(r'[{}।॥०-९\d\-.|]', ' ', t)
        key = re.sub(r'\s+', '', t)
        if len(DEV.findall(key)) >= 12:
            yield n, key, l.strip()


R = list(lines(ref))
exact = {k for _, k, _ in R}
# index reference lines by their character 4-grams, to compare only likely pairs
grams = collections.defaultdict(set)
for i, (_, k, _) in enumerate(R):
    for j in range(len(k) - 3):
        grams[k[j:j + 4]].add(i)

out = []
for f in target:
    for n, k, l in lines(f):
        if k in exact:
            continue
        hits = collections.Counter()
        for j in range(len(k) - 3):
            for i in grams.get(k[j:j + 4], ()):
                hits[i] += 1
        best = None
        for i, c in hits.most_common(5):
            if c < (len(k) - 3) * 0.5:
                break
            r = difflib.SequenceMatcher(None, k, R[i][1]).ratio()
            if r >= 0.85 and (not best or r > best[0]):
                best = (r, i)
        if best:
            rn, _, rl = R[best[1]]
            out.append((f'{best[0]:.2f}', f'{f}:{n}', l, f'{ref}:{rn}', rl))
out.sort(key=lambda r: -float(r[0]))
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in out:
        o.write('\t'.join(r) + '\n')
print(f'{len(out)} lines close to but not the same as {ref}')
