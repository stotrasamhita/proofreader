"""Find word-boundary vowel elisions that the house rule says to mark (or not).
Rule: mark ऽ except a+a; ā+a -> ाऽ ; a+ā / ā+ā -> ाऽऽ ; e/o+a -> ेऽ/ोऽ. Not inside compounds."""
import sys, os, re, collections, csv
import corpus
from proofreader.text import parse_file, clean
from proofreader.index import read_manifest, root_dir
files = corpus.gold() + sys.argv[2:]
skipm = corpus.skip_meter()
files = [f for f in files if f not in skipm]
toks = {f: [(clean(w), ln.lineno) for u in parse_file(os.path.join(root_dir(), f)) for w, ln in u.words()] for f in files}
lex = collections.Counter(w.replace('ऽ', '') for t in toks.values() for w, _ in t)
# independent words ending in a / ā that commonly precede an elided vowel
A_WORDS = set('च न एव इव अत्र तत्र यत्र सर्वत्र अथ इति_no'.split()) - {'इति_no'}
AA_WORDS = set('वा तथा यथा सदा यदा तदा कदा सर्वदा मया त्वया तया यया कया मा सा या का एषा तव मम'.split()) - {'तव', 'मम'}
A_WORDS |= {'तव', 'मम', 'मे_no'} - {'मे_no'}
def right_ok(r, base):
    # the right piece is a word gold writes on its own, far more often than
    # the whole token: वा+अपि (अपि everywhere), not या+अति (याति is the word)
    n = lex[r]
    return n >= 5 and n >= 2 * lex[base]
lex_g = collections.Counter(re.findall('[ऀ-ॿ]+', open(os.path.join(root_dir(), 'gita/words/gita-words.tex')).read().replace('ऽ', '')))
rows = []
for f, ts in toks.items():
    for w, ln in ts:
        if w.startswith('ऽ'):
            continue
        base = w.replace('ऽ', '')
        if lex_g.get(base):
            continue          # a word the Gita word-split text has whole
        for i in range(1, len(base) - 1):
            if base[i] != 'ा':
                continue
            left_a, left_aa, rest = base[:i], base[:i + 1], base[i + 1:]
            for left, lv in ((left_a, 'a'), (left_aa, 'ā')):
                if left not in (A_WORDS if lv == 'a' else AA_WORDS):
                    continue
                for rv, r in (('a', 'अ' + rest), ('ā', 'आ' + rest)):
                    if not right_ok(r, base):
                        continue
                    want = '' if (lv, rv) == ('a', 'a') else ('ऽ' if (lv, rv) == ('ā', 'a') else 'ऽऽ')
                    cand = base[:i + 1] + want + rest
                    rows.append((f, ln, w, cand, f'{left}+{r}', lv + '+' + rv))
# keep a token only if the reading is unambiguous (all parses give the same spelling)
by = collections.defaultdict(set)
info = {}
for f, ln, w, cand, parse, kind in rows:
    by[(f, ln, w)].add(cand); info.setdefault((f, ln, w), []).append((cand, parse, kind))
out = csv.writer(open(sys.argv[1], 'w'), delimiter='\t')
out.writerow(['file', 'line', 'current', 'proposed', 'parse', 'kind', 'ambiguous'])
c = collections.Counter()
for k, cands in by.items():
    f, ln, w = k
    amb = len(cands) > 1
    for cand, parse, kind in info[k]:
        if cand != w:
            out.writerow([f, ln, w, cand, parse, kind, 'yes' if amb else ''])
            c[(f.split('/')[0], 'amb' if amb else 'fix')] += 1
            break
print(sorted(c.items()))
