"""A loaded index + metre checker + reviewer decisions, shared by the CLI
and the review server."""

import glob
import os
import re

from .checks import check_file, style_findings, verse_id
from .index import Index, read_manifest, rel, root_dir, tool_dir
from .text import WORD_RE, key, parse_file

ACCEPTED = os.path.join(tool_dir(), 'accepted.txt')
SKIP_METER = os.path.join(tool_dir(), 'skip-meter.txt')
GOLD = os.path.join(tool_dir(), 'gold.txt')
SOURCE_EXTS = ('.tex', '.txt', '.md')


def load_accepted():
    """Words (by key) and verses ('meter: <first line>') marked as correct."""
    out = set()
    if os.path.exists(ACCEPTED):
        with open(ACCEPTED, encoding='utf-8') as f:
            for l in f:
                l = l.split('#', 1)[0].strip()
                if l.startswith('meter:'):
                    out.add(verse_id([l[len('meter:'):]]))
                elif l:
                    out.add(key(l))
    return frozenset(out)


def add_accepted(entries, note=''):
    with open(ACCEPTED, 'a', encoding='utf-8') as f:
        for e in entries:
            f.write(e + (f'  # {note}' if note else '') + '\n')


def skip_meter_files():
    out = set()
    if os.path.exists(SKIP_METER):
        with open(SKIP_METER, encoding='utf-8') as f:
            for l in f:
                l = l.split('#', 1)[0].strip()
                if l:
                    out |= {rel(p) for p in glob.glob(os.path.join(root_dir(), l), recursive=True)}
    return out


def expand_paths(paths):
    """Files and directories -> sorted list of source files."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for d, _, fs in os.walk(p):
                files += [os.path.join(d, f) for f in sorted(fs) if f.endswith(SOURCE_EXTS)]
        else:
            files.append(p)
    return sorted(files)


def approve(paths):
    """Append files to gold.txt. Returns the root-relative paths added."""
    have = set(read_manifest())
    added = [rel(p) for p in paths if rel(p) not in have]
    with open(GOLD, 'a', encoding='utf-8') as f:
        for rp in added:
            f.write(rp + '\n')
    return added


class Session:
    def __init__(self, meter=True):
        self.idx = Index.load()
        self.meter = None
        if meter:
            from .meter import MeterChecker
            self.meter = MeterChecker()
        self.reload()

    def reload(self):
        """Re-read reviewer decisions and config (after accept / approve)."""
        self.accepted = load_accepted()
        self.no_meter = skip_meter_files()
        self.gold = set(self.idx.files)

    def rebuild(self):
        Index.build(read_manifest(), log=lambda *a: None).save()
        self.idx = Index.load()
        self.reload()

    def check(self, path, threshold, style=False):
        """Findings for one file, checked against gold minus itself.
        Non-Sanskrit files (skip-meter.txt) get no Sanskrit checks at all."""
        rp = rel(path)
        if rp in self.no_meter:
            return []
        removed = self.idx.without([rp])
        try:
            return check_file(path, self.idx, None if rp in self.no_meter else self.meter,
                              self.accepted, rp, threshold, style)
        finally:
            self.idx.restore(removed)

    def style(self, path):
        """House-style findings only (no word scoring or metre: fast).
        Files in skip-meter.txt (Hindi/Awadhi) are not Sanskrit-styled."""
        rp = rel(path)
        if rp in self.no_meter:
            return []
        removed = self.idx.without([rp])
        try:
            return style_findings(parse_file(path), self.idx, self.accepted, rp)
        finally:
            self.idx.restore(removed)

    def close(self):
        if self.meter:
            self.meter.save_cache()


def replace_word(path, lineno, word, occ, replacement, join_next=False):
    """Replace the occ-th occurrence of `word` (as a whole Devanagari token)
    on source line `lineno` -- with join_next, together with the space and
    the token after it. Returns the new line, or raises ValueError."""
    with open(path, encoding='utf-8', newline='') as f:
        lines = f.read().split('\n')
    if not 1 <= lineno <= len(lines):
        raise ValueError(f'line {lineno} is out of range')
    line = lines[lineno - 1]
    hits = [m for m in WORD_RE.finditer(line) if m.group(0) == word]
    if occ >= len(hits):
        raise ValueError('word not found on that source line '
                         '(it may span two lines); edit the line instead')
    m = hits[occ]
    end = m.end()
    for _ in range(int(join_next)):
        nxt = WORD_RE.search(line, end)
        if nxt is None or line[end:nxt.start()].strip():
            raise ValueError('no following word on the same line to join with')
        end = nxt.end()
    lines[lineno - 1] = line[:m.start()] + replacement + line[end:]
    _write(path, lines)
    return lines[lineno - 1]


def read_line(path, lineno):
    with open(path, encoding='utf-8', newline='') as f:
        lines = f.read().split('\n')
    return lines[lineno - 1].rstrip('\r')


def replace_line(path, lineno, text):
    with open(path, encoding='utf-8', newline='') as f:
        lines = f.read().split('\n')
    if not 1 <= lineno <= len(lines):
        raise ValueError(f'line {lineno} is out of range')
    cr = '\r' if lines[lineno - 1].endswith('\r') else ''
    lines[lineno - 1] = re.sub(r'[\r\n]', '', text) + cr
    _write(path, lines)


def _write(path, lines):
    tmp = path + '.proof-tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(lines))
    os.replace(tmp, path)
