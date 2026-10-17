import sys, os, collections, csv
import corpus
from proofreader.index import Index, read_manifest, root_dir
from proofreader.text import parse_file
from proofreader.style import check_units
from proofreader import splitmodel
idx = Index.load()
model = splitmodel.load()
rej = splitmodel.rejected_pairs()
M = corpus.PADMA_M
skipm = corpus.skip_meter()
files = [f for f in corpus.gold() if f not in skipm]
w = csv.writer(open(sys.argv[1], 'w'), delimiter='\t')
w.writerow(['source', 'file', 'line', 'rule', 'text', 'suggestion', 'p'])
cnt = collections.Counter()
for rp in files:
    removed = idx.without([rp]) if rp != M else []
    try:
        for s in check_units(parse_file(os.path.join(root_dir(), rp)), idx):
            r = s.rule
            if 'split' in r or 'avagraha' in r:
                w.writerow(['rule', rp, s.lineno, r, s.word, s.replacement, '']); cnt['rule:'+r] += 1
        rows = splitmodel.candidate_rows([rp], idx, model, min_p=0.5, skip=rej)
        for row in rows:
            w.writerow(['model', rp, row['line'], 'split', row.get('current',''), row.get('proposed',''), row['note']]); cnt['model'] += 1
    finally:
        if removed: idx.restore(removed)
print(cnt)
