// Captures the app in every style and mode, at desktop and phone width, and checks layout rules.
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const OUT = process.argv[2];
const URL = process.argv[3] ?? 'http://localhost:4173/';
fs.mkdirSync(OUT, { recursive: true });
const exe = ['/opt/pw-browsers/chromium/chrome-linux/chrome', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find((p) => fs.existsSync(p));
const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
const report = [];

for (const [w, h, tag] of [[1280, 900, 'desktop'], [375, 800, 'phone']]) {
  for (const style of ['wheel', 'console', 'editorial']) {
    for (const mode of ['dark', 'light']) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: mode, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e)));
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
      await page.addInitScript(([s, m]) => { localStorage.setItem('sp-style', s); localStorage.setItem('sp-mode', m); }, [style, mode]);
      await page.goto(URL);
      await page.waitForSelector('text=Aún no hay un set');
      if (tag === 'desktop' && style === 'wheel' && mode === 'dark') await page.screenshot({ path: `${OUT}/00-empty-${style}-${mode}.png` });
      await page.getByRole('button', { name: 'Usar biblioteca de ejemplo' }).first().click();
      await page.waitForSelector('text=Biblioteca de ejemplo');
      // Pin two tracks by hand.
      await page.locator('summary', { hasText: 'Temas fijados' }).click();
      await page.getByRole('radio', { name: 'A mano' }).click();
      for (const [a, t, b, k] of [['Pin Artist', 'Peak Anthem', '128', '8A'], ['Other Artist', 'Opening Tune', '119', '9A']]) {
        await page.fill('#pin-artist', a); await page.fill('#pin-title', t); await page.fill('#pin-bpm', b); await page.fill('#pin-key', k);
        await page.getByRole('button', { name: 'Fijar tema' }).click();
      }
      await page.getByRole('button', { name: 'Generar set' }).last().click();
      await page.waitForSelector('.tracklist .row');
      await page.waitForTimeout(300);
      const m = await page.evaluate(() => {
        const de = document.documentElement;
        const fonts = new Set(); const sizes = new Set(); const weights = new Set();
        for (const el of document.querySelectorAll('body *')) {
          if (!el.childNodes.length || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
          const cs = getComputedStyle(el);
          sizes.add(parseFloat(cs.fontSize)); weights.add(cs.fontWeight);
        }
        const small = [...document.querySelectorAll('button, input, select, a, summary, [role=radio], [role=switch]')].filter((el) => {
          const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
          return r.width > 0 && cs.visibility !== 'hidden' && !el.classList.contains('sr-only') && (r.height < 43.5 || r.width < 43.5) && el.type !== 'checkbox' && el.tagName !== 'INPUT';
        }).map((el) => `${el.tagName}.${el.className}:${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`);
        return { overflow: de.scrollWidth - de.clientWidth, sizes: [...sizes].sort((a, b) => a - b), weights: [...weights], small,
          rows: document.querySelectorAll('.tracklist .row').length, pinned: document.querySelectorAll('.trow[data-pinned]').length };
      });
      report.push({ tag, style, mode, errors, ...m });
      if (tag === 'phone') await page.screenshot({ path: `${OUT}/${tag}-${style}-${mode}.png`, fullPage: false });
      else await page.screenshot({ path: `${OUT}/${tag}-${style}-${mode}.png`, fullPage: false });
      if (tag === 'desktop') {
        await page.locator('.panel-right').scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${OUT}/${tag}-${style}-${mode}-full.png`, fullPage: true });
      }
      await ctx.close();
    }
  }
}
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
for (const r of report) console.log(r.tag, r.style, r.mode, 'overflow', r.overflow, 'rows', r.rows, 'pinned', r.pinned, 'sizes', r.sizes.join('/'), 'weights', r.weights.join('/'), 'small', r.small.length, r.errors.length ? 'ERR ' + r.errors.join('|') : '');
await browser.close();
