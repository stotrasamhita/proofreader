"""Local server for `proof.py review ROUND.json`: the shared review page
(round.html) with decisions saved to decisions/<round>.json.

  GET  /                       the page
  GET  /edits.json             the round(s) being reviewed
  GET  /api/decisions?round=R  {docs: [...]}
  POST /api/decision           {round, id, doc}  (doc null clears the decision)
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .index import tool_dir
from .rounds import DecisionFile

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'round.html')


def make_handler(title, rounds, files):
    ids = {r['round']: {x['id'] for x in r['rows']} for r in rounds}
    edits = json.dumps({'title': title, 'rounds': rounds}, ensure_ascii=False).encode()

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

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path in ('/', '/index.html'):
                with open(PAGE, 'rb') as f:
                    return self._send(200, f.read(), 'text/html; charset=utf-8')
            if u.path == '/edits.json':
                return self._send(200, edits)
            if u.path == '/api/decisions':
                df = files.get(q.get('round'))
                if not df:
                    return self._send(404, {'error': 'no such round'})
                return self._send(200, {'docs': df.docs(), 'store': 'local',
                                           'path': os.path.relpath(df.path, tool_dir())})
            self._send(404, {'error': 'not found'})

        def do_POST(self):
            if urlparse(self.path).path != '/api/decision':
                return self._send(404, {'error': 'not found'})
            try:
                b = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                df, rid = files.get(b.get('round')), b.get('id')
                if not df or rid not in ids[df.round]:
                    raise ValueError('no such row')
                if b.get('doc') is None:
                    df.delete(rid)
                else:
                    if b['doc'].get('id') != rid:
                        raise ValueError('id mismatch')
                    df.set(b['doc'])
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                return self._send(400, {'error': str(e)})
            self._send(200, {'ok': True})

    return Handler


def serve(rounds_path, title, rounds, decisions_dir, host, port):
    files = {r['round']: DecisionFile(r['round'], rounds_path, decisions_dir) for r in rounds}
    for df in files.values():
        df.save()                  # records which round file the decisions belong to
    httpd = ThreadingHTTPServer((host, port), make_handler(title, rounds, files))
    for r in rounds:
        df = files[r['round']]
        print(f'round {r["round"]}: {len(r["rows"])} rows, {len(df.docs())} decided -> '
              f'{df.path}', file=sys.stderr)
    print(f'review at http://{host}:{port}/  (Ctrl-C to stop)', file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
