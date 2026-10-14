import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiClient, ApiError, getApiBaseUrl } from '../src/api.js';
function jsonResponse(status, body) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' }
    });
}
function clientFor(handler, calls) {
    const fetchImpl = async (url, init) => {
        calls.push({ url, init });
        return handler(url, init);
    };
    return new ApiClient(fetchImpl, 'http://localhost:8000');
}
const validChat = {
    session_id: 'sess-1',
    answer: 'The fee is 120,000.',
    sources: [
        {
            section: 'Fees > BS SE',
            page_start: 47,
            page_end: 47,
            score: 0.91,
            text: 'Tuition fee is 120,000 per semester.'
        }
    ],
    standalone_question: 'What is the fee for BS Software Engineering?'
};
test('getApiBaseUrl reads meta content and falls back to localhost', () => {
    assert.equal(getApiBaseUrl(null), 'http://localhost:8000');
    assert.equal(getApiBaseUrl({
        querySelector: () => ({ getAttribute: () => 'http://api.example.com/' })
    }), 'http://api.example.com');
});
test('chat sends typed JSON body to POST /chat', async () => {
    const calls = [];
    const api = clientFor(async () => jsonResponse(200, validChat), calls);
    const result = await api.chat('What is the fee?', null, false, 8);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, 'http://localhost:8000/chat');
    assert.equal(calls[0].init?.method, 'POST');
    assert.equal((calls[0].init?.headers)['Content-Type'], 'application/json');
    assert.equal(calls[0].init?.body, JSON.stringify({ question: 'What is the fee?', session_id: null, rewrite: false, k: 8 }));
    assert.equal(result.session_id, 'sess-1');
    assert.equal(result.sources.length, 1);
    assert.equal(result.sources[0].page_start, 47);
});
test('follow-up chat reuses the session id', async () => {
    const calls = [];
    const api = clientFor(async () => jsonResponse(200, validChat), calls);
    await api.chat('and for hosts?', 'sess-1', false, 8);
    assert.equal(calls[0].init?.body, JSON.stringify({ question: 'and for hosts?', session_id: 'sess-1', rewrite: false, k: 8 }));
});
test('FastAPI detail errors become ApiError messages', async () => {
    const api = clientFor(async () => jsonResponse(400, { detail: 'Question cannot be empty.' }), []);
    await assert.rejects(() => api.chat(' ', null), (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.message, 'Question cannot be empty.');
        assert.equal(err.status, 400);
        return true;
    });
});
test('generic HTTP errors use status text', async () => {
    const api = clientFor(async () => jsonResponse(502, { message: 'bad gateway' }), []);
    await assert.rejects(() => api.health(), (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.message, 'Request failed with status 502');
        return true;
    });
});
test('network failures name the configured API URL', async () => {
    const api = new ApiClient(async () => {
        throw new TypeError('Failed to fetch');
    }, 'http://localhost:8000');
    await assert.rejects(() => api.chat('fees', null), (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.message, 'Could not connect to http://localhost:8000');
        return true;
    });
});
test('malformed successful chat payloads are rejected', async () => {
    const api = clientFor(async () => jsonResponse(200, { answer: 'partial' }), []);
    await assert.rejects(() => api.chat('fees', null), (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.message, 'Invalid response from the server.');
        return true;
    });
});
test('health and clear-session request the expected routes', async () => {
    const calls = [];
    const api = clientFor(async (url, init) => {
        if (init?.method === 'DELETE') {
            return jsonResponse(200, { cleared: 'sess-1' });
        }
        return jsonResponse(200, { status: 'ok', chunks_loaded: 12 });
    }, calls);
    const health = await api.health();
    const cleared = await api.clearSession('sess-1');
    assert.equal(health.chunks_loaded, 12);
    assert.equal(cleared.cleared, 'sess-1');
    assert.equal(calls[0].url, 'http://localhost:8000/health');
    assert.equal(calls[0].init?.method, 'GET');
    assert.equal(calls[1].url, 'http://localhost:8000/chat/sess-1');
    assert.equal(calls[1].init?.method, 'DELETE');
});
test('health 503 reports that the index is not ready', async () => {
    const api = clientFor(async () => jsonResponse(503, { detail: 'Index not loaded yet' }), []);
    await assert.rejects(() => api.health(), (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.message, 'The prospectus index is not ready yet.');
        assert.equal(err.status, 503);
        return true;
    });
});
