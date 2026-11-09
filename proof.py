#!/usr/bin/env python3
"""Proofread StotraSamhita texts against a gold (already proofread) corpus.

  proof.py build                     rebuild the index from gold.txt
  proof.py setup                     first run on a bare checkout: verse-checker + index
  proof.py check FILE...             report likely errors in FILEs (or gh:OWNER/REPO[@REF][:PATH])
  proof.py round FILES --id R1 --out round-R1.json   the flags as a review round
  proof.py selfcheck                 check every gold file against the rest
  proof.py eval ORIG FIXED           measure recall on a before/after pair
  proof.py accept WORD...            mark words as valid (never flag again)
  proof.py accept --verse 'FIRST LINE'  mark a verse's metre as valid
  proof.py approve FILE...           add proofread files to gold.txt, rebuild
  proof.py gold-index [--label L]    refresh the shipped gold snapshot (from committed gold)
  proof.py style FILE|DIR... [--apply mechanical|all]   house-style issues / bulk fixes
  proof.py dupes [FILES] [--scope gold|all]   same verse elsewhere with a different reading
  proof.py edits [FILES] --out X.csv  proposed style edits to cherry-pick (approve column)
  proof.py apply-edits X.csv         apply the approved rows
  proof.py splits [FILES] --out X.csv likely word splits from the learned model
  proof.py serve FILE|DIR...         review in the browser (fix / accept / approve)
  proof.py review ROUND.json         review a built round in the browser -> decisions/ROUND.json
  proof.py import ROUND.json FILE    merge decisions exported from a review page
  proof.py apply ROUND [--dry-run]   apply it: mis-click check, edits, rejects to accepted.txt
  proof.py submit ROUND              send it to the editor as a pull request
  proof.py site ROUND.json --out D   static review page (decisions kept in the browser)
"""

import argparse
import json
import difflib
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proofreader.checks import REPORT_THRESHOLD, DocContext, score_word, verse_ok  # noqa: E402
from proofreader.index import Index, read_manifest, rel, root_dir  # noqa: E402
from proofreader.session import (ACCEPTED, Session, add_accepted, approve,  # noqa: E402
                                 expand_paths, load_accepted)
from proofreader.text import key, parse_file  # noqa: E402
from proofreader import locate  # noqa: E402

def get_meter(args):
    if args.no_meter:
        return None
    from proofreader.meter import MeterChecker
    return MeterChecker()


def print_findings(findings, fmt, sort):
    if sort == 'score':
        findings = sorted(findings, key=lambda f: (-f.score, f.path, f.line))
    if fmt == 'tsv':
        print('path\tline\tkind\tscore\ttext\tsuggestion\treasons\tcontext')
        for f in findings:
            print('\t'.join([f.path, str(f.line), f.kind, str(f.score), f.text,
                             f.suggestion, ' ; '.join(f.reasons), f.context]))
        return
    for f in findings:
        head = f'{f.path}:{f.line}  [{f.kind} {f.score:g}]  {f.text}'
        if f.suggestion:
            head += f'  → {f.suggestion}?'
        print(head)
        for r in f.reasons:
            print(f'      {r}')
        if f.context and f.kind != 'meter':
            print(f'      | {f.context.replace(f.text, "«" + f.text + "»", 1)}')


def summarize(findings, nfiles):
    c = Counter(f.kind for f in findings)
    print(f'\n{nfiles} file(s): {c["word"]} word flags, {c["meter"]} metre flags'
          + (f', {c["style"]} style notes' if c['style'] else ''), file=sys.stderr)


def run_checks(paths, args):
    session = Session(meter=not args.no_meter)
    stale = set(session.idx.stale_files())
    findings = []
    for p in paths:
        if rel(p) in stale:
            print(f'warning: {rel(p)} differs from its copy in the gold index (checked '
                  'against the rest of gold; `proof.py build` if you have the gold texts)', file=sys.stderr)
        findings += session.check(p, args.threshold, args.style)
    session.close()
    return findings


def cmd_build(args):
    paths = read_manifest()
    Index.build(paths).save()


def inputs(args):
    """Files to work on: local paths or GitHub sources (fetched into work/)."""
    from proofreader.fetch import resolve
    paths, fetched = resolve(args.files, log=lambda m: print(m, file=sys.stderr))
    for src, commit in fetched:
        print(f'{src} at {commit[:10]}', file=sys.stderr)
    return expand_paths(paths), fetched


def cmd_check(args):
    files, _ = inputs(args)
    findings = run_checks(files, args)
    print_findings(findings, args.format, args.sort)
    summarize(findings, len(files))


def cmd_selfcheck(args):
    files = [os.path.join(root_dir(), p) for p in read_manifest()]
    findings = run_checks(files, args)
    print_findings(findings, args.format, args.sort)
    summarize(findings, len(files))


def cmd_accept(args):
    add_accepted([f'meter: {w}' if args.verse else w for w in args.words], args.note)
    print(f'accepted {len(args.words)} ' + ('verse(s)' if args.verse else 'word(s)'))


def cmd_approve(args):
    for rp in approve(args.files):
        print(f'approved: {rp}')
    cmd_build(args)


def cmd_style(args):
    """List house-style issues; --apply writes the fixes into the files."""
    from proofreader.session import replace_word
    session = Session(meter=False)
    files, _ = inputs(args)
    wanted = set(args.rules.split(',')) if args.rules else None
    found, applied, failed, shown = Counter(), Counter(), [], []
    for p in files:
        fs = session.style(p)
        rules_of = {id(f): f.reasons[0].split(':')[0] for f in fs}
        if wanted:
            fs = [f for f in fs if set(rules_of[id(f)].split('+')) <= wanted]
        for f in fs:
            found[rules_of[id(f)]] += 1
        todo = [f for f in fs if args.apply == 'all' or (args.apply == 'mechanical' and f.mechanical)]
        for f in sorted(todo, key=lambda f: (f.line, -f.occ)):
            try:
                replace_word(p, f.line, f.text, f.occ, f.suggestion, f.join_next)
                applied[rules_of[id(f)]] += 1
            except ValueError as e:
                failed.append(f'{f.path}:{f.line} {f.text}: {e}')
        shown += [f for f in fs if f not in todo]
    if not args.summary:
        print_findings(shown, args.format, 'line')
    print(f'\n{len(files)} file(s). Found: ' + (', '.join(f'{r} {n}' for r, n in found.most_common()) or 'none'),
          file=sys.stderr)
    if args.apply:
        print('Applied: ' + (', '.join(f'{r} {n}' for r, n in applied.most_common()) or 'none'),
              file=sys.stderr)
    for x in failed:
        print('could not apply: ' + x, file=sys.stderr)


def cmd_dupes(args):
    """The same verse in two places with different readings."""
    from proofreader.dupes import corpus_files, find, word_diff
    gold = set(read_manifest())
    files = expand_paths(args.files) if args.files else corpus_files(root_dir())
    files = [os.path.abspath(f) for f in files]
    log = (lambda m: print(m, file=sys.stderr))
    vps = find(files, rel, log=log)
    if args.scope == 'gold':
        vps = [v for v in vps if v.a_path in gold or v.b_path in gold]
    if args.ignore:
        pats = args.ignore.split(',')
        vps = [v for v in vps if not any(p in v.a_path or p in v.b_path for p in pats)]
    tag = lambda p: 'gold' if p in gold else '    '
    if args.format == 'tsv':
        print('a_path\ta_line\ta_gold\tb_path\tb_line\tb_gold\ta_text\tb_text')
    for v in vps:
        if args.format == 'tsv':
            for a, b, r in v.differing:
                print('\t'.join([a.path, str(a.lineno), tag(a.path).strip(), b.path, str(b.lineno),
                                 tag(b.path).strip(), a.text, b.text]))
            continue
        a0, b0 = v.lines[0][0], v.lines[0][1]
        print(f'[{tag(v.a_path)}] {v.a_path}:{a0.lineno}\n[{tag(v.b_path)}] {v.b_path}:{b0.lineno}')
        for a, b, r in v.differing:
            x, y = word_diff(a.text, b.text)
            print(f'    {a.lineno:>6}  {x}\n    {b.lineno:>6}  {y}')
        print()
    n_gold = sum(v.a_path in gold and v.b_path in gold for v in vps)
    print(f'{len(vps)} verse pair(s) with differing readings ({n_gold} between two gold files)',
          file=sys.stderr)


def cmd_edits(args):
    """Export house-style edits for a set of files (default: gold) as a CSV."""
    from proofreader.edits import style_rows, write_csv
    session = Session(meter=False)
    files = expand_paths(args.files) if args.files else \
        [os.path.join(root_dir(), p) for p in read_manifest()]
    rows = []
    for p in files:
        rows += style_rows(session.style(p), p)
    order = {'style-mechanical': 1, 'style-review': 2}
    rows.sort(key=lambda r: (order.get(r['category'], 0), r['file'], int(r['line'])))
    write_csv(rows, args.out)
    print(f'{len(rows)} edit(s) -> {args.out}', file=sys.stderr)


def cmd_apply_edits(args):
    from proofreader.edits import apply_rows, read_csv
    applied, failed = apply_rows(read_csv(args.csv))
    print(f'applied {applied} edit(s)', file=sys.stderr)
    for x in failed:
        print('skipped: ' + x, file=sys.stderr)


def cmd_splits(args):
    """Rank likely word splits with the learned model and export them."""
    from proofreader import splitmodel as SM
    from proofreader.edits import write_csv
    idx = Index.load()
    if args.train or not os.path.exists(SM.MODEL):
        n, pos = SM.train(idx)
        print(f'trained on {n} labels ({pos} split)', file=sys.stderr)
    paths = [rel(p) for p in expand_paths(args.files)] if args.files else read_manifest()
    paths = [p for p in paths if 'HanumanChalisa' not in p]
    rows = SM.candidate_rows(paths, idx, SM.load(), args.min_p, SM.rejected_pairs())
    write_csv(rows, args.out)
    print(f'{len(rows)} likely split(s) -> {args.out}', file=sys.stderr)


def cmd_serve(args):
    from proofreader.server import serve
    serve(inputs(args)[0], args.host, args.port, meter=not args.no_meter)


def _show(path):
    r = os.path.relpath(path)
    return path if r.startswith('..') else r


def _import(rounds_path, rounds, decisions_dir, sources):
    """Merge decisions from exported files or directories into decisions/<round>.json."""
    from proofreader.rounds import DecisionFile, read_decisions
    docs = [d for src in sources for d in read_decisions(src)]
    known = {r['round'] for r in rounds}
    for r in rounds:
        df = DecisionFile(r['round'], rounds_path, decisions_dir)
        n = df.import_docs(docs, {x['id'] for x in r['rows']})
        print(f'round {r["round"]}: ' + ', '.join(f'{v} {k}' for k, v in sorted(n.items()) if v)
              + (' (nothing for this round)' if not n else '') + f' -> {_show(df.path)}')
        if n['applied']:
            print(f'  {n["applied"]} differ from a decision already applied: kept the applied one')
        if n['unknown']:
            print(f'  {n["unknown"]} for row ids not in {rounds_path}: skipped')
    other = sorted({d.get('round') for d in docs} - known - {None})
    if other:
        print(f'skipped decisions for other rounds: {", ".join(other)}')


def cmd_review(args):
    """Serve the shared review page for a round file; decisions go to decisions/<round>.json."""
    from proofreader.rounds import load_rounds, use_root
    from proofreader.roundserver import serve
    use_root(args.rounds)
    title, rounds = load_rounds(args.rounds, args.round)
    if args.title:
        title = args.title
    if args.import_from:
        _import(args.rounds, rounds, args.decisions, args.import_from)
    serve(args.rounds, title, rounds, args.decisions, args.host, args.port)


def cmd_import(args):
    from proofreader.rounds import load_rounds, use_root
    use_root(args.rounds)
    _import(args.rounds, load_rounds(args.rounds, args.round)[1], args.decisions, args.sources)


def cmd_site(args):
    """Write a static review page (index.html + edits.json) that saves decisions in the browser."""
    from proofreader.roundserver import PAGE
    from proofreader.rounds import load_rounds
    title, rounds = args.title or '', []
    for p in args.rounds:
        t, rs = load_rounds(p)
        title = title or t
        rounds += rs
    ids = [r['round'] for r in rounds]
    if len(ids) != len(set(ids)):
        sys.exit(f'the same round id in two files: {ids}')
    data = json.dumps({'title': title, 'rounds': rounds}, ensure_ascii=False)
    with open(PAGE, encoding='utf-8') as f:
        page = f.read()
    os.makedirs(args.out, exist_ok=True)
    if args.inline:             # one self-contained file; opens from disk too
        tag = '<script type="application/json" id="edits-data"></script>'
        assert tag in page
        page = page.replace(tag, tag.replace('></', '>' + data.replace('</', '<\\/') + '</'))
    else:
        with open(os.path.join(args.out, 'edits.json'), 'w', encoding='utf-8') as f:
            f.write(data)
    with open(os.path.join(args.out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page)
    print(f'{len(rounds)} round(s), {sum(len(r["rows"]) for r in rounds)} rows -> {args.out}/index.html'
          + ('' if args.inline else ' + edits.json'))


def _keeps(row, idx, accepted, note):
    """accepted.txt lines for a rejected row: the word(s) as printed, or the
    verse's first line. A metre row outside a verse (a nāmāvalī name) keeps
    the word instead."""
    from proofreader.checks import verse_id
    from proofreader.text import WORD_RE
    if row['category'] == 'meter':
        path = os.path.join(root_dir(), row['file'])
        if os.path.exists(path):
            units = [u for u in parse_file(path) if u.kind == 'verse'
                     and any(l.lineno == row['line'] for l in u.lines)]
            first = units[0].lines[0].text.strip() if units else None
        else:               # a reviewer's own text, not here: a whole-verse row starts with its first line
            first = row['current'].split('\n')[0].strip() if 'lines' in row else None
        if first:
            return [] if verse_id([first]) in accepted else [f'meter: {first}  # {note}']
    elif row['category'] != 'word':
        return []           # style rows: a reject is a split label, not a kept word
    words = WORD_RE.findall(row['current'])
    if len(words) > 1:      # 'आनन्दवत्यै~नमः': keep only what gold does not know
        words = [w for w in words if not idx.words[key(w)]] or words
    return [f'{w}  # {note}' for w in dict.fromkeys(words) if key(w) not in accepted]


def cmd_apply(args):
    """Apply a round reviewed with `proof.py review`: mis-click check, the
    accepted edits, split labels, and rejects to accepted.txt. Decisions
    already applied are skipped, so a round can be applied as it goes."""
    from proofreader.rounds import DecisionFile, load_rounds, use_root
    df = DecisionFile(args.round, directory=args.decisions)
    if not os.path.exists(df.path):
        sys.exit(f'no decisions file {df.path}; review the round first (proof.py review ROUND.json)')
    rows_path = args.rows or df.rows_path
    if not rows_path or not os.path.exists(rows_path):
        sys.exit(f'{df.path}: its round file {rows_path!r} is missing; pass --rows')
    use_root(rows_path)               # before apply_round, which reads the root on import
    print(f'texts in {root_dir()}')
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'corpus-checks'))
    import apply_round
    import misclick
    R = {r['id']: r for r in load_rounds(rows_path, args.round)[1][0]['rows']}
    if args.skip:
        df.mark_applied(int(i) for i in args.skip.split(','))
    done = set(df.data['applied'])
    D = {int(i): d for i, d in df.data['decisions'].items() if int(i) not in done}
    print(f'round {args.round}: {len(R)} rows, {len(df.data["decisions"])} decided, '
          f'{len(done)} applied before, {len(D)} to apply now')
    if not D:
        return
    n = misclick.check(R, D)
    n.pop('missing', None)
    if (n['stale'] or n['mixed'] or n['unknown']) and not args.force:
        sys.exit('stopped: stale, mixed or unknown decisions above. Fix them on the page, '
                 'or sign them off and re-run with --force.')
    if n['edited']:
        print('(edited proposals above: check them by eye, and that verse lines still scan)')

    absent = sorted({R[i]['file'] for i, d in D.items() if d['status'] == 'accept'
                     and not os.path.exists(os.path.join(root_dir(), R[i]['file']))})
    if absent and not args.keeps_only:
        sys.exit(f'{len(absent)} file(s) with accepted edits are not here (e.g. {absent[0]}): '
                 'a reviewer\'s own texts? Re-run with --keeps-only to take just the keeps and '
                 'split labels, or fetch the texts and pass --root.')

    idx, accepted = Index.load(), load_accepted()
    keeps = []
    for i, d in sorted(D.items()):
        if d['status'] == 'reject':
            keeps += _keeps(R[i], idx, accepted, f'{args.round}-{i} reviewed: kept as printed')
    if args.dry_run:
        rows, miss, labels = apply_round.plan(R, list(D.values()))
        for r in rows:
            print(f'would apply #{r["id"]} {r["file"]}:{r["line"]}  {r["current"]} -> {r["proposed"]}')
        for m in miss:
            print(f'  MISSING #{m["id"]} {m["file"]}:{m["line"]} {m["current"]}')
        for k in keeps:
            print(f'would keep  {k}')
        print(f'{len(rows)} edit(s), {len(miss)} not found, {len(labels)} label(s), '
              f'{len(keeps)} keep(s); nothing written')
        return

    if args.keeps_only:
        from proofreader import splitmodel
        labels = apply_round.split_labels(R, list(D.values()))
        splitmodel.add_labels(labels)
        if keeps:
            with open(ACCEPTED, 'a', encoding='utf-8') as f:
                f.write(''.join(k + '\n' for k in keeps))
        for k in keeps:
            print('  kept', k)
        print(f'keeps only: accepted.txt +{len(keeps)}, labels +{len(labels)}; '
              f'{sum(d["status"] == "accept" for d in D.values())} accepted edit(s) left to the texts\' owner')
        df.mark_applied(set(D))
        return

    csv_path = df.path[:-len('.json')] + '.apply.csv'
    applied, failed, miss, labels = apply_round.apply(R, list(D.values()), csv_path)
    if keeps:
        with open(ACCEPTED, 'a', encoding='utf-8') as f:
            f.write(''.join(k + '\n' for k in keeps))
    print(f'applied {applied}, failed {len(failed)}, not found {len(miss)}, '
          f'labels +{len(labels)}, accepted.txt +{len(keeps)}')
    held = {m['id'] for m in miss}
    for m in miss:
        print(f'  MISSING #{m["id"]} {m["file"]}:{m["line"]} {m["current"]}')
    for f in failed:
        print('  FAILED', f)
        held.add(int(f.split()[0].lstrip('#')))
    for k in keeps:
        print('  kept', k)
    df.mark_applied(set(D) - held)
    if os.environ.get('PROOF_ROOT'):
        for repo in sorted({R[i]['file'].split('/')[0] for i in D}):
            print(f'edits are in a fetched copy: git -C {os.path.join(root_dir(), repo)} diff')
    if held:
        print(f'{len(held)} row(s) not applied: {",".join(map(str, sorted(held)))}. Edit them by hand '
              f'and mark them done with --skip, or re-run to retry them.')


def cmd_submit(args):
    """Send a reviewed round to the editor as a pull request (via the GitHub API and gh)."""
    from proofreader.rounds import DecisionFile
    from proofreader import submit
    df = DecisionFile(args.round, directory=args.decisions)
    if not os.path.exists(df.path) or not df.docs():
        sys.exit(f'nothing to submit: no decisions in {df.path}')
    if not df.rows_path or not os.path.exists(df.rows_path):
        sys.exit(f'{df.path}: its round file {df.rows_path!r} is missing')
    submit.submit(df, args.repo, args.as_id or args.round, dry_run=args.dry_run)


def cmd_gold_index(args):
    """Refresh gold-index.json.gz, the gold snapshot that ships with the repo."""
    from proofreader import golddb
    before = golddb.info() if os.path.exists(golddb.DB) else {'files': 0, 'repos': {}}
    old = set(golddb.read(Index).files) if before['files'] else set()
    idx, revs, warn = golddb.snapshot(Index, args.label)
    for w in warn:
        print('warning: ' + w)
    new = set(idx.files)
    print(f'{golddb.DB}: {len(new)} files ({len(new - old)} added, {len(old - new)} removed) from '
          + ', '.join(f'{r}@{c}' for r, c in revs.items()))
    for p in sorted(new - old):
        print('  + ' + p)
    for p in sorted(old - new):
        print('  - ' + p)
    print('commit it with a note of why now (a gold tag, a closed round).')


def cmd_setup(args):
    """What a checkout of the proofreader alone needs: verse-checker and the index."""
    import subprocess
    from proofreader.meter import VERSE_CHECKER_URL, verse_checker
    vc = verse_checker()
    if vc:
        print(f'verse-checker: {vc}')
    else:
        dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor', 'verse-checker')
        print(f'fetching verse-checker into {dest} …')
        subprocess.run(['git', 'clone', '-q', '--depth', '1', VERSE_CHECKER_URL, dest], check=True)
    from proofreader import golddb
    idx = Index.load()                   # builds the local cache from gold-index.json.gz
    if idx.source == 'texts':
        print('gold index: built from the gold texts here (proof.py build)')
    else:
        i = golddb.info()
        print('gold snapshot' + (f' {i["label"]}' if i['label'] else '') + ': '
              + ', '.join(f'{r}@{c}' for r, c in i['repos'].items()))
    print(f'gold index: {len(idx.files)} files, {len(idx.words):,} distinct words. Ready:\n'
          '  proof.py check gh:OWNER/REPO[@REF][:PATH]\n'
          '  proof.py round gh:OWNER/REPO:PATH --id R1 --out round-R1.json')


def cmd_fetch(args):
    from proofreader.fetch import resolve
    for p in resolve(args.files)[0]:
        print(p)


def _verse_rows(path, rp, findings, meter):
    """Whole-verse rows for metre findings, as the review page shows them:
    every pāda editable, the printed verse with the syllables to look at marked."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'corpus-checks'))
    import versenum
    from proofreader.checks import verse_ok
    from proofreader.meter import by_position, mark
    units = {u.lines[0].lineno: u for u in parse_file(path) if u.kind == 'verse'}
    out = []
    for f in findings:
        u = units.get(f.line)
        if not u:
            continue
        lines = [l.text for l in u.lines]
        ok, r = verse_ok(lines, meter)
        pats, hint = r['patterns'], r.get('hint', '')
        soft = by_position(lines, pats, hint)
        shown = mark(lines, pats, hint, '\x01', '\x02', {i: set(v) for i, v in soft.items()}, '\x03', '\x04')
        try:
            vnum = versenum.label(rp, f.line)
        except (OSError, UnicodeDecodeError):
            vnum = ''
        dev = vnum.translate(str.maketrans('0123456789', '०१२३४५६७८९'))
        shown = [x.strip() for x in shown]
        if len(shown) > 1:
            shown[len(shown) // 2 - 1] += ' ।'
        shown[-1] += f' ॥ {dev} ॥' if dev else ' ॥'
        out.append({'category': 'meter', 'rule': 'meter', 'file': rp, 'line': f.line, 'occ': 0,
                    'lines': [l.lineno for l in u.lines], 'current': '\n'.join(l.strip() for l in lines),
                    'proposed': '\n'.join(l.strip() for l in lines), 'context': ' / '.join(lines),
                    'note': ' · '.join(x for x in f.reasons if not x.startswith(('at:', '‹›'))),
                    'vnum': vnum, 'shown': '\n'.join(shown), 'score': f.score})
    return out


def cmd_round(args):
    """Check files and write the flags as a review round (word and metre rows)."""
    from proofreader.index import tool_dir
    files, fetched = inputs(args)
    session = Session(meter=not args.no_meter)
    rows = []
    for p in files:
        rp = rel(p)
        fs = session.check(p, args.threshold)
        with open(p, encoding='utf-8', errors='replace') as fh:
            raw = fh.read().split('\n')
        for f in fs:
            if f.kind == 'word':
                rows.append({'category': 'word', 'rule': 'word', 'file': rp, 'line': f.line, 'occ': 0,
                             'current': f.text, 'proposed': f.suggestion or f.text,
                             'context': raw[f.line - 1].strip() if f.line <= len(raw) else f.context,
                             'note': ' · '.join(f.reasons), 'score': f.score})
        if session.meter:
            rows += _verse_rows(p, rp, [f for f in fs if f.kind == 'meter'], session.meter)
    session.close()
    for r in rows:
        r['section'] = 'Metre' if r['category'] == 'meter' else 'Words'
    if not args.no_splits:
        rows += _split_rows(files)
    order = {'Metre': 0, 'Consonant splits': 1, 'Words': 2}
    rows.sort(key=lambda r: (order[r['section']], r['file'], r['line']))
    lines = {}

    def read_lines(rp):
        if rp not in lines:
            with open(os.path.join(root_dir(), rp), encoding='utf-8', errors='replace') as fh:
                lines[rp] = fh.read().split('\n')
        return lines[rp]
    for r in rows:
        r['chap'] = locate.chap(read_lines(r['file']), r['line'])
    if args.ocr:
        locate.add_pages(rows, read_lines, args.ocr)
    for i, r in enumerate(rows, 1):
        r.update(id=i, round=args.id)
    data = {'title': args.title or f'Review {args.id}', 'rounds': [
        {'round': args.id, 'label': args.id, 'title': ', '.join(s for s, _ in fetched) or
         ', '.join(sorted({r['file'] for r in rows})), 'rows': rows}]}
    if fetched:
        data['root'] = os.path.relpath(root_dir(), tool_dir())
        data['sources'] = [{'source': s, 'commit': c} for s, c in fetched]
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    c = Counter(r['section'] for r in rows)
    print(f'{len(files)} file(s): {c["Words"]} word rows, {c["Metre"]} metre rows, '
          f'{c["Consonant splits"]} consonant splits -> {args.out}\n'
          f'next: proof.py review {args.out}   (or proof.py site {args.out} --out DIR)', file=sys.stderr)


def _split_rows(files):
    """Consonant-final words run into the next word (house rule: written apart), from
    corpus-checks/freeword.py and tjoin.py run on these files. Candidates, to be read."""
    import subprocess
    import tempfile
    from proofreader.index import tool_dir
    out, seen = [], set()
    gold = read_manifest()
    if not gold or not os.path.exists(os.path.join(root_dir(), gold[0])):
        print('consonant splits skipped: the checks count words in the gold texts, which are not here '
              '(clone the StotraSamhita repos next to proofreader/)', file=sys.stderr)
        return out
    for check, cols in (('freeword', (0, 1, 4, 5)), ('tjoin', (0, 1, 2, 3))):
        with tempfile.NamedTemporaryFile('r', suffix='.tsv', encoding='utf-8') as tmp:
            subprocess.run([sys.executable, os.path.join(tool_dir(), 'corpus-checks', check + '.py'), tmp.name,
                            *[os.path.abspath(f) for f in files]], check=True, stdout=subprocess.DEVNULL,
                           cwd=os.path.join(tool_dir(), 'corpus-checks'))
            for l in tmp:
                c = l.rstrip('\n').split('\t')
                w, split, at, line = (c[i] for i in cols)
                f, n = at.rsplit(':', 1)
                rp = rel(f)
                if (rp, n, w) in seen:
                    continue
                seen.add((rp, n, w))
                out.append({'category': 'word', 'rule': 'split', 'section': 'Consonant splits', 'file': rp,
                            'line': int(n), 'occ': 0, 'current': w, 'proposed': split, 'context': line.strip(),
                            'note': f'house rule: a consonant-final word is written apart ({check}.py). '
                                    'Reject if it is one word or a compound.'})
    return out


def cmd_eval(args):
    """Check ORIG against gold minus FIXED, then score the flags against the
    corrections that FIXED actually made."""
    def toks(p):
        return [(w, n) for n, u in enumerate(parse_file(p)) for w, _ in u.words()]
    orig, fixed = toks(args.orig), toks(args.fixed)
    a, b = [w for w, _ in orig], [w for w, _ in fixed]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    # An orig token counts as a real error only if it was corrected into a
    # similar word; re-spacing, anusvara/avagraha style, rewrites and added
    # colophons are not errors the checker should be judged on.
    real, style = set(), set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            continue
        fixed_keys = [key(w) for w in b[j1:j2]]
        joined = ''.join(fixed_keys)
        for i in range(i1, i2):
            k = key(a[i])
            if k in joined:
                style.add(i)
            elif any(difflib.SequenceMatcher(None, k, f).ratio() >= 0.66 for f in fixed_keys):
                real.add(i)

    idx = Index.load()
    removed = idx.without([rel(args.fixed)])
    accepted = load_accepted()
    doc = DocContext(a)
    scores = [score_word(w, idx, accepted, doc)[0] for w, _ in orig]
    idx.restore(removed)

    print(f'orig tokens {len(a):,}; corrected tokens: {len(real):,} substantive, '
          f'{len(style):,} style-only (spacing / anusvara / avagraha)')
    print(f'{"threshold":>9} {"flagged":>8} {"hits":>6} {"precision":>9} {"recall":>7}')
    for t in (1, 2, 3, 4, 5, 6, 8, 10):
        flagged = {i for i, s in enumerate(scores) if s >= t}
        hits = len(flagged & real)
        print(f'{t:>9} {len(flagged):>8,} {hits:>6,} {hits / max(1, len(flagged)):>9.1%} '
              f'{hits / max(1, len(real)):>7.1%}')
    if not args.no_meter:
        meter = get_meter(args)
        units = parse_file(args.orig)
        bad_units = {n for n, u in enumerate(units) if u.kind == 'verse'
                     and not verse_ok([l.text for l in u.lines], meter)[0]}
        meter.save_cache()
        unit_of = [n for _, n in orig]
        verse_units = {n for n, u in enumerate(units) if u.kind == 'verse'}
        err_units = {unit_of[i] for i in real} & verse_units
        print(f'\nmetre: {len(bad_units):,} of {len(verse_units):,} verses flagged; '
              f'{len(bad_units & err_units):,} of {len(err_units):,} verses with a real error '
              f'are flagged ({len(bad_units & err_units) / max(1, len(bad_units)):.1%} precision)')
        for t in (3, 5, 8):
            flagged = {i for i, s in enumerate(scores) if s >= t}
            union = {i for i in real if i in flagged or unit_of[i] in bad_units}
            print(f'  words ≥{t} or metre: {len(union):,} of {len(real):,} real errors covered '
                  f'({len(union) / max(1, len(real)):.1%})')
    if args.show_missed:
        print('\nmissed substantive corrections (orig → fixed):')
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op != 'equal' and any(i in real and scores[i] < args.threshold
                                     for i in range(i1, i2)):
                print(f'  {" ".join(a[i1:i2])} → {" ".join(b[j1:j2])}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', help='where the texts live (default: the StotraSamhita folder; '
                    'for fetched sources, work/)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--threshold', type=float, default=REPORT_THRESHOLD,
                       help='minimum score to report (default %(default)s)')
        p.add_argument('--no-meter', action='store_true', help='skip chandas checks')
        p.add_argument('--style', action='store_true', help='also report house-style notes')
        p.add_argument('--format', choices=('text', 'tsv'), default='text')
        p.add_argument('--sort', choices=('line', 'score'), default='line')

    sub.add_parser('build').set_defaults(fn=cmd_build)
    p = sub.add_parser('check')
    p.add_argument('files', nargs='+')
    common(p)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser('selfcheck')
    common(p)
    p.set_defaults(fn=cmd_selfcheck)
    p = sub.add_parser('eval')
    p.add_argument('orig')
    p.add_argument('fixed')
    p.add_argument('--show-missed', action='store_true')
    p.add_argument('--no-meter', action='store_true')
    p.add_argument('--threshold', type=float, default=REPORT_THRESHOLD)
    p.set_defaults(fn=cmd_eval)
    p = sub.add_parser('accept')
    p.add_argument('words', nargs='+')
    p.add_argument('--verse', action='store_true',
                   help="each argument is a verse's first line; accept its metre")
    p.add_argument('--note', default='')
    p.set_defaults(fn=cmd_accept)
    p = sub.add_parser('style', help='house-style issues (and bulk fixes)')
    p.add_argument('files', nargs='+')
    p.add_argument('--apply', choices=('mechanical', 'all'),
                   help='write fixes: mechanical = nasal/final-m only; all = also split/avagraha/join')
    p.add_argument('--rules', help='comma-separated subset: nasal,final-m,join,split,avagraha')
    p.add_argument('--summary', action='store_true', help='counts only')
    p.add_argument('--format', choices=('text', 'tsv'), default='text')
    p.set_defaults(fn=cmd_style)
    p = sub.add_parser('dupes', help='same verse, different readings')
    p.add_argument('files', nargs='*', help='default: every .tex in the StotraSamhita repos')
    p.add_argument('--scope', choices=('gold', 'all'), default='gold',
                   help='gold: only pairs involving a gold file (default)')
    p.add_argument('--ignore', help='comma-separated path fragments to skip')
    p.add_argument('--format', choices=('text', 'tsv'), default='text')
    p.set_defaults(fn=cmd_dupes)
    p = sub.add_parser('edits', help='export proposed house-style edits as a CSV to cherry-pick')
    p.add_argument('files', nargs='*', help='default: the gold files')
    p.add_argument('--out', default='edits.csv')
    p.set_defaults(fn=cmd_edits)
    p = sub.add_parser('apply-edits', help='apply the rows marked approve in an edits CSV')
    p.add_argument('csv')
    p.set_defaults(fn=cmd_apply_edits)
    p = sub.add_parser('splits', help='likely word splits ranked by the learned model')
    p.add_argument('files', nargs='*', help='default: the gold files')
    p.add_argument('--min-p', type=float, default=0.3)
    p.add_argument('--train', action='store_true', help='retrain on labels/split-labels.jsonl first')
    p.add_argument('--out', default='splits.csv')
    p.set_defaults(fn=cmd_splits)
    p = sub.add_parser('serve', help='browser review UI')
    p.add_argument('files', nargs='+')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--no-meter', action='store_true')
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser('submit', help='send a reviewed round to the editor as a pull request')
    p.add_argument('round', metavar='ROUND')
    p.add_argument('--as', dest='as_id', metavar='ID', help='submit under another round id (if ROUND is taken)')
    p.add_argument('--repo', default='stotrasamhita/proofreader')
    p.add_argument('--decisions', help='decisions directory (default: decisions/)')
    p.add_argument('--dry-run', action='store_true', help='show what would be sent; send nothing')
    p.set_defaults(fn=cmd_submit)
    p = sub.add_parser('gold-index', help='refresh gold-index.json.gz from the gold repos\' committed HEAD')
    p.add_argument('--label', default='', help='what this snapshot is, e.g. gold-2026-11-08')
    p.set_defaults(fn=cmd_gold_index)
    p = sub.add_parser('setup', help='fetch verse-checker and build the index from gold-index.json.gz')
    p.set_defaults(fn=cmd_setup)
    p = sub.add_parser('fetch', help='fetch GitHub sources into work/ and print their paths')
    p.add_argument('files', nargs='+', metavar='SOURCE', help='gh:OWNER/REPO[@REF][:PATH] or a GitHub URL')
    p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser('round', help='check files and write the flags as a review round')
    p.add_argument('files', nargs='+', metavar='FILE|DIR|SOURCE')
    p.add_argument('--id', required=True, help='round id, e.g. R1 (never reuse a published one)')
    p.add_argument('--out', required=True, help='round file to write')
    p.add_argument('--title', help='page heading')
    p.add_argument('--threshold', type=float, default=REPORT_THRESHOLD)
    p.add_argument('--no-meter', action='store_true')
    p.add_argument('--no-splits', action='store_true', help='leave out the consonant-split rows')
    p.add_argument('--ocr', metavar='OCR.txt', help="the print's OCR, pages headed '### NNNN.json': "
                   'adds the PDF page and the print line to each row')
    p.set_defaults(fn=cmd_round)
    p = sub.add_parser('review', help='review a round file in the browser; decisions to decisions/ROUND.json')
    p.add_argument('rounds', metavar='ROUND.json', help="a builder's round file, or a page's edits.json")
    p.add_argument('--round', help='which round, if the file holds several (default: all)')
    p.add_argument('--title', help='page heading')
    p.add_argument('--decisions', help='decisions directory (default: decisions/)')
    p.add_argument('--import', dest='import_from', metavar='FILE|DIR', action='append',
                   help='first merge in exported decisions (see `import`); repeatable')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8766)
    p.set_defaults(fn=cmd_review)
    p = sub.add_parser('import', help='merge exported decisions into decisions/ROUND.json')
    p.add_argument('rounds', metavar='ROUND.json', help='the round file the decisions are for')
    p.add_argument('sources', nargs='+', metavar='FILE|DIR',
                   help="a file exported from the review page, or a directory of artifact-DB docs")
    p.add_argument('--round', help='only this round, if the file holds several')
    p.add_argument('--decisions', help='decisions directory (default: decisions/)')
    p.set_defaults(fn=cmd_import)
    p = sub.add_parser('site', help='static review page that keeps decisions in the browser')
    p.add_argument('rounds', nargs='+', metavar='ROUND.json')
    p.add_argument('--out', required=True, help='output directory')
    p.add_argument('--title', help='page heading')
    p.add_argument('--inline', action='store_true', help='put the rows inside index.html (one file)')
    p.set_defaults(fn=cmd_site)
    p = sub.add_parser('apply', help="apply a reviewed round: mis-click check, edits, labels, rejects to accepted.txt")
    p.add_argument('round', metavar='ROUND', help='round id, e.g. E1 (reads decisions/E1.json)')
    p.add_argument('--decisions', help='decisions directory (default: decisions/)')
    p.add_argument('--rows', help='the round file, if it moved since the review')
    p.add_argument('--dry-run', action='store_true', help='show what would change; write nothing')
    p.add_argument('--force', action='store_true', help='apply despite stale or mixed decisions (signed off)')
    p.add_argument('--keeps-only', action='store_true',
                   help="don't edit texts (a reviewer's own): only rejects to accepted.txt and split labels")
    p.add_argument('--skip', metavar='IDS', help='comma-separated row ids to mark done without applying '
                   '(fixed by hand)')
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser('approve')
    p.add_argument('files', nargs='+')
    p.set_defaults(fn=cmd_approve)

    args = ap.parse_args()
    if args.root:
        os.environ['PROOF_ROOT'] = os.path.abspath(args.root)
    args.fn(args)


if __name__ == '__main__':
    main()
