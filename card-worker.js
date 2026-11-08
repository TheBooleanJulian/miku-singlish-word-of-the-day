// Worker-side card rendering: resvg's wasm (bundled by wrangler as a compiled module), the DejaVu fonts
// and sgmigu.png (served from ./assets through the ASSETS binding). Loaded once per isolate.
// worker.js imports this lazily and falls back to the plain photo if anything here fails.
import { initWasm } from '@resvg/resvg-wasm';
import resvgWasm from '@resvg/resvg-wasm/index_bg.wasm';
import { parseFont, buildCardSvg, renderPng, cardDates, pngSize } from './card.js';

const FONT_FILES = { sans: 'DejaVuSans.ttf', sansBold: 'DejaVuSans-Bold.ttf', mono: 'DejaVuSansMono.ttf', monoBold: 'DejaVuSansMono-Bold.ttf' };
let loading = null;

async function asset(env, path) {
  const res = await env.ASSETS.fetch(new Request(`https://assets.local/${path}`));
  if (!res.ok) throw new Error(`asset ${path}: ${res.status}`);
  return new Uint8Array(await res.arrayBuffer());
}

function load(env) {
  loading ??= (async () => {
    await initWasm(resvgWasm);
    const names = Object.keys(FONT_FILES);
    const buffers = await Promise.all(names.map((k) => asset(env, `fonts/${FONT_FILES[k]}`)));
    const miku = await asset(env, 'sgmigu.png');
    return { fonts: Object.fromEntries(names.map((k, i) => [k, parseFont(buffers[i])])), buffers, miku, mikuSize: pngSize(miku) };
  })().catch((err) => { loading = null; throw err; });
  return loading;
}

// post: { date: "YYYY-MM-DD", entry, content } as stored by worker.js. Returns PNG bytes.
export async function renderCardPng(env, post) {
  const { fonts, buffers, miku, mikuSize } = await load(env);
  const svg = buildCardSvg({
    word: post.entry.word,
    type: post.entry.type,
    pronunciation: post.entry.pronunciation,
    meaning: post.entry.meaning,
    examples: post.content?.examples || [],
    ...cardDates(post.date)
  }, fonts, mikuSize);
  return renderPng(svg, buffers, miku);
}
