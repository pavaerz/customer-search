# Fase 3B — historical evidence, not synthetic labels

`campaign15.json.gz` freezes the preexisting local campaign15 report snapshot (26 revisions, 94 discovery appearances). `campaign15-pages.json.gz` contains 59 referenced documents and 59 original cached HTML pages. Export used SQLite mode=ro; every HTML matched both saved text fingerprint and canonical evidence channels/offsets. No missing page was fabricated. No credentials, cookies or tokens are included.

Historical decisions are HISTORICAL_SYSTEM_LABEL, not independent ground truth. Known KForge, DIEGOHELP, Digisourced and browser failures are diagnostic findings from CAMPAIGN-15-REPORT.md. Offline replay does not acquire pages, use paid APIs, or remeasure browser results. Test synthetic examples are labeled separately in test names.

Replay: `PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_commercial3b.py`.

`ai-extra-historical.json.gz` contains saved Inputcomm revision 707 and DSI Design careers revision 713 from campaign 13, plus four existing documents per case, exported read-only. These complement the eight campaign-15 cases in `scripts/evaluate_commercial3b.py`. Public index titles/snippets are labeled `search_index`, not fabricated original pages. Scripted MOCK responses are development fixtures, not actual model predictions or independent human labels. Precision and recall remain unknown.
