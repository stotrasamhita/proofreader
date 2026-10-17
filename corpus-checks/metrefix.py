"""metrefix.py VERSES.json OUT.tsv — one-letter word changes that make a verse scan.

For a verse the metre check rejects, try replacing one word with a word one
edit away (a code point changed, added, dropped, or two swapped) that occurs
at least 3 times in the whole corpus. Report every replacement after which the
verse passes (exact known metre, or the structural rules in meter.py).

This complements neardup.py, which only looks at rare words: here both forms
may be common (सहस्रकोटि / सहस्रकोटी), and the metre is the evidence.

VERSES.json: a list of {file, line, padas: [...]} (e.g. the open metre rows
of a review round, with the verse's pāda lines).
"""
import sys, os, json, collections
import corpus
from proofreader.text import parse_file, clean, WORD_RE
from proofreader.meter import MeterChecker, structural_check

MIN = 3
verses = json.load(open(sys.argv[1]))
cnt = collections.Counter()
for f in sorted(set(corpus.gold()) | set(corpus.reference())):
    try:
        for u in parse_file(os.path.join(corpus.ROOT, f)):
            for ln in u.lines:
                cnt.update(clean(m.group(0)) for m in WORD_RE.finditer(ln.text.replace('\\mbox{}', '')))
    except Exception:
        pass
vocab = [w for w, c in cnt.items() if c >= MIN and len(w) >= 2]
dels = collections.defaultdict(set)
for w in vocab:
    dels[w].add(w)
    for i in range(len(w)):
        dels[w[:i] + w[i + 1:]].add(w)


def one_edit(a, b):
    if a == b:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, l = sorted((a, b), key=len)
    return len(l) - len(s) == 1 and any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def neighbours(w):
    out = set()
    for k in {w} | {w[:i] + w[i + 1:] for i in range(len(w))}:
        for v in dels.get(k, ()):
            if one_edit(w, v):
                out.add(v)
    return sorted(out, key=lambda v: -cnt[v])[:40]


mc = MeterChecker()


def passes(lines):
    r = mc.check(lines)
    return r['ok'] or structural_check(r['patterns'])[0]


rows = []
for n, v in enumerate(verses):
    padas = v['padas']
    if passes(padas):
        continue
    for i, line in enumerate(padas):
        for m in WORD_RE.finditer(line):
            w = clean(m.group(0))
            if len(w) < 2:
                continue
            for x in neighbours(w):
                new = line[:m.start()] + m.group(0).replace(w, x) + line[m.end():]
                if passes(padas[:i] + [new] + padas[i + 1:]):
                    rows.append((v['file'], v['line'], i + 1, w, x, cnt[w], cnt[x], new, ' / '.join(padas)))
    if n % 25 == 0:
        print(n, len(rows), file=sys.stderr)
mc.save_cache()
rows.sort(key=lambda r: -r[6] / (r[5] + 1))
with open(sys.argv[2], 'w') as o:
    for r in rows:
        o.write('\t'.join(map(str, r)) + '\n')
print(len(rows), 'replacements that make a verse scan, in', len({(r[0], r[1]) for r in rows}), 'verses')
