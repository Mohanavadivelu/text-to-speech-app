"""
Takes screenshots of each UI design HTML fragment using Chrome headless,
then auto-crops each image to just the rendered element (removes dark background padding).

Run from any directory: python pyside6_app/design/take_screenshots.py
"""
import subprocess
import tempfile
import os
import pathlib
from PIL import Image, ImageChops

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DESIGN_DIR = pathlib.Path(__file__).parent
SCREENSHOTS_DIR = DESIGN_DIR / "screenshots"
CSS_FILE = DESIGN_DIR / "styles.css"

CSS = CSS_FILE.read_text(encoding="utf-8")

# Body background color used in all pages — pixels matching this are cropped away.
BG_COLOR = (7, 7, 13)
CROP_PADDING = 20  # px of dark background to keep around the element


def make_html(fragment: str, body_extra: str = "") -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{CSS}
body {{
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background: #07070d;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 32px 20px;
    min-height: 100vh;
    {body_extra}
}}
</style>
</head>
<body>
{fragment}
</body>
</html>"""


def autocrop(path: str):
    """Crop the screenshot to the bounding box of non-background pixels."""
    img = Image.open(path).convert("RGB")
    bg = Image.new("RGB", img.size, BG_COLOR)
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if bbox is None:
        return  # image is entirely background — leave as-is
    left  = max(0, bbox[0] - CROP_PADDING)
    top   = max(0, bbox[1] - CROP_PADDING)
    right = min(img.width,  bbox[2] + CROP_PADDING)
    bottom= min(img.height, bbox[3] + CROP_PADDING)
    img.crop((left, top, right, bottom)).save(path)


COMPONENTS = {
    "titlebar": {
        "file": "titlebar.html",
        "window_size": "1060,400",
        "wrap": lambda html: f'<div class="app-window" style="width:980px;">{html}</div>',
    },
    "text_panel": {
        "file": "text_panel.html",
        "window_size": "1060,800",
        "wrap": lambda html: (
            '<div class="app-window" style="width:980px;">'
            '<div class="body" style="grid-template-columns:1fr; padding:16px;">'
            f'<div class="card text-panel">{html}</div>'
            '</div></div>'
        ),
    },
    "settings_panel": {
        "file": "settings_panel.html",
        "window_size": "1060,1000",
        "wrap": lambda html: (
            '<div class="app-window" style="width:980px;">'
            '<div class="body" style="grid-template-columns:300px; padding:16px; justify-content:center;">'
            f'<div class="card settings-panel">{html}</div>'
            '</div></div>'
        ),
    },
    "audio_player": {
        "file": "audio_player.html",
        "window_size": "1060,600",
        "wrap": lambda html: f'<div class="app-window" style="width:980px;">{html}</div>',
    },
    "statusbar": {
        "file": "statusbar.html",
        "window_size": "1060,400",
        "wrap": lambda html: f'<div class="app-window" style="width:980px;">{html}</div>',
    },
    "state_previews": {
        "file": "state_previews.html",
        "window_size": "1060,3000",
        # body already set to flex-direction:column so both child divs stack vertically
        "wrap": lambda html: html,
    },
}


def screenshot(name: str, cfg: dict):
    fragment = (DESIGN_DIR / cfg["file"]).read_text(encoding="utf-8")
    wrapped = cfg["wrap"](fragment)
    html = make_html(wrapped)

    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(html)
        tmp_path = f.name

    out_path = str(SCREENSHOTS_DIR / f"{name}.png")

    try:
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--window-size={cfg['window_size']}",
                f"--screenshot={out_path}",
                f"file:///{tmp_path.replace(os.sep, '/')}",
            ],
            check=True,
            capture_output=True,
        )
        autocrop(out_path)
        print(f"  OK  {name}.png")
    except subprocess.CalledProcessError as e:
        print(f"  ERR {name}: {e.stderr.decode()[:200]}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    print("Taking screenshots...")
    for name, cfg in COMPONENTS.items():
        screenshot(name, cfg)
    print("Done. Screenshots saved to:", SCREENSHOTS_DIR)
