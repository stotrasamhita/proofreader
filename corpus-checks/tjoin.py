"""tjoin.py OUT.tsv [TARGET.tex ...] — a free word in -त् run into a following त/थ-word.

House style writes a consonant-final word apart from the next (स्यात् त्वद्भक्तिमतां).
The split check in style.py leaves त्त/त्थ alone unless the exact pair is attested
apart, because the cluster is far more often inside a word (तत्त्व, महत्तत्त्वं), so
these junctions were never offered for splitting. This check looks only at words
that begin with a free word in -त् (verbs: स्यात्, भवेत्, कुर्यात्, पठेत्, भजेत्,
धारयेत्, भूयात्, अभवत्; ablatives in -आत्: तस्मात्, पश्चात्, कोपात्, दूरात्, पुरात्,
सम्भ्रमात्; pronouns and particles: तत्, यत्, एतत्, सर्वमेतत्, चेत्, यावत्, तावत्,
किञ्चित्, कश्चित्, काचित्, काश्चित्, विधिवत्) followed by a त- or थ-word,
and reports the split form.

Not flagged: compounds and fixed forms written joined in gold (तत्त्व, तत्तद्,
तत्तन्, तत्तुल्य, पश्चात्ताप, the Virāṭa यत्ता “ready”, names such as यत्तदीया and
यत्तच्छब्दस्वरूपिणी), and anything in accepted.txt.

Columns: joined, proposed, file:line, line.
"""
import sys, os, re
import corpus
from proofreader.text import clean, WORD_RE

target = sys.argv[2:] or corpus.gold()
accepted = {l.split('#')[0].strip() for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt'), encoding='utf-8')}
FREE = ['सर्वमेतत्', 'एतत्', 'तत्', 'यत्', 'स्यात्', 'भवेत्', 'कुर्यात्', 'पठेत्', 'भजेत्', 'धारयेत्', 'भूयात्',
        'सोऽभवत्', 'अभवत्', 'आसीत्', 'तस्मात्', 'पश्चात्', 'कोपात्', 'दूरात्', 'पुरात्', 'सम्भ्रमात्', 'चेत्',
        'यावत्', 'तावत्', 'किञ्चित्', 'कश्चित्', 'काचित्', 'काश्चित्', 'विधिवत्']
KEEP = ('तत्त्व', 'तत्तद', 'तत्तत्', 'तत्तन्', 'तत्तुल्य', 'पश्चात्ताप', 'यत्ता', 'यत्तः', 'यत्तदीया',
        'यत्तच्छब्द', 'तत्त्र')

out = []
for f in target:
    for n, l in enumerate(open(os.path.join(corpus.ROOT, f), encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        for m in WORD_RE.finditer(re.sub(r'(?<!\\)%.*', '', l)):
            w = clean(m.group(0))
            if w in accepted or w.startswith(KEEP):
                continue
            p = next((p for p in FREE if w.startswith(p) and len(w) > len(p) + 1 and w[len(p)] in 'तथ'), None)
            if p:
                out.append((w, p + ' ' + w[len(p):], f'{f}:{n}', l.strip()))
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in out:
        o.write('\t'.join(r) + '\n')
print(len(out), 'joined')
