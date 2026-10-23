# Catalogue extraction review

The exact publisher URL supplied in the project brief was downloaded. The source record is [catalogue_source.json](../data/catalogue_source.json). The downloaded PDF has **91 pages**, despite the assignment's approximate “~80 pp” description. It opens without PDF repair. No other edition was substituted.

SHA-256: `1af230e1c768809f18db59434edb783b2d5d1d9ef06d4129b05d9640b4cf0465`

## Checks performed

- The assignment's fourth page was extracted and rendered to confirm Project 4 and the five questions.
- Catalogue PDF page 2 was rendered and compared with text extraction. The opening paragraph establishes incorporation in 1948; the footer establishes the price-update date as 20-01-2025 and states that prices can change without notice.
- PDF page 4 contains two illustrated book entries. Native PDF text-block order retains each entry's heading, author, description, contents, and bibliographic line.
- PDF page 11 is a three-column listing, with printed page number 8. Text extraction follows the catalogue's native block sequence rather than sorting rows across columns. This preserves reading order on the inspected page, including entries continued between columns.
- The cover has no extractable text. The next contents image has a text footer; image text is not OCR-processed. Ninety PDF pages have at least some extractable text. The bot does not claim OCR coverage.
- The currency glyph in bibliographic lines extracts as a backtick, e.g. `` `1400 ``. The rendered PDF confirms this is the rupee symbol. Exact evidence retains the extracted glyph; generated answers may label the currency in words.

## Retrieval-driven correction

The first index had 587 chunks. A real price-update query retrieved six copies/fragments of the same repeated footer, crowding out other context. The final index contains **567 chunks** after a general correction: text blocks in the bottom 6% of a page that match exactly on at least three pages are represented once, on the first actual occurrence. The canonical document retains every original occurrence in `repeated_pdf_pages`.

The price notice's first occurrence is PDF page 2. Its text remains unchanged, including the subject-to-change notice. No question strings or expected answers select the canonical footer. Book body text and repeated series labels are retained. Synthetic PDF regression tests verify footer provenance, retained body text, native ordering, and unique stable chunk IDs.

## Metadata and limits

Every chunk has a filename, zero-based `pdf_page_index`, one-based `pdf_page`, PDF label, character start index, page-local chunk index, ID, and source hash. The interface cites **PDF positions**, not printed page labels. For example, PDF page 4 has label 1; PDF page 11 has label 8.

This is native text-block extraction with representative visual checks, not automatic column recognition or a guarantee that every complex record is reconstructed perfectly. Long entries can cross chunk or page boundaries. Retrieval and generation are evaluated separately; users should inspect the original PDF for critical details.
