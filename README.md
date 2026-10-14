# 🚀 Hệ Thống Bán Tài Khoản Google Gemini Pro 18 Tháng Tự Động & CRM Doanh Nghiệp

Hệ thống bán hàng trực tuyến và Quản trị khách hàng (CRM) trọn gói, tích hợp cổng thanh toán **API Pay (MBBank VietQR Auto-Detect 0.0s)**, tự động đồng bộ **Google Sheets 12 cột chuẩn**, gửi hóa đơn tự động qua **Gmail SMTP**, và thông báo tức thì về nhóm **Telegram Bot**.

---

## 🌟 Tính Năng Nổi Bật

- ⚡ **Thanh Toán Tự Động 100% Qua VietQR MBBank**:
  - Tự động tạo mã QR động đúng số tiền và cú pháp `PRO18T {SĐT}`.
  - Tự động quét và nhận diện biến động số dư tài khoản MBBank trong 0.0s - 1.5s.
  - Khách quét tiền xong là modal tự động nhảy ngay sang bước kích hoạt license.
- 📊 **Quản Trị CRM Đầy Đủ (Admin Dashboard)**:
  - **Bảo mật**: Đăng nhập bằng mã bảo mật, tự động bắn cảnh báo IP & thiết bị về Telegram khi Admin đăng nhập.
  - **Quản lý đơn hàng**: Xem chi tiết, gắn nhãn ghi chú, trạng thái đơn, lọc theo ngày.
  - **Quản lý kho License**: Cấp phát tự động, nạp thêm mã hàng loạt, cảnh báo khi tồn kho thấp.
  - **Theo dõi Traffic Real-time**: Bắt IP thật, vị trí địa lý, trình duyệt và phân loại 7 kênh nguồn (Facebook Ads, TikTok, Google Search, Zalo Chat...).
  - **Nhật ký biến động số dư ngân hàng**: Xem luồng tiền vào MBBank theo thời gian thực.
- 📈 **Đồng Bộ Dữ Liệu Google Sheets (Chuẩn 12 Cột)**:
  - Tự động ghi nhận mọi đơn hàng vào Google Sheet với đầy đủ 12 cột: `Ngày Giờ`, `Mã Đơn`, `Sản Phẩm`, `Giá Tiền`, `Họ Tên`, `Số Điện Thoại (giữ nguyên số 0)`, `Gmail`, `Nội Dung CK`, `Link Bản Quyền`, `Nguồn Khách`, `IP & Vị Trí`, `Trạng Thái`.
  - Tự động tạo dòng tiêu đề màu xanh đen Dark Navy `#0f172a` nếu trang tính chưa có.
- 🔔 **Thông Báo Telegram Bot Siêu Gọn (Chỉ 1 Icon Quan Trọng)**:
  - 🟢 **Đơn Hàng Mới**: Gửi tức thì khi khách thanh toán thành công (kèm link cấp, cú pháp CK, mã đơn dạng `<code>` để 1-tap copy).
  - ⚠️ **Cảnh Báo Tồn Kho**: Tự động báo khi số lượng license trong kho `<= 5`.
  - 📊 **Báo Cáo Tổng Kết Ngày**: Doanh thu, số đơn, traffic, tỷ lệ chuyển đổi (CR).
  - 🛡️ **Bảo Mật Admin**: Báo cáo khi có lượt đăng nhập vào trang Quản trị.
- ✉️ **Gửi Email Hóa Đơn & Bản Quyền Tự Động**:
  - Gửi email định dạng HTML chuyên nghiệp từ Gmail cá nhân / doanh nghiệp đến khách hàng ngay khi xác nhận thanh toán.

---

## 📁 Cấu Trúc Thư Mục Dự Án

```
webbantaikhoangemini/
├── index.html                       # Giao diện Landing Page bán hàng & Modal VietQR API Pay
├── admin.html                       # Bảng điều khiển CRM Quản trị viên
├── server.ps1                       # Backend HTTP Server (REST API trên cổng 8080)
├── START_SERVER.bat                 # Khởi động nhanh Server chỉ với 1 click
├── apipay_bridge.py                 # Module kết nối API Pay MBBank Cloud
├── telegram_sender.py               # Module gửi thông báo Telegram chuẩn UTF-8
├── mailer.py                        # Module gửi Email hóa đơn qua Gmail SMTP
├── GoogleAppsScript_CRM_AutoBot.js  # Mã nguồn Google Apps Script đồng bộ Sheet & Bot
├── payment_config.json              # File cấu hình cổng thanh toán & Google Sheet Webhook
├── telegram_config.json             # File cấu hình Bot Token & Chat ID Telegram
├── default_qr.txt                   # Dữ liệu ảnh VietQR dự phòng
├── HUONG_DAN_SU_DUNG.txt            # Tài liệu hướng dẫn vận hành chi tiết
└── assets/                          # Hình ảnh sản phẩm & banner
```

---

## 🚀 Hướng Dẫn Cài Đặt & Vận Hành

### 1. Yêu Cầu Môi Trường
- Hệ điều hành: Windows 10 / 11 / Windows Server
- Đã cài đặt **Python 3.8+** và **PowerShell**

### 2. Các Lựa Chọn Triển Khai Lên Hosting (Đầy Đủ 100%)

#### 🌐 Lựa chọn A: Hosting cPanel / DirectAdmin / PHP (Hostinger, AZDIGI, Vietnix, TinoHost...)
1. Nén toàn bộ các file trong thư mục này thành file `.zip`.
2. Tải lên thư mục `public_html/` trên hosting của bạn và giải nén.
3. Hệ thống đã có sẵn `.htaccess`, thư mục `admin/` và `api.php` tự động nhận diện và xử lý mọi API mà không cần cài đặt thêm bất cứ thứ gì!

#### 🚀 Lựa chọn B: Hosting Nginx (aaPanel, FastPanel, CloudPanel, Nginx Server)
1. Tải toàn bộ mã nguồn lên thư mục web của Nginx (ví dụ `/www/wwwroot/webbantaikhoangemini`).
2. Dự án đã cấu trúc sẵn thư mục `admin/index.html` và `admin/index.php` nên bạn có thể truy cập ngay `domain.com/admin` mà không bị lỗi 404!
3. (Tùy chọn) Thao khảo file mẫu [nginx.conf.example](file:///c:/Users/Admin/Desktop/GI%C3%80U%20SANG%20PH%C3%9A%20QU%C3%9D/gemini-pro-crm-fullsource/nginx.conf.example) để cấu hình rewrite `/api/` mượt mà nhất.

#### 🐧 Lựa chọn C: VPS Linux (Ubuntu / Debian / CentOS / Docker)
Chạy lệnh khởi động máy chủ Python hiệu năng cao tích hợp sẵn:
```bash
python3 server.py
# Hoặc chạy nền qua PM2:
pm2 start server.py --name "gemini-crm" --interpreter python3
```

#### 💻 Lựa chọn D: Chạy cục bộ trên máy tính Windows
Nhấp đúp chuột vào file `START_SERVER.bat` hoặc mở terminal chạy:
```powershell
powershell -ExecutionPolicy Bypass -File .\server.ps1
```

- Truy cập trang bán hàng cho khách: `http://localhost:8080/` (hoặc tên miền của bạn)
- Truy cập trang Quản trị CRM: `http://localhost:8080/admin` (Mật khẩu: `Khoi@123`)

---

## ⚙️ Cấu Hình Tích Hợp

### 1. Cấu hình Telegram Bot
Chỉnh sửa trong [telegram_config.json](file:///c:/Users/Admin/Desktop/GI%C3%80U%20SANG%20PH%C3%9A%20QU%C3%9D/gemini-pro-crm-fullsource/telegram_config.json) hoặc cấu hình trực tiếp từ giao diện Admin:
```json
{
  "botToken": "8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c",
  "chatId": "-1004413665683",
  "lowStockThreshold": 5,
  "dailyReportTime": "10:00",
  "enabled": true
}
```

### 2. Cấu hình Google Sheets & Apps Script
1. Mở file [GoogleAppsScript_CRM_AutoBot.js](file:///c:/Users/Admin/Desktop/GI%C3%80U%20SANG%20PH%C3%9A%20QU%C3%9D/gemini-pro-crm-fullsource/GoogleAppsScript_CRM_AutoBot.js).
2. Vào Google Sheet của bạn ➜ **Tiện ích mở rộng** ➜ **Apps Script** ➜ Dán toàn bộ mã nguồn.
3. Bấm **Triển khai (Deploy)** ➜ **Tùy chọn triển khai mới** ➜ Chọn **Ứng dụng web (Web App)**:
   - Thực thi dưới dạng: **Tôi (tài khoản của bạn)**
   - Ai có quyền truy cập: **Bất kỳ ai (Anyone)**
4. Sao chép URL Web App dạng `https://script.google.com/macros/s/.../exec` dán vào ô Webhook trong trang Quản trị CRM và bấm **Lưu Cấu Hình**.

---

## 🔒 Bảo Mật & Bản Quyền

- Bản quyền thuộc về **Gemini Pro Enterprise Vietnam**.
- Hotline / Zalo hỗ trợ: `0567.960.777`.
- Chính sách bảo hành: `30 Ngày (Cam kết 1 đổi 1)`.
