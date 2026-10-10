// OPCIONAL, SOLO PARA USO PERSONAL.
// Mini proxy para Cloudflare Workers que permite a TU navegador leer una página de lista de beatport.com.
// Despliégalo en tu propia cuenta (gratis) y pega su URL en Avanzado > Proxy de Beatport.
// Revisa antes los términos de uso de Beatport: no lo abras al público ni lo uses con fines comerciales.
const ALLOWED_ORIGIN = 'https://TU-USUARIO.github.io'; // cambia por el origen donde sirvas la app

export default {
  async fetch(request) {
    const cors = {
      'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
      'Access-Control-Allow-Methods': 'GET',
      Vary: 'Origin',
    };
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    const target = new URL(request.url).searchParams.get('url') || '';
    let u;
    try { u = new URL(target); } catch { return new Response('url inválida', { status: 400, headers: cors }); }
    // Solo páginas de listas de géneros de Beatport.
    if (u.hostname !== 'www.beatport.com' || !/^\/genre\/[^/]+\/\d+\/top-100\/?$/.test(u.pathname)) {
      return new Response('solo listas top-100 de beatport.com', { status: 403, headers: cors });
    }
    const res = await fetch(u.toString(), { headers: { Accept: 'text/html', 'Accept-Language': 'en-US,en;q=0.9' } });
    return new Response(await res.text(), { status: res.status, headers: { ...cors, 'Content-Type': 'text/html; charset=utf-8' } });
  },
};
