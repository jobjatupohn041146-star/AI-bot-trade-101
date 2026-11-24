"""Build the static results website for GitHub Pages: docs/index.html

    python scripts/export_dashboard.py   # journals -> data/dashboard/*.json
    python scripts/build_site.py         # json -> docs/index.html
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "dashboard"
REPO = "https://github.com/jobjatupohn041146-star/AI-bot-trade-101"
BRANCH = "claude/trusting-cannon-rdn0br"

data = {p.stem: json.loads(p.read_text())["rows"] for p in sorted(SRC.glob("*.json"))}
html = (ROOT / "scripts" / "site_template.html").read_text(encoding="utf-8")
html = (html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
            .replace("__UPDATED__", date.today().isoformat())
            .replace("__REPO__", REPO).replace("__BRANCH__", BRANCH))
out = ROOT / "docs" / "index.html"
out.write_text(html, encoding="utf-8")
(ROOT / "docs" / ".nojekyll").touch()
print(f"wrote {out} ({len(html):,} bytes)")
