# AI Bot Trade 101 — บอทเทรดที่ให้ Claude เทรดแทน

📊 **หน้าเว็บผลทดสอบ:** https://jobjatupohn041146-star.github.io/AI-bot-trade-101/ (ไฟล์ `docs/index.html` สร้างใหม่ด้วย `python scripts/export_dashboard.py && python scripts/build_site.py`)

บอทที่ **ต้องไปเรียนก่อน** (ICT, Elliott Wave, Price Action, SMC) แล้วจึงเทรดโดยผ่าน Logic 3 เสาหลัก:
**1. จิตวิทยาการเทรด → 2. Technical Analysis → 3. Money Management**
ส่วน Take Profit / Stop Loss จะ **ให้ AI หาเองจากสถิติ** ที่เก็บระหว่างเทรด

> ⚠️ ค่าเริ่มต้นคือ Backtest / Paper / **Testnet / Demo** — เงินจริงต้องเปิด 2 ชั้นเอง (ดูหัวข้อ "เทรดจริง")
> การเทรดมีความเสี่ยงสูง ผลลัพธ์ในอดีตไม่รับประกันอนาคต

## ภาพรวมการทำงาน

```
          ┌──────────────── ขั้นที่ 0: เรียนก่อน (curriculum) ────────────────┐
knowledge/*.md ──► study ──► data/playbook.md  (ถ้าความรู้เปลี่ยน ต้องเรียนใหม่)
                                       │  ยังไม่เรียน = บอทปฏิเสธการเทรด
                                       ▼
แท่งเทียนใหม่ ─► มุมมอง TF ใหญ่ (เช่น 4h) จากแท่งที่ปิดแล้วเท่านั้น
              ─► ด่าน 1a จิตวิทยา (tilt / revenge / overtrade / daily loss)
              ─► ด่าน 2  วิเคราะห์ 4 สำนัก → คะแนน confluence → (Claude ตัดสินใจ)
              ─► ด่าน 1b จิตวิทยา ณ จุดเข้า (FOMO / ความมั่นใจ)
              ─► ด่าน 3  Money Management (size จาก invalidation, drawdown, kill-switch)
              ─► เข้าออเดอร์ที่ open แท่งถัดไป ─► บันทึก journal + เส้นทางราคา (MFE/MAE)
                                                        │
        learn-exits: fit บนเทรดเก่า 70% → ตรวจบนเทรดใหม่ 30% ◄──┘ → ผ่านถึงใช้จริง
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
| `tradebot/brokers/` | `SimBroker` (backtest/paper), `CCXTBroker` (คริปโต, testnet), `MT5Broker` (Forex/ทองคำ, demo) |
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

# 4) เทรดสด (เริ่มที่ paper → testnet/demo)
python -m tradebot live --broker sim  --yf GC=F --timeframe 1h --ai                  # paper
python -m tradebot live --broker ccxt --exchange bybit --symbol BTC/USDT:USDT --ai   # testnet
python -m tradebot live --broker mt5  --symbol XAUUSD --ai                           # MT5 demo
```

ไม่ระบุข้อมูล → ใช้ข้อมูลสังเคราะห์ (สำหรับทดสอบระบบเท่านั้น ไม่มี edge จริง)

## เรื่อง Take Profit / Stop Loss (ตามโจทย์: ให้ AI ไปหาจากสถิติ)

1. **Learning mode (เริ่มต้น)** — ไม่มี TP ตายตัว
   - มีแค่ *protective stop* ที่จุด invalidation เชิงโครงสร้าง (ใต้ OB / ใต้ไส้ที่ sweep / ใต้ swing) เพราะ Money Management ต้องใช้ระยะนี้คำนวณ size และกันพอร์ตพัง
   - ถือตามเวลา (`learning_hold_bars`, ค่าเริ่มต้น 24 แท่ง) แล้วบันทึก *เส้นทางราคาทุกแท่ง* (กำไร/ขาดทุนสูงสุดในหน่วย R)
2. **Optimized mode** — เมื่อ setup ใดมีอย่างน้อย 30 เทรด (`min_trades_to_optimize`)
   - `learn-exits` จะ replay ทุกคู่ SL (50–100% ของ stop โครงสร้าง) × TP (0.5R–5R) บนเส้นทางจริง
   - **กัน overfit (walk-forward)**: หาคู่ที่ดีที่สุดจากเทรดเก่า 70% แล้วทดสอบกับเทรดใหม่ 30% ที่ไม่เคยเห็น
     ใช้จริงก็ต่อเมื่อผลบนชุดทดสอบ > 0 และไม่แย่กว่าการออกแบบเดิม ไม่ผ่าน → แสดงใน `rejected_overfit_or_no_edge`
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

## Multi-timeframe
- ตั้งใน `config.py`: `htf = "4h"` (ปิดได้ด้วย `None`)
- บอท resample TF เล็กเป็น TF ใหญ่ แล้วใช้ **เฉพาะแท่ง TF ใหญ่ที่ปิดแล้ว** (ไม่แอบดูอนาคต)
- bias ของ TF ใหญ่ = โครงสร้าง (BOS/CHoCH) + EMA50/200 → เทรดตาม bias ได้ +2 คะแนน, สวน bias −2.5 คะแนน

## เทรดจริง / Demo / Testnet

| Broker | ตลาด | ค่าเริ่มต้น | ตั้งค่า |
|---|---|---|---|
| `sim` | อะไรก็ได้ที่ yfinance มี | paper | — |
| `ccxt` | คริปโต (Bybit, OKX, Binance Futures …) | **testnet** | env `TRADEBOT_API_KEY`, `TRADEBOT_API_SECRET` (`TRADEBOT_API_PASSWORD` สำหรับ OKX) |
| `mt5` | Forex / ทองคำ / CFD (Windows + MT5 terminal) | **ปฏิเสธบัญชี real** | login ใน terminal หรือ env `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`; `MT5_SERVER_UTC_OFFSET` = เวลาเซิร์ฟเวอร์โบรกเกอร์ต่าง UTC กี่ชั่วโมง (ให้ killzone ตรง) |

ระบบความปลอดภัย:
- **เงินจริงต้องเปิด 2 ชั้น**: ใส่ `--real` และตั้ง env `TRADEBOT_I_UNDERSTAND_RISK=YES`
- Stop loss ถูกส่งไปอยู่ที่โบรกเกอร์/exchange พร้อมออเดอร์ (บอทดับ stop ก็ยังอยู่)
  ถ้าตั้ง stop ไม่สำเร็จ บอทจะปิด position ทันที — ไม่มีวันถือโดยไม่มี stop
- ขนาด position ถูกปัด **ลง** ตามขั้นต่ำของโบรกเกอร์ (ไม่มีวันเสี่ยงเกินที่คำนวณ)
- ถ้ามี position ค้างอยู่ก่อนเริ่มบอท → บอทไม่ยอมเริ่ม (ไม่รับ position ที่ไม่รู้ที่มา)
- Kill-switch (DD ≥ 20%) → หยุดลูปทันที
- ข้อจำกัด: สถานะจิตวิทยา (แพ้ติดกัน ฯลฯ) อยู่ในหน่วยความจำ ถ้ารีสตาร์ทบอทจะเริ่มนับใหม่

## ขั้นต่อไปที่แนะนำ
- เก็บสถิติด้วยข้อมูลจริงหลายปี/หลายตลาด แล้วรัน `learn-exits`
- รันบน testnet/demo อย่างน้อย 1–3 เดือน เทียบผลกับ backtest ก่อนคิดถึงเงินจริง
