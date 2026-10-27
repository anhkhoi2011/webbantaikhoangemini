from runtime_config import with_runtime_secrets, separate_runtime_secrets
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
import secrets
import hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import re

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
ORDER_LOCK = threading.RLock()
SYNC_LOCK = threading.Lock()
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
VISIT_SYNC_LOCK = threading.Lock()
VISIT_SYNC_EVENT = threading.Event()
ADMIN_TOKENS = {}
ADMIN_TOKEN_TTL = 8 * 60 * 60
ADMIN_LOGIN_EVENTS = {}
ADMIN_LOGIN_EVENTS_LOCK = threading.Lock()
ADMIN_LOGIN_EVENT_TTL = 10 * 60
DEFAULT_ADMIN_HASH = "c5bc82fc5c9d4553a39af5ea2f18257e2ba60b2822fdf93725abcd4451c0bada"

def allowed_origins():
    raw = os.environ.get("ALLOWED_ORIGINS", "https://geminigiare.io.vn,https://www.geminigiare.io.vn,https://webbantaikhoangemini.n2.tinhgon.xyz")
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}

def _admin_hash():
    return os.environ.get("ADMIN_PASSWORD_HASH", DEFAULT_ADMIN_HASH)

def _admin_authorized(handler):
    token = handler.headers.get("X-Admin-Token", "")
    now = datetime.now().timestamp()
    expires = ADMIN_TOKENS.get(token, 0)
    if expires > now:
        ADMIN_TOKENS[token] = now + ADMIN_TOKEN_TTL
        return True
    if token:
        ADMIN_TOKENS.pop(token, None)
    return False

def _requires_admin(path, method):
    if path in ("/api/admin-login", "/api/orders") and method == "POST":
        return path != "/api/orders"
    if path in ("/api/licenses", "/api/licenses/claim", "/api/licenses/auto-claim", "/api/licenses/reissue", "/api/visits", "/api/bank-transactions", "/api/payment-config", "/api/pixel-config", "/api/telegram-config", "/api/telegram-notify", "/api/admin-login-notify", "/api/send-email", "/api/simulate-payment", "/api/apipay-test", "/api/get-apps-script", "/api/tele-buyer/status", "/api/tele-buyer/request-otp", "/api/tele-buyer/submit-otp", "/api/tele-buyer/buy", "/api/coupons", "/api/coupons/apply"):
        return method != "GET" or path in ("/api/licenses", "/api/visits", "/api/bank-transactions")
        return True
    return False

def get_current_package_price():
    cfg = read_json_file("payment_config.json", {})
    try:
        p = int(cfg.get("packagePrice") or 129000)
        return p if p > 0 else 129000
    except Exception:
        return 129000

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

def parse_money(value, default=0):
    try:
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if re.fullmatch(r"-?\d+[.,]\d{1,2}", text):
            return int(float(text.replace(",", ".")))
        digits = ''.join(ch for ch in text if ch.isdigit())
        return (-1 if text.startswith("-") else 1) * int(digits) if digits else int(default)
    except (TypeError, ValueError):
        return int(default)

def read_json_file(filename, default):
    filepath = os.path.join(BASE_DIR, filename)
    result = default
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                result = json.load(f)
        except (OSError, ValueError):
            pass
    return with_runtime_secrets(filename, result, BASE_DIR)

def write_json_file(filename, data):
    filepath = os.path.join(BASE_DIR, filename)
    try:
        data = separate_runtime_secrets(filename, data, BASE_DIR)
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

def now_vn():
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")

def is_paid_order(order):
    return bool(re.search(r"đã thanh toán|da thanh toan|thành công|thanh cong|^(paid|completed|success)$", str(order.get("status") or ""), re.I))

def normalized_memo(value):
    return re.sub(r"\s+", "", str(value or "")).upper()

def payment_key(tx):
    if tx.get("paymentKey"):
        return tx["paymentKey"]
    reference = tx.get("bankReference") or tx.get("referenceCode") or tx.get("transactionReference") or ""
    amount = parse_money(tx.get("amount") or tx.get("creditAmount") or tx.get("transferAmount"), 0)
    content = normalized_memo(tx.get("description") or tx.get("content") or tx.get("memo") or tx.get("comment"))
    # Phone references recur. Use stable request/time data, never a delivery UUID.
    if not reference and re.search(r"PRO18T\d+$", content):
        reference = tx.get("publicId") or tx.get("transactionId") or tx.get("paidAt") or tx.get("completedAt") or tx.get("transactionDateTime") or tx.get("time") or tx.get("createdAt") or ""
    return hashlib.sha256(f"{reference}|{amount}|{content}".encode()).hexdigest()

def successful_tx(tx):
    simulated = str(tx.get("id") or "").startswith("SIM_") or any(word in str(tx.get("source") or "").lower() for word in ("simulat", "sandbox"))
    if simulated and read_json_file("payment_config.json", {}).get("testMode") is not True:
        return False
    status = str(tx.get("status") or "COMPLETED").upper()
    return status in {"PAID", "COMPLETED", "SUCCESS", "CREDIT"} and str(tx.get("transferType") or tx.get("direction") or "").lower() not in {"out", "debit"} and parse_money(tx.get("amount") or tx.get("transferAmount") or tx.get("creditAmount"), 0) > 0

# Source fields describe the visit that created the order, including empty UTM values.
# Retries may enrich IP/location but must never replace the original visit with another one.
ORDER_TRACKING_FIELDS = (
    "fullUrl", "domain", "referrer", "rawReferrer", "utmSource", "utmMedium",
    "utmCampaign", "utmContent", "utmTerm", "fbclid", "gclid", "ttclid",
    "sessionId", "visitId", "visitedAt", "landingAt", "isFromAd", "attributionVersion", "attributionUpdatedAt",
)

def preserve_order_tracking(previous, updated):
    if previous.get("fullUrl"):
        for key in ORDER_TRACKING_FIELDS:
            updated[key] = previous.get(key, "")
    return updated

def sheet_payload(order):
    payload = dict(order)
    payload.update(action="sync_order" if order.get("paidNotified") or order.get("telegramOwner") == "server" else "new_order" if is_paid_order(order) else "pending_order", product=order.get("package") or order.get("product") or "Google Gemini Pro 18 Tháng")
    for key in ["paidNotified", "sheetSyncedHash", "sheetSyncedAt", "sheetSyncError", "telegramSent", "telegramOwner", "telegramSyncError", "emailSent"]:
        payload.pop(key, None)
    return payload

def sync_order_integrations(order_id):
    with SYNC_LOCK:
        with ORDER_LOCK:
            order = next((dict(o) for o in read_json_file("orders.json", []) if o.get("orderId") == order_id), None)
        if not order:
            return

        def persist(updates):
            order.update(updates)
            with ORDER_LOCK:
                orders = read_json_file("orders.json", [])
                current = next((o for o in orders if o.get("orderId") == order_id), None)
                if current is not None:
                    current.update(updates)
                    if not write_json_file("orders.json", orders):
                        raise OSError("Cannot persist integration delivery state")

        def send_local_telegram():
            if order.get("paidNotified"):
                return
            import telegram_sender
            _, recipients = telegram_sender.get_current_tele_config()
            sent = dict(order.get("telegramSent") or {})
            for cid in recipients:
                if not sent.get(cid) and telegram_sender.send_telegram_raw(telegram_sender.get_payment_success_template(order), chat_id=cid):
                    sent[cid] = now_vn()
                    persist({"telegramSent": dict(sent)})
            complete = bool(recipients) and all(sent.get(cid) for cid in recipients)
            persist({"paidNotified": complete, "telegramSyncError": "" if complete else "Telegram delivery failed; retry pending"})

        paid = is_paid_order(order)
        webhook = read_json_file("payment_config.json", {}).get("googleSheetWebhookUrl") or ""
        webhook = webhook if webhook and "SAMPLE" not in webhook else ""
        # Once fallback starts, keep one owner for all remaining chat retries.
        # sync_order stores the row without asking Apps Script to send again.
        if paid and (order.get("telegramOwner") == "server" or not webhook):
            if order.get("telegramOwner") != "server":
                persist({"telegramOwner": "server"})
            send_local_telegram()
        if not webhook:
            return
        payload = sheet_payload(order)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if order.get("sheetSyncedHash") == digest and (not paid or order.get("paidNotified")):
            return
        posted = False
        result = None
        try:
            with urllib.request.urlopen(webhook + "?action=health", timeout=15) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("protocolVersion") != 2:
                raise ValueError("Apps Script v2 is required")
            req = urllib.request.Request(webhook, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
            posted = True
            with urllib.request.urlopen(req, timeout=25) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("status") != "success":
                raise ValueError("Sheet did not acknowledge the order")
            if paid and payload["action"] == "new_order" and result.get("notificationsComplete") is not True:
                raise ValueError("Apps Script did not confirm Telegram delivery")
            updates = {"sheetSyncedHash": digest, "sheetSyncError": "", "sheetSyncedAt": now_vn()}
            if paid and payload["action"] == "new_order":
                updates.update(paidNotified=True, telegramSyncError="")
            persist(updates)
        except Exception as exc:
            persist({"sheetSyncError": type(exc).__name__ + ": Sheet sync failed; retry pending"})
            if not paid or order.get("paidNotified") or order.get("telegramOwner") == "server":
                return
            import telegram_sender
            _, recipients = telegram_sender.get_current_tele_config()
            receipts = result.get("telegramSent") if isinstance(result, dict) else None
            explicit_failure = isinstance(result, dict) and result.get("status") == "success" and result.get("notificationsComplete") is False
            # A timeout after POST is ambiguous: Apps Script may already have sent
            # the message. Retry the same idempotent endpoint instead of duplicating it.
            # Legacy scripts have no per-chat receipts; fallback is safe for one chat
            # only, when their response explicitly confirms failed delivery.
            if not posted or (explicit_failure and (isinstance(receipts, dict) or len(recipients) == 1)):
                updates = {"telegramOwner": "server"}
                if isinstance(receipts, dict):
                    sent = dict(order.get("telegramSent") or {})
                    sent.update({str(cid): receipt for cid, receipt in receipts.items() if receipt})
                    updates["telegramSent"] = sent
                persist(updates)
                send_local_telegram()


def queue_order_sync(order_id):
    threading.Thread(target=sync_order_integrations, args=(order_id,), daemon=True).start()

def visit_payload(visit):
    fields = (*ORDER_TRACKING_FIELDS, "ip", "location", "device", "browser", "userAgent", "time")
    return {"action": "track_visit", **{key: visit.get(key, "") for key in fields}}


def visit_digest(visit):
    return hashlib.sha256(json.dumps(visit_payload(visit), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def refresh_visit_order_links():
    # Never acquire ORDER_LOCK while holding VISITS_LOCK.
    with ORDER_LOCK:
        orders = read_json_file("orders.json", [])
    with VISITS_LOCK:
        data = read_json_file(VISITS_FILE, {})
        visits = data.get("visits", [])
        by_id = {v["visitId"]: v for v in visits if v.get("visitId")}
        by_session_url = {}
        for visit in visits:
            by_session_url.setdefault((visit.get("sessionId"), visit.get("fullUrl")), []).append(visit)
            visit.update(orderIds=[], paidOrderIds=[], orders=[])
        for order in orders:
            visit = by_id.get(order.get("visitId"))
            if not order.get("visitId") and order.get("sessionId") and order.get("fullUrl"):
                candidates = by_session_url.get((order["sessionId"], order["fullUrl"]), [])
                visit = candidates[0] if len(candidates) == 1 else None
            if visit is not None:
                visit["orderIds"].append(order["orderId"])
                if is_paid_order(order):
                    visit["paidOrderIds"].append(order["orderId"])
                visit["orders"].append({key: order.get(key, "") for key in ("orderId", "status", "createdAt", "paidAt")})
        if visits:
            write_json_file(VISITS_FILE, data)


def sync_visit_integrations(visit_id):
    if not visit_id:
        return
    with VISIT_SYNC_LOCK:
        with VISITS_LOCK:
            visit = next((dict(v) for v in read_json_file(VISITS_FILE, {}).get("visits", []) if v.get("visitId") == visit_id), None)
        if not visit:
            return
        digest = visit_digest(visit)
        if visit.get("sheetSyncedHash") == digest:
            return
        webhook = read_json_file("payment_config.json", {}).get("googleSheetWebhookUrl") or ""
        if not webhook or "SAMPLE" in webhook:
            return
        try:
            with urllib.request.urlopen(webhook + "?action=health", timeout=15) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("protocolVersion") != 2 or health.get("trafficColumns", 0) < 25:
                raise ValueError("Cần cập nhật Apps Script hỗ trợ mã lượt truy cập")
            req = urllib.request.Request(webhook, data=json.dumps(visit_payload(visit), ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("status") != "success" or result.get("visitId") != visit_id:
                raise ValueError("Sheet chưa xác nhận đúng mã lượt truy cập")
            updates = {"sheetSyncedHash": digest, "sheetSyncError": "", "sheetSyncedAt": now_vn()}
        except Exception as exc:
            updates = {"sheetSyncError": type(exc).__name__ + ": Sheet chưa xác nhận lượt truy cập, sẽ gửi lại"}
        with VISITS_LOCK:
            data = read_json_file(VISITS_FILE, {})
            current = next((v for v in data.get("visits", []) if v.get("visitId") == visit_id), None)
            if current:
                current.update(updates)
                write_json_file(VISITS_FILE, data)


def queue_visit_sync(visit_id):
    if visit_id:
        VISIT_SYNC_EVENT.set()


def payment_is_current(tx, order):
    # The short phone reference is reusable, so its payment must belong to this checkout.
    if not re.fullmatch(r"PRO18T\s*\d+", str(order.get("memo") or ""), re.I) or not order.get("createdAt"):
        return True
    def parse(value):
        text = str(value or "")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(text, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone(timedelta(hours=7)))
    created = parse(order["createdAt"])
    paid = parse(tx.get("paidAt") or tx.get("completedAt") or tx.get("transactionDateTime") or tx.get("time") or tx.get("updatedAt") or tx.get("createdAt"))
    return created is not None and paid is not None and paid >= created


def mark_order_paid(order_id, tx_id=None, tx_data=None, source="API Pay"):
    tx = dict(tx_data or {})
    with ORDER_LOCK:
        orders = read_json_file("orders.json", [])
        order = next((o for o in orders if o.get("orderId") == order_id), None)
        if not order:
            return None
        if is_paid_order(order):
            queue_order_sync(order_id)
            return dict(order)
        if not successful_tx(tx) or not payment_is_current(tx, order):
            return None
        memo = normalized_memo(order.get("memo"))
        content = normalized_memo(tx.get("description") or tx.get("content") or tx.get("memo"))
        exact_request = bool(order.get("apipayPublicId") and order["apipayPublicId"] == tx.get("publicId"))
        if memo and (content and memo not in content or not content and not exact_request):
            return None
        amount = parse_money(tx.get("amount"), 0)
        if amount < parse_money(order.get("amountRaw") or order.get("amount"), get_current_package_price()):
            return None
        key = payment_key(tx)
        identity = str(tx.get("transactionId") or tx.get("publicId") or tx_id or tx.get("id") or key)
        if any(o.get("orderId") != order_id and is_paid_order(o) and (o.get("paymentKey") == key or o.get("paymentTxId") == identity) for o in orders):
            return None
        order.update(paymentTxId=identity, paymentKey=key, paymentSource=source, paidAt=tx.get("paidAt") or tx.get("transactionDateTime") or tx.get("time") or now_vn(), amountRaw=amount)
        order["amount"] = f"{amount:,}đ".replace(",", ".")
        if not order.get("licenseLink"):
            with LICENSE_LOCK:
                lics = read_licenses()
                existing = next((lic for lic in lics if f"({order_id})" in lic.get("assignedTo", "")), None)
                free = existing or next((lic for lic in lics if lic.get("status") == "Sẵn sàng"), None)
                if free:
                    free.update(status="Đã cấp", assignedTo=f"{order.get('name')} ({order_id})")
                    write_json_file(LICENSES_FILE, lics)
                    order["licenseLink"] = free["link"]
        order["status"] = "Đã thanh toán (BIDV)" if order.get("licenseLink") else "Đã thanh toán (Chờ cấp link)"
        if order.get("couponCode") and not order.get("couponCounted"):
            with COUPONS_LOCK:
                coupons = read_json_file(COUPONS_FILE, [])
                for coupon in coupons:
                    if str(coupon.get("code") or "").upper() == order["couponCode"].upper():
                        coupon["usedCount"] = int(coupon.get("usedCount") or 0) + 1
                        break
                write_json_file(COUPONS_FILE, coupons)
            order["couponCounted"] = True
        write_json_file("orders.json", orders)
        result = dict(order)
    refresh_visit_order_links()
    queue_order_sync(order_id)
    return result


class GeminiCRMHandler(SimpleHTTPRequestHandler):
    # Explicit MIME keeps MP4 playback reliable behind simple Python hosting.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mp4": "video/mp4"}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Thiết lập CORS toàn diện cho phép gọi API mượt mà
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin in allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/admin", "/admin/") or path.endswith(".html") or path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
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

        if _requires_admin(path, "GET") and not _admin_authorized(self):
            return self.send_json({"status": "error", "message": "Admin authentication required"}, 401)

        blocked_files = {"/runtime_secrets.json", "/runtime_config.py", "/payment_config.json", "/telegram_config.json", "/orders.json", "/licenses.json", "/bank_transactions.json", "/visits.json", "/pixel_stats.json", "/coupons.json", "/temp_login.json", "/GoogleAppsScript_CRM_AutoBot.js", "/server.py", "/server.ps1", "/api.php"}
        if path in blocked_files:
            return self.send_json({"status": "error", "message": "Resource not available"}, 404)

        # Điều hướng trang chủ và admin
        if path == "/" or path == "":
            self.path = "/index.html"
            return super().do_GET()
        if path == "/admin" or path == "/admin/":
            self.path = "/admin.html"
            return super().do_GET()

        if path == "/api/health":
            cfg = read_json_file("payment_config.json", {})
            import telegram_sender
            telegram_token, telegram_chats = telegram_sender.get_current_tele_config()
            return self.send_json({"status": "success", "build": "2026-10-27-telegram-retry", "paymentVerificationVersion": 3, "paymentConfigured": bool(cfg.get("accessKey") and cfg.get("secretKey")), "telegramConfigured": bool(telegram_token and telegram_chats), "bankCode": cfg.get("bankCode"), "testMode": cfg.get("testMode") is True})

        # 1. API: Cấu hình cổng thanh toán
        if path == "/api/payment-config":
            cfg = read_json_file("payment_config.json", {})
            public_keys = {"packagePrice", "originalPrice", "nextPrice", "packageName", "provider", "bankPublicId", "vaNumber", "accountNo", "physicalAccountNo", "bankBin", "accountName", "bankCode", "pollIntervalSeconds", "testMode", "enabled", "pixelId", "pixelEnabled"}
            return self.send_json({k: v for k, v in cfg.items() if k in public_keys})

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
            expected_amount = 0
            order_created_at = None
            pending_order = {}
            if order_id:
                for pending in read_json_file("orders.json", []):
                    if str(pending.get("orderId") or "") == order_id:
                        pending_order = pending
                        order_created_at = pending.get("createdAt")
                        expected_amount = parse_money(pending.get("amount"), get_current_package_price())
                        break

            if not pending_order:
                return self.send_json({"paid": False, "message": "Order not found"}, 404)
            # Match against saved checkout data, never caller-supplied phone/memo/amount.
            memo = str(pending_order.get("memo") or "")
            phone = str(pending_order.get("phone") or "")
            clean_memo = normalized_memo(memo)
            clean_phone = phone.replace("+84", "0").replace(" ", "")
            expected_amount = parse_money(pending_order.get("amountRaw") or pending_order.get("amount"), get_current_package_price())
            public_id = str(pending_order.get("apipayPublicId") or public_id)
            ambiguous_reference = sum(1 for candidate in read_json_file("orders.json", []) if not is_paid_order(candidate) and normalized_memo(candidate.get("memo")) == clean_memo) > 1
            if not order_id:
                return self.send_json({"paid": False, "message": "Missing orderId"}, 400)
            # 4.1 Kiểm tra qua ApiPay bridge nếu có publicId
            if public_id:
                try:
                    import apipay_bridge
                    res = apipay_bridge.check_payment_status(public_id)
                    paid_amount = parse_money(res.get("amount") or (res.get("transaction") or {}).get("amount"), 0)
                    if res.get("paid") and paid_amount >= expected_amount and paid_amount > 0:
                        updated_order = mark_order_paid(order_id, public_id, res.get("transaction"), "APIPay Cloud PR")
                        return self.send_json({
                            "paid": updated_order is not None,
                            "message": "Payment verified via APIPay Cloud",
                            "transaction": res.get("transaction"),
                            "order": updated_order,
                            "source": "APIPay Cloud"
                        })
                except Exception as e:
                    pass

            # 4.2 Kiểm tra danh sách Payment Requests gần nhất trên ApiPay Cloud bằng phone / memo
            if (clean_phone or clean_memo) and not ambiguous_reference:
                try:
                    import apipay_bridge
                    res = apipay_bridge.check_recent_payment_requests(memo, phone, expected_amount or parse_money(query.get("amount", [0])[0], 0), not_before=order_created_at)
                    if res.get("paid"):
                        pr_tx = res.get("transaction") or {}
                        pr_pub = pr_tx.get("publicId") or pr_tx.get("id") or public_id
                        updated_order = mark_order_paid(order_id, pr_pub, pr_tx, "APIPay Cloud Recent PR")
                        return self.send_json({
                            "paid": updated_order is not None,
                            "message": "Payment verified via APIPay Cloud Recent",
                            "transaction": pr_tx,
                            "order": updated_order,
                            "source": "APIPay Cloud Recent"
                        })
                except Exception as e:
                    pass

            # 4.3 Kiểm tra đối soát trong nhật ký giao dịch ngân hàng (bank_transactions.json)
            # Chỉ khớp giao dịch chưa bị đơn khác nhận, không nhận nhầm giao dịch cũ
            txs = read_json_file("bank_transactions.json", [])
            tx_updated = False
            for tx in txs:
                # Nếu giao dịch đã được đơn khác sử dụng thì bỏ qua (1 giao dịch = 1 đơn duy nhất)
                used_by = tx.get("used_by_order")
                if used_by and used_by != order_id:
                    continue

                desc = (tx.get("description") or tx.get("memo") or "").upper().replace(" ", "")
                is_match = False
                if clean_memo and clean_memo in desc:
                    is_match = True
                elif not clean_memo and clean_phone and len(clean_phone) >= 9 and clean_phone in desc:
                    is_match = True

                if is_match and not ambiguous_reference and successful_tx(tx) and payment_is_current(tx, pending_order):
                    if expected_amount and parse_money(tx.get("amount"), 0) < expected_amount:
                        continue
                    if order_id and not tx.get("used_by_order"):
                        tx["used_by_order"] = order_id
                        tx_updated = True
                    if tx_updated:
                        write_json_file("bank_transactions.json", txs)
                    updated_order = mark_order_paid(order_id, tx.get("id"), tx, tx.get("source", "Live Bank Stream"))
                    return self.send_json({
                        "paid": updated_order is not None,
                        "message": "Payment verified via Live Bank Feed",
                        "transaction": tx,
                        "order": updated_order,
                        "source": tx.get("source", "Live Bank Stream")
                    })

            # 4.4 Kiểm tra trong orders.json (CHỈ KHỚP ĐÚNG orderId NÀY NẾU ĐÃ ĐƯỢC DUYỆT HOẶC WEBHOOK XÁC NHẬN)
            # TUYỆT ĐỐI KHÔNG KHỚP THEO SỐ ĐIỆN THOẠI ĐỂ TRÁNH LỖI KHÁCH CŨ TẠO ĐƠN MỚI BỊ NHẬN NHẦM
            if order_id:
                orders = read_json_file("orders.json", [])
                for order in orders:
                    o_id = (order.get("orderId") or "").strip()
                    if order_id == o_id:
                        st = (order.get("status") or "").lower()
                        is_paid = "đã thanh toán" in st or "da thanh toan" in st or "thành công" in st or "thanh cong" in st
                        if is_paid:
                            return self.send_json({
                                "paid": True,
                                "message": "Payment verified via Order Database",
                                "transaction": order,
                                "order": order,
                                "source": "Order Database"
                            })
                        break

            return self.send_json({"paid": False, "message": "Chờ quét mã thanh toán..."})

        # 5. API: Lấy ảnh QR VietQR chuẩn
        if path == "/api/qr-image":
            qr_file = os.path.join(BASE_DIR, "default_qr.txt")
            if os.path.exists(qr_file):
                with open(qr_file, "r", encoding="utf-8") as f:
                    raw_b64 = f.read().replace("data:image/png;base64,", "").strip()
                img_data = base64.b64decode(raw_b64)
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml" if img_data.lstrip().startswith(b"<svg") else "image/png")
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

        # 10. API: Báo động lên giá (Mốc 200 đơn lên giá 159K, FOMO chạy từ 150 lên 195)
        if path == "/api/fomo-stats" or path == "/api/sold-stats":
            client_ip = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For")
            if client_ip:
                client_ip = client_ip.split(",")[0].strip()
            else:
                client_ip = self.client_address[0]

            # Khởi điểm đúng 150 đơn, cộng thêm số đơn thanh toán thật từ orders.json (tối đa 195)
            orders = read_json_file("orders.json", [])
            paid_count = len([o for o in orders if ("đã thanh toán" in (o.get("status") or "").lower() or "thành công" in (o.get("status") or "").lower())])
            current_sold = min(195, max(150, 150 + paid_count))
            remaining = max(5, 200 - current_sold)

            pricing = read_json_file("payment_config.json", {})
            current_price = f"{get_current_package_price():,}đ".replace(",", ".")
            next_price = f"{parse_money(pricing.get('nextPrice'), 159000):,}đ".replace(",", ".")

            # Đồng bộ lại sold_stats.json ở mốc chuẩn
            write_json_file("sold_stats.json", {
                "baseCount": 150,
                "targetCount": 200,
                "maxFomo": 195,
                "currentSold": current_sold,
                "currentPrice": current_price,
                "nextPrice": next_price
            })

            return self.send_json({
                "status": "success",
                "soldCount": current_sold,
                "baseCount": 150,
                "targetCount": 200,
                "maxFomo": 195,
                "remainingSlots": remaining,
                "currentPrice": current_price,
                "nextPrice": next_price,
                "clientIp": client_ip
            })

        # Mặc định trả về static file
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_post_json()

        if path == "/api/admin-login":
            supplied = str(body.get("password") or "")
            supplied_hash = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
            if not secrets.compare_digest(supplied_hash, _admin_hash()):
                return self.send_json({"status": "error", "message": "Invalid admin credentials"}, 401)
            token = secrets.token_urlsafe(32)
            ADMIN_TOKENS[token] = datetime.now().timestamp() + ADMIN_TOKEN_TTL
            return self.send_json({"status": "success", "token": token, "expiresIn": ADMIN_TOKEN_TTL})

        if _requires_admin(path, "POST") and not _admin_authorized(self):
            return self.send_json({"status": "error", "message": "Admin authentication required"}, 401)

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
            allowed_events = {"PageView", "ViewContent", "Lead", "InitiateCheckout", "Purchase"}
            if ev not in allowed_events:
                return self.send_json({"status": "error", "message": "Unsupported pixel event"}, 400)
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
            visit_id = str(body.get("visitId") or "").strip()
            full_url = str(body.get("fullUrl") or "")
            landing = urllib.parse.urlparse(full_url)
            origin = self.headers.get("Origin", "").rstrip("/")
            if origin in allowed_origins() and full_url and origin != f"{landing.scheme}://{landing.netloc}":
                return self.send_json({"status": "error", "message": "URL lượt truy cập không khớp trang hiện tại"}, 409)
            client_ip = (self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()
            ip = body.get("ip") or client_ip
            if ip in ("127.0.0.1", "::1") and client_ip not in ("127.0.0.1", "::1"):
                ip = client_ip
            ua = self.headers.get("User-Agent", "")
            device = body.get("device") or ("Điện thoại" if any(k in ua for k in ("Mobile", "Android", "iPhone", "iPad")) else "Máy tính")
            domain = (landing.hostname or self.headers.get("Host", "").split(":")[0] or "Khác").lower()
            label = str(body.get("referrer") or "").strip()
            ref = (label or body.get("rawReferrer") or "").lower()
            query = urllib.parse.parse_qs(landing.query)
            if "facebook" in ref or ref in ("fb", "meta") or (not label and "fbclid" in query):
                source, label = "facebook", label or "Facebook"
            elif "tiktok" in ref or (not label and "ttclid" in query):
                source, label = "tiktok", label or "TikTok"
            elif "google" in ref or (not label and "gclid" in query):
                source, label = "google", label or "Tìm kiếm Google"
            elif "zalo" in ref:
                source, label = "zalo", label or "Zalo Chat"
            elif not ref or "trực tiếp" in ref or ref in ("direct", "truc tiep"):
                source, label = "direct", label or "Truy cập trực tiếp"
            else:
                source, label = "other", label or "Khác"
            with VISITS_LOCK:
                data = read_json_file(VISITS_FILE, {"totalVisits": 0, "todayVisits": 0, "visits": []})
                today = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y")
                if data.get("lastDate") != today:
                    data.update(lastDate=today, todayVisits=0)
                visits = data.setdefault("visits", [])
                existing = next((v for v in visits if visit_id and v.get("visitId") == visit_id), None)
                if existing:
                    # Attribution and counting remain fixed; retries only enrich the same visit.
                    for key, value in (("ip", ip), ("location", body.get("location")), ("device", body.get("device")), ("browser", body.get("browser"))):
                        if value:
                            existing[key] = value
                    entry = existing
                else:
                    entry = {key: body.get(key) or "" for key in (*ORDER_TRACKING_FIELDS, "userAgent")}
                    entry.update(visitId=visit_id, fullUrl=full_url, domain=domain, referrer=label,
                                 time=body.get("time") or datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S %d/%m/%Y"), visitedAt=body.get("visitedAt") or now_vn(),
                                 ip=ip, location=body.get("location") or "", device=device,
                                 browser=body.get("browser") or "Trình duyệt Web")
                    visits.insert(0, entry)
                    data["totalVisits"] = int(data.get("totalVisits", 0)) + 1
                    data["todayVisits"] = int(data.get("todayVisits", 0)) + 1
                    bucket = "mobile" if "Mobile" in device or "Điện thoại" in device else "desktop" if "Máy tính" in device or "PC" in device else "other"
                    for name, key in (("devices", bucket), ("sources", source), ("domains", domain)):
                        counters = data.setdefault(name, {})
                        counters[key] = counters.get(key, 0) + 1
                    data["visits"] = visits[:1000]
                if not write_json_file(VISITS_FILE, data):
                    return self.send_json({"status": "error", "message": "Không lưu được lượt truy cập"}, 500)
            refresh_visit_order_links()
            queue_visit_sync(visit_id)
            return self.send_json({"status": "success", "visitId": visit_id, "duplicate": existing is not None,
                                   "totalVisits": data["totalVisits"], "todayVisits": data["todayVisits"], "clientIp": entry["ip"], "sheetSync": "queued"})

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
            client_ip = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For")
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
            body.setdefault("userAgent", self.headers.get("User-Agent", ""))
            ua = body["userAgent"]
            body.setdefault("browser", "Edge" if "Edg/" in ua else "Chrome" if "Chrome/" in ua else "Safari" if "Safari/" in ua else "Không xác định")

            if not body.get("location") or body.get("location") == "Việt Nam":
                # Nếu đã có IP thật từ ngoài mạng, có thể đối soát
                if body.get("ip") and body.get("ip") not in ["127.0.0.1", "::1"]:
                    pass

            if not body.get("device"):
                ua = self.headers.get("User-Agent", "")
                body["device"] = "Điện thoại" if ("Mobile" in ua or "Android" in ua or "iPhone" in ua) else "Máy tính PC"
            
            # Tự động trích xuất Tên Miền Đặt Hàng (Domain Tracking)
            order_domain = ""
            if body.get("fullUrl"):
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

            with ORDER_LOCK:
                orders = read_json_file("orders.json", [])
                existing = next((o for o in orders if o.get("orderId") == order_id), {})
                for flag in ("paidNotified", "couponCounted", "telegramSent", "telegramOwner", "telegramSyncError", "sheetSyncedHash", "sheetSyncedAt", "sheetSyncError"):
                    body.pop(flag, None)
                if not existing and body.get("fullUrl"):
                    origin = self.headers.get("Origin", "").rstrip("/")
                    landing = urllib.parse.urlparse(body["fullUrl"])
                    landing_origin = f"{landing.scheme}://{landing.netloc}"
                    if origin in allowed_origins() and origin != landing_origin:
                        return self.send_json({"status": "error", "message": "URL nguồn không khớp trang đang tạo đơn. Vui lòng tải lại trang trước khi đặt hàng."}, 409)
                if not existing and body.get("visitId"):
                    with VISITS_LOCK:
                        captured_visit = next((v for v in read_json_file(VISITS_FILE, {}).get("visits", []) if v.get("visitId") == body["visitId"]), None)
                    if captured_visit and captured_visit.get("fullUrl"):
                        # One visit ID describes one original URL/source for both traffic and orders.
                        for key in ORDER_TRACKING_FIELDS:
                            body[key] = captured_visit.get(key, "")
                        for key in ("ip", "location"):
                            if captured_visit.get(key):
                                body[key] = captured_visit[key]
                if is_paid_order(body) and not is_paid_order(existing) and not _admin_authorized(self):
                    return self.send_json({"status": "error", "message": "Payment must be verified by the server before confirming the order"}, 409)
                merged = dict(existing)
                merged.update({key: value for key, value in body.items() if value is not None and value != ""})
                preserve_order_tracking(existing, merged)
                merged["createdAt"] = existing.get("createdAt") or body.get("createdAt") or now_vn()
                if is_paid_order(existing):
                    for key in ("status", "paidAt", "paymentTxId", "paymentKey", "licenseLink", "amount", "amountRaw"):
                        if existing.get(key):
                            merged[key] = existing[key]
                if is_paid_order(merged):
                    duplicate = next((o for o in orders if o.get("orderId") != order_id and is_paid_order(o) and ((merged.get("paymentKey") and o.get("paymentKey") == merged["paymentKey"]) or (merged.get("paymentTxId") and o.get("paymentTxId") == merged["paymentTxId"]))), None)
                    if duplicate:
                        return self.send_json({"status": "error", "message": "Giao dịch đã thuộc đơn khác", "orderId": duplicate["orderId"]}, 409)
                    merged["paidAt"] = existing.get("paidAt") or merged.get("paidAt") or now_vn()
                    if merged.get("couponCode") and not merged.get("couponCounted"):
                        with COUPONS_LOCK:
                            coupons = read_json_file(COUPONS_FILE, [])
                            for coupon in coupons:
                                if str(coupon.get("code") or "").upper() == merged["couponCode"].upper():
                                    coupon["usedCount"] = int(coupon.get("usedCount") or 0) + 1
                                    break
                            write_json_file(COUPONS_FILE, coupons)
                        merged["couponCounted"] = True
                orders = [merged if o.get("orderId") == order_id else o for o in orders]
                if not existing:
                    orders.insert(0, merged)
                if not write_json_file("orders.json", orders[:500]):
                    return self.send_json({"status": "error", "message": "Không lưu được đơn"}, 500)
            refresh_visit_order_links()
            queue_order_sync(order_id)
            return self.send_json({"status": "success", "orderId": order_id, "order": merged, "sheetSync": "queued"})

        # API: Nhận Webhook từ APIPay / Casso / SeAPay / MBBank
        if path == "/api/webhook":
            webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
            supplied_secret = self.headers.get("X-Webhook-Secret", "") or str((body.get("webhookSecret") if isinstance(body, dict) else "") or "")
            if webhook_secret and not secrets.compare_digest(supplied_secret, webhook_secret):
                return self.send_json({"status": "error", "message": "Invalid webhook signature"}, 401)
            import re
            sys.stdout.write(f"[WEBHOOK INCOMING] Payload: {json.dumps(body, ensure_ascii=False)[:300]}\n")
            sys.stdout.flush()

            items = []
            if isinstance(body, list):
                items = body
            elif isinstance(body.get("data"), dict) and isinstance(body["data"].get("records"), list):
                items = body["data"]["records"]
            elif isinstance(body.get("data"), list):
                items = body.get("data")
            elif isinstance(body.get("data"), dict) and body.get("data"):
                items = [body.get("data")]
            elif isinstance(body.get("records"), list):
                items = body.get("records")
            elif isinstance(body.get("transactions"), list):
                items = body.get("transactions")
            elif isinstance(body, dict) and body:
                items = [body]

            current_txs = read_json_file("bank_transactions.json", [])
            orders = read_json_file("orders.json", [])
            orders_updated = False

            for it in items:
                # Trích xuất số tiền an toàn (hỗ trợ cả int, float, string "129000", "129.000đ")
                raw_amt = it.get("amount") or it.get("transferAmount") or it.get("creditAmount") or 0
                try:
                    amt = parse_money(raw_amt, 0)
                except Exception:
                    amt = 0

                desc = str(it.get("content") or it.get("description") or it.get("memo") or it.get("comment") or "").strip()
                status_raw = str(it.get("status") or "").upper()
                public_id = str(it.get("publicId") or "").strip()

                # Kiểm tra giao dịch hợp lệ
                is_valid_tx = successful_tx(it)

                if is_valid_tx:
                    pkg_price = get_current_package_price()
                    actual_amt = amt if amt > 0 else pkg_price
                    tx_record = {
                        "id": str(it.get("id") or it.get("publicId") or f"TX_{int(datetime.now().timestamp()) % 1000000:06d}"),
                        "amount": actual_amt,
                        "description": desc or f"PRO18T (APIPay {public_id})",
                        "bank": it.get("bank") or it.get("bankCode") or "BIDV",
                        "time": it.get("paidAt") or it.get("completedAt") or it.get("transactionDateTime") or it.get("time") or it.get("updatedAt") or it.get("createdAt") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "APIPay Webhook",
                        "publicId": public_id
                    }
                    tx_record["paymentKey"] = payment_key(it)
                    tx_record["status"] = status_raw or "COMPLETED"
                    previous_tx = next((tx for tx in current_txs if tx.get("id") == tx_record["id"] or tx.get("paymentKey", payment_key(tx)) == tx_record["paymentKey"]), None)
                    if previous_tx:
                        if previous_tx.get("used_by_order"):
                            continue
                        tx_record = previous_tx
                    else:
                        current_txs.insert(0, tx_record)

                    # Tự động khớp với đơn hàng đang chờ thanh toán
                    clean_desc = (desc or "").upper().replace(" ", "")
                    candidates = []
                    exact_requests = []
                    for order in read_json_file("orders.json", []):
                        st = (order.get("status") or "").lower()
                        if "chờ thanh toán" in st and not order.get("paidNotified"):
                            order_amount = parse_money(order.get("amount"), pkg_price)
                            if actual_amt < order_amount or not payment_is_current(tx_record, order):
                                continue
                            phone = (order.get("phone") or "").replace("+84", "0").replace(" ", "")
                            memo = (order.get("memo") or f"PRO18T {phone}").upper().replace(" ", "")
                            o_pub = (order.get("apipayPublicId") or "").strip()
                            if public_id and public_id == o_pub:
                                exact_requests.append(order)
                            elif memo and memo in clean_desc:
                                candidates.append(order)
                    # Prefer APIPay's unique request ID. A shared phone reference must not
                    # select an arbitrary order when more than one checkout is pending.
                    matches = exact_requests or candidates
                    matched_order = matches[0] if len(matches) == 1 else None

                    if matched_order:
                        tx_record["used_by_order"] = matched_order.get("orderId")
                        mark_order_paid(matched_order.get("orderId"), tx_record["id"], tx_record, "APIPay Webhook")
                        orders_updated = True

            write_json_file("bank_transactions.json", current_txs[:150])
            return self.send_json({"status": "success", "message": "Webhook processed", "count": len(items)})

        # 4. API: Mô phỏng thanh toán (Simulate)
        if path == "/api/simulate-payment":
            if read_json_file("payment_config.json", {}).get("testMode") is not True:
                return self.send_json({"status": "error", "message": "Simulation is disabled for live payments"}, 403)
            phone = body.get("phone", "0901234567")
            memo = body.get("memo", f"PRO18T {phone}")
            amount = int(body.get("amount") or get_current_package_price())
            sim_tx = {
                "id": f"SIM_{int(datetime.now().timestamp()) % 1000000:06d}",
                "amount": amount,
                "description": memo,
                "bank": "BIDV",
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
                return self.send_json({"status": "success" if ok else "error", "message": "" if ok else "Telegram delivery failed"}, 200 if ok else 502)
            except Exception as e:
                return self.send_json({"status": "error", "message": str(e)}, 500)

        # 7. API: Cảnh báo đăng nhập Admin
        if path == "/api/admin-login-notify":
            try:
                # Idempotency guard: retries from the browser/proxy must not create
                # another Telegram alert for the same real login event.
                event_id = str(body.get("loginEventId") or "").strip()
                if event_id:
                    now = datetime.now().timestamp()
                    with ADMIN_LOGIN_EVENTS_LOCK:
                        expired = [key for key, seen_at in ADMIN_LOGIN_EVENTS.items()
                                   if now - seen_at > ADMIN_LOGIN_EVENT_TTL]
                        for key in expired:
                            ADMIN_LOGIN_EVENTS.pop(key, None)
                        if event_id in ADMIN_LOGIN_EVENTS:
                            return self.send_json({"status": "success", "duplicate": True})
                        ADMIN_LOGIN_EVENTS[event_id] = now

                import telegram_sender
                msg = telegram_sender.get_admin_login_template(body)
                ok = telegram_sender.send_telegram_raw(msg)
                if not ok:
                    return self.send_json({"status": "error", "message": "Telegram send failed"}, 502)
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
    # Khởi động luồng ngầm tự động đồng bộ Webhook URL trên ApiPay Cloud
    def _sync_apipay_worker():
        import time
        while True:
            try:
                import apipay_bridge
                public_webhook = os.environ.get("PUBLIC_WEBHOOK_URL", "https://geminigiare.io.vn").strip()
                if public_webhook:
                    apipay_bridge.sync_apipay_webhook_url(public_webhook.rstrip("/") + "/api/webhook")
            except Exception:
                pass
            time.sleep(300)
    threading.Thread(target=_sync_apipay_worker, daemon=True).start()

    def _integration_worker():
        import time
        while True:
            for order in read_json_file("orders.json", []):
                try:
                    sync_order_integrations(order.get("orderId"))
                except Exception as exc:
                    sys.stderr.write(f"Integration retry: {type(exc).__name__}\n")
            time.sleep(30)
    threading.Thread(target=_integration_worker, daemon=True).start()
    def _visit_integration_worker():
        # Traffic retries have their own worker so they cannot delay paid order alerts.
        retry_cursor = 0
        while True:
            VISIT_SYNC_EVENT.clear()
            with VISITS_LOCK:
                pending = [v["visitId"] for v in read_json_file(VISITS_FILE, {}).get("visits", [])
                           if v.get("visitId") and v.get("sheetSyncedHash") != visit_digest(v)]
            if pending:
                start = retry_cursor % len(pending)
                batch = (pending[start:] + pending[:start])[:10]
                for visit_id in batch:
                    try:
                        sync_visit_integrations(visit_id)
                    except Exception as exc:
                        sys.stderr.write(f"Visit integration retry: {type(exc).__name__}\n")
                retry_cursor = start + len(batch)
            VISIT_SYNC_EVENT.wait(30)
    threading.Thread(target=_visit_integration_worker, daemon=True).start()
    server = HTTPServer(("0.0.0.0", PORT), GeminiCRMHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng máy chủ...")
        server.server_close()

if __name__ == "__main__":
    run()
