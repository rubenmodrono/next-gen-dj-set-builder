# Set Planifier (web)

> Un set no es una lista de buenos temas: es una curva. Esta app la construye.

Versión web de Set Planifier. Genera sets de DJ a partir de tu propia biblioteca (o de una lista de Beatport), con curva de BPM/energía por tramos (Warm-up 25 %, Peak time 50 %, Closing 25 %), mezcla armónica sobre la rueda Camelot y temas fijados por ti que el algoritmo coloca en la posición correcta.

Salida por tema: `Artista - Título - BPM - tonalidad`.

## Qué incluye

- **Importar biblioteca**: rekordbox XML, Traktor NML, CSV/TSV (cabeceras en español o inglés). Se procesa en tu navegador y se guarda en IndexedDB. No se sube a ningún servidor.
- **Temas fijados** (hasta 20): búsqueda en tu biblioteca, entrada manual o pegar una lista. El motor prueba varias posiciones para cada uno y elige la combinación de menor coste de transición.
- **Mezcla armónica**: estricta, con saltos conocidos (energy boost) o libre.
- **Curva por tramos** editable (BPM objetivo y peso de cada tramo) y duración del set.
- **Tres estilos** (Rueda, Consola, Editorial), cada uno en **modo claro y oscuro** con interruptor. Se recuerda la elección y se respeta `prefers-color-scheme`.
- **Previews de 30 s** (Deezer / iTunes) y exportación a texto y CSV.
- Atajos: `Ctrl/Cmd + Enter` genera, `Esc` detiene la preview.

## Desarrollo

```bash
npm install
npm run dev          # http://localhost:5173
npm test             # 29 tests del motor, importadores y temas fijados
npm run build        # tsc + vite build → dist/
npm run build:single # un único index.html en dist-single/
npm run preview
```

Requisitos: Node 20+.

Comprobaciones auxiliares (necesitan Chromium): `scripts/shots.mjs` (capturas), `scripts/contrast.mjs` (contraste AA) y `scripts/axe.mjs` (accesibilidad).

## Estructura

```
src/core/      motor: Camelot, preparePool, beam search, planSet (temas fijados)
src/library/   importadores (rekordbox, Traktor, CSV), biblioteca demo, IndexedDB
src/sources/   Beatport (vía proxy propio), LLM opcional, previews
src/ui/        React: App, paneles, resultado, rueda, curva
src/styles.css tokens de 3 estilos × 2 modos
tests/         pruebas del motor
functions/     lector de Beatport integrado (Cloudflare Pages Functions)
worker/        proxy opcional para Beatport (Cloudflare Worker propio)
```

## Cómo exportar tu biblioteca

- **rekordbox**: Archivo > Exportar colección en formato xml.
- **Traktor**: la colección es `collection.nml` en la carpeta de Traktor.
- **CSV**: columnas `Artista`, `Título`, `BPM`, `Tonalidad` y opcionalmente `Género`. El separador se detecta solo.

Si no tienes archivo a mano, el botón de demo carga una biblioteca ficticia de 350 temas.

## Desplegar gratis

### GitHub Pages (recomendado, ya configurado)

La web vive en la carpeta `web/` de este repositorio y el workflow `.github/workflows/deploy-web.yml` la publica.

1. En **Settings > Pages**, en *Source* elige **GitHub Actions** (una sola vez).
2. Haz push a `main` con cambios en `web/` o lanza el workflow a mano desde **Actions > Desplegar web en GitHub Pages > Run workflow**.
3. La URL será `https://rubenmodrono.github.io/next-gen-dj-set-builder/`.

`vite.config.ts` usa `base: './'`, así que funciona bajo una subruta.

### Alternativas

- **Cloudflare Pages**: build `npm run build`, salida `dist`. Aplica `public/_headers`.
- **Netlify**: igual. También aplica `_headers`.

GitHub Pages no permite cabeceras propias. La política CSP se inserta como `<meta>` en el build, así que sigue protegida.

## Beatport (opcional)

Los navegadores bloquean Beatport por CORS, así que la lectura pasa siempre por un servidor.

- **En Cloudflare Pages no tienes que configurar nada.** La carpeta `functions/` se despliega con la web y `functions/beatport.js` queda en la misma dirección (`/beatport`). Solo lee listas top-100 de género, solo responde a peticiones de tu propia web y guarda cada lista una hora en caché.
- **En GitHub Pages** (que solo sirve archivos estáticos) esa función no existe. Despliega `worker/beatport-proxy.js` como Worker propio, define `ALLOWED_ORIGIN` con la URL de tu web y pega su dirección en *Avanzado > Proxy propio*.
- Sin ninguna de las dos opciones, la app funciona con tu biblioteca.

Es para uso personal. Revisa los términos de uso de Beatport antes de abrir la web al público.

## Privacidad y seguridad

- Tu biblioteca no sale del navegador.
- Las claves de Gemini/Claude (opcionales) se guardan en `sessionStorage`; solo en `localStorage` si marcas *Recordar*. No metas una clave propia en el código de una web pública.
- CSP restrictiva, `no-referrer` y cabeceras `nosniff` / `Permissions-Policy`.
- Las previews consultan Deezer e iTunes desde tu navegador. Respeta sus términos: solo fragmentos de 30 s y sin descargas.

## Puntos sin verificar

- Respuesta real de Deezer/iTunes (JSONP) y de un proxy de Beatport en un navegador en vivo.
- Mapeo de `MUSICAL_KEY` de Traktor cuando no existe `INFO KEY`.
- Exportaciones reales de rekordbox de gran tamaño (se probó con 12 000 temas sintéticos).
