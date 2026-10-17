"""versenum.py — the printed number of the verse at a line, as LaTeX numbers it.

Counts numbered verse macros (\\twolineshloka, \\fourlineindentedshloka, …; a
starred one prints no number) since the counter was last reset by \\chapter,
\\section/\\sect or \\resetShloka. Files with several chapters or sections get
chapter-verse (AR adhyāya-verse); a stotra in one section gets just the verse.
"""
import re, os
import corpus

SHLOKA = re.compile(r'\\([a-z]*shloka)(\*?)(?![a-zA-Z])')
RESET = re.compile(r'\\(chapter|chapt|section|sect|resetShloka)(?![a-zA-Z])')
_cache = {}


def numbers(path):
    """{line number of a verse macro: (chapter, section, verse or None)}"""
    if path in _cache:
        return _cache[path]
    out, ch, sec, v = {}, 0, 0, 0
    for n, l in enumerate(open(os.path.join(corpus.ROOT, path), encoding='utf-8'), 1):
        l = re.sub(r'(?<!\\)%.*', '', l)
        for m in RESET.finditer(l):
            k = m.group(1)
            if k == 'chapter':
                ch, sec = ch + 1, 0
            elif k in ('section', 'sect'):
                sec += 1
            v = 0
        m = SHLOKA.search(l)
        if m and m.group(1) not in ('newshloka',):
            if m.group(2):
                out[n] = (ch, sec, None, m.group(1))
            else:
                v += 1
                out[n] = (ch, sec, v, m.group(1))
    _cache[path] = (out, ch, sec)
    return _cache[path]


def _at(path, line):
    out = numbers(path)[0]
    starts = [n for n in out if n <= line]
    return out[max(starts)] if starts else None


def label(path, line):
    """'13', '2-13' (chapter-verse), or '' for an unnumbered verse."""
    out, nch, nsec = numbers(path)
    at = _at(path, line)
    if not at:
        return ''
    ch, sec, v, _ = at
    if v is None:
        return ''
    if nch > 1:
        return f'{ch}-{v}'
    if nsec > 1:
        return f'{sec}-{v}'
    return str(v)


def dandas(path, line, n):
    """What the verse macro prints after each of its n lines: । after every
    line but the last (only after the even lines in the indented four- and
    six-line forms), and ॥ number ॥ after the last."""
    at = _at(path, line)
    macro = at[3] if at else 'twolineshloka'
    v = at[2] if at else None
    even_only = 'indented' in macro and n >= 4
    out = [(' ।' if (i % 2 or not even_only) else '') for i in range(n - 1)]
    star = at is not None and v is None
    if star:
        out.append(' ।' if macro.startswith('oneline') else ' ॥')
    else:
        out.append(' ॥ ' + ''.join('०१२३४५६७८९'[int(c)] for c in str(v)) + ' ॥' if v else ' ॥')
    return out
