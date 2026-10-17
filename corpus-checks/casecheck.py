"""casecheck.py OUT.tsv [TARGET.tex ...] — a case ending out of step with its line.

Two signals, each reported with the proposed fix:

  sandhi  a word ending in -o (from -aḥ) before a voiceless consonant, where
          the language wants -aś/-as/-aḥ (भौमवारो च → भौमवारे च / भौमवारश्च).
          Reported only when the -e (locative) or -aḥ (nominative) form is a
          word found elsewhere in the corpus.
  list    in a line where two or more a-stem words share one case ending
          (locative -e, instrumental -ena, dative -āya, ...), a word with a
          different ending sits next to च / वा among them, and the same stem
          with the shared ending is found elsewhere in the corpus.

Neither proves an error (vocatives in -o, compounds and verbs look alike),
so every hit needs a reader. Words in accepted.txt are skipped.
"""
import sys, os, re, collections
import corpus
from proofreader.text import parse_file, clean, WORD_RE

target = sys.argv[2:] or corpus.gold()
VOICELESS = set('कखचछटठतथपफशषस')
# a-stem endings (masc./neut.), longest first
ENDS = [('ेषु', 'loc.pl'), ('ेभ्यः', 'dat.pl'), ('ानाम्', 'gen.pl'), ('ानां', 'gen.pl'), ('ाणाम्', 'gen.pl'), ('ाणां', 'gen.pl'),
        ('ेन', 'ins'), ('ेण', 'ins'), ('ाय', 'dat'), ('स्य', 'gen'), ('ात्', 'abl'), ('ाद्', 'abl'), ('ैः', 'ins.pl'),
        ('े', 'loc'), ('ः', 'nom'), ('ो', 'nom')]
FORM = {'loc': 'े', 'ins': 'ेन', 'dat': 'ाय', 'gen': 'स्य', 'abl': 'ात्', 'loc.pl': 'ेषु', 'ins.pl': 'ैः', 'gen.pl': 'ानां', 'nom': 'ः'}
LISTWORDS = {'च', 'वा', 'तथा', 'अथ'}


def parse(w):
    for e, c in ENDS:
        if w.endswith(e) and len(w) > len(e) + 1 and re.match('[क-ह]', w[-len(e) - 1]):
            return w[:-len(e)], c
    return None


def toks(t):
    return [clean(m.group(0)).replace('-', '') for m in WORD_RE.finditer(t.replace('\\mbox{}', ''))]


cnt = collections.Counter()
for f in sorted(set(target) | set(corpus.gold()) | set(corpus.reference())):
    try:
        for u in parse_file(os.path.join(corpus.ROOT, f)):
            for ln in u.lines:
                cnt.update(toks(ln.text))
    except Exception:
        pass
acc = {l.split()[0] for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt')) if l.strip() and not l.startswith('#')}

rows = []
for f in target:
    try:
        units = parse_file(os.path.join(corpus.ROOT, f))
    except Exception:
        continue
    for u in units:
        if u.kind != 'verse':
            continue
        for ln in u.lines:
            ws = [w for w in toks(ln.text) if w]
            ps = [parse(w) for w in ws]
            for i, w in enumerate(ws):
                if w in acc or len(w) < 4:
                    continue
                # sandhi: -o before a voiceless consonant
                if w.endswith('ो') and i + 1 < len(ws) and ws[i + 1][:1] in VOICELESS and ps[i] \
                        and not cnt[w[:-1] + 'ुः'] and not w.endswith('थो'):      # प्रभो (voc. of प्रभु), …रथो = …र् अथो
                    stem = w[:-1]
                    alts = [(stem + e, n) for e, n in (('े', 'loc'), ('ः', 'nom')) if cnt[stem + e]]
                    if alts:
                        best = max(alts, key=lambda a: cnt[a[0]])
                        rows.append(('sandhi', f, ln.lineno, w, best[0], f'-o before {ws[i + 1]}; {best[0]} ×{cnt[best[0]]}', ln.text.strip()))
                        continue
                # list: a different ending among words that share one, next to च/वा
                if not ps[i] or not any(x in LISTWORDS for x in ws[max(0, i - 1):i + 2]):
                    continue
                shared = collections.Counter(p[1] for j, p in enumerate(ps) if p and j != i)
                if not shared:
                    continue
                c, k = shared.most_common(1)[0]
                stem, mine = ps[i]
                if k < 2 or mine == c or c == 'nom' or (mine == 'nom' and w.endswith('ः')):
                    continue
                alt = stem + FORM[c]
                if cnt[alt] and cnt[w] <= 3:
                    rows.append(('list', f, ln.lineno, w, alt, f'{k} words in the line are {c}, this one is {mine}; {alt} ×{cnt[alt]}', ln.text.strip()))
with open(sys.argv[1], 'w') as o:
    for r in rows:
        o.write('\t'.join(map(str, r)) + '\n')
print(len(rows), 'hits', dict(collections.Counter(r[0] for r in rows)))
