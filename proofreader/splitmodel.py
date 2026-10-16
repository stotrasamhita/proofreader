"""A learned ranker for word splits (house style: consonant-final words are
written apart, but compounds stay joined).

The rule in style.split_word proposes splits only when the gold vocabulary
is sure. This model ranks every remaining junction (halanta + consonant
inside a token) by how likely the reviewer is to accept a split there. It is
trained on reviewer decisions (labels.jsonl: accepted/rejected splits) plus
the Virāṭa editor's practice (original vs proofread: junctions split vs kept),
plus the Gītā against its word-split twin (gita/words/gita-words.tex, same
line numbers): every junction there is a known word boundary or not.
Typical signals: after तद्/जगत्/श्रीमत् keep joined (compounds); after verb
forms like भवेत्/स्यात् and before particles like तु, split.
"""

import difflib
import json
import os
import pickle

from .index import root_dir, tool_dir
from .style import _CONSONANT, _INTERNAL
from .text import clean, key, parse_file

LABELS = os.path.join(tool_dir(), 'labels', 'split-labels.jsonl')
MODEL = os.path.join(tool_dir(), 'index', 'split-model.pkl')
PARTICLES = {'तु', 'च', 'हि', 'वै', 'एव', 'अपि', 'वा', 'न', 'इति', 'ते', 'मे', 'मां', 'त्वां', 'तं',
             'सः', 'तत्', 'यत्', 'सा', 'ताः', 'यदि', 'तदा'}
VIRATA = ('Mahabharatam/parvas/04-virāṭaparva-orig.tex', 'Mahabharatam/parvas/04-virāṭaparva.tex')
GITA = ('gita/gita.tex', 'gita/words/gita-words.tex')
_FINAL = str.maketrans({'द': 'त', 'ग': 'क', 'ड': 'ट', 'ब': 'प', 'ज': 'च'})


def _bucket(n):
    return 0 if n == 0 else 1 if n < 3 else 2 if n < 10 else 3 if n < 50 else 4


def features(left, right, whole, idx):
    lk, rk = key(left), key(right)
    lc = idx.words.get(lk, 0)
    f = {'Lend=' + left[-2:]: 1, 'Llen': min(len(lk), 12) / 12,
         'Lcnt%d' % _bucket(lc): 1, 'Rcnt%d' % _bucket(idx.words.get(rk, 0)): 1,
         'Rlen': min(len(rk), 20) / 20, 'R1=' + right[0]: 1, 'Rend=' + rk[-2:]: 1,
         'Rend3=' + rk[-3:]: 1, 'Rpart': 1 if rk in PARTICLES else 0,
         'Wcnt%d' % _bucket(idx.words.get(key(whole), 0)): 1,
         'pair%d' % _bucket(idx.pairs.get((lk, rk), 0)): 1,
         'internal': 1 if left[-2:] + right[0] in _INTERNAL else 0,
         'Lend_lp': max(-8, idx.char_logprobs(lk)[-1]) / 8 if lk else 0}
    if lc >= 20:
        f['L=' + lk] = 1
    return f


def junctions(w):
    """Split points: after a virama, before a consonant, not after ञ/ङ/ण."""
    return [i for i in range(2, len(w) - 1)
            if w[i - 1] == '्' and _CONSONANT.match(w[i]) and w[i - 2] not in 'ञङण']


def add_labels(decisions):
    """Append reviewer split decisions ({current, proposed, status}) to the
    label file, so every review round improves the model."""
    os.makedirs(os.path.dirname(LABELS), exist_ok=True)
    with open(LABELS, 'a', encoding='utf-8') as f:
        for d in decisions:
            parts = d['proposed'].split(' ')
            if 'split' in d['rule'] and len(parts) == 2 and d['status'] in ('accept', 'reject'):
                f.write(json.dumps({'left': parts[0], 'right': parts[1], 'whole': d['current'],
                                    'label': 1 if d['status'] == 'accept' else 0,
                                    'file': d['file'], 'line': d['line']}, ensure_ascii=False) + '\n')


def _final(p):
    """Voiced and voiceless final stops are one word end (यद् / यत्)."""
    return p[:-2] + p[-2].translate(_FINAL) + '्' if p.endswith('्') and len(p) >= 2 else p


def gita_labels(idx=None):
    """Labelled junctions from the Gītā: a junction in a gita.tex token is a
    word boundary when the word-split line has a pada ending there and the
    next pada starting there. Boundaries are label 1, except a joined न् + न/म
    (an assimilated त्/द्, as in तन्मे; a word ending in न् is written apart),
    which house style keeps joined; compound-internal junctions are label 0.
    Words written apart at a halanta are label 1."""
    import re
    from .text import WORD_RE
    g, w = (os.path.join(root_dir(), v) for v in GITA)
    if not (os.path.exists(g) and os.path.exists(w)):
        return []
    with open(w, encoding='utf-8') as f:
        wlines = [re.sub(r'(?<!\\)%.*', '', l) for l in f.read().split('\n')]
    out = []
    for u in parse_file(g):
        ws = u.words()
        for j, (t, ln) in enumerate(ws):
            t = clean(t)
            pads = [clean(p) for p in WORD_RE.findall(wlines[ln.lineno - 1])] if ln.lineno <= len(wlines) else []
            for i in junctions(t):
                if idx is not None and idx.words.get(key(t[:i]), 0) < 2:
                    continue
                left, right = _final(t[:i]), t[i:]
                bound = any(a.endswith('्') and len(a) > 2 and left.endswith(_final(a)) and right[:2] == b[:2]
                            for a, b in zip(pads, pads[1:]))
                nasal = t[i - 2] == 'न' and t[i] in 'नम'
                out.append({'left': t[:i], 'right': t[i:], 'whole': t, 'line': ln.lineno,
                            'label': 1 if bound and not nasal else 0})
            if t.endswith('्') and j + 1 < len(ws) and ws[j + 1][1] is ln:
                nxt = clean(ws[j + 1][0])
                out.append({'left': t, 'right': nxt, 'whole': t + nxt, 'line': ln.lineno, 'label': 1})
    return out


def _training(idx):
    X, y = [], []
    if os.path.exists(LABELS):
        with open(LABELS, encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                if r['file'] == GITA[0]:
                    continue                 # the word-split text decides the Gītā
                X.append(features(r['left'], r['right'], r['whole'], idx))
                y.append(r['label'])
    # features as the review page sees them: with the Gītā left out of the index
    removed = idx.without([GITA[0]])
    try:
        for r in gita_labels(idx):
            X.append(features(r['left'], r['right'], r['whole'], idx))
            y.append(r['label'])
    finally:
        idx.restore(removed)
    o, p = (os.path.join(root_dir(), v) for v in VIRATA)
    if os.path.exists(o) and os.path.exists(p):
        a = [clean(w) for u in parse_file(o) for w, _ in u.words()]
        b = [clean(w) for u in parse_file(p) for w, _ in u.words()]
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op == 'equal':
                for w in a[i1:i2]:
                    for i in junctions(w):
                        if idx.words.get(key(w[:i]), 0) >= 2:
                            X.append(features(w[:i], w[i:], w, idx))
                            y.append(0)
                            break
            elif (op == 'replace' and i2 - i1 == 1 and j2 - j1 == 2
                  and a[i1] == b[j1] + b[j1 + 1] and b[j1].endswith('्')):
                X.append(features(b[j1], b[j1 + 1], a[i1], idx))
                y.append(1)
    return X, y


def train(idx):
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    X, y = _training(idx)
    dv = DictVectorizer()
    clf = LogisticRegression(C=1.0, max_iter=2000, class_weight='balanced')
    clf.fit(dv.fit_transform(X), y)
    os.makedirs(os.path.dirname(MODEL), exist_ok=True)
    with open(MODEL, 'wb') as f:
        pickle.dump((dv, clf), f)
    return len(y), sum(y)


def load():
    with open(MODEL, 'rb') as f:
        return pickle.load(f)


def best_split(w, idx, model):
    """(probability, left, right) of the most likely split of token w, or None."""
    dv, clf = model
    cands = []
    for i in junctions(w):
        left, right = w[:i], w[i:]
        if idx.words.get(key(left), 0) < 2 or len(key(right)) < 2:
            continue
        cands.append((left, right))
    if not cands:
        return None
    probs = clf.predict_proba(dv.transform([features(l, r, w, idx) for l, r in cands]))[:, 1]
    p, (left, right) = max(zip(probs, cands), key=lambda t: t[0])
    return float(p), left, right


def candidate_rows(paths, idx, model, min_p=0.3, skip=()):
    """Edit rows (see edits.py) for likely splits in the given root-relative
    files, most likely first. `skip` holds (file, token) pairs already
    rejected by a reviewer."""
    import collections
    from types import SimpleNamespace
    from .edits import style_rows
    from .style import _MARKS_RE
    from .text import WORD_RE
    rows = []
    for rp in paths:
        ap = os.path.join(root_dir(), rp)
        found = []
        for u in parse_file(ap):
            for line in u.lines:
                seen = collections.Counter()
                for m in WORD_RE.finditer(line.text):
                    w = m.group(0)
                    occ = seen[w]
                    seen[w] += 1
                    if _MARKS_RE.search(w) or (rp, w) in skip:
                        continue
                    r = best_split(w, idx, model)
                    if not r or r[0] < min_p:
                        continue
                    p, left, right = r
                    found.append(SimpleNamespace(
                        text=w, occ=occ, line=line.lineno, path=rp, join_next=0, mechanical=False,
                        suggestion=left + ' ' + right, p=p,
                        reasons=[f'split: model {p:.0%} likely' + (' (low confidence)' if p < 0.5 else '')]))
        rows += style_rows(found, ap)
    prob = lambda r: int(r['note'].split('model ')[1].split('%')[0])
    rows.sort(key=lambda r: (-prob(r), r['file'], int(r['line'])))
    return rows


def rejected_pairs():
    if not os.path.exists(LABELS):
        return set()
    with open(LABELS, encoding='utf-8') as f:
        return {(r['file'], r['whole']) for r in map(json.loads, f) if r['label'] == 0}
