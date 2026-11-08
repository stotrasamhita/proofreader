"""apply_round.py ROUND.json DECISIONS_DIR — apply accepted rows (ZWNJ-tolerant),
append split labels, print what was skipped.

A whole-verse row (has `lines`, and `current`/`proposed` hold one pāda per
line) is applied pāda by pāda, each on its own line. If the reviewer changed
the number of pādas, the row is reported for a hand edit instead.

`proof.py apply` calls apply() directly.
"""
import json, glob, sys, re, csv, os
import corpus
from proofreader import edits, splitmodel as sm
ROOT = corpus.ROOT


def split_labels(R, D):
    """Split-model labels from split/join decisions (accepted or rejected)."""
    labels = []
    for d in D:
        r = dict(R[d['id']]); r['proposed'] = d['proposed']
        if r['rule'] in ('split', 'join') and len((r['proposed'] if r['rule'] == 'split' else r['current']).split(' ')) == 2:
            cur, prop = (r['current'], r['proposed']) if r['rule'] == 'split' else (r['proposed'], r['current'])
            st = d['status'] if r['rule'] == 'split' else ('reject' if d['status'] == 'accept' else 'accept')
            labels.append({'rule': 'split', 'current': cur, 'proposed': prop, 'status': st, 'file': r['file'], 'line': r['line']})
    return labels


def plan(R, D):
    """Resolve decisions against the files. Returns (rows to apply, rows not
    found or needing a hand edit, split labels)."""
    rows, miss, todo = [], [], []
    labels = split_labels(R, D)
    for d in D:
        r = dict(R[d['id']]); r['proposed'] = d['proposed']
        if d['status'] != 'accept': continue
        if 'lines' in r:
            cur, prop = r['current'].split('\n'), r['proposed'].split('\n')
            if len(cur) != len(prop) or len(cur) != len(r['lines']):
                miss.append({**r, 'current': f"pāda count changed ({len(cur)} -> {len(prop)}): edit by hand"}); continue
            for n, c, q in zip(r['lines'], cur, prop):
                if c != q: todo.append({**r, 'line': n, 'current': c, 'proposed': q})
            continue
        todo.append(r)
    for r in todo:
        line = open(os.path.join(ROOT, r['file']), encoding='utf-8').read().split('\n')[r['line'] - 1]
        if r['current'] not in line:
            m = re.search(''.join(re.escape(c) + '‌?' for c in r['current']), line)
            if not m: miss.append(r); continue
            r['current'] = m.group(0)
        rows.append(r)
    return rows, miss, labels


def apply(R, D, csv_path):
    """R: id -> row, D: list of decisions. Writes the files and the labels;
    returns (applied, failed, miss, labels)."""
    rows, miss, labels = plan(R, D)
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, edits.FIELDS, extrasaction='ignore'); w.writeheader()
        for r in rows: w.writerow({**r, 'approve': 'y'})
    applied, failed = edits.apply_rows(edits.read_csv(csv_path), log=lambda *a: None)
    sm.add_labels(labels)
    return applied, failed, miss, labels


if __name__ == '__main__':
    R = {r['id']: r for r in json.load(open(sys.argv[1]))}
    D = [json.load(open(f)) for f in glob.glob(sys.argv[2] + '/*.json')]
    applied, failed, miss, labels = apply(R, D, sys.argv[1] + '.apply.csv')
    print(f'applied {applied}, failed {len(failed)}, not found {len(miss)}, labels +{len(labels)}')
    for m in miss: print('  MISSING', m['file'], m['line'], m['current'])
    for f in failed: print('  FAILED', f)
