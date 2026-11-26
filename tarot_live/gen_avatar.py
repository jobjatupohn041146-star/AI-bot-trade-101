"""Make the looping fortune-teller video for the overlay background.

    python -m tarot_live.gen_avatar portrait                  # AI portrait (needs OPENAI_API_KEY / REPLICATE_API_TOKEN)
    python -m tarot_live.gen_avatar loop                      # offline: seamless "breathing" loop from the portrait (ffmpeg)
    python -m tarot_live.gen_avatar loop --mode api           # real motion via a Replicate image-to-video model
    python -m tarot_live.gen_avatar loop --image my.png       # use your own picture instead

Files: tarot_live/overlay/avatar/portrait.png and loop.mp4 (served at /avatar/loop.mp4; the overlay
shows it automatically when present). Needs `ffmpeg` on PATH (and Pillow for local mode).

`--mode local` is fully offline and loops perfectly (every motion is periodic over the clip), but it only
sways/zooms/pulses the still image: eyes and mouth do not move. `--mode api` gives real animation; its
HTTP flow is not exercised in CI (no network/keys) and model input names vary, see --image-field.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import gen_cards

OUT = Path(__file__).parent / "overlay" / "avatar"

PORTRAIT_PROMPT = (
    "Portrait of a mysterious Thai fortune teller woman, long black hair, wearing an ornate white lace "
    "crown and veil with silver filigree, dark violet temple with misty pillars behind her, soft ethereal "
    "glow, calm gaze toward the viewer, centered, upper body, vertical 9:16 composition with empty space "
    "at the bottom third, photorealistic fantasy, cinematic lighting. No text, no watermark."
)
MOTION_PROMPT = ("She breathes slowly and blinks softly, a gentle smile, hair and veil drift slightly, "
                 "glowing particles float in the air. Camera static, seamless calm loop.")


def frame_params(n: int, total: int, width: int, height: int) -> tuple[float, float, float, float]:
    """(zoom, dx, dy, brightness) for frame n. Every term is sin/cos(2*pi*n/total), so frame `total`
    equals frame 0 and the clip loops with no seam."""
    t = 2 * math.pi * n / total
    return (1.07 + 0.035 * math.sin(t), width * 0.012 * math.sin(t), height * 0.008 * math.cos(t),
            1 + 0.06 * math.sin(t))


def render_local_loop(image: Path, out: Path, seconds: float = 10, fps: int = 30,
                      width: int = 1080, height: int = 1920) -> None:
    """Offline loop: slow breathing zoom + sway + glow pulse, rendered with sub-pixel accuracy.

    (ffmpeg's zoompan rounds to whole pixels and visibly jitters, so frames are computed here
    and piped to ffmpeg only for H.264 encoding.)
    """
    try:
        from PIL import Image, ImageEnhance
    except ImportError:
        raise SystemExit("local mode needs Pillow: pip install Pillow")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH")
    src = Image.open(image).convert("RGB")
    scale = max(width / src.width, height / src.height)  # cover-fit to the target frame
    src = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
    left, top = (src.width - width) // 2, (src.height - height) // 2
    src = src.crop((left, top, left + width, top + height))
    total = int(seconds * fps)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for n in range(total):
            zoom, dx, dy, bright = frame_params(n, total, width, height)
            s_ = 1 / zoom
            cx, cy = width / 2 + dx, height / 2 + dy
            frame = src.transform((width, height), Image.AFFINE,
                                  (s_, 0, cx - s_ * width / 2, 0, s_, cy - s_ * height / 2), Image.BICUBIC)
            proc.stdin.write(ImageEnhance.Brightness(frame).enhance(bright).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode()
    if proc.wait():
        raise SystemExit(f"ffmpeg failed:\n{err[-800:]}")


def pingpong_cmd(src: Path, out: Path) -> list[str]:
    """Play forward then backward so any clip loops without a jump cut."""
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter_complex",
            "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", "-an", str(out)]


def run(cmd: list[str]) -> None:
    if shutil.which(cmd[0]) is None:
        raise SystemExit(f"{cmd[0]} not found on PATH (install ffmpeg)")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{cmd[0]} failed:\n{r.stderr[-800:]}")


def api_animate(image: Path, prompt: str, image_field: str, model: str, timeout: int = 900) -> bytes:
    """Replicate image-to-video. Returns raw mp4 bytes."""
    token = os.environ["REPLICATE_API_TOKEN"]
    data_uri = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
    d = gen_cards._post(f"https://api.replicate.com/v1/models/{model}/predictions",
                        {"Authorization": f"Bearer {token}", "Prefer": "wait"},
                        {"input": {image_field: data_uri, "prompt": prompt}})
    deadline = time.time() + timeout
    while d.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise SystemExit("timed out waiting for the video model")
        time.sleep(5)
        req = urllib.request.Request(d["urls"]["get"], headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    if d["status"] != "succeeded":
        raise SystemExit(f"video model {d['status']}: {d.get('error')}")
    out = d["output"]
    with urllib.request.urlopen(out[0] if isinstance(out, list) else out, timeout=300) as r:
        return r.read()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tarot_live.gen_avatar")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("portrait", help="generate the reader's portrait image")
    sp.add_argument("--provider", choices=gen_cards.PROVIDERS)
    sp.add_argument("--prompt", default=PORTRAIT_PROMPT)
    sl = sub.add_parser("loop", help="turn the portrait into a looping mp4")
    sl.add_argument("--mode", choices=["local", "api"], default="local")
    sl.add_argument("--image", type=Path, help="default: overlay/avatar/portrait.png")
    sl.add_argument("--seconds", type=float, default=10)
    sl.add_argument("--prompt", default=MOTION_PROMPT)
    sl.add_argument("--model", default=os.environ.get("TAROT_VIDEO_MODEL", "kwaivgi/kling-v2.1"),
                    help="Replicate model for --mode api (env TAROT_VIDEO_MODEL)")
    sl.add_argument("--image-field", default="start_image", help="the model's image input name")
    for s in (sp, sl):
        s.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)

    if a.cmd == "portrait":
        name = a.provider or ("openai" if os.environ.get("OPENAI_API_KEY") else "replicate")
        need = "OPENAI_API_KEY" if name == "openai" else "REPLICATE_API_TOKEN"
        if need not in os.environ:
            print(f"set {need} first", file=sys.stderr)
            return 2
        data = gen_cards.PROVIDERS[name](a.prompt, 7)
        (a.out / "portrait.png").write_bytes(data)
        print(f"wrote {a.out / 'portrait.png'}")
        return 0

    image = a.image or a.out / "portrait.png"
    if not image.exists():
        print(f"{image} not found: run `portrait` first or pass --image", file=sys.stderr)
        return 2
    target = a.out / "loop.mp4"
    if a.mode == "local":
        render_local_loop(image, target, a.seconds)
    else:
        if "REPLICATE_API_TOKEN" not in os.environ:
            print("set REPLICATE_API_TOKEN first", file=sys.stderr)
            return 2
        raw = a.out / "raw.mp4"
        raw.write_bytes(api_animate(image, a.prompt, a.image_field, a.model))
        run(pingpong_cmd(raw, target))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
