# AI Bot Trade 101 — บอทเทรดที่ให้ Claude เทรดแทน

บอทที่ **ต้องไปเรียนก่อน** (ICT, Elliott Wave, Price Action, SMC) แล้วจึงเทรดโดยผ่าน Logic 3 เสาหลัก:
**1. จิตวิทยาการเทรด → 2. Technical Analysis → 3. Money Management**
ส่วน Take Profit / Stop Loss จะ **ให้ AI หาเองจากสถิติ** ที่เก็บระหว่างเทรด

> ⚠️ ตอนนี้ทำงานเป็น **Paper trading / Backtest เท่านั้น** ยังไม่ส่งออเดอร์เงินจริง
> การเทรดมีความเสี่ยงสูง ผลลัพธ์ในอดีตไม่รับประกันอนาคต

## ภาพรวมการทำงาน

```
          ┌──────────────── ขั้นที่ 0: เรียนก่อน (curriculum) ────────────────┐
knowledge/*.md ──► study ──► data/playbook.md  (ถ้าความรู้เปลี่ยน ต้องเรียนใหม่)
                                       │  ยังไม่เรียน = บอทปฏิเสธการเทรด
                                       ▼
แท่งเทียนใหม่ ─► ด่าน 1a จิตวิทยา (tilt / revenge / overtrade / daily loss)
              ─► ด่าน 2  วิเคราะห์ 4 สำนัก → คะแนน confluence → (Claude ตัดสินใจ)
              ─► ด่าน 1b จิตวิทยา ณ จุดเข้า (FOMO / ความมั่นใจ)
              ─► ด่าน 3  Money Management (size จาก invalidation, drawdown, kill-switch)
              ─► เข้าออเดอร์ที่ open แท่งถัดไป ─► บันทึก journal + เส้นทางราคา (MFE/MAE)
                                                        │
                       learn-exits: จำลองทุกคู่ SL/TP ◄──┘ → เลือกคู่ที่ expectancy ดีสุดต่อ setup
```

## โครงสร้าง

| ไฟล์ | หน้าที่ |
|---|---|
| `knowledge/01–07_*.md` | บทเรียน: Price Action, SMC, ICT, Elliott Wave, จิตวิทยา, MM, Logic เข้าเทรด |
| `tradebot/curriculum.py` | ระบบ "เรียนก่อนเทรด": สร้าง playbook, ตรวจว่าครอบคลุมทุกหัวข้อ, ล็อกด้วย hash ของบทเรียน |
| `tradebot/analysis/` | `price_action` (เทรนด์, S/R, pin bar, engulfing), `smc` (OB, FVG, liquidity sweep, premium/discount), `ict` (killzone, OTE, displacement, MSS, Asian range sweep), `elliott` (นับคลื่น + กฎเหล็ก 3 ข้อ), `structure` (HH/HL, BOS, CHoCH) |
| `tradebot/psychology.py` | ด่านจิตวิทยา — กฎที่ AI override ไม่ได้ |
| `tradebot/money.py` | Position sizing, ลด risk เมื่อ drawdown, kill-switch |
| `tradebot/decision/rules.py` | คะแนน confluence + ระบุ setup + จุด invalidation เชิงโครงสร้าง |
| `tradebot/decision/claude_agent.py` | Claude ตัดสินใจขั้นสุดท้าย (BUY/SELL/HOLD) พร้อมเหตุผลครบ 3 เสา |
| `tradebot/exits.py` | Learning mode → Optimized mode ของ SL/TP |
| `tradebot/journal.py` | บันทึกทุกเทรด (SQLite) รวมเส้นทางราคารายแท่ง |
| `tradebot/engine.py` | ลูปแท่งต่อแท่ง (ไม่มี lookahead: ตัดสินใจตอนปิดแท่ง, เข้าที่ open แท่งถัดไป) |

## เริ่มใช้งาน

```bash
pip install -r requirements.txt

# 1) ให้บอทไปเรียนก่อน (บังคับ)
python -m tradebot study            # แบบ offline: รวบรวมกฎจากบทเรียน
python -m tradebot study --claude   # ให้ Claude อ่านบทเรียนทั้งหมดแล้วเขียน playbook ของตัวเอง (ต้องมี ANTHROPIC_API_KEY)
python -m tradebot status

# 2) Backtest เพื่อเก็บสถิติ (Learning mode)
python -m tradebot backtest --csv my_xauusd_1h.csv     # คอลัมน์: time,open,high,low,close,volume
python -m tradebot backtest --yf GC=F --interval 1h    # ต้อง pip install yfinance
python -m tradebot backtest --csv data.csv --ai        # ให้ Claude เป็นคนตัดสินใจ

# 3) เมื่อเก็บสถิติพอ ให้ AI หา SL/TP ที่ดีที่สุดต่อ setup
python -m tradebot learn-exits
python -m tradebot stats

# 4) Paper trading แบบสด
python -m tradebot paper --yf GC=F --interval 1h --ai
```

ไม่ระบุข้อมูล → ใช้ข้อมูลสังเคราะห์ (สำหรับทดสอบระบบเท่านั้น ไม่มี edge จริง)

## เรื่อง Take Profit / Stop Loss (ตามโจทย์: ให้ AI ไปหาจากสถิติ)

1. **Learning mode (เริ่มต้น)** — ไม่มี TP ตายตัว
   - มีแค่ *protective stop* ที่จุด invalidation เชิงโครงสร้าง (ใต้ OB / ใต้ไส้ที่ sweep / ใต้ swing) เพราะ Money Management ต้องใช้ระยะนี้คำนวณ size และกันพอร์ตพัง
   - ถือตามเวลา (`learning_hold_bars`, ค่าเริ่มต้น 24 แท่ง) แล้วบันทึก *เส้นทางราคาทุกแท่ง* (กำไร/ขาดทุนสูงสุดในหน่วย R)
2. **Optimized mode** — เมื่อ setup ใดมีอย่างน้อย 30 เทรด (`min_trades_to_optimize`)
   - `learn-exits` จะ replay ทุกคู่ SL (50–100% ของ stop โครงสร้าง) × TP (0.5R–5R) บนเส้นทางจริง
   - ถ้าแท่งเดียวโดนทั้ง SL และ TP ให้นับว่าโดน SL (มองแง่ร้ายไว้ก่อน)
   - เลือกคู่ที่ expectancy สูงสุดและเป็นบวกเท่านั้น → บันทึกใน `data/sltp_policy.json` แล้วบอทใช้อัตโนมัติ
   - Setup ที่ expectancy ติดลบหลัง 30 เทรด → ถูกปิด (Money Management)

## ตัวอย่างกฎจิตวิทยา/MM (แก้ได้ใน `tradebot/config.py`)

| กฎ | ค่าเริ่มต้น |
|---|---|
| แพ้ติดกัน → พัก (tilt) | 3 ครั้ง → พัก 24 แท่ง |
| Cooldown หลังแพ้ (anti-revenge) | 3 แท่ง |
| เทรดสูงสุดต่อวัน | 4 |
| ขาดทุนรายวันสูงสุด | 3% |
| FOMO | ราคาห่าง EMA20 > 3 ATR หรือแท่งล่าสุด > 3 ATR |
| Risk ต่อเทรด | 1% (ลดเหลือ 0.5% เมื่อ DD > 10%) |
| Kill-switch | DD ≥ 20% |

## Claude ทำอะไรบ้าง
- **ตอนเรียน**: อ่านบทเรียนทั้งหมด แล้วเขียน playbook ของตัวเองครบ 7 หมวด (ระบบตรวจว่าครบก่อนอนุญาตให้เทรด)
- **ตอนเทรด**: ได้รับ context ทั้ง 4 สำนัก + สภาพจิตใจ + บัญชี + สถิติ journal ของตัวเอง → ตอบเป็น JSON (action, setup, confidence, เหตุผลแยก 3 เสา)
- ถูกเรียกเฉพาะเมื่อกฎพบ setup ที่น่าสนใจ (`prefilter_score`) เพื่อประหยัดค่า API
- กฎจิตวิทยาและ MM **มีอำนาจเหนือ Claude เสมอ**; ถ้า API error / ปฏิเสธ → HOLD
- ใช้โมเดล `claude-opus-5-5` พร้อม server-side fallback เมื่อโมเดลปฏิเสธคำขอ (ปิดได้โดยเอา `fallbacks` ออกใน `claude_agent.py`)

## ทดสอบ
```bash
python -m pytest -q
```

## ขั้นต่อไปที่แนะนำ
- เก็บสถิติด้วยข้อมูลจริงหลายปี/หลายตลาด ก่อนเชื่อผล optimize (ระวัง overfit — ควรแยก train/test)
- เพิ่ม Multi-timeframe (HTF bias + LTF entry)
- เชื่อมโบรกเกอร์จริง (MT5 / ccxt) — ควรเริ่มจาก demo account
