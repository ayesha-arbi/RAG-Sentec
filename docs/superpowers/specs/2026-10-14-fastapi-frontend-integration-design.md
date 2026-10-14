# FastAPI–Frontend Integration Design

## Objective

Connect the existing TypeScript frontend in `frontend` to the FastAPI application in `Prospecto` without redesigning the interface. The browser must use the backend for every assistant response, preserve server-side conversation continuity, expose useful loading and failure states, and contain no demonstration messages, canned replies, simulated delays, or fabricated application data.

## Existing System

The backend exposes these routes from `Prospecto/api.py`:

- `GET /health` returns `{ status, chunks_loaded }` and reports `503` until the retrieval index is available.
- `POST /chat` accepts `{ question, session_id?, rewrite, k }` and returns `{ session_id, answer, sources, standalone_question }`.
- `DELETE /chat/{session_id}` clears server-side conversation history and returns `{ cleared }`.

The frontend is framework-free TypeScript compiled by `tsc`. `app.ts` binds browser events, `state.ts` owns application state, `ui.ts` renders the interface, and `data.ts` currently supplies demonstration messages and notes. The composer currently produces a simulated assistant reply after a timeout.

## Architecture

Add a focused `frontend/src/api.ts` module as the browser/backend boundary. It will own the TypeScript request and response contracts, API base URL normalization, JSON requests, response validation at the fields consumed by the UI, and conversion of non-successful responses into readable errors. The fetch implementation will be injectable for tests while defaulting to the browser's native `fetch`.

The API base URL will be read from a meta element in `frontend/index.html`, with `http://localhost:8000` as the local-development default. This keeps the existing plain TypeScript build and static-server workflow; changing environments will require editing deployment HTML rather than recompiling source.

`StateStore` will remain the single state owner. It will gain the active backend session ID, request/loading status, backend readiness status, and current error. Assistant messages will optionally carry backend source chunks and the standalone question. No backend response will be synthesized or replaced by a local fallback.

## Initial State and Removal of Fake Data

The initial message and notes collections will be empty. The frontend will not display the current consciousness-themed conversation, sample notes, sample media, or sample code. The canned response array and response timeout will be deleted.

The static fake conversations in the chats drawer will be replaced with an honest empty/current-session state. The canned “summarize” note action will be removed because no summarization API exists. User-created notes, links, highlights, filtering, grouping, themes, panel resizing, sharing, and other functionality that operates on real user data will remain.

The chat title will use a neutral Prospecto title until the user starts a conversation. It may be updated from the first user question, but it will not be seeded with demo subject matter.

## Data Flow

On page load, the frontend calls `GET /health`. While health is unresolved, the composer communicates that the backend is being checked and prevents submission. A successful health response enables the composer. A failed or unavailable health response leaves the existing interface visible, shows a concise retryable error, and does not invent any chat content.

On valid form submission:

1. Add the user's question to state immediately.
2. Clear any previous request error, mark the request as loading, and disable duplicate submission.
3. Call `POST /chat` with the trimmed question, the stored session ID or `null`, `rewrite: false`, and `k: 8`, matching backend defaults explicitly.
4. Store the returned session ID.
5. Add the returned answer and source chunks as the assistant message.
6. Clear loading state and restore composer focus.

If the request fails, the user's submitted message remains, no assistant message is fabricated, loading ends, and an inline error describes the server detail when available or a concise network failure otherwise. The user can retry by submitting again.

Starting a new chat calls `DELETE /chat/{session_id}` when a session exists, then clears local messages, sources, errors, and the local session ID. If server cleanup fails, the frontend still discards the local session ID so subsequent questions cannot accidentally continue the old conversation; it reports the cleanup failure without blocking a fresh chat.

## Rendering and Interaction

The existing typing indicator becomes a state-driven loading indicator rather than an independently appended temporary DOM element. The composer input and submit button are disabled during health checking and chat submission, with accessible status text and `aria` attributes.

Assistant text remains escaped through the existing renderer. Source chunks appear beneath the associated answer in a compact disclosure section using the current visual language. Each source displays its section, page or page range, score, and excerpt. Empty source arrays render no disclosure. Backend error text is escaped before rendering.

Existing UI layout, glass themes, note cards, filters, modals, rails, and resizing behavior remain visually unchanged except where fake-data controls need an honest empty state and where loading, error, and source elements are added.

## Error Handling

The client distinguishes these cases:

- Backend JSON error with a FastAPI `detail` string: display that detail.
- Backend non-success response without a usable detail: display a status-based error.
- Network failure or unreachable API: display a connection error naming the configured API URL.
- Malformed success payload: display an invalid-response error rather than inserting partial data.
- Health `503`: report that the index is not ready and allow health retry.

Errors are application state, not browser alerts, so rerenders cannot silently erase them and tests can assert their behavior.

## Backend Scope

The existing API contracts and RAG behavior remain unchanged unless tests expose a narrowly necessary integration issue. CORS remains enabled for the separately served local frontend. Any backend adjustment will preserve response-model validation and will not alter retrieval or answer generation.

## Testing

Frontend tests will use Node's built-in test runner and an injected fetch implementation. They will cover:

- Correct URL, method, headers, and typed body for chat requests.
- Session ID propagation on follow-up requests.
- Parsing a complete chat response including sources.
- FastAPI detail errors, generic HTTP errors, network failures, and malformed successful payloads.
- Health and clear-session request behavior.
- Store transitions for loading, success, failure, and session reset where those transitions are extracted into testable methods.

Backend tests will exercise the FastAPI routes with the retriever and answer generator isolated from external embedding and LLM services. They will verify health readiness, empty-question rejection, chat response shape, session continuity, and session clearing.

End-to-end verification will include the complete frontend test suite, TypeScript strict compilation, backend test suite, and a local smoke test that serves both applications and confirms the browser client can reach health and submit a chat request when backend credentials and model access are available. If live model access is unavailable, that external limitation will be reported explicitly; the HTTP integration will still be exercised against the real FastAPI application with deterministic dependency isolation.

## Constraints

- Preserve the current UI design and real user-facing functionality.
- Use strict TypeScript and the existing framework-free architecture.
- Do not add Axios, a frontend framework, or unrelated dependencies.
- Do not retain or introduce demo messages, mock responses, fake notes, simulated response delays, or fabricated chat history.
- Do not change retrieval, prompting, or answer semantics as part of frontend integration.
- Keep changes limited to files required for the API boundary, state/rendering integration, honest empty states, configuration, tests, and run documentation.

## Success Criteria

- A fresh page contains no demo messages, notes, or conversations.
- The composer is usable only when the FastAPI backend is ready.
- Every assistant answer displayed in the chat is the corresponding `POST /chat` response.
- Follow-up questions reuse the returned backend session ID.
- New chat clears both local state and the active backend session when possible.
- Loading, source, empty, and error states render without breaking existing interactions or visual layout.
- The API URL can be configured without editing TypeScript.
- Frontend compilation and tests, backend tests, and integration smoke checks produce recorded passing evidence or an explicit external-service limitation.
