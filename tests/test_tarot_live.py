import asyncio
import random

from tarot_live import reader
from tarot_live.cards import DECK, draw
from tarot_live.engine import Engine
from tarot_live.server import App


def test_deck_is_78_unique():
    assert len(DECK) == 78
    assert len({c.name_en for c in DECK}) == 78


def test_draw_distinct_and_clamped():
    d = draw(5, random.Random(1))
    assert len({x.card.id for x in d}) == 5
    assert len(draw(0)) == 1


def test_gift_tiers():
    e = Engine()
    assert e.on_gift("a", 5) is None            # below lowest tier
    assert e.on_gift("a", 10).cards == 1
    assert e.on_gift("a", 15).cards == 2
    j = e.on_gift("a", 20); assert j.cards == 2 and j.bonus
    assert e.on_gift("a", 99).cards == 5
    assert e.coins["a"] == 5 + 10 + 15 + 20 + 99


def test_question_attached_and_expires():
    e = Engine()
    e.on_comment("a", "รักเป็นยังไง", now=1000)
    assert e.on_gift("a", 10, now=1100).question == "รักเป็นยังไง"
    e.on_comment("b", "เก่า", now=0)
    assert e.on_gift("b", 10, now=1000).question == ""


def test_queue_cap():
    e = Engine(max_queue=2)
    assert e.on_gift("a", 10) and e.on_gift("b", 10)
    assert e.on_gift("c", 10) is None
    assert e.coins["c"] == 10  # still credited to leaderboard


def test_like_goal_fires_once_per_step():
    e = Engine(goal_step=300)
    assert e.on_likes(299) is None
    j = e.on_likes(300)
    assert j.free and e.goal == 600
    assert e.on_likes(301) is None
    assert e.on_likes(1300) is not None and e.goal == 1500  # skipped goals don't flood the queue
    assert e.snapshot()["goal_progress"] == 1300 - 1200


def test_leaderboard_order():
    e = Engine()
    e.on_gift("a", 10); e.on_gift("b", 50)
    assert [r["user"] for r in e.leaderboard()] == ["b", "a"]


def test_reader_template_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    e = Engine(); e.on_comment("มะมี่", "เรื่องงาน")
    job = e.on_gift("มะมี่", 15)
    text = asyncio.run(reader.read(job, draw(2, random.Random(2))))
    assert "มะมี่" in text and "เรื่องงาน" in text


def test_pipeline_end_to_end(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def src():
        yield {"type": "comment", "user": "k", "text": "รัก"}
        yield {"type": "gift", "user": "k", "coins": 10}

    async def run():
        app = App(src(), display_secs=0, rng=random.Random(3))
        sent = []

        async def cap(msg): sent.append(msg["event"])
        app.broadcast = cap
        await app.ingest()
        w = asyncio.create_task(app.worker())
        await asyncio.sleep(0.2); w.cancel()
        return sent

    ev = asyncio.run(run())
    assert "reading_start" in ev and "reading" in ev
