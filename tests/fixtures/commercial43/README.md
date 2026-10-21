# Phase 4.3 — historical validation set

`dataset.json` contains human-reviewed POSITIVE / NEGATIVE / AMBIGUOUS labels, independently assigned from the saved text, not copied from application outcomes. It covers every one of campaign 27's 81 agency traces, original Apiceweb/Parklab examples from campaign 24, selected 25/26 attribution cases and the four campaign 27 audited sites. Original URL, acquisition date, declared subject, skill, relationship, uncertainty and rationale are recorded. Null means unknown, not a negative fact.

POSITIVE means an explicit technical request or standing technical partnership attributable to an organization **at acquisition**. It does not mean an open paid commission today. Apiceweb and Parklab are the only two positive organizations in this curated set; both were already used during prior development. This is regression validation, not an independent benchmark, not a representative market sample and not evidence of commercial conversion.

NEGATIVE is scoped to the examined source: service pitches, wrong subjects/roles, generic listings, institutional information or excluded targets. It is not a claim that a whole company never hires. AMBIGUOUS includes generic collaboration snippets, hosted vacancies without resolved clients, and companies whose website needs remain unproven.

`campaign25.json.gz`, `campaign26.json.gz`, `campaign27.json.gz` preserve saved traces, revisions, original HTML, documents and tasks. Campaign 24 uses `../commercial40/campaign24.json.gz`. Original pages are checked against the saved document's **extracted text hash** (which differs from the raw HTML hash); dates are not renewed. Missing originals are not synthesized. Graphalia and Domilea have search metadata only. Startup Bakery's official ATS link is saved, but the ATS vacancy content is absent.

Synthetic tests in `test_commercial43.py`, `browser43_harness.py` and `test_commercial_browser43.py` are separate and do not count as real examples. The browser harness simulates a cancellable slow resource and executes real local Chromium without external transport.

Run from the repository:

```bash
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python scripts/replay_commercial43.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -m unittest test_commercial43 test_commercial_browser43
```

Replay invokes admission, original-source inspection, identity, classification, qualification and the commercial view with saved input. It cannot rerun Google discovery offline. Missing originals stop that branch. Browser results remain historical; no real audit is simulated as successful. No production database, provider, AI, email, or campaign starts are involved. The before replay uses the same dataset with the baseline code restored into an isolated temporary directory from the verified backup.
