"""`proof.py submit ROUND`: a reviewed round, sent to the editor as a pull request.

The pull request adds two files to the proofreader repo:

  decisions/<round>.json        the decisions (as decisions/ keeps them; nothing on who made them)
  decisions/<round>.rows.json   the rows they were made on, with the sources and commits reviewed

It is made through the GitHub API with `gh` (signed in as the reviewer), so no
checkout of the repo is needed: a branch review/<round> on the repo itself if
the reviewer may push there, else on their fork. The commit is credited to the
reviewer's GitHub no-reply address, never their own email.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

from .rounds import load_rounds


class GhError(Exception):
    pass


def gh(path, method='GET', body=None):
    cmd = ['gh', 'api', '-X', method, path]
    if body is not None:
        cmd += ['--input', '-']
    r = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if r.returncode:
        raise GhError((r.stdout + r.stderr).strip())
    return json.loads(r.stdout) if r.stdout.strip() else None


def _exists(path):
    try:
        gh(path)
        return True
    except GhError as e:
        if 'HTTP 404' in str(e) or 'Not Found' in str(e):
            return False
        raise


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + '\n'


def payload(df, rid):
    """(files {repo path: text}, summary) for decisions file df, sent as round rid."""
    with open(df.rows_path, encoding='utf-8') as f:
        raw = json.load(f)
    title, rounds = load_rounds(df.rows_path, df.round)
    rd = dict(rounds[0])
    rows = [dict(r, round=rid) for r in rd['rows']]
    ids = {r['id'] for r in rows}
    docs = {str(d['id']): dict(d, round=rid) for d in df.docs() if d['id'] in ids}
    sources = raw.get('sources', []) if isinstance(raw, dict) else []
    rows_doc = {'title': title, 'rounds': [dict(rd, round=rid, label=rid if rd.get('label') == df.round
                                                else rd.get('label', rid), rows=rows)]}
    if sources:
        rows_doc['sources'] = sources     # no 'root': that was where the reviewer's copy lived
    dec_doc = {'round': rid, 'rows': f'decisions/{rid}.rows.json', 'applied': [], 'decisions': docs}
    st = [d['status'] for d in docs.values()]
    edited = sum(1 for d in docs.values() if d['status'] == 'accept'
                 and d.get('proposed') != next(r['proposed'] for r in rows if r['id'] == d['id']))
    files = sorted({r['file'] for r in rows})
    own = bool(sources) and not all(s['source'].lower().startswith(('gh:stotrasamhita/',
                                                                     'https://github.com/stotrasamhita/'))
                                    for s in sources)
    summary = dict(rows=len(rows), decided=len(docs), accept=st.count('accept'),
                   reject=st.count('reject'), edited=edited, files=files, sources=sources,
                   own=own, title=rd.get('title') or title)
    return {f'decisions/{rid}.json': _dumps(dec_doc), f'decisions/{rid}.rows.json': _dumps(rows_doc)}, summary


def _body(rid, s):
    texts = '\n'.join(f'- `{x["source"]}` at `{x["commit"][:10]}`' for x in s['sources']) or \
        '\n'.join(f'- `{f}`' for f in s['files'][:20]) + ('\n- …' if len(s['files']) > 20 else '')
    how = (f'`proof.py apply {rid} --keeps-only`: the texts are the reviewer\'s own, so take the '
           'readings marked correct and the split labels, and leave the texts to them.'
           if s['own'] else f'`proof.py apply {rid}`: apply the accepted edits to the texts here, '
           'and send the rejects to `accepted.txt`.')
    return (f'Review round **{rid}**' + (f' ({s["title"]})' if s['title'] else '') +
            f': {s["decided"]} of {s["rows"]} rows decided, {s["accept"]} accepted '
            f'({s["edited"]} with the fix edited), {s["reject"]} marked correct.\n\n'
            f'Texts reviewed:\n{texts}\n\nAfter merging: {how}\n\n'
            '_Sent with `proof.py submit`._\n')


def submit(df, repo, rid, dry_run=False, log=print):
    files, s = payload(df, rid)
    title = f'Review {rid}: {s["decided"]} decisions'
    if dry_run:
        for p, text in files.items():
            log(f'would add {p} ({len(text.encode()):,} bytes)')
        log(f'pull request to {repo}: {title}\n\n{_body(rid, s)}')
        return None
    if not shutil.which('gh'):
        out = os.path.join(os.path.dirname(df.path), f'submit-{rid}')
        os.makedirs(out, exist_ok=True)
        for p, text in files.items():
            with open(os.path.join(out, os.path.basename(p)), 'w', encoding='utf-8') as f:
                f.write(text)
        sys.exit(f'gh (the GitHub CLI) is not installed. The two files are in {out}: add them to '
                 f'decisions/ in a pull request to https://github.com/{repo}, or install gh, '
                 '`gh auth login`, and run this again.')
    try:
        me = gh('user')
        up = gh(f'repos/{repo}')
        base = up['default_branch']
        if _exists(f'repos/{repo}/contents/decisions/{rid}.json?ref={base}'):
            sys.exit(f'round {rid} is already in {repo}: submit it under another id with --as')
        if up.get('permissions', {}).get('push'):
            head = repo
        else:                                    # a fork of the reviewer's own
            fork = gh(f'repos/{repo}/forks', 'POST', {})
            head = fork['full_name']
            for _ in range(30):
                if _exists(f'repos/{head}/branches/{base}'):
                    break
                time.sleep(2)
            try:
                gh(f'repos/{head}/merge-upstream', 'POST', {'branch': base})
            except GhError:
                pass                             # a fresh fork is already up to date
        base_sha = gh(f'repos/{repo}/git/ref/heads/{base}')['object']['sha']
        tree = gh(f'repos/{head}/git/commits/{base_sha}')['tree']['sha']
        entries = [{'path': p, 'mode': '100644', 'type': 'blob',
                    'sha': gh(f'repos/{head}/git/blobs', 'POST', {'content': t, 'encoding': 'utf-8'})['sha']}
                   for p, t in files.items()]
        tree = gh(f'repos/{head}/git/trees', 'POST', {'base_tree': tree, 'tree': entries})['sha']
        who = {'name': me['login'], 'email': f'{me["id"]}+{me["login"]}@users.noreply.github.com',
               'date': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
        commit = gh(f'repos/{head}/git/commits', 'POST', {
            'message': f'Review {rid}: {s["decided"]} decisions ({s["accept"]} accepted, {s["reject"]} correct)',
            'tree': tree, 'parents': [base_sha], 'author': who, 'committer': who})['sha']
        branch = f'review/{rid}'
        n = 1
        while _exists(f'repos/{head}/git/ref/heads/{branch}'):
            n += 1
            branch = f'review/{rid}-{n}'
        gh(f'repos/{head}/git/refs', 'POST', {'ref': f'refs/heads/{branch}', 'sha': commit})
        pr = gh(f'repos/{repo}/pulls', 'POST', {
            'title': title, 'body': _body(rid, s), 'base': base,
            'head': branch if head == repo else f'{head.split("/")[0]}:{branch}',
            'maintainer_can_modify': True})
    except GhError as e:
        sys.exit(f'GitHub said: {e}\n(is gh signed in? `gh auth status`)')
    log(f'pull request: {pr["html_url"]}')
    return pr['html_url']
