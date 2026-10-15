# -*- coding: utf-8 -*-
"""
Telegram Userbot Auto Buyer for @shopxoainon_bot
Tự động gõ /buy -> Chọn Gói Gemini 18 Tháng (5p) -> Bấm số 1 -> Bấm Trừ ví -> Bóc tách link Google Service
"""
import os
import re
import sys
import json
import asyncio
from datetime import datetime

# Cấu hình API Telegram lấy từ người dùng
API_ID = 35960524
API_HASH = "84ccced1603c27fdec1051965e31c6dc"
SESSION_FILE = "userbot_session"
BOT_USERNAME = "shopxoainon_bot"
ADMIN_BOT_TOKEN = "7942171549:AAEBc_r5z8e05ZtL-m1Z_6yX-1z7j7818Y8"  # Token bot thông báo admin nếu có
ADMIN_CHAT_ID = "6828551915"

try:
    from telethon import TelegramClient, events
    from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
except ImportError:
    print("Vui lòng cài đặt Telethon: pip install telethon")
    sys.exit(1)

def get_client():
    return TelegramClient(SESSION_FILE, API_ID, API_HASH)

async def check_is_authorized():
    client = get_client()
    await client.connect()
    is_auth = await client.is_user_authorized()
    await client.disconnect()
    return is_auth

async def request_otp(phone_number):
    """Bước 1: Gửi yêu cầu mã OTP đăng nhập về app Telegram"""
    client = get_client()
    await client.connect()
    
    if await client.is_user_authorized():
        await client.disconnect()
        return {"status": "already_authorized", "message": "Tài khoản đã đăng nhập sẵn rồi!"}
    
    clean_phone = phone_number.strip().replace(" ", "")
    if clean_phone.startswith("0"):
        clean_phone = "+84" + clean_phone[1:]
    elif not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone

    res = await client.send_code_request(clean_phone)
    # Lưu phone_code_hash vào file tạm
    with open("temp_login.json", "w", encoding="utf-8") as f:
        json.dump({
            "phone": clean_phone,
            "phone_code_hash": res.phone_code_hash
        }, f)
        
    await client.disconnect()
    return {
        "status": "code_sent",
        "phone": clean_phone,
        "phone_code_hash": res.phone_code_hash,
        "message": f"Đã gửi mã xác nhận OTP vào ứng dụng Telegram của số {clean_phone}!"
    }

async def submit_otp(code, password=None):
    """Bước 2: Xác thực mã OTP và mật khẩu 2 bước (nếu có)"""
    if not os.path.exists("temp_login.json"):
        return {"status": "error", "message": "Không tìm thấy phiên đăng nhập. Vui lòng gửi lại số điện thoại!"}
        
    with open("temp_login.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    
    client = get_client()
    await client.connect()
    
    try:
        await client.sign_in(phone=phone, code=code.strip(), phone_code_hash=phone_code_hash)
        me = await client.get_me()
        await client.disconnect()
        if os.path.exists("temp_login.json"):
            os.remove("temp_login.json")
        return {
            "status": "success",
            "user": f"{me.first_name} (@{me.username})",
            "message": "Đăng nhập Telegram Userbot thành công 100%!"
        }
    except SessionPasswordNeededError:
        if password:
            try:
                await client.sign_in(password=password.strip())
                me = await client.get_me()
                await client.disconnect()
                if os.path.exists("temp_login.json"):
                    os.remove("temp_login.json")
                return {
                    "status": "success",
                    "user": f"{me.first_name} (@{me.username})",
                    "message": "Đăng nhập thành công với mật khẩu 2FA!"
                }
            except Exception as e:
                await client.disconnect()
                return {"status": "error_2fa", "message": f"Mật khẩu 2FA không đúng: {e}"}
        else:
            await client.disconnect()
            return {"status": "need_password", "message": "Tài khoản có bảo mật 2 lớp (2FA). Vui lòng cung cấp mật khẩu 2FA!"}
    except Exception as e:
        await client.disconnect()
        return {"status": "error", "message": f"Lỗi xác thực: {e}"}

async def execute_buy_gemini():
    """
    Tự động thao tác mua gói:
    1. Gửi /buy vào @shopxoainon_bot
    2. Chờ danh sách và bấm nút '🤖 📦 Gói Gemini Pro & Drive 5TB 18 Tháng (dùng ngay trong 5p)'
    3. Chờ thông tin sản phẩm và bấm nút '1'
    4. Kiểm tra số dư ví: nếu thiếu tiền -> báo hết tiền
    5. Bấm nút 'Trừ ví'
    6. Chờ bot giao link và bóc tách đường link https://serviceactivation.google.com/...
    """
    client = get_client()
    await client.connect()
    
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"status": "error", "message": "Userbot chưa được đăng nhập! Vui lòng đăng nhập trước."}
        
    try:
        bot = await client.get_entity(BOT_USERNAME)
        print(f"[*] Đang gửi lệnh /buy vào @{BOT_USERNAME}...")
        
        # 1. Gửi /buy
        await client.send_message(bot, "/buy")
        await asyncio.sleep(2)
        
        # 2. Tìm tin nhắn phản hồi danh sách sản phẩm
        messages = await client.get_messages(bot, limit=5)
        target_msg = None
        target_btn = None
        
        for msg in messages:
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        btn_text = btn.text.lower()
                        # Tìm nút gói Gemini 18 Tháng dùng ngay trong 5p (bỏ qua nút có chữ hết hàng hoặc X đỏ)
                        if "gemini" in btn_text and ("5p" in btn_text or "18 tháng" in btn_text or "dùng ngay" in btn_text):
                            if "❌" not in btn.text and "hết hàng" not in btn_text:
                                target_msg = msg
                                target_btn = btn
                                break
                    if target_btn:
                        break
            if target_btn:
                break
                
        if not target_btn:
            await client.disconnect()
            return {
                "status": "out_of_stock_in_bot",
                "message": "Không tìm thấy nút mua hoặc Gói Gemini 18T trong bot @shopxoainon_bot hiện đang HẾT HÀNG!"
            }
            
        print(f"[*] Đã tìm thấy nút: '{target_btn.text}'. Đang bấm...")
        await target_btn.click()
        await asyncio.sleep(2)
        
        # 3. Chờ tin nhắn 'THÔNG TIN SẢN PHẨM' và bấm nút '1'
        messages = await client.get_messages(bot, limit=3)
        btn_one = None
        for msg in messages:
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        if btn.text.strip() == "1":
                            btn_one = btn
                            break
                    if btn_one:
                        break
            if btn_one:
                break
                
        if not btn_one:
            await client.disconnect()
            return {"status": "error", "message": "Không tìm thấy nút số lượng '1'!"}
            
        print("[*] Đang bấm chọn số lượng: 1...")
        await btn_one.click()
        await asyncio.sleep(2)
        
        # 4. Kiểm tra trang 'CHỌN PHƯƠNG THỨC THANH TOÁN'
        messages = await client.get_messages(bot, limit=3)
        payment_msg = None
        btn_tru_vi = None
        
        for msg in messages:
            msg_text = msg.text or ""
            # Kiểm tra xem có cảnh báo thiếu tiền không
            if "ví chưa đủ" in msg_text.lower() or "thiếu" in msg_text.lower():
                await client.disconnect()
                return {
                    "status": "insufficient_balance",
                    "raw_text": msg_text,
                    "message": "⚠️ VÍ BOT @shopxoainon_bot KHÔNG ĐỦ TIỀN! Vui lòng nạp thêm tiền vào bot để tiếp tục mua tự động."
                }
                
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        if "trừ ví" in btn.text.lower():
                            payment_msg = msg
                            btn_tru_vi = btn
                            break
                    if btn_tru_vi:
                        break
            if btn_tru_vi:
                break
                
        if not btn_tru_vi:
            await client.disconnect()
            return {
                "status": "insufficient_balance_or_no_button",
                "message": "Không tìm thấy nút 'Trừ ví' hoặc ví chưa đủ tiền thanh toán 12.800đ!"
            }
            
        print(f"[*] Đang bấm: '{btn_tru_vi.text}'...")
        await btn_tru_vi.click()
        
        # 5. Chờ bot giao link (Bot có thể mất từ 5s đến 90s để nguồn API trả link)
        print("[*] Đã thanh toán trừ ví thành công. Đang lắng nghe tin nhắn giao link từ bot...")
        
        link_found = None
        # Vòng lặp chờ tối đa 90 giây
        for wait_round in range(18):
            await asyncio.sleep(5)
            latest_msgs = await client.get_messages(bot, limit=5)
            for m in latest_msgs:
                full_text = m.text or ""
                # Tìm link Google Activation
                match = re.search(r'(https?://(?:serviceactivation\.google\.com|one\.google\.com)[^\s\n\r<>"\']+)', full_text)
                if match:
                    link_found = match.group(1).strip()
                    break
            if link_found:
                break
                
        await client.disconnect()
        
        if link_found:
            print(f"[SUCCESS] Đã bóc tách link thành công: {link_found}")
            return {
                "status": "success",
                "license_link": link_found,
                "message": "Mua link thành công từ bot @shopxoainon_bot!"
            }
        else:
            return {
                "status": "pending_delivery",
                "message": "Đã trừ ví thành công nhưng bot đang chờ nguồn API giao link (có thể mất 1-3 phút)."
            }
            
    except Exception as e:
        await client.disconnect()
        return {"status": "error", "message": f"Lỗi trong quá trình thao tác bot: {str(e)}"}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "request_otp":
            phone = sys.argv[2] if len(sys.argv) > 2 else ""
            res = asyncio.run(request_otp(phone))
            print(json.dumps(res, ensure_ascii=False))
        elif cmd == "submit_otp":
            code = sys.argv[2] if len(sys.argv) > 2 else ""
            pwd = sys.argv[3] if len(sys.argv) > 3 else None
            res = asyncio.run(submit_otp(code, pwd))
            print(json.dumps(res, ensure_ascii=False))
        elif cmd == "buy":
            res = asyncio.run(execute_buy_gemini())
            print(json.dumps(res, ensure_ascii=False))
        elif cmd == "check_auth":
            res = asyncio.run(check_is_authorized())
            print(json.dumps({"is_authorized": res}))
    else:
        print("Usage: python telegram_buyer.py [request_otp <phone> | submit_otp <code> [pwd] | buy | check_auth]")
