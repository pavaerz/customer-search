# Campaign 34 / Phase 34.1 fixtures

`saved.json` comes exclusively from the local saved Campaign 34 ledger: public snippets, valid structured outputs and diagnostics. No invalid raw response was retained by that campaign. No credentials or live fetches.

Tests recreate one deliberately invalid Mate citation to exercise its observed error class. That response is a controlled counterexample, not a recovered model output. E89's snippet is real saved evidence; no original E89 page was fetched during Campaign 34 or this work.

`original-synthetic.html` is a fictional Alfa Srl document for `alfa.example`. Its identity, date, request, budget, address and email exist only for the offline pipeline test. It is not a real lead. The pilot simulates a read failure for E89 and never substitutes this fictional document for a real company's page.
