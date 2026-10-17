"""moved.py OUT.tsv [TARGET.tex ...] — a letter moved one place, inside a compound.

Flags a spot in a word where swapping two neighbouring letters (a consonant,
a half-consonant such as र्, a vowel sign) turns a sequence the corpus never
uses into one it uses often: हयाञ्छत्रुनिर्बहण, where निर्बहण occurs nowhere
else but निबर्हण occurs 125 times. Moving र् past ब changes two code points
at once, so neardup.py (one code point) cannot see it. And the slip sits
inside a long compound that is rare as a whole even when spelt right, so
whole-word checks cannot either. This check compares only a window of
letters around the swap, which works inside compounds.

A hit: the window (two letters either side of the swap) occurs at most once
in the corpus outside this word, and the swapped window at least 10 times and
10 times as often. Counts come from every text in the repos except the
unproofread -orig copies, which repeat their own slips. Words in accepted.txt
are skipped.

Order: swaps that move र् first (the commonest slip: the reph typed one
letter early or late), then by how common the swapped window is. The
suggested word is only the swap; the real fix can differ (सवर्तः here is
संवर्तः, the sage, not सर्वतः).
On gold (2026-10-17): 253 hits, 24 of them moving र्, with 4 real slips
among those 24 (निर्बहण, तोष्टुर्महति, जर्नादने, सवर्तः) and noise below.

Columns: swapped window count, word, its count, window, swapped window,
suggested word, file:line, line.
"""
import sys, os, re, collections
import corpus
from proofreader.text import parse_file, clean, WORD_RE

RARE, COMMON = 1, 10
target = sys.argv[2:] or corpus.gold()
accepted = {l.split('#')[0].strip() for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt'), encoding='utf-8')}
C = '[\u0915-\u0939\u0958-\u095f]\u093c?'
UNIT = re.compile(f'{C}्|{C}|[ा-ौॢॣ]|[ंःँ]|.')
CONS, MATRA, MARK = re.compile(f'^{C}$'), re.compile('^[ा-ौॢॣ]$'), re.compile('^[ंःँ]$')


def toks(t):
    return [w for w in (clean(m.group(0)).replace('-', '') for m in WORD_RE.finditer(t.replace('\\mbox{}', ''))) if w]


def wellformed(us):
    """vowel signs only after a full consonant, ं/ः not after a half-consonant or at the start"""
    for i, u in enumerate(us):
        prev = us[i - 1] if i else ''
        if MATRA.match(u) and not CONS.match(prev):
            return False
        if MARK.match(u) and (not prev or prev.endswith('्')):
            return False
    return True


cnt, where, line = collections.Counter(), {}, {}
tset = set(target)
for f in sorted(tset | set(corpus.gold()) | set(corpus.reference())):
    try:
        units = parse_file(os.path.join(corpus.ROOT, f))
    except Exception:
        continue
    for u in units:
        for ln in u.lines:
            for w in toks(ln.text):
                cnt[w] += 1
                if f in tset and w not in where:
                    where[w], line[w] = f'{f}:{ln.lineno}', ln.text.strip()

# candidate swaps, and the windows they need counted
cands, need = [], set()
for w in where:
    if cnt[w] > 2 or w in accepted or len(w) < 4:
        continue
    us = UNIT.findall(w)
    for i in range(len(us) - 1):
        a, b = us[i], us[i + 1]
        if a == b or MARK.match(a) or MARK.match(b):
            continue
        vs = us[:i] + [b, a] + us[i + 2:]
        if not wellformed(vs):
            continue
        lo, hi = max(0, i - 2), min(len(us), i + 4)
        win, sw = ''.join(us[lo:hi]), ''.join(vs[lo:hi])
        cands.append((w, win, sw, ''.join(vs)))
        need |= {win, sw}

# token-weighted substring counts of the needed windows
lens = sorted({len(s) for s in need})
sub = collections.Counter()
for w, c in cnt.items():
    seen = set()
    for n in lens:
        for j in range(len(w) - n + 1):
            s = w[j:j + n]
            if s in need and s not in seen:
                seen.add(s)
                sub[s] += c

rows = []
for w, win, sw, v in cands:
    own = cnt[w] * (win in w)
    if sub[win] - own <= RARE and sub[sw] >= COMMON and sub[sw] >= 10 * max(1, sub[win] - own):
        rows.append((sub[sw], w, cnt[w], win, sw, v, where[w], line[w]))
rows.sort(key=lambda r: ('र्' not in r[3] + r[4], -r[0]))   # a misplaced र् first
best = {}
for r in rows:                     # one row per word: its best swap
    best.setdefault(r[1], r)
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in best.values():
        o.write('\t'.join(map(str, r)) + '\n')
print(len(best), 'words with a letter moved one place')
