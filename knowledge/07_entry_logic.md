# Logic การเข้าเทรด 3 เสาหลัก

บอทจะเข้าเทรดได้ก็ต่อเมื่อ **ผ่านทั้ง 3 ด่าน** ตามลำดับ:

## ด่าน 1: จิตวิทยา (Psychology Gate)
ตรวจสภาพ "จิตใจ" ของระบบก่อน: แพ้ติดกันไหม, ถึงลิมิตรายวันไหม, อยู่ใน cooldown ไหม, เป็นการไล่ราคา (FOMO) หรือเปล่า
→ ถ้าไม่ผ่าน = ไม่ดูกราฟต่อเลย

## ด่าน 2: Technical Analysis (Confluence)
รวมหลักฐานจาก 4 สำนัก ต้องได้คะแนน confluence ถึงเกณฑ์:
1. **ทิศทาง (Bias)**: โครงสร้างตลาด (PA/SMC) + EMA
2. **โซน (Where)**: OB / FVG / S/R / Premium-Discount / OTE
3. **จังหวะ (When)**: Liquidity sweep, CHoCH/MSS, แท่งเทียนยืนยัน, Killzone
4. **บริบทคลื่น (Elliott)**: อยู่ปลายคลื่น 2/4 = บวก, impulse จบแล้ว = ลบ

## ด่าน 3: Money Management
คำนวณขนาด position จากจุด invalidation, ตรวจ drawdown, ความเสี่ยงรวม, ต้องมี size > 0

## เรื่อง Take Profit / Stop Loss
- ช่วงแรก (**Learning mode**): ใช้ "จุด invalidation เชิงโครงสร้าง" เป็น protective stop เพื่อคุมความเสี่ยงและคำนวณ size เท่านั้น
  ไม่ตั้ง TP ตายตัว — ถือตามเวลา (time exit) เพื่อเก็บสถิติ MFE/MAE (กำไร/ขาดทุนสูงสุดระหว่างถือ) ให้ครบ
- เมื่อสถิติพอ (**Optimized mode**): AI จำลองทุกคู่ SL/TP จากเส้นทางราคาที่บันทึกไว้ แล้วเลือกคู่ที่ให้ expectancy สูงสุดแยกตาม setup

## กฎสำคัญ (Key Rules)
- ต้องผ่าน 3 ด่านตามลำดับ: จิตวิทยา → เทคนิค → Money Management
- AI (Claude) เสนอได้ แต่ hard rule ของจิตวิทยาและ MM มีอำนาจเหนือ AI เสมอ
- ไม่มี confluence พอ = HOLD
