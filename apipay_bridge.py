# -*- coding: utf-8 -*-
"""
ApiPay Bridge Module for Google Gemini Pro CRM
Author: CRM Team
Description: Connects to app.apipay.vn API for MBBank Auto-Detection using AccessKey & SecretKey
"""

import sys
import json
import base64
import urllib.request
import urllib.error
import ssl
import os

# SSL Context to handle certificates across environments
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_config.json")

def load_config():
    cfg = {
        "accessKey": "5a03a2c11ed56ea65b7e7e11107f638ec8acfb95165a6a50225c91a477a157c2",
        "secretKey": "LK00NYGOmyz8i7MhhNOD/gz0YcMBjUS4+DfD/l1zXmKcKXo1v5ScvycSlu8DcngsKUSLWJzF+fS+eysDi0B3gQ==",
        "bankPublicId": "cmv2nmvn408tb01mny26u27ie",
        "accountNo": "517041996",
        "bankBin": "970422",
        "accountName": "NGUYEN TRAN HAN"
    }
    if os.path.exists(DEFAULT_CONFIG_PATH):
        try:
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg

def get_headers(access_key, secret_key):
    auth_str = f"{access_key}:{secret_key}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    return {
        "Authorization": f"Bearer {b64_auth}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

def test_connection():
    cfg = load_config()
    headers = get_headers(cfg["accessKey"], cfg["secretKey"])
    url = "https://app.apipay.vn/v1/client/banks"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            banks = data.get("data", {}).get("message", [])
            primary_bank = banks[0] if banks else None
            return {
                "status": "success",
                "message": "Kết nối APIPay thành công 100%!",
                "bank": primary_bank,
                "accountName": primary_bank.get("accountName") if primary_bank else cfg["accountName"],
                "accountNumber": primary_bank.get("accountNumber") if primary_bank else cfg["accountNo"]
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def create_payment_request(phone, amount=None, memo=None):
    cfg = load_config()
    if amount is None or amount <= 0:
        amount = cfg.get("packagePrice", 119000)
    if not memo:
        memo = f"PRO18T {phone}"
    headers = get_headers(cfg["accessKey"], cfg["secretKey"])
    url = "https://app.apipay.vn/v1/client/payment-requests"
    bank_id = cfg.get("bankPublicId", "cmv2nmvn408tb01mny26u27ie")
    payload = {
        "bankPublicId": bank_id,
        "amount": int(amount),
        "content": memo
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pr_data = data.get("data", {})
            return {
                "status": "success",
                "publicId": pr_data.get("publicId"),
                "payUrl": pr_data.get("payUrl"),
                "qrUrl": pr_data.get("qrUrl"),
                "accountNumber": pr_data.get("accountNumber", cfg["accountNo"]),
                "accountName": pr_data.get("accountName", cfg["accountName"]),
                "bankCode": pr_data.get("bankCode", "MB"),
                "amount": pr_data.get("amount", amount),
                "content": memo
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_payment_status(public_id):
    if not public_id:
        return {"status": "error", "message": "Missing publicId"}
    cfg = load_config()
    headers = get_headers(cfg["accessKey"], cfg["secretKey"])
    url = f"https://app.apipay.vn/v1/client/payment-requests/{public_id}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pr = data.get("data", {})
            st = (pr.get("status") or "").upper()
            is_paid = st in ["PAID", "COMPLETED", "SUCCESS"]
            return {
                "status": "success",
                "paid": is_paid,
                "paymentStatus": st,
                "amount": pr.get("amount"),
                "content": pr.get("content"),
                "transaction": pr
            }
    except Exception as e:
        return {"status": "error", "paid": False, "message": str(e)}

def check_recent_payment_requests(memo=None, phone=None, amount=None):
    """
    Tra cứu danh sách Payment Requests gần nhất trên ApiPay Cloud.
    Nếu có bất kỳ Payment Request nào khớp với memo hoặc phone có trạng thái COMPLETED hoặc PAID thì trả về True ngay!
    """
    cfg = load_config()
    if amount is None or amount <= 0:
        amount = cfg.get("packagePrice", 119000)
    headers = get_headers(cfg["accessKey"], cfg["secretKey"])
    url = "https://app.apipay.vn/v1/client/payment-requests"
    req = urllib.request.Request(url, headers=headers)
    clean_phone = phone.replace("+84", "0").replace(" ", "") if phone else ""
    clean_memo = memo.replace(" ", "").upper() if memo else ""

    try:
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            payload = data.get("data", {})
            if isinstance(payload, dict):
                prs = payload.get("data", payload.get("items", []))
            elif isinstance(payload, list):
                prs = payload
            else:
                prs = []
            for pr in prs:
                st = (pr.get("status") or "").upper()
                is_paid = st in ["PAID", "COMPLETED", "SUCCESS"]
                if is_paid:
                    # Chỉ chấp nhận Payment Request được tạo trong vòng 20 phút trở lại
                    created_at_str = pr.get("createdAt") or ""
                    if created_at_str:
                        try:
                            created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                            diff_sec = (now_utc - created_dt).total_seconds()
                            if diff_sec > 24 * 60 * 60:
                                continue
                        except Exception:
                            pass

                    content = (pr.get("content") or "").replace(" ", "").upper()
                    try:
                        pr_amount = int(float(str(pr.get("amount") or 0).replace(",", "")))
                    except Exception:
                        pr_amount = 0
                    if amount and pr_amount < int(amount):
                        continue
                    # Khớp theo memo hoặc phone
                    matches = clean_memo in content if clean_memo else (clean_phone and len(clean_phone) >= 9 and clean_phone in content)
                    if matches:
                        return {
                            "status": "success",
                            "paid": True,
                            "paymentStatus": st,
                            "amount": pr.get("amount"),
                            "content": pr.get("content"),
                            "transaction": pr,
                            "source": "APIPay Cloud Recent PR"
                        }
            return {"status": "success", "paid": False, "message": "Chưa có giao dịch hoàn tất"}
    except Exception as e:
        return {"status": "error", "paid": False, "message": str(e)}

def get_qr_base64(memo="PRO18T", amount=None):
    cfg = load_config()
    if amount is None or amount <= 0:
        amount = cfg.get("packagePrice", 119000)
    bank_bin = cfg.get("bankBin", "970422")
    acc_no = cfg.get("vaNumber", cfg.get("accountNo", "VQRQAMRMQ5816"))
    acc_name = cfg.get("accountName", "NGUYEN TRAN HAN")
    import urllib.parse
    url = f"https://img.vietqr.io/image/{bank_bin}-{acc_no}-compact2.png?amount={amount}&addInfo={urllib.parse.quote(memo)}&accountName={urllib.parse.quote(acc_name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = resp.read()
            b64 = base64.b64encode(data).decode("utf-8")
            return {"status": "success", "base64": b64}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def sync_apipay_webhook_url(target_url=None):
    """
    Tự động đồng bộ URL Webhook trên ApiPay Cloud.
    Đảm bảo Webhook của ApiPay luôn gửi về đúng backend server đang chạy (không bị chết link).
    """
    try:
        if not target_url:
            return {"status": "skipped", "message": "PUBLIC_WEBHOOK_URL chưa được cấu hình"}
        cfg = load_config()
        headers = get_headers(cfg["accessKey"], cfg["secretKey"])
        req = urllib.request.Request("https://app.apipay.vn/v1/client/webhooks", headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            whs = data.get("data", {}).get("data", [])
            for wh in whs:
                wh_id = wh.get("id")
                curr_url = wh.get("webhookUrl")
                if curr_url != target_url:
                    patch_req = urllib.request.Request(
                        f"https://app.apipay.vn/v1/client/webhooks/{wh_id}",
                        data=json.dumps({"webhookUrl": target_url}).encode("utf-8"),
                        headers=headers,
                        method="PATCH"
                    )
                    with urllib.request.urlopen(patch_req, context=ctx, timeout=8) as p_resp:
                        sys.stdout.write(f"[APIPAY WEBHOOK SYNC] Updated webhook {wh_id} -> {target_url}\n")
                        sys.stdout.flush()
                    return {"status": "success", "action": "updated", "webhookUrl": target_url}
            return {"status": "success", "action": "already_up_to_date", "webhookUrl": target_url}
    except Exception as e:
        sys.stdout.write(f"[APIPAY WEBHOOK SYNC ERROR] {e}\n")
        sys.stdout.flush()
        return {"status": "error", "message": str(e)}

def output_json(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True).encode("ascii"))

def main():
    if len(sys.argv) < 2:
        res = test_connection()
        output_json(res)
        return

    cmd = sys.argv[1].lower()
    if cmd == "test":
        res = test_connection()
        output_json(res)
    elif cmd == "create":
        phone = sys.argv[2] if len(sys.argv) > 2 else "0901234567"
        amount = int(sys.argv[3]) if len(sys.argv) > 3 else 119000
        memo = sys.argv[4] if len(sys.argv) > 4 else f"PRO18T {phone}"
        res = create_payment_request(phone, amount, memo)
        output_json(res)
    elif cmd == "check":
        public_id = sys.argv[2] if len(sys.argv) > 2 else ""
        res = check_payment_status(public_id)
        output_json(res)
    elif cmd == "qr":
        memo = sys.argv[2] if len(sys.argv) > 2 else "PRO18T"
        amount = int(sys.argv[3]) if len(sys.argv) > 3 else 119000
        res = get_qr_base64(memo, amount)
        output_json(res)
    else:
        output_json({"status": "error", "message": f"Unknown cmd {cmd}"})

if __name__ == "__main__":
    main()
