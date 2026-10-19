"""freeword.py OUT.tsv [TARGET.tex ...] — a consonant-final word gold writes on its own, run into the next.

House style writes a word that ends in a consonant apart from the next word
(साक्षाद् रामायणात्मना, भवेद् यदि, तान् सर्वान् मोचयामि). style.py splits such
tokens, but at clusters that are usually word-internal (द्य, द्व, द्र, त्त, त्स,
न्न, न्म …) it waits for the exact pair to be attested apart, so a rare
right-hand word is never split. This check keys on the left-hand word instead:
L (ending in a virama) is free when gold has it as a token of its own at least
4 times and at least 4 times as often as run into a following known word. Each
target token (default: gold) that splits as free L + known R is reported.

Words that end in a vowel are not checked: before a consonant they cannot fuse
without a vowel sandhi (राजावदत् is राजा + अवदत्), so gold has none to split.

It is a candidate list, to be read: about a third of the hits are real. Drop
- inflected single words that happen to split (भवान्या, जपन्तं, महान्तौ, पठन्ते);
- compounds (स्वयम्भू, किम्पुरुष, महत्तत्त्व, सकृत्स्मरण, केशान्ते "at the hair-end");
- -न् doubled before the next word's vowel (राजन्नेतावत्, पश्यन्नात्मनि), which must be
  written joined, and त्→न् nasal sandhi (घोरान्मुच्यते), which gold keeps joined;
- त् + ह = द्ध (कुर्याद्धरिः), which must be written joined.

Columns: joined, proposed split, S (L alone), J (L joined), file:line, line.
"""
import sys, os, re, collections
import corpus
from proofreader.text import clean, WORD_RE

target = sys.argv[2:] or corpus.gold()
accepted = {l.split('#')[0].strip() for l in open(os.path.join(corpus.HERE, '..', 'accepted.txt'), encoding='utf-8')}
SUFFIX = {'तं', 'ते', 'तौ', 'तु', 'ता', 'तः', 'ती', 'या', 'यैः', 'यां', 'त्वाद्', 'तम्'}


def tokens(f):
    for n, l in enumerate(open(os.path.join(corpus.ROOT, f), encoding='utf-8'), 1):
        if l.lstrip().startswith('%'):
            continue
        t = re.sub(r'(?<!\\)%.*', '', l)
        t = re.sub(r'\\-|\\footnotemark(\{\})?', '', t)
        for m in WORD_RE.finditer(t):
            w = clean(m.group(0))
            if w:
                yield n, w, l.strip()


def points(w):
    """Split points after a virama, before a consonant; never after ञ ङ ण
    (assimilated nasals: धनञ्जयः, शङ्कर)."""
    for i in range(3, len(w) - 1):
        if w[i - 1] == '्' and 'क' <= w[i] <= 'ह' and w[i - 2] not in 'ञङण':
            yield i


G = collections.Counter()
for f in corpus.gold():
    for _, w, _ in tokens(f):
        G[w] += 1
R = collections.Counter()
for f in corpus.reference():
    try:
        for _, w, _ in tokens(f):
            R[w] += 1
    except (OSError, UnicodeDecodeError):
        pass
J = collections.Counter()
for w, c in G.items():
    for i in points(w):
        if G[w[i:]] >= 2:
            J[w[:i]] += c


def known(r):
    return G[r] >= 2 or any(G[r[:k]] >= 3 for k in range(3, len(r)))


out = []
for f in target:
    for n, w, l in tokens(f):
        if w in accepted or G[w] > 4 or R[w] >= 3:
            continue
        for i in points(w):
            a, b = w[:i], w[i:]
            if b in SUFFIX or len(b) < 3:
                continue
            if G[a] >= 4 and G[a] >= 4 * J[a] and known(b):
                out.append((w, f'{a} {b}', str(G[a]), str(J[a]), f'{f}:{n}', l))
                break
with open(sys.argv[1], 'w', encoding='utf-8') as o:
    for r in out:
        o.write('\t'.join(r) + '\n')
print(len(out), 'candidates')
