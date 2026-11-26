"""Generate the 78-card deck (+ card back) with an image API.

    export OPENAI_API_KEY=...            # or REPLICATE_API_TOKEN=...
    python -m tarot_live.gen_cards --dry-run              # write prompts only, no API calls
    python -m tarot_live.gen_cards --only 0 1 2           # try 3 cards first
    python -m tarot_live.gen_cards                        # all 79 images, skips ones already made

    python -m tarot_live.gen_cards --from-sheet deck.png  # cut the 22 Major Arcana out of a deck sheet picture
    python -m tarot_live.gen_cards --minors --style-ref deck.png   # draw the other 56 in that picture's style

Output: tarot_live/overlay/cards/NN.png (NN = card id, see cards.py) and back.png.
Re-running resumes: existing files are never regenerated unless --force.
NOTE: the HTTP calls are not exercised in CI (no network/keys); prompt building,
resume and retry logic are unit-tested with a fake provider.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .cards import DECK, MAJOR, SUITS

OUT = Path(__file__).parent / "overlay" / "cards"

STYLE = (
    "Dark romantic fantasy tarot card illustration, vertical portrait, black and deep violet palette with "
    "gold filigree frame, glowing crescent moons, purple roses, candlelight and crystals, glamorous "
    "painterly anime-realism, rich detail, soft magical glow, consistent art style across a full deck. "
    "No text, no letters, no numbers, no watermark."
)
BACK_PROMPT = (
    "Tarot card back design, symmetrical, black and violet background, ornate gold filigree frame, large "
    "glowing crescent moon at the center with a radiant sunburst, small crescent moon above, sparkling "
    "stars. No text, no letters, no watermark."
)

# Scene per Major Arcana (same order as cards.MAJOR)
MAJOR_SCENES = [
    "a young traveler at a cliff edge with a small white dog and a bundle on a staff, bright sky",
    "a magician with one hand raised, a wand, and a table of cup, sword, wand, pentacle, infinity symbol overhead",
    "a veiled priestess seated between a black and a white pillar, crescent moon at her feet, scroll in lap",
    "a regal empress on a cushioned throne in a lush wheat field with a crown of stars",
    "a stern emperor on a stone throne carved with ram heads, red robes, mountains behind",
    "a hierophant in ceremonial robes on a throne blessing two kneeling acolytes, crossed keys",
    "two figures beneath a radiant angel in a garden with a tree of flames and a tree of fruit",
    "a warrior in a chariot drawn by a black and a white sphinx under a canopy of stars",
    "a calm woman gently closing the jaws of a lion, infinity symbol above her head",
    "a hooded old hermit on a snowy peak holding a lantern with a six-pointed star",
    "a great wheel with zodiac symbols, a sphinx on top, serpent and jackal, clouds with four winged creatures",
    "a seated judge on a throne holding an upright sword and scales, red robe, pillars",
    "a man hanging upside down by one foot from a living tree, serene face, golden halo",
    "a skeleton knight in black armor on a white horse, rising sun between two towers, symbolic rebirth",
    "an angel with rainbow wings pouring water between two cups, one foot on land and one in water",
    "a horned figure on a pedestal with two loosely chained figures, inverted torch, dark cavern",
    "a tall tower struck by lightning, crown blown off, falling figures, flames from windows",
    "a kneeling woman pouring water from two jugs under a great eight-pointed star, night sky",
    "a full moon between two towers, a wolf and a dog howling, a crayfish crawling from a pool",
    "a joyful child on a white horse under a huge radiant sun, sunflowers, red banner",
    "an angel blowing a trumpet over rising figures from coffins, snow mountains",
    "a dancing figure within a laurel wreath holding two wands, four creatures in the corners",
]

SUIT_SYMBOL = {"Wands": "flowering wooden wands", "Cups": "golden cups", "Swords": "silver swords",
               "Pentacles": "golden pentacle coins"}
SUIT_SCENE = {"Wands": "fiery desert and distant castle", "Cups": "rivers, lotus and moonlit water",
              "Swords": "stormy clouds and mountains", "Pentacles": "lush garden with vines and a path"}
PIPS = {"Ace": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7, "Eight": 8,
        "Nine": 9, "Ten": 10}
COURT = {
    "Page": "a young page standing and holding a single {sym}, gazing at it with curiosity",
    "Knight": "an armored knight on a horse holding a {sym}, charging across the landscape",
    "Queen": "a crowned queen seated on a throne holding a {sym}, calm and wise",
    "King": "a crowned king seated on a grand throne holding a {sym}, commanding presence",
}


def prompt_for(card_id: int) -> str:
    card = DECK[card_id]
    if card_id < len(MAJOR):
        scene = f"{card.name_en}: {MAJOR_SCENES[card_id]}"
    else:
        rank, _, suit = card.name_en.partition(" of ")
        sym = SUIT_SYMBOL[suit]
        if rank == "Ace":
            body = f"a single hand emerging from a cloud holding one of the {sym}"
        elif rank in PIPS:
            body = f"{PIPS[rank]} of the {sym} arranged in a composition expressing '{rank}' energy"
        else:
            body = COURT[rank].format(sym=sym.rstrip("s"))
        scene = f"{card.name_en}: {body}, {SUIT_SCENE[suit]} in the background"
    return f"{scene}. {STYLE}"


def all_jobs() -> list[tuple[str, str]]:
    return [(f"{c.id:02d}", prompt_for(c.id)) for c in DECK] + [("back", BACK_PROMPT)]


# --- providers: (prompt, seed) -> PNG bytes ---------------------------------
def _post(url: str, headers: dict, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def openai_provider(prompt: str, seed: int) -> bytes:
    key = os.environ["OPENAI_API_KEY"]
    d = _post("https://api.openai.com/v1/images/generations", {"Authorization": f"Bearer {key}"},
              {"model": os.environ.get("TAROT_IMAGE_MODEL", "gpt-image-1"), "prompt": prompt,
               "size": "1024x1536", "quality": os.environ.get("TAROT_IMAGE_QUALITY", "medium"), "n": 1})
    return base64.b64decode(d["data"][0]["b64_json"])


def replicate_provider(prompt: str, seed: int) -> bytes:
    token = os.environ["REPLICATE_API_TOKEN"]
    model = os.environ.get("TAROT_REPLICATE_MODEL", "black-forest-labs/flux-schnell")
    d = _post(f"https://api.replicate.com/v1/models/{model}/predictions",
              {"Authorization": f"Bearer {token}", "Prefer": "wait"},
              {"input": {"prompt": prompt, "aspect_ratio": "2:3", "output_format": "png", "seed": seed}})
    if d.get("status") != "succeeded":
        raise RuntimeError(f"replicate status={d.get('status')} error={d.get('error')}")
    out = d["output"]
    url = out[0] if isinstance(out, list) else out
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


# --- cutting cards out of a deck "sheet" picture -----------------------------
# Grid of the "Queen of Tarot" sheet (15 columns x 4 rows), measured on a 1536x1024 picture.
SHEET_REF = (1536, 1024)
SHEET_GRID = dict(x0=30, pitch_x=99.07, w=93, y0=424, pitch_y=131, h=125, cols=15)
CARD_OUT = (384, 576)  # 2:3, matches the overlay's card shape


def extract_major_from_sheet(sheet: Path, out: Path, force: bool = False) -> list[str]:
    """Write 00.png..21.png (the Major Arcana) from a deck sheet. Slots 0-21 of the grid, row by row.

    Only the Major Arcana are cut: on the sheet this was built for, the minor-arcana labels are
    duplicated/missing, so cutting them would show the wrong card.
    """
    from PIL import Image, ImageFilter

    src = Image.open(sheet).convert("RGB")
    k = src.width / SHEET_REF[0]
    g = SHEET_GRID
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for i in range(len(MAJOR)):
        r, c = divmod(i, g["cols"])
        x, y = (g["x0"] + c * g["pitch_x"]) * k, (g["y0"] + r * g["pitch_y"]) * k
        path = out / f"{i:02d}.png"
        if path.exists() and not force:
            continue
        tile = src.crop((round(x), round(y), round(x + g["w"] * k), round(y + g["h"] * k)))
        tile = tile.resize(CARD_OUT, Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
        tile.save(path)
        done.append(f"{i:02d}")
    return done


def _multipart(fields: dict[str, str], files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "----tarotlive" + os.urandom(8).hex()
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for name, filename, data in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                     f"Content-Type: image/png\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


STYLE_REF_PREFIX = (
    "The attached picture is ONLY a style reference (art style, colour palette, ornate gold filigree card frame, "
    "glamorous painterly figures). Do not copy its layout or reuse its cards. Draw ONE new tarot card: "
)


def openai_style_provider(refs: list[Path]) -> Callable[[str, int], bytes]:
    """OpenAI image *edit* with reference pictures, so all 56 new cards share the deck's look."""
    from PIL import Image
    import io

    blobs = []
    for r in refs:
        im = Image.open(r).convert("RGB")
        im.thumbnail((1536, 1536))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        blobs.append(("image[]", r.stem + ".png", buf.getvalue()))

    def provider(prompt: str, seed: int) -> bytes:
        key = os.environ["OPENAI_API_KEY"]
        body, ctype = _multipart(
            {"model": os.environ.get("TAROT_IMAGE_MODEL", "gpt-image-1"), "prompt": STYLE_REF_PREFIX + prompt,
             "size": "1024x1536", "quality": os.environ.get("TAROT_IMAGE_QUALITY", "medium"), "n": "1"}, blobs)
        req = urllib.request.Request("https://api.openai.com/v1/images/edits", body,
                                     {"Authorization": f"Bearer {key}", "Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=240) as r:
            return base64.b64decode(json.loads(r.read())["data"][0]["b64_json"])

    return provider


PROVIDERS: dict[str, Callable[[str, int], bytes]] = {"openai": openai_provider, "replicate": replicate_provider}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def generate(jobs: list[tuple[str, str]], provider: Callable[[str, int], bytes], out: Path,
             force: bool = False, workers: int = 3, retries: int = 3, sleep: Callable[[float], None] = time.sleep,
             log: Callable[[str], None] = print) -> dict:
    """Run jobs concurrently. Returns {"done": [...], "skipped": [...], "failed": {name: error}}."""
    out.mkdir(parents=True, exist_ok=True)
    res: dict = {"done": [], "skipped": [], "failed": {}}

    def one(job: tuple[str, str]) -> None:
        name, prompt = job
        path = out / f"{name}.png"
        if path.exists() and not force:
            res["skipped"].append(name)
            return
        seed = int(name) if name.isdigit() else 999
        for attempt in range(1, retries + 1):
            try:
                data = provider(prompt, seed)
                if not data.startswith(PNG_MAGIC):
                    raise ValueError("response is not a PNG")
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)  # no half-written files if interrupted
                res["done"].append(name)
                log(f"ok {name}")
                return
            except (urllib.error.URLError, RuntimeError, ValueError, KeyError, TimeoutError, OSError) as e:
                detail = ""
                if isinstance(e, urllib.error.HTTPError):
                    if e.code in (400, 401, 403):  # bad request/key/policy: retrying will not help
                        res["failed"][name] = f"HTTP {e.code}: {e.read()[:200]!r}"
                        log(f"FAIL {name}: {res['failed'][name]}")
                        return
                    detail = f" HTTP {e.code}"
                if attempt == retries:
                    res["failed"][name] = f"{type(e).__name__}{detail}: {e}"
                    log(f"FAIL {name}: {res['failed'][name]}")
                else:
                    sleep(2 ** attempt)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, jobs))
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tarot_live.gen_cards")
    p.add_argument("--provider", choices=PROVIDERS, default=None, help="default: openai if OPENAI_API_KEY else replicate")
    p.add_argument("--only", nargs="*", help="card ids (0-77) and/or 'back'")
    p.add_argument("--force", action="store_true", help="regenerate existing files")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--from-sheet", type=Path, metavar="PICTURE", help="cut the 22 Major Arcana out of a deck sheet picture")
    p.add_argument("--minors", action="store_true", help="only the 56 minor arcana (ids 22-77)")
    p.add_argument("--style-ref", type=Path, nargs="+", metavar="PICTURE",
                   help="reference picture(s) so new cards match your deck's look (OpenAI only)")
    p.add_argument("--dry-run", action="store_true", help="write prompts.json, make no API calls")
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)

    if a.from_sheet:
        if not a.from_sheet.exists():
            print(f"{a.from_sheet} not found", file=sys.stderr)
            return 2
        done = extract_major_from_sheet(a.from_sheet, a.out, a.force)
        print(f"cut {len(done)} Major Arcana into {a.out} (existing files kept; --force to redo)")
        return 0

    jobs = all_jobs()
    if a.minors:
        jobs = [j for j in jobs if j[0].isdigit() and int(j[0]) >= len(MAJOR)]
    if a.only:
        want = {f"{int(x):02d}" if x.isdigit() else x for x in a.only}
        jobs = [j for j in jobs if j[0] in want]
        if not jobs:
            print("no matching cards", file=sys.stderr)
            return 2
    if a.dry_run:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "prompts.json").write_text(json.dumps(dict(jobs), ensure_ascii=False, indent=1))
        print(f"wrote {len(jobs)} prompts to {a.out / 'prompts.json'}")
        return 0

    name = a.provider or ("openai" if os.environ.get("OPENAI_API_KEY") else "replicate")
    need = "OPENAI_API_KEY" if name == "openai" else "REPLICATE_API_TOKEN"
    if need not in os.environ:
        print(f"set {need} first (or use --dry-run)", file=sys.stderr)
        return 2
    if a.style_ref:
        missing = [str(r) for r in a.style_ref if not r.exists()]
        if missing or name != "openai":
            print(f"--style-ref needs OPENAI_API_KEY and existing files {missing}", file=sys.stderr)
            return 2
        provider = openai_style_provider(a.style_ref)
    else:
        provider = PROVIDERS[name]
    res = generate(jobs, provider, a.out, a.force, a.workers)
    print(f"done={len(res['done'])} skipped={len(res['skipped'])} failed={len(res['failed'])}")
    for k, v in res["failed"].items():
        print(f"  {k}: {v}", file=sys.stderr)
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
