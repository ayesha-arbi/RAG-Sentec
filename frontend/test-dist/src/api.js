export const DEFAULT_API_BASE = 'http://localhost:8000';
export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}
export function normalizeApiBase(url) {
    return url.trim().replace(/\/+$/, '');
}
export function getApiBaseUrl(root) {
    const doc = root ?? (typeof document !== 'undefined' ? document : null);
    const content = doc?.querySelector('meta[name="api-base"]')?.getAttribute('content');
    if (content && content.trim()) {
        return normalizeApiBase(content);
    }
    return DEFAULT_API_BASE;
}
function isRecord(value) {
    return typeof value === 'object' && value !== null;
}
function parseSource(value) {
    if (!isRecord(value)) {
        throw new ApiError('Invalid response from the server.');
    }
    if (typeof value.section !== 'string' ||
        typeof value.page_start !== 'number' ||
        typeof value.page_end !== 'number' ||
        typeof value.score !== 'number' ||
        typeof value.text !== 'string') {
        throw new ApiError('Invalid response from the server.');
    }
    return {
        section: value.section,
        page_start: value.page_start,
        page_end: value.page_end,
        score: value.score,
        text: value.text
    };
}
function parseHealth(value) {
    if (!isRecord(value) || typeof value.status !== 'string' || typeof value.chunks_loaded !== 'number') {
        throw new ApiError('Invalid response from the server.');
    }
    return { status: value.status, chunks_loaded: value.chunks_loaded };
}
function parseChat(value) {
    if (!isRecord(value) ||
        typeof value.session_id !== 'string' ||
        typeof value.answer !== 'string' ||
        typeof value.standalone_question !== 'string' ||
        !Array.isArray(value.sources)) {
        throw new ApiError('Invalid response from the server.');
    }
    return {
        session_id: value.session_id,
        answer: value.answer,
        sources: value.sources.map(parseSource),
        standalone_question: value.standalone_question
    };
}
async function readJson(res) {
    return res.json();
}
async function errorFromResponse(res) {
    let detail;
    try {
        const body = await readJson(res);
        if (isRecord(body)) {
            detail = body.detail;
        }
    }
    catch {
        detail = undefined;
    }
    if (typeof detail === 'string' && detail.trim()) {
        return new ApiError(detail, res.status);
    }
    return new ApiError(`Request failed with status ${res.status}`, res.status);
}
export class ApiClient {
    constructor(fetchImpl, baseUrl) {
        this.fetchImpl = fetchImpl ?? ((input, init) => fetch(input, init));
        this.baseUrl = normalizeApiBase(baseUrl ?? getApiBaseUrl());
    }
    async request(path, init) {
        let res;
        try {
            res = await this.fetchImpl(`${this.baseUrl}${path}`, init);
        }
        catch {
            throw new ApiError(`Could not connect to ${this.baseUrl}`);
        }
        if (!res.ok) {
            throw await errorFromResponse(res);
        }
        try {
            return await readJson(res);
        }
        catch {
            throw new ApiError('Invalid response from the server.');
        }
    }
    async health() {
        try {
            return parseHealth(await this.request('/health', { method: 'GET' }));
        }
        catch (err) {
            if (err instanceof ApiError && err.status === 503) {
                throw new ApiError('The prospectus index is not ready yet.', 503);
            }
            throw err;
        }
    }
    async chat(question, sessionId, rewrite = false, k = 8) {
        const body = {
            question,
            session_id: sessionId,
            rewrite,
            k
        };
        return parseChat(await this.request('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }));
    }
    async clearSession(sessionId) {
        const value = await this.request(`/chat/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
        if (!isRecord(value) || typeof value.cleared !== 'string') {
            throw new ApiError('Invalid response from the server.');
        }
        return { cleared: value.cleared };
    }
}
