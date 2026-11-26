"""Filters for untrusted viewer text (comments, nicknames) before display or LLM use."""
from __future__ import annotations

import re
import unicodedata

def _rx(pattern: str, flags: int = 0) -> re.Pattern:
    # Thai "ำ" decomposes under NFKC, so patterns and the text they match are both normalized.
    return re.compile(unicodedata.normalize("NFKC", pattern), flags)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


URL = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(com|net|org|co|th|me|io)\b\S*)", re.I)
CONTROL = re.compile(r"[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩]")

# Prompt-injection attempts (Thai + English)
INJECTION = _rx(
    r"ignore (all |the )?(previous|above|prior)|system prompt|you are now|act as|jailbreak|developer mode"
    r"|ลืมคำสั่ง|คำสั่งก่อนหน้า|ข้ามกฎ|เปิดเผย.{0,6}(prompt|พรอมต์|คำสั่ง)|แกล้งเป็น|ทำตัวเป็น.{0,10}(ai|เอไอ|บอท)",
    re.I,
)
# Mild profanity list (extend as needed); masked in chat, drops the question
PROFANITY = _rx(r"(เหี้ย|สัส|ควย|หี|เย็ด|แม่ง|ไอ้สัตว์|fuck|shit|bitch)", re.I)
# Topics the reader must not give verdicts on
SENSITIVE = _rx(
    r"(ตาย|เสียชีวิต|ฆ่าตัวตาย|อยากตาย|มะเร็ง|โรค|ป่วย|ผ่าตัด|ท้อง|ตั้งครรภ์|แท้ง|ฟ้อง|คดี|ติดคุก"
    r"|หวย|เลขเด็ด|ถูกรางวัล|หุ้น|คริปโต|เทรด|ลงทุน|กู้เงิน)",
    re.I,
)


def clean(text: str, limit: int = 120) -> str:
    """Strip control chars, URLs, collapse whitespace, cap length."""
    text = CONTROL.sub("", text or "")
    text = URL.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def clean_name(name: str) -> str:
    return clean(name, 30) or "ผู้ชม"


def mask_profanity(text: str) -> str:
    if not PROFANITY.search(_norm(text)):
        return text  # leave clean text byte-identical
    return PROFANITY.sub(lambda m: "*" * len(m.group(0)), _norm(text))


def classify_question(text: str) -> tuple[str, str]:
    """Return (usable_question, flag). flag: 'ok' | 'sensitive' | 'blocked'.

    'blocked' (injection/profanity) and 'sensitive' both return an empty question so the
    LLM never sees the raw text; the reader acknowledges 'sensitive' gently.
    """
    t = clean(text, 120)
    if not t:
        return "", "ok"
    n = _norm(t)
    if INJECTION.search(n) or PROFANITY.search(n):
        return "", "blocked"
    if SENSITIVE.search(n):
        return "", "sensitive"
    return t, "ok"


def chat_visible(text: str) -> str | None:
    """Text safe to show on the overlay chat, or None to hide the message."""
    t = clean(text, 80)
    if not t or INJECTION.search(_norm(t)):
        return None
    return mask_profanity(t)
