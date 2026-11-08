"""changekind.py ROUND.json [DECISIONS_DIR] — sort a round's rows by the kind of change
(current → proposed), so a reviewer can take one kind at a time and accept it in bulk.
Families: 1 one letter misread (न→त), 2 dropped vowel sign, 3 dropped ं/ः/ऽ, 4 dropped virāma,
half-letter or repha, 5 vowel sign misread (े→ै), 6 words written apart, 7 different ending,
8 different word or several changes. Prints each family with its sub-kinds (the exact change)
and counts; with DECISIONS_DIR (flat decision JSONs), only the undecided rows.
`family(current, proposed)` -> (number, sub-kind) is used by review builders (group_c4.py)."""
import difflib, glob, json, os, sys, collections

MAT = set('ािीुूृेैोौ')
LABEL = {1: 'One letter misread', 2: 'Dropped vowel sign', 3: 'Dropped ं / ः / ऽ',
         4: 'Dropped virāma, half-letter or repha', 5: 'Vowel sign misread',
         6: 'Words written apart', 7: 'Different ending (case, number, sandhi)',
         8: 'Different word or several changes (recension?)'}


def cons(s):
    return len(s) == 1 and 'क' <= s <= 'ह'


def ops(a, b):
    return [(a[i1:i2], b[j1:j2]) for o, i1, i2, j1, j2 in
            difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o != 'equal']


def family(a, b):
    if a.replace(' ', '') == b.replace(' ', '').replace('्', '') or (' ' in b and a.replace(' ', '') == b.replace(' ', '')):
        return 6, 'written apart'
    if ' ' in b and ' ' not in a and len(ops(a.replace(' ', ''), b.replace(' ', ''))) <= 1 and \
            all(y.startswith('्') or y == '' or y in ('्', 'ं') for x, y in ops(a, b.replace(' ', '')) if not x):
        return 6, 'written apart'
    o = ops(a, b)
    if len(o) == 1:
        x, y = o[0]
        if cons(x) and cons(y): return 1, '%s→%s' % (x, y)
        if not x and y in MAT: return 2, '+' + y
        if not x and y.strip() in ('ं', 'ः'): return 3, '+' + y.strip()
        if not x and (y.startswith('्') or y.startswith('र्') or (len(y) == 2 and y[1] == '्')): return 4, '+' + y
        if x in MAT and y in MAT: return 5, '%s→%s' % (x, y)
        if not x and y == 'ऽ': return 3, '+ऽ'
        if x == 'ा' and not y: return 5, '-ा'
    if b[:-3] == a[:-3] or (len(o) == 1 and a.endswith(o[0][0]) and b.endswith(o[0][1])):
        return 7, ' / '.join('%s→%s' % (x or '∅', y or '∅') for x, y in o)
    return 8, ''


if __name__ == '__main__':
    rows = json.load(open(sys.argv[1]))
    rows = rows['rows'] if isinstance(rows, dict) else rows
    if len(sys.argv) > 2:
        done = {json.load(open(f))['id'] for f in glob.glob(os.path.join(sys.argv[2], '*.json'))}
        rows = [r for r in rows if r['id'] not in done]
    g = collections.defaultdict(collections.Counter)
    for r in rows:
        f, sub = family(r['current'], r['proposed']); g[f][sub] += 1
    for f in sorted(g):
        print('%d. %s · %d' % (f, LABEL[f], sum(g[f].values())))
        for sub, n in g[f].most_common():
            if sub: print('     %3d  %s' % (n, sub))
