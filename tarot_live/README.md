# tarot_live — ต้นแบบ AI ไลฟ์ดูดวงไพ่ทาโร่

ผู้ชมส่งของขวัญ → เข้าคิว → สุ่มไพ่ → LLM เขียนคำทำนายไทย → (TTS) → โชว์บนโอเวอร์เลย์สำหรับ OBS

## รัน (ไม่ต้องต่อ TikTok)
    pip install aiohttp
    python -m tarot_live --mock            # ผู้ชมปลอม
    # เปิด http://localhost:8765/

## ต่อ TikTok LIVE จริง
    pip install TikTokLive
    python -m tarot_live --tiktok <username>

## ตัวเลือกเสริม
- `ANTHROPIC_API_KEY` (+ `pip install anthropic`): ให้ Claude เขียนคำทำนาย (ตั้งโมเดลด้วย `TAROT_MODEL`, ค่าเริ่มต้น `claude-haiku-5-5`) ถ้าไม่ตั้ง จะใช้เทมเพลตสำเร็จรูป
- `--tts` (+ `pip install edge-tts`): เสียงไทย `th-TH-PremwadeeNeural` เล่นผ่านหน้าโอเวอร์เลย์

## ใช้กับ OBS
Add **Browser Source** → `http://localhost:8765/` ขนาด 1080×1920 วางทับภาพ/วิดีโอหมอดู AI
(แก้ `<video id="avatar">` ใน `overlay/index.html` ให้ชี้ไฟล์วิดีโอวนลูปของคุณ หรือใส่เป็นเลเยอร์ใน OBS แทน)

## ไฟล์
| ไฟล์ | หน้าที่ |
|---|---|
| `cards.py` | ไพ่ 78 ใบ + ความหมาย ตั้งตรง/กลับหัว |
| `engine.py` | ตารางราคา (`DEFAULT_TIERS`), คิว, ลีดเดอร์บอร์ด, เป้าไลก์ |
| `reader.py` | เขียนคำทำนาย (Claude / เทมเพลต) |
| `sources.py` | แหล่งอีเวนต์: mock และ TikTok |
| `server.py` | aiohttp + WebSocket + ตัวทำงานคิว |
| `overlay/index.html` | หน้าโอเวอร์เลย์ |

## สถานะ
- ทดสอบแล้ว: ตรรกะทั้งหมด (`pytest tests/test_tarot_live.py`) และหน้าโอเวอร์เลย์กับ mock
- **ยังไม่ได้ทดสอบ**: `tiktok_source` กับห้องไลฟ์จริง, `--tts`, การเรียก Claude จริง
- TikTokLive เป็นไลบรารีไม่เป็นทางการ อาจพังเมื่อ TikTok อัปเดต
- คำทำนายเพื่อความบันเทิง ควรแปะป้ายว่าเป็นเนื้อหา AI ตามนโยบาย TikTok
