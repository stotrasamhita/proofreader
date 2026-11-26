"""rules.py OUT.tsv FILE... — spelling rules the leave-few-out check (review/lfo/) showed the
word check misses, because gold had the wrong form often enough to vouch for it:
  tattva   तत्व/सत्व → तत्त्व/सत्त्व where the word or a compound member starts there
           (तत्वतः, आत्मतत्वं, सत्वगुण). Not the suffix -tva (प्रेतत्वं, अमृतत्व, दासत्वं),
           त्विष् (…तत्विषे) or सत्वर "quick".
  nsta     न्स्त → ंस्त, -n before t- (भवान्स्तथा → भवांस्तथा). Not -n before an st- word
           (पुमान्स्त्री, ध्यायन्स्तुवन्, राजन्स्तूयमाना, स्तम्भ, स्तब्ध, स्तव, स्तन, स्तीर्ण, स्तोत्र).
  drstum   द्रुष्टुं → द्रष्टुं (Phase B2 round 1, Virāṭa 53-21).
  natva    प्रभावेन → प्रभावेण (the editor's house spelling, 2026-11-08).
Columns: rule, word, proposed, file:line, line."""
import re, sys
sys.path.insert(0, '..')
from proofreader.text import parse_file, clean

# A compound member that starts with tattva/sattva: word start, or after a member
# ending in a long vowel / -a of a likely first member (आत्म, परम, गुण, शुद्ध …).
TATTVA = re.compile(r'(?:^|(?<=आत्म)|(?<=परम)|(?<=शुद्ध)|(?<=महा)|(?<=सर्व)|(?<=गुण)|(?<=ब्रह्म))([तस])त्व(?!र|िष|ेष)')
RULES = [
    ('tattva', TATTVA, lambda m: m.group(1) + 'त्त्व'),
    ('nsta', re.compile('न्स्त(?!्र|ु|ू|ो|म्भ|ब्ध|व|न|ीर्ण)'), lambda m: 'ंस्त'),
    ('drstum', re.compile('द्रुष्टु'), lambda m: 'द्रष्टु'),
    ('natva', re.compile('प्रभावेन'), lambda m: 'प्रभावेण'),
]


def main(out, files):
    n = 0
    with open(out, 'w', encoding='utf-8') as f:
        for p in files:
            for u in parse_file(p):
                for w, ln in u.words():
                    w = clean(w)
                    for name, rx, rep in RULES:
                        new = rx.sub(rep, w)
                        if new != w:
                            f.write(f'{name}\t{w}\t{new}\t{p}:{ln.lineno}\t{ln.text.strip()}\n')
                            n += 1
    print(n, 'hits ->', out, file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
