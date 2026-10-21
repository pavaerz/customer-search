# Phase 4.1 — originals saved during campaign 25

`campaign25.json.gz` contains the immutable read-only campaign 25 snapshot, its 36 commercial revisions, discovery traces, tasks, documents, execution metadata and 43 cached HTML pages. Extracted on 2026-10-18; no page was downloaded for this phase. The per-page `checked_at` is the original acquisition time. Document content hashes must be compared with `digest(text_with_legal(html))`, not with the raw HTTP HTML hash.

`implementation-report/phase41-integrity.json` records the fixture hash and checks matching document text hashes and acquisition timestamps. Historical annotations are preserved; replay output is written separately. Public evidence may contain professional names and published business contact channels. The fixture contains no API key or `.env` content and does not authorize contacting anyone.

`Saved41` in `tests/test_commercial41.py` uses actual saved cases, except the explicitly constructed Startup Bakery resolution hint (no official page was available). `Synthetic41` tests boundaries with invented `.example` / `.test` pages. Browser41 exercises real local Chromium against artificial pages and mocked access failures: it is not an audit of Brighi or Infinito.

Offline replay:

```sh
PYTHONPATH=implementation-report/offline-test-guard:. .venv/bin/python scripts/replay_commercial41.py
```

The replay uses a disposable database and saved originals only. Discovery policy, source reclassification and outbound screening are separate comparisons; historical browser measurements remain unchanged. It is neither a new campaign nor a forecast of query yield. Missing originals remain missing. The guard blocks production database access/writes and external connections.
