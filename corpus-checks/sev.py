"""sev.py ROUND.json OUT.json — score metre rows by how far off they are, so the
worst (a line 2+ syllables short: text missing or doubled) are reviewed first.
Mātrā differences count half; anuṣṭup lines are measured against 8/16."""
import json, re, collections, sys
R = json.load(open(sys.argv[1]))
def sev(r):
    n = r['note']
    pats = re.findall(r'([LG]+) \((\d+)\)', n)
    lens = [int(x) for _, x in pats]
    anu = 'nuṣṭup' in n
    m = re.search(r'line (\d+) has (\d+) mātrās \(the others have (\d+)\)', n)
    if m: return abs(int(m.group(2)) - int(m.group(3))) / 2, 'mātrā'
    m = re.search(r'line (\d+) has (\d+) syllables \(the others have (\d+)\)', n)
    if m: return abs(int(m.group(2)) - int(m.group(3))), 'syll'
    if anu and lens:
        exp = [16 if x > 11 else 8 for x in lens]
        return max(abs(a - b) for a, b in zip(lens, exp)), 'anuṣṭup'
    if 'unequal lengths' in n and lens:
        mode = collections.Counter(lens).most_common(1)[0][0]
        return max(abs(x - mode) for x in lens), 'len'
    if 'differs from the other lines' in n:
        return 0.5 * len(re.findall(r'syllable', n)), 'pattern'
    return 0.5, 'other'
out = collections.Counter()
for r in R:
    if r['rule'] != 'metre': continue
    s, k = sev(r); r['_sev'] = s; out[(s, k)] += 1
for k in sorted(out, reverse=True): print(k, out[k])
json.dump(R, open(sys.argv[2], 'w'), ensure_ascii=False)
