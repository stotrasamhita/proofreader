"""apply_round.py ROUND.json DECISIONS_DIR — apply accepted rows (ZWNJ-tolerant),
append split labels, print what was skipped."""
import json, glob, sys, re, csv, os
import corpus
from proofreader import edits, splitmodel as sm
ROOT = corpus.ROOT
R = {r['id']: r for r in json.load(open(sys.argv[1]))}
D = [json.load(open(f)) for f in glob.glob(sys.argv[2] + '/*.json')]
rows, miss, labels = [], [], []
for d in D:
    r = dict(R[d['id']]); r['proposed'] = d['proposed']
    if r['rule'] in ('split', 'join') and len((r['proposed'] if r['rule'] == 'split' else r['current']).split(' ')) == 2:
        cur, prop = (r['current'], r['proposed']) if r['rule'] == 'split' else (r['proposed'], r['current'])
        st = d['status'] if r['rule'] == 'split' else ('reject' if d['status'] == 'accept' else 'accept')
        labels.append({'rule': 'split', 'current': cur, 'proposed': prop, 'status': st, 'file': r['file'], 'line': r['line']})
    if d['status'] != 'accept': continue
    line = open(os.path.join(ROOT, r['file']), encoding='utf-8').read().split('\n')[r['line'] - 1]
    if r['current'] not in line:
        m = re.search(''.join(re.escape(c) + '‌?' for c in r['current']), line)
        if not m: miss.append(r); continue
        r['current'] = m.group(0)
    rows.append(r)
p = sys.argv[1] + '.apply.csv'
with open(p, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, edits.FIELDS, extrasaction='ignore'); w.writeheader()
    for i, r in enumerate(rows, 1): w.writerow({**r, 'id': i, 'approve': 'y'})
applied, failed = edits.apply_rows(edits.read_csv(p), log=lambda *a: None)
sm.add_labels(labels)
print(f'applied {applied}, failed {len(failed)}, not found {len(miss)}, labels +{len(labels)}')
for m in miss: print('  MISSING', m['file'], m['line'], m['current'])
for f in failed: print('  FAILED', f)
