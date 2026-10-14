import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiClient } from '../dist/api.js';
import { StateStore } from '../dist/state.js';

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

test('checkHealth marks the backend ready', async () => {
  const store = new StateStore(
    new ApiClient(async () => jsonResponse(200, { status: 'ok', chunks_loaded: 3 }), 'http://localhost:8000')
  );
  await store.checkHealth();
  const state = store.getState();
  assert.equal(state.backendStatus, 'ready');
  assert.equal(state.requestStatus, 'idle');
  assert.equal(state.error, null);
});

test('sendMessage keeps the user turn and appends the server answer', async () => {
  const store = new StateStore(
    new ApiClient(async (url, init) => {
      if (url.endsWith('/health')) {
        return jsonResponse(200, { status: 'ok', chunks_loaded: 3 });
      }
      assert.equal(init?.method, 'POST');
      return jsonResponse(200, {
        session_id: 'abc',
        answer: 'Hostels are listed on page 80.',
        sources: [
          { section: 'Hostels', page_start: 80, page_end: 81, score: 0.4, text: 'Hostel allocation...' }
        ],
        standalone_question: 'Where are hostels listed?'
      });
    }, 'http://localhost:8000')
  );
  await store.checkHealth();
  await store.sendMessage('Where are hostels?');
  const state = store.getState();
  assert.equal(state.sessionId, 'abc');
  assert.equal(state.messages.length, 2);
  assert.equal(state.messages[0].role, 'user');
  assert.equal(state.messages[1].text, 'Hostels are listed on page 80.');
  assert.equal(state.messages[1].sources?.length, 1);
  assert.equal(state.requestStatus, 'idle');
});

test('failed chat leaves the user message and records an error', async () => {
  const store = new StateStore(
    new ApiClient(async (url) => {
      if (url.endsWith('/health')) {
        return jsonResponse(200, { status: 'ok', chunks_loaded: 1 });
      }
      return jsonResponse(500, { detail: 'LLM unavailable' });
    }, 'http://localhost:8000')
  );
  await store.checkHealth();
  await store.sendMessage('fees?');
  const state = store.getState();
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].role, 'user');
  assert.equal(state.error, 'LLM unavailable');
  assert.equal(state.requestStatus, 'idle');
});

test('resetChat clears the local session even if DELETE fails', async () => {
  let deleted = false;
  const store = new StateStore(
    new ApiClient(async (url, init) => {
      if (url.endsWith('/health')) {
        return jsonResponse(200, { status: 'ok', chunks_loaded: 1 });
      }
      if (init?.method === 'DELETE') {
        deleted = true;
        throw new TypeError('offline');
      }
      return jsonResponse(200, {
        session_id: 'keep-me',
        answer: 'ok',
        sources: [],
        standalone_question: 'q'
      });
    }, 'http://localhost:8000')
  );
  await store.checkHealth();
  await store.sendMessage('hello');
  await store.resetChat();
  const state = store.getState();
  assert.equal(deleted, true);
  assert.equal(state.sessionId, null);
  assert.equal(state.messages.length, 0);
  assert.equal(state.error.includes('Could not connect'), true);
});
