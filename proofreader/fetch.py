"""Texts from a GitHub repo, for checking without a local clone.

A source is a GitHub URL (the repo, or a /tree/ or /blob/ link to a folder
or file) or `gh:OWNER/REPO[@REF][:PATH]`. It is fetched into work/REPO/ as a
shallow, sparse clone of the text files only (.tex, .txt, .md) -- the same
`REPO/path` layout as the StotraSamhita folder, so a gold file fetched this
way is still recognised as gold. work/ then serves as the root (PROOF_ROOT)
for checking, reviewing and applying; the clone is a normal git checkout, so
applied edits show in `git -C work/REPO diff`.

Private repos work wherever git can already authenticate to GitHub.
"""

import os
import re
import subprocess
from dataclasses import dataclass

from .index import tool_dir

WORK = os.path.join(tool_dir(), 'work')
EXTS = ('.tex', '.txt', '.md')

_URL = re.compile(r'^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?'
                  r'(?:/(?:tree|blob)/([^/]+)(?:/(.*?))?)?/?$')
_RAW = re.compile(r'^https?://raw\.githubusercontent\.com/([\w.-]+)/([\w.-]+)/([^/]+)/(.+)$')
_GH = re.compile(r'^gh:([\w.-]+)/([\w.-]+)(?:@([^:]+))?(?::(.*))?$')


@dataclass
class Source:
    owner: str
    repo: str
    ref: str = ''            # branch, tag or commit; '' = the default branch
    path: str = ''           # file or folder inside the repo; '' = all of it

    @property
    def url(self):
        return f'https://github.com/{self.owner}/{self.repo}'

    def __str__(self):
        return f'gh:{self.owner}/{self.repo}' + (f'@{self.ref}' if self.ref else '') + \
               (f':{self.path}' if self.path else '')


def parse(arg):
    """A Source, or None if arg is not a GitHub source."""
    for rx in (_GH, _URL, _RAW):
        m = rx.match(arg.strip())
        if m:
            o, r, ref, path = m.groups()
            return Source(o, r, ref or '', (path or '').strip('/'))
    return None


def _git(cwd, *args, capture=False):
    r = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip() or r.stdout.strip()}')
    return r.stdout.strip() if capture else None


def _patterns(path):
    if not path:
        return [f'*{e}' for e in EXTS]
    if path.endswith(EXTS):
        return [f'/{path}']
    return [f'/{path}/**/*{e}' for e in EXTS]


def fetch(src, log=print):
    """Fetch src into work/REPO; returns (local path of the file or folder, commit)."""
    d = os.path.join(WORK, src.repo)
    if os.path.isdir(os.path.join(d, '.git')):
        have = _git(d, 'remote', 'get-url', 'origin', capture=True)
        if have.rstrip('/').removesuffix('.git').lower() != src.url.lower():
            raise SystemExit(f'{d} is a clone of {have}, not {src.url}; move it aside first')
        if _git(d, 'status', '--porcelain', '--untracked-files=no', capture=True):
            log(f'{src.repo}: has local edits (git -C {d} diff); using it as it is, not re-fetching')
            return _target(d, src), _git(d, 'rev-parse', 'HEAD', capture=True)
    else:
        os.makedirs(d, exist_ok=True)
        _git(d, 'init', '-q')
        _git(d, 'remote', 'add', 'origin', src.url + '.git')
        _git(d, 'config', 'core.sparseCheckout', 'true')
    sparse = os.path.join(d, '.git', 'info', 'sparse-checkout')
    os.makedirs(os.path.dirname(sparse), exist_ok=True)
    old = open(sparse, encoding='utf-8').read().split() if os.path.exists(sparse) else []
    pats = list(dict.fromkeys(old + _patterns(src.path)))
    with open(sparse, 'w', encoding='utf-8') as f:
        f.write('\n'.join(pats) + '\n')
    log(f'fetching {src} …')
    r = subprocess.run(['git', '-C', d, 'fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin',
                        src.ref or 'HEAD'], capture_output=True, text=True)
    if r.returncode:
        err = r.stderr.strip()
        if "couldn't find remote ref" in err:
            raise SystemExit(f'{src}: {src.url} has no branch, tag or commit {src.ref!r}')
        raise SystemExit(f'{src}: could not fetch from {src.url} ({err}). A private repo needs '
                         'git to be signed in to GitHub (e.g. `gh auth setup-git`).')
    _git(d, 'checkout', '-q', '--detach', 'FETCH_HEAD')
    _git(d, 'read-tree', '-mu', 'HEAD')      # apply the (possibly widened) sparse patterns
    commit = _git(d, 'rev-parse', 'HEAD', capture=True)
    return _target(d, src), commit


def _target(d, src):
    p = os.path.join(d, src.path)
    if not os.path.exists(p):
        raise SystemExit(f'{src}: no such file or folder in {src.url} (or no .tex/.txt/.md in it)')
    return p


def resolve(args, log=print):
    """Local paths for a mix of local paths and GitHub sources. Sets PROOF_ROOT
    to work/ when anything was fetched. Returns (paths, [(source, commit)])."""
    paths, fetched = [], []
    for a in args:
        src = parse(a)
        if src is None:
            paths.append(a)
            continue
        p, commit = fetch(src, log)
        paths.append(p)
        fetched.append((str(src), commit))
    if fetched:
        local = [p for p in paths if not os.path.abspath(p).startswith(WORK + os.sep)]
        if local:
            raise SystemExit(f'mix of local files and GitHub sources ({local[0]}): check them separately')
        os.environ['PROOF_ROOT'] = WORK
    return paths, fetched
