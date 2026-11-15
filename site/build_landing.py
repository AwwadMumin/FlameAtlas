"""Build site/index.html, the landing page designed by Alaa and Hiba (ported from their Next.js branch to one
static file). Links go to workspace.html and story.html.   python site/build_landing.py"""
import base64
from pathlib import Path

SITE = Path(__file__).resolve().parent
logo = "data:image/png;base64," + base64.b64encode((SITE / "flame-atlas-logo.png").read_bytes()).decode()
html = (SITE / "landing_template.html").read_text(encoding="utf-8")
html = (html.replace("__GLOBALS__", (SITE / "landing_globals.css").read_text(encoding="utf-8"))
            .replace("__LANDING__", (SITE / "landing.css").read_text(encoding="utf-8"))
            .replace("__LOGO__", logo))
(SITE / "index.html").write_text(html, encoding="utf-8")
print("site/index.html (landing):", len(html) // 1024, "KB")
