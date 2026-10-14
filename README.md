# Prospecto

Prospecto turns a dense university prospectus into an accessible, conversational source of information. Instead of searching through hundreds of pages, prospective students can ask natural-language questions and receive focused answers through a friendly chat interface.

The project combines a retrieval-augmented generation (RAG) pipeline with a lightweight web experience, making important admissions and academic information easier to discover.

## What Makes Prospecto Different

- **Built for university prospectuses** — the retrieval pipeline is designed around structured academic content such as programs, admissions, fees, policies, and campus information.
- **Grounded responses** — relevant prospectus sections are retrieved before an answer is generated, helping keep responses connected to the source material.
- **Layout-aware document processing** — the ingestion workflow preserves useful document structure, including sections, tables, and reading order.
- **Fast local retrieval** — processed chunks and embeddings are stored locally, avoiding repeated document parsing for every question.
- **Conversational sessions** — the API supports session-based chat so users can ask natural follow-up questions.
- **Decoupled architecture** — the TypeScript frontend and FastAPI backend can be developed, tested, and deployed independently.

## Project Structure

```text
RAG-Sentec/
|-- frontend/                 # TypeScript chat interface
|   |-- assets/               # Logos and visual assets
|   |-- src/                  # API client, state, types, and UI logic
|   `-- test/                 # Frontend API and state tests
|-- Prospecto/                # Python RAG pipeline and FastAPI service
|   |-- api.py                # Chat, health, and session endpoints
|   |-- ingest.py             # Prospectus ingestion workflow
|   |-- retrieval.py          # Semantic retrieval logic
|   |-- answer.py             # Context-grounded answer generation
|   |-- llm.py                # Gemini model integration
|   |-- evaluate.py           # Retrieval and response evaluation
|   `-- out_g/                # Processed pages, chunks, and embeddings
`-- docs/                     # Project design documentation
```

## Tech Stack

| Layer | Technologies |
| --- | --- |
| Frontend | TypeScript, HTML5, CSS3 |
| Backend API | Python, FastAPI, Uvicorn, Pydantic |
| AI and embeddings | Google Gemini |
| RAG and retrieval | NumPy, semantic embeddings, local vector similarity |
| Document processing | Docling, PyMuPDF, Tiktoken |
| Testing | Node.js test runner, Python `unittest`, HTTPX |

## How It Works

```text
University prospectus
        |
        v
Document extraction and chunking
        |
        v
Embedding generation and local indexing
        |
        v
Relevant-context retrieval
        |
        v
Gemini-powered grounded response
        |
        v
Conversational web interface
```

Prospecto demonstrates how RAG can turn static institutional documents into a practical, student-focused information experience.
