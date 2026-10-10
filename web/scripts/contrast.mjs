// WCAG contrast check of every text/background pair in every style and mode.
import fs from 'node:fs';
const css = fs.readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const L = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const cr = (a, b) => { const [x, y] = [L(a), L(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const mix = (a, b, t) => a.map((v, i) => v * (1 - t) + b[i] * t);
const hsl = (h, s, l) => { s /= 100; l /= 100; const k = (n) => (n + h / 30) % 12; const a = s * Math.min(l, 1 - l); const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1))); return [f(0), f(8), f(4)]; };
let bad = 0;
for (const style of ['wheel', 'console', 'editorial']) for (const mode of ['dark', 'light']) {
  const m = new RegExp(`html\\[data-style='${style}'\\]\\[data-mode='${mode}'\\] \\{([^}]*)\\}`).exec(css)[1];
  const v = Object.fromEntries([...m.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((x) => [x[1], hex(x[2])]));
  const keyL = Number(/--key-l:\s*(\d+)%/.exec(m)[1]);
  const dangerBg = mix(v.surface, v.danger, 0.08);
  const checks = [
    ['ink/bg', v.ink, v.bg, 4.5], ['ink/surface', v.ink, v.surface, 4.5], ['ink/raised', v.ink, v.raised, 4.5],
    ['muted/bg', v.muted, v.bg, 4.5], ['muted/surface', v.muted, v.surface, 4.5], ['muted/raised', v.muted, v.raised, 4.5],
    ['accent-ink/accent', v['accent-ink'], v.accent, 4.5], ['accent-text/surface', v['accent-text'], v.surface, 4.5], ['accent-text/bg', v['accent-text'], v.bg, 4.5], ['accent-text/raised', v['accent-text'], v.raised, 4.5],
    ['danger/bg', v.danger, v.bg, 4.5], ['danger/surface', v.danger, v.surface, 4.5], ['danger/errorbox', v.danger, dangerBg, 4.5],
    ['warn/surface', v.warn, v.surface, 4.5], ['warn/raised', v.warn, v.raised, 4.5], ['warn/bg', v.warn, v.bg, 4.5],
    ['focus/bg', v.focus, v.bg, 3], ['focus/surface', v.focus, v.surface, 3],
    ['bg tip text', v.bg, v.ink, 4.5], ['border-strong/bg', mix(v.bg, v.ink, mode === 'dark' ? 0.42 : 0.48), v.bg, 3],
  ];
  let worstKey = 99;
  for (let h = 0; h < 360; h += 30) worstKey = Math.min(worstKey, cr(hex('#101320'), hsl(h, 62, keyL)));
  checks.push(['key-ink/key fills (worst hue)', [0, 0, 0], [0, 0, 0], 0]);
  for (const [name, a, b, min] of checks) {
    if (name.startsWith('key-ink')) { const ok = worstKey >= 4.5; if (!ok) bad++; console.log(`${ok ? 'ok ' : 'FAIL'} ${style}/${mode} ${name} ${worstKey.toFixed(2)}`); continue; }
    const r = cr(a, b); const ok = r >= min; if (!ok) bad++;
    if (!ok) console.log(`FAIL ${style}/${mode} ${name} ${r.toFixed(2)} (< ${min})`);
  }
}
console.log(bad ? `${bad} failing pairs` : 'all pairs pass');
