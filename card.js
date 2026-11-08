// The daily word card (1080×640), a port of card_generator.py (Pillow) to SVG so the Worker can
// rasterise it with resvg. Same layout, palette, fonts (DejaVu) and coordinates as the Python card.
// Pure functions only: card-worker.js loads the fonts/image and renders the PNG.
import { Resvg } from '@resvg/resvg-wasm';

const C = {
  bgDeep: 'rgb(8,16,26)', bgRight: 'rgb(6,13,21)', teal: 'rgb(0,212,200)', tealDim: 'rgb(0,130,124)',
  white: '#fff', black: '#000', greyLight: 'rgb(185,200,215)', greyMid: 'rgb(105,125,145)',
  pill: 'rgb(0,80,76)', egLabel: 'rgb(0,55,52)'
};
const W = 1080, H = 640, TEXT_LEFT = 44, TEXT_RIGHT = 688, MIKU_LEFT = 700;
const MAX_W = TEXT_RIGHT - TEXT_LEFT;
export const MIKU_HREF = 'https://assets.local/sgmigu.png'; // resolved from bytes by renderPng, never fetched

// ── font metrics: just enough TrueType (head, hhea, hmtx, cmap format 4) to measure text ──
export function parseFont(bytes) {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const tables = {};
  for (let i = 0, n = v.getUint16(4); i < n; i++) {
    const r = 12 + i * 16;
    tables[String.fromCharCode(...bytes.subarray(r, r + 4))] = v.getUint32(r + 8);
  }
  const upem = v.getUint16(tables.head + 18);
  const ascent = v.getInt16(tables.hhea + 4) / upem;
  const descent = -v.getInt16(tables.hhea + 6) / upem;
  const nMetrics = v.getUint16(tables.hhea + 34);
  const adv = (gid) => v.getUint16(tables.hmtx + 4 * Math.min(gid, nMetrics - 1)) / upem;

  // cmap: the Windows Unicode BMP subtable (3,1), format 4.
  let sub = 0;
  for (let i = 0, n = v.getUint16(tables.cmap + 2); i < n; i++) {
    const r = tables.cmap + 4 + i * 8;
    if (v.getUint16(r) === 3 && v.getUint16(r + 2) === 1) sub = tables.cmap + v.getUint32(r + 4);
  }
  const segX2 = v.getUint16(sub + 6), ends = sub + 14, starts = ends + segX2 + 2, deltas = starts + segX2, ranges = deltas + segX2;
  const glyph = (cp) => {
    for (let s = 0; s < segX2; s += 2) {
      if (cp > v.getUint16(ends + s)) continue;
      const start = v.getUint16(starts + s);
      if (cp < start) return 0;
      const ro = v.getUint16(ranges + s);
      if (!ro) return (cp + v.getInt16(deltas + s)) & 0xffff;
      const g = v.getUint16(ranges + s + ro + 2 * (cp - start));
      return g ? (g + v.getInt16(deltas + s)) & 0xffff : 0;
    }
    return 0;
  };
  const cache = new Map();
  const advance = (ch) => {
    if (!cache.has(ch)) { const g = glyph(ch.codePointAt(0)); cache.set(ch, g ? adv(g) : 0.6); }
    return cache.get(ch);
  };
  return { ascent, descent, width: (text, size) => [...text].reduce((w, ch) => w + advance(ch), 0) * size };
}

// Greedy word wrap, identical to card_generator._wrap.
export function wrap(font, text, size, maxW) {
  const lines = [];
  let cur = '';
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const test = cur ? `${cur} ${word}` : word;
    if (font.width(test, size) <= maxW) cur = test;
    else { if (cur) lines.push(cur); cur = word; }
  }
  if (cur) lines.push(cur);
  return lines;
}

// Trim to fit maxW, ending with "…".
export function fit(font, text, size, maxW) {
  if (font.width(text, size) <= maxW) return text;
  let t = text;
  while (t && font.width(`${t}…`, size) > maxW) t = t.slice(0, -1);
  return `${t.trimEnd()}…`;
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

// Pillow anchors → SVG baselines. "la": y is the ascender line; "lm"/"mm": y is the middle of ascender/descender.
const top = (font, y, size) => y + font.ascent * size;
const mid = (font, y, size) => y + ((font.ascent - font.descent) / 2) * size;

/**
 * @param card  { word, type, pronunciation, meaning, examples: string[], dateStr: "08 Nov 2026", dayStr: "Sunday" }
 * @param fonts { sans, sansBold, mono, monoBold } from parseFont
 * @param miku  { width, height } of sgmigu.png
 */
export function buildCardSvg(card, fonts, miku = { width: 884, height: 884 }) {
  const { sans, sansBold, mono, monoBold } = fonts;
  const out = [];
  const text = (font, family, weight, size, x, y, fill, s, extra = '') =>
    out.push(`<text x="${x}" y="${y.toFixed(1)}" font-family="${family}" font-weight="${weight}" font-size="${size}" fill="${fill}"${extra}>${esc(s)}</text>`);
  const SANS = 'DejaVu Sans', MONO = 'DejaVu Sans Mono';

  // Background, right-panel gradient, border, top stripe, corner brackets.
  out.push(`<defs><linearGradient id="rp" x1="${MIKU_LEFT}" x2="${W}" y1="0" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="${C.bgDeep}"/><stop offset="1" stop-color="${C.bgRight}"/></linearGradient>`
    + '<filter id="glow" x="-10%" y="-50%" width="120%" height="200%"><feGaussianBlur stdDeviation="8"/></filter></defs>');
  out.push(`<rect width="${W}" height="${H}" fill="${C.bgDeep}"/><rect x="${MIKU_LEFT}" width="${W - MIKU_LEFT}" height="${H}" fill="url(#rp)"/>`);
  out.push(`<rect x="18.5" y="18.5" width="${W - 37}" height="${H - 37}" rx="22" fill="none" stroke="${C.tealDim}"/>`);
  out.push(`<rect x="18" y="18" width="${W - 36}" height="9" rx="4.5" fill="${C.teal}"/>`);
  for (const [bx, by, sx, sy] of [[18, 18, 1, 1], [W - 18, 18, -1, 1], [18, H - 18, 1, -1], [W - 18, H - 18, -1, -1]]) {
    out.push(`<path d="M${bx + sx * 24} ${by}H${bx}V${by + sy * 24}" fill="none" stroke="${C.teal}" stroke-width="3"/>`);
  }

  // Title with a soft glow, then the word (shrunk to fit long phrases; the Pillow card just overflowed).
  const title = 'Miku Singlish word of the day leh?';
  text(sansBold, SANS, 'bold', 40, TEXT_LEFT, top(sansBold, 36, 40), C.teal, title, ' fill-opacity="0.2" filter="url(#glow)"');
  text(sansBold, SANS, 'bold', 40, TEXT_LEFT, top(sansBold, 36, 40), C.teal, title);
  const word = card.word.toUpperCase();
  let wordSize = 74;
  while (wordSize > 36 && sansBold.width(word, wordSize) > MAX_W) wordSize -= 2;
  text(sansBold, SANS, 'bold', wordSize, TEXT_LEFT, top(sansBold, 94 + (74 - wordSize) * 0.6, wordSize), C.white, fit(sansBold, word, wordSize, MAX_W));

  // Type pill + pronunciation.
  const ty = 178, typeText = fit(monoBold, card.type, 17, 300);
  const typeW = Math.trunc(monoBold.width(`  ${typeText}  `, 17));
  out.push(`<rect x="${TEXT_LEFT + 0.5}" y="${ty + 0.5}" width="${typeW}" height="26" rx="6" fill="${C.pill}" stroke="${C.tealDim}"/>`);
  text(monoBold, MONO, 'bold', 17, TEXT_LEFT + typeW / 2, mid(monoBold, ty + 13, 17), C.white, typeText, ' text-anchor="middle"');
  const pronX = TEXT_LEFT + typeW + 12;
  text(monoBold, MONO, 'bold', 17, pronX, mid(monoBold, ty + 13, 17), C.greyMid, fit(monoBold, `/${card.pronunciation}/`, 17, TEXT_RIGHT - pronX));

  // Meaning: two lines, as before ("…" now marks a cut instead of dropping text silently).
  text(monoBold, MONO, 'bold', 14, TEXT_LEFT, top(monoBold, 218, 14), C.tealDim, 'MEANING');
  const mLines = wrap(sans, card.meaning, 20, MAX_W);
  if (mLines.length > 2) mLines[1] = fit(sans, `${mLines[1]} ${mLines[2]}`, 20, MAX_W);
  let cy = 236;
  for (const line of mLines.slice(0, 2)) { text(sans, SANS, 'normal', 20, TEXT_LEFT, top(sans, cy, 20), C.greyLight, line); cy += 25; }

  // Examples box: teal background, black text, up to three sentences.
  const examples = (card.examples || []).slice(0, 3).filter(Boolean);
  if (examples.length) {
    const exY = Math.max(cy + 14, 300);
    const indent = TEXT_LEFT + Math.trunc(monoBold.width('eg.  ', 14));
    const exMaxW = TEXT_RIGHT - indent - 8;
    const all = examples.map((ex) => wrap(sansBold, ex, 19, exMaxW));
    const LINE_H = 26, GAP = 8;
    const boxH = all.reduce((n, l) => n + l.length, 0) * LINE_H + (all.length - 1) * GAP + 22;
    out.push(`<rect x="${TEXT_LEFT - 8}" y="${exY}" width="${TEXT_RIGHT - TEXT_LEFT + 8}" height="${boxH}" rx="10" fill="${C.teal}"/>`);
    text(monoBold, MONO, 'bold', 14, TEXT_LEFT, mid(monoBold, exY + Math.trunc(boxH / 2), 14), C.egLabel, 'eg.');
    let ey = exY + 11;
    all.forEach((lines, i) => {
      for (const line of lines) { text(sansBold, SANS, 'bold', 19, indent, top(sansBold, ey, 19), C.black, line); ey += LINE_H; }
      if (i < all.length - 1) {
        out.push(`<path d="M${indent} ${ey + GAP / 2 - 0.5}H${TEXT_RIGHT - 12}" stroke="${C.pill}"/>`);
        ey += GAP;
      }
    });
  }

  // Migu figure: right panel, bottom-anchored; date block centred in the space above it.
  const pW = W - MIKU_LEFT, pH = H - 24;
  let mw = pW, mh = Math.trunc(miku.height * (pW / miku.width));
  if (mh > pH) { mw = Math.trunc(miku.width * (pH / miku.height)); mh = pH; }
  const mx = MIKU_LEFT + Math.trunc((pW - mw) / 2), my = H - mh - 10;
  out.push(`<image href="${MIKU_HREF}" x="${mx}" y="${my}" width="${mw}" height="${mh}"/>`);
  const cx = MIKU_LEFT + pW / 2, blankMid = Math.trunc((34 + my - 12) / 2);
  text(mono, MONO, 'normal', 14, cx, mid(mono, blankMid - 16, 14), C.tealDim, card.dayStr.toUpperCase(), ' text-anchor="middle"');
  text(sansBold, SANS, 'bold', 22, cx, mid(sansBold, blankMid + 8, 22), C.white, card.dateStr, ' text-anchor="middle"');

  text(mono, MONO, 'normal', 13, W / 2, mid(mono, H - 34, 13), C.greyMid, '@mikusinglishwordofthedaylehbot  •  TheBooleanJulian', ' text-anchor="middle" xml:space="preserve"');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out.join('')}</svg>`;
}

// Rasterise. initWasm must have run first (card-worker.js in the Worker, the test in Node).
export function renderPng(svg, fontBuffers, mikuPng) {
  const resvg = new Resvg(svg, { font: { fontBuffers, loadSystemFonts: false, defaultFontFamily: 'DejaVu Sans' } });
  for (const href of resvg.imagesToResolve()) resvg.resolveImage(href, mikuPng);
  const img = resvg.render();
  const png = img.asPng();
  img.free();
  resvg.free();
  return png;
}

// "2026-11-08" → { dateStr: "08 Nov 2026", dayStr: "Sunday" }, as bot.py passed them (%d %b %Y, %A).
// Fixed English names: ICU's en-GB short month for September is "Sept", Python's %b is "Sep".
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export function cardDates(isoDate) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return { dateStr: `${String(d.getUTCDate()).padStart(2, '0')} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`, dayStr: DAYS[d.getUTCDay()] };
}

// PNG width/height from the IHDR chunk.
export const pngSize = (b) => ({ width: new DataView(b.buffer, b.byteOffset).getUint32(16), height: new DataView(b.buffer, b.byteOffset).getUint32(20) });
