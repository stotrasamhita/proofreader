"""Review rounds and their decisions, kept on disk for `proof.py review` and
`proof.py apply`.

A round file is what the builders write: a list of rows, or a page's
edits.json ({title?, rounds: [{round, label, title, rows}]}). Its decisions go
to decisions/<round>.json:

  {"round": "E1", "rows": "<round file, relative to the proofreader>",
   "applied": [ids already applied], "decisions": {"<id>": {...}}}

Each decision has the fields the Claude artifact DB uses (round, id, status,
category, rule, file, line, occ, current, proposed, decidedAt) and nothing
about who made it.
"""

import glob
import json
import os
import re
import threading
from collections import Counter

from .index import tool_dir

DECISIONS_DIR = os.path.join(tool_dir(), 'decisions')
FIELDS = ('round', 'id', 'status', 'category', 'rule', 'file', 'line', 'occ',
          'current', 'proposed', 'decidedAt')


def load_rounds(path, round_id=None):
    """(page title, [{round, label, title, rows}]) from a round file."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    title = ''
    if isinstance(data, list):
        rid = round_id or next((r['round'] for r in data if r.get('round')), None) \
            or re.sub(r'^round-', '', os.path.basename(path).split('.')[0])
        rounds = [{'round': rid, 'label': rid, 'title': '', 'rows': data}]
    else:
        title = data.get('title', '')
        rounds = data.get('rounds') or [{'round': data['round'], 'title': data.get('title', ''),
                                         'rows': data['rows']}]
        if round_id:
            rounds = [r for r in rounds if r['round'] == round_id]
            if not rounds:
                raise SystemExit(f'{path}: no round {round_id}')
    for r in rounds:
        ids = [x['id'] for x in r['rows']]
        if len(ids) != len(set(ids)):
            raise SystemExit(f'{path}: round {r["round"]} has duplicate row ids')
    return title, rounds


def use_root(path):
    """A round built from fetched files records its root (work/); make it the
    root for this run unless PROOF_ROOT is already set."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    root = data.get('root') if isinstance(data, dict) else None
    if root and not os.environ.get('PROOF_ROOT'):
        os.environ['PROOF_ROOT'] = os.path.join(tool_dir(), root)


def _rel(path):
    return os.path.relpath(os.path.abspath(path), tool_dir())


class DecisionFile:
    """decisions/<round>.json, written atomically on every change."""

    def __init__(self, round_id, rows_path=None, directory=None):
        self.round = round_id
        self.path = os.path.join(directory or DECISIONS_DIR, f'{round_id}.json')
        self.lock = threading.Lock()
        self.data = {'round': round_id, 'rows': None, 'applied': [], 'decisions': {}}
        if os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as f:
                self.data.update(json.load(f))
        if rows_path:
            self.data['rows'] = _rel(rows_path)

    @property
    def rows_path(self):
        p = self.data.get('rows')
        return p and os.path.join(tool_dir(), p)

    def docs(self):
        return list(self.data['decisions'].values())

    def set(self, doc):
        if doc.get('status') not in ('accept', 'reject'):
            raise ValueError('status must be accept or reject')
        if doc.get('round') != self.round:
            raise ValueError(f'decision for round {doc.get("round")!r}, not {self.round}')
        doc = {k: doc[k] for k in FIELDS if k in doc}
        with self.lock:
            self.data['decisions'][str(doc['id'])] = doc
            self.save()

    def delete(self, row_id):
        with self.lock:
            self.data['decisions'].pop(str(row_id), None)
            self.save()

    def mark_applied(self, ids):
        with self.lock:
            self.data['applied'] = sorted(set(self.data['applied']) | set(ids))
            self.save()

    def import_docs(self, docs, row_ids):
        """Merge decisions in; the imported one wins, except over a decision
        already applied. Returns a Counter: new, changed, same, applied (kept
        as applied), unknown (no such row)."""
        n = Counter()
        applied = set(self.data['applied'])
        with self.lock:
            for d in docs:
                if d.get('round') != self.round or d.get('status') not in ('accept', 'reject'):
                    continue
                d = {k: d[k] for k in FIELDS if k in d}
                i = d['id']
                old = self.data['decisions'].get(str(i))
                same = old and all(old.get(k) == d.get(k) for k in ('status', 'proposed'))
                if i not in row_ids:
                    n['unknown'] += 1
                elif same:
                    n['same'] += 1
                elif i in applied:
                    n['applied'] += 1
                else:
                    n['changed' if old else 'new'] += 1
                    self.data['decisions'][str(i)] = d
            self.save()
        return n

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
        os.replace(tmp, self.path)


def read_decisions(path):
    """Decision docs from any of the forms they travel in: a file exported from
    the review page ({format: 'stotrasamhita-decisions', decisions: [...]}), a
    list of docs, one doc (possibly wrapped in {data}), a decisions/<round>.json,
    or a directory of one-JSON-per-doc files exported from the artifact DB."""
    if os.path.isdir(path):
        return [d for f in sorted(glob.glob(os.path.join(path, '*.json'))) for d in read_decisions(f)]
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get('decisions'), list):
        docs = data['decisions']
    elif isinstance(data, dict) and isinstance(data.get('decisions'), dict):
        docs = list(data['decisions'].values())
    elif isinstance(data, list):
        docs = data
    else:
        docs = [data]
    return [d.get('data', d) for d in docs if isinstance(d, dict)]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
        os.replace(tmp, self.path)
