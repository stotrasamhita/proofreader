"""repha.py OUT.tsv [TARGET.tex ...] — a consonant doubled after repha.

Old printings double the consonant after र् (सूर्य्य, सर्व्व, धर्म्म, वर्द्धमान,
मर्द्दल); modern editions, and gold, write it single (सूर्य, सर्व, धर्म,
वर्धमान, मर्दल). Flags every word with र् + C + ् + C (C doubled), or with an
unaspirated stop doubling its aspirate (र्द्ध, र्त्थ, र्ग्घ, र्ब्भ, र्ज्झ, र्ड्ढ),
in the target texts (default: every text in the repos, gold included), and
proposes the single form. Genuine doubling after repha is very rare, so each
hit is a likely slip; the count of the single form in the corpus is the evidence.

Not flagged: र्च्छ (मूर्च्छा, आर्च्छत्: च्छ is the ordinary spelling of a medial छ,
and gold writes मूर्च्छ 30 times to मूर्छ 4), and र्द्धि from ऋद्धि (महर्द्धि,
परर्द्धिः, धनर्द्धि), told apart from vardh- (वर्द्धित, वर्द्धिनी) by the letter
after it. And कार्त्तिक(ेय), from कृत्तिका: its त्त is etymological, and the editor keeps
both कार्त्तिक and कार्तिक as written, not standardised (round B7, 2026-10-18).

Columns: single-form count, word, proposed, file:line, line.
"""
import sys, os, re, collections
import corpus
from proofreader.text import clean, WORD_RE

ASP = {'द': 'ध', 'त': 'थ', 'ग': 'घ', 'ब': 'भ', 'ज': 'झ', 'ड': 'ढ', 'क': 'ख', 'च': 'छ', 'ट': 'ठ', 'प': 'फ'}
DBL = re.compile('र्([क-ह])्(?=([क-ह]))')
everything = corpus.gold() + corpus.reference()
target = sys.argv[2:] or everything


RDDHI = re.compile('र्द्धि(?![तनष])')


def single(w):
    def f(m):
        a, b, i = m.group(1), m.group(2), m.start()
        if a == 'च' and b == 'छ' or a == 'द' and RDDHI.match(w, i) or i >= 2 and w.startswith('कार्त्तिक', i - 2):
            return m.group(0)
        return 'र्' if a == b or ASP.get(a) == b else m.group(0)
    return DBL.sub(f, w)


def words(f):
    for n, l in enumerate(open(os.path.join(corpus.ROOT, f), encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        for m in WORD_RE.finditer(l):
            yield n, l, clean(m.group(0))


count = collections.Counter(w for f in everything for _, _, w in words(f))
out = []
for f in target:
    for n, l, w in words(f):
        s = single(w)
        if s != w:
            out.append((count[s], w, s, f'{f}:{n}', l.strip()))
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in out:
        o.write('\t'.join(map(str, r)) + '\n')
print(len(out), 'hits in', len({r[3].rsplit(':', 1)[0] for r in out}), 'files')
