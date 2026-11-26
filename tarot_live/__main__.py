"""python -m tarot_live [--mock | --tiktok USERNAME] [--tts] [--port 8765]"""
import argparse

from aiohttp import web

from .server import App
from .store import Store
from .sources import mock_source, tiktok_source


def main() -> None:
    p = argparse.ArgumentParser(prog="tarot_live")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true", help="fake viewers (default)")
    g.add_argument("--tiktok", metavar="USERNAME", help="connect to a real TikTok LIVE (without @)")
    p.add_argument("--tts", action="store_true", help="Thai speech with edge-tts")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--db", default="data/tarot_live.db", help="state file ('' to disable persistence)")
    p.add_argument("--speed", type=float, default=1.0, help="mock event speed")
    a = p.parse_args()
    source = tiktok_source(a.tiktok) if a.tiktok else mock_source(a.speed)
    print(f"Overlay: http://localhost:{a.port}/  (add as OBS Browser Source, 1080x1920)")
    web.run_app(App(source, use_tts=a.tts, store=Store(a.db) if a.db else None).build(), host="127.0.0.1", port=a.port, print=None)


main()
