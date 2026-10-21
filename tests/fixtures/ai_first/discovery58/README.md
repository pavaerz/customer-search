# Campaign 54 discovery and validation replay

`company-receipts.json`: the nine actual AZIENDE search receipts of Campaign 54, read from the local database without writes. They are search metadata, not original evidence or qualified companies.

`short-query-results.json`: the first of the two separately authorized post-campaign Serper probes. Seven results; company relevance was reviewed from metadata only. No original reads or qualification are implied.

`invalid.json`: six saved invalid AI responses from the private diagnostic excerpts, paired with their original evidence segments. Existing diagnostic redaction is preserved. Campaign 54 output is not modified. The tests reconstruct the minimum validation context and test institution negatives and geography independently where full link/owner context is not captured.

Synthetic boundary cases in test_objective_discovery58.py are explicitly labelled; no mock result is a real commercial opportunity.
