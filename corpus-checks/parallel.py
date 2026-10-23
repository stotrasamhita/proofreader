"""parallel.py A.tex B.tex OUT.tsv — line up the verse lines of A against a parallel text B.

Each verse line ({…} inside a shloka macro) is normalised (no spaces, avagraha,
dandas, hyphens or TeX) and matched to B's most similar line through shared
character trigrams, then scored with difflib. Output: one row per A line with
its best B line and the score; 1.0 = same up to spacing and avagraha.
"""
import sys, re, difflib, collections

def verses(p):
    out = []
    for n, l in enumerate(open(p, encoding='utf-8'), 1):
        s = l.strip()
        if not s.startswith('{') or s.startswith('{॥'): continue
        t = re.sub(r'%.*', '', s).strip()
        t = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})?', '', t).strip('{} ')
        if len(t) < 8: continue
        out.append((n, t, norm(t)))
    return out

def norm(t):
    return re.sub(r'[\sऽ।॥\-‌‍०-९0-9.,;:!?()\[\]{}]', '', t)

A, B = verses(sys.argv[1]), verses(sys.argv[2])
tri = collections.defaultdict(set)
for j, (_, _, b) in enumerate(B):
    for k in range(len(b) - 2): tri[b[k:k + 3]].add(j)
with open(sys.argv[3], 'w', encoding='utf-8') as f:
    for n, t, a in A:
        c = collections.Counter(j for k in range(len(a) - 2) for j in tri.get(a[k:k + 3], ()))
        best = max(((difflib.SequenceMatcher(None, a, B[j][2]).ratio(), j) for j, _ in c.most_common(8)), default=(0, None))
        r, j = best
        f.write(f"{n}\t{r:.3f}\t{t}\t{B[j][0] if j is not None else ''}\t{B[j][1] if j is not None else ''}\n")
