"""repeat.py OUT.tsv [TARGET.tex ...] — a word typed twice in a row.

Flags the same word written twice running, inside a line or across a line break
(the last word of one line and the first of the next, within a verse), in the target texts
(default: gold). Doubling is often meant (पुनः पुनः, जय जय, हरे हरे, दिने दिने), so
each pair is reported with how many times that doubling occurs across the whole
corpus (gold + reference); a doubling seen only here, once or twice, is the likely slip.

Columns: word, count of this doubling in the corpus, file:line, line.
"""
import sys, os, re, collections
import corpus
from proofreader.text import clean, WORD_RE

target = sys.argv[2:] or corpus.gold()


def words(f):
    """(line number, cleaned word, line) for every word, comments and TeX skipped."""
    for n, l in enumerate(open(os.path.join(corpus.ROOT, f), encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        if not l.strip() or '\\uvacha' in l:
            yield n, '', None   # a verse or speaker break: no doubling across it
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
        if re.search('[।॥]', t) and not WORD_RE.search(re.sub('[।॥०-९]', '', t)):
            continue
        for m in WORD_RE.finditer(t):
            w = clean(m.group(0))
            if w:
                yield n, w, l.strip()


def doublings(f):
    prev = None
    for n, w, l in words(f):
        if prev and prev[1] == w and len(w) > 1:
            yield w, n, l
        prev = (n, w, l)


seen = collections.Counter()
for f in corpus.gold() + corpus.reference():
    try:
        for w, _, _ in doublings(f):
            seen[w] += 1
    except (OSError, UnicodeDecodeError):
        pass
out = []
for f in target:
    for w, n, l in doublings(f):
        out.append((w, seen[w], f'{f}:{n}', l))
out.sort(key=lambda r: r[1])
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in out:
        o.write('\t'.join(map(str, r)) + '\n')
print(f'{len(out)} doublings; {sum(1 for r in out if r[1] <= 2)} seen at most twice in the corpus')
