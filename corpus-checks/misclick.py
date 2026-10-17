"""misclick.py ROUND.json DECISIONS_DIR — check a round's decisions before applying.

Run this before apply_round.py. It flags:
  stale    the decision's file/line/current text no longer matches its row
           (the page showed an older version of the row);
  edited   the reviewer typed a different proposal (verify it by eye, and
           for verse lines check that it still scans);
  mixed    the same change (current -> proposed) was accepted in one place
           and rejected in another: a likely mis-click, or a deliberate
           exception that needs an explicit sign-off;
  missing  rows left undecided.
"""
import sys, json, glob, collections

R = {r['id']: r for r in json.load(open(sys.argv[1]))}
D = {}
for f in glob.glob(sys.argv[2] + '/*.json') + glob.glob(sys.argv[2] + '/decisions/*.json'):
    d = json.load(open(f))
    d = d.get('data', d)
    D[d['id']] = d
n = collections.Counter()
by = collections.defaultdict(list)
for i, d in sorted(D.items()):
    r = R.get(i)
    if not r:
        print('unknown row', i); n['unknown'] += 1; continue
    if (d.get('file'), d.get('line'), d.get('current')) != (r['file'], r['line'], r['current']):
        print(f'stale   #{i} {r["file"]}:{r["line"]} row={r["current"]!r} decision={d.get("current")!r}'); n['stale'] += 1
    if d['status'] == 'accept' and d.get('proposed', r['proposed']) != r['proposed']:
        print(f'edited  #{i} {r["file"]}:{r["line"]} {r["proposed"]!r} -> {d["proposed"]!r}'); n['edited'] += 1
    by[(r['current'], r['proposed'])].append((i, d['status']))
for (cur, prop), ds in by.items():
    if len({s for _, s in ds}) > 1:
        print(f'mixed   {cur} -> {prop}: ' + ', '.join(f'#{i} {s}' for i, s in ds)); n['mixed'] += 1
left = sorted(set(R) - set(D))
if left:
    print(f'missing {len(left)} undecided: {left[:20]}{" ..." if len(left) > 20 else ""}')
print(dict(n), f'{len(D)} decided of {len(R)}')
