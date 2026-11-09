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

## Without the StotraSamhita repos

The proofreader checkout alone is enough. `gold-index.json.gz` (about 2 MB) holds
what the checks need from gold: per-file word counts, spellings and word pairs.
The texts themselves are not needed.

```sh
./proof.py setup        # once: fetches verse-checker into vendor/, builds index/ from gold-index.json.gz
./proof.py check gh:stotrasamhita/stotra-sangrahah:stotras/nadi/GangaStotram.tex
./proof.py check https://github.com/OWNER/REPO/blob/BRANCH/path/to/file.tex
./proof.py round gh:OWNER/REPO@v1.2:chapters --id R1 --out round-R1.json   # --ocr OCR.txt: PDF pages
./proof.py review round-R1.json        # or: proof.py site round-R1.json --out DIR
./proof.py apply R1                    # edits the fetched copy: git -C work/REPO diff
```

A round has three sections: **Metre**, **Consonant splits** (a consonant-final word
run into the next, written apart by house rule: `corpus-checks/freeword.py` and
`tjoin.py`; needs the gold texts, so it is skipped without the repos; `--no-splits`
leaves it out) and **Words**. Every row carries `chap` (the text, its section and
verse number), and the review page has a drop-down to show one text at a time.
Given the print's OCR with `--ocr OCR.txt` (one file, each page headed
`### NNNN.json`, NNNN the PDF page), each row also gets that PDF page and the
print's line, shown on the page (`~` = near it: the line is not in the print);
type a page number in the search box to list that page's rows.

A source is `gh:OWNER/REPO[@REF][:PATH]` (a file, a folder, or the whole repo)
or a GitHub link to one. It is fetched into `work/REPO/` as a shallow clone of
just the .tex/.txt/.md files asked for. A round built from it records `work/` as
its root, so `review` and `apply` find the files again. Private repos work
wherever git is signed in to GitHub. A fetched copy with local edits is used as it
is, never re-fetched over.

`gold-index.json.gz` is a snapshot, refreshed by hand at a meaningful point,
for example a gold tag or a closed round, not on every build:

```sh
./proof.py gold-index --label gold-2026-11-08   # from each gold repo's committed HEAD
```

It reads committed `HEAD` only, never a working tree, warns about unpushed
commits, and records each repo's commit. `proof.py build` touches only your
local `index/`. A local index built from the texts is never replaced by the
snapshot; on a checkout without the texts, the local index follows the snapshot.

### Sending a review back

```sh
./proof.py submit R1 --dry-run     # what would be sent
./proof.py submit R1               # opens a pull request to stotrasamhita/proofreader
```

`submit` needs the GitHub CLI (`gh auth login`). It adds `decisions/R1.json` and
`decisions/R1.rows.json` in one commit on a `review/R1` branch, on a fork if you
can't push to the repo, and opens the pull request. The commit is credited to
your GitHub no-reply address. If the round id is taken, use `--as R1-yourname`.
The editor merges it and runs `proof.py apply R1`, or `--keeps-only` when the
texts were your own: then only the readings you marked correct and the split
labels are taken, and your texts stay yours to edit (`proof.py apply R1` on your side).

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

## Review a built round

A round is a list of proposed edits written by a builder (`[{id, round, category,
rule, file, line, occ, current, proposed, context, note}, …]`), or a review
page's `edits.json` (`{title, rounds: [{round, label, title, rows}]}`).

```sh
./proof.py review review/phaseE/rounds/round-E1.json      # then open http://127.0.0.1:8766/
./proof.py apply E1 --dry-run                              # what would change
./proof.py apply E1                                        # do it
```

`review` serves the shared review page (`proofreader/round.html`) and saves each
decision to `decisions/<round>.json` as you click. `apply` then

1. runs the mis-click check (`corpus-checks/misclick.py`) and stops on stale or
   mixed decisions (fix them on the page, or sign them off with `--force`);
2. applies the accepts (`corpus-checks/apply_round.py`, whole verses pāda by pāda)
   and appends split labels;
3. writes each reject to `accepted.txt` as `word  # E1-12 reviewed: kept as printed`
   (a rejected verse as `meter: <its first line>`).

Applied decisions are recorded in the decisions file and skipped next time, so a
long round can be decided and applied in parts. A row that cannot be applied is
reported for a hand edit; mark it done with `--skip 12,15`. `review --import DIR`
first loads decisions exported from a Claude review page (one JSON per doc). The
same `round.html`, published with an `edits.json` as a Claude artifact, saves to
the artifact's database instead. No reviewer identity is stored anywhere.

### Without a server

```sh
./proof.py site review/phaseE/rounds/round-E1.json --out /tmp/e1            # index.html + edits.json
./proof.py site round-E1.json round-C3.json --out /tmp/rv --inline          # one file, opens from disk
./proof.py import review/phaseE/rounds/round-E1.json ~/Downloads/decisions-E1.json
./proof.py apply E1
```

`site` writes a static copy of the page for any web host (or, with `--inline`, a
single HTML file to send to a reviewer). Opened there, the page keeps decisions in
that browser; **Export decisions** saves them as `decisions-<round>.json`, which
`proof.py import` merges into `decisions/<round>.json` (an imported decision wins,
except over one already applied). The page's **Import decisions…** loads such a
file back, e.g. to carry on in another browser. `import` also reads a directory of
docs exported from a Claude page.

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

`house-words.txt` lists spellings decided once for everywhere
(`जगत्कृत्स्न = जगत् कृत्स्न`, `त्वत् प्रियार्थ = त्वत्प्रियार्थ`). A rule matches at the
start of a word, whatever the ending, and is applied as a mechanical fix.

On the Virāṭa diff, split flags match the editor 85% of the time and
avagraha 95%. The review page has a *House style* mode with an
"Apply all mechanical" button.

### Learned splits

The split rule only proposes what the gold vocabulary is sure of. The rest
are ranked by a small model trained on reviewer decisions
(`labels/split-labels.jsonl`) and the Virāṭa editor's practice. It learns,
for example, that a split after तद्/जगत्/श्रीमत् is usually a compound
(kept joined) and one after भवेत्/स्यात् or before तु is not. On held-out
decisions, 88% of its p ≥ 0.5 suggestions were accepted.

```sh
./proof.py splits --out splits.csv          # gold files, p >= 0.3, most likely first
./proof.py splits --train --out splits.csv  # retrain after adding labels
```

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
| `corpus-checks/` | Corpus-wide consistency and near-miss checks, plus the round tools (mis-click check, apply, audit). `corpus-checks/METHODS.md` lists every proofreading method used so far and how to run them on a new text. |
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
