# Project explanation and viva preparation

Use the evaluation report and real screenshots to state what has actually been verified. This guide explains the design; it does not certify that every feature has passed testing.

The Gemini key is configured privately, and live embedding and structured-chat smoke checks passed. Full catalogue ingestion and answer-quality evaluation remain pending. The existing 14/14 evaluation, 32-test baseline, restart result, and five assessment screenshots were recorded using Ollama. Consult `reports/gemini-readiness.json` for the new offline checks; do not present them as Gemini answer-quality evidence.

## A 60-second explanation

“My project is the Orient BlackSwan History Bot. It answers questions using only the publisher's History catalogue for 2024–25. I extract native PDF text blocks page by page, preserve one canonical copy of repeated footers, and split text into overlapping chunks with source, page, and chunk IDs. The configured Gemini or Ollama embedding model converts the chunks into vectors stored persistently in ChromaDB.

“For a question, the application embeds the query and retrieves six relevant chunks. A LangChain prompt sends that evidence to the configured language model, which produces a structured answer and supporting quotations. The backend checks that quotations occur in the retrieved chunks, checks whether the evidence supports the answer using the full cited passages, and builds the displayed references from its own metadata.

“If the catalogue does not support the answer, the result is exactly `Not found`. Operational failures appear as errors. Streamlit provides the interface. The important distinction is that retrieval finds similar text; validation must still establish whether that text answers the question.”

## Short demonstration sequence

1. Show the README's setup instructions and the catalogue source/hash record. Explain why the edition is fixed.
2. Configure the selected providers in `.env` and run `python -m history_bot doctor`. For Gemini, enter the key privately; for an Ollama provider, start its service. Ingest once with the selected embedding configuration, start Streamlit, and show readiness. Explain that `doctor` does not validate the key with Google.
3. Ask one supported assessment question. Compare the answer, exact excerpt, and one-based PDF page with the actual PDF.
4. Ask a paraphrase. Explain that the question uses embeddings and retrieval rather than a hard-coded response.
5. Ask the Physics textbook question and one unrelated question. Show the exact unsupported response, `Not found`.
6. Open the evidence display to show retrieved text and backend source metadata. Explain that similarity alone does not prove answerability.
7. Restart the app and confirm that it reopens the persistent index. Use the recorded restart result to substantiate this claim.
8. Show the evaluation report and actual screenshots for the providers being demonstrated. Existing reports and screenshots show Ollama; a new full Gemini evaluation writes `reports/evaluation-gemini-gemini.json` and `.md`. State any failures or unexecuted checks plainly.

## Concepts in plain language

| Concept | Explanation in this project |
| --- | --- |
| RAG | Retrieval-augmented generation: retrieve relevant text from a fixed source, then use that text to answer. |
| Extraction | Reading native PDF text-block order while retaining page identity. Representative multi-column pages were inspected; there is no general column-detection algorithm. |
| Footer canonicalization | Keeping one searchable copy of an exact repeated bottom-margin notice at its earliest actual page, with the other occurrence pages recorded. |
| Chunking | Dividing a long document into smaller pieces that can be embedded and retrieved. |
| Overlap | Repeating some text at adjacent chunk boundaries to reduce the chance of separating a fact from its context. |
| Embedding | A numeric representation used to compare the meaning of a question and document text. |
| ChromaDB | The persistent vector store that holds chunk embeddings, text, and metadata. |
| Retrieval | Selecting chunks whose embeddings are close to the question embedding. |
| Grounding | Requiring the answer to follow from the supplied catalogue evidence rather than outside knowledge. |
| Metadata | Source information attached to a chunk, such as filename, PDF page index, and chunk ID. |
| Structured output | A defined response shape that the backend can inspect instead of trusting arbitrary text. |
| Entailment check | A separate model check of whether the cited evidence supports the proposed answer. It can make mistakes. |
| Abstention | Declining to answer when evidence is insufficient, represented here by exactly `Not found`. |
| Idempotent ingestion | Repeating ingestion of the same unchanged source/configuration does not silently add duplicate chunks. |

## Likely viva questions

**Why use RAG instead of asking the model directly?**  
A model may use outside knowledge or invent an answer. RAG supplies catalogue passages and makes the evidence inspectable. It still needs validation.

**What is the architecture?**  
PDF → PyMuPDF extraction → LangChain chunks → Gemini or Ollama embeddings → persistent ChromaDB → top-six retrieval → LangChain structured generation → evidence validation → Streamlit answer and references.

**Where do you use LangChain?**  
For the recursive text splitter, Chroma integration, prompt composition, and the Gemini/Ollama chat-model interfaces with structured output.

**Which models are configured?**  
The example configuration selects Gemini `gemini-embedding-001` with 768-dimensional output for embeddings and `gemini-3.5-flash-lite` for generation and the separate evidence-support check. The optional local setup uses Ollama `nomic-embed-text:v1.5` and `qwen3:8b`. Gemini chat can also be combined explicitly with local Ollama embeddings. Consult the actual `.env` or process environment before describing the active setup.

**Do you need an API key?**  
Gemini requires `GEMINI_API_KEY`, stored privately in the Git-ignored `.env` or process environment. The app explicitly uses the Gemini Developer API backend. Both providers set to Gemini require no Ollama service. An entirely local Ollama configuration requires no API key, but its models must be installed and its service running. Providers never silently fall back to each other.

**What data goes to Gemini?**  
Gemini embeddings send catalogue text during ingestion and the question during retrieval. Gemini generation sends the question and retrieved catalogue evidence for generation and validation. The catalogue remains the sole factual source; the API integration does not add web search.

**Why are the document and query tasks different?**  
The embedding model distinguishes indexed documents from search queries. Gemini `gemini-embedding-001` uses `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY`. Local Nomic embeddings use `search_document:` and `search_query:` prefixes. Both sides must use the same provider/model, compatible dimensions, and the corresponding retrieval tasks.

**Can the old Ollama index be queried with Gemini embeddings?**  
No. Equal vector dimensions do not make two embedding spaces compatible. Switching embedding providers/models or dimensions requires ingestion into the matching collection. The signature also records source and chunk/task settings. Changing only the chat model does not require new document embeddings.

**Are model weights fixed?**  
Ollama exposes a model-weight digest. Gemini exposes a hosted model ID and configuration, not an immutable weight digest. The manifest records that distinction; a hosted identity label must not be described as proof that Google's weights never change.

**What happens if Google's rate limit interrupts ingestion?**  
Successful batches stay in Chroma. Rerunning ingestion with the same source and embedding configuration skips stored chunk IDs and embeds the missing chunks. The index is marked ready only when all chunks are saved. Google's quota may count each text in an embedding batch, and the limit depends on the account/project. The provider wrapper retries explicit short-window quota failures up to three times when Google supplies a retry delay of at most 60 seconds; authentication, daily-quota, and unknown errors are surfaced. A manual retry after the limit resets can resume the remaining work without rebuilding.

**Why use 1,200 characters and 180 characters of overlap?**  
They are practical starting settings that balance useful context with selective retrieval. They are character counts, not token counts, and should be reviewed against actual catalogue passages.

**Why retrieve six chunks?**  
It gives the model several candidate passages while keeping context limited. This is a design setting, not proof that six is optimal for every question.

**Why canonicalize repeated footers?**  
The baseline retrieval returned duplicate pricing notices in all six results for some queries. Keeping a single canonical occurrence preserves the notice and its true source page while allowing other passages to be retrieved. The rule uses exact repetition, page position, and minimum text length rather than question-specific keywords.

**How is that rule defined?**  
Exact text of at least 40 characters in the bottom 6% of a page, occurring at least three times, is represented once at its earliest actual page. The occurrence pages remain metadata. Repeated body text and unique notices are retained.

**Does the closest chunk always contain the answer?**  
No. Similarity finds related language; it does not establish the exact entity, fact, or relationship requested.

**How do citations work?**  
The backend owns filename/page/chunk metadata. It validates a proposed exact quotation against a retrieved chunk, then uses that chunk's metadata to display the source. The model cannot invent an authoritative page number.

**Why show one-based PDF page numbers?**  
They match the page position a reader usually selects in a PDF viewer. Printed page labels may differ and should be distinguished if shown.

**Does a valid quotation prove a correct answer?**  
No. It proves the text exists in the retrieved chunk. The quotation must also support the requested relationship, which is why a separate support check is used.

**Does the second model check eliminate hallucinations?**  
No. It is another fallible check. Exact source validation, narrow prompts, abstention, and evaluation work together; manual inspection remains valuable.

**What happens after restarting?**  
The design reopens the persisted Chroma index. Report the actual restart test outcome rather than assuming persistence has been verified.

**What happens when the PDF changes?**  
The source hash/configuration must identify the index content. Re-ingestion should be deliberate so an old index is not silently treated as the new edition.

**Do you send the entire PDF on every question?**  
No. The PDF is ingested separately. Questions use the stored embeddings and retrieved chunks.

**Why no conversation memory?**  
The assessment asks independent catalogue questions. Passing old chat answers into new questions could introduce unsupported context. Showing previous results in the interface does not require model memory.

**What is the difference between `Not found` and an error?**  
`Not found` means the available catalogue evidence does not support the answer. An unavailable model, failed request, or broken database is an operational problem and must be shown as an error.

**Are the expected assessment answers built into the code?**  
They must not be. Expected values belong in evaluation data. Every question and suggested shortcut must run through the same retrieval and validation pipeline.

**What are the main limitations?**  
Retrieval can miss evidence; chunking can separate related text; multi-column extraction can misassociate complicated listings; and language-model support checks can fail. The fixed catalogue cannot establish current facts or subjective rankings.

## Why assessment questions 3–5 should be rejected

**3. “What is the price of a Physics textbook?”**  
The requested entity is a Physics textbook. A history book mentioning physics, a scientist, or nuclear research does not establish that entity or its price. A price attached to a nearby but different book is insufficient. Without exact supporting catalogue evidence, return `Not found`.

**4. “Who is the current Minister of Education?”**  
“Current” requires present-day evidence. The fixed History 2024–25 catalogue cannot establish a current officeholder merely by mentioning a historical politician or ministry. Outside knowledge and web searches are not allowed as answer evidence, so return `Not found`.

**5. “Which is the ‘best’ history book for a beginner?”**  
The question asks for a subjective ranking and a specific audience. Promotional language or an introductory description does not establish one single best book for beginners. Without explicit evidence supporting that claim, return `Not found`.

## Submission honesty checklist

- State supported assessment answers only after comparing actual responses and quotations with the catalogue.
- Keep expected answers separate from observed outputs in evaluation records.
- Describe unexecuted checks and failures explicitly.
- Attribute the earlier 14/14 results and five assessment screenshots to Ollama. Run and save a provider-specific Gemini evaluation before claiming Gemini passed.
- Use screenshots taken from the running application.
- Explain AI assistance transparently according to the applicable course rules. The user's brief states that AI and internet use are allowed.

## Course references

The [course repository](https://github.com/provks/GenAI) covers the basic upload → chunk → embed → store → retrieve → answer flow. Its [grounded tutor example](https://github.com/provks/GenAI/blob/main/grounded_tutor.py) demonstrates constrained outputs and uncertainty handling. These are teaching references; the actual project configuration and evaluation records determine what was implemented and verified.

Gemini integration references: [configured chat model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [embedding tasks and dimensions](https://ai.google.dev/gemini-api/docs/embeddings), and [LangChain's Google integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai).
