"""gate.py OUT.tsv — group split/join practice by LEFT word across gold + all your decisions.
A group is inconsistent when the same left word is written apart in some places and fused
(left + a gold word) in others. Prints groups with counts; examples in OUT."""
import sys, os, re, json, collections, glob
import corpus
from proofreader.text import parse_file, clean
from proofreader.index import read_manifest, root_dir
from proofreader import splitmodel as sm
ROOT = root_dir()
files = corpus.gold()
CONS = re.compile('[क-हक़-य़]')
def syl(s):
    return sum(1 for i, c in enumerate(s) if ('अ' <= c <= 'औ') or (CONS.match(c) and not (i + 1 < len(s) and s[i + 1] == '्')))
toks = []        # (file, line, word, next_word_or_None, linetext)
vocab = collections.Counter()
for f in files:
    for u in parse_file(os.path.join(ROOT, f)):
        ws = [(clean(w), ln) for w, ln in u.words()]
        for i, (w, ln) in enumerate(ws):
            vocab[w] += 1
            nxt = ws[i + 1][0] if i + 1 < len(ws) and ws[i + 1][1] is ln else None
            toks.append((f, ln.lineno, w, nxt, ln.text))
lefts = collections.Counter(w for f, n, w, nx, t in toks if w.endswith('्') and nx and not nx.startswith('ऽ'))
split = collections.defaultdict(list); fused = collections.defaultdict(list)
for f, n, w, nx, t in toks:
    if w.endswith('्') and nx and not nx.startswith('ऽ') and ('-' + w) not in t and (w + '-') not in t:
        split[w].append((f, n, w + ' ' + nx))
L = sorted(lefts, key=len, reverse=True)
for f, n, w, nx, t in toks:
    for l in L:
        if w.startswith(l) and len(w) > len(l) + 1:
            rest = w[len(l):]
            if vocab[rest] >= 2 and re.match('[क-ह]', rest) and ('-' + rest) not in t and '\\mbox' not in t \
               and syl(rest) >= 2 and not (l.endswith('न्') and rest[0] in 'नम') and '‌' not in w:
                fused[l].append((f, n, w)); break
dec = collections.defaultdict(lambda: [0, 0])
for x in map(json.loads, open(sm.LABELS)):
    dec[x['left']][x['label']] += 1
out = open(sys.argv[1], 'w')
G = []
for l in set(split) & set(fused):
    G.append((min(len(split[l]), len(fused[l])), l))
for _, l in sorted(G, reverse=True):
    d = dec.get(l, [0, 0])
    out.write('\t'.join([l, str(len(split[l])), str(len(fused[l])), f'dec split {d[1]} / joined {d[0]}',
        '; '.join(f'{f.split("/")[-1]}:{n} {s}' for f, n, s in split[l]),
        '; '.join(f'{f.split("/")[-1]}:{n} {s}' for f, n, s in fused[l])]) + '\n')
print(len(G), 'left words written both apart and fused')
