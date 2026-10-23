# -*- coding: utf-8 -*-
"""
Telegram Notification Engine for Gemini Pro CRM
Đảm bảo 100% UTF-8 không lỗi font, định dạng tin nhắn gọn gàng, đẹp mắt, chuyên nghiệp.
"""
import sys
import json
import ssl
import urllib.request
import urllib.error
from datetime import datetime
from html import escape

# SSL Context đảm bảo gửi thông báo Telegram thông suốt trong mọi môi trường
tele_ssl_ctx = ssl.create_default_context()
tele_ssl_ctx.check_hostname = False
tele_ssl_ctx.verify_mode = ssl.CERT_NONE

# Đảm bảo console Windows không bị lỗi Unicode
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

import os

DEFAULT_BOT_TOKEN = "8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c"
DEFAULT_CHAT_ID = "-1004413665683"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_current_tele_config():
    token, ids = None, []
    for filename in ["telegram_config.json", "payment_config.json"]:
        try:
            with open(os.path.join(BASE_DIR, filename), encoding="utf-8-sig") as f:
                config = json.load(f)
            token = token or config.get("botToken") or config.get("telegramBotToken")
            values = config.get("chatIds") or config.get("telegramChatIds") or [config.get("chatId") or config.get("telegramChatId")]
            ids.extend(str(value) for value in values if value)
        except (OSError, ValueError):
            pass
    return token or DEFAULT_BOT_TOKEN, list(dict.fromkeys(ids or [DEFAULT_CHAT_ID, "-5585627393"]))

def send_telegram_raw(html_text, bot_token=None, chat_id=None):
    token, default_ids = get_current_tele_config()
    recipients = [str(chat_id)] if chat_id else default_ids
    results = []
    for cid in recipients:
        payload = {"chat_id": cid, "text": html_text, "parse_mode": "HTML", "disable_web_page_preview": True}
        req = urllib.request.Request(f"https://api.telegram.org/bot{bot_token or token}/sendMessage", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, context=tele_ssl_ctx, timeout=10) as resp:
                results.append(bool(json.loads(resp.read().decode("utf-8")).get("ok")))
        except Exception as exc:
            sys.stderr.write(f"Telegram chat {cid}: {type(exc).__name__}\n")
            results.append(False)
    return bool(results) and all(results)

# ==========================================
# 4 MẪU TIN NHẮN CHUẨN ĐẸP, GỌN GÀNG, CHUYÊN NGHIỆP
# ==========================================

def extract_domain_from_order(order):
    """Trích xuất tên miền website mà khách hàng đã đặt hàng."""
    domain = (order.get("domain") or "").strip().lower()
    if not domain:
        url = order.get("fullUrl") or order.get("url") or ""
        if url:
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                domain = (parsed.hostname or parsed.netloc or "").strip().lower()
            except Exception:
                domain = ""
    return domain

def format_ad_tracking_lines(order):
    """
    Tạo khối thông tin nguồn quảng cáo và link chi tiết rõ ràng gửi về Telegram.
    Đặc biệt ghi rõ link khi khách đến từ chiến dịch Facebook Ads, TikTok Ads, Google...
    """
    full_url = order.get("fullUrl") or order.get("url") or ""
    fbclid = order.get("fbclid") or ""
    utm_source = order.get("utmSource") or order.get("utm_source") or ""
    utm_campaign = order.get("utmCampaign") or order.get("utm_campaign") or ""
    referrer = order.get("referrer") or ""
    raw_ref = order.get("rawReferrer") or ""

    is_ad = bool(fbclid or utm_source or utm_campaign or "quảng cáo" in referrer.lower() or "ads" in referrer.lower() or "facebook" in referrer.lower() or "tiktok" in referrer.lower())

    lines = []
    if is_ad or fbclid or utm_source:
        ad_badge = "🔵 Quảng Cáo Facebook (Meta Ads)" if (fbclid or "facebook" in (utm_source + referrer).lower() or "fb" in utm_source.lower()) else (
                   "⚫ Quảng Cáo TikTok Ads" if ("tiktok" in (utm_source + referrer).lower()) else (
                   "🔴 Quảng Cáo Google Ads" if ("google" in (utm_source + referrer).lower() or order.get("gclid")) else f"📢 Quảng Cáo ({referrer or utm_source})"))
        lines.append(f"🎯 <b>Nguồn QC:</b> <b>{ad_badge}</b>")
        if utm_campaign:
            lines.append(f"🏷️ <b>Chiến dịch (Campaign):</b> <code>{utm_campaign}</code>")
        if utm_source:
            lines.append(f"📌 <b>UTM Source:</b> <code>{utm_source}</code>")
        if fbclid:
            short_fbclid = (fbclid[:30] + "...") if len(fbclid) > 30 else fbclid
            lines.append(f"🆔 <b>FB Click ID:</b> <code>{short_fbclid}</code>")
        if full_url:
            lines.append(f"🔗 <b>LINK QUẢNG CÁO KHÁCH BẤM VÀO:</b>\n<code>{full_url}</code>")
        elif raw_ref:
            lines.append(f"🔗 <b>Link giới thiệu:</b> <code>{raw_ref}</code>")
    else:
        lines.append(f"🧭 <b>Nguồn truy cập:</b> {referrer or 'Trực tiếp / Bookmark'}")
        if full_url:
            lines.append(f"🔗 <b>Link truy cập:</b> <code>{full_url}</code>")

    return "\n".join(lines)

def get_payment_success_template(order):
    fields = [("Mã đơn", "orderId"), ("Mã lượt truy cập", "visitId"), ("Mã phiên", "sessionId"), ("Khách", "name"), ("SĐT", "phone"), ("Email", "email"), ("Thanh toán lúc (GMT+7)", "paidAt"), ("Tạo đơn lúc", "createdAt"), ("Vào trang lúc", "landingAt"), ("IP", "ip"), ("Vị trí IP (ước lượng)", "location"), ("Thiết bị", "device"), ("Trình duyệt", "browser"), ("Nguồn khách", "referrer"), ("Tên miền", "domain"), ("URL vào trang", "fullUrl"), ("Referrer gốc", "rawReferrer"), ("UTM Source", "utmSource"), ("UTM Medium", "utmMedium"), ("Chiến dịch", "utmCampaign"), ("UTM Content", "utmContent"), ("UTM Term", "utmTerm"), ("FB Click ID", "fbclid"), ("Google Click ID", "gclid"), ("TikTok Click ID", "ttclid"), ("Nội dung CK", "memo"), ("Mã giao dịch", "paymentTxId"), ("Cổng thanh toán", "paymentSource"), ("Voucher", "couponCode"), ("Link cấp", "licenseLink"), ("Trạng thái", "status")]
    lines = ["🟢 <b>ĐƠN HÀNG ĐÃ THANH TOÁN (" + escape(str(order.get("amount") or "")) + ")</b>"]
    for label, key in fields:
        value = order.get(key)
        if not value and key in ("ip", "location", "referrer"):
            value = "Không xác định"
        if value:
            lines.append(f"<b>{label}:</b> <code>{escape(str(value)[:80])}</code>")
    return "\n".join(lines)

def send_payment_success_notification(order):
    return send_telegram_raw(get_payment_success_template(order))

def get_low_stock_template(current_stock=0, threshold=5):
    return f"""⚠️ <b>CẢNH BÁO: KHO SẮP HẾT</b>
Kho License còn: <b>{current_stock} mã</b> (Ngưỡng: &lt;= {threshold})
👉 Mua thêm tại bot: https://t.me/shopxoainon_bot
Nạp vào kho tại: /admin"""

def get_daily_report_template(stats=None):
    if not stats:
        stats = {
            "date": datetime.now().strftime("%d/%m/%Y"),
            "traffic": 312,
            "orders": 28,
            "revenue": "2.520.000 VNĐ",
            "cr": "9.0%",
            "stock": 16
        }
    return f"""📊 <b>BÁO CÁO NGÀY ({stats.get('date')})</b>
Doanh thu: <b>{stats.get('revenue')}</b> ({stats.get('orders')} đơn)
Traffic: {stats.get('traffic')} lượt (CR: {stats.get('cr')})
Kho còn: {stats.get('stock')} mã khả dụng"""

def get_admin_login_template(data=None):
    if not data:
        data = {}
    time_str = data.get("time", datetime.now().strftime("%H:%M %d/%m/%Y"))
    ip = data.get("ip", "127.0.0.1")
    location = data.get("location", "Việt Nam")
    device = data.get("device", "Desktop PC • Chrome")

    return f"""🛡️ <b>ĐĂNG NHẬP ADMIN THÀNH CÔNG</b>
Thời gian: {time_str}
IP: <code>{ip}</code> ({location})
Thiết bị: {device}"""

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["admin_login", "payment_success", "low_stock", "daily_report", "raw", "test_all"], default="test_all")
    parser.add_argument("--data", help="JSON data string for order")
    parser.add_argument("--file", help="Path to file containing JSON data or raw text")
    parser.add_argument("--raw", help="Raw HTML message to send")
    parser.add_argument("--token", default=None)
    parser.add_argument("--chat_id", default=None)
    args = parser.parse_args()

    order_data = {}
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8-sig") as f:
                content = f.read().strip()
                if args.type == "raw":
                    args.raw = content
                else:
                    order_data = json.loads(content)
        except Exception as e:
            sys.stderr.write(f"File read error: {e}\n")
    elif args.data:
        try:
            order_data = json.loads(args.data)
        except:
            pass

    if args.type == "raw" and args.raw:
        ok = send_telegram_raw(args.raw, args.token, args.chat_id)
        print("Sent raw:", ok)
    elif args.type == "admin_login":
        msg = get_admin_login_template(order_data)
        ok = send_telegram_raw(msg, args.token, args.chat_id)
        print("Sent admin_login:", ok)
    elif args.type == "payment_success":
        msg = get_payment_success_template(order_data)
        ok = send_telegram_raw(msg, args.token, args.chat_id)
        print("Sent payment_success:", ok)
    elif args.type == "low_stock":
        msg = get_low_stock_template()
        ok = send_telegram_raw(msg, args.token, args.chat_id)
        print("Sent low_stock:", ok)
    elif args.type == "daily_report":
        msg = get_daily_report_template()
        ok = send_telegram_raw(msg, args.token, args.chat_id)
        print("Sent daily_report:", ok)
    elif args.type == "test_all":
        import time
        print("Sending 3 business notification types (Đơn thành công, Cảnh báo kho, Báo cáo ngày)...")
        
        sample_order = {
            "orderId": "#GEM-7492",
            "name": "Nguyễn Hoàng Nam",
            "phone": "0912345678",
            "email": "hoangnam.ai@gmail.com",
            "amount": "90.000 VNĐ",
            "memo": "PRO18T 0912345678",
            "ip": "113.161.42.18",
            "location": "TP. Hồ Chí Minh",
            "referrer": "Facebook Ads",
            "licenseLink": "https://one.google.com/promo/gemini-pro/ACT-NAM7492",
            "remainingStock": 16,
            "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }
        
        # 1. Đơn thanh toán thành công
        print("1. Bắn thông báo: Đơn hàng mới thanh toán thành công (90.000đ)...")
        send_telegram_raw(get_payment_success_template(sample_order), args.token, args.chat_id)
        time.sleep(1.2)
        
        # 2. Cảnh báo kho
        print("2. Bắn thông báo: Cảnh báo tồn kho license...")
        send_telegram_raw(get_low_stock_template(current_stock=3, threshold=5), args.token, args.chat_id)
        time.sleep(1.2)
        
        # 3. Báo cáo doanh thu ngày
        print("3. Bắn thông báo: Báo cáo doanh thu tổng kết ngày...")
        send_telegram_raw(get_daily_report_template(), args.token, args.chat_id)
        
        print("Hoàn tất bắn 3 thông báo chuẩn đẹp (Đơn thành công, Cảnh báo kho, Báo cáo ngày) về Telegram!")
