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

### 6. Case ending out of step (`casecheck.py`)
- **Question:** is a case ending out of step with grammar or with the rest of the line?
- **Two signals:**
  - **sandhi:** -o (from -aḥ) before a voiceless consonant, where it must stay -aḥ or become -aś/-as (भौमवारो च, सर्वेशो कमला);
  - **list:** a word whose ending differs from two or more others in its line, next to च / वा.
- **Why it was needed:** Gakaradi 178 read चतुर्थ्यां भौमवारो च चन्द्रसूर्योपरागके. `neardup.py` missed it because the right form, भौमवारे, is itself rare (2 copies in the corpus).
- **Catches:** body parts in a kavaca left nominative where they should be accusative duals (पार्श्वो → पार्श्वे, कर्णो → कर्णौ), and locative absolutes (प्राप्तो प्रसवकाले → प्राप्ते).
- **False hits:** u-stem vocatives (प्रभो, filtered when प्रभुः is attested), -o from अथो, and vocatives of rarer u-stems (ब्रह्मबन्धो). Every hit needs a reader.

### 7. Metre as the evidence (`metrefix.py`)
- **Question:** for a verse that does not scan, does replacing one word with a word one edit away, attested 3+ times in the corpus, make it scan?
- **Why it adds something:** both forms can be common words (सहस्रकोटि / सहस्रकोटी), which `neardup.py` cannot see. The metre is what shows which one is wrong.
- **Run it on:** the open metre rows. Trust a hit when it is the only way, or one of very few ways, to fix the verse, and the replacement is much more common than the word it replaces.
- **Caught on gold (2026-10-17):** दण्डवत्प्रणि[प]त्याह, भुमौ ×2, समरामि ×3, नाम्नामष्टोत्तर[ं], योगात्मेन, अन्योन्य-ईक्षण. Reading the flagged line turned up two more slips in the same Gaṅgāṣṭaka line, प्रायश्चितं and जलकाणिक्रा.
- **False hits:** a short common word swapped for another (नमः → नवमः, सदा → सा) can make a verse scan by accident. Mixed upajāti verses (11- and 12-syllable pādas) fail the structural check but are genuine; record them as correct.

### 8. Words run together after ः or ं (`runon.py`)
- **Question:** is a rare word really two ordinary words with the space dropped after a visarga or anusvāra (महात्मनःसदा, परेषांसर्वा)?
- **Signal:** the joined word occurs at most twice in the corpus, both halves at least 5 times each, and the two halves also occur elsewhere as separate adjacent words (the support count). Real compounds (मनःस्थितं, नभःस्थले, निःसङ्गो) rarely appear split, so they sort to the bottom.
- **Skipped:** the prefix सं-, and ं before स् (n-sandhi, as in तांस्तथा).
- **Caught (2026-10-17):** Gītā 5.12 युक्तःकर्मफलं (the Gītā word file and the Bhīṣma parva both split it), Padma बहुशःपापं, Karṇa महात्मनःसदा and परेषांसर्वा. Reading the unsupported hits also turned up a non-run-on slip: Virāṭa पुनःसरः for पुरःसरः.
- **False hits:** visarga compounds and names (स्वयंसिद्धः, तपःसक्तो) are written joined on purpose. Read the line.

### 9. A letter moved one place (`moved.py`)
- **Question:** does swapping two neighbouring letters (a consonant, a half-consonant such as र्, a vowel sign) turn a sequence the corpus never uses into one it uses often?
- **Why it was needed:** Virāṭa had हयाञ्छत्रुनिर्बहण for -निबर्हण. Every other check missed it or buried it:
  - moving र् past ब changes two code points, so `neardup.py` (one edit) cannot see it;
  - the word is a long compound, rare as a whole even when spelt right, so whole-word checks have nothing to compare it with;
  - check 1 did flag it (the trigram बहण occurs nowhere else) but ranked it 2,267th of 7,003, with a nonsense suggestion.
  The metre check flagged the verse, which is how it was found.
- **Signal:** compare only a window of letters around the swap (two either side), counted as substrings across the corpus. That works inside compounds. The window must occur at most once outside this word, and the swapped window at least 10 times.
- **Order:** swaps that move र् first. The reph typed a letter early or late is the commonest slip of this kind.
- **Caught (2026-10-17):** निर्बहण (निबर्हण ×125), क्षत्रियस्तोष्टुर्महति (-तोष्टुमर्हति), Padma जर्नादने (जनार्दने; the swap is two places, but the window still flags it), Bhīṣmastavarāja and Śānti सवर्तः (the sage संवर्तः).
- **False hits:** many, outside the र् tier (नूतने → नूतेन). The suggestion is only the swap; read the line for the real fix.

### 10. One syllable-level edit that makes a verse scan (`metrerepair.py`)
- **Question:** for a verse that fails the metre check, is there one small edit (a vowel's length, an anusvāra or visarga, a doubled consonant, a virāma added or dropped, one akṣara or one conjunct dropped) after which it scans? `--all` includes verses already recorded as correct.
- **Why it adds something:** unlike check 7, the new word need not be attested, so it works inside long compounds (दन्तपङ्कित → दन्तपङ्क्ति).
- **Ranking:** keep an edit when it lowers the word's proofreader score by 1.5 or more, or when the new word is well attested and the edit is not a deletion.
- **Result on gold (2026-10-17):** a second pass over all 239 failing verses (225 recorded correct) found no new fix among the recorded ones. Reading the 14 unrecorded verses found four real slips: Padma सुषुप्तः → सुषुपतुः (dual, "the two slept"), Vivāha Maṅgalāṣṭaka भूधराश्च → भूधराः, Dhanvantari Aṣṭottara दन्तपङ्कित → दन्तपङ्क्ति, Śiva Mahimna स्त्वद्\mbox{}ध्रुवमिं → स्त्वध्रुवमिदं. The cluster, virāma and vowel-move edits were added after that: they now find the second and third, and point at the right word for the first (सुषुपतः). A syllable inserted (मिं → मिदं) is not tried.
- **False hits:** many. Deleting a syllable often leaves a short common word (देहि → हि, सदा → स) that scans by accident, and Upajāti verses that mix 11- and 12-syllable pādas, or Purāṇa ślokas with a 17-syllable line, have no real fix. Read the verse.

### 11. A consonant doubled after repha (`repha.py`)
- **Question:** does a word double the consonant after र्, as old printings do (सूर्य्य, सर्व्व, धर्म्म, आर्त्त, मुहूर्त्त, वर्द्धित, मर्द्दल)? Gold writes it single. An unaspirated stop before its aspirate counts as a doubling (र्द्ध, र्त्थ).
- **Not flagged:** र्च्छ, because च्छ is the ordinary spelling of a medial छ (gold has मूर्च्छ- 30 times, मूर्छ- 4). Also र्द्धि from ऋद्धि (महर्द्धि, परर्द्धिः, धनर्द्धि), told apart from vardh- (वर्द्धित, वर्द्धिनी) by the letter after it.
- **Not a slip:** कार्त्तिक(ेय) is from कृत्तिका, so the त्त is etymological. Gold writes it both ways (24 doubled, 27 single), and the editor ruled both correct and not to be standardised (round B7, 2026-10-18). The check skips it. वार्त्ता (from वृत्ति) is the same case; gold writes वार्ता every time.
- **Found (2026-10-18):** 39 places in gold, 24 of them कार्त्तिक. Beyond gold, about 500 places in 120 files, most of them in Vālmīki Ayodhyā, Rāmāyaṇa-ratnākara and the Padma sources (र्त्त, र्य्य, र्ल्ल, र्म्म, र्द्द, र्प्प).

### 12. Sandhi left unmade between two words (`sandhi.py`)
- **Question:** a word written apart from the next one keeps a final sound that sandhi should have changed. The cases are: -अः before a voiced sound (रामः गच्छति), -आः or -इः etc. before a vowel or voiced consonant, सः before a consonant, a visarga before च छ त थ ट ठ (नमः त्रि-), -त्/-क् before a voiced sound (कदाचित् गौतमी), and -म् before a consonant inside a line.
- **Skipped:** a space at a pāda break, where pausa is allowed (within one syllable of the midpoint, on lines of 14+ syllables), and comments.
- **False hits to drop by eye:** prose colophons and credits (…शास्त्रिभिः विरचितं), fixed formulas (नमः इदमर्घ्यम्, श्रौषट् वौषट्, viniyoga lines such as श्रीविष्णुः ऋषिः).
- **Found (2026-10-18):** 41 hits in gold, of which about 20 are slips (पठेत् भक्ति-, विलसत् गोपी- in two copies of the same verse, त्रिशाखैः बिल्व-). Reading them also turned up शरैरर्पितः ऋद्धः (probably क्रुद्धः) and विदिक्षुः दिक्षु.

### 13. Anusvāra against the class nasal inside a word (`nasal.py`)
- **Question:** before a stop, does gold write the anusvāra (संग, कंठ) in some words and the class nasal (सङ्ग, कण्ठ) in others? Words are keyed with the nasal folded to ं, and a key written both ways is reported.
- **Found (2026-10-18):** nothing. Gold writes the class nasal 22,384 times. The anusvāra appears only in संज्ञा and its compounds (as in the Gītā), and in Hindi बंदि (Hanumān Chālīsā).

### 14. A word typed twice (`repeat.py`)
- **Question:** is a word written twice running, inside a line or across a line break within a verse? Doubling is usually meant (कुञ्जे कुञ्जे, निशि निशि, पुनः पुनः), so each pair carries how often that doubling occurs across the whole corpus, and the rare ones are listed first.
- **Skipped:** blank lines and speaker lines (\uvacha), so the last word of one verse and the first of the next (…परः पतिः / पतिः सुराणां is within a verse and stays) do not pair.
- **Found (2026-10-19):** 442 doublings in gold, none a slip; all intended repetition or anadiplosis.

### 15. A quotation that differs from its source (`quotes.py`)
- **Question:** does a line in gold that quotes the Gītā (the super-gold reference; any other text can be passed as REF) read as the Gītā does? Every line is compared with every Gītā line, spaces ignored, and a line of similarity 0.85 or more that is not identical is reported.
- **Found (2026-10-19):** 42 lines quote the Gītā exactly (20 in the Gītā Māhātmya, 8 in the Viṣṇusahasranāma, 8 in Padma Ekādaśī). Only two near-misses, both echoes rather than quotations: Padma Ekādaśī न लिप्यते स पापेन (Gītā 5.10 लिप्यते न स) and Virāṭa 77.35 …भुङ्क्ष्व राज्यं समग्रं (Gītā 11.33 समृद्धम्).

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

**Layout:** a long-metre verse (pādas of 10 or more syllables) is written as four pādas when the file writes its other long verses that way. Some stotras write every verse in two long lines; that is that text's choice, so leave it. A pāda break inside a word ends in a plain `-`, as in चित्तवृत्ति- / स्त्वन्नाम… (280 places in gold). Never use `\-`: it is an optional hyphen and does not print at the end of a pāda line.

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
- **Let the reviewer edit the whole verse, not just the flagged pāda.** The metre check flags the pāda that differs from the others, but the slip is often in another pāda (Yamāṣṭakam's extra यः, Tulasī's दानतोयविशुद्धि[दा], Gaṇeśa 108's श्रीदोऽज उत्पलकरः). Give each failing verse one row with all its pādas editable, one per line; `apply_round.py` applies such rows pāda by pāda.
- **Compare a nāmāvalī with its stotram.** Of the Aṣṭottaraśatanāma pairs, Tulasī's nāmāvalī had the right form (दानतोयविशुद्धिदायै) and Veṅkaṭeśa's had a different name (मङ्गेश for रङ्गेश): each copy catches slips in the other.
- **Point at the syllable.** A bare metre hint ("even pāda syllables 5–7 are GGL") makes the reader hunt, and the eye corrects the slip while it hunts. `meter.mark()` marks the syllables the hint is about; `proof.py check` prints them on an `at:` line, and the review page shows the verse as printed (dandas, verse number from `versenum.py`) with them highlighted. On already-decided rows the mark fell on the syllable the reviewer had changed every time. Check the metre name before trusting a hint: any verse of 16-syllable lines used to be read as anuṣṭup, which mislabelled pañcacāmara verses.
- **Tell the ārṣa licence apart.** A marked syllable with a short vowel and no ं/ः or final consonant of its own is heavy only because a conjunct follows (`meter.by_position`). When the conjunct starts the next word (नमा‹मि› श्रीविहारिणम्, नागेन्द्रहारा‹य› त्रिलोचनाय, वर्षा‹णि› द्वादश), the texts routinely let it count as light: a verse whose every mark is of this kind is likely correct, and is shown apart (dashed on the page, ‹› in `proof.py check`). A conjunct inside the word is not evidence either way: धर्नुर्धरः and वचसा गृह्णामि were slips of exactly that shape.
- **Take a second look at the rejects, with the marks.** Rejected metre rows hide slips the eye corrected on first reading. Re-scan every verse recorded as correct, keep those that still do not scan, and show the ones only slightly off first (one marked syllable). The second look at 212 such verses (2026-10-17) turned up धर्नुर्धरः, प्रवथयां, सीतशोकहर ×2, पुरूषोत्तम, वचसा गृह्णामि, सुरासुरसेवित and दन्तित्वकृत in its first 53 rows.
- **Record rejects.** A rejected word goes into `accepted.txt` ("reviewed correct") and a rejected verse into the verse list, so the same false hit never comes back.
- **Fix every copy.** When fixing a typo, grep the whole corpus for it. Copies of the same stotra and the source text (the Śānti parva for the Bhīṣmastavarāja) often share the slip.
- **Grammar is not the arbiter for epic text; the source edition (mūlam) is.** Epic and purāṇic texts keep non-Pāṇinian (ārṣa) forms. Virāṭa 5.36 reads ऋजुर्मृदुः सत्यवादो: the ऋदु for ऋजु was a typo, but सत्यवादो (not सत्यवादी) is the mūlam's reading. When the unproofread OCR copy has the same reading, flag the row as "your call" and ask for a check against the source edition.
- **For a line that is too short, look for an outside copy.** sanskritdocuments.org has many of these texts, including the Adhyātma Rāmāyaṇa (`/doc_raama/adhyaatmaRamAyo.html` for Ayodhyā). Three "off by 2+" lines turned out to have dropped words that the outside copy kept (सुमन्त्रं **मन्त्रिसत्तमम्**, क्रमेण **स्फुटम्**, भस्मसितं **सितं** च). If the outside copy has the same irregular metre, the received text is irregular: record the verse as correct.
- **Measure on a known pair.** Virāṭa Parva exists as OCR (`-orig`) and as proofread text. `proof.py eval ORIG FIXED` gives real recall figures to test a new check against.

## Running it on a new text

1. Put the new text outside gold. Run `proof.py check` on it, with gold as the vocabulary.
2. Run `neardup.py OUT.tsv new.tex`. It flags only the new text but counts words across everything.
3. Run the consistency scripts with the new file added (`consistency.py OUT.tsv new.tex`, `avag.py OUT.tsv new.tex`). This shows where it departs from house style.
4. Review, apply (`misclick.py`, then `apply_round.py`), audit, and re-run until it converges. Then add the text to gold with `proof.py approve FILE`.
