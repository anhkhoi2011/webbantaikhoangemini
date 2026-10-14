import sys
import json
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def strip_tags(html):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html)

def send_email_from_json(json_str):
    try:
        data = json.loads(json_str)
        sender_email = (data.get("senderEmail") or "nguyenhanocb1@gmail.com").strip()
        sender_name = (data.get("senderName") or "Google Gemini Pro Support VN").strip()
        sender_pass = (data.get("senderPassword") or "mfam krzt mygf upll").strip().replace(" ", "")
        recipient = data.get("recipient", "").strip()
        subject = data.get("subject", "Hướng dẫn kích hoạt Google Gemini Pro & Bộ nhớ 5TB").strip()
        html_body = data.get("htmlBody", "<p>Email kích hoạt bản quyền</p>")

        if not recipient or not sender_pass:
            out = json.dumps({"status": "error", "message": "Vui lòng nhập email người nhận và mật khẩu ứng dụng Gmail!"}, ensure_ascii=True)
            sys.stdout.buffer.write(out.encode('utf-8') + b'\n')
            return

        msg = MIMEMultipart("alternative")
        # Standard RFC formataddr with Header encoding so display name matches exact client expectations
        from_display = Header(sender_name, 'utf-8').encode()
        msg["From"] = formataddr((from_display, sender_email))
        msg["To"] = recipient
        msg["Reply-To"] = sender_email
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="gmail.com")
        msg["MIME-Version"] = "1.0"
        msg["X-Mailer"] = "Google Gemini Pro Dispatcher"

        # 1. Plain text fallback part (Crucial for spam filter pass score)
        plain_text = f"""Xin chào Bạn,

Hệ thống gửi tới bạn thông tin và đường link nhận gói Google Gemini Pro 18 Tháng (5TB Cloud):

HƯỚNG DẪN 2 CÁCH KÍCH HOẠT:
Cách 1 (Nhanh): Mở liên kết kích hoạt trên trình duyệt đang đăng nhập tài khoản Gmail cần nâng cấp, sau đó nhấn "Tham gia / Chấp nhận" để nhận ngay 5TB dung lượng.
Cách 2 (Cho Gmail khác): Sao chép đường link, mở tab trình duyệt mới đang đăng nhập tài khoản Gmail cần nâng cấp, dán link vào thanh địa chỉ rồi nhấn "Tham gia".

Chính sách bảo hành: 30 Ngày (Cam kết 1 đổi 1)
Hotline & Zalo hỗ trợ kỹ thuật: 0567.960.777

Trân trọng,
Google Gemini Pro Support VN
"""
        part_text = MIMEText(plain_text, "plain", "utf-8")
        msg.attach(part_text)

        # 2. HTML formatted part
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # Connect and send
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=25)
        server.starttls()
        server.login(sender_email, sender_pass)
        server.sendmail(sender_email, [recipient], msg.as_bytes())
        server.quit()

        out = json.dumps({"status": "success", "message": f"Đã gửi email thành công tới {recipient}"}, ensure_ascii=True)
        sys.stdout.buffer.write(out.encode('utf-8') + b'\n')
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        out = json.dumps({"status": "error", "message": str(e)}, ensure_ascii=True)
        sys.stdout.buffer.write(out.encode('utf-8') + b'\n')

if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            content = f.read()
        send_email_from_json(content)
    else:
        content = sys.stdin.read()
        send_email_from_json(content)
