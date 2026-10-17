"""Split / avagraha consistency across the gold corpus.

For every place two words are written apart at a halanta (तत् सर्वं), look for
the same pair written joined (तत्सर्वं) anywhere else, and vice versa. For
every word, look for spellings that differ only in avagraha (वापि / वाऽपि).
Usage: python3 consistency.py OUT.tsv [extra files...]
"""
import sys, os, re, collections, csv
import corpus
from proofreader.text import parse_file, key, clean
from proofreader.index import read_manifest, root_dir

ROOT = root_dir()
files = corpus.gold() + sys.argv[2:]

CONS = re.compile('[\u0915-\u0939\u0958-\u095F]')
def syl(s):
    n = 0
    for i, c in enumerate(s):
        if 'अ' <= c <= 'औ' or c in 'ॠॡ':
            n += 1
        elif CONS.match(c) and not (i + 1 < len(s) and s[i + 1] == '्'):
            n += 1
    return n

split = collections.defaultdict(list)    # joined-key -> [(file, line, t1, t2, padabreak)]
joined = collections.defaultdict(list)   # key -> [(file, line, tok)]
avag = collections.defaultdict(lambda: collections.defaultdict(list))

for f in files:
    for u in parse_file(os.path.join(ROOT, f)):
        ws = [(clean(w), ln) for w, ln in u.words()]
        for i, (w, ln) in enumerate(ws):
            joined[key(w)].append((f, ln.lineno, w))
            if not w.startswith('ऽ'):
                avag[w.replace('ऽ', '')][w].append((f, ln.lineno))
            if i + 1 < len(ws) and w.endswith('्') and ws[i + 1][1] is ln:
                t2 = ws[i + 1][0]
                if t2.startswith('ऽ'):
                    continue
                pb = False
                if u.kind == 'verse':
                    txt = ln.text
                    pos = txt.find(w + ' ' + t2)
                    if pos < 0:
                        pos = txt.find(t2)
                    before = syl(' '.join(re.findall('[ऀ-ॿ]+', txt[:pos + len(w)])))
                    total = syl(' '.join(re.findall('[ऀ-ॿ]+', txt)))
                    pb = total >= 14 and abs(before - total / 2) < 0.6
                split[key(w + t2)].append((f, ln.lineno, w, t2, pb))

out = csv.writer(open(sys.argv[1], 'w'), delimiter='\t')
out.writerow(['kind', 'form_a', 'n_a', 'form_b', 'n_b', 'files', 'examples_a', 'examples_b'])
nsp = 0
for k, occ in split.items():
    occ_in = [o for o in occ if not o[4]]          # pāda-break splits are not a choice
    j = joined.get(k, [])
    if not occ_in or not j:
        continue
    nsp += 1
    a = f'{occ_in[0][2]} {occ_in[0][3]}'
    fs = sorted({o[0].split('/')[0] for o in occ_in} | {o[0].split('/')[0] for o in j})
    out.writerow(['split', a, len(occ_in), j[0][2], len(j), ','.join(fs),
                  '; '.join(f'{o[0]}:{o[1]}' for o in occ_in[:4]),
                  '; '.join(f'{o[0]}:{o[1]}' for o in j[:4])])
nav = 0
for base, forms in avag.items():
    if len(forms) < 2:
        continue
    fl = sorted(forms.items(), key=lambda t: -len(t[1]))
    nav += 1
    (fa, oa), (fb, ob) = fl[0], fl[1]
    fs = sorted({o[0].split('/')[0] for _, os_ in fl for o in os_})
    out.writerow(['avagraha', fa, len(oa), fb, len(ob), ','.join(fs),
                  '; '.join(f'{o[0]}:{o[1]}' for o in oa[:4]),
                  '; '.join(f'{o[0]}:{o[1]}' for o in ob[:4])])
print(len(files), 'files;', nsp, 'split/joined pairs;', nav, 'avagraha variants')
