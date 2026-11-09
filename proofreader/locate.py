"""Where a review row sits: its text, section and verse (r['chap']), and its page
in a scanned print (r['page'], r['ocr']) when the round is given the print's OCR.

chap   '<text> · <section> · verse N': the text is the file's first \\sect (or
       \\chapt), then the nearest \\sect / \\dnsub above the row if it differs,
       then the verse number from the %॥N॥ comment on or just after the row.
       The review page's drop-down filters on the part before the first ' · '.

pages  The OCR as one text file, each page headed '### NNNN.json' (NNNN = the
       PDF page). A row goes to the page sharing the most character 4-grams
       with its line, searched only inside its file's page range; near-ties go
       to the page of the nearest well-matched line. A line the print lacks
       (a stock saṅkalpa an editor added) gets that nearest page, marked
       r['page_approx'].
"""
import collections
import re

HEAD = re.compile(r'\\(?:sect|chapt|dnsub)\{([^}]*)\}')
VNUM = re.compile(r'॥([०-९0-9]+)॥')


def chap(lines, n, name=None):
    heads = [(k, m.group(1)) for k, l in enumerate(lines) for m in [HEAD.search(l)] if m]
    text = name or (heads[0][1] if heads else '')
    sec = next((h for k, h in reversed(heads) if k < n), '')
    v = next((m.group(1) for k in range(n - 1, min(n + 3, len(lines))) for m in [VNUM.search(lines[k])] if m), None)
    return ' · '.join(x for x in (text, sec if sec != text else '', 'verse ' + v if v else '') if x)


def _norm(s):
    s = re.sub(r'\\[a-zA-Z]+\*?|(?<!\\)%.*|[{}~\\]', ' ', s)
    return re.sub(r'[^\u0900-\u0963\u0970-\u097f]', '', s)   # Devanagari letters only


def _grams(s, n=4):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


class Print:
    def __init__(self, path):
        self.pages, cur = {}, None
        for l in open(path, encoding='utf-8'):
            m = re.match(r'### (\d+)\.json', l)
            if m:
                cur = int(m.group(1)); self.pages[cur] = []; continue
            if cur is not None and l.strip() and l.strip() != '###':
                self.pages[cur].append(l.rstrip('\n'))
        self.index = collections.defaultdict(set)
        for p, t in self.pages.items():
            for g in _grams(_norm(' '.join(t))):
                self.index[g].add(p)

    def locate(self, text, lo=0, hi=10 ** 9, expect=None):
        q = _grams(_norm(text))
        score = collections.Counter(p for g in q for p in self.index.get(g, ()) if lo <= p <= hi)
        if not score:
            return None, 0.0, ''
        top = score.most_common(1)[0][1]
        near = [p for p, s in score.items() if s >= 0.9 * top]
        p = min(near, key=lambda p: (abs(p - expect) if expect is not None else 0, -score[p]))
        best = max(self.pages[p], key=lambda l: len(q & _grams(_norm(l))))
        return p, score[p] / len(q), best.strip()

    def span(self, lines):
        """(lo, hi, [(line, page)]) for one file: its well-matched lines near their median page."""
        hits = []
        for n, l in enumerate(lines, 1):
            if len(_norm(l)) >= 30:
                p, c, _ = self.locate(l)
                if p and c >= 0.6:
                    hits.append((n, p))
        if not hits:
            return None
        med = sorted(p for _, p in hits)[len(hits) // 2]
        core = [(n, p) for n, p in hits if abs(p - med) <= 20]
        return min(p for _, p in core), max(p for _, p in core), core


def add_pages(rows, read_lines, ocr_path):
    """Set page / ocr / page_approx on rows; read_lines(file) gives a file's lines."""
    pr, spans = Print(ocr_path), {}
    for f in {r['file'] for r in rows}:
        spans[f] = pr.span(read_lines(f))
    for r in rows:
        sp = spans[r['file']]
        if not sp:
            continue
        lo, hi, core = sp
        L = read_lines(r['file'])
        ns = r.get('lines') or [r['line']]
        text = ' '.join(L[n - 1] for n in ns)
        if len(_norm(text)) < 24:   # short line: add a neighbour on each side
            text = ' '.join(L[max(0, ns[0] - 2):ns[-1] + 1])
        near = min(core, key=lambda np: (abs(np[0] - r['line']), np[0] < r['line']))[1]
        p, conf, best = pr.locate(text, lo, hi, near)
        if p is None or conf < 0.35:
            r.update(page=near, page_approx=True, ocr='')
        else:
            r.update(page=p, ocr=best)
    return rows
