"""Compounds written apart: a bare a-stem (ends in a consonant with inherent a,
no case ending) followed by another word, where either the joined form is in
gold, or the stem never stands alone anywhere in gold. Skips names-lists
(hyphen/= joined) and prose-ish Hindi files."""
import sys, os, re, collections, csv
import corpus
from proofreader.text import parse_file, clean, key
from proofreader.index import read_manifest, root_dir
ROOT = root_dir()
skipm = corpus.skip_meter()
files = [f for f in corpus.gold() if f not in skipm]
C = re.compile('[क-ह]$')
toks = {}
lex = collections.Counter()
for f in files:
    ts = []
    for u in parse_file(os.path.join(ROOT, f)):
        if u.kind != 'verse': continue
        ws = u.words()
        for i, (w, ln) in enumerate(ws):
            w = clean(w); ts.append((w, ln.lineno, ln.text)); lex[key(w)] += 1
    toks[f] = ts
# vocatives / indeclinables that legitimately end in bare a
OK = set('च न एव इव अथ अत्र तत्र यत्र सर्वत्र तव मम सह विना पुनः राम कृष्ण देव नृप राजन् विप्र भगवन् मुने वत्स प्रभो हर शिव विष्णो पार्थ तात'.split())
out = []
for f, ts in toks.items():
    for (a, n, text), (b, n2, _) in zip(ts, ts[1:]):
        if n != n2 or not C.search(a) or a in OK or len(a) < 3: continue
        if (a + ' ' + b) not in text: continue           # hyphen / macro between
        j = key(a + b); alone = lex[key(a)]
        infl = re.search('(ेन|स्य|ाय|त्र|ैव|ेव|ेद|ाम|ाथ|ाच|त्य|न्त|य|व|ण|स|च|ह|न्न)$', a)
        final = re.match('(वि)?(वर्जित|सहित|समन्वित|संयुत|समायुक्त|युक्त|पूर्वक|परायण|रहित|विहीन|हीन|सम्पन्न|परिवृत|आवृत|कृत|भूषित|शोभित|प्रिय)', b)
        if (lex[j] >= 1 and not infl and alone <= 3) or (final and not infl and alone <= 3):
            out.append((f, n, a + ' ' + b, a + b, f"joined form in gold ×{lex[j]}; '{a}' stands alone ×{alone} in gold", text.strip()))
w = csv.writer(open(sys.argv[1], 'w'), delimiter='\t'); w.writerows(out)
print(len(out), collections.Counter(o[0].split('/')[0] for o in out))
