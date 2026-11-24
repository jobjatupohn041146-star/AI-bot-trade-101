# Money Management (การบริหารเงินทุน)

## หลักการ
- **Fixed Fractional Risk**: เสี่ยงคงที่ต่อเทรด เช่น 1% ของทุน
- **Position Size** = (ทุน × risk%) ÷ ระยะห่างจากจุดเข้าถึงจุด invalidation (stop)
  - ตัวอย่าง: ทุน 10,000$ risk 1% = 100$ ระยะ stop 2$ → size = 50 หน่วย
- **Drawdown control**: เมื่อ drawdown เพิ่ม → ลด risk ลง (ป้องกันพอร์ตล้าง)
- **Max Drawdown Kill-switch**: drawdown ถึงเพดาน → หยุดระบบทั้งหมด รอตรวจสอบ
- **ความเสี่ยงรวม**: จำกัดความเสี่ยงของทุก position ที่เปิดอยู่รวมกัน

## คณิตศาสตร์ของการขาดทุน
| ขาดทุน | ต้องกำไรกลับเท่าไร |
|---|---|
| 10% | 11.1% |
| 25% | 33.3% |
| 50% | 100% |

## Expectancy (ความคาดหวัง)
`Expectancy = (Win% × AvgWin) − (Loss% × AvgLoss)` ต้องเป็นบวกเท่านั้นระบบจึงจะอยู่รอด
Setup ไหน expectancy ติดลบหลังเก็บสถิติพอ → ปิด setup นั้น

## กฎสำคัญ (Key Rules)
- Risk ต่อเทรดไม่เกิน 1% (ค่าเริ่มต้น)
- Drawdown > 10% → ลด risk ลงครึ่งหนึ่ง
- Drawdown ≥ 20% → หยุดระบบ (kill-switch)
- ขนาด position คำนวณจากระยะ stop เสมอ ไม่ใช่ความรู้สึก
- ปิด setup ที่ expectancy ติดลบเมื่อมีตัวอย่างเพียงพอ
