# Campaign 57 source replay

`originals.json.gz` contains four actual cached pages acquired on 20–21 October 2026: DeveloperWay home and developer invitation, and two Indie Hackers posts. Copied read-only from the local cache after Campaign 57. No network requests, edits to the originals, or synthetic commercial outcomes.

The tests separately label synthetic adversarial HTML and model responses. Offline assertions cover literal source selection, publication attribution, response controls and display semantics; they do not demonstrate new commercial leads or model performance.

`observed-response.json.gz` preserves the unchanged response from the final paid saved-original probe and its exact supplied input. At execution it failed `unexpected_action_link`; the regression test checks its offline revalidation after allowing only a cited, owner-attributed, offered signup link in a manual `REVIEW_OUTREACH`. This is not a new API execution or a modification of Campaign 57. The provider payload used for that probe precedes the final passage-priority regression fixes; final payload construction is tested separately through the actual worker.
