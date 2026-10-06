"""House-style checks.

The conventions are the ones the proofread texts follow (measured over the
gold corpus and the Virāṭa original→proofread diff):

  nasal     class nasal, not anusvara, before a stop inside a word
            (सम्प्राप्त, not संप्राप्त); संज्ञ keeps its anusvara
  nasal2    doubled nasal before म/न (सम्मत, सन्निधि; not संमत)
  final-m   a word before a danda (। or ॥) ends in म्; at the end of an odd
            pāda of a four-line verse (no danda) it is म् only if the next
            pāda starts with a vowel, else ं; inside a line, ं before a
            consonant. म् + vowel inside a line stays apart (never joined).
  split     a consonant-final word is written apart from the next word
            (तत् सर्वं); sandhi-changed junctions (वाञ्जनो) and compounds
            known to gold stay joined
  avagraha  elided अ after ो/े is marked (सोऽहं), and words are spelt with
            the avagraha usage of gold (वाऽपि)

nasal, nasal2 and final-m are mechanical (`fix` is safe to apply in bulk);
split and avagraha rest on the gold vocabulary and are for review.
"""

import re
from dataclasses import dataclass

from .text import WORD_RE, clean, key

_STOP_NASAL = {**dict.fromkeys('कखगघ', 'ङ'), **dict.fromkeys('चछजझ', 'ञ'),
               **dict.fromkeys('टठडढ', 'ण'), **dict.fromkeys('तथदध', 'न'),
               **dict.fromkeys('पफबभ', 'म'), 'म': 'म', 'न': 'न'}
_ANUSVARA_RE = re.compile('ं(?=([कखगघचछजझटठडढतथदधपफबभ]|[मन](?!्)))')
_CONSONANT = re.compile('[क-हक़-य़]')
_VOWEL_START = re.compile('^[ऄ-औ]')

# Lines that end with a danda, by macro: (line index, number of lines) -> bool
_DANDA_EVERY_LINE = {'onelineshloka', 'twolineshloka', 'threelineshloka', 'THREElineshloka',
                     'annotwolineshloka'}


def line_has_danda(macro, j, n):
    if j == n - 1:
        return True
    if macro in _DANDA_EVERY_LINE:
        return True
    if macro == 'fourlineshloka':
        return False
    return j % 2 == 1          # four/six-line and indented one-line verses: even lines


_MATRA = {'अ': '', 'आ': 'ा', 'इ': 'ि', 'ई': 'ी', 'उ': 'ु', 'ऊ': 'ू', 'ऋ': 'ृ', 'ॠ': 'ॄ',
          'ऌ': 'ॢ', 'ए': 'े', 'ऐ': 'ै', 'ओ': 'ो', 'औ': 'ौ'}


def join_vowel(w, nxt):
    """'अहम्' + 'अपि' -> 'अहमपि'."""
    return w[:-1] + _MATRA[nxt[0]] + nxt[1:]


@dataclass
class StyleIssue:
    lineno: int
    word: str
    occ: int
    rule: str
    replacement: str           # replaces `word` (or `word` + next word if join)
    mechanical: bool
    note: str
    join_next: int = 0         # number of following words the replacement absorbs


def fix_nasals(w):
    """S1/S2: anusvara before a stop or म/न inside the word -> class nasal."""
    if 'ं' not in w[:-1]:
        return w
    out = _ANUSVARA_RE.sub(lambda m: _STOP_NASAL[m.group(1)] + '्', w)
    # keep संज्ञ (anusvara before ज्ञ) as the corpus does
    return out.replace('ञ्ज्ञ', 'ंज्ञ')


# Junction clusters that are far more often word-internal (वसन्ते, सन्दधानं,
# पापात्मा, याम्यं): a split there needs the word pair attested apart in gold.
_INTERNAL = {'न्त', 'न्द', 'न्न', 'न्थ', 'न्ध', 'न्य', 'न्व', 'त्म', 'त्व', 'त्त', 'त्य', 'त्र',
             'द्ध', 'द्य', 'द्र', 'द्व', 'म्य', 'म्म', 'म्ब', 'म्भ', 'म्प', 'त्स', 'न्स',
             'न्म'}   # न्म is mostly त्→न् nasal sandhi (अकस्मान्मां), kept joined


def split_word(w, idx):
    """S4: 'तत्सर्वं' -> 'तत् सर्वं' when the token splits at halanta +
    consonant into gold words, and gold writes it split more often than
    joined (an unknown joined form counts as never written joined).
    Returns the split surface form or None."""
    k = key(w)
    if '्' not in w[:-1]:
        return None
    joined = idx.words.get(k, 0)
    # split points in the surface form: after a virama, before a consonant
    # never after ञ्/ङ्/ण्: assimilated or word-internal nasals stay joined
    # (कृतवाञ्जनो, धनञ्जयः, शङ्कर)
    points = [i for i in range(2, len(w) - 1) if w[i - 1] == '्' and _CONSONANT.match(w[i])
              and w[i - 2] not in 'ञङण']
    if not points:
        return None

    def known(s, n=2):
        return idx.words.get(key(s), 0) >= n

    def ends_here(s):
        """A left piece unknown to gold, but the char LM expects a word to
        end after it (house style makes -द्, -त्, -न् word ends common)."""
        if len(key(s)) < 4:
            return False
        lp = idx.char_logprobs(key(s))      # last entry is P($ | s)
        return lp[-1] > -2.5

    # dynamic programme over split points: fewest pieces, all known
    cuts = [0] + points + [len(w)]
    best = {0: []}
    for a in range(len(cuts)):
        if cuts[a] not in best:
            continue
        for b in range(a + 1, len(cuts)):
            piece = w[cuts[a]:cuts[b]]
            last = cuts[b] == len(w)
            ok = known(piece) or (not last and ends_here(piece) and
                                  known(w[cuts[b]:], 3) and len(key(w[cuts[b]:])) >= 3)
            if ok and (cuts[b] not in best or
                                 len(best[cuts[a]]) + 1 < len(best[cuts[b]])):
                best[cuts[b]] = best[cuts[a]] + [piece]
    parts = best.get(len(w))
    if not parts or len(parts) < 2:
        return None
    for a, b in zip(parts, parts[1:]):
        apart = idx.pairs.get((key(a), key(b)), 0)
        risky = a[-2:] + b[0] in _INTERNAL or len(key(b)) < 3
        if (risky and apart < 2) or (joined and apart <= joined):
            return None
    return ' '.join(parts)


def avagraha_word(w, idx, min_share=0.8, min_count=3):
    """S5: spell the word with the avagraha usage gold uses for it, or mark
    an elided अ after ो/े. Returns the respelled form or None."""
    if w.startswith('ऽ'):
        return None              # elision across the pāda break: keep it
    k = key(w)
    forms = idx.surface.get(k)
    if not forms:
        # a gold word with a settled ऽ spelling ending a longer token
        for i in range(1, len(w) - 3):
            tail = w[i:]
            fs = idx.surface.get(key(tail))
            if fs and len(key(tail)) >= 4:
                top, n = max(fs.items(), key=lambda t: t[1])
                if ('ऽ' in top and top.replace('ऽ', '') == tail.replace('ऽ', '') and top != tail
                        and n >= min_count and n / sum(fs.values()) >= min_share):
                    return w[:i] + top
    if forms:
        total = sum(forms.values())
        top, n = max(forms.items(), key=lambda t: t[1])
        if (top != w and top.replace('ऽ', '') == w.replace('ऽ', '')
                and n >= min_count and n / total >= min_share):
            return top
        return None
    # unknown word: ो/े + consonant where अ+rest is a gold word -> mark ऽ
    for i in range(1, len(w) - 1):
        if w[i] in 'ोे' and _CONSONANT.match(w[i + 1]):
            left, right = w[:i + 1], 'अ' + w[i + 1:]
            # ए+ति / ए+यं are as likely इति / इयं sandhi (जयेति, जातेयं)
            ambiguous = w[i] == 'े' and ('इ' + w[i + 1:] in idx.forms or
                                         key('इ' + w[i + 1:]) in idx.words)
            if (idx.words.get(key(left), 0) >= 2 and idx.words.get(key(right), 0) >= 3
                    and len(key(right)) >= 3 and not ambiguous):
                return left + 'ऽ' + w[i + 1:]
    return None


_MARKS_RE = re.compile('[\u0951-\u0954\u1CD0-\u1CFF\uA8E0-\uA8F1\u200C\u200D]')


def word_issues(w, idx, danda=None, nxt=None, allow_join=True):
    """House-style fixes for one token. `danda` is True/False for the last
    word of a verse line (None elsewhere); `nxt` is the following token on
    the same line. Returns (replacement, rules, notes, mechanical, join_next)
    or None. The replacement folds every applicable fix together."""
    rules, notes, cur, join = [], [], w, False

    fixed = fix_nasals(cur)
    if fixed != cur:
        rules.append('nasal'); notes.append('class nasal instead of anusvara inside a word')
        cur = fixed

    if danda is True and cur.endswith('ं'):
        rules.append('final-m'); notes.append('line ends with a danda: final म्')
        cur = cur[:-1] + 'म्'
    elif danda is False:
        # odd pāda of a four-line verse: म् only before a vowel-initial pāda
        vowel_next = bool(nxt and _VOWEL_START.match(nxt))
        if cur.endswith('म्') and not vowel_next:
            rules.append('final-m'); notes.append('next pāda starts with a consonant: final ं')
            cur = cur[:-2] + 'ं'
        elif cur.endswith('ं') and vowel_next:
            rules.append('final-m'); notes.append('next pāda starts with a vowel: final म्')
            cur = cur[:-1] + 'म्'
    elif danda is None and cur.endswith('म्') and nxt and not _VOWEL_START.match(nxt):
        rules.append('final-m'); notes.append('final m before a consonant inside a line is written ं')
        cur = cur[:-2] + 'ं'
    # म् + vowel inside a line stays apart (house style: never join)

    if not join and not _MARKS_RE.search(cur):   # vocabulary rules need plain text
        sp = split_word(cur, idx)
        if sp:
            rules.append('split'); notes.append('consonant-final word written apart')
            cur = sp
        else:
            av = avagraha_word(cur, idx)
            if av:
                rules.append('avagraha'); notes.append('avagraha as in the gold texts')
                cur = av
    if not rules:
        return None
    mechanical = all(r in ('nasal', 'final-m') for r in rules)
    return cur, rules, notes, mechanical, join


def check_units(units, idx):
    """All house-style issues in a parsed file, one per token."""
    out = []
    for u in units:
        n = len(u.lines)
        for j, line in enumerate(u.lines):
            toks = list(WORD_RE.finditer(line.text))
            seen = {}
            continued = line.text.rstrip().endswith('-')
            absorbed = set()
            for t_i, m in enumerate(toks):
                w = m.group(0)
                occ = seen.get(w, 0)
                seen[w] = occ + 1
                if t_i in absorbed:
                    continue
                last = t_i == len(toks) - 1
                # what follows the word on this line decides the final-m rule:
                # a space + word (mid-phrase), a danda, or other punctuation
                gap = line.text[m.end():toks[t_i + 1].start() if not last else len(line.text)]
                danda, nxt = None, None
                if any(c in gap for c in '।॥|'):
                    danda = True
                elif not last:
                    if not gap.strip():
                        nxt = toks[t_i + 1].group(0)
                    else:
                        danda = 'skip'           # dash, bracket, comma: leave as written
                elif u.kind == 'verse' and not continued:
                    danda = line_has_danda(u.macro, j, n)
                    if danda is False and j + 1 < n:       # first word of the next pāda
                        nt = WORD_RE.search(u.lines[j + 1].text)
                        nxt = nt.group(0) if nt else None
                r = word_issues(w, idx, danda, nxt, allow_join=u.kind == 'verse')
                if r:
                    rep, rules, notes, mech, join = r
                    n_join = 0
                    if join:
                        # a chain अहम् अपि इदम् … joins into one edit
                        n_join = 1
                        absorbed.add(t_i + 1)
                        k = t_i + 1
                        while (rep.endswith('म्') and k + 1 < len(toks)
                               and not line.text[toks[k].end():toks[k + 1].start()].strip()
                               and _VOWEL_START.match(toks[k + 1].group(0))):
                            rep = join_vowel(rep, toks[k + 1].group(0))
                            k += 1
                            n_join += 1
                            absorbed.add(k)
                    out.append(StyleIssue(line.lineno, w, occ, '+'.join(rules), rep, mech,
                                          '; '.join(notes), n_join))
    return out
