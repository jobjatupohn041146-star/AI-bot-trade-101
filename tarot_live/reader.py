"""Turns drawn cards into a Thai reading. Uses Claude if ANTHROPIC_API_KEY is set, else a template."""
from __future__ import annotations

import os

from .cards import Drawn
from .engine import Job

SYSTEM = """คุณคือ "แม่หมอ" หมอดูไพ่ทาโร่ที่ไลฟ์สดบน TikTok พูดภาษาไทยอบอุ่น ลึกลับเล็กน้อย เป็นกันเอง
กติกา:
- ตอบ 3-5 ประโยค ไม่เกิน 450 ตัวอักษร เพราะจะถูกอ่านออกเสียง ห้ามใช้ markdown หรืออีโมจิ
- เรียกชื่อผู้ชมหนึ่งครั้ง อธิบายความหมายไพ่แต่ละใบแล้วเชื่อมกับคำถาม (ถ้าไม่มีคำถามให้ดูภาพรวมชีวิตช่วงนี้)
- เพื่อความบันเทิง ห้ามฟันธงเรื่องสุขภาพ การเสียชีวิต กฎหมาย การลงทุน หรือการตั้งครรภ์
- ปิดท้ายด้วยคำแนะนำเชิงบวกที่ลงมือทำได้จริงหนึ่งข้อ"""


def _template(job: Job, drawn: list[Drawn]) -> str:
    who = "ทุกคน" if job.free else f"คุณ{job.user}"
    parts = [f"{who} ไพ่ที่เปิดได้คือ"]
    for i, d in enumerate(drawn, 1):
        parts.append(f"ใบที่ {i} {d.label} สื่อถึง{d.meaning}")
    text = " ".join(parts) + "."
    if job.question:
        text += f" ถ้ามองในเรื่อง \"{job.question}\" ไพ่บอกให้ใจเย็นและเชื่อสัญชาตญาณของตัวเอง"
    text += " ค่อยๆ ก้าวไปทีละขั้น แล้วพลังดีๆ จะตามมาเอง"
    return text


async def read(job: Job, drawn: list[Drawn], model: str | None = None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _template(job, drawn)
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=key)
        cards = "\n".join(f"{i}. {d.label} — {d.meaning}" for i, d in enumerate(drawn, 1))
        user_msg = (
            f"ผู้ชม: {job.user}\nคำถาม: {job.question or '(ไม่มี ขอดูภาพรวม)'}\n"
            f"{'ไพ่ทอง: ขอคำทำนายลึกขึ้นเล็กน้อย' if job.bonus else ''}\nไพ่ที่เปิดได้:\n{cards}"
        )
        resp = await client.messages.create(
            model=model or os.environ.get("TAROT_MODEL", "claude-haiku-5-5"),
            max_tokens=600,
            system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            timeout=20,
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text or _template(job, drawn)
    except Exception as e:  # never leave dead air on stream
        print(f"[reader] LLM failed, using template: {e}")
        return _template(job, drawn)
