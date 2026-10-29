// Color palettes for the app. Each has a light and a dark set. Status colors (green for ok, red for danger)
// stay the same in every palette on purpose: they carry meaning. scripts/check-palettes.mjs checks contrast.

export const DEFAULT_PALETTE = "teal";

const W = { warm: "#A24B08", warmBg: "#FDF1E0" };
const WD = { warm: "#F2B66B", warmBg: "#2B2316" };

export const PALETTES = [
  {
    id: "teal", name: "Scrubs teal", note: "Calm, hospital-fresh",
    light: { ink: "#10302C", paper: "#F6FAF9", raised: "#FFFFFF", muted: "#4B6460", line: "#D3E3E0", primary: "#0F766E", onPrimary: "#FFFFFF", primaryBg: "#E3F3F0", ...W },
    dark: { ink: "#E6F2F0", paper: "#0E1918", raised: "#162423", muted: "#A8C1BD", line: "#284240", primary: "#4FC3B5", onPrimary: "#06201D", primaryBg: "#12302D", ...WD },
  },
  {
    id: "blue", name: "Clinical blue", note: "Trusted, familiar",
    light: { ink: "#13233A", paper: "#F6F9FC", raised: "#FFFFFF", muted: "#4A5C73", line: "#D5E0EC", primary: "#1D5FA8", onPrimary: "#FFFFFF", primaryBg: "#E6F0FA", ...W },
    dark: { ink: "#E6EEF8", paper: "#0E1620", raised: "#162230", muted: "#A9B9CC", line: "#28384D", primary: "#6FA8E8", onPrimary: "#071526", primaryBg: "#172B45", ...WD },
  },
  {
    id: "sage", name: "Sage and coral", note: "Soft, caring, human",
    light: { ink: "#1D2B27", paper: "#F7FAF8", raised: "#FFFFFF", muted: "#4F625C", line: "#D7E3DD", primary: "#35705D", onPrimary: "#FFFFFF", primaryBg: "#E8F2EE", warm: "#AF3C22", warmBg: "#FBEAE5" },
    dark: { ink: "#E7F0EC", paper: "#0F1815", raised: "#17231F", muted: "#AABFB7", line: "#2A4039", primary: "#6DBFA3", onPrimary: "#07201A", primaryBg: "#172E27", warm: "#F09A85", warmBg: "#35201B" },
  },
  {
    id: "lavender", name: "Lavender", note: "Quiet and gentle",
    light: { ink: "#221B3A", paper: "#F9F8FC", raised: "#FFFFFF", muted: "#4D4666", line: "#DDD8EB", primary: "#5B459E", onPrimary: "#FFFFFF", primaryBg: "#EEEAF8", ...W },
    dark: { ink: "#ECE8F8", paper: "#14111F", raised: "#1D1930", muted: "#BDB5D6", line: "#342E50", primary: "#A593E8", onPrimary: "#130B2E", primaryBg: "#2A2250", ...WD },
  },
  {
    id: "navy", name: "Navy and aqua", note: "Deep and steady",
    light: { ink: "#0F2233", paper: "#F5F9FB", raised: "#FFFFFF", muted: "#445A6B", line: "#D2DEE8", primary: "#1B4F72", onPrimary: "#FFFFFF", primaryBg: "#E3EEF6", ...W },
    dark: { ink: "#E4EDF5", paper: "#0C1620", raised: "#14212E", muted: "#A5B7C7", line: "#263A4C", primary: "#5FA8D8", onPrimary: "#061827", primaryBg: "#12304A", ...WD },
  },
  {
    id: "rose", name: "Rose", note: "Warm and kind",
    light: { ink: "#3A1824", paper: "#FDF8FA", raised: "#FFFFFF", muted: "#6A4C58", line: "#EBD6DE", primary: "#A62F5B", onPrimary: "#FFFFFF", primaryBg: "#FBE8EF", warm: "#8A5A00", warmBg: "#FDF3DC" },
    dark: { ink: "#F6E9EF", paper: "#1B1217", raised: "#261A21", muted: "#CDB0BD", line: "#44303A", primary: "#E889AB", onPrimary: "#2A0A18", primaryBg: "#3D1A29", warm: "#E8C06A", warmBg: "#2E2512" },
  },
];

const vars = (t) =>
  `--ink: ${t.ink}; --paper: ${t.paper}; --paper-raised: ${t.raised}; --muted: ${t.muted}; --line: ${t.line}; ` +
  `--primary: ${t.primary}; --on-primary: ${t.onPrimary}; --primary-bg: ${t.primaryBg}; ` +
  `--indigo: ${t.primary}; --indigo-bg: ${t.primaryBg}; --warm: ${t.warm}; --warm-bg: ${t.warmBg};`;

export function isPalette(id) {
  return PALETTES.some((p) => p.id === id);
}

export function paletteCss() {
  return PALETTES.map(
    (p) => `.scheduler-root.pal-${p.id} { ${vars(p.light)} }\n.scheduler-root.pal-${p.id}.dark { ${vars(p.dark)} }`
  ).join("\n");
}
