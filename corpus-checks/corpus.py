"""Which files the corpus checks read.

gold()       the proofread texts (proofreader/gold.txt), with the Padma Purāṇa
             master file in place of its generated chapters/.
reference()  every other .tex in the repos, minus generated, backup and Vedic
             (accented) copies. Used only for word counts, never flagged.
skip_meter() texts not in verse (or not in Sanskrit), from skip-meter.txt.
"""
import os, re, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from proofreader.index import read_manifest, root_dir  # noqa: E402

ROOT = root_dir()
PADMA_CH = 'puja-vidhanam/kathas/ekadashi/padma-puranam/chapters/'
PADMA_M = 'puja-vidhanam/kathas/ekadashi/padma-puranam/ekadashi-mahatmyam-padma-puranam.tex'


def gold():
    fs = [f for f in read_manifest() if not f.startswith(PADMA_CH)]
    return fs + ([PADMA_M] if PADMA_M not in fs else [])


def reference():
    g = set(gold())
    out = []
    for p in glob.glob(ROOT + '/**/*.tex', recursive=True):
        r = os.path.relpath(p, ROOT)
        if r in g or '/chapters/' in r or 'vedamantra' in r or re.search(r'[.-](R0|orig)\.tex$', r):
            continue
        out.append(r)
    return sorted(out)


def skip_meter():
    return {l.split('#')[0].strip() for l in open(os.path.join(HERE, '..', 'skip-meter.txt')) if l.split('#')[0].strip()}
