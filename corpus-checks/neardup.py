"""neardup.py OUT.tsv [TARGET.tex ...] — rare words one keystroke from a common word.

Flags a word in the target texts (default: gold) that occurs at most twice in
the whole corpus but is one edit away from a word that occurs at least 20
times as often: one code point changed, added, dropped, or two neighbours
swapped (रघावौ / राघवौ). Counts come from every text in the repos, not just
the target, because the right form is often rare in the target alone (gold
has राघवौ twice; the corpus has it 85 times).

A hit is "supported" when the common word appears elsewhere next to the same
neighbour (सह राघवौ). Order: edits inside the word with support, inside
without, then edits in the last two code points (mostly case endings) with
and without support. Words in accepted.txt are skipped.

Columns: tier, support, word, count, common word, its count, edit, file:line.
On gold (2026-10-17): 34 supported inner hits, ~10 real typos among them.
"""
import sys, os, collections
import corpus
from proofreader.text import parse_file, clean, WORD_RE

target = sys.argv[2:] or corpus.gold()
cnt = collections.Counter()                    # all texts
bi = collections.Counter()                     # (word, next word), all texts
ctx = collections.defaultdict(list)            # target word -> [(prev, next)]
where = {}


def toks(t):
    return [w for w in (clean(m.group(0)).replace('-', '') for m in WORD_RE.finditer(t.replace('\\mbox{}', ''))) if w]


tset = set(target)
for f in sorted(tset | set(corpus.gold()) | set(corpus.reference())):
    try:
        units = parse_file(os.path.join(corpus.ROOT, f))
    except Exception:
        continue
    for u in units:
        for ln in u.lines:
            ws = toks(ln.text)
            for i, w in enumerate(ws):
                if i:
                    bi[ws[i - 1], w] += 1
                if len(w) < 3:
                    continue
                cnt[w] += 1
                if f in tset:
                    where.setdefault(w, f'{f}:{ln.lineno}')
                    ctx[w].append((ws[i - 1] if i else '', ws[i + 1] if i + 1 < len(ws) else ''))

acc = {l.split()[0] for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt')) if l.strip() and not l.startswith('#')}

dels = collections.defaultdict(set)            # one-deletion neighbourhoods
for w in cnt:
    dels[w].add(w)
    for i in range(len(w)):
        dels[w[:i] + w[i + 1:]].add(w)


def edit(a, b):
    """(position, kind) of the single edit turning a into b, else None"""
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        if len(d) == 1:
            return d[0], 'sub'
        if len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]]:
            return d[0], 'swap'
        return None
    s, l = (a, b) if len(a) < len(b) else (b, a)
    if len(l) - len(s) != 1:
        return None
    for i in range(len(l)):
        if l[:i] + l[i + 1:] == s:
            return i, 'ins' if len(b) > len(a) else 'del'
    return None


rows = []
for w in where:
    c = cnt[w]
    if c > 2 or w in acc or len(w) < 4:
        continue
    best = None
    for k in {w} | {w[:i] + w[i + 1:] for i in range(len(w))}:
        for v in dels.get(k, ()):
            if v == w or cnt[v] < 20 * c or cnt[v] < 20:
                continue
            e = edit(w, v)
            if e and (best is None or cnt[v] > cnt[best[0]]):
                best = (v, e)
    if best:
        v, (pos, kind) = best
        inner = pos < min(len(w), len(v)) - 2
        sup = sum(bi[p, v] + bi[v, n] for p, n in ctx[w])
        rows.append((inner, sup, w, c, v, cnt[v], kind, where[w]))
rows.sort(key=lambda r: (not r[0], not r[1], -r[5]))
with open(sys.argv[1], 'w') as o:
    for r in rows:
        o.write('\t'.join(map(str, ('inner' if r[0] else 'ending',) + r[1:])) + '\n')
print(len(rows), 'rare words one edit from a common word;', sum(r[0] for r in rows), 'inner;',
      sum(bool(r[0] and r[1]) for r in rows), 'inner with context support')
