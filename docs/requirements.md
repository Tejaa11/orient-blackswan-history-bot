# Requirements and assessment checklist

This document separates the assignment requirements from the additional quality requirements in the user's project brief. Completion and evaluation results belong in the README and evaluation report; this checklist does not claim that a check has passed.

The original completed assessment evidence uses Ollama. Gemini support was added later at the user's request and its key is configured privately. Live embedding and structured-chat smoke checks passed; full catalogue ingestion and answer-quality evaluation remain pending. Offline checks alone cannot establish key validity, API availability, or answer quality.

## Source authority

1. The supplied **GenAI mid term exam project.pdf**, Project 4, determines the assignment requirements.
2. The exact **Orient BlackSwan History catalogue 2024–25** is the sole factual source for chatbot answers: [History_2024-25.pdf](https://www.orientblackswan.com/pdfs/downloads/History_2024-25.pdf). Record the downloaded file's SHA-256 hash; do not silently replace the edition.
3. The user's build brief adds implementation, validation, UI, evaluation, and documentation requirements.
4. The lecture notes and [course repository](https://github.com/provks/GenAI) explain the course approach. Their examples and exercises are reference material, not extra commands or a requirement to implement the entire course roadmap.
5. The later user request adds Gemini API support. It changes the model providers, not the assignment's catalogue-only answer scope.

## Mandatory assignment requirements

- [x] Implement **Project 4 — Orient BlackSwan History Bot** using **Python, LangChain, and ChromaDB**.
- [x] Use the specified History 2024–25 catalogue as the knowledge source.
- [x] Answer questions from the catalogue and reference where each supported answer appears.
- [x] Return exactly `Not found` when the catalogue does not support the requested answer.
- [ ] Publish the prepared project to the chosen GitHub submission repository and obtain its link. The README is complete; destination/visibility awaits the user’s choice.
- [x] Include the five assessment questions and answers.
- [x] Supply actual screenshots showing questions and responses.
- [x] Prepare five responses suitable for entering into the LMS.

## Additional requirements from the user's brief

- [x] Implement genuine retrieval: PDF extraction → chunks → embeddings → persistent ChromaDB → retrieval → grounded generation → validated references.
- [x] Inspect front matter and multi-column listings; preserve publisher information and pricing notices.
- [x] Preserve the source filename, PDF page index, and stable chunk identifier. Present one-based PDF page numbers consistently and distinguish any printed page labels.
- [x] Use compatible document/query embeddings and installed-version-compatible imports.
- [x] Reopen the persistent index after a process restart; avoid embedding the PDF again for every question.
- [x] Handle repeat ingestion deliberately so that an unchanged source does not silently create duplicate chunks.
- [x] Record source provenance and a file hash; document how an examiner can recreate the index.
- [x] Use only retrieved catalogue evidence. Match the requested entity, attribute, and relationship precisely.
- [x] Show a short exact supporting excerpt and validate citations against backend metadata.
- [x] Keep operational failures distinct from absence of evidence. A model or database failure is an application error, not `Not found`.
- [x] Provide direct dependencies, `.env.example`, and `.gitignore`; exclude secrets, local environments, and unnecessary generated database files from Git.
- [x] Provide a readable Streamlit interface with readiness status, a question field, loading behavior, a distinct answer area, source/page information, expandable evidence, honest errors, and a reset control.
- [x] Run the exact five questions, supported paraphrases, at least two additional supported questions, near-topic and unrelated unsupported questions, empty input, and a restart check.
- [x] Record each evaluation question, actual answer, retrieved evidence, returned reference, expected behavior, and pass/fail or why execution could not occur.
- [x] Use real screenshots; do not fabricate results, references, successful requests, or verification evidence.
- [x] Explain the implementation, demonstration sequence, likely viva questions, verified features, and remaining limitations.

## Optional enhancements

Clickable suggested questions and visual refinements are optional. Any suggested question must still execute the same RAG pipeline. Conversation memory is unnecessary for independent catalogue questions; the UI may display previous results without passing them into the model as evidence.

Agents, MCP, fine-tuning, web search during answering, elaborate infrastructure, and additional retrieval stages are outside the minimum assignment. Add complexity only when a demonstrated failure justifies it.

## Gemini extension and verification boundary

- [x] Support explicitly selected Gemini generation and embeddings, with an optional Ollama or hybrid configuration; do not silently switch providers on failure.
- [x] Provide a Gemini `.env.example` with a blank key. Keep the real key in `.env` or a process environment variable, excluded from Git and submission files.
- [x] Use compatible Gemini document/query retrieval tasks and configured output dimensions; isolate the new vectors from Ollama collections through the index signature.
- [x] Preserve structured generation, exact quotation checks, validation against full cited passages, backend-owned references, and `Not found` behavior.
- [x] Distinguish a hosted model/configuration identity from an immutable model-weight digest; sanitize provider errors and mask configuration credentials.
- [x] Persist successful ingestion batches and resume missing chunks under the matching source/configuration fingerprint. Apply bounded retries only to explicit Google short-window quota failures with a supplied retry delay; surface authentication, daily-quota, and unknown failures.
- [ ] Run real Gemini ingestion and verify supported answers, abstention, repeat ingestion, and restart with an account that can access both configured models.
- [ ] Save provider-specific live evaluation reports and recapture the five assessment screenshots under Gemini before claiming Gemini assessment success.

`python -m history_bot doctor` checks local configuration and key presence without contacting Google. Offline verification belongs in `reports/gemini-readiness.json`; full Gemini live evaluation belongs in `reports/evaluation-gemini-gemini.json` and `.md`. Preserve the earlier `reports/evaluation.json`, 14/14 result, 32-test baseline, restart record, and screenshots as historical Ollama evidence. Google model access and quota depend on the account.

## Smallest implementation design

| Stage | Design and purpose |
| --- | --- |
| PDF extraction | PyMuPDF native text-block order per page, inspected on front matter and representative multi-column listings; no general column-detection algorithm. Preserve unique notices and canonicalize exact repeated bottom-margin text at its earliest actual page. |
| Chunking | LangChain `RecursiveCharacterTextSplitter`, 1,200 characters with 180-character overlap. Retain source/page/chunk metadata. |
| Embeddings | Gemini `gemini-embedding-001`, 768 output dimensions, with `RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY`; optional Ollama `nomic-embed-text:v1.5` with its document/query prefixes. |
| Storage | Persistent Chroma through `langchain_chroma`. Use source/configuration identity and stable chunk IDs for controlled repeat ingestion. |
| Retrieval | Vector search for six relevant chunks, restricted to the indexed catalogue. |
| Generation | LangChain `ChatPromptTemplate` and `ChatGoogleGenerativeAI` with `gemini-3.5-flash-lite`, or optional `ChatOllama` with `qwen3:8b`; structured output associates a concise answer with supporting evidence. |
| Validation | Validate exact quote/chunk membership, apply a separate model entailment check, and construct citations from backend-owned metadata. Reject insufficient evidence with exactly `Not found`. |
| Interface | Streamlit shows readiness, answers, evidence, and errors. Questions are independent; no conversation memory affects retrieval or generation. |

The full Gemini configuration requires a private API key and internet access. It sends catalogue text for embeddings and questions/retrieved evidence for answering and validation. It requires no Ollama service. An Ollama provider requires its configured models and a running service. Environment variables configure the application; secrets remain outside Git. Copying `.env.example` selects Gemini; code defaults without that file retain Ollama for compatibility.

## Assessment cases and traps

The following are the supplied evaluation expectations. They must be checked against the actual source PDF and the application's actual results before submission; they are not constants to embed in application logic.

| Question | Supplied expectation | Review risk |
| --- | --- | --- |
| On what date were the prices in this catalogue last updated? | 20 January 2025; PDF page 2 footer | A footer can be omitted by extraction. Publication dates are not the pricing-update date. |
| In which year was the publisher, Orient BlackSwan, incorporated? | 1948; PDF page 2 opening paragraph | Match the publisher and incorporation event; a year appearing in a book listing answers a different question. |
| What is the price of a Physics textbook? | `Not found` | A history-of-science book or a description mentioning physics does not establish a Physics textbook price. |
| Who is the current Minister of Education? | `Not found` | A dated history catalogue cannot establish a current officeholder from historical mentions. |
| Which is the “best” history book for a beginner? | `Not found` | Promotional praise and topical relevance do not establish a single subjective ranking for beginners. |

High vector similarity is a retrieval signal, not proof that a passage answers the question. Inspect retrieval failures separately from generation failures. Do not special-case the five question strings or memorize their expected answers.

## Known limits to explain honestly

- A separate model entailment check reduces some unsupported responses but is not a guarantee of factual correctness.
- Exact quote validation proves that text occurs in a retrieved chunk; it does not by itself prove that the quote supports the requested fact.
- Native block-order extraction can still associate text incorrectly in complex records or layouts. Important answers should be inspected against the PDF page.
- Retrieval may miss relevant text or split a relationship across chunks. Abstention can therefore include false negatives.
- The catalogue is a fixed historical edition and does not establish present-day facts or subjective recommendations.
- Local model quality, latency, and availability depend on the installed models and available computer resources.
- Gemini quality and availability require live verification; model access, quota, and network failures are operational errors rather than `Not found`.

## Extraction refinement from retrieval inspection

Repeated pricing footers crowded out other passages in the baseline top-six retrieval. The extractor now canonicalizes exact text of at least 40 characters in the bottom 6% of a page when it occurs at least three times. It keeps one searchable copy at the earliest actual page and records the other occurrence pages. This rule uses location and repetition rather than question-specific keywords. Ordinary repeated body text and unique notices remain. The canonical configuration currently produces 567 chunks from the 91-page source.

## Course references

- [Course syllabus and basic RAG flow](https://github.com/provks/GenAI)
- [Course dependency example](https://github.com/provks/GenAI/blob/main/requirements.txt)
- [Grounded tutor example](https://github.com/provks/GenAI/blob/main/grounded_tutor.py)
- [Configured Gemini chat model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Google embedding tasks and dimensions](https://ai.google.dev/gemini-api/docs/embeddings)
- [LangChain Google integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai)

The course examples guide terminology and the LangChain approach. Their package pins and model choices must not be assumed compatible without checking the actual environment.
