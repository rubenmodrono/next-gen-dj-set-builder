// Lector integrado de listas de Beatport para Cloudflare Pages (Pages Functions).
// Se despliega solo junto con la web: queda en la misma dirección (/beatport), sin CORS y sin configurar nada.
// Solo lee listas top-100 de género y las guarda una hora en la caché de Cloudflare.
// Revisa antes los términos de uso de Beatport: es para uso personal, no comercial.

const HEADERS = { 'X-SP-Proxy': '1', 'X-Content-Type-Options': 'nosniff' };

export async function onRequestGet({ request }) {
  const site = request.headers.get('Sec-Fetch-Site');
  if (site && site !== 'same-origin' && site !== 'none') {
    return new Response('solo desde esta web', { status: 403, headers: HEADERS });
  }
  const params = new URL(request.url).searchParams;
  if (params.get('probe')) return new Response(null, { status: 204, headers: HEADERS });

  let target;
  try { target = new URL(params.get('url') || ''); } catch { return new Response('url inválida', { status: 400, headers: HEADERS }); }
  if (target.protocol !== 'https:' || target.hostname !== 'www.beatport.com' || !/^\/genre\/[^/]+\/\d+\/top-100\/?$/.test(target.pathname)) {
    return new Response('solo listas top-100 de beatport.com', { status: 403, headers: HEADERS });
  }
  const res = await fetch(target.toString(), {
    headers: { Accept: 'text/html', 'Accept-Language': 'en-US,en;q=0.9' },
    cf: { cacheEverything: true, cacheTtl: 3600 },
  });
  return new Response(await res.text(), {
    status: res.status,
    headers: { ...HEADERS, 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'private, max-age=600' },
  });
}
