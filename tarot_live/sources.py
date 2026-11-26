"""Event sources. Each is an async generator yielding dicts:
  {"type": "comment", "user", "text"} | {"type": "gift", "user", "coins"} | {"type": "likes", "total"}
"""
from __future__ import annotations

import asyncio
import random

NAMES = ["K.", "May", "ฟ้าใส98", "BEA", "Sweet K", "น้องจ๊อบ", "มะมี่ไอซ์", "Wora"]
QUESTIONS = ["เรื่องงานช่วงนี้เป็นยังไงคะ", "ความรักจะดีขึ้นไหม", "ควรเปลี่ยนงานไหมคะ", "เดือนนี้การเงินเป็นยังไง"]


async def mock_source(speed: float = 1.0):
    """Fake viewers for demoing the overlay with no TikTok connection."""
    likes = 0
    while True:
        await asyncio.sleep(random.uniform(1.0, 3.0) / speed)
        user = random.choice(NAMES)
        r = random.random()
        if r < 0.45:
            likes += random.randint(5, 40)
            yield {"type": "likes", "total": likes}
        elif r < 0.7:
            yield {"type": "comment", "user": user, "text": random.choice(QUESTIONS)}
        else:
            yield {"type": "comment", "user": user, "text": random.choice(QUESTIONS)}
            await asyncio.sleep(0.3)
            yield {"type": "gift", "user": user, "coins": random.choice([10, 15, 20, 50])}


async def tiktok_source(username: str):
    """Real TikTok LIVE via the unofficial `TikTokLive` package (pip install TikTokLive).

    NOTE: written against TikTokLive 6.x and not exercised against a live room here;
    attribute names may differ between versions. Unofficial API - can break anytime.
    """
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import CommentEvent, GiftEvent, LikeEvent

    q: asyncio.Queue = asyncio.Queue()
    client = TikTokLiveClient(unique_id=username)

    @client.on(CommentEvent)
    async def _comment(e: CommentEvent):
        q.put_nowait({"type": "comment", "user": e.user.nickname, "text": e.comment})

    @client.on(LikeEvent)
    async def _like(e: LikeEvent):
        q.put_nowait({"type": "likes", "total": getattr(e, "total", 0) or 0})

    @client.on(GiftEvent)
    async def _gift(e: GiftEvent):
        # Streakable gifts (roses etc.) fire repeatedly; only count when the streak ends.
        if e.gift.streakable and e.streaking:
            return
        count = e.repeat_count if e.gift.streakable else 1
        q.put_nowait({"type": "gift", "user": e.user.nickname, "coins": e.gift.diamond_count * count})

    task = asyncio.create_task(client.start())
    try:
        while True:
            yield await q.get()
            if task.done() and q.empty():
                task.result()
                return
    finally:
        task.cancel()
