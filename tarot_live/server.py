"""aiohttp app: serves the overlay, pushes state over /ws, runs the reading worker."""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

from aiohttp import WSMsgType, web

from . import reader, safety, tts
from .cards import draw
from .engine import Engine
from .store import Store

OVERLAY = Path(__file__).parent / "overlay"


class App:
    def __init__(self, source, engine: Engine | None = None, use_tts: bool = False,
                 display_secs: float = 12.0, rng: random.Random | None = None,
                 store: Store | None = None):
        self.source = source
        self.engine = engine or Engine()
        self.use_tts = use_tts
        self.display_secs = display_secs
        self.rng = rng
        self.store = store
        if store:
            store.load(self.engine)
        self.clients: set[web.WebSocketResponse] = set()
        self.wake = asyncio.Event()

    async def broadcast(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(data)
            except Exception:
                self.clients.discard(ws)

    async def push_state(self) -> None:
        await self.broadcast({"event": "state", **self.engine.snapshot()})

    async def handle_event(self, ev: dict) -> None:
        e = self.engine
        t = ev.get("type")
        if t == "comment":
            e.on_comment(ev["user"], ev["text"])
            shown = safety.chat_visible(ev["text"])
            if shown:
                await self.broadcast({"event": "chat", "user": safety.mask_profanity(safety.clean_name(ev["user"])),
                                      "text": shown})
        elif t == "likes":
            e.on_likes(int(ev["total"]))
        elif t == "gift":
            job = e.on_gift(ev["user"], int(ev["coins"]))
            await self.broadcast({"event": "gift", "user": ev["user"], "coins": ev["coins"],
                                  "queued": job is not None})
        if self.store:
            self.store.save(e)
        self.wake.set()
        await self.push_state()

    async def ingest(self) -> None:
        async for ev in self.source:
            await self.handle_event(ev)

    async def worker(self) -> None:
        while True:
            job = self.engine.next_job()
            if job is None:
                self.wake.clear()
                await self.wake.wait()
                continue
            if self.store:
                self.store.save(self.engine)
            drawn = draw(job.cards, self.rng)
            await self.push_state()
            await self.broadcast({"event": "reading_start", "user": safety.mask_profanity(job.user), "free": job.free,
                                  "question": job.question, "cards": [d.to_dict() for d in drawn]})
            text = await reader.read(job, drawn)
            audio = await tts.speak(text) if self.use_tts else None
            await self.broadcast({"event": "reading", "text": text, "audio": audio})
            await asyncio.sleep(self.display_secs + len(text) / 12)  # ~12 chars/sec spoken
            await self.broadcast({"event": "reading_end"})

    async def ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.clients.add(ws)
        await ws.send_str(json.dumps({"event": "state", **self.engine.snapshot()}, ensure_ascii=False))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clients.discard(ws)
        return ws

    async def start_tasks(self, app: web.Application) -> None:
        app["tasks"] = [asyncio.create_task(self.ingest()), asyncio.create_task(self.worker())]

    async def stop_tasks(self, app: web.Application) -> None:
        for t in app["tasks"]:
            t.cancel()

    def build(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/ws", self.ws)
        app.router.add_get("/", lambda r: web.FileResponse(OVERLAY / "index.html"))
        (OVERLAY / "audio").mkdir(exist_ok=True)
        app.router.add_static("/audio", OVERLAY / "audio")
        (OVERLAY / "avatar").mkdir(exist_ok=True)
        app.router.add_static("/avatar", OVERLAY / "avatar")  # optional loop from gen_avatar
        (OVERLAY / "cards").mkdir(exist_ok=True)
        app.router.add_static("/cards", OVERLAY / "cards")  # optional art from gen_cards
        app.on_startup.append(self.start_tasks)
        app.on_cleanup.append(self.stop_tasks)
        return app
