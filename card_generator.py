"""
Card generator — Miku's Singlish Word of the Day Bot
Clean layout: no dots, no lines. Date in right panel above Migu.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

# ── Palette ────────────────────────────────────────────────────────────────────
BG_DEEP      = (8,   16,  26)
BG_RIGHT     = (6,   13,  21)
TEAL_PRIMARY = (0,   212, 200)
TEAL_DIM     = (0,   130, 124)
WHITE        = (255, 255, 255)
BLACK        = (0,   0,   0)
GREY_LIGHT   = (185, 200, 215)
GREY_MID     = (105, 125, 145)
PINK_ACCENT  = (255, 80,  180)

CARD_W, CARD_H = 1080, 640
TEXT_LEFT  = 44
TEXT_RIGHT = 688    # hard right edge — all text/boxes stay left of this
MIKU_LEFT  = 700    # Migu panel starts here

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MIKU_PATH  = os.path.join(SCRIPT_DIR, "assets", "sgmigu.png")
FONT_DIR   = os.path.join(SCRIPT_DIR, "fonts")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for path in [
        os.path.join(FONT_DIR, name),
        f"/usr/share/fonts/truetype/dejavu/{name}",
        f"/usr/share/fonts/truetype/liberation/{name}",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _rr(draw, xy, radius, fill=None, outline=None, lw=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=lw)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def generate_card(
    word: str,
    word_type: str,
    pronunciation: str,
    meaning: str,
    examples: list[str],    # list of 3 sentences
    date_str: str,          # e.g. "15 Apr 2025"
    day_str: str,           # e.g. "Wednesday"
    output_path: str = "/tmp/miku_wotd.png",
) -> str:
    """Render the card and return the output path."""

    # ── Canvas ─────────────────────────────────────────────────────────────────
    img  = Image.new("RGBA", (CARD_W, CARD_H), BG_DEEP)
    draw = ImageDraw.Draw(img)

    # Left→right gradient (left panel slightly lighter)
    for x in range(CARD_W):
        if x < MIKU_LEFT:
            col = BG_DEEP
        else:
            t   = (x - MIKU_LEFT) / (CARD_W - MIKU_LEFT)
            col = tuple(int(BG_DEEP[i] * (1 - t) + BG_RIGHT[i] * t) for i in range(3))
        draw.line([(x, 0), (x, CARD_H)], fill=col + (255,))

    # Outer border
    _rr(draw, [18, 18, CARD_W - 18, CARD_H - 18], radius=22, outline=TEAL_DIM, lw=1)

    # Top accent stripe
    draw.rounded_rectangle([18, 18, CARD_W - 18, 27], radius=22, fill=TEAL_PRIMARY)

    # Corner L-brackets
    bs, bw = 24, 3
    for bx, by, sx, sy in [
        (18, 18, 1, 1), (CARD_W - 18, 18, -1, 1),
        (18, CARD_H - 18, 1, -1), (CARD_W - 18, CARD_H - 18, -1, -1),
    ]:
        draw.line([(bx, by), (bx + sx * bs, by)], fill=TEAL_PRIMARY, width=bw)
        draw.line([(bx, by), (bx, by + sy * bs)], fill=TEAL_PRIMARY, width=bw)

    # ── Fonts ──────────────────────────────────────────────────────────────────
    f_title  = _font("DejaVuSans-Bold.ttf",    40)
    f_word   = _font("DejaVuSans-Bold.ttf",    74)
    f_tag    = _font("DejaVuSansMono-Bold.ttf", 17)
    f_label  = _font("DejaVuSansMono-Bold.ttf", 14)
    f_body   = _font("DejaVuSans.ttf",          20)
    f_ex     = _font("DejaVuSans-Bold.ttf",     19)
    f_date   = _font("DejaVuSans-Bold.ttf",     22)
    f_day    = _font("DejaVuSansMono.ttf",      14)
    f_footer = _font("DejaVuSansMono.ttf",      13)

    MAX_W = TEXT_RIGHT - TEXT_LEFT   # 644px

    # ── TITLE ──────────────────────────────────────────────────────────────────
    title = "Miku Singlish word of the day leh?"
    glow  = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd    = ImageDraw.Draw(glow)
    gd.text((TEXT_LEFT, 36), title, font=f_title, fill=(0, 212, 200, 50))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8)))
    draw = ImageDraw.Draw(img)
    draw.text((TEXT_LEFT, 36), title, font=f_title, fill=TEAL_PRIMARY)

    # ── WORD ───────────────────────────────────────────────────────────────────
    draw.text((TEXT_LEFT, 94), word.upper(), font=f_word, fill=WHITE)

    # Type pill + pronunciation
    ty        = 178
    type_text = f"  {word_type}  "
    type_w    = int(draw.textlength(type_text, font=f_tag))
    _rr(draw, [TEXT_LEFT, ty, TEXT_LEFT + type_w, ty + 26],
        radius=6, fill=(0, 80, 76), outline=TEAL_DIM, lw=1)
    draw.text((TEXT_LEFT + type_w // 2, ty + 13), type_text,
              font=f_tag, fill=WHITE, anchor="mm")
    draw.text((TEXT_LEFT + type_w + 12, ty + 13), f"/{pronunciation}/",
              font=f_tag, fill=GREY_MID, anchor="lm")

    # ── MEANING ────────────────────────────────────────────────────────────────
    draw.text((TEXT_LEFT, 218), "MEANING", font=f_label, fill=TEAL_DIM)
    m_lines = _wrap(draw, meaning, f_body, MAX_W)
    cy = 236
    for line in m_lines[:2]:
        draw.text((TEXT_LEFT, cy), line, font=f_body, fill=GREY_LIGHT)
        cy += 25

    # ── EXAMPLES BOX — cyan bg, black text, 3 sentences ───────────────────────
    ex_y      = max(cy + 14, 300)
    eg_label  = "eg."
    eg_w      = int(draw.textlength(eg_label + "  ", font=f_label))
    indent    = TEXT_LEFT + eg_w
    ex_max_w  = TEXT_RIGHT - indent - 8

    all_ex_lines = [_wrap(draw, ex, f_ex, ex_max_w) for ex in examples[:3]]

    LINE_H    = 26
    GAP       = 8
    total_lines = sum(len(l) for l in all_ex_lines)
    box_h     = total_lines * LINE_H + (len(all_ex_lines) - 1) * GAP + 22

    _rr(draw, [TEXT_LEFT - 8, ex_y, TEXT_RIGHT, ex_y + box_h], radius=10, fill=TEAL_PRIMARY)

    draw.text((TEXT_LEFT, ex_y + box_h // 2), eg_label,
              font=f_label, fill=(0, 55, 52), anchor="lm")

    ey = ex_y + 11
    for i, lines in enumerate(all_ex_lines):
        for line in lines:
            draw.text((indent, ey), line, font=f_ex, fill=BLACK)
            ey += LINE_H
        if i < len(all_ex_lines) - 1:
            draw.line(
                [(indent, ey + GAP // 2 - 1), (TEXT_RIGHT - 12, ey + GAP // 2 - 1)],
                fill=(0, 80, 76), width=1,
            )
            ey += GAP

    # ── MIGU FIGURE — right panel, bottom-anchored ────────────────────────────
    migu_y_start = CARD_H
    try:
        miku  = Image.open(MIKU_PATH).convert("RGBA")
        p_w   = CARD_W - MIKU_LEFT          # 380px
        p_h   = CARD_H - 24
        ratio = p_w / miku.width
        new_w, new_h = p_w, int(miku.height * ratio)
        if new_h > p_h:
            ratio = p_h / miku.height
            new_w, new_h = int(miku.width * ratio), p_h
        miku         = miku.resize((new_w, new_h), Image.LANCZOS)
        mx           = MIKU_LEFT + (p_w - new_w) // 2
        my           = CARD_H - new_h - 10
        migu_y_start = my
        img.alpha_composite(miku, dest=(mx, my))
    except Exception:
        pass
    draw = ImageDraw.Draw(img)

    # ── DATE BLOCK — centred in blank space above Migu ────────────────────────
    right_cx  = MIKU_LEFT + (CARD_W - MIKU_LEFT) // 2   # 890
    blank_mid = (34 + migu_y_start - 12) // 2
    draw.text((right_cx, blank_mid - 16), day_str.upper(),
              font=f_day, fill=TEAL_DIM, anchor="mm")
    draw.text((right_cx, blank_mid + 8),  date_str,
              font=f_date, fill=WHITE, anchor="mm")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    draw.text((CARD_W // 2, CARD_H - 34),
              "@mikusinglishwordofthedaylehbot  •  TheBooleanJulian",
              font=f_footer, fill=GREY_MID, anchor="mm")

    img.convert("RGB").save(output_path, "PNG", quality=95)
    return output_path
