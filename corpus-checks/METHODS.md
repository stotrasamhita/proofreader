# Proofreading methods

These are the ideas used to bring the gold corpus to a clean state (October 2026), written down so they can be reused on texts that are not yet proofread. Each check asks a different question, so each one finds errors the others miss. The scripts in this folder run on gold by default. Most take extra files or a target list.

`proof.py` (see ../README.md) has the per-word and per-verse checks. The scripts here are corpus-wide checks for **consistency** and **near-misses**.

## Checks that find errors

### 1. Unlikely letter sequences (`proof.py check`, `selfcheck`)
- **Question:** does this word contain letter sequences (trigrams) that the rest of the corpus never uses?
- **Catches:** OCR damage, impossible clusters, an independent vowel inside a word (बहुऋक्ष).
- **Blind spot:** it misses a typo made only of ordinary sequences (रघावौ: रघा and घाव are both common). Check 2 covers that.
- **Leave-one-out:** score each file with its own words removed from the counts. Otherwise a typo counts as evidence for itself.

### 2. One-keystroke slips (`neardup.py`)
- **Question:** is this rare word one edit away from a common word? An edit is one letter changed, added, dropped, or two neighbours swapped.
- **Counts come from every text in the repos, not just the target.** Gold has राघवौ only twice; the whole corpus has it 85 times.
- **Leave out unproofread OCR copies** (`-orig.tex`) from the counts. They repeat the same errors and make a typo look attested: गोङ्गेयो only surfaced once the Virāṭa `-orig` file was excluded.
- **Require context support.** The common word should appear somewhere next to the same neighbour word (सह राघवौ). Without that, almost every hit is a real word one letter from another (रमया/मया, करालं/कालं).
- **Ranking:** edits inside the word first, then edits in the last two letters. Those are mostly case endings (राघवं/राघवौ).
- **Caught on gold:** 11 clear slips that every earlier round missed, including दुष्ट्वा, श्रूत्वा, माहामुनिः, सुग्रिवेण, विनिर्भुक्तो, गोङ्गेयो and कावरी.

### 3. Metre (`proof.py check`, chandas)
- **Question:** do the lines of a verse scan alike?
- **Order rows by severity** (`sev.py`):
  1. lines off by 2+ syllables (text missing or doubled);
  2. off by one;
  3. same length but the light/heavy pattern differs.
- Mātrā differences count half.
- **Expect false hits:** songs in loose metres (Bhaja Govindam, Liṅgāṣṭakam), and genuine irregularities (in the Gītā). A reject records the verse as fine (`proof.py accept --verse`).

### 4. Same verse, different readings (`proof.py dupes`)
- **Question:** a verse that appears in two texts (an Adhyātma Rāmāyaṇa stotra and its stotra-sangrahah copy) should read the same. Where it doesn't, one copy is wrong.

### 5. Split model (`splitmodel.py`, `loo.py`)
- **Question:** at each halanta junction (तत् सर्वं / तत्सर्वं), would the house practice split or join?
- **Training:** labels from reviewed decisions (`labels/split-labels.jsonl`).
- **Keep only halanta-junction labels.** Other rows that a round adds pollute the training set.

### Not yet built: case agreement in a list
Gakaradi 178 read चतुर्थ्यां भौमवारो च चन्द्रसूर्योपरागके: a nominative among locatives, for भौमवारे. `neardup.py` missed it because the right form is itself rare (2 copies in the corpus). A check could flag a word whose ending differs from its neighbours in a च-list, where swapping the ending would make them match.

## Checks for consistency (the same word written two ways)

Each of these finds one word in two forms. One form is chosen and the other is changed to match. When both forms are legitimately different words (ते न / तेन, तत् त्वं / तत्त्वं), a recorded sign-off settles it.

| Script | What it compares |
|---|---|
| `consistency.py` | a halanta pair written apart in one place and joined elsewhere; spellings that differ only in avagraha (वापि / वाऽपि) |
| `gate.py` | groups by the left word: is `X्` written apart in some places and fused in others? |
| `fullpairs.py` | **every** adjacent pair, not only halanta junctions: नमोऽस्तु ते / नमोऽस्तुते, राम रामेति / रामरामेति. The halanta-only checks missed these. |
| `avag.py` | elisions the house avagraha rule says to mark (or not): ā+a → ाऽ, a/ā+ā → ाऽऽ, e/o+a → ेऽ/ोऽ, a+a unmarked, never inside a compound |
| `broken_compounds.py` | a bare a-stem written apart from the next word, where the stem never stands alone or the joined form exists |

**False hits to filter:**
- The space at a pāda break is not a choice. Skip a space within half a syllable of the line's midpoint on verse lines of 14 or more syllables.
- Hyphens and `\mbox{}` are typesetting, so count them as joined.
- Look-alikes are different words: ते न / तेन, स ह / सह.

**Arbiter:** follow a reference text the editor trusts most (here the Gītā, with `gita/words/gita-words.tex` as a fully split copy). Then follow grammar, then the majority. Still surface disagreements with the arbiter, because it has rare slips too.

## Process safeguards

- **Sign-off rule:** never apply a change that would leave the same word in two forms without the editor's explicit sign-off. A reject in a consistency round counts as a sign-off. Keep the list of sign-offs so later scans don't re-raise them.
- **Mis-click check before applying** (`misclick.py`). It flags:
  - stale rows (the line changed since the round was built);
  - proposals the reviewer typed in (check verse lines still scan);
  - the same change accepted in one place and rejected in another;
  - undecided rows.
- **Audit after applying** (`audit.py`). It flags:
  - the same junction decided both ways;
  - a decided form that a later edit undid;
  - the opposite form still standing elsewhere.
- **Re-run everything after each round.** Fixes create new inconsistencies, for example a round-13 accept that split प्राची सरस्वती in one place only. Repeat until every scan is empty or fully signed off.
- **Record rejects.** A rejected word goes into `accepted.txt` ("reviewed correct") and a rejected verse into the verse list, so the same false hit never comes back.
- **Fix every copy.** When fixing a typo, grep the whole corpus for it. Copies of the same stotra and the source text (the Śānti parva for the Bhīṣmastavarāja) often share the slip.
- **Grammar is not the arbiter for epic text; the source edition (mūlam) is.** Epic and purāṇic texts keep non-Pāṇinian (ārṣa) forms. Virāṭa 5.36 reads ऋजुर्मृदुः सत्यवादो: the ऋदु for ऋजु was a typo, but सत्यवादो (not सत्यवादी) is the mūlam's reading. When the unproofread OCR copy has the same reading, flag the row as "your call" and ask for a check against the source edition.
- **Measure on a known pair.** Virāṭa Parva exists as OCR (`-orig`) and as proofread text. `proof.py eval ORIG FIXED` gives real recall figures to test a new check against.

## Running it on a new text

1. Put the new text outside gold. Run `proof.py check` on it, with gold as the vocabulary.
2. Run `neardup.py OUT.tsv new.tex`. It flags only the new text but counts words across everything.
3. Run the consistency scripts with the new file added (`consistency.py OUT.tsv new.tex`, `avag.py OUT.tsv new.tex`). This shows where it departs from house style.
4. Review, apply (`misclick.py`, then `apply_round.py`), audit, and re-run until it converges. Then add the text to gold with `proof.py approve FILE`.
