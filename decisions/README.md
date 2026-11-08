# decisions/

One file per review round, written by `proof.py review` (and `proof.py import`):

```
<round>.json        {"round", "rows": "<round file>", "applied": [ids], "decisions": {"<id>": {...}}}
<round>.rows.json   the round's rows, for rounds that arrived by pull request
```

Each decision is `{round, id, status (accept|reject), category, rule, file, line,
occ, current, proposed, decidedAt}`. Nothing in it says who made it.

Rounds come here two ways:

- **Reviewed here:** `proof.py review ROUND.json`, then `proof.py apply ROUND`.
  `applied` lists the decisions already applied.
- **By pull request from a reviewer:** `proof.py submit ROUND` on their side adds
  `<round>.json` and `<round>.rows.json`. After merging, run `proof.py apply ROUND`
  to apply the edits to texts here, and send the rejects to `accepted.txt`. If the
  texts are the reviewer's own, not ones here, use `proof.py apply ROUND --keeps-only`:
  it keeps the reviewed-correct readings and the split labels and leaves the texts alone.

`*.apply.csv` (what `apply` last wrote) and `*.tmp` are not committed.
