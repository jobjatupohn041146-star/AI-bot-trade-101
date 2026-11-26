"""Core state: gift tiers, reading queue, leaderboard, like-goal. No I/O, easy to test."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from . import safety


@dataclass(frozen=True)
class Tier:
    min_coins: int
    cards: int
    label: str          # shown in the price table
    bonus: bool = False  # "ไพ่ทอง" = extra deeper reading


# Mirrors the price table in the screenshot. Edit freely.
DEFAULT_TIERS = [
    Tier(10, 1, "10 เหรียญ · ไพ่ 1 ใบ"),
    Tier(15, 2, "15 เหรียญ · ไพ่ 2 ใบ"),
    Tier(20, 2, "20 เหรียญ · ไพ่ 2 ใบ + ไพ่ทอง", bonus=True),
    Tier(50, 5, "50 เหรียญ · ไพ่ 5 ใบ ปักหมุดค้างไว้", bonus=True),
]

QUESTION_TTL = 300  # seconds a viewer's last comment counts as their question


@dataclass
class Job:
    user: str
    cards: int
    question: str = ""
    bonus: bool = False
    free: bool = False
    sensitive: bool = False  # viewer asked about a topic we do not give verdicts on
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"user": self.user, "cards": self.cards, "free": self.free}


class Engine:
    def __init__(self, tiers: list[Tier] | None = None, goal_step: int = 300, max_queue: int = 30):
        self.tiers = sorted(tiers or DEFAULT_TIERS, key=lambda t: t.min_coins)
        self.goal_step = goal_step
        self.goal = goal_step
        self.likes = 0
        self.max_queue = max_queue
        self.queue: deque[Job] = deque()
        self.coins: dict[str, int] = {}
        self.rituals: dict[str, int] = {}
        self._questions: dict[str, tuple[str, float]] = {}

    # --- inputs -------------------------------------------------
    def on_comment(self, user: str, text: str, now: float | None = None) -> None:
        user = safety.clean_name(user)
        if not safety.clean(text):
            return
        self._questions[user] = (text, now if now is not None else time.time())
        if len(self._questions) > 500:  # bound memory on busy rooms
            oldest = min(self._questions, key=lambda u: self._questions[u][1])
            del self._questions[oldest]

    def tier_for(self, coins: int) -> Tier | None:
        best = None
        for t in self.tiers:
            if coins >= t.min_coins:
                best = t
        return best

    def on_gift(self, user: str, coins: int, now: float | None = None) -> Job | None:
        """Queue a reading if the gift value reaches a tier. Returns the Job or None."""
        if coins <= 0:
            return None
        user = safety.clean_name(user)
        self.coins[user] = self.coins.get(user, 0) + coins
        tier = self.tier_for(coins)
        if tier is None or len(self.queue) >= self.max_queue:
            return None
        now = now if now is not None else time.time()
        q, ts = self._questions.get(user, ("", 0.0))
        question, flag = safety.classify_question(q) if now - ts <= QUESTION_TTL else ("", "ok")
        job = Job(user=user, cards=tier.cards, question=question, bonus=tier.bonus,
                  sensitive=flag == "sensitive")
        self.queue.append(job)
        self.rituals[user] = self.rituals.get(user, 0) + 1
        return job

    def on_likes(self, total: int) -> Job | None:
        """Update like count. When the goal is crossed, queue one free daily card."""
        self.likes = max(self.likes, total)
        if self.likes >= self.goal:
            while self.goal <= self.likes:
                self.goal += self.goal_step
            job = Job(user="ทุกคนในห้อง", cards=1, free=True)
            self.queue.append(job)
            return job
        return None

    def next_job(self) -> Job | None:
        return self.queue.popleft() if self.queue else None

    # --- persistence (see store.py) ------------------------------
    def dump(self) -> dict:
        return {"likes": self.likes, "goal": self.goal, "coins": self.coins, "rituals": self.rituals,
                "queue": [{"user": j.user, "cards": j.cards, "question": j.question, "bonus": j.bonus,
                           "free": j.free, "sensitive": j.sensitive} for j in self.queue]}

    def restore(self, d: dict) -> None:
        self.likes = int(d.get("likes", 0))
        self.goal = int(d.get("goal", self.goal_step))
        self.coins = {str(k): int(v) for k, v in d.get("coins", {}).items()}
        self.rituals = {str(k): int(v) for k, v in d.get("rituals", {}).items()}
        self.queue = deque(Job(**j) for j in d.get("queue", []))

    # --- views --------------------------------------------------
    def leaderboard(self, n: int = 5) -> list[dict]:
        top = sorted(self.coins.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [{"user": u, "coins": c, "rituals": self.rituals.get(u, 0)} for u, c in top]

    def snapshot(self) -> dict:
        prev_goal = self.goal - self.goal_step
        return {
            "likes": self.likes,
            "goal": self.goal,
            "goal_progress": self.likes - prev_goal,
            "goal_step": self.goal_step,
            "leaderboard": self.leaderboard(),
            "queue": [j.to_dict() for j in list(self.queue)[:8]],
            "queue_len": len(self.queue),
            "tiers": [t.label for t in self.tiers],
        }
