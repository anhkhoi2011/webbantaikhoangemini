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
import threading
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
LICENSES_FILE = "licenses.json"
LICENSE_LOCK = threading.Lock()
AUTOBUY_LOCK = threading.Lock()
LICENSE_STATUSES = {"Sẵn sàng", "Đã cấp"}

def read_json_file(filename, default):
    filepath = os.path.join(BASE_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except:
            return default
    return default

def write_json_file(filename, data):
    filepath = os.path.join(BASE_DIR, filename)
    try:
        tmp_path = filepath + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
        return True
    except:
        return False


def normalize_license(item):
    """Return a safe, normalized inventory record or None."""
    if not isinstance(item, dict):
        return None
    link = str(item.get("link") or "").strip()
    if not link or not (link.startswith("https://") or link.startswith("http://")):
        return None
    if "GM-STOCK-" in link or "GM-KEY-" in link:
        return None
    try:
        item_id = int(item.get("id") or 0)
    except (TypeError, ValueError):
        item_id = 0
    return {
        "id": item_id,
        "link": link,
        "status": item.get("status") if item.get("status") in LICENSE_STATUSES else "Sẵn sàng",
        "assignedTo": str(item.get("assignedTo") or "-")[:300]
    }


def read_licenses():
    raw = read_json_file(LICENSES_FILE, [])
    if not isinstance(raw, list):
        return []
    return [item for item in (normalize_license(x) for x in raw) if item]


def next_license_id(items):
    return max((int(item.get("id") or 0) for item in items), default=0) + 1


def license_stock_count(items):
    return sum(1 for item in items if item.get("status") == "Sẵn sàng")

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
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            body = json.dumps({"status": "error", "message": "Invalid JSON response"}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_post_json(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        try:
            raw = self.rfile.read(content_len).decode("utf-8", errors="replace")
            return json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, Exception):
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

        # 3.1 API: Lấy kho license dùng chung cho mọi thiết bị
        if path == "/api/licenses":
            with LICENSE_LOCK:
                items = read_licenses()
                # Tự sửa các bản ghi cũ không có ID trước khi trả về.
                changed = False
                used_ids = set()
                for item in items:
                    if not item.get("id") or item["id"] in used_ids:
                        item["id"] = next_license_id(items)
                        changed = True
                    used_ids.add(item["id"])
                if changed:
                    write_json_file(LICENSES_FILE, items)
            return self.send_json({"status": "success", "items": items, "available": license_stock_count(items)})

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

        # 10. API: Báo động lên giá (Mốc 200 đơn lên giá 129K, FOMO chạy từ 150 lên 195)
        if path == "/api/fomo-stats" or path == "/api/sold-stats":
            client_ip = self.headers.get("X-Forwarded-For")
            if client_ip:
                client_ip = client_ip.split(",")[0].strip()
            else:
                client_ip = self.client_address[0]

            # Khởi điểm đúng 150 đơn, cộng thêm số đơn thanh toán thật từ orders.json (tối đa 195)
            orders = read_json_file("orders.json", [])
            paid_count = len([o for o in orders if ("đã thanh toán" in (o.get("status") or "").lower() or "thành công" in (o.get("status") or "").lower())])
            current_sold = min(195, max(150, 150 + paid_count))
            remaining = max(5, 200 - current_sold)

            # Đồng bộ lại sold_stats.json ở mốc chuẩn
            write_json_file("sold_stats.json", {
                "baseCount": 150,
                "targetCount": 200,
                "maxFomo": 195,
                "currentSold": current_sold,
                "currentPrice": "90.000đ",
                "nextPrice": "129.000đ"
            })

            return self.send_json({
                "status": "success",
                "soldCount": current_sold,
                "baseCount": 150,
                "targetCount": 200,
                "maxFomo": 195,
                "remainingSlots": remaining,
                "currentPrice": "90.000đ",
                "nextPrice": "129.000đ",
                "clientIp": client_ip
            })

        # Mặc định trả về static file
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_post_json()

        # 0. API: Thao tác kho license tập trung
        if path == "/api/licenses":
            action = str(body.get("action") or "").strip().lower()
            with LICENSE_LOCK:
                items = read_licenses()
                if action in ("add", "bulk_add", "import"):
                    raw_items = body.get("items")
                    if raw_items is None:
                        raw_items = [{"link": link} for link in (body.get("links") or [])]
                    if not isinstance(raw_items, list):
                        return self.send_json({"status": "error", "message": "items phải là một mảng"}, 400)
                    existing = {item["link"] for item in items}
                    added = []
                    skipped = []
                    for raw in raw_items:
                        normalized = normalize_license(raw if isinstance(raw, dict) else {"link": raw})
                        if not normalized:
                            skipped.append(str(raw)[:120])
                            continue
                        if normalized["link"] in existing:
                            skipped.append(normalized["link"])
                            continue
                        normalized["id"] = next_license_id(items + added)
                        items.append(normalized)
                        added.append(normalized)
                        existing.add(normalized["link"])
                    if not write_json_file(LICENSES_FILE, items):
                        return self.send_json({"status": "error", "message": "Không thể lưu kho license"}, 500)
                    return self.send_json({"status": "success", "items": items, "added": len(added), "skipped": skipped, "available": license_stock_count(items)})

                if action == "delete":
                    del_id = body.get("id")
                    del_link = str(body.get("link") or "").strip()
                    try:
                        del_id = int(del_id) if del_id is not None and str(del_id).strip() != "" else None
                    except (TypeError, ValueError):
                        del_id = None

                    new_items = []
                    for item in items:
                        # Bỏ qua item nếu trùng ID hoặc trùng Link
                        if del_id is not None and item.get("id") == del_id:
                            continue
                        if del_link and item.get("link") == del_link:
                            continue
                        new_items.append(item)

                    write_json_file(LICENSES_FILE, new_items)
                    return self.send_json({"status": "success", "items": new_items, "available": license_stock_count(new_items)})

                if action == "clear":
                    if not write_json_file(LICENSES_FILE, []):
                        return self.send_json({"status": "error", "message": "Không thể xóa kho license"}, 500)
                    return self.send_json({"status": "success", "items": [], "available": 0})

                return self.send_json({"status": "error", "message": "Action kho license không hợp lệ"}, 400)

        # 0.1 API: Cấp phát nguyên tử một license theo FIFO
        if path == "/api/licenses/claim":
            name = str(body.get("name") or "Khách hàng").strip()[:120]
            order_id = str(body.get("orderId") or "").strip()[:80]
            with LICENSE_LOCK:
                items = read_licenses()
                available = [item for item in items if item.get("status") == "Sẵn sàng"]
                available.sort(key=lambda item: (int(item.get("id") or 0), items.index(item)))
                if not available:
                    return self.send_json({"status": "out_of_stock", "message": "Kho hiện đã hết license", "available": 0}, 409)
                selected = available[0]
                selected["status"] = "Đã cấp"
                selected["assignedTo"] = f"{name} ({order_id})" if order_id else name
                if not write_json_file(LICENSES_FILE, items):
                    return self.send_json({"status": "error", "message": "Không thể cập nhật kho license"}, 500)
                return self.send_json({"status": "success", "license": selected, "licenseLink": selected["link"], "available": license_stock_count(items)})

        # 0.15 API: Cấp license + TỰ ĐỘNG MUA LINK từ bot khi kho hết hàng
        if path == "/api/licenses/auto-claim":
            name = str(body.get("name") or "Khách hàng").strip()[:120]
            order_id = str(body.get("orderId") or "").strip()[:80]

            # Bước 1: Thử cấp từ kho hiện có trước (không tốn tiền mua)
            with LICENSE_LOCK:
                items = read_licenses()
                available = [item for item in items if item.get("status") == "Sẵn sàng"]
                available.sort(key=lambda item: (int(item.get("id") or 0), items.index(item)))
                if available:
                    selected = available[0]
                    selected["status"] = "Đã cấp"
                    selected["assignedTo"] = f"{name} ({order_id})" if order_id else name
                    if not write_json_file(LICENSES_FILE, items):
                        return self.send_json({"status": "error", "message": "Không thể cập nhật kho license"}, 500)
                    return self.send_json({
                        "status": "success", "source": "stock",
                        "license": selected, "licenseLink": selected["link"],
                        "available": license_stock_count(items)
                    })

            # Bước 2: Kho hết -> Khóa auto-buy để chỉ 1 luồng mua tại một thời điểm
            if not AUTOBUY_LOCK.acquire(blocking=False):
                return self.send_json({
                    "status": "auto_buy_in_progress",
                    "message": "Hệ thống đang tự mua link cho đơn khác, vui lòng thử lại sau vài giây",
                    "available": 0
                }, 202)

            try:
                # Kiểm tra userbot đã đăng nhập chưa
                try:
                    import telegram_buyer
                    is_auth = asyncio.run(telegram_buyer.check_is_authorized())
                except Exception as e:
                    return self.send_json({
                        "status": "userbot_not_authorized",
                        "message": f"Userbot chưa đăng nhập hoặc lỗi Telethon: {e}",
                        "available": 0
                    }, 200)

                if not is_auth:
                    return self.send_json({
                        "status": "userbot_not_authorized",
                        "message": "Userbot chưa đăng nhập! Vào /admin đăng nhập OTP trước.",
                        "available": 0
                    }, 200)

                # Gọi bot mua link (trừ ví bot @shopxoainon_bot ~12.800đ)
                try:
                    buy_res = asyncio.run(telegram_buyer.execute_buy_gemini())
                except Exception as e:
                    return self.send_json({
                        "status": "error",
                        "message": f"Lỗi gọi bot mua link: {e}",
                        "available": 0
                    }, 500)

                buy_status = buy_res.get("status") or "error"

                # Bot giao link ngay -> nạp vào kho rồi cấp cho khách
                if buy_status == "success" and buy_res.get("license_link"):
                    link = str(buy_res["license_link"]).strip()
                    with LICENSE_LOCK:
                        items = read_licenses()
                        new_item = {
                            "id": next_license_id(items),
                            "link": link,
                            "status": "Đã cấp",
                            "assignedTo": f"{name} ({order_id})" if order_id else name
                        }
                        items.append(new_item)
                        if not write_json_file(LICENSES_FILE, items):
                            return self.send_json({"status": "error", "message": "Đã mua link nhưng không lưu được kho"}, 500)
                        return self.send_json({
                            "status": "success", "source": "auto_buy",
                            "license": new_item, "licenseLink": link,
                            "available": license_stock_count(items)
                        })

                # Các trạng thái lỗi từ bot: trả đúng status để frontend hiện fallback
                status_map = {
                    "out_of_stock_in_bot": "out_of_stock_in_bot",
                    "insufficient_balance": "insufficient_balance",
                    "insufficient_balance_or_no_button": "insufficient_balance",
                    "pending_delivery": "pending_delivery",
                }
                mapped = status_map.get(buy_status, "error")
                return self.send_json({
                    "status": mapped,
                    "message": buy_res.get("message") or "Không lấy được link từ bot",
                    "available": 0
                }, 200)
            finally:
                AUTOBUY_LOCK.release()

        # 0.2 API: Cấp lại một link cụ thể cho đơn hàng
        if path == "/api/licenses/reissue":
            try:
                item_id = int(body.get("id"))
            except (TypeError, ValueError):
                item_id = None
            name = str(body.get("name") or "Khách hàng").strip()[:120]
            order_id = str(body.get("orderId") or "").strip()[:80]
            with LICENSE_LOCK:
                items = read_licenses()
                selected = next((item for item in items if item.get("id") == item_id and item.get("status") == "Sẵn sàng"), None)
                if not selected:
                    return self.send_json({"status": "out_of_stock", "message": "Không tìm thấy license sẵn sàng"}, 409)
                selected["status"] = "Đã cấp"
                selected["assignedTo"] = f"{name} ({order_id})" if order_id else name
                if not write_json_file(LICENSES_FILE, items):
                    return self.send_json({"status": "error", "message": "Không thể cập nhật kho license"}, 500)
                return self.send_json({"status": "success", "license": selected, "licenseLink": selected["link"], "available": license_stock_count(items)})

        # 0.3 API: Validate số điện thoại trước khi gọi Telegram
        if path == "/api/tele-buyer/request-otp":
            phone = str(body.get("phone") or "").strip()
            digits = phone.replace("+", "").replace(" ", "").replace("-", "")
            if not digits.isdigit() or len(digits) < 9 or len(digits) > 15:
                return self.send_json({"status": "error", "message": "Vui lòng nhập số điện thoại Telegram hợp lệ"}, 400)
            try:
                import telegram_buyer
                res = asyncio.run(telegram_buyer.request_otp(phone))
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 1. API: Lưu cấu hình cổng thanh toán
        if path == "/api/payment-config":
            write_json_file("payment_config.json", body)
            return self.send_json({"status": "success", "message": "Payment config saved"})

        # 2. API: Nhận hoặc xóa biến động số dư
        if path == "/api/bank-transactions":
            write_json_file("bank_transactions.json", [])
            return self.send_json({"status": "success", "message": "Transactions cleared"})

        # 3. API: Lưu đơn hàng mới / Xóa đơn & Tự động bắn thông báo Telegram
        if path == "/api/orders":
            action = str(body.get("action") or "").strip().lower()
            if action == "delete":
                del_id = str(body.get("orderId") or "").strip()
                orders = read_json_file("orders.json", [])
                orders = [o for o in orders if o.get("orderId") != del_id]
                write_json_file("orders.json", orders)
                return self.send_json({"status": "success", "orders": orders})

            if action == "clear":
                write_json_file("orders.json", [])
                return self.send_json({"status": "success", "orders": []})

            orders = read_json_file("orders.json", [])
            order_id = body.get("orderId", f"#GEM-{int(datetime.now().timestamp()) % 10000:04d}")
            body["orderId"] = order_id
            
            # Tự động làm giàu IP, Location, Device từ HTTP Headers nếu client thiếu
            client_ip = self.headers.get("X-Forwarded-For")
            if client_ip:
                client_ip = client_ip.split(",")[0].strip()
            else:
                client_ip = self.client_address[0]

            if not body.get("ip") or body.get("ip") in ["127.0.0.1", "::1"]:
                if client_ip and client_ip not in ["127.0.0.1", "::1"]:
                    body["ip"] = client_ip

            if not body.get("location") or body.get("location") == "Việt Nam":
                # Nếu đã có IP thật từ ngoài mạng, có thể đối soát
                if body.get("ip") and body.get("ip") not in ["127.0.0.1", "::1"]:
                    pass

            if not body.get("device"):
                ua = self.headers.get("User-Agent", "")
                body["device"] = "Điện thoại" if ("Mobile" in ua or "Android" in ua or "iPhone" in ua) else "Máy tính PC"
            
            # Cập nhật nếu trùng mã đơn, ngược lại thêm mới
            existing_order = None
            found = False
            for i, o in enumerate(orders):
                if o.get("orderId") == order_id:
                    existing_order = o
                    # Giữ lại các cờ thông báo nếu đã gửi
                    if o.get("qrNotified"):
                        body["qrNotified"] = True
                    if o.get("paidNotified"):
                        body["paidNotified"] = True
                    orders[i] = body
                    found = True
                    break
            if not found:
                orders.insert(0, body)
            if len(orders) > 500:
                orders = orders[:500]

            status_str = (body.get("status") or "").lower()

            # Bắn Telegram khi thanh toán thành công (kể cả khi có link hoặc chờ cấp link)
            is_paid = ("đã thanh toán" in status_str or "thành công" in status_str or "paid" in status_str) and ("chờ thanh toán" not in status_str)
            send_paid_flag = False
            if is_paid and not body.get("paidNotified"):
                body["paidNotified"] = True
                send_paid_flag = True

            def _bg_notify(order_data):
                try:
                    import telegram_sender
                    telegram_sender.send_telegram_raw(telegram_sender.get_payment_success_template(order_data))
                except Exception as e:
                    sys.stderr.write(f"Telegram paid notify error: {e}\n")

                # Đồng bộ Google Sheet qua Webhook
                try:
                    cfg = read_json_file("payment_config.json", {})
                    webhook = cfg.get("googleSheetWebhookUrl")
                    if webhook and "SAMPLE" not in webhook:
                        req_data = json.dumps({
                            "action": "new_order",
                            "time": order_data.get("time") or datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            "orderId": order_data.get("orderId"),
                            "product": order_data.get("package") or "Google Gemini Pro 18 Tháng",
                            "amount": order_data.get("amount") or "90.000 VNĐ",
                            "name": order_data.get("name") or "Khách hàng",
                            "phone": order_data.get("phone") or "",
                            "email": order_data.get("email") or "",
                            "memo": order_data.get("memo") or f"PRO18T {order_data.get('phone', '')}",
                            "licenseLink": order_data.get("licenseLink") or "",
                            "referrer": order_data.get("referrer") or "Trực tiếp",
                            "ipLocation": f"{order_data.get('ip', '127.0.0.1')} ({order_data.get('location', 'VN')})",
                            "status": order_data.get("status") or "Đã thanh toán (MBBank)"
                        }).encode("utf-8")
                        req = urllib.request.Request(webhook, data=req_data, headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=8)
                except Exception as e:
                    sys.stderr.write(f"Google Sheet webhook error: {e}\n")

            if send_paid_flag:
                threading.Thread(target=_bg_notify, args=(dict(body),), daemon=True).start()

            write_json_file("orders.json", orders)
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
            orders = read_json_file("orders.json", [])
            orders_updated = False

            for it in items:
                amt = int(it.get("amount") or 0)
                desc = it.get("description") or it.get("memo") or it.get("content") or ""
                if amt > 0:
                    tx_record = {
                        "id": str(it.get("id") or f"TX_{int(datetime.now().timestamp()) % 1000000:06d}"),
                        "amount": amt,
                        "description": desc,
                        "bank": it.get("bank") or "MBBank",
                        "time": it.get("time") or it.get("transactionDateTime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "Webhook API Pay"
                    }
                    current_txs.insert(0, tx_record)

                    # Tự động khớp với đơn hàng đang chờ thanh toán
                    clean_desc = desc.upper().replace(" ", "")
                    for order in orders:
                        st = (order.get("status") or "").lower()
                        if "chờ thanh toán" in st and not order.get("paidNotified"):
                            phone = (order.get("phone") or "").replace("+84", "0").replace(" ", "")
                            memo = (order.get("memo") or f"PRO18T {phone}").upper().replace(" ", "")
                            if (phone and phone in clean_desc) or (memo and memo in clean_desc):
                                order["paymentTxId"] = tx_record["id"]
                                order["paymentSource"] = "APIPay Webhook"
                                # Cấp license
                                with LICENSE_LOCK:
                                    lics = read_licenses()
                                    free_lic = next((l for l in lics if l.get("status") == "Sẵn sàng"), None)
                                    if free_lic:
                                        free_lic["status"] = "Đã cấp"
                                        free_lic["assignedTo"] = f"{order.get('name')} ({order.get('orderId')})"
                                        write_json_file(LICENSES_FILE, lics)
                                        order["licenseLink"] = free_lic.get("link", "")
                                        order["status"] = "Đã thanh toán (MBBank)"
                                    else:
                                        order["licenseLink"] = ""
                                        order["status"] = "Đã thanh toán (Chờ cấp link)"

                                # Bắn Telegram báo đơn hàng đã thanh toán thành công
                                try:
                                    import telegram_sender
                                    order["paidNotified"] = True
                                    telegram_sender.send_telegram_raw(telegram_sender.get_payment_success_template(order))
                                except:
                                    pass
                                orders_updated = True
                                break

            write_json_file("bank_transactions.json", current_txs[:150])
            if orders_updated:
                write_json_file("orders.json", orders)
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
