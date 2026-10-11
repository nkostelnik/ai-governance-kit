"""Draw docs/social-preview.png (1280x640), the GitHub social preview image.

    pip install pillow   # only needed to regenerate the image; not a project dependency
    python docs/make_social_preview.py

Matches the companion NDA triage project's style. Uses Windows fonts.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
BG, FG, MUTED, LINE = "#0f172a", "#f8fafc", "#94a3b8", "#334155"
FONTS = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def centered(draw: ImageDraw.ImageDraw, y: int, text: str, f, fill) -> None:
    w = draw.textlength(text, font=f)
    draw.text(((W - w) / 2, y), text, font=f, fill=fill)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# Tier pills
pills = [("LOW", "#22c55e"), ("MEDIUM", "#eab308"), ("HIGH", "#f97316"), ("PROHIBITED", "#ef4444")]
pill_font = font("segoeuib.ttf", 24)
widths = [d.textlength(t, font=pill_font) + 56 for t, _ in pills]
gap = 22
x = (W - sum(widths) - gap * (len(pills) - 1)) / 2
for (text, color), w in zip(pills, widths):
    d.rounded_rectangle([x, 96, x + w, 142], radius=23, fill=color)
    tw = d.textlength(text, font=pill_font)
    d.text((x + (w - tw) / 2, 103), text, font=pill_font, fill=BG)
    x += w + gap

centered(d, 178, "AI Governance Kit", font("georgiab.ttf", 76), FG)
sub = font("segoeui.ttf", 29)
centered(d, 290, "Tiers proposed AI uses and reviews AI vendor terms against", sub, MUTED)
centered(d, 330, "an attorney's rubric. The model reads; the rubric decides.", sub, MUTED)

# Pipeline row
d.line([160, 404, W - 160, 404], fill=LINE, width=2)
d.line([160, 474, W - 160, 474], fill=LINE, width=2)
steps = ["intake", "verify", "tier", "vendor review", "register", "memo", "evals"]
step_font = sep_font = font("consola.ttf", 24)
sep = " > "
total = sum(d.textlength(s, font=step_font) for s in steps) + d.textlength(sep, font=sep_font) * (len(steps) - 1)
x = (W - total) / 2
for i, step in enumerate(steps):
    d.text((x, 424), step, font=step_font, fill=FG)
    x += d.textlength(step, font=step_font)
    if i < len(steps) - 1:
        d.text((x, 424), sep, font=sep_font, fill=MUTED)
        x += d.textlength(sep, font=sep_font)

centered(d, 532, "Python  |  Claude  |  Pydantic  |  Attorney review required. Not legal advice.",
         font("segoeui.ttf", 23), MUTED)

out = Path(__file__).resolve().parent / "social-preview.png"
img.save(out)
print(out)
