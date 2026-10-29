// Fails if any palette has a text/background pair below WCAG AA (4.5 to 1). Run by `npm run build`.
import { PALETTES } from "../src/themes.js";

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);

const pairs = [
  ["ink", "paper"], ["ink", "raised"], ["muted", "paper"], ["muted", "raised"], ["ink", "primaryBg"],
  ["onPrimary", "primary"], ["primary", "paper"], ["primary", "raised"], ["primary", "primaryBg"], ["warm", "warmBg"],
];
let bad = 0;
for (const p of PALETTES) {
  for (const mode of ["light", "dark"]) {
    for (const [fg, bg] of pairs) {
      const r = ratio(p[mode][fg], p[mode][bg]);
      if (r < 4.5) {
        bad++;
        console.error(`${p.id} ${mode}: ${fg} on ${bg} is ${r.toFixed(2)} (needs 4.5)`);
      }
    }
  }
}
if (bad) process.exit(1);
console.log(`Palettes OK: ${PALETTES.length} palettes, light and dark, all pairs at least 4.5 to 1.`);
