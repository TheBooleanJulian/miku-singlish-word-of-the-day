"""Import Singlish / Singapore English entries from English Wiktionary.

Writes ``wiktionary_words.json`` next to ``singlish_words.py``. Entries whose
word already exists in the hand-curated bank are skipped, so the curated
definitions always win.

Source and licence: definitions come from Wiktionary (https://en.wiktionary.org),
written by Wiktionary contributors and licensed CC BY-SA 4.0. They are condensed
(only Singapore/Singlish-labelled senses kept, trimmed to fit a card) and each
entry records its source page URL. See the README's licence section.

Stdlib only. Usage (from the repo root):

    python scripts/import_wiktionary.py [--cache-dir DIR] [--limit N]

``--cache-dir`` keeps downloaded page HTML so re-runs don't hit Wiktionary again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from singlish_words import CURATED_WORDS, normalise_word  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "wiktionary_words.json"
API = "https://en.wiktionary.org/w/api.php"
PAGE_HTML = "https://en.wiktionary.org/api/rest_v1/page/html/"
CATEGORIES = ["Category:Singlish", "Category:Singapore English"]
USER_AGENT = (
    "miku-singlish-word-of-the-day/1.0 "
    "(https://github.com/TheBooleanJulian/miku-singlish-word-of-the-day)"
)
REQUEST_GAP_S = 0.15          # polite pacing between uncached requests
MAX_MEANING = 300             # card shows 2 lines; caption shows the full text

POS_HEADINGS = {
    "noun", "proper noun", "verb", "adjective", "adverb", "interjection",
    "particle", "phrase", "prepositional phrase", "pronoun", "preposition",
    "conjunction", "determiner", "numeral", "prefix", "suffix", "idiom",
    "proverb", "contraction", "classifier", "abbreviation", "initialism",
    "acronym", "symbol",
}
REGION_RE = re.compile(r"\b(Singapore|Singlish)\b", re.I)
# Hedged labels ("mildly/sometimes derogatory": kiasuism, chapalang) stay in the
# default pool; ethnic slurs, vulgarity and plain "derogatory" are gated.
NSFW_RE = re.compile(
    r"vulgar|obscene|offensive|slur|racist|sexual|"
    r"(?<!mildly )(?<!sometimes )(?<!possibly )(?<!often )derogatory",
    re.I,
)
# Some explicit senses carry no label at all ("ku ku bird: Penis"), so check the gloss too.
NSFW_GLOSS_RE = re.compile(
    r"\b(fuck\w*|penis(es)?|vagina\w*|cunts?|cocks?|dicks?|testicles?|scrotum|semen|"
    r"masturbat\w*|prostitut\w*|sex|sexual\w*|shit\w*|arse\w*|asshole\w*|bitch\w*|"
    r"whores?|sluts?|bastards?|genitals?|genitalia|buttocks?)\b",
    re.I,
)
# Inflection / error entries add nothing useful to a word-of-the-day bank.
SKIP_GLOSS_RE = re.compile(
    r"^(plural of|misspelling of|present participle of|simple past|past participle of|"
    r"third-person singular|obsolete form of|archaic form of|comparative form of|"
    r"superlative form of|used other than figuratively or idiomatically)\b",
    re.I,
)
# Glosses that only point at another entry: "Initialism of pa chew cheng."
POINTER_KINDS = (r"alternative (?:form|spelling|letter-case form)|initialism|abbreviation|"
                 r"acronym|clipping|synonym|ellipsis|contraction|short form")
POINTER_RE = re.compile(rf"^({POINTER_KINDS}) of\s+(.+?)(?:\s*[(:;.,]|$)", re.I)
# The whole gloss is just the pointer, e.g. "Alternative spelling of agak-agak (“to estimate”)."
BARE_POINTER_RE = re.compile(rf"^({POINTER_KINDS}) of\s+[^.()]+(\s*\([^)]*\))?\s*\.?$", re.I)
# Drop text inside these when extracting a gloss.
SKIP_TAGS = {"ul", "ol", "dl", "sup", "style", "script", "table", "link", "meta"}
SKIP_CLASS_RE = re.compile(r"usage-label-sense|citation-whole|nyms|maintenance|h-usage-example|reference")


# ── tiny DOM ──────────────────────────────────────────────────────────────────
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "source", "track", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs), [], parent

    @property
    def cls(self) -> str:
        return self.attrs.get("class") or ""

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def text(self, skip=None) -> str:
        out = []
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            elif not (skip and skip(c)):
                out.append(c.text(skip))
        return "".join(out)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(html: str) -> Node:
    b = TreeBuilder()
    b.feed(html)
    return b.root


def clean(text: str) -> str:
    text = re.sub(r"[​‎‏]", "", text)   # zero-width / direction marks
    text = re.sub(r"\s+", " ", text).strip()
    # Legacy Telegram Markdown chokes on these; the bot sends meanings with it.
    text = text.replace("`", "'").replace("*", "").replace("_", " ")
    text = text.replace("[", "(").replace("]", ")")
    text = re.sub(r"\(\s*\)", "", text)
    return re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s+", " ", text)).strip()


def _skip_in_gloss(n: Node) -> bool:
    return n.tag in SKIP_TAGS or bool(SKIP_CLASS_RE.search(n.cls))


# ── extraction ────────────────────────────────────────────────────────────────
def extract_entry(title: str, html: str, regional_only: bool = True) -> dict | None:
    """Build a word-bank entry from a page's Singapore/Singlish senses.

    regional_only=False takes the first two English senses of any kind; used
    for the target of a pointer entry ("siew mai" -> "shumai").
    """
    root = parse_html(html)
    english = next((h.parent for h in root.iter() if h.tag == "h2" and h.attrs.get("id") == "English"), None)
    if english is None:
        return None

    senses: list[dict] = []
    pos_seen: list[str] = []
    ipa = ""

    def walk(section: Node, pos: str | None, term_regional: bool):
        nonlocal ipa
        for child in section.children:
            if not isinstance(child, Node):
                continue
            if child.tag == "section":
                head = next((c for c in child.children if isinstance(c, Node) and re.fullmatch(r"h[3-6]", c.tag)), None)
                name = clean(head.text()).lower() if head else ""
                if name in POS_HEADINGS:
                    walk(child, name, False)
                elif name.startswith("pronunciation"):
                    if not ipa:
                        ipa = pick_ipa(child)
                    walk(child, pos, term_regional)
                else:
                    walk(child, pos, term_regional)
            elif child.tag == "p" and pos:
                labels = " ".join(n.text() for n in child.iter() if "usage-label-term" in n.cls)
                if REGION_RE.search(labels):
                    term_regional = True
            elif child.tag == "ol" and pos:
                for li in child.children:
                    if isinstance(li, Node) and li.tag == "li":
                        take_sense(li, pos, term_regional)

    def take_sense(li: Node, pos: str, inherited: bool):
        label = " ".join(n.text() for n in li.children if isinstance(n, Node) and "usage-label-sense" in n.cls)
        regional = inherited or bool(REGION_RE.search(label)) or not regional_only
        gloss = clean(li.text(_skip_in_gloss))
        if regional and gloss:
            senses.append({"pos": pos, "gloss": gloss, "label": label})
            if pos not in pos_seen:
                pos_seen.append(pos)
        # Sub-senses (## lines) may carry the Singapore label themselves.
        for sub in li.children:
            if isinstance(sub, Node) and sub.tag == "ol":
                for sli in sub.children:
                    if isinstance(sli, Node) and sli.tag == "li":
                        take_sense(sli, pos, regional and not gloss)

    walk(english, None, False)

    kept, pointer = [], None
    for s in senses:
        if SKIP_GLOSS_RE.match(s["gloss"]):
            continue
        m = POINTER_RE.match(s["gloss"])
        if m and pointer is None:
            pointer = [m.group(1).capitalize(), m.group(2).strip(" '\"")]
        if s["gloss"] not in [k["gloss"] for k in kept]:
            kept.append(s)
    if not regional_only:
        kept = kept[:2]
    if not kept:
        return None

    entry = {
        "word": title,
        "type": " / ".join(p for p in pos_seen if any(k["pos"] == p for k in kept)),
        "pronunciation": ipa or title,
        "meaning": join_meanings([k["gloss"] for k in kept]),
        # %20 rather than "_": underscores in a URL can break Telegram Markdown.
        "source": "https://en.wiktionary.org/wiki/" + urllib.parse.quote(title, safe=""),
    }
    if NSFW_GLOSS_RE.search(title) or any(
        NSFW_RE.search(k["label"]) or NSFW_GLOSS_RE.search(k["gloss"]) for k in kept
    ):
        entry["nsfw"] = True
    if pointer:
        entry["_pointer"] = pointer   # resolved in a second pass, then removed
    return entry


def pick_ipa(section: Node) -> str:
    """First IPA transcription, preferring a line that mentions Singapore."""
    candidates = []
    for li in (n for n in section.iter() if n.tag == "li"):
        ipas = [n.text().strip() for n in li.iter() if "IPA" in n.cls.split()]
        ipas = [i for i in ipas if i[:1] in "/["]
        if ipas:
            candidates.append((bool(REGION_RE.search(li.text())), ipas[0]))
    if not candidates:
        return ""
    best = next((i for regional, i in candidates if regional), candidates[0][1])
    # "˭" (unaspirated) isn't in DejaVu Sans Mono, the card's font; aspirated
    # stops keep their "ʰ" so the contrast survives.
    return best.strip("/[]").replace("˭", "").strip()


def join_meanings(glosses: list[str]) -> str:
    glosses = [g[:1].upper() + g[1:] for g in glosses]
    if len(glosses) == 1:
        return _cap(glosses[0])
    out = ""
    for i, g in enumerate(glosses, 1):
        piece = f"{i}. {g}"
        if out and len(out) + 1 + len(piece) > MAX_MEANING:
            break
        out = f"{out} {piece}".strip()
    return _cap(out)


def _is_bare_alt(entry: dict) -> bool:
    """Meaning is only a pointer like 'Alternative spelling of X.' or 'Initialism of Y.'"""
    return all(BARE_POINTER_RE.match(re.sub(r"^\d+\.\s*", "", part.strip()))
               for part in re.split(r"(?=\b\d+\. )", entry["meaning"]) if part.strip())


def _self_pointer(entry: dict) -> bool:
    p = entry.get("_pointer")
    return bool(p) and normalise_word(p[1]) == normalise_word(entry["word"])


def _cap(text: str) -> str:
    if len(text) <= MAX_MEANING:
        return text
    cut = text[: MAX_MEANING - 1]
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


# ── network ───────────────────────────────────────────────────────────────────
def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            if e.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
        except urllib.error.URLError:
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    return ""


def category_titles(category: str) -> list[str]:
    titles, cont = [], {}
    while True:
        params = {"action": "query", "list": "categorymembers", "cmtitle": category,
                  "cmnamespace": "0", "cmlimit": "500", "format": "json", **cont}
        data = json.loads(http_get(API + "?" + urllib.parse.urlencode(params)))
        titles += [m["title"] for m in data["query"]["categorymembers"]]
        if "continue" not in data:
            return titles
        cont = {"cmcontinue": data["continue"]["cmcontinue"]}
        time.sleep(REQUEST_GAP_S)


def page_html(title: str, cache_dir: Path | None) -> str:
    name = urllib.parse.quote(title, safe="")
    if title != title.lower():   # "KPKB" vs "kpkb" on case-insensitive filesystems
        name += "~" + hashlib.md5(title.encode()).hexdigest()[:8]
    cache = cache_dir / (name + ".html") if cache_dir else None
    if cache and cache.exists():
        return cache.read_text(encoding="utf-8")
    html = http_get(PAGE_HTML + urllib.parse.quote(title.replace(" ", "_"), safe=""))
    time.sleep(REQUEST_GAP_S)
    if cache:
        cache.write_text(html, encoding="utf-8")
    return html


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", type=Path, help="keep downloaded page HTML here")
    ap.add_argument("--limit", type=int, help="only process the first N titles (testing)")
    args = ap.parse_args()
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)

    titles: list[str] = []
    for cat in CATEGORIES:
        for t in category_titles(cat):
            if t not in titles:
                titles.append(t)
    print(f"{len(titles)} titles across {len(CATEGORIES)} categories", file=sys.stderr)
    if args.limit:
        titles = titles[: args.limit]

    curated = {normalise_word(w["word"]) for w in CURATED_WORDS}
    entries, skipped_dupe, skipped_empty = {}, 0, 0
    for n, title in enumerate(titles, 1):
        if normalise_word(title) in curated:
            skipped_dupe += 1
            continue
        entry = extract_entry(title, page_html(title, args.cache_dir))
        if not entry:
            skipped_empty += 1
            continue
        if n % 100 == 0:
            print(f"  {n}/{len(titles)}", file=sys.stderr)
        key = normalise_word(title)
        if key in entries:
            skipped_dupe += 1
            # "agak agak" vs "agak-agak": keep whichever has a real definition;
            # "kpkb" (-> "KPKB") vs "KPKB" (-> "kao peh kao bu"): the one that
            # points somewhere other than its own case variant.
            old = entries[key]
            if (_is_bare_alt(old) and not _is_bare_alt(entry)) or (
                _self_pointer(old) and not _self_pointer(entry)
            ):
                entries[key] = entry
            continue
        entries[key] = entry

    # Pointer entries ("Alternative spelling of X", "Initialism of Y"): append the
    # target's meaning and nsfw flag. Targets outside the two categories are
    # fetched individually, falling back to their general English senses.
    # A few passes so chains (ba zhang -> bak chang -> zongzi) resolve.
    by_key = {normalise_word(w["word"]): w for w in CURATED_WORDS}
    by_key.update(entries)
    pending = {k: e.pop("_pointer") for k, e in entries.items() if "_pointer" in e}

    fetched: dict[str, dict] = {}

    def fetch(target: str) -> dict:
        if target not in fetched:
            html = page_html(target, args.cache_dir)
            t = extract_entry(target, html) or extract_entry(target, html, regional_only=False) or {}
            t.pop("_pointer", None)
            fetched[target] = t
        return fetched[target]

    def lookup(target: str, pointer_entry: dict) -> dict:
        key = normalise_word(target)
        if key not in by_key:
            by_key[key] = fetch(target)
        found = by_key[key]
        # "kpkb" -> "KPKB" normalise to the same key; fetch the exact page instead.
        return fetch(target) if found is pointer_entry else found

    for _ in range(3):
        for key, (kind, target) in list(pending.items()):
            e = entries[key]
            t = lookup(target, e) if _is_bare_alt(e) else None
            if t is None:
                del pending[key]            # has a real definition already
            elif t and t is not e and not _is_bare_alt(t):
                e["meaning"] = _cap(f"{kind} of '{t['word']}'. {t['meaning']}")
                if t.get("nsfw"):
                    e["nsfw"] = True
                del pending[key]

    out = sorted(entries.values(), key=lambda e: e["word"].lower())
    OUTPUT_PATH.write_text(
        "[\n" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in out) + "\n]\n",
        encoding="utf-8",
    )
    print(f"wrote {len(out)} entries to {OUTPUT_PATH.name} "
          f"(skipped {skipped_dupe} duplicates, {skipped_empty} with no usable Singapore sense)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
