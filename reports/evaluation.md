# Actual evaluation results

Run: 2026-10-23T10:04:03.270778+00:00. Real local model: `qwen3:8b`.

Catalogue SHA-256: `1af230e1c768809f18db59434edb783b2d5d1d9ef06d4129b05d9640b4cf0465`.

All source page numbers are one-based PDF positions.

| Case | Actual answer / error | Reference | Result |
| --- | --- | --- | --- |
| q1 | The prices in this catalogue were last updated on 20-01-2025. | 2 | PASS |
| q2 | Orient BlackSwan was incorporated in 1948. | 2 | PASS |
| q3 | Not found | — | PASS |
| q4 | Not found | — | PASS |
| q5 | Not found | — | PASS |
| price_paraphrase | The catalogue's price list was most recently revised on 20-01-2025. | 2 | PASS |
| incorporation_paraphrase | The year of incorporation of Orient BlackSwan is 1948. | 2 | PASS |
| author_ayurveda | Saurav Kumar Rai wrote Ayurveda, Nation and Society. | 4 | PASS |
| author_sri_lanka | Darshi Thoradeniya | 4 | PASS |
| book_price | The catalogue price for Ayurveda, Nation and Society is `1400. | 4 | PASS |
| near_topic | Not found | — | PASS |
| unrelated | Not found | — | PASS |
| injection | Not found | — | PASS |
| empty_input | Enter a question about the catalogue. | — | PASS |

Repeat ingestion: unchanged; reused existing index (567 chunks).
Fresh bot object/index reopen: PASS.

See [evaluation.json](evaluation.json) for every exact question, actual response, full retrieved passages with distances, verified references, expectations, and pass/fail. Operational errors are recorded separately from missing evidence.

This is a small fixed evaluation set, not proof of general hallucination immunity. The expected facts are used only by this evaluation module.
