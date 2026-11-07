"""namchandas.py ORDER.tsv NAMAVALI.tex STOTRAM.txt SFIRST SLAST [OUT.tsv]
— judge a nāmāvalī's readings by its stotram's metre. Each name (as it now
stands in NAMAVALI.tex, paired line by line with ORDER.tsv, the hand-fixed
ocrorder.py output) is turned back to the stotram's form as namforms.py does.
Where it differs from the stotram text, it is put into the stotram verse in
place of the stretch it matches (nearest edit distance) and the verse is
scanned (verse-checker; anuṣṭup by the śloka rules) with the stotram's own
reading and with the nāmāvalī's.

Prints, per differing name: name no., ocr line, verse, nāmāvalī form, the
stotram stretch, metre with the stotram reading (ok/BAD), with the nāmāvalī
reading (ok/BAD), and the hint for the worse one. Then every stotram verse
that does not scan by itself (a slip in the stotram text, which a nāmāvalī
reading may mend). Names placed between exact hits (non-integer ORDER pos:
moved) are looked for in their verse; a name
with no close match there is listed as not found and not scanned."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
_argv = sys.argv; sys.argv = ['x', '/dev/null', '/dev/null']
from namastotra import lev
sys.argv = _argv
from proofreader.meter import MeterChecker, structural_check

ORDER, NAM, KK, SA, SB = sys.argv[1:6]
OUT = sys.argv[6] if len(sys.argv) > 6 else None
SA, SB = int(SA), int(SB)
DEV = re.compile('[ऀ-ॣ॰-ॿ]')


def norm(t):
    return re.sub('[ङञणनम]्(?=[क-म])', 'ं', t).replace('ॐ', 'ओं')


# the stotram as one letter string (as ocrorder.py builds it), each letter tagged
# with its verse and its half-verse line
kk = open(KK, encoding='utf-8').read().split('\n')
S, verse, line, ln, vlines = '', [], [], 0, {}
_first = re.search(r'॥\s*([०-९]+)॥', '\n'.join(kk[SA - 1:SB])).group(1)
v = int(_first.translate(str.maketrans('०१२३४५६७८९', '0123456789')))
for l in kk[SA - 1:SB]:
    l = norm(l.split(' var ')[0])
    for ch in l:
        if DEV.match(ch) and ch not in '।॥ऽ' and not '०' <= ch <= '९':
            S += ch; verse.append(v); line.append(ln)
    vlines.setdefault(v, []).append(ln)
    ln += 1
    if re.search(r'॥\s*[०-९]+॥', l):
        v += 1
S = list(S)

RULES = [('ायै', 'ा'), ('्वै', 'ू'), ('्यै', 'ी'), ('ये', 'ि'), ('वे', 'ु'), ('त्रे', 'ृ'), ('ते', '्'), ('दे', '्'),
         ('षे', 'ि'), ('से', '्'), ('ने', '्'), ('णे', '्'), ('ै', '')]


def nominative(w):
    w = norm(w).replace('~', '').replace(' ', '')
    for a, b in RULES:
        if w.endswith(a):
            return w[:-len(a)] + b
    return w


names = [m.group(1) for m in re.finditer(r'^(.*?)~नमः', open(NAM, encoding='utf-8').read(), re.M)]
rows = [l.rstrip('\n').split('\t') for l in open(ORDER, encoding='utf-8')]
assert len(names) == len(rows), (len(names), len(rows))

mc = MeterChecker()


def scan(text_by_line, v):
    lines = [''.join(text_by_line[i]) for i in vlines[v]]
    pats = mc.check(lines)['patterns']
    ok, hint = structural_check(pats)
    return ok, hint


def lines_of(s):
    d = {}
    for i, ch in enumerate(s):
        d.setdefault(line[i], []).append(ch)
    return d


ALLOW = {'ा': 'ा', 'ी': 'ी्', 'ि': 'ि', 'ु': 'ुू', 'ृ': 'ाृ'}
base = lines_of(S)
out, moved = [], []
for i, (w, r) in enumerate(zip(names, rows), 1):
    pos = float(r[0])
    g = nominative(w)
    core = g[:-1] if len(g) > 2 else g      # the last letter goes with sandhi: keep the stotram's
    if core and core[0] in 'अआइईउऊऋएऐओऔ':
        core = core[1:]                      # so does an initial vowel
    if pos.is_integer():
        span = range(max(0, int(pos) - 3), min(len(S), int(pos) + 40))
    else:                                    # moved or not in the stotram: search its verse
        vv = int(r[7]) or next(int(x[7]) for x in rows[i:] if int(x[7]))
        span = [k for k in range(len(S)) if verse[k] == vv]
    if not core:
        continue
    # a stretch must end where the stotram's next letter can be the name's last
    # (or a consonant can't follow): that keeps the stretch from cutting a syllable
    tail = lambda e: 0 if e >= len(S) or S[e] == g[-1] or not 'क' <= S[e] <= 'ह' else 0.5
    d0, _, _, s, L = min(((lev(core, ''.join(S[s:s + L])) + tail(s + L), abs(L - len(core)),
                           abs(s - pos), s, L)
                          for s in span for L in range(max(1, len(core) - 3), len(core) + 4)))
    if d0 == 0:
        continue
    if d0 * 3 > len(core):
        moved.append((i, r[1], r[7], w)); continue
    v = verse[s]
    new = S[:s] + list(core) + S[s + L:]
    # the substituted letters take the line of the stretch's start
    tags = line[:s] + [line[s]] * len(core) + line[s + L:]
    d = {}
    for ch, t in zip(new, tags):
        d.setdefault(t, []).append(ch)
    rok, rh = scan(base, v)
    bok, bh = scan(d, v)
    out.append((i, r[1], v, w, ''.join(S[s:s + L]), core, 'ok' if rok else 'BAD', 'ok' if bok else 'BAD',
                bh if not bok else rh))
res = ['\t'.join(map(str, o)) for o in out]
bad = []
for v in sorted(vlines):
    ok, h = scan(base, v)
    if not ok:
        bad.append('verse %d\t%s\t%s' % (v, ' / '.join(''.join(base.get(i, [])) for i in vlines[v]), h))
mc.save_cache()
text = '\n'.join(['# name\tocr\tverse\tnamavali\tstotram\tnam-core\tmetre(stotram)\tmetre(namavali)\thint'] + res
                 + ['', '# not found in the stotram (not scanned)'] + ['\t'.join(map(str, m)) for m in moved]
                 + ['', '# stotram verses that do not scan as they stand'] + bad) + '\n'
(open(OUT, 'w', encoding='utf-8').write(text) if OUT else sys.stdout.write(text))
print(len(out), 'differ;', sum(o[7] == 'BAD' and o[6] == 'ok' for o in out), 'break the metre;',
      sum(o[6] == 'BAD' and o[7] == 'ok' for o in out), 'mend it;', len(bad), 'stotram verses do not scan',
      file=sys.stderr)
