"""The gold index: word and character n-gram statistics over proofread text.

Per-file word counts are kept so any gold file can be checked against the
index *minus itself* (leave-one-out); otherwise a gold file would vouch for
its own errors.
"""

import glob
import math
import gzip
import hashlib
import os
import pickle
import subprocess
from collections import Counter

from .text import char_ngrams, key, parse_file

NGRAM_SIZES = (1, 2, 3, 4, 5)   # 3/4 for novelty; all orders feed the char LM
LM_ORDER = 5
LM_DISCOUNT = 0.75
INDEX_VERSION = 2


def root_dir():
    """The StotraSamhita root: the parent of the proofreader directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tool_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rel(path):
    return os.path.relpath(os.path.abspath(path), root_dir())


def read_manifest(path=None):
    """Expand gold.txt into a sorted list of root-relative file paths."""
    path = path or os.path.join(tool_dir(), 'gold.txt')
    include, exclude = set(), set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            target = exclude if line.startswith('-') else include
            pattern = os.path.join(root_dir(), line.lstrip('-').strip())
            target.update(rel(p) for p in glob.glob(pattern, recursive=True))
    return sorted(include - exclude)


def file_words(path):
    """Counter of word keys in one file."""
    return Counter(key(w) for u in parse_file(path) for w, _ in u.words())


def _sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def _git_rev(path):
    try:
        return subprocess.run(['git', '-C', os.path.dirname(path), 'rev-parse', '--short', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ''


def deletes(k):
    """All strings obtained by deleting one character (SymSpell-style)."""
    return {k[:i] + k[i + 1:] for i in range(len(k))}


class Index:
    def __init__(self):
        self.version = INDEX_VERSION
        self.words = Counter()           # key -> count over gold
        self.forms = {}                  # key -> most common surface form
        self.ngrams = {n: Counter() for n in NGRAM_SIZES}
        self.ctx_total = Counter()       # context h -> sum of counts of h+x
        self.ctx_types = Counter()       # context h -> number of distinct x seen after h
        self.files = {}                  # rel path -> {'sha', 'rev', 'words': Counter}
        self._deletes = None

    # -- building -----------------------------------------------------------

    @classmethod
    def build(cls, paths, log=print):
        idx = cls()
        form_counts = {}
        for p in paths:
            ap = os.path.join(root_dir(), p)
            wc = Counter()
            for u in parse_file(ap):
                for w, _ in u.words():
                    k = key(w)
                    wc[k] += 1
                    form_counts.setdefault(k, Counter())[w] += 1
            idx.files[p] = {'sha': _sha(ap), 'rev': _git_rev(ap), 'words': wc}
            idx._add(wc, +1)
        idx.forms = {k: c.most_common(1)[0][0] for k, c in form_counts.items()}
        log(f'indexed {len(paths)} files, {sum(idx.words.values()):,} words, '
            f'{len(idx.words):,} distinct keys')
        return idx

    def _add(self, wc, sign):
        self._lp_cache = {}
        for k, c in wc.items():
            self.words[k] += sign * c
            d = sign * c
            for n in NGRAM_SIZES:
                grams = self.ngrams[n]
                for g in char_ngrams(k, n):
                    old = grams[g]
                    grams[g] = old + d
                    h = g[:-1]
                    self.ctx_total[h] += d
                    if old <= 0 < old + d:
                        self.ctx_types[h] += 1
                    elif old > 0 >= old + d:
                        self.ctx_types[h] -= 1

    # -- character language model ------------------------------------------
    # Interpolated absolute discounting over characters of keys, with ^ and $
    # as word boundaries. Used to compare a word against its edited variants.

    def _prob(self, x, h):
        if not h:
            uni = self.ngrams[1]
            total = self.ctx_total['']
            return (max(uni.get(x, 0), 0) + 0.5) / (total + 0.5 * (len(uni) + 1))
        lower = self._prob(x, h[1:])
        total = self.ctx_total.get(h, 0)
        if total <= 0:
            return lower
        c = max(self.ngrams[len(h) + 1].get(h + x, 0), 0)
        return (max(c - LM_DISCOUNT, 0) + LM_DISCOUNT * self.ctx_types[h] * lower) / total

    def char_logprobs(self, k):
        """log2 P of each character of k (and the end marker) given up to
        LM_ORDER-1 preceding characters."""
        s = '^' + k + '$'
        return [math.log2(self._prob(s[i], s[max(0, i - LM_ORDER + 1):i]))
                for i in range(1, len(s))]

    def logprob(self, k):
        cache = self.__dict__.setdefault('_lp_cache', {})
        lp = cache.get(k)
        if lp is None:
            lp = cache[k] = sum(self.char_logprobs(k))
        return lp

    # -- persistence --------------------------------------------------------

    @staticmethod
    def default_path():
        return os.path.join(tool_dir(), 'index', 'gold.pkl.gz')

    def save(self, path=None):
        path = path or self.default_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._deletes = None
        self._lp_cache = {}
        with gzip.open(path, 'wb') as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path=None):
        path = path or cls.default_path()
        if not os.path.exists(path):
            raise SystemExit(f'No index at {path}; run `proof.py build` first.')
        with gzip.open(path, 'rb') as f:
            idx = pickle.load(f)
        if getattr(idx, 'version', None) != INDEX_VERSION:
            raise SystemExit('Index format is out of date; run `proof.py build`.')
        return idx

    # -- leave-one-out ------------------------------------------------------

    def without(self, rel_paths):
        """Temporarily subtract gold files' contributions (in place).
        Returns the list of files actually subtracted, for restore()."""
        done = [p for p in rel_paths if p in self.files]
        for p in done:
            self._add(self.files[p]['words'], -1)
        return done

    def restore(self, done):
        for p in done:
            self._add(self.files[p]['words'], +1)

    def stale_files(self):
        """Gold files whose content changed since the index was built."""
        out = []
        for p, meta in self.files.items():
            ap = os.path.join(root_dir(), p)
            if not os.path.exists(ap) or _sha(ap) != meta['sha']:
                out.append(p)
        return out

    # -- near-miss lookup ---------------------------------------------------

    def neighbours(self, k):
        """Gold keys within one edit (insert/delete/substitute/transpose) of k,
        with their current counts, most frequent first."""
        if self._deletes is None:
            d = {}
            for w in self.words:
                d.setdefault(w, set()).add(w)
                for x in deletes(w):
                    d.setdefault(x, set()).add(w)
            self._deletes = d
        cands = set(self._deletes.get(k, ()))
        for x in deletes(k):
            cands |= self._deletes.get(x, set())
            if x in self.words:
                cands.add(x)
        cands.discard(k)
        out = [(c, self.words[c]) for c in cands
               if self.words[c] > 0 and _within_one_edit(k, c)]
        return sorted(out, key=lambda t: -t[1])


def _within_one_edit(a, b):
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return (len(diff) == 2 and diff[1] == diff[0] + 1
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]
