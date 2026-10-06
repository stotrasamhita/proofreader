"""Local review server: `proof.py serve FILES/DIRS`.

Shows each text with flagged words and verses highlighted. Fixes, accepts
and approvals are written straight back to the source files, accepted.txt
and gold.txt; commit them with git as usual.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .index import rel, root_dir
from .session import (Session, add_accepted, approve, read_line, replace_line,
                      replace_word)
from .text import WORD_RE, parse_file

FLOOR = 2.0          # findings at or above this are sent; the UI filters further
_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'review.html')


class Reviewer:
    def __init__(self, files, meter=True):
        self.files = {rel(f): os.path.abspath(f) for f in files}
        print(f'loading index and metre data for {len(self.files)} file(s)…', file=sys.stderr)
        self.session = Session(meter)
        self.lock = threading.RLock()
        self.cache = {}            # rel path -> (mtime, epoch, payload)
        self.epoch = 0             # bumped when accepted/gold change
        threading.Thread(target=self._warm, daemon=True).start()

    def _warm(self):
        for rp in list(self.files):
            try:
                self.payload(rp)
            except Exception as e:  # keep warming the rest
                print(f'{rp}: {e}', file=sys.stderr)

    # -- data ---------------------------------------------------------------

    def path(self, rp):
        if rp not in self.files:
            raise KeyError(f'not a served file: {rp}')
        return self.files[rp]

    def payload(self, rp):
        ap = self.path(rp)
        mtime = os.path.getmtime(ap)
        with self.lock:
            hit = self.cache.get(rp)
            if hit and hit[0] == mtime and hit[1] == self.epoch:
                return hit[2]
            findings = self.session.check(ap, FLOOR, style=True)
            data = build_payload(rp, ap, findings, rp in self.session.gold)
            self.cache[rp] = (mtime, self.epoch, data)
            return data

    def summary(self):
        out = []
        for rp in self.files:
            hit = self.cache.get(rp)
            row = {'path': rp, 'gold': rp in self.session.gold, 'ready': bool(hit)}
            if hit:
                fs = hit[2]['findings']
                row['scores'] = [f['score'] for f in fs if f['kind'] != 'style']
                row['style'] = sum(f['kind'] == 'style' for f in fs)
            out.append(row)
        return out

    def invalidate(self):
        with self.lock:
            self.session.reload()
            self.epoch += 1
        threading.Thread(target=self._warm, daemon=True).start()


def build_payload(rp, ap, findings, gold):
    """Units with lines split into plain/flagged segments, plus findings."""
    by_line, meter_at = {}, {}
    fl, style_at = [], {}
    for f in findings:
        d = {'id': len(fl), 'kind': f.kind, 'line': f.line, 'text': f.text,
             'score': f.score, 'reasons': f.reasons, 'suggestion': f.suggestion}
        fl.append(d)
        if f.kind == 'word':
            by_line.setdefault(f.line, []).append(d)
        elif f.kind == 'meter':
            meter_at[f.line] = d
        elif f.kind == 'style':
            d.update(occ=f.occ, join_next=f.join_next, mechanical=f.mechanical,
                     spans_lines=False)
            style_at[(f.line, f.text, f.occ)] = d
    units = []
    for u in parse_file(ap):
        lines = []
        for line in u.lines:
            pending = list(by_line.get(line.lineno, []))
            segs, pos, seen = [], 0, {}
            continued = line.text.rstrip().endswith('-')
            for m in WORD_RE.finditer(line.text):
                t = m.group(0)
                occ = seen.get(t, 0)
                seen[t] = occ + 1
                ids = []
                hit = next((d for d in pending if d['text'] == t or
                            (continued and d['text'].startswith(t))), None)
                if hit is not None:
                    pending.remove(hit)
                    hit['occ'] = occ
                    hit['spans_lines'] = hit['text'] != t
                    ids.append(hit['id'])
                st = style_at.get((line.lineno, t, occ))
                if st is not None:
                    ids.append(st['id'])
                if not ids:
                    continue
                if m.start() > pos:
                    segs.append([line.text[pos:m.start()], []])
                segs.append([t, ids])
                pos = m.end()
            if pos < len(line.text):
                segs.append([line.text[pos:], []])
            lines.append({'n': line.lineno, 'segs': segs})
        meter = meter_at.get(u.lines[0].lineno) if u.kind == 'verse' else None
        units.append({'kind': u.kind, 'lines': lines,
                      'meter': meter['id'] if meter else None})
    return {'path': rp, 'gold': gold, 'modified': _modified(ap),
            'units': units, 'findings': fl}


def _modified(ap):
    try:
        out = subprocess.run(['git', '-C', os.path.dirname(ap), 'status', '--porcelain', '--', ap],
                             capture_output=True, text=True, timeout=10).stdout
        return bool(out.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def _diff(ap):
    try:
        return subprocess.run(['git', '-C', os.path.dirname(ap), 'diff', '--', ap],
                              capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)


def make_handler(rv):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype='application/json; charset=utf-8'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _guard(self, fn):
            try:
                self._send(200, fn())
            except KeyError as e:
                self._send(404, {'error': str(e).strip("'")})
            except ValueError as e:
                self._send(400, {'error': str(e)})
            except Exception as e:  # surface, don't kill the server
                self._send(500, {'error': f'{type(e).__name__}: {e}'})

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == '/':
                with open(_HTML, 'rb') as f:
                    return self._send(200, f.read(), 'text/html; charset=utf-8')
            routes = {
                '/api/files': lambda: {'files': rv.summary(), 'root': root_dir()},
                '/api/file': lambda: rv.payload(q['path']),
                '/api/line': lambda: {'text': read_line(rv.path(q['path']), int(q['line']))},
                '/api/diff': lambda: {'diff': _diff(rv.path(q['path']))},
            }
            if u.path in routes:
                return self._guard(routes[u.path])
            self._send(404, {'error': 'not found'})

        def do_POST(self):
            n = int(self.headers.get('Content-Length') or 0)
            try:
                b = json.loads(self.rfile.read(n) or b'{}')
            except json.JSONDecodeError:
                return self._send(400, {'error': 'bad JSON'})
            u = urlparse(self.path).path

            def fix():
                replace_word(rv.path(b['path']), int(b['line']), b['word'],
                             int(b.get('occ', 0)), b['replacement'], int(b.get('join_next') or 0))
                return rv.payload(b['path'])

            def style_apply():
                """Apply every mechanical style fix in the file."""
                ap = rv.path(b['path'])
                todo = [f for f in rv.payload(b['path'])['findings']
                        if f['kind'] == 'style' and f['mechanical']]
                done = 0
                for f in sorted(todo, key=lambda f: (f['line'], -f['occ'])):
                    try:
                        replace_word(ap, f['line'], f['text'], f['occ'], f['suggestion'])
                        done += 1
                    except ValueError:
                        pass
                out = rv.payload(b['path'])
                out['applied'] = done
                return out

            def edit_line():
                replace_line(rv.path(b['path']), int(b['line']), b['text'])
                return rv.payload(b['path'])

            def accept():
                entry = f"meter: {b['verse']}" if b.get('verse') else b['word']
                add_accepted([entry], b.get('note', ''))
                rv.invalidate()
                return rv.payload(b['path'])

            def do_approve():
                ap = rv.path(b['path'])
                approve([ap])
                with rv.lock:
                    rv.session.rebuild()
                rv.invalidate()
                return rv.payload(b['path'])

            routes = {'/api/fix': fix, '/api/edit-line': edit_line, '/api/style-apply': style_apply,
                      '/api/accept': accept, '/api/approve': do_approve}
            if u in routes:
                return self._guard(routes[u])
            self._send(404, {'error': 'not found'})

    return Handler


def serve(files, host='127.0.0.1', port=8765, meter=True):
    if not files:
        raise SystemExit('no .tex/.txt/.md files to review')
    rv = Reviewer(files, meter)
    httpd = ThreadingHTTPServer((host, port), make_handler(rv))
    print(f'review at http://{host}:{port}/   (Ctrl-C to stop)', file=sys.stderr)
    if host in ('127.0.0.1', 'localhost'):
        print(f'from another machine: ssh -L {port}:localhost:{port} <this host>', file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        rv.session.close()
