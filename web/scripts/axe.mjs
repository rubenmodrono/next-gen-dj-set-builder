// Runs axe-core on the generated-set view in every style and mode, at desktop and phone width.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
const axeSrc = fs.readFileSync(new URL('../node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');
const exe = ['/opt/pw-browsers/chromium/chrome-linux/chrome', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find((p) => fs.existsSync(p));
const b = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
let total = 0;
for (const [w, h] of [[1280, 900], [375, 800]]) for (const style of ['wheel', 'console', 'editorial']) for (const mode of ['dark', 'light']) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, bypassCSP: true });
  const p = await ctx.newPage();
  await p.addInitScript(([s, m]) => { localStorage.setItem('sp-style', s); localStorage.setItem('sp-mode', m); }, [style, mode]);
  await p.goto(process.argv[2] ?? 'http://localhost:4173/');
  await p.getByRole('button', { name: 'Usar biblioteca de ejemplo' }).first().click();
  await p.locator('summary', { hasText: 'Temas fijados' }).click();
  await p.getByRole('radio', { name: 'A mano' }).click();
  await p.fill('#pin-artist', 'x'); await p.locator('#pin-artist').blur();
  await p.getByRole('button', { name: 'Generar set' }).last().click();
  await p.waitForSelector('.tracklist .row');
  await p.waitForTimeout(300);
  await p.addScriptTag({ content: axeSrc });
  const res = await p.evaluate(async () => (await window.axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] })).violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes[0].html.slice(0, 140), why: v.nodes[0].failureSummary?.slice(0, 200) })));
  total += res.length;
  console.log(`${w}px ${style}/${mode}:`, res.length ? JSON.stringify(res, null, 1) : 'no violations');
  await ctx.close();
}
console.log('total violation types:', total);
await b.close();
