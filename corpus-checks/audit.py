"""audit.py ROUND.json=DECISIONS_DIR ... — cross-check every past decision.

1. the same junction decided both ways in different places;
2. a decided line that no longer carries the decided form (a later edit undid it);
3. a decided form whose opposite still stands elsewhere in gold.
"""
import json, glob, collections, re, os, sys
import corpus
ROOT = corpus.ROOT
RD = [a.split('=', 1) for a in sys.argv[1:]]
D = []   # (round, id, file, line, cur, prop, status, final)
for rf, dd in RD:
    R = {r['id']: r for r in json.load(open(rf))}
    for f in glob.glob(dd + '/*.json') + glob.glob(dd + '/decisions/*.json'):
        d = json.load(open(f)); d = d.get('data', d); r = R[d['id']]
        fin = d['proposed'] if d['status'] == 'accept' else r['current']
        D.append(dict(round=os.path.basename(rf)[6:-5], id=d['id'], file=r['file'], line=r['line'], cur=r['current'], prop=d['proposed'],
                      status=d['status'], final=fin, section=r.get('section', '')))
print(len(D), 'decisions')
# 1. same junction decided both ways: key = text with spaces/ZWNJ/ऽ removed; outcome = written form
def k(s): return re.sub('[ ‌]', '', s)
by = collections.defaultdict(list)
for d in D:
    if k(d['cur']) == k(d['prop']) and ' ' in (d['cur'] + d['prop']):      # pure split/join row
        # pair = the junction(s) that differ
        by[k(d['cur'])].append(d)
print('\n=== 1. Same word decided both ways (different places) ===')
n1 = 0
for key, ds in by.items():
    outs = {d['final'] for d in ds}
    if len(outs) > 1:
        n1 += 1
        print(key, '::', ' | '.join(f"{d['final']} [{d['round']}#{d['id']} {d['status'][:3]} {d['file'].split('/')[-1][:18]}:{d['line']}]" for d in ds))
print(n1, 'conflicts')
# 2. decision vs current text: does the decided final form still stand, and is the opposite form present elsewhere in gold?
fs = corpus.gold()
T = {f: open(os.path.join(ROOT, f), encoding='utf-8').read().split('\n') for f in fs}
print('\n=== 2. Decided line no longer has your decided form ===')
n2 = 0
for d in D:
    if d['file'] not in T or d['line'] > len(T[d['file']]): continue
    l = T[d['file']][d['line'] - 1].replace('‌', '')
    if d['final'].replace('‌', '') not in l:
        n2 += 1; print(f"{d['round']}#{d['id']} {d['status']} {d['file'].split('/')[-1]}:{d['line']} decided '{d['final']}' — line now: {l.strip()[:80]}")
print(n2)
print('\n=== 3. Decided form vs the opposite form elsewhere in gold ===')
n3 = 0; done = set()
for key, ds in by.items():
    fin = {d['final'] for d in ds}
    if len(fin) > 1: continue
    f0 = fin.pop(); opp = [d['cur'] if d['final'] == d['prop'] else d['prop'] for d in ds][0]
    if f0 == opp or key in done: continue
    done.add(key)
    hits = []
    for f, L in T.items():
        for n, l in enumerate(L, 1):
            if l.lstrip().startswith('%'): continue
            ll = l.replace('‌', '')
            if re.search(r'(?<![ऀ-ॿ])' + re.escape(opp) + r'(?![ऀ-ॿ])', ll) and not re.search(re.escape(opp.replace(' ', '-')), ll):
                hits.append(f"{f.split('/')[-1]}:{n}")
    if hits:
        n3 += 1; print(f"you chose '{f0}' ({', '.join(d['round']+'#'+str(d['id']) for d in ds)}) — '{opp}' still at: {'; '.join(hits[:5])}")
print(n3)
