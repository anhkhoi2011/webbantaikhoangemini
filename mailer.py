# -*- coding: utf-8 -*-
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

def send_activation_email(data):
    """
    Hàm gửi email bản quyền thực tế qua Gmail SMTP
    Trả về dict: {"status": "success" | "error", "message": ...}
    """
    try:
        if isinstance(data, str):
            data = json.loads(data)

        sender_email = (data.get("senderEmail") or "nguyenhanocb1@gmail.com").strip()
        sender_name = (data.get("senderName") or "Google Gemini Pro Support VN").strip()
        sender_pass = (data.get("senderPassword") or "mfam krzt mygf upll").strip().replace(" ", "")
        recipient = (data.get("recipient") or "").strip()
        subject = (data.get("subject") or "Hướng dẫn kích hoạt Google Gemini Pro & Bộ nhớ 5TB").strip()
        html_body = data.get("htmlBody") or "<p>Email kích hoạt bản quyền</p>"

        if not recipient:
            return {"status": "error", "message": "Vui lòng nhập email người nhận!"}
        if not sender_pass:
            return {"status": "error", "message": "Vui lòng cấu hình mật khẩu ứng dụng Gmail!"}

        msg = MIMEMultipart("alternative")
        from_display = Header(sender_name, 'utf-8').encode()
        msg["From"] = formataddr((from_display, sender_email))
        msg["To"] = recipient
        msg["Reply-To"] = sender_email
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="gmail.com")
        msg["MIME-Version"] = "1.0"
        msg["X-Mailer"] = "Google Gemini Pro Dispatcher"

        # 1. Plain text fallback part (Crucial for anti-spam filters)
        plain_text = strip_tags(html_body)
        if not plain_text.strip():
            plain_text = f"""Xin chào,\n\nCảm ơn bạn đã đăng ký gói Google Gemini Pro 18 Tháng (5TB Cloud).\nVui lòng mở email ở chế độ HTML để kích hoạt đường link bản quyền.\nHotline hỗ trợ: 0567.960.777"""
        part_text = MIMEText(plain_text, "plain", "utf-8")
        msg.attach(part_text)

        # 2. HTML formatted part
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # Connect and send via Gmail SMTP
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=25)
        server.starttls()
        server.login(sender_email, sender_pass)
        server.sendmail(sender_email, [recipient], msg.as_bytes())
        server.quit()

        return {"status": "success", "message": f"Đã gửi email thành công tới {recipient}"}
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {"status": "error", "message": str(e)}

def send_email_from_json(json_str):
    try:
        data = json.loads(json_str)
        res = send_activation_email(data)
        out = json.dumps(res, ensure_ascii=False)
        sys.stdout.buffer.write(out.encode('utf-8') + b'\n')
    except Exception as e:
        out = json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        sys.stdout.buffer.write(out.encode('utf-8') + b'\n')

if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            content = f.read()
        send_email_from_json(content)
    else:
        content = sys.stdin.read()
        send_email_from_json(content)
