"""runon.py OUT.tsv [TARGET.tex ...] — two words run together after ः or ं.

Flags a word in the target texts (default: gold) that has a visarga or
anusvāra followed by a consonant inside it (महात्मनःसदा, परेषांसर्वा), where
the joined word is rare (at most twice in the whole corpus) but both halves
are ordinary words (each at least 5 times). Real compounds and words joined
by sandhi (अन्तःकरण, नमःशिवाय, संसार) are common as a whole, so they drop out.

A hit is "supported" when the two halves also occur elsewhere as separate,
adjacent words (महात्मनः सदा); real compounds rarely are. Supported hits come
first. Skipped: the prefix सं-, and ं before स् (n-sandhi: तांस्तथा).

Counts come from every text in the repos, not just the target. Words in
accepted.txt are skipped.

Columns: support (times the split pair occurs), word, its count, left half, count, right half, count, file:line, line.
"""
import sys, os, re, collections
import corpus
from proofreader.text import parse_file, clean, WORD_RE

RARE, COMMON = 2, 5
target = sys.argv[2:] or corpus.gold()
JOIN = re.compile('[ःं](?=[क-हक़-य़])')
accepted = {l.split('#')[0].strip() for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt'), encoding='utf-8')}


def toks(t):
    return [w for w in (clean(m.group(0)).replace('-', '') for m in WORD_RE.finditer(t.replace('\\mbox{}', ''))) if w]


cnt = collections.Counter()
bi = collections.Counter()          # adjacent pairs, all texts
where = collections.defaultdict(list)
tset = set(target)
for f in sorted(tset | set(corpus.gold()) | set(corpus.reference())):
    try:
        units = parse_file(os.path.join(corpus.ROOT, f))
    except Exception:
        continue
    for u in units:
        for ln in u.lines:
            ws = toks(ln.text)
            cnt.update(ws)
            bi.update(zip(ws, ws[1:]))
            if f in tset:
                for w in ws:
                    if JOIN.search(w):
                        where[w].append((f, ln.lineno, ln.text.strip()))

rows = []
for w, locs in where.items():
    if cnt[w] > RARE or w in accepted:
        continue
    for m in JOIN.finditer(w):
        a, b = w[:m.end()], w[m.end():]
        if a == 'सं' or (a.endswith('ं') and b.startswith('स्')):   # prefix; n-sandhi (तांस्तथा)
            continue
        if cnt[a] >= COMMON and cnt[b] >= COMMON:
            for f, n, t in locs:
                rows.append((bi[a, b], w, cnt[w], a, cnt[a], b, cnt[b], f'{f}:{n}', t))
            break
rows.sort(key=lambda r: (-r[0], -min(r[4], r[6])))
with open(sys.argv[1], 'w') as o:
    for r in rows:
        o.write('\t'.join(map(str, r)) + '\n')
print(sum(r[0] > 0 for r in rows), 'supported and', sum(r[0] == 0 for r in rows), 'unsupported run-together words in', len({r[7].rsplit(':', 1)[0] for r in rows}), 'files')
