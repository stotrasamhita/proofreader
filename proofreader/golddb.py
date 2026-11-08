"""gold-index.json.gz: the gold index in a form that can live in the repo.

The index (index.py) is a pickle under index/, built from the gold texts. This
file holds only what the index is built from, so that someone without the
StotraSamhita repos can still check a text:

  files    gold path -> {sha, rev, words: {key: count}}   (leave-one-out needs them per file)
  surface  key -> [[spelling, count], ...], only where a key has a spelling other than itself
  pairs    [[key, key, count], ...]   adjacent words within a line

Everything else (totals, character n-grams, the language model's contexts)
is recomputed from the per-file counts on load, which gives back exactly the
index it was written from. The file is deterministic (sorted, gzip mtime 0),
so it changes only when gold does. It is JSON, not a pickle: loading it runs
no code.

It is a snapshot, refreshed by hand (`proof.py gold-index`), not on every
build: always from each gold repo's committed HEAD, never a working tree, and
it records those commits (`repos`) so a result can be traced to the gold it
came from.
"""

import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter

from .index import read_manifest, root_dir, tool_dir

DB = os.path.join(tool_dir(), 'gold-index.json.gz')
FORMAT = 'stotrasamhita-gold-index'
VERSION = 1


def sha(path=DB):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def dump(idx, repos=None, label=''):
    surface = {k: list(v.items()) for k, v in sorted(idx.surface.items())
               if not (len(v) == 1 and k in v)}
    data = {
        'format': FORMAT, 'version': VERSION, 'index_version': idx.version,
        'label': label, 'repos': dict(sorted((repos or {}).items())),
        'files': {p: {'sha': m['sha'], 'rev': m.get('rev', ''),
                      'words': dict(sorted((k, c) for k, c in m['words'].items() if c))}
                  for p, m in sorted(idx.files.items())},
        'surface': surface,
        'pairs': [[a, b, c] for (a, b), c in sorted(idx.pairs.items()) if c],
    }
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return gzip.compress(text.encode('utf-8'), 9, mtime=0)


def write(idx, path=DB, repos=None, label=''):
    """Write the file if its content changed; return its sha1."""
    blob = dump(idx, repos, label)
    if not os.path.exists(path) or open(path, 'rb').read() != blob:
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, path)
    return hashlib.sha1(blob).hexdigest()


def read(cls, path=DB):
    """An Index (of class cls) rebuilt from the file."""
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    if data.get('format') != FORMAT or data.get('version') != VERSION:
        raise SystemExit(f'{path}: not a gold index this proofreader can read')
    idx = cls()
    if data['index_version'] != idx.version:
        raise SystemExit(f'{path} is for index version {data["index_version"]}, '
                         f'this proofreader needs {idx.version}: update one of them')
    for p, m in data['files'].items():
        wc = Counter(m['words'])
        idx.files[p] = {'sha': m['sha'], 'rev': m['rev'], 'words': wc}
        idx._add(wc, +1)
    stored = data['surface']
    idx.surface = {k: dict(stored[k]) if k in stored else {k: c} for k, c in idx.words.items()}
    idx.forms = {k: Counter(v).most_common(1)[0][0] for k, v in idx.surface.items()}
    idx.pairs = Counter({(a, b): c for a, b, c in data['pairs']})
    return idx


def info(path=DB):
    """The snapshot's header: label, repos, number of files."""
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    return {'label': data.get('label', ''), 'repos': data.get('repos', {}), 'files': len(data['files'])}


def _git(repo, *args, data=None):
    r = subprocess.run(['git', '-C', repo, *args], input=data, capture_output=True)
    if r.returncode:
        raise SystemExit(f'{repo}: git {" ".join(args)}: {r.stderr.decode().strip()}')
    return r.stdout


def snapshot(cls, label='', log=print):
    """Build the index from each gold repo's committed HEAD and write the file.
    Returns (index, {repo: commit}, [warnings])."""
    root = root_dir()
    with open(os.path.join(tool_dir(), 'gold.txt'), encoding='utf-8') as f:
        repos = sorted({l.split('#', 1)[0].strip().lstrip('-').strip().split('/')[0]
                        for l in f if l.split('#', 1)[0].strip()})
    revs, warn = {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for repo in repos:
            rp = os.path.join(root, repo)
            revs[repo] = _git(rp, 'rev-parse', '--short', 'HEAD').decode().strip()
            if not _git(rp, 'branch', '-r', '--contains', 'HEAD').strip():
                warn.append(f'{repo} HEAD {revs[repo]} is not pushed: outside users cannot see it')
            if _git(rp, 'status', '--porcelain', '--untracked-files=no').strip():
                warn.append(f'{repo} has uncommitted changes: left out (the snapshot is HEAD)')
            names = [n for n in _git(rp, 'ls-tree', '-r', '-z', '--name-only', 'HEAD').decode().split('\0')
                     if n.endswith(('.tex', '.txt', '.md'))]
            out = _git(rp, 'cat-file', '--batch', data=''.join(f'HEAD:{n}\n' for n in names).encode())
            i = 0
            for n in names:                  # "<sha> blob <size>\n<content>\n" per file
                j = out.index(b'\n', i)
                size = int(out[i:j].split()[2])
                dest = os.path.join(tmp, repo, n)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as f:
                    f.write(out[j + 1:j + 1 + size])
                i = j + 1 + size + 1
        old = os.environ.get('PROOF_ROOT')
        os.environ['PROOF_ROOT'] = tmp
        try:
            idx = cls.build(read_manifest(), log=log)
        finally:
            if old is None:
                del os.environ['PROOF_ROOT']
            else:
                os.environ['PROOF_ROOT'] = old
    for p, m in idx.files.items():
        m['rev'] = revs[p.split('/')[0]]
    write(idx, repos=revs, label=label)
    return idx, revs, warn
