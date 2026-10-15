# -*- coding: utf-8 -*-
"""
Production HTTP Server for Google Gemini Pro CRM (Linux / Windows / Docker / Cloud)
Hỗ trợ chạy trên mọi Hosting VPS Linux, Windows Server, Docker, Render, Railway, v.v.
Không yêu cầu cài đặt thư viện bên thứ 3 (Chạy thuần thư viện chuẩn Python 3.8+).
Cổng mặc định: 8080 (hoặc qua biến môi trường PORT).
"""

import os
import sys
import json
import base64
import asyncio
import urllib.request
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

# Đảm bảo console UTF-8 trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

PORT = int(os.environ.get("PORT", 8080))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def read_json_file(filename, default):
    filepath = os.path.join(BASE_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default

def write_json_file(filename, data):
    filepath = os.path.join(BASE_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

class GeminiCRMHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Thiết lập CORS toàn diện cho phép gọi API mượt mà
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_post_json(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        raw = self.rfile.read(content_len).decode("utf-8")
        try:
            return json.loads(raw)
        except:
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Điều hướng trang chủ và admin
        if path == "/" or path == "":
            self.path = "/index.html"
            return super().do_GET()
        if path == "/admin" or path == "/admin/":
            self.path = "/admin.html"
            return super().do_GET()

        # 1. API: Cấu hình cổng thanh toán
        if path == "/api/payment-config":
            cfg = read_json_file("payment_config.json", {})
            return self.send_json(cfg)

        # 2. API: Lấy biến động số dư ngân hàng
        if path == "/api/bank-transactions":
            txs = read_json_file("bank_transactions.json", [])
            return self.send_json(txs)

        # 3. API: Lấy danh sách đơn hàng
        if path == "/api/orders":
            orders = read_json_file("orders.json", [])
            return self.send_json(orders)

        # 4. API: Kiểm tra trạng thái thanh toán thật (check-payment)
        if path == "/api/check-payment":
            memo = query.get("memo", [""])[0]
            phone = query.get("phone", [""])[0]
            public_id = query.get("publicId", [""])[0]

            # 4.1 Kiểm tra qua ApiPay bridge nếu có publicId
            if public_id:
                try:
                    import apipay_bridge
                    res = apipay_bridge.check_payment_status(public_id)
                    if res.get("paid"):
                        return self.send_json({
                            "paid": True,
                            "message": "Payment verified via APIPay Cloud",
                            "transaction": res.get("transaction"),
                            "source": "APIPay Cloud"
                        })
                except Exception as e:
                    pass

            # 4.2 Kiểm tra đối soát trong nhật ký giao dịch ngân hàng
            txs = read_json_file("bank_transactions.json", [])
            clean_phone = phone.replace("+84", "0").replace(" ", "") if phone else ""
            clean_memo = memo.replace(" ", "").upper() if memo else ""

            for tx in txs:
                desc = (tx.get("description") or tx.get("memo") or "").upper().replace(" ", "")
                if (clean_phone and clean_phone in desc) or (clean_memo and clean_memo in desc):
                    return self.send_json({
                        "paid": True,
                        "message": "Payment verified via Live Bank Feed",
                        "transaction": tx,
                        "source": tx.get("source", "Live Bank Stream")
                    })

            return self.send_json({"paid": False, "message": "Chờ quét mã thanh toán..."})

        # 5. API: Lấy ảnh QR VietQR chuẩn
        if path == "/api/qr-image":
            qr_file = os.path.join(BASE_DIR, "default_qr.txt")
            if os.path.exists(qr_file):
                with open(qr_file, "r", encoding="utf-8") as f:
                    raw_b64 = f.read().replace("data:image/png;base64,", "").strip()
                img_data = base64.b64decode(raw_b64)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(img_data)))
                self.end_headers()
                self.wfile.write(img_data)
                return
            else:
                return self.send_json({"status": "error", "message": "QR image not found"}, 404)

        # 6. API: Lấy mã Google Apps Script để copy nhanh
        if path == "/api/get-apps-script":
            script_path = os.path.join(BASE_DIR, "GoogleAppsScript_CRM_AutoBot.js")
            if os.path.exists(script_path):
                with open(script_path, "r", encoding="utf-8") as f:
                    code = f.read()
                return self.send_json({"status": "success", "code": code})
            return self.send_json({"status": "error", "message": "Script file not found"}, 404)

        # 7. API: Cấu hình Telegram
        if path == "/api/telegram-config":
            cfg = read_json_file("telegram_config.json", {})
            return self.send_json(cfg)

        # 8. API: Test kết nối API Pay
        if path == "/api/apipay-test":
            try:
                import apipay_bridge
                res = apipay_bridge.test_connection()
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 9. API: Kiểm tra trạng thái Userbot Auto Buyer (@shopxoainon_bot)
        if path == "/api/tele-buyer/status":
            try:
                import telegram_buyer
                is_auth = asyncio.run(telegram_buyer.check_is_authorized())
                return self.send_json({"status": "success", "is_authorized": is_auth})
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e), "is_authorized": False}, 500)

        # Mặc định trả về static file
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_post_json()

        # 1. API: Lưu cấu hình cổng thanh toán
        if path == "/api/payment-config":
            write_json_file("payment_config.json", body)
            return self.send_json({"status": "success", "message": "Payment config saved"})

        # 2. API: Nhận hoặc xóa biến động số dư
        if path == "/api/bank-transactions":
            write_json_file("bank_transactions.json", [])
            return self.send_json({"status": "success", "message": "Transactions cleared"})

        # 3. API: Lưu đơn hàng mới & Tự động bắn thông báo Telegram
        if path == "/api/orders":
            orders = read_json_file("orders.json", [])
            order_id = body.get("orderId", f"#GEM-{int(datetime.now().timestamp()) % 10000:04d}")
            body["orderId"] = order_id
            
            # Cập nhật nếu trùng mã đơn, ngược lại thêm mới
            found = False
            for i, o in enumerate(orders):
                if o.get("orderId") == order_id:
                    orders[i] = body
                    found = True
                    break
            if not found:
                orders.insert(0, body)
            if len(orders) > 500:
                orders = orders[:500]
            write_json_file("orders.json", orders)

            # Bắn Telegram khi thanh toán thành công
            status_str = (body.get("status") or "").lower()
            is_paid = ("đã thanh toán" in status_str or "thành công" in status_str or "paid" in status_str) and ("chờ" not in status_str)
            if is_paid:
                try:
                    import telegram_sender
                    telegram_sender.send_telegram_raw(telegram_sender.get_payment_success_template(body))
                except:
                    pass

                # Đồng bộ Google Sheet qua Webhook
                try:
                    cfg = read_json_file("payment_config.json", {})
                    webhook = cfg.get("googleSheetWebhookUrl")
                    if webhook and "SAMPLE" not in webhook:
                        req_data = json.dumps({
                            "action": "new_order",
                            "time": body.get("time") or datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            "orderId": order_id,
                            "product": body.get("package") or "Google Gemini Pro 18 Tháng",
                            "amount": body.get("amount") or "90.000 VNĐ",
                            "name": body.get("name") or "Khách hàng",
                            "phone": body.get("phone") or "",
                            "email": body.get("email") or "",
                            "memo": body.get("memo") or f"PRO18T {body.get('phone', '')}",
                            "licenseLink": body.get("licenseLink") or "",
                            "referrer": body.get("referrer") or "Trực tiếp",
                            "ipLocation": f"{body.get('ip', '127.0.0.1')} ({body.get('location', 'VN')})",
                            "status": body.get("status") or "Đã thanh toán (MBBank)"
                        }).encode("utf-8")
                        req = urllib.request.Request(webhook, data=req_data, headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=8)
                except:
                    pass

            return self.send_json({"status": "success", "orderId": order_id})

        # API: Nhận Webhook từ APIPay / Casso / SeAPay / MBBank
        if path == "/api/webhook":
            items = []
            if isinstance(body.get("data"), list):
                items = body.get("data")
            elif isinstance(body.get("data", {}).get("records"), list):
                items = body.get("data", {}).get("records")
            elif isinstance(body.get("records"), list):
                items = body.get("records")
            elif isinstance(body.get("transactions"), list):
                items = body.get("transactions")
            elif isinstance(body, list):
                items = body
            elif isinstance(body, dict) and body:
                items = [body]

            current_txs = read_json_file("bank_transactions.json", [])
            for it in items:
                amt = int(it.get("amount") or 0)
                desc = it.get("description") or it.get("memo") or it.get("content") or ""
                if amt > 0:
                    current_txs.insert(0, {
                        "id": str(it.get("id") or f"TX_{int(datetime.now().timestamp()) % 1000000:06d}"),
                        "amount": amt,
                        "description": desc,
                        "bank": it.get("bank") or "MBBank",
                        "time": it.get("time") or it.get("transactionDateTime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "Webhook API Pay"
                    })
            write_json_file("bank_transactions.json", current_txs[:150])
            return self.send_json({"status": "success", "message": "Webhook processed", "count": len(items)})

        # 4. API: Mô phỏng thanh toán (Simulate)
        if path == "/api/simulate-payment":
            phone = body.get("phone", "0901234567")
            memo = body.get("memo", f"PRO18T {phone}")
            amount = int(body.get("amount", 90000))
            sim_tx = {
                "id": f"SIM_{int(datetime.now().timestamp()) % 1000000:06d}",
                "amount": amount,
                "description": memo,
                "bank": "MBBank",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Simulated / Test Admin"
            }
            txs = read_json_file("bank_transactions.json", [])
            txs.insert(0, sim_tx)
            write_json_file("bank_transactions.json", txs[:150])
            return self.send_json({"status": "success", "transaction": sim_tx})

        # 5. API: Tạo yêu cầu thanh toán ApiPay
        if path == "/api/apipay-create":
            try:
                import apipay_bridge
                phone = body.get("phone", "0901234567")
                amount = int(body.get("amount", 90000))
                memo = body.get("memo", f"PRO18T {phone}")
                res = apipay_bridge.create_payment_request(phone, amount, memo)
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 6. API: Gửi thông báo Telegram
        if path == "/api/telegram-notify":
            msg = body.get("message", "")
            try:
                import telegram_sender
                ok = telegram_sender.send_telegram_raw(msg)
                return self.send_json({"status": "success" if ok else "error"})
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 7. API: Cảnh báo đăng nhập Admin
        if path == "/api/admin-login-notify":
            try:
                import telegram_sender
                msg = telegram_sender.get_admin_login_template(body)
                telegram_sender.send_telegram_raw(msg)
                return self.send_json({"status": "success"})
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 8. API: Gửi Email hóa đơn qua Gmail SMTP
        if path == "/api/send-email":
            try:
                import mailer
                res = mailer.send_activation_email(body)
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 9. API: Yêu cầu gửi mã OTP Telegram Userbot
        if path == "/api/tele-buyer/request-otp":
            try:
                import telegram_buyer
                phone = body.get("phone", "")
                res = asyncio.run(telegram_buyer.request_otp(phone))
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 10. API: Xác thực mã OTP & Đăng nhập Telegram Userbot
        if path == "/api/tele-buyer/submit-otp":
            try:
                import telegram_buyer
                code = body.get("code", "")
                pwd = body.get("password", None)
                res = asyncio.run(telegram_buyer.submit_otp(code, pwd))
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 11. API: Mua link tự động từ bot @shopxoainon_bot
        if path == "/api/tele-buyer/buy":
            try:
                import telegram_buyer
                res = asyncio.run(telegram_buyer.execute_buy_gemini())
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        return self.send_json({"status": "ignored"}, 404)

def run():
    print(f"==================================================================")
    print(f"  GOOGLE GEMINI PRO 18T CRM SERVER (PRODUCTION READY)")
    print(f"  Môi trường: Python {sys.version.split()[0]} • Cổng: {PORT}")
    print(f"  Trang bán hàng : http://localhost:{PORT}/")
    print(f"  Trang Quản trị : http://localhost:{PORT}/admin (Mật khẩu: Khoi@123)")
    print(f"==================================================================")
    server = HTTPServer(("0.0.0.0", PORT), GeminiCRMHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng máy chủ...")
        server.server_close()

if __name__ == "__main__":
    run()
