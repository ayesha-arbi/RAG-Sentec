# RAG-Sentec

Prospecto answers questions from a university prospectus. The TypeScript UI in `frontend` talks to the FastAPI app in `Prospecto`.

## Run locally

From `Prospecto`:

```
uvicorn api:app --reload --port 8000
```

From `frontend`:

```
npm start
```

The browser reads the API URL from the `api-base` meta tag in `frontend/index.html` (default `http://localhost:8000`). Change that tag for another environment; you do not need to rebuild TypeScript to point at a different host.

## Tests

Frontend:

```
cd frontend
npm test
```

Backend (isolates retrieval and answer generation):

```
cd Prospecto
python -m unittest test_api.py
```
