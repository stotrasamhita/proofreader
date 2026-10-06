# StotraSamhita proofreader

Flags likely errors in Sanskrit texts by comparing them with a **gold corpus**
of already-proofread texts, and by checking metre. The output is a ranked list
of words and verses to look at, with suggested corrections where possible.

Run it from this directory. It expects the StotraSamhita repos as sibling
directories (`../stotra-sangrahah`, `../Mahabharatam`, `../verse-checker`, …).

```sh
./proof.py build                                  # (re)build the index from gold.txt
./proof.py check ../puja-vidhanam/kathas/ekadashi --sort score
./proof.py check FILE.tex --threshold 8 --no-meter
./proof.py check FILE.tex --format tsv > flags.tsv   # for a spreadsheet
./proof.py selfcheck --sort score                 # gold files, each against the rest
./proof.py eval ORIG.tex FIXED.tex --show-missed  # measure on a before/after pair
./proof.py accept वेधं --note "Ekadashi technical term"
./proof.py accept --verse 'शरणागतानां देवानां सहायं कुरु वै प्रभो' --note hypermetric
./proof.py approve ../puja-vidhanam/kathas/ekadashi/padma-puranam/chapters/40-utpanna.tex
```

## Review in the browser

```sh
./proof.py serve ../puja-vidhanam/kathas/ekadashi        # then open http://127.0.0.1:8765/
# on a remote machine:  ssh -L 8765:localhost:8765 <host>
```

The page shows each file's text with flagged words highlighted (red ≥ 10,
amber ≥ 6, violet below) and metre-flagged verses edged in orange. Click a flag,
or step through flags with `j`/`k`, and then:

- **Apply** the suggestion (`Enter`) or type a replacement. This edits that
  one word in the source file.
- **Edit line** (`e`) to change the raw TeX source line, e.g. to split a word
  or fix a word that spans two lines.
- **Accept** (`a`) a valid word or verse. It goes to `accepted.txt` and is
  never flagged again, in any file.
- **Approve as gold** when the file is done. It is added to `gold.txt` and the
  index is rebuilt.
- **Diff** shows your uncommitted edits to the file (`git diff`).

The min-score slider and "flagged only" filter the view. `#path:line` in the
URL opens a file at a line. Edits go straight to the working tree of each
repo; review with the Diff button or `git diff`, then commit as usual.

## House style

```sh
./proof.py style ../stotra-sangrahah/stotras --summary        # counts per rule
./proof.py style FILE.tex                                      # list issues
./proof.py style FILE.tex --apply mechanical                   # write nasal/final-m fixes
```

Rules, measured on the gold texts and the Virāṭa original→proofread diff:

| rule | convention | kind |
|---|---|---|
| nasal | class nasal before a stop (सम्प्राप्त), doubled before म/न (सम्मत); संज्ञ kept | mechanical |
| final-m | `म्` before a danda (।/॥); at an odd pāda end without a danda, `म्` only if the next pāda starts with a vowel, else `ं`; inside a line `ं` before a consonant, and `म्` + vowel stays apart (never joined) | mechanical |
| split | consonant-final word written apart (तत् सर्वं); assimilated sandhi (वाञ्जनो, अकस्मान्मां) and gold compounds stay joined | review |
| avagraha | elided अ marked (सोऽहं); spelt as gold spells it (वाऽपि) | review |

On the Virāṭa diff, split flags match the editor 85% of the time and
avagraha 95%. The review page has a *House style* mode with an
"Apply all mechanical" button.

## Same verse, different readings

```sh
./proof.py dupes                     # pairs involving a gold file
./proof.py dupes --scope all --format tsv > dupes.tsv
```

Lines are compared after normalizing spaces, anusvara/nasal, avagraha and
pāda-end sandhi, so only substantive differences remain. A verse pair needs two
matching lines, so shared stock half-lines don't count. Derived copies
(`gita/words`, `stotras-pdf`, `-orig` files) are skipped. A difference between
a gold text and a non-gold one usually points at an error in the non-gold text.
Between two gold texts it is an error or a variant reading to decide on.

## Files

| File | Purpose |
|---|---|
| `gold.txt` | Globs of trusted (proofread) files. `approve` appends to it and rebuilds. |
| `accepted.txt` | Words and verses marked correct, so they are never flagged again. |
| `skip-meter.txt` | Files whose verses are not metre-checked (e.g. Awadhi). |
| `index/` | Generated: gold index and metre cache. Rebuild with `build`. |
| `patches/verse-checker-py3.patch` | Two Python 3 fixes to `../verse-checker`; apply with `git -C ../verse-checker apply ../proofreader/patches/verse-checker-py3.patch`. |

## How a word is scored

Every word is reduced to a **key**: svaras, ZWJ/ZWNJ and avagraha removed,
class nasal + stop written as anusvara, final `म्` as `ं`. So `शङ्कर`/`शंकर`
and `वधम्`/`वधं` are the same word. Spelling convention never looks like a new
word; `--style` reports convention issues separately.

1. **Orthography rules** (`ortho`): impossible sequences, such as two vowel
   signs, virama + sign, nukta, `ङ्भ`. They fire on about 10 of 150K gold
   words, and those are errors.
2. **Known word**: the key is in the gold lexicon, so it passes.
3. **Unseen character trigrams**: Sanskrit compounds are mostly unique words,
   but their letter sequences are not. A typo usually creates one or two
   trigrams never seen in gold. The score saturates, so long valid compounds
   are not punished for length.
4. **Look-alike correction** (noisy channel): try OCR/typing confusions
   (प/ष, व/ब, म/भ, ग/म, ि/ी, dropped `्`/`ं`/`र्`, …). Each candidate is
   scored with a 5-gram character language model trained on gold. If one is
   much likelier (in bits), flag the word and suggest that candidate.
5. **Near-miss**: one edit away from a gold word, weighted by that word's
   frequency. Edits in the last two letters count less, because they are
   usually a different inflection.
6. **Document evidence**: a word or trigram that recurs in the same file is
   probably a name or term of that text (कीचक in Virāṭa), so its score is
   reduced.

A gold file is always checked against the index *minus itself*
(leave-one-out), so it never vouches for its own errors.

## How a verse is checked (chandas)

1. `verse-checker` (StotraSamhita fork) is tried first. An exact metre match
   passes.
2. **Anuṣṭup** verses (16-syllable lines, any number) are judged by the śloka
   rules: even pāda ⏑–⏑ at 5–7, odd pāda pathyā or one of the four vipulās,
   and no ⏑⏑ at syllables 2–3.
3. Other verses must be **internally consistent**: same syllable count per line,
   and same laghu/guru pattern except at pāda-final syllables and the
   upajāti/epic-triṣṭubh free syllables (1 and 3). Lines with equal mātrā
   counts pass, for mātrā metres. This works for metres verse-checker does not
   know, and points at the exact line and syllable.

Severity: wrong syllable count 5, broken śloka rule 4, pattern deviation 3.

## Measured on Virāṭa Parva (original OCR vs proofread)

Gold minus Virāṭa (about 115K words, mostly stotras). 646 real word corrections;
re-spacing and anusvara/avagraha changes are excluded.

| word threshold | words flagged | precision | recall |
|---|---|---|---|
| 3 | 2,389 | 14% | 52% |
| 6 | 674 | 24% | 25% |
| 10 | 141 | 40% | 9% |

Metre flags 167 of 3,461 verses, and 50% of those contain a real error. Words ≥ 3
plus metre cover 61% of the real errors. Precision is understated, because the
"proofread" Virāṭa still contains errors that the tool flags (e.g. `पराङ्भुखम्`).
Recall will rise as the gold corpus grows.

Errors with no visible symptom are out of reach: a valid word replaced by
another valid word (शर्व for सर्व), with the metre intact.

## Workflow

1. `check` a new or in-progress text with `--sort score`, then fix from the top.
   For each flag, fix the source, `accept` the word or verse, or leave it.
2. When a text is fully proofread, `approve` it. It joins the gold corpus and
   strengthens every later check.
3. Re-run `selfcheck` now and then. A better index finds errors that remain in
   the gold texts.
