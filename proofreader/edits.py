"""Proposed edits as a CSV to cherry-pick: mark `approve` (y/yes/x/1) on the
rows you want, then `proof.py apply-edits FILE.csv` applies exactly those.

Each row names a file, a line, the exact text there (`current`, which may
span several words) and its replacement. `occ` says which occurrence of
`current` on that line is meant.
"""

import csv
import os
import re

from .index import rel, root_dir
from .text import WORD_RE

FIELDS = ['id', 'approve', 'category', 'rule', 'file', 'line', 'occ', 'current', 'proposed',
          'context', 'note']
YES = {'y', 'yes', 'x', '1', 'true', '✓', 'ok'}


def write_csv(rows, path):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:   # BOM: Excel reads UTF-8
        w = csv.DictWriter(f, FIELDS, extrasaction='ignore')
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({'id': i, 'approve': '', **r})


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def _spans(line, text):
    """Occurrences of `text` in `line` that start and end at word boundaries."""
    out, start = [], line.find(text)
    while start != -1:
        end = start + len(text)
        before = line[start - 1] if start else ' '
        after = line[end] if end < len(line) else ' '
        if not WORD_RE.match(before) and not WORD_RE.match(after):
            out.append((start, end))
        start = line.find(text, start + 1)
    return out


def occurrence(line, text, at):
    """Which boundary-delimited occurrence of `text` starts at offset `at`."""
    return sum(1 for s, _ in _spans(line, text) if s < at)


def apply_rows(rows, log=print):
    """Apply approved rows. Rows on the same line are applied right to left,
    so earlier ones keep their positions. Returns (applied, failed)."""
    todo = [r for r in rows if r.get('approve', '').strip().lower() in YES]
    by_file = {}
    for r in todo:
        by_file.setdefault(r['file'], []).append(r)
    applied, failed = 0, []
    for rp, rs in sorted(by_file.items()):
        path = os.path.join(root_dir(), rp)
        with open(path, encoding='utf-8', newline='') as f:
            lines = f.read().split('\n')
        # resolve every row against the unmodified file first
        edits = []
        for r in rs:
            n = int(r['line'])
            spans = _spans(lines[n - 1], r['current']) if 1 <= n <= len(lines) else []
            occ = int(r.get('occ') or 0)
            if occ >= len(spans):
                failed.append(f"#{r['id']} {rp}:{n}: '{r['current']}' not found (file changed?)")
                continue
            edits.append((n, spans[occ][0], spans[occ][1], r['proposed'], r['id']))
        edits.sort(key=lambda t: (t[0], -t[1]))
        ok = []
        for i, t in enumerate(edits):
            nxt = edits[i - 1] if i else None          # the edit to its right on the same line
            if nxt and nxt[0] == t[0] and t[2] > nxt[1]:
                failed.append(f'#{t[4]} {rp}:{t[0]}: overlaps #{nxt[4]}; approve one, re-export the other')
                continue
            ok.append(t)
        for n, s, e, new, rid in ok:
            lines[n - 1] = lines[n - 1][:s] + new + lines[n - 1][e:]
            applied += 1
        edits = ok
        tmp = path + '.proof-tmp'
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write('\n'.join(lines))
        os.replace(tmp, path)
        log(f'{rp}: {len(edits)} edit(s)')
    return applied, failed


def style_rows(findings, path):
    """CSV rows for house-style findings in one file."""
    with open(path, encoding='utf-8', newline='') as f:
        lines = f.read().split('\n')
    rows = []
    for fd in findings:
        line = lines[fd.line - 1]
        hits = [m for m in WORD_RE.finditer(line) if m.group(0) == fd.text]
        if fd.occ >= len(hits):
            continue                       # word spans source lines: skip
        m = hits[fd.occ]
        current, end = fd.text, m.end()
        if fd.join_next:
            for _ in range(int(fd.join_next)):
                nxt = WORD_RE.search(line, end)
                if nxt is None:
                    break
                end = nxt.end()
            current = line[m.start():end]
        rule = fd.reasons[0].split(':')[0]
        rows.append({'category': 'style-mechanical' if fd.mechanical else 'style-review',
                     'rule': rule, 'file': fd.path, 'line': fd.line,
                     'occ': occurrence(line, current, m.start()), 'current': current,
                     'proposed': fd.suggestion, 'context': line.strip(),
                     'note': fd.reasons[0].split(':', 1)[1].strip()})
    return rows
