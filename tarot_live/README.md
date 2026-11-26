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
| `safety.py` | กรองข้อความผู้ชม: ลบลิงก์/อักขระควบคุม, กัน prompt injection, คำหยาบ, หัวข้อละเอียดอ่อน |
| `store.py` | เก็บคิว/ลีดเดอร์บอร์ด/เป้าไลก์ใน SQLite (`--db`, ค่าเริ่มต้น `data/tarot_live.db`) |
| `gen_cards.py` | สร้างภาพไพ่ 78 ใบ + หลังไพ่ ด้วย OpenAI หรือ Replicate (Flux) |
| `gen_avatar.py` | สร้างภาพหมอดูและวิดีโอวนลูปสำหรับพื้นหลัง |
| `server.py` | aiohttp + WebSocket + ตัวทำงานคิว |
| `overlay/index.html` | หน้าโอเวอร์เลย์ |

## สถานะ
- คำถามที่เป็น injection/คำหยาบ/หัวข้อละเอียดอ่อน (สุขภาพ หวย การลงทุน ฯลฯ) จะไม่ถูกส่งให้ LLM ระบบตอบภาพรวมและไม่ฟันธง รายการคำอยู่ใน `safety.py` ปรับเพิ่มได้
- ทดสอบแล้ว: ตรรกะทั้งหมด (`pytest tests/test_tarot_live.py`) และหน้าโอเวอร์เลย์กับ mock
- **ยังไม่ได้ทดสอบ**: `tiktok_source` กับห้องไลฟ์จริง, `--tts`, การเรียก Claude จริง
- TikTokLive เป็นไลบรารีไม่เป็นทางการ อาจพังเมื่อ TikTok อัปเดต
- คำทำนายเพื่อความบันเทิง ควรแปะป้ายว่าเป็นเนื้อหา AI ตามนโยบาย TikTok

## สร้างภาพไพ่
    python -m tarot_live.gen_cards --dry-run        # ดูพรอมต์ทั้ง 79 อัน (prompts.json) ไม่เสียเงิน
    export OPENAI_API_KEY=...                       # หรือ REPLICATE_API_TOKEN
    python -m tarot_live.gen_cards --only 0 16 back # ลอง 3 ใบก่อน ดูสไตล์ถูกใจไหม
    python -m tarot_live.gen_cards                  # ที่เหลือทั้งหมด (รันซ้ำได้ ข้ามใบที่ทำแล้ว)
ผลลัพธ์อยู่ที่ `overlay/cards/NN.png` (NN = เลขไพ่ใน `cards.py`) + `back.png` โอเวอร์เลย์จะใช้ภาพเองถ้ามี ไม่มีก็ใช้การ์ดตัวอักษรเดิม
ปรับสไตล์ที่ตัวแปร `STYLE` ใน `gen_cards.py` ก่อนรันทั้งหมด ราคาต่อภาพดูที่หน้าราคาของผู้ให้บริการ (ราว 79 ภาพ)
ภาพ AI สไตล์อาจไม่เหมือนกันเป๊ะทุกใบ ถ้าใบไหนหลุดให้รันใหม่ด้วย `--only N --force`

## วิดีโอหมอดูวนลูป
    pip install Pillow                                # ต้องมี ffmpeg ในเครื่องด้วย
    python -m tarot_live.gen_avatar portrait          # สร้างภาพหมอดู (ต้องมี OPENAI_API_KEY หรือ REPLICATE_API_TOKEN)
    python -m tarot_live.gen_avatar loop              # ทำคลิปวนลูป 10 วินาทีแบบออฟไลน์
    python -m tarot_live.gen_avatar loop --image my.png   # ใช้ภาพของคุณเอง
    python -m tarot_live.gen_avatar loop --mode api   # ให้โมเดลวิดีโอ (Replicate) ทำให้ขยับจริง
ผลลัพธ์: `overlay/avatar/loop.mp4` โอเวอร์เลย์เล่นให้เองถ้ามีไฟล์ และจะเรืองแสงเป็นจังหวะตอนแม่หมอกำลังทำนาย
- `--mode local` (ค่าเริ่มต้น): ภาพนิ่งหายใจเข้าออก ขยับเบาๆ และเรืองแสง วนลูปเนียน ไม่ต้องใช้อินเทอร์เน็ต แต่ตากับปากไม่ขยับ เรนเดอร์คลิป 10 วินาทีใช้ประมาณ 1 นาที
- `--mode api`: ได้การขยับจริง (กะพริบตา ผมปลิว) แล้วต่อคลิปไปข้างหน้า+ย้อนกลับให้วนลูปไม่สะดุด ชื่อโมเดลตั้งด้วย `TAROT_VIDEO_MODEL` และชื่อช่องรับภาพด้วย `--image-field` (แต่ละโมเดลไม่เหมือนกัน) ส่วนนี้ยังไม่เคยทดสอบกับ API จริง
- ถ้าต้องการปากขยับตามเสียง ต้องใช้บริการอื่น เช่น HeyGen หรือ Live2D แล้วใส่เป็นเลเยอร์ใน OBS แทน

## ใช้รูป "ชีตไพ่ + แม่หมอ" ที่มีอยู่แล้ว
ถ้ามีภาพรวมแบบหน้าปกสำรับ (แม่หมออยู่ด้านบน ไพ่เรียงอยู่ด้านล่าง) ตัดแม่หมอกับหลังไพ่ออกมาใช้ได้เลย:

    python -m tarot_live.gen_avatar sheet my_deck_sheet.png
    python -m tarot_live.gen_avatar loop
ได้ `overlay/avatar/portrait.png`, `overlay/cards/back.png` และ `loop.mp4` ถ้าตัดไม่ตรง ปรับสัดส่วนด้วย `--reader-box X0 Y0 X1 Y1` / `--back-box ...` (ค่า 0-1 ของความกว้าง/สูงภาพ)
ไพ่ในชีตตัวเล็กและมีตัวอักษรฝังในภาพ จึงไม่ได้นำมาใช้เป็นหน้าไพ่ ถ้าอยากได้หน้าไพ่สไตล์เดียวกัน ใช้ `gen_cards` (สไตล์ตั้งค่าไว้ให้เข้ากับชีตนี้แล้ว)
