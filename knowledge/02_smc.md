# Smart Money Concept (SMC)

## แนวคิดหลัก
สถาบัน (Smart Money) ต้องการสภาพคล่อง (Liquidity) เพื่อเปิดออเดอร์ขนาดใหญ่ จึงมักดันราคาไปกวาด stop loss ของรายย่อยก่อน แล้วค่อยไปทางจริง

## องค์ประกอบ
- **Market Structure**
  - **BOS (Break of Structure)**: ราคาปิดทะลุ swing ตามเทรนด์เดิม = เทรนด์ยังไปต่อ
  - **CHoCH (Change of Character)**: ราคาปิดทะลุ swing สวนเทรนด์เดิม = สัญญาณเปลี่ยนเทรนด์ครั้งแรก
- **Order Block (OB)**: แท่งเทียนฝั่งตรงข้ามแท่งสุดท้ายก่อนเกิดแรงเหวี่ยง (displacement) ที่ทำ BOS/CHoCH
  - Bullish OB = แท่งแดงสุดท้ายก่อนราคาพุ่งขึ้นทำ BOS
  - OB ถูกยกเลิกเมื่อราคาปิดทะลุฝั่งตรงข้ามของ OB
- **Fair Value Gap (FVG / Imbalance)**: ช่องว่างระหว่างไส้แท่งที่ 1 และแท่งที่ 3 ราคามักกลับมาเติม
- **Liquidity**
  - Buy-side liquidity (BSL) = เหนือ swing high / Equal Highs
  - Sell-side liquidity (SSL) = ใต้ swing low / Equal Lows
  - **Liquidity Sweep**: ไส้ทะลุ swing แล้วปิดกลับเข้ามา = กวาด stop แล้ว
- **Premium / Discount**: แบ่ง dealing range ครึ่งหนึ่ง (Equilibrium 50%)
  - Long ควรเข้าใน Discount (<50%), Short ควรเข้าใน Premium (>50%)

## กฎสำคัญ (Key Rules)
- ลำดับที่ดีที่สุด: Liquidity sweep → CHoCH/BOS พร้อม displacement → ราคากลับมา retest OB/FVG → เข้า
- Long เฉพาะใน Discount, Short เฉพาะใน Premium
- ใช้ OB/FVG ที่ยัง "ไม่ถูก mitigate" เท่านั้น
- จุด invalidation (ที่ใช้คำนวณขนาด position) คือใต้ OB/ใต้ swing ที่ถูก sweep
