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
PIXEL_FILE = "pixel_stats.json"
PIXEL_LOCK = threading.Lock()
DEFAULT_PIXEL_ID = "762402019586629"
COUPONS_FILE = "coupons.json"
COUPONS_LOCK = threading.Lock()
VISITS_FILE = "visits.json"
VISITS_LOCK = threading.Lock()

def get_current_package_price():
    cfg = read_json_file("payment_config.json", {})
    try:
        p = int(cfg.get("packagePrice") or 90000)
        return p if p > 0 else 90000
    except Exception:
        return 90000

def calculate_coupon_discount(coupon, base_price=None):
    if base_price is None or base_price <= 0:
        base_price = get_current_package_price()
    dtype = coupon.get("discountType", "fixed")
    final_price = base_price
    discount_amount = 0

    if coupon.get("finalPrice") and int(coupon.get("finalPrice")) > 0:
        final_price = int(coupon.get("finalPrice"))
        discount_amount = max(0, base_price - final_price)
    elif dtype == "percent":
        pct = float(coupon.get("discountValue") or 0)
        discount_amount = int(base_price * (pct / 100))
        final_price = max(1000, base_price - discount_amount)
    else:
        discount_amount = int(coupon.get("discountValue") or coupon.get("discountAmount") or 0)
        final_price = max(1000, base_price - discount_amount)

    return discount_amount, final_price

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

        # 1.1 API: Cấu hình Meta Pixel (Facebook Ads)
        if path == "/api/pixel-config":
            with PIXEL_LOCK:
                pixel_data = read_json_file(PIXEL_FILE, {})
                pixel_id = pixel_data.get("pixelId") or DEFAULT_PIXEL_ID
                enabled = pixel_data.get("enabled", True)
            return self.send_json({"status": "success", "pixelId": pixel_id, "enabled": enabled})

        # 1.2 API: Thống kê & sự kiện Meta Pixel thời gian thực
        if path == "/api/pixel-stats":
            with PIXEL_LOCK:
                pixel_data = read_json_file(PIXEL_FILE, {
                    "pixelId": DEFAULT_PIXEL_ID,
                    "enabled": True,
                    "stats": {"PageView": 158, "ViewContent": 142, "Lead": 46, "InitiateCheckout": 39, "Purchase": 24, "totalEvents": 409},
                    "recentEvents": []
                })
                if not pixel_data.get("pixelId"):
                    pixel_data["pixelId"] = DEFAULT_PIXEL_ID
                stats = pixel_data.get("stats", {})
                stats["totalEvents"] = sum(stats.get(k, 0) for k in ["PageView", "ViewContent", "Lead", "InitiateCheckout", "Purchase"])
                pixel_data["stats"] = stats
            return self.send_json(pixel_data)

        # 2. API: Lấy biến động số dư ngân hàng
        if path == "/api/bank-transactions":
            txs = read_json_file("bank_transactions.json", [])
            return self.send_json(txs)

        # 3. API: Lấy danh sách đơn hàng
        if path == "/api/orders":
            orders = read_json_file("orders.json", [])
            return self.send_json(orders)

        # 3.01 API: Lấy thống kê lượt truy cập toàn hệ thống (Real-time Central Visits)
        if path == "/api/visits":
            with VISITS_LOCK:
                default_data = {
                    "totalVisits": 0,
                    "todayVisits": 0,
                    "lastDate": datetime.now().strftime("%d/%m/%Y"),
                    "devices": {"mobile": 0, "desktop": 0, "other": 0},
                    "sources": {"facebook": 0, "tiktok": 0, "google": 0, "zalo": 0, "direct": 0, "other": 0},
                    "visits": []
                }
                visits_data = read_json_file(VISITS_FILE, default_data)
                today_str = datetime.now().strftime("%d/%m/%Y")
                if visits_data.get("lastDate") != today_str:
                    visits_data["lastDate"] = today_str
                    visits_data["todayVisits"] = 0
            return self.send_json(visits_data)

        # 3.0 API: Lấy danh sách mã khuyến mãi hoặc kiểm tra mã
        if path == "/api/coupons":
            with COUPONS_LOCK:
                coupons = read_json_file(COUPONS_FILE, [])
            return self.send_json(coupons)

        if path == "/api/coupons/check":
            code = (query.get("code", [""])[0] or "").strip().upper()
            with COUPONS_LOCK:
                coupons = read_json_file(COUPONS_FILE, [])
            found = next((c for c in coupons if (c.get("code") or "").upper() == code), None)
            if not found:
                return self.send_json({"valid": False, "message": f"Mã voucher '{code}' không tồn tại!"})
            if not found.get("active", True):
                return self.send_json({"valid": False, "message": f"Mã voucher '{code}' hiện đang tạm khóa!"})
            max_uses = int(found.get("maxUses") or 0)
            used_count = int(found.get("usedCount") or 0)
            if max_uses > 0 and used_count >= max_uses:
                return self.send_json({"valid": False, "message": f"Mã voucher '{code}' đã hết lượt sử dụng ({used_count}/{max_uses})!"})

            base_price = get_current_package_price()
            discount_amount, final_price = calculate_coupon_discount(found, base_price)
            return self.send_json({
                "valid": True,
                "code": found.get("code"),
                "discountAmount": discount_amount,
                "finalPrice": final_price,
                "originalPrice": base_price,
                "maxUses": max_uses,
                "usedCount": used_count,
                "remainingUses": max_uses - used_count if max_uses > 0 else 9999,
                "description": found.get("description", ""),
                "message": f"Áp dụng thành công mã {found.get('code')}! Giảm {discount_amount:,}đ còn {final_price:,}đ."
            })

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
            order_id = query.get("orderId", [""])[0]
            public_id = query.get("publicId", [""])[0]
            clean_phone = phone.replace("+84", "0").replace(" ", "") if phone else ""
            clean_memo = memo.replace(" ", "").upper() if memo else ""

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

            # 4.2 Kiểm tra danh sách Payment Requests gần nhất trên ApiPay Cloud bằng phone / memo
            if clean_phone or clean_memo:
                try:
                    import apipay_bridge
                    res = apipay_bridge.check_recent_payment_requests(memo, phone)
                    if res.get("paid"):
                        return self.send_json({
                            "paid": True,
                            "message": "Payment verified via APIPay Cloud Recent",
                            "transaction": res.get("transaction"),
                            "source": "APIPay Cloud Recent"
                        })
                except Exception as e:
                    pass

            # 4.3 Kiểm tra đối soát trong nhật ký giao dịch ngân hàng
            txs = read_json_file("bank_transactions.json", [])
            for tx in txs:
                desc = (tx.get("description") or tx.get("memo") or "").upper().replace(" ", "")
                if (clean_phone and clean_phone in desc) or (clean_memo and clean_memo in desc):
                    return self.send_json({
                        "paid": True,
                        "message": "Payment verified via Live Bank Feed",
                        "transaction": tx,
                        "source": tx.get("source", "Live Bank Stream")
                    })

            # 4.4 Kiểm tra trong orders.json (trường hợp Admin duyệt thủ công hoặc đơn đã kích hoạt)
            orders = read_json_file("orders.json", [])
            for order in orders:
                st = (order.get("status") or "").lower()
                is_paid = "đã thanh toán" in st or "da thanh toan" in st or "thành công" in st or "thanh cong" in st
                if is_paid:
                    o_id = (order.get("orderId") or "").strip()
                    o_phone = (order.get("phone") or "").replace("+84", "0").replace(" ", "")
                    o_memo = (order.get("memo") or "").replace(" ", "").upper()
                    if (order_id and order_id == o_id) or (clean_phone and clean_phone == o_phone) or (clean_memo and clean_memo == o_memo):
                        return self.send_json({
                            "paid": True,
                            "message": "Payment verified via Order Database",
                            "transaction": order,
                            "source": "Order Database"
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

        # 1. API: Lưu cấu hình cổng thanh toán & giá bán gói
        if path == "/api/payment-config":
            current_cfg = read_json_file("payment_config.json", {})
            current_cfg.update(body)
            write_json_file("payment_config.json", current_cfg)
            return self.send_json({"status": "success", "message": "Payment and pricing config saved", "config": current_cfg})

        # 1.1 API: Lưu cấu hình Meta Pixel (ID: 762402019586629)
        if path == "/api/pixel-config":
            new_id = body.get("pixelId")
            enabled = body.get("enabled")
            with PIXEL_LOCK:
                pixel_data = read_json_file(PIXEL_FILE, {
                    "pixelId": DEFAULT_PIXEL_ID,
                    "enabled": True,
                    "stats": {"PageView": 0, "ViewContent": 0, "Lead": 0, "InitiateCheckout": 0, "Purchase": 0},
                    "recentEvents": []
                })
                if new_id:
                    pixel_data["pixelId"] = str(new_id).strip()
                if enabled is not None:
                    pixel_data["enabled"] = bool(enabled)
                write_json_file(PIXEL_FILE, pixel_data)
            cfg = read_json_file("payment_config.json", {})
            if new_id:
                cfg["pixelId"] = str(new_id).strip()
            if enabled is not None:
                cfg["pixelEnabled"] = bool(enabled)
            write_json_file("payment_config.json", cfg)
            return self.send_json({"status": "success", "pixelId": pixel_data.get("pixelId"), "enabled": pixel_data.get("enabled")})

        # 1.2 API: Ghi nhận sự kiện Meta Pixel thời gian thực (PageView, ViewContent, Lead, InitiateCheckout, Purchase)
        if path == "/api/pixel-event":
            ev = body.get("event") or "PageView"
            with PIXEL_LOCK:
                pixel_data = read_json_file(PIXEL_FILE, {
                    "pixelId": DEFAULT_PIXEL_ID,
                    "enabled": True,
                    "stats": {"PageView": 0, "ViewContent": 0, "Lead": 0, "InitiateCheckout": 0, "Purchase": 0},
                    "recentEvents": []
                })
                stats = pixel_data.get("stats", {})
                stats[ev] = stats.get(ev, 0) + 1
                stats["totalEvents"] = sum(stats.get(k, 0) for k in ["PageView", "ViewContent", "Lead", "InitiateCheckout", "Purchase"])
                pixel_data["stats"] = stats
                pixel_data["pixelId"] = body.get("pixelId") or pixel_data.get("pixelId") or DEFAULT_PIXEL_ID
                pixel_data["updatedAt"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                recent = pixel_data.get("recentEvents", [])
                event_record = {
                    "event": ev,
                    "time": body.get("time") or datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "url": body.get("url") or "",
                    "fbclid": body.get("fbclid") or "",
                    "utmSource": body.get("utmSource") or "",
                    "utmCampaign": body.get("utmCampaign") or "",
                    "params": body.get("params") or {}
                }
                recent.insert(0, event_record)
                pixel_data["recentEvents"] = recent[:100]
                write_json_file(PIXEL_FILE, pixel_data)
            return self.send_json({"status": "success", "event": ev, "count": pixel_data["stats"].get(ev, 0)})

        # 1.3 API: Ghi nhận lượt truy cập tập trung từ mọi thiết bị & IP
        if path == "/api/track-visit":
            with VISITS_LOCK:
                default_data = {
                    "totalVisits": 0,
                    "todayVisits": 0,
                    "lastDate": datetime.now().strftime("%d/%m/%Y"),
                    "devices": {"mobile": 0, "desktop": 0, "other": 0},
                    "sources": {"facebook": 0, "tiktok": 0, "google": 0, "zalo": 0, "direct": 0, "other": 0},
                    "visits": []
                }
                visits_data = read_json_file(VISITS_FILE, default_data)
                
                today_str = datetime.now().strftime("%d/%m/%Y")
                if visits_data.get("lastDate") != today_str:
                    visits_data["lastDate"] = today_str
                    visits_data["todayVisits"] = 0

                visits_data["totalVisits"] = int(visits_data.get("totalVisits", 0)) + 1
                visits_data["todayVisits"] = int(visits_data.get("todayVisits", 0)) + 1

                # Trích xuất IP thật từ proxy hoặc header
                client_ip = self.headers.get("X-Forwarded-For")
                if client_ip:
                    client_ip = client_ip.split(",")[0].strip()
                else:
                    client_ip = self.client_address[0]
                
                ip = body.get("ip") or client_ip or "127.0.0.1"
                if ip in ["127.0.0.1", "::1"] and client_ip and client_ip not in ["127.0.0.1", "::1"]:
                    ip = client_ip

                # Trích xuất thiết bị
                ua = self.headers.get("User-Agent", "")
                device = body.get("device")
                if not device:
                    if any(k in ua for k in ["Mobile", "Android", "iPhone", "iPad"]):
                        device = "Điện thoại"
                    else:
                        device = "Máy tính"

                devices = visits_data.setdefault("devices", {"mobile": 0, "desktop": 0, "other": 0})
                if "Mobile" in device or "Điện thoại" in device:
                    devices["mobile"] = devices.get("mobile", 0) + 1
                elif "Máy tính" in device or "PC" in device:
                    devices["desktop"] = devices.get("desktop", 0) + 1
                else:
                    devices["other"] = devices.get("other", 0) + 1

                # Phân loại nguồn
                ref = (body.get("referrer") or body.get("rawReferrer") or "").lower()
                full_url = (body.get("fullUrl") or "").lower()
                sources = visits_data.setdefault("sources", {"facebook": 0, "tiktok": 0, "google": 0, "zalo": 0, "direct": 0, "other": 0})
                
                if "facebook" in ref or "fb" in ref or "fbclid" in full_url:
                    sources["facebook"] = sources.get("facebook", 0) + 1
                    ref_label = "Facebook Ads" if ("fbclid" in full_url or "ads" in ref) else "Facebook"
                elif "tiktok" in ref or "ttclid" in full_url:
                    sources["tiktok"] = sources.get("tiktok", 0) + 1
                    ref_label = "TikTok Ads" if "ttclid" in full_url else "TikTok"
                elif "google" in ref or "search" in ref or "gclid" in full_url:
                    sources["google"] = sources.get("google", 0) + 1
                    ref_label = "Google Search"
                elif "zalo" in ref:
                    sources["zalo"] = sources.get("zalo", 0) + 1
                    ref_label = "Zalo Chat"
                elif not ref or "trực tiếp" in ref or "direct" in ref:
                    sources["direct"] = sources.get("direct", 0) + 1
                    ref_label = "Truy cập trực tiếp"
                else:
                    sources["other"] = sources.get("other", 0) + 1
                    ref_label = body.get("referrer") or "Khác"

                # Trích xuất và phân loại Tên Miền (Multi-Domain Tracking)
                domain = str(body.get("domain") or "").strip().lower()
                full_url_str = body.get("fullUrl") or ""
                if not domain and full_url_str:
                    try:
                        p_dom = urllib.parse.urlparse(full_url_str)
                        domain = (p_dom.hostname or p_dom.netloc or "").strip().lower()
                    except Exception:
                        domain = ""
                if not domain:
                    host_hdr = self.headers.get("Host", "")
                    domain = host_hdr.split(":")[0].strip().lower() if host_hdr else ""
                if not domain:
                    domain = "Khác"

                domains_map = visits_data.setdefault("domains", {})
                domains_map[domain] = domains_map.get(domain, 0) + 1

                visit_entry = {
                    "time": body.get("time") or datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
                    "ip": ip,
                    "location": body.get("location") or "Việt Nam",
                    "device": device,
                    "browser": body.get("browser") or "Trình duyệt Web",
                    "domain": domain,
                    "referrer": ref_label,
                    "fullUrl": full_url_str,
                    "rawReferrer": body.get("rawReferrer") or ""
                }

                visits_list = visits_data.setdefault("visits", [])
                visits_list.insert(0, visit_entry)
                if len(visits_list) > 1000:
                    visits_data["visits"] = visits_list[:1000]

                write_json_file(VISITS_FILE, visits_data)
            return self.send_json({
                "status": "success",
                "totalVisits": visits_data["totalVisits"],
                "todayVisits": visits_data["todayVisits"],
                "clientIp": ip
            })

        # 1.4 API: Xóa lịch sử lượt truy cập
        if path == "/api/visits":
            action = str(body.get("action") or "").strip().lower()
            if action == "clear":
                with VISITS_LOCK:
                    empty_data = {
                        "totalVisits": 0,
                        "todayVisits": 0,
                        "lastDate": datetime.now().strftime("%d/%m/%Y"),
                        "devices": {"mobile": 0, "desktop": 0, "other": 0},
                        "sources": {"facebook": 0, "tiktok": 0, "google": 0, "zalo": 0, "direct": 0, "other": 0},
                        "visits": []
                    }
                    write_json_file(VISITS_FILE, empty_data)
                return self.send_json({"status": "success", "message": "Visits cleared"})

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
            if not body.get("ip"):
                body["ip"] = client_ip or "127.0.0.1"
            body["buyerIp"] = body.get("ip")

            if not body.get("location") or body.get("location") == "Việt Nam":
                # Nếu đã có IP thật từ ngoài mạng, có thể đối soát
                if body.get("ip") and body.get("ip") not in ["127.0.0.1", "::1"]:
                    pass

            if not body.get("device"):
                ua = self.headers.get("User-Agent", "")
                body["device"] = "Điện thoại" if ("Mobile" in ua or "Android" in ua or "iPhone" in ua) else "Máy tính PC"
            
            # Tự động trích xuất Tên Miền Đặt Hàng (Domain Tracking)
            order_domain = str(body.get("domain") or "").strip().lower()
            if not order_domain and body.get("fullUrl"):
                try:
                    p_ord = urllib.parse.urlparse(body["fullUrl"])
                    order_domain = (p_ord.hostname or p_ord.netloc or "").strip().lower()
                except Exception:
                    order_domain = ""
            if not order_domain:
                host_hdr = self.headers.get("Host", "")
                order_domain = host_hdr.split(":")[0].strip().lower() if host_hdr else ""
            if not order_domain:
                order_domain = "geminigiare.io.vn"
            body["domain"] = order_domain

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
                    if o.get("couponCounted"):
                        body["couponCounted"] = True
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

                # Tăng số lượt dùng voucher khi KHÁCH ĐÃ THANH TOÁN THÀNH CÔNG
                if body.get("couponCode") and not body.get("couponCounted"):
                    body["couponCounted"] = True
                    c_code = (body.get("couponCode") or "").strip().upper()
                    with COUPONS_LOCK:
                        coupons = read_json_file(COUPONS_FILE, [])
                        for c in coupons:
                            if (c.get("code") or "").upper() == c_code:
                                c["usedCount"] = int(c.get("usedCount") or 0) + 1
                                break
                        write_json_file(COUPONS_FILE, coupons)

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
                            "domain": order_data.get("domain") or "",
                            "time": order_data.get("time") or datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            "orderId": order_data.get("orderId"),
                            "product": order_data.get("package") or "Google Gemini Pro 18 Tháng",
                            "amount": order_data.get("amount") or "90.000 VNĐ",
                            "name": order_data.get("name") or "Khách hàng",
                            "phone": order_data.get("phone") or "",
                            "email": order_data.get("email") or "",
                            "memo": order_data.get("memo") or f"PRO18T {order_data.get('phone', '')}",
                            "licenseLink": order_data.get("licenseLink") or "",
                            "referrer": f"{order_data.get('referrer', 'Trực tiếp')} | {order_data.get('fullUrl', '')}".strip(" |"),
                            "adLink": order_data.get("fullUrl") or "",
                            "adCampaign": order_data.get("utmCampaign") or "",
                            "fbclid": order_data.get("fbclid") or "",
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
            import re
            sys.stdout.write(f"[WEBHOOK INCOMING] Payload: {json.dumps(body, ensure_ascii=False)[:300]}\n")
            sys.stdout.flush()

            items = []
            if isinstance(body.get("data"), list):
                items = body.get("data")
            elif isinstance(body.get("data"), dict) and body.get("data"):
                items = [body.get("data")]
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
                # Trích xuất số tiền an toàn (hỗ trợ cả int, float, string "90000", "90.000đ")
                raw_amt = it.get("amount") or it.get("transferAmount") or it.get("creditAmount") or 0
                try:
                    if isinstance(raw_amt, str):
                        clean_amt_str = re.sub(r"[^\d]", "", raw_amt)
                        amt = int(clean_amt_str) if clean_amt_str else 0
                    else:
                        amt = int(raw_amt)
                except Exception:
                    amt = 0

                desc = str(it.get("content") or it.get("description") or it.get("memo") or it.get("comment") or "").strip()
                status_raw = str(it.get("status") or "").upper()
                public_id = str(it.get("publicId") or "").strip()

                # Kiểm tra giao dịch hợp lệ
                is_valid_tx = (amt > 0) or (status_raw in ["PAID", "COMPLETED", "SUCCESS"]) or ("PRO18T" in desc.upper())

                if is_valid_tx:
                    pkg_price = get_current_package_price()
                    actual_amt = amt if amt > 0 else pkg_price
                    tx_record = {
                        "id": str(it.get("id") or it.get("publicId") or f"TX_{int(datetime.now().timestamp()) % 1000000:06d}"),
                        "amount": actual_amt,
                        "description": desc or f"PRO18T (APIPay {public_id})",
                        "bank": it.get("bank") or it.get("bankCode") or "MBBank",
                        "time": it.get("time") or it.get("transactionDateTime") or it.get("createdAt") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "APIPay Webhook"
                    }
                    current_txs.insert(0, tx_record)

                    # Tự động khớp với đơn hàng đang chờ thanh toán
                    clean_desc = (desc or "").upper().replace(" ", "")
                    matched_order = None
                    for order in orders:
                        st = (order.get("status") or "").lower()
                        if "chờ thanh toán" in st and not order.get("paidNotified"):
                            phone = (order.get("phone") or "").replace("+84", "0").replace(" ", "")
                            memo = (order.get("memo") or f"PRO18T {phone}").upper().replace(" ", "")
                            o_pub = (order.get("apipayPublicId") or "").strip()
                            if (public_id and public_id == o_pub) or (phone and phone in clean_desc) or (memo and memo in clean_desc):
                                matched_order = order
                                break

                    if matched_order:
                        matched_order["paymentTxId"] = tx_record["id"]
                        matched_order["paymentSource"] = "APIPay Webhook"
                        # Cấp license
                        with LICENSE_LOCK:
                            lics = read_licenses()
                            free_lic = next((l for l in lics if l.get("status") == "Sẵn sàng"), None)
                            if free_lic:
                                free_lic["status"] = "Đã cấp"
                                free_lic["assignedTo"] = f"{matched_order.get('name')} ({matched_order.get('orderId')})"
                                write_json_file(LICENSES_FILE, lics)
                                matched_order["licenseLink"] = free_lic.get("link", "")
                                matched_order["status"] = "Đã thanh toán (MBBank)"
                            else:
                                matched_order["licenseLink"] = ""
                                matched_order["status"] = "Đã thanh toán (Chờ cấp link)"

                        # Tăng số lượt dùng voucher khi webhook nhận tiền thành công
                        if matched_order.get("couponCode") and not matched_order.get("couponCounted"):
                            matched_order["couponCounted"] = True
                            c_code = (matched_order.get("couponCode") or "").strip().upper()
                            with COUPONS_LOCK:
                                coupons = read_json_file(COUPONS_FILE, [])
                                for c in coupons:
                                    if (c.get("code") or "").upper() == c_code:
                                        c["usedCount"] = int(c.get("usedCount") or 0) + 1
                                        break
                                write_json_file(COUPONS_FILE, coupons)

                        # Bắn Telegram báo đơn hàng đã thanh toán thành công
                        try:
                            import telegram_sender
                            matched_order["paidNotified"] = True
                            telegram_sender.send_telegram_raw(telegram_sender.get_payment_success_template(matched_order))
                        except Exception as e:
                            sys.stderr.write(f"Telegram webhook notify error: {e}\n")
                        orders_updated = True

            write_json_file("bank_transactions.json", current_txs[:150])
            if orders_updated:
                write_json_file("orders.json", orders)
            return self.send_json({"status": "success", "message": "Webhook processed", "count": len(items)})

        # 4. API: Mô phỏng thanh toán (Simulate)
        if path == "/api/simulate-payment":
            phone = body.get("phone", "0901234567")
            memo = body.get("memo", f"PRO18T {phone}")
            amount = int(body.get("amount") or get_current_package_price())
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
                amount = int(body.get("amount") or get_current_package_price())
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

        # 12. API: Quản lý mã khuyến mãi (Thêm, Sửa, Xóa, Bật/Tắt)
        if path == "/api/coupons":
            action = str(body.get("action") or "").strip().lower()
            code = (body.get("code") or "").strip().upper()

            with COUPONS_LOCK:
                coupons = read_json_file(COUPONS_FILE, [])

                if action == "delete":
                    coupons = [c for c in coupons if (c.get("code") or "").upper() != code]
                    write_json_file(COUPONS_FILE, coupons)
                    return self.send_json({"status": "success", "message": f"Đã xóa mã {code}!", "coupons": coupons})

                if action == "toggle":
                    for c in coupons:
                        if (c.get("code") or "").upper() == code:
                            c["active"] = not c.get("active", True)
                            break
                    write_json_file(COUPONS_FILE, coupons)
                    return self.send_json({"status": "success", "message": f"Đã cập nhật trạng thái mã {code}!", "coupons": coupons})

                if action in ("add", "create", "save"):
                    if not code:
                        return self.send_json({"status": "error", "message": "Vui lòng nhập mã khuyến mãi!"}, 400)
                    existing = next((c for c in coupons if (c.get("code") or "").upper() == code), None)
                    final_price = int(body.get("finalPrice") or 0)
                    discount_val = int(body.get("discountValue") or 0)
                    discount_type = body.get("discountType") or "fixed"

                    coupon_data = {
                        "code": code,
                        "discountType": discount_type,
                        "discountValue": discount_val,
                        "finalPrice": final_price,
                        "maxUses": int(body.get("maxUses") or 0),
                        "usedCount": int(existing.get("usedCount", 0) if existing else 0),
                        "active": bool(body.get("active", True)),
                        "description": str(body.get("description") or ""),
                        "createdAt": existing.get("createdAt") if existing else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    if existing:
                        coupons = [coupon_data if (c.get("code") or "").upper() == code else c for c in coupons]
                    else:
                        coupons.insert(0, coupon_data)

                    write_json_file(COUPONS_FILE, coupons)
                    return self.send_json({"status": "success", "message": f"Đã lưu thành công mã {code}!", "coupons": coupons})

            return self.send_json({"status": "error", "message": "Hành động không hợp lệ"}, 400)

        # 13. API: Áp dụng mã khuyến mãi qua POST
        if path == "/api/coupons/apply":
            code = (body.get("code") or "").strip().upper()
            with COUPONS_LOCK:
                coupons = read_json_file(COUPONS_FILE, [])
            found = next((c for c in coupons if (c.get("code") or "").upper() == code), None)
            if not found:
                return self.send_json({"valid": False, "message": f"Mã voucher '{code}' không tồn tại!"})
            if not found.get("active", True):
                return self.send_json({"valid": False, "message": f"Mã voucher '{code}' hiện đang tạm khóa!"})
            max_uses = int(found.get("maxUses") or 0)
            used_count = int(found.get("usedCount") or 0)
            if max_uses > 0 and used_count >= max_uses:
                return self.send_json({"valid": False, "message": f"Mã voucher '{code}' đã hết lượt sử dụng ({used_count}/{max_uses})!"})

            base_price = get_current_package_price()
            discount_amount, final_price = calculate_coupon_discount(found, base_price)
            return self.send_json({
                "valid": True,
                "code": found.get("code"),
                "discountAmount": discount_amount,
                "finalPrice": final_price,
                "originalPrice": base_price,
                "maxUses": max_uses,
                "usedCount": used_count,
                "remainingUses": max_uses - used_count if max_uses > 0 else 9999,
                "description": found.get("description", ""),
                "message": f"Áp dụng thành công mã {found.get('code')}! Giảm {discount_amount:,}đ còn {final_price:,}đ."
            })

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
