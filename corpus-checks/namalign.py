"""namalign.py NAMAVALI.tex STOTRAM.tex [OUT.tsv] — a nāmāvalī that is already in order, aligned
with its stotram: which names are missing, extra or spelled otherwise.

namastotra.py looks for each name a little ahead of the last one found, so one miss early on
(a long pūrvabhāga before the first name) throws every later name "out of order". Here each
name's stem (namastotra.stem, an initial vowel dropped) is found everywhere in the stotram's
letter stream (class nasal + virāma before a consonant read as anusvāra, svaras dropped), and
the longest chain of hits in the order of both texts (longest stems weigh most) anchors the
names. A name off the chain is looked for only between its two anchors: the nearest stretch
there by edit distance is what the stotram reads in its place. Stotram text between two
anchors that no name accounts for is reported too (a name the nāmāvalī may lack; often only
च, तथा, एव, the verse number or a phalaśruti).
Columns: kind (name / gap), n, name, stem, distance, stotram stretch, nāmāvalī line, stotram line.
"""
import bisect, os, re, sys
_argv = sys.argv; sys.argv = ['x', '/dev/null', '/dev/null']
from namastotra import stem, lev, names   # noqa: E402
sys.argv = _argv

SV = re.compile('[\u0951\u0952\u1cd0-\u1cff\ua8e0-\ua8ff]')
DEV = re.compile('[\u0900-\u0950\u0953-\u0963\u0970-\u097f]')
NAS = re.compile('[ङञणनम]्(?=[क-म])')


def norm(t):
    return NAS.sub('ं', SV.sub('', t))


def stream(path):
    chars, where = [], []
    for n, l in enumerate(open(path, encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = norm(re.sub(r'\\[a-zA-Z]+\*?', ' ', t))
        for ch in t:
            if DEV.match(ch) and ch not in '।॥ऽ' and not '०' <= ch <= '९':
                chars.append(ch)
                where.append(n)
    return ''.join(chars), where


def key(w):
    s = norm(stem(w))
    if s[:1] in 'अआइईउऊऋएऐओऔ' and len(s) >= 4:
        s = s[1:]
    return s


def chain(keys, text, cap=400):
    """Longest weighted chain of exact hits, increasing in name number and in stotram place."""
    pairs = []
    for i, s in enumerate(keys):
        if len(s) < 2:
            continue
        j, k = text.find(s), 0
        while j >= 0 and k < cap:
            pairs.append((j, i, len(s)))
            j, k = text.find(s, j + 1), k + 1
    pairs.sort(key=lambda p: (p[0], -p[1]))
    best = {}           # name -> (score, pair) of the best chain ending at that name's hit
    tree = [(0, None)] * (len(keys) + 1)   # Fenwick tree over name number: max (score, pair)

    def query(i):
        r = (0, None)
        while i > 0:
            r = max(r, tree[i], key=lambda x: x[0]); i -= i & -i
        return r

    def update(i, v):
        i += 1
        while i <= len(keys):
            if v[0] > tree[i][0]:
                tree[i] = v
            i += i & -i
    parent, ends = {}, []
    g = 0
    while g < len(pairs):            # hits at one stotram place cannot chain with each other
        h = g
        while h < len(pairs) and pairs[h][0] == pairs[g][0]:
            h += 1
        group = []
        for p in pairs[g:h]:
            j, i, L = p
            sc, pp = query(i)        # chains ending at names before i
            if pp is not None and pp[0] + pp[2] > j:
                sc, pp = 0, None     # overlaps the hit before: start afresh (rare)
            group.append(((sc + L, p), pp))
        for v, pp in group:
            parent[v[1]] = pp
            update(v[1][1], v)
            ends.append(v)
        g = h
    if not ends:
        return {}
    p = max(ends, key=lambda x: x[0])[1]
    out = {}
    while p is not None:
        out[p[1]] = p
        p = parent[p]
    # a name that also occurs earlier (in the pūrvabhāga, say) may anchor there: from the end
    # backwards, move each anchor to its stem's last place before the next anchor
    nxt = len(text)
    for i in sorted(out, reverse=True):
        j, _, L = out[i]
        k = text.rfind(keys[i], j, nxt)
        if k > j and k + L <= nxt:
            out[i] = (k, i, L)
        nxt = out[i][0]
    return out


def nearest(s, text, a, b):
    best = (len(s) + 1, a, 0)
    for i in range(a, max(a, b - 1) + 1):
        for L in (len(s) - 2, len(s) - 1, len(s), len(s) + 1, len(s) + 2):
            if L < 1 or i + L > b:
                continue
            d = lev(s, text[i:i + L])
            if d < best[0]:
                best = (d, i, L)
    return best


def align(nam, sto):
    nm = names(nam)
    keys = [key(w) for _, w in nm]
    text, where = stream(sto)
    lines = open(sto, encoding='utf-8').read().split('\n')
    anch = chain(keys, text)
    rows = []
    idx = sorted(anch)
    bounds = [(-1, 0)] + [(i, anch[i][0]) for i in idx] + [(len(nm), len(text))]
    ends = {i: anch[i][0] + anch[i][2] for i in idx}
    for (ia, pa), (ib, pb) in zip(bounds, bounds[1:]):
        a = ends.get(ia, 0) if ia >= 0 else (max(0, pb - 200) if ib < len(nm) else 0)
        b = pb
        free = list(range(ia + 1, ib))
        used = []
        for i in free:
            s = keys[i]
            if not s:
                continue
            d, j, L = nearest(s, text, a, b) if b > a else (len(s), a, 0)
            if L and d <= max(1, len(s) // 3):
                used.append((j, j + L))
            if d == 0:
                continue   # a short stem (गिरे → ग), there all the same
            rows.append(('name', i + 1, nm[i][1], s, d, text[j:j + L],
                         f'{os.path.relpath(nam)}:{nm[i][0]}',
                         lines[where[min(j, len(where) - 1)] - 1].strip()))
        if ia >= 0 and ib < len(nm):  # stotram text between two anchors left over by the names
            left, k = [], a
            for x, y in sorted(used):
                if x > k:
                    left.append((k, x))
                k = max(k, y)
            if b > k:
                left.append((k, b))
            for x, y in left:
                if y - x >= 6:
                    rows.append(('gap', ia + 1, nm[ia][1], '', y - x, text[x:y],
                                 f'{os.path.relpath(nam)}:{nm[ia][0]}',
                                 lines[where[x] - 1].strip()))
    return nm, anch, rows


if __name__ == '__main__':
    NAM, STO = sys.argv[1], sys.argv[2]
    nm, anch, rows = align(NAM, STO)
    out = open(sys.argv[3], 'w', encoding='utf-8') if len(sys.argv) > 3 else sys.stdout
    for r in rows:
        out.write('\t'.join(map(str, r)) + '\n')
    print(f'{len(nm)} names, {len(anch)} anchored in order, {sum(r[0] == "name" for r in rows)} off the chain, '
          f'{sum(r[0] == "gap" for r in rows)} stretches of stotram left over', file=sys.stderr)
