"""'Go to school first': the bot refuses to trade until it has studied the
knowledge base (ICT, SMC, Elliott Wave, Price Action, psychology, money
management) and produced a playbook that covers every required topic.
If the knowledge files change, the bot must study again."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, KNOWLEDGE_DIR

PLAYBOOK = DATA_DIR / "playbook.md"
LEARNED = DATA_DIR / "learned.json"

REQUIRED_SECTIONS = [
    "## Price Action", "## SMC", "## ICT", "## Elliott Wave",
    "## Psychology", "## Money Management", "## Entry Checklist",
]


def knowledge_files(kdir: Path = KNOWLEDGE_DIR) -> list[Path]:
    return sorted(kdir.glob("*.md"))


def knowledge_text(kdir: Path = KNOWLEDGE_DIR) -> str:
    return "\n\n".join(f"<!-- {p.name} -->\n{p.read_text(encoding='utf-8')}" for p in knowledge_files(kdir))


def knowledge_hash(kdir: Path = KNOWLEDGE_DIR) -> str:
    h = hashlib.sha256()
    for p in knowledge_files(kdir):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def coverage(playbook: str) -> dict[str, bool]:
    return {s: s.lower() in playbook.lower() for s in REQUIRED_SECTIONS}


def _key_rules(text: str) -> str:
    m = re.search(r"## กฎสำคัญ \(Key Rules\)\n(.*?)(?=\n## |\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def offline_playbook(kdir: Path = KNOWLEDGE_DIR) -> str:
    """Compile the Key Rules of every lesson without calling the API."""
    mapping = {
        "01": "## Price Action", "02": "## SMC", "03": "## ICT", "04": "## Elliott Wave",
        "05": "## Psychology", "06": "## Money Management", "07": "## Entry Checklist",
    }
    parts = ["# Trading Playbook (compiled offline from knowledge/)\n"]
    for p in knowledge_files(kdir):
        head = mapping.get(p.name[:2], f"## {p.stem}")
        parts.append(f"{head}\n{_key_rules(p.read_text(encoding='utf-8'))}\n")
    return "\n".join(parts)


STUDY_PROMPT = """You are studying to become a disciplined discretionary trader.
Read the whole curriculum below (Price Action, Smart Money Concept, ICT, Elliott
Wave, trading psychology, money management and the 3-pillar entry logic).

Write your own condensed PLAYBOOK in Thai (technical terms may stay in English)
that you will follow when you trade. Use exactly these second-level headings:
## Price Action
## SMC
## ICT
## Elliott Wave
## Psychology
## Money Management
## Entry Checklist

Under each heading: the concrete, checkable rules you will apply, how the
school combines with the others, and the common mistakes to avoid. The Entry
Checklist must run in order: psychology -> technical confluence -> money
management. Do not invent fixed take-profit levels: TP/SL will be fitted later
from the bot's own trade statistics; only describe structural invalidation.

Return only the playbook markdown.

<curriculum>
{curriculum}
</curriculum>"""


def study(use_claude: bool = False, model: str = "claude-opus-5-5", kdir: Path = KNOWLEDGE_DIR,
          out_dir: Path = DATA_DIR) -> dict:
    if use_claude:
        import anthropic

        client = anthropic.Anthropic()
        with client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high"},
            messages=[{"role": "user", "content": STUDY_PROMPT.format(curriculum=knowledge_text(kdir))}],
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise RuntimeError("Claude declined the study request")
        playbook = "".join(b.text for b in msg.content if b.type == "text")
        method = f"claude:{msg.model}"
    else:
        playbook = offline_playbook(kdir)
        method = "offline"
    cov = coverage(playbook)
    if not all(cov.values()):
        missing = [k for k, v in cov.items() if not v]
        raise RuntimeError(f"Playbook incomplete, missing: {missing}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / PLAYBOOK.name).write_text(playbook, encoding="utf-8")
    record = {"knowledge_hash": knowledge_hash(kdir), "method": method,
              "studied_at": datetime.now(timezone.utc).isoformat(), "coverage": cov}
    (out_dir / LEARNED.name).write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record


def is_learned(kdir: Path = KNOWLEDGE_DIR, out_dir: Path = DATA_DIR) -> tuple[bool, str]:
    lf, pb = out_dir / LEARNED.name, out_dir / PLAYBOOK.name
    if not lf.exists() or not pb.exists():
        return False, "not studied yet — run: python -m tradebot study"
    rec = json.loads(lf.read_text())
    if rec.get("knowledge_hash") != knowledge_hash(kdir):
        return False, "knowledge changed since last study — study again"
    if not all(coverage(pb.read_text(encoding="utf-8")).values()):
        return False, "playbook does not cover all topics"
    return True, f"learned ({rec['method']}, {rec['studied_at']})"


def load_playbook(out_dir: Path = DATA_DIR) -> str:
    p = out_dir / PLAYBOOK.name
    return p.read_text(encoding="utf-8") if p.exists() else ""
