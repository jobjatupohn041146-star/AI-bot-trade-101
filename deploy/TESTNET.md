# รันกลยุทธ์อันดับ 1 บน Bybit Testnet (1–3 เดือน)

กลยุทธ์: โครงสร้างตลาดตามเทรนด์ + EMA 50/200 + ทิศทาง TF 4 ชม., RR 1:3, เสี่ยง 0.5% ต่อไม้
(ลดจาก 1% เพราะสถิติแพ้ติดกันได้ถึง ~23 ไม้)

1. สมัคร https://testnet.bybit.com → รับเงินทดลอง → สร้าง API key (สิทธิ์ Trade เท่านั้น ห้ามเปิด Withdraw)
2. เช่า VPS Linux (Ubuntu) ที่เปิดตลอด → `sudo bash deploy/setup_vps.sh`
3. ใส่ key ใน `/etc/tradebot.env` (`TRADEBOT_API_KEY`, `TRADEBOT_API_SECRET`)
4. เรียนก่อน: `sudo -u tradebot .venv/bin/python -m tradebot study`
5. เริ่ม: `sudo systemctl enable --now tradebot-testnet@BTC tradebot-testnet@ETH tradebot-testnet@SOL`
6. ดูผล: `sudo -u tradebot .venv/bin/python -m tradebot stats --db data/testnet/BTC_journal.db`

บอทจำสถานะได้แม้รีสตาร์ท, stop loss อยู่ที่ exchange เสมอ, ไม่มีวันส่งออเดอร์เงินจริงถ้าไม่ใส่ `--real`
และ env `TRADEBOT_I_UNDERSTAND_RISK=YES`

เกณฑ์ก่อนคิดถึงเงินจริง (ตั้งไว้ล่วงหน้า): หลัง ≥ 60 ไม้ปิดแล้ว ผลเฉลี่ย > 0R, ไม่มีบั๊กส่งออเดอร์,
และผลไม่ต่างจาก forward test รายวันใน `stats/forward_summary.json` เกินกว่าค่าธรรมเนียม/slippage
