import { createHash } from 'node:crypto';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

const single = process.env.SINGLE_FILE === '1';

/**
 * Adds a Content-Security-Policy meta tag to the static build. Works on any static host (GitHub Pages cannot set headers).
 * Scripts: this site, the one inline theme bootstrap (by hash) and the two preview APIs (JSONP).
 * connect-src allows https: because the optional Beatport proxy and model APIs are chosen by the user.
 */
function csp(): Plugin {
  return {
    name: 'set-planifier-csp',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => `'sha256-${createHash('sha256').update(m[1]).digest('base64')}'`);
        const policy = [
          "default-src 'self'",
          `script-src 'self' ${inline.join(' ')} https://api.deezer.com https://itunes.apple.com`,
          "style-src 'self'",
          "img-src 'self' data:",
          "font-src 'self' data:",
          'media-src https:',
          "connect-src 'self' https:",
          "object-src 'none'",
          "base-uri 'none'",
          "form-action 'none'",
        ].join('; ');
        return html.replace('<head>', `<head>\n  <meta http-equiv="Content-Security-Policy" content="${policy}" />\n  <meta name="referrer" content="no-referrer" />`);
      },
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [react(), ...(single ? [viteSingleFile()] : [csp()])],
  build: { outDir: single ? 'dist-single' : 'dist', target: 'es2020', assetsInlineLimit: single ? 100_000_000 : 4096 },
});
