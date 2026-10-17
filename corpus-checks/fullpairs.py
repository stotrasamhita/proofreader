"""fullpairs.py OUT.tsv [all] — every word pair written in more than one way.

For each two adjacent words A B on one line (B starting with a consonant, so
joining needs no sandhi), look for the same sequence written joined (AB, one
token) or hyphenated (A-B) anywhere in gold. Unlike consistency.py this is not
limited to A ending in a halanta: it also finds compounds written apart
(राम नाम / रामनाम). \\mbox{} and ZWNJ count as joined. A space at the pāda break
of a verse line is not a choice and is ignored. With `all`, the non-gold texts
are scanned too and reported separately.
"""
import sys, os, re, collections
import corpus
from proofreader.text import parse_file, key, clean, WORD_RE
from proofreader.index import read_manifest, root_dir

ROOT = root_dir()
gold = corpus.gold()
CONS = re.compile('[\u0915-\u0939\u0958-\u095F]')


def syl(s):
    return sum(1 for i, c in enumerate(s) if ('अ' <= c <= 'औ') or (CONS.match(c) and not (i + 1 < len(s) and s[i + 1] == '्')))


def scan(files, forms):
    """forms[key] -> {'apart'|'hyphen'|'joined': [(file, line, text)]}"""
    for f in files:
        try:
            units = parse_file(os.path.join(ROOT, f))
        except Exception:
            continue
        for u in units:
            for ln in u.lines:
                t = ln.text.replace('\\mbox{}', '')
                ms = list(WORD_RE.finditer(t))
                total = syl(' '.join(m.group(0) for m in ms))
                for i, m in enumerate(ms):
                    w = clean(m.group(0))
                    forms[key(w)]['joined'].append((f, ln.lineno, w))
                    if i + 1 == len(ms):
                        continue
                    nx = clean(ms[i + 1].group(0))
                    sep = t[m.end():ms[i + 1].start()]
                    if not CONS.match(nx[0]):
                        continue
                    if re.fullmatch(r'\s+', sep):
                        kind = 'apart'
                        if u.kind == 'verse' and total >= 14:
                            before = syl(' '.join(x.group(0) for x in ms[:i + 1]))
                            if abs(before - total / 2) < 0.6:
                                continue          # pāda break
                    elif re.fullmatch(r'\s*-\s*', sep):
                        kind = 'hyphen'
                    else:
                        continue
                    forms[key(w + nx)][kind].append((f, ln.lineno, w + (' ' if kind == 'apart' else '-') + nx))


def report(forms, out, label):
    rows = []
    for k, d in forms.items():
        kinds = [x for x in ('apart', 'hyphen', 'joined') if d.get(x)]
        if len(kinds) < 2 or 'apart' not in kinds and 'joined' not in kinds:
            continue
        rows.append((k, d, kinds))
    rows.sort(key=lambda r: -min(len(r[1][x]) for x in r[2]))
    for k, d, kinds in rows:
        ex = lambda x: '; '.join(f'{f.split("/")[-1]}:{n} {s}' for f, n, s in d[x][:5])
        out.write('\t'.join([label, '/'.join(kinds)] + [f'{x}:{len(d.get(x, []))}' for x in ('apart', 'hyphen', 'joined')]
                            + [ex(x) if d.get(x) else '' for x in ('apart', 'hyphen', 'joined')]) + '\n')
    return rows


if __name__ == '__main__':
    out = open(sys.argv[1], 'w')
    G = collections.defaultdict(lambda: collections.defaultdict(list))
    scan(gold, G)
    rows = report(G, out, 'gold')
    c = collections.Counter(r[2] and '/'.join(r[2]) for r in rows)
    print(len(rows), 'pairs in gold written more than one way:', dict(c))
