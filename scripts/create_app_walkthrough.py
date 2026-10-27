"""Render a captioned RiskSense AI walkthrough from current repo assets.

The visuals are illustrative. No patient records or live credentials are used.
Requires Pillow and a temporary imageio-ffmpeg install (see deliverables/README.md).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
APP = PROJECTS / "medguide"
SITE = PROJECTS / "shitwebsite"
OUTPUT = ROOT / "deliverables" / "risksense_ai_app_walkthrough.mp4"
POSTER = ROOT / "deliverables" / "risksense_ai_app_walkthrough_poster.png"
FONT = APP / "assets" / "fonts" / "Rubik-Regular.ttf"
FONT_MEDIUM = APP / "assets" / "fonts" / "Rubik-Medium.ttf"
LOGO = APP / "assets" / "images" / "risksense_logo.jpg"
DASHBOARD = ROOT / "deliverables" / "latest_dashboard_preview.png"
if not DASHBOARD.exists():
    DASHBOARD = SITE / "public" / "images" / "dashboard-dark-demo.png"

W, H, FPS = 960, 540, 15
NAVY = (8, 18, 35)
WHITE = (239, 247, 252)
MUTED = (170, 193, 211)
CYAN = (82, 211, 214)
BLUE = (116, 178, 242)


def font(size: int, medium: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_MEDIUM if medium else FONT), size)


def fit_image(path: Path, width: int, height: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    scale = min(width / image.width, height / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), (13, 28, 47))
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas


def lines(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    result: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=fnt) > max_width:
            result.append(line)
            line = word
        else:
            line = candidate
    if line:
        result.append(line)
    return result


SCENES = [
    ("WELCOME", "RiskSense AI", "A guided tour of the latest patient app", LOGO, 3.5),
    ("01 / GET STARTED", "Sign in and activate", "Register in the app, verify your account, then complete access setup on the website. Existing members can sign in directly.", APP / "assets/onboarding/slide-1.png", 5.0),
    ("02 / ONBOARDING", "Complete your health profile", "Follow the six onboarding steps. Add your demographics and health details; chronic medications are optional.", APP / "assets/onboarding/slide-2.png", 5.0),
    ("03 / DASHBOARD", "Your overview at a glance", "Open Dashboard to see your latest diabetes and heart disease risk results, drug enquiry count, and recent vitals.", DASHBOARD, 5.0),
    ("04 / RISK ANALYSIS", "Update, choose, analyse", "Tap Update Health Metrics. Enter valid measurements, choose Diabetes or Heart Disease, and generate a risk report.", DASHBOARD, 5.0),
    ("05 / RESULTS", "Review trends and history", "Read the estimated risk and contributing factors. Use History and Health Trends to revisit results and recorded measurements.", APP / "assets/onboarding/slide-5.png", 5.0),
    ("06 / NUTRITION", "Log food and water", "Use Nutrition to set goals, record meals and water, and view seven-day trends. Blood Glucose also records glucose readings and insulin doses.", APP / "assets/onboarding/slide-2.png", 5.0),
    ("07 / FITNESS", "Track daily activity", "Use Fitness for steps, active time, calories, weight, and BMI trends. Generate a fitness routine from your latest risk context.", APP / "assets/onboarding/slide-3.png", 5.0),
    ("08 / MINDFULNESS", "Make room to reset", "Log mood, try a guided breathing exercise, or play a meditation session. Review your activity over the past seven days.", APP / "assets/onboarding/slide-4.png", 5.0),
    ("09 / ASSISTANT", "Ask and manage medications", "Ask reviewed medication questions or type: add medication metformin + every morning + 500 mg. View or remove saved medications in chat.", DASHBOARD, 5.0),
    ("KEEP EXPLORING", "Your health, clearer", "RiskSense AI offers decision support, not a diagnosis. Use the in-app Help icons for guidance on each screen.", LOGO, 4.0),
]


def background() -> Image.Image:
    image = Image.new("RGB", (W, H))
    pix = image.load()
    for y in range(H):
        for x in range(W):
            glow = max(0.0, 1 - math.hypot(x - 760, y - 80) / 700)
            pix[x, y] = (
                int(8 + 11 * glow + 4 * y / H),
                int(18 + 33 * glow + 5 * y / H),
                int(35 + 47 * glow + 8 * y / H),
            )
    return image


def scene_base(index: int, scene: tuple) -> tuple[Image.Image, Image.Image]:
    eyebrow, title, body, path, _ = scene
    frame = background()
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle((35, 26, 260, 58), radius=16, fill=(22, 54, 77), outline=(48, 111, 131), width=1)
    draw.text((52, 35), "RISKSENSE AI  /  APP GUIDE", font=font(12, True), fill=CYAN)
    draw.text((48, 120), eyebrow, font=font(16, True), fill=CYAN)
    title_font = font(43 if len(title) < 25 else 39, True)
    y = 159
    for line in lines(draw, title, title_font, 510):
        draw.text((46, y), line, font=title_font, fill=WHITE)
        y += 51
    y += 20
    body_font = font(22)
    for line in lines(draw, body, body_font, 490):
        draw.text((48, y), line, font=body_font, fill=MUTED)
        y += 34
    draw.line((48, 471, 910, 471), fill=(40, 75, 99), width=1)
    draw.text((48, 488), "ILLUSTRATIVE DEMO  •  NO PATIENT DATA", font=font(12, True), fill=(129, 158, 179))
    draw.text((876, 486), f"{index + 1:02d}/{len(SCENES):02d}", font=font(14, True), fill=CYAN)
    card_w, card_h = 289, 408
    card = fit_image(path, card_w, card_h)
    card_rgba = Image.new("RGBA", (card_w + 18, card_h + 18), (0, 0, 0, 0))
    card_rgba.paste(card, (9, 9))
    mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card_w - 1, card_h - 1), radius=22, fill=255)
    card_rgba.putalpha(Image.new("L", card_rgba.size, 0))
    card_rgba.paste(card, (9, 9), mask)
    ImageDraw.Draw(card_rgba).rounded_rectangle((8, 8, card_w + 9, card_h + 9), radius=23, outline=(116, 211, 228, 190), width=2)
    return frame, card_rgba


def render() -> None:
    dependency = Path.home() / "AppData/Local/Temp/risksense-video-deps"
    sys.path.insert(0, str(dependency))
    import imageio_ffmpeg

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(OUTPUT)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stdin is not None
    for index, scene in enumerate(SCENES):
        base, card = scene_base(index, scene)
        if index == 0:
            base.save(POSTER)
        duration = scene[4]
        frames = round(duration * FPS)
        for step in range(frames):
            progress = step / max(1, frames - 1)
            frame = base.copy().convert("RGBA")
            shadow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            sx, sy = 611, 69 + round(7 * (1 - progress))
            ImageDraw.Draw(shadow).rounded_rectangle((sx + 8, sy + 12, sx + 309, sy + 430), radius=26, fill=(0, 0, 0, 100))
            shadow = shadow.filter(ImageFilter.GaussianBlur(14))
            frame = Image.alpha_composite(frame, shadow)
            frame.alpha_composite(card, (sx, sy))
            overlay = ImageDraw.Draw(frame)
            overlay.rounded_rectangle((48, 518, 912, 522), radius=2, fill=(40, 70, 89))
            overlay.rounded_rectangle((48, 518, 48 + round(864 * (index + progress) / len(SCENES)), 522), radius=2, fill=CYAN)
            fade = min(1.0, progress * 5, (1 - progress) * 5)
            if fade < 1:
                veil = Image.new("RGBA", frame.size, (*NAVY, round((1 - fade) * 255)))
                frame = Image.alpha_composite(frame, veil)
            process.stdin.write(frame.convert("RGB").tobytes())
        print(f"Rendered scene {index + 1}/{len(SCENES)}: {scene[1]}", flush=True)
    process.stdin.close()
    error = process.stderr.read().decode("utf-8", "replace")
    if process.wait() != 0:
        raise RuntimeError(error[-2000:])
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    render()
