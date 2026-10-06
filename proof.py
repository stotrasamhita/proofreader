#!/usr/bin/env python3
"""Proofread StotraSamhita texts against a gold (already proofread) corpus.

  proof.py build                     rebuild the index from gold.txt
  proof.py check FILE...             report likely errors in FILEs
  proof.py selfcheck                 check every gold file against the rest
  proof.py eval ORIG FIXED           measure recall on a before/after pair
  proof.py accept WORD...            mark words as valid (never flag again)
  proof.py accept --verse 'FIRST LINE'  mark a verse's metre as valid
  proof.py approve FILE...           add proofread files to gold.txt, rebuild
  proof.py serve FILE|DIR...         review in the browser (fix / accept / approve)
"""

import argparse
import difflib
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proofreader.checks import REPORT_THRESHOLD, DocContext, score_word, verse_ok  # noqa: E402
from proofreader.index import Index, read_manifest, rel, root_dir  # noqa: E402
from proofreader.session import (Session, add_accepted, approve, expand_paths,  # noqa: E402
                                 load_accepted)
from proofreader.text import key, parse_file  # noqa: E402

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
            print(f'warning: {rel(p)} changed since the index was built; '
                  'run `proof.py build`', file=sys.stderr)
        findings += session.check(p, args.threshold, args.style)
    session.close()
    return findings


def cmd_build(args):
    paths = read_manifest()
    Index.build(paths).save()


def cmd_check(args):
    files = expand_paths(args.files)
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


def cmd_serve(args):
    from proofreader.server import serve
    serve(expand_paths(args.files), args.host, args.port, meter=not args.no_meter)


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
    p = sub.add_parser('serve', help='browser review UI')
    p.add_argument('files', nargs='+')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--no-meter', action='store_true')
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser('approve')
    p.add_argument('files', nargs='+')
    p.set_defaults(fn=cmd_approve)

    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
