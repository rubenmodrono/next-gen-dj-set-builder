import type { RawTrack } from '../core/types';

export type Provider = 'none' | 'gemini' | 'claude';

export interface LlmSettings {
  provider: Provider;
  geminiKey: string;
  geminiModel: string;
  claudeKey: string;
  claudeModel: string;
}

export const DEFAULT_LLM: LlmSettings = {
  provider: 'none',
  geminiKey: '',
  geminiModel: 'gemini-2.5-flash',
  claudeKey: '',
  claudeModel: 'claude-sonnet-5-5',
};

export function buildTranscribePrompt(pageText: string): string {
  return `Below is the visible text of a Beatport chart page. Transcribe every track row shown, up to 100, exactly as written on the page.

Rules:
- Copy values from the text. Never invent, estimate or complete a value from memory. Use null when a field is not on the page.
- "artists" is a list of artist names. "title" is the track name WITHOUT the mix name. "mix" is the mix or version (Original Mix, Extended Mix, "X Remix", ...).
- "bpm" is a number. "key" is the key exactly as shown (for example "A Minor", "Db Major", or a Camelot code).
- "genre" is the genre shown for the track, or the chart's genre if none is shown per track.

Reply with only a JSON array, one object per track, for example:
[{"artists":["Artist One","Artist Two"],"title":"Track Title","mix":"Extended Mix","genre":"Progressive House","bpm":124,"key":"G Minor"}]

PAGE TEXT:
${pageText}`;
}

/** Reads a JSON array of tracks out of a model reply (plain JSON, fenced, or surrounded by text). */
export function parseTracksJson(reply: string): RawTrack[] {
  let value: unknown;
  const tryParse = (s: string): boolean => {
    try {
      value = JSON.parse(s);
      return true;
    } catch {
      return false;
    }
  };
  const trimmed = reply.trim();
  if (!tryParse(trimmed)) {
    const fence = /```(?:json)?\s*([\s\S]*?)```/.exec(trimmed);
    const start = trimmed.indexOf('[');
    const end = trimmed.lastIndexOf(']');
    if (!(fence && tryParse(fence[1])) && !(start >= 0 && end > start && tryParse(trimmed.slice(start, end + 1)))) {
      throw new Error('La respuesta del modelo no contiene una lista JSON legible.');
    }
  }
  if (!Array.isArray(value)) throw new Error('La respuesta del modelo no es una lista.');
  const out: RawTrack[] = [];
  for (const item of value as unknown[]) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const artists = Array.isArray(o.artists)
      ? o.artists.filter((a): a is string => typeof a === 'string')
      : typeof o.artist === 'string'
        ? [o.artist]
        : [];
    const bpm = typeof o.bpm === 'number' ? o.bpm : typeof o.bpm === 'string' ? Number(o.bpm) : null;
    if (typeof o.title !== 'string' || !artists.length) continue;
    out.push({
      artists,
      title: o.title,
      mix: typeof o.mix === 'string' ? o.mix : null,
      genre: typeof o.genre === 'string' ? o.genre : null,
      bpm: bpm != null && Number.isFinite(bpm) ? bpm : null,
      key: typeof o.key === 'string' ? o.key : null,
    });
  }
  return out;
}

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: { message?: string } | string };
    const msg = typeof body.error === 'string' ? body.error : body.error?.message;
    return msg ? `${res.status}: ${msg}` : String(res.status);
  } catch {
    return String(res.status);
  }
}

async function askGemini(prompt: string, s: LlmSettings, signal?: AbortSignal): Promise<string> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(s.geminiModel)}:generateContent`;
  const res = await fetch(url, {
    method: 'POST',
    signal,
    headers: { 'content-type': 'application/json', 'x-goog-api-key': s.geminiKey },
    body: JSON.stringify({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0, responseMimeType: 'application/json' },
    }),
  });
  if (!res.ok) throw new Error(`Gemini respondió ${await readError(res)}`);
  const body = (await res.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
  const text = (body.candidates?.[0]?.content?.parts ?? []).map((p) => p.text ?? '').join('');
  if (!text) throw new Error('Gemini no devolvió texto.');
  return text;
}

async function askClaude(prompt: string, s: LlmSettings, signal?: AbortSignal): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    signal,
    headers: { 'content-type': 'application/json', 'x-api-key': s.claudeKey, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({
      model: s.claudeModel,
      max_tokens: 8000,
      temperature: 0,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  if (!res.ok) throw new Error(`Claude respondió ${await readError(res)}`);
  const body = (await res.json()) as { content?: { type: string; text?: string }[] };
  const text = (body.content ?? []).filter((b) => b.type === 'text').map((b) => b.text ?? '').join('');
  if (!text) throw new Error('Claude no devolvió texto.');
  return text;
}

export async function transcribeChart(pageText: string, s: LlmSettings, signal?: AbortSignal): Promise<RawTrack[]> {
  const prompt = buildTranscribePrompt(pageText);
  if (s.provider === 'gemini') return parseTracksJson(await askGemini(prompt, s, signal));
  if (s.provider === 'claude') return parseTracksJson(await askClaude(prompt, s, signal));
  throw new Error('No hay ningún modelo configurado.');
}

export function buildUrlPrompt(url: string): string {
  return `Open this Beatport chart page and transcribe every track row shown, up to 100, exactly as written on the page: ${url}

Rules:
- Copy values from the page. Never invent, estimate or complete a value from memory. Use null when a field is not on the page.
- "artists" is a list of artist names. "title" is the track name WITHOUT the mix name. "mix" is the mix or version (Original Mix, Extended Mix, "X Remix", ...).
- "bpm" is a number. "key" is the key exactly as shown (for example "A Minor", "Db Major", or a Camelot code).
- "genre" is the genre shown for the track, or the chart's genre if none is shown per track.

Reply with only a JSON array, one object per track, for example:
[{"artists":["Artist One","Artist Two"],"title":"Track Title","mix":"Extended Mix","genre":"Progressive House","bpm":124,"key":"G Minor"}]`;
}

interface ClaudeBlock { type: string; text?: string }
interface ClaudeReply { stop_reason?: string; content?: ClaudeBlock[] }

/** The model reads the page from its own servers (useful when the phone's request to Beatport is blocked). */
export async function transcribeFromUrl(url: string, s: LlmSettings, signal?: AbortSignal): Promise<RawTrack[]> {
  const prompt = buildUrlPrompt(url);
  if (s.provider === 'gemini') {
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(s.geminiModel)}:generateContent`;
    const res = await fetch(endpoint, {
      method: 'POST',
      signal,
      headers: { 'content-type': 'application/json', 'x-goog-api-key': s.geminiKey },
      body: JSON.stringify({
        contents: [{ role: 'user', parts: [{ text: prompt }] }],
        tools: [{ url_context: {} }],
        generationConfig: { temperature: 0 },
      }),
    });
    if (!res.ok) throw new Error(`Gemini respondió ${await readError(res)}`);
    const body = (await res.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
    const text = (body.candidates?.[0]?.content?.parts ?? []).map((p) => p.text ?? '').join('');
    return parseTracksJson(text);
  }
  if (s.provider === 'claude') {
    const tools = [{ type: 'web_fetch_20250910', name: 'web_fetch', max_uses: 3 }];
    const messages: { role: 'user' | 'assistant'; content: unknown }[] = [{ role: 'user', content: prompt }];
    for (let round = 0; round < 4; round++) {
      const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        signal,
        headers: { 'content-type': 'application/json', 'x-api-key': s.claudeKey, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model: s.claudeModel, max_tokens: 8000, messages, tools }),
      });
      if (!res.ok) throw new Error(`Claude respondió ${await readError(res)}`);
      const body = (await res.json()) as ClaudeReply;
      if (body.stop_reason === 'pause_turn') {
        messages.push({ role: 'assistant', content: body.content ?? [] });
        continue;
      }
      const text = (body.content ?? []).filter((b) => b.type === 'text').map((b) => b.text ?? '').join('\n');
      return parseTracksJson(text);
    }
    throw new Error('Claude no terminó de leer la página.');
  }
  throw new Error('No hay ningún modelo configurado.');
}
