"""namforms.py (run in a folder holding ocrorder.py output as order-fixed.tsv) — each name turned back from the dative to
the stotram's form (ायै→ा, C्यै→Cी, ये→ि, वे→ु, ते→त्, दे→द्, षे→िः, त्रे→ृ, से→स्, ने→न्)
and compared, letter by letter, with the stotram where order1000 placed it.
The last letter is not compared (sandhi). Prints every name that differs:
an OCR slip in the book, a slip in the reference, or a real variant."""
import re, sys, os
# usage: namforms.py ORDER.tsv STOTRAM.txt SFIRST SLAST  (ORDER.tsv: ocrorder.py output, hand-fixed)
ORDER, KKF, SA_, SB_ = sys.argv[1:5]
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ocrorder.py'), encoding='utf-8').read().split('items = []')[0]
sys.argv = ['ocrorder.py', '', '0', '0', KKF, SA_, SB_, '']
exec(_src)
from namastotra import lev
RULES = [('ायै', 'ा'), ('्यै', '़ी'), ('ये', 'ि'), ('वे', 'ु'), ('त्रे', 'ृ'), ('ते', '्'), ('दे', '्'),
         ('षे', 'ि'), ('से', '्'), ('ने', '्'), ('णे', '्'), ('ै', '')]
rows = [l.rstrip('\n').split('\t') for l in open(ORDER, encoding='utf-8')]
out = []
for i, r in enumerate(rows, 1):
    w = norm(r[2]); p = int(float(r[0])) if float(r[0]).is_integer() else None
    for a, b in RULES:
        if w.endswith(a):
            g = w[:-len(a)] + b.replace('़', ''); break
    else:
        g = w
    g = g.replace('ऽ', '')
    core = g[:-1] if len(g) > 2 else g
    if core and core[0] in 'अआइईउऊऋएऐओऔ':
        core = core[1:]; init = True
    else:
        init = False
    # find core in S at/near the recorded position (moved names: search whole verse)
    pos = int(float(r[0]))
    win = S[max(0, pos - 3): pos + len(core) + 60]
    k = win.find(core)
    ALLOW = {'ा': 'ा', 'ी': 'ी्', 'ि': 'ि', 'ु': 'ुू', 'ृ': 'ाृ'}
    nxt = win[k + len(core)] if k >= 0 and k + len(core) < len(win) else ''
    ok = k >= 0 and (g[-1] not in ALLOW or nxt in ALLOW[g[-1]])
    if not ok:
        j = S.find(core)
        best = min(range(max(0, pos - 3), min(len(S), pos + 40)), key=lambda k: lev(core, S[k:k + len(core)]))
        out.append((i, r[1], r[2], r[3], S[max(0, best - 1): best + len(core) + 2], lev(core, S[best:best + len(core)]), r[7]))
for o in out:
    print('\t'.join(map(str, o)))
print(len(out), 'differ', file=sys.stderr)
