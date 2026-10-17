"""metrerepair.py OUT.json [--all] — one syllable-level edit that makes a failing verse scan.

Scans every gold verse the metre check rejects (with --all, also the ones
recorded correct in accepted.txt) and, word by word, tries one small edit:
a vowel's length, an anusvāra or visarga added or dropped, a consonant
doubled or undoubled, a virāma added or dropped (पङ्कित -> पङ्क्ति), one
akṣara or one conjunct cluster dropped (भूधराश्च -> भूधराः). An edit is kept
when the verse then scans, and ranked by how much it lowers the word's
proofreader score (score_word), or by corpus attestation.

Unlike metrefix.py, the new word need not be attested, so it reaches inside
long compounds. The price is noise: most hits are nonsense that happens to
scan (देहि -> हि). Read the line; the useful output is often the verse itself.
"""
import sys, os, json, re, collections
import corpus
from proofreader.text import parse_file, clean, WORD_RE
from proofreader.checks import _meter_findings, verse_id, verse_ok, score_word
from proofreader.session import load_accepted, skip_meter_files
from proofreader.meter import MeterChecker
from proofreader.index import Index

M = MeterChecker(); acc = load_accepted(); skip = skip_meter_files(); idx = Index.load()
ALL = '--all' in sys.argv
cnt = collections.Counter()
for f in set(corpus.gold()) | set(corpus.reference()):
    try:
        for u in parse_file(os.path.join(corpus.ROOT, f)):
            for ln in u.lines:
                cnt.update(w for w in (clean(m.group(0)).replace('-', '') for m in WORD_RE.finditer(ln.text)) if w)
    except Exception:
        pass
C='[क-हक़-य़]़?'
V='[अ-औॠॡ]'
UNIT=re.compile(f'{C}्|{C}|{V}|[ा-ौॢॣृॄ]|[ंःँ]|ऽ|.')
CONS=re.compile(f'^{C}$')
LONG={'ि':'ी','ी':'ि','ु':'ू','ू':'ु','ृ':'ॄ','ा':'','े':'','ो':'','':'ा'}
IV={'अ':'आ','आ':'अ','इ':'ई','ई':'इ','उ':'ऊ','ऊ':'उ'}
def variants(word):
    us=UNIT.findall(word); n=len(us)
    for i,u in enumerate(us):
        nxt=us[i+1] if i+1<n else ''
        if CONS.match(u):
            # vowel sign after it (or inherent a)
            m=nxt if re.match('^[ा-ौृॄ]$',nxt) else ''
            for a,b in LONG.items():
                if a==m and (a or b):
                    if a=='ा' and b=='': pass
                    if a in 'ेो': continue
                    yield 'len', ''.join(us[:i+1])+b+''.join(us[i+2 if m else i+1:])
            # geminate: C -> C्C
            yield 'gem', ''.join(us[:i])+u+'्'+''.join(us[i:])
        if u in IV: yield 'len', ''.join(us[:i])+IV[u]+''.join(us[i+1:])
        if u.endswith('्') and i>0 and us[i-1]==u: yield 'degem',''.join(us[:i])+''.join(us[i+1:])
        if u=='ं' : yield 'anus-', ''.join(us[:i])+''.join(us[i+1:])
        if u=='ः' : yield 'vis-', ''.join(us[:i])+''.join(us[i+1:])
        # anusvara after a vowel-final akshara
        if (CONS.match(u) or re.match('^[ा-ौ]$',u) or u in IV) and not re.match('^[ा-ौृॄंः्]$',nxt):
            yield 'anus+', ''.join(us[:i+1])+'ं'+''.join(us[i+1:])
        # delete one akshara (consonant + its vowel sign)
        if CONS.match(u) and not (i>0 and us[i-1].endswith('्')):
            j=i+1+(1 if re.match('^[ा-ौृॄ]$',nxt) else 0)
            if j<n and us[j] in 'ंः': j+=1
            yield 'del', ''.join(us[:i])+''.join(us[j:])
    if us and not us[-1] in 'ंः्' : yield 'vis+', word+'ः'
    for i,u in enumerate(us):
        nxt=us[i+1] if i+1<n else ''
        # virama+: drop an inherent a, making a conjunct (पङ्कित -> पङ्क्ति needs two steps; this covers Ca+C -> C्C)
        if CONS.match(u) and i+1<n and CONS.match(nxt):
            yield 'vir+', ''.join(us[:i])+u+'्'+''.join(us[i+1:])
        # virama-: C्C -> CaC
        if u.endswith('्') and i+1<n and CONS.match(nxt):
            yield 'vir-', ''.join(us[:i])+u[:-1]+''.join(us[i+1:])
        # drop a whole cluster+vowel (च in भूधराश्च, तु, हि ...), leaving visarga when a sibilant cluster ends a vowel
        if CONS.match(u) and i>0 and us[i-1].endswith('्'):
            j=i+1+(1 if re.match('^[ा-ौृॄ]$',nxt) else 0)
            k=i-1
            while k>0 and us[k-1].endswith('्'): k-=1
            rest=''.join(us[j:])
            yield 'delc', ''.join(us[:k])+rest
            if us[k] in ('श्','स्','ष्','र्'): yield 'delc', ''.join(us[:k])+'ः'+rest
    # move a vowel sign: Cि + C्C -> C्Cि  (पङ्कित -> पङ्क्ति)
    for i in range(n-2):
        if CONS.match(us[i]) and re.match('^[ि-ौ]$',us[i+1]) and CONS.match(us[i+2]) and (i+3>=n or not re.match('^[ा-ौ्]$',us[i+3])):
            yield 'mv', ''.join(us[:i])+us[i]+'्'+us[i+2]+us[i+1]+''.join(us[i+3:])
WTOK = re.compile(r'[\u0900-\u097f\u200c\u200d]+')
out = []
for f in sorted(set(corpus.gold()) - skip):
    try:
        units = parse_file(os.path.join(corpus.ROOT, f))
    except Exception:
        continue
    for u in units:
        if u.kind != 'verse':
            continue
        lines = [l.text for l in u.lines]
        if not _meter_findings(u, M, f) or (verse_id(lines) in acc and not ALL):
            continue
        fixes = []
        for li, l in enumerate(lines):
            for m in WTOK.finditer(l):
                w = m.group(0).replace('\u200c', '').replace('\u200d', '')
                seen = set()
                for kind, nw in variants(w) if len(w) > 1 else ():
                    if not nw or nw == w or nw in seen:
                        continue
                    seen.add(nw)
                    L2 = list(lines); L2[li] = l[:m.start()] + nw + l[m.end():]
                    if verse_ok(L2, M)[0]:
                        so, sn = score_word(w, idx)[0], score_word(nw, idx)[0]
                        if sn < so - 1.5 or (kind not in ('del', 'delc') and cnt[nw] >= 2 and cnt[nw] >= 3 * max(1, cnt[w])):
                            fixes.append(dict(line=u.lines[li].lineno, old=w, new=nw, kind=kind, gain=round(so - sn, 1),
                                              cold=cnt[w], cnew=cnt[nw]))
        out.append(dict(file=f, line=u.lines[0].lineno, text=lines, accepted=verse_id(lines) in acc,
                        fixes=sorted(fixes, key=lambda x: -x['gain'])))
M.save_cache()
json.dump(out, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
print(len(out), 'failing verses;', sum(bool(v['fixes']) for v in out), 'with a ranked fix')
