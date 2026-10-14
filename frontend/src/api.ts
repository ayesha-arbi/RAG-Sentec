export const DEFAULT_API_BASE = 'http://localhost:8000';

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface QueryRoot {
  querySelector(selectors: string): { getAttribute(name: string): string | null } | null;
}

export interface SourceChunk {
  section: string;
  page_start: number;
  page_end: number;
  score: number;
  text: string;
}

export interface ChatRequestBody {
  question: string;
  session_id: string | null;
  rewrite: boolean;
  k: number;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  sources: SourceChunk[];
  standalone_question: string;
}

export interface HealthResponse {
  status: string;
  chunks_loaded: number;
}

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function normalizeApiBase(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

export function getApiBaseUrl(root?: QueryRoot | null): string {
  const doc = root ?? (typeof document !== 'undefined' ? document : null);
  const content = doc?.querySelector('meta[name="api-base"]')?.getAttribute('content');
  if (content && content.trim()) {
    return normalizeApiBase(content);
  }
  return DEFAULT_API_BASE;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseSource(value: unknown): SourceChunk {
  if (!isRecord(value)) {
    throw new ApiError('Invalid response from the server.');
  }
  if (
    typeof value.section !== 'string' ||
    typeof value.page_start !== 'number' ||
    typeof value.page_end !== 'number' ||
    typeof value.score !== 'number' ||
    typeof value.text !== 'string'
  ) {
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

function parseHealth(value: unknown): HealthResponse {
  if (!isRecord(value) || typeof value.status !== 'string' || typeof value.chunks_loaded !== 'number') {
    throw new ApiError('Invalid response from the server.');
  }
  return { status: value.status, chunks_loaded: value.chunks_loaded };
}

function parseChat(value: unknown): ChatResponse {
  if (
    !isRecord(value) ||
    typeof value.session_id !== 'string' ||
    typeof value.answer !== 'string' ||
    typeof value.standalone_question !== 'string' ||
    !Array.isArray(value.sources)
  ) {
    throw new ApiError('Invalid response from the server.');
  }
  return {
    session_id: value.session_id,
    answer: value.answer,
    sources: value.sources.map(parseSource),
    standalone_question: value.standalone_question
  };
}

async function readJson(res: Response): Promise<unknown> {
  return res.json();
}

async function errorFromResponse(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    const body = await readJson(res);
    if (isRecord(body)) {
      detail = body.detail;
    }
  } catch {
    detail = undefined;
  }
  if (typeof detail === 'string' && detail.trim()) {
    return new ApiError(detail, res.status);
  }
  return new ApiError(`Request failed with status ${res.status}`, res.status);
}

export class ApiClient {
  readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;

  constructor(fetchImpl?: FetchLike, baseUrl?: string) {
    this.fetchImpl = fetchImpl ?? ((input, init) => fetch(input, init));
    this.baseUrl = normalizeApiBase(baseUrl ?? getApiBaseUrl());
  }

  private async request(path: string, init: RequestInit): Promise<unknown> {
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    } catch {
      throw new ApiError(`Could not connect to ${this.baseUrl}`);
    }
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    try {
      return await readJson(res);
    } catch {
      throw new ApiError('Invalid response from the server.');
    }
  }

  async health(): Promise<HealthResponse> {
    try {
      return parseHealth(await this.request('/health', { method: 'GET' }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        throw new ApiError('The prospectus index is not ready yet.', 503);
      }
      throw err;
    }
  }

  async chat(
    question: string,
    sessionId: string | null,
    rewrite = false,
    k = 8
  ): Promise<ChatResponse> {
    const body: ChatRequestBody = {
      question,
      session_id: sessionId,
      rewrite,
      k
    };
    return parseChat(
      await this.request('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
    );
  }

  async clearSession(sessionId: string): Promise<{ cleared: string }> {
    const value = await this.request(`/chat/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
    if (!isRecord(value) || typeof value.cleared !== 'string') {
      throw new ApiError('Invalid response from the server.');
    }
    return { cleared: value.cleared };
  }
}
