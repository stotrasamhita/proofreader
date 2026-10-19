"""nasal.py OUT.tsv [TARGET.tex ...] — anusvāra or class nasal before a stop, inside a word.

Before a stop (क…म) a word can write the anusvāra (संग, कंठ, संत) or the nasal of
the stop's class (सङ्ग, कण्ठ, सन्त). Both are correct; a corpus should pick one.
Words are keyed with every such nasal folded to ं, and a key written both ways
across the target texts (default: gold) is reported, with counts and the files
of the minority form. Word-final ं (before a space) is not involved, and neither is
ं before य र ल व श ष स ह, which can only be the anusvāra.

Columns: minority form, its count, majority form, its count, files of the minority form.
A summary line gives the corpus-wide ratio of class nasal to anusvāra.
"""
import sys, os, re, collections
import corpus
from proofreader.text import clean, WORD_RE

target = sys.argv[2:] or corpus.gold()
CLS = {'ङ': 'कखगघ', 'ञ': 'चछजझ', 'ण': 'टठडढ', 'न': 'तथदध', 'म': 'पफबभ'}
NAS = re.compile('([ङञणनम])्(?=([क-म]))')
ANU = re.compile('ं(?=[क-म])')


def fold(w):
    return NAS.sub(lambda m: 'ं' if m.group(2) in CLS[m.group(1)] else m.group(0), w)


forms = collections.defaultdict(collections.Counter)
where = collections.defaultdict(set)
anu = cls = 0
for f in target:
    for l in open(os.path.join(corpus.ROOT, f), encoding='utf-8'):
        if l.lstrip().startswith('%'):
            continue
        for m in WORD_RE.finditer(re.sub(r'(?<!\\)%.*', '', l)):
            w = clean(m.group(0))
            k = fold(w)
            if k == w and not ANU.search(w):
                continue
            anu += len(ANU.findall(w))
            cls += sum(1 for x in NAS.finditer(w) if x.group(2) in CLS[x.group(1)])
            forms[k][w] += 1
            where[w].add(f)
rows = []
for k, c in forms.items():
    if len(c) < 2:
        continue
    (maj, nm), *rest = c.most_common()
    for w, n in rest:
        rows.append((w, n, maj, nm, ' '.join(sorted(where[w]))))
rows.sort(key=lambda r: -r[3])
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in rows:
        o.write('\t'.join(map(str, r)) + '\n')
print(f'{len(rows)} words written both ways; inside words, class nasal {cls}, anusvāra {anu}')
