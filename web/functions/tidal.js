// Lector de catálogo de Tidal para Cloudflare Pages (Pages Functions).
// Las credenciales NO están en el código: se definen como variables de entorno del proyecto en Cloudflare
//   TIDAL_CLIENT_ID, TIDAL_CLIENT_SECRET (secreto) y, opcionalmente, TIDAL_COUNTRY (por defecto ES).
// El navegador solo habla con esta función (misma web, sin CORS); el secreto nunca sale de Cloudflare.

const API = 'https://openapi.tidal.com/v2';
const TOKEN_URL = 'https://auth.tidal.com/v1/oauth2/token';

let cached = null; // { token, expiresAt } se reutiliza mientras el entorno de ejecución siga vivo

const json = (status, body, extra = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-Content-Type-Options': 'nosniff', ...extra } });

async function getToken(env, force = false) {
  if (!force && cached && cached.expiresAt > Date.now() + 60_000) return cached.token;
  const basic = btoa(`${env.TIDAL_CLIENT_ID}:${env.TIDAL_CLIENT_SECRET}`);
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { Authorization: `Basic ${basic}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'grant_type=client_credentials',
  });
  if (!res.ok) throw new Error(`Tidal rechazó las credenciales (código ${res.status}).`);
  const data = await res.json();
  cached = { token: data.access_token, expiresAt: Date.now() + Number(data.expires_in || 3600) * 1000 };
  return cached.token;
}

export async function onRequestGet({ request, env }) {
  const configured = Boolean(env.TIDAL_CLIENT_ID && env.TIDAL_CLIENT_SECRET);
  const flag = { 'X-SP-Tidal': configured ? '1' : '0' };

  const site = request.headers.get('Sec-Fetch-Site');
  if (site && site !== 'same-origin' && site !== 'none') return json(403, { error: 'solo desde esta web' }, flag);

  const params = new URL(request.url).searchParams;
  if (params.get('probe')) return new Response(null, { status: 204, headers: flag });
  if (!configured) return json(501, { error: 'Tidal no está configurado en este servidor.' }, flag);

  const country = /^[A-Z]{2}$/.test(env.TIDAL_COUNTRY || '') ? env.TIDAL_COUNTRY : 'ES';
  const ids = params.get('ids');
  const q = (params.get('q') || '').trim();
  const cursor = params.get('cursor');

  let upstream;
  if (ids) {
    if (!/^\d{1,12}(,\d{1,12}){0,19}$/.test(ids)) return json(400, { error: 'ids inválidos' }, flag);
    upstream = new URL(`${API}/tracks`);
    upstream.searchParams.set('countryCode', country);
    upstream.searchParams.set('filter[id]', ids);
    upstream.searchParams.set('include', 'artists');
  } else if (q && q.length <= 100) {
    upstream = new URL(`${API}/searchResults`);
    upstream.searchParams.set('countryCode', country);
    upstream.searchParams.set('filter[query]', q);
    upstream.searchParams.set('include', 'tracks,tracks.artists');
    if (cursor && /^[\w.=\-]{1,300}$/.test(cursor)) upstream.searchParams.set('page[cursor]', cursor);
  } else {
    return json(400, { error: 'falta la búsqueda (q) o los ids' }, flag);
  }

  try {
    const call = async (force) => fetch(upstream.toString(), {
      headers: { Accept: 'application/vnd.api+json', Authorization: `Bearer ${await getToken(env, force)}` },
      cf: { cacheEverything: true, cacheTtl: 3600 },
    });
    let res = await call(false);
    if (res.status === 401) res = await call(true);
    return new Response(await res.text(), {
      status: res.status,
      headers: { ...flag, 'Content-Type': 'application/json; charset=utf-8', 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=600' },
    });
  } catch (e) {
    return json(502, { error: e instanceof Error ? e.message : 'No pude hablar con Tidal.' }, flag);
  }
}
