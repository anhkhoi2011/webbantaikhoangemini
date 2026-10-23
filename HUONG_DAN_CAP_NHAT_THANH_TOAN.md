Bản sửa thanh toán và thông báo ngày 23/10/2026

Đã sửa lỗi payload new_order có amount bị nhận nhầm là webhook ngân hàng. Một mã đơn cập nhật một dòng, giao dịch gửi lại không tạo UUID/đơn mới. Apps Script dùng khóa khi ghi Sheet và lưu trạng thái Telegram theo từng chat. Nhóm cũ -1004413665683 và nhóm mới -5585627393 đều nhận đơn.

Google Sheet giữ 12 cột cũ và bổ sung thành 40 cột: tên miền; lúc tạo đơn, thanh toán, vào trang; IP/vị trí ước lượng; thiết bị/trình duyệt; URL/referrer; UTM source/medium/campaign/content/term; fbclid/gclid/ttclid; mã/khóa giao dịch; cổng thanh toán; voucher/giảm giá; phiên truy cập; user agent và trạng thái gửi. Giá trị không có dữ liệu được để trống hoặc ghi Không xác định. Thời gian hiển thị GMT+7. Telegram rút gọn giá trị quá dài; Sheet giữ dữ liệu đầy đủ.

Thứ tự cập nhật bắt buộc:

1. Mở project Apps Script hiện đang liên kết trong payment_config.json (appsScriptProjectUrl).
2. Thay nội dung file script trong project Google bằng toàn bộ GoogleAppsScript_CRM_AutoBot.js ở thư mục này rồi lưu.
3. Chọn Deploy → Manage deployments → biểu tượng sửa của Web App đang dùng → Version: New version → Deploy. Dùng lại deployment hiện tại để giữ nguyên URL /exec trong cấu hình.
4. Mở URL googleSheetWebhookUrl kèm ?action=health. Phản hồi phải có protocolVersion: 2 và columns: 40.
5. Cập nhật các file website/backend từ thư mục này lên hosting đang chạy. Nếu chạy Windows, khởi động lại START_SERVER.bat/server.ps1; server.ps1 hiện gọi backend Python chung để tránh ba phiên bản xử lý khác nhau. Máy cần Python 3.8+.
6. Vào Admin → Đồng bộ toàn bộ đơn sang Google Sheet để cập nhật dữ liệu cũ. Đồng bộ dùng sync_order: cập nhật cùng mã đơn, không gửi lại Telegram/email hay cấp thêm link. Chỉ có thể bổ sung các trường đã từng thu thập; không thể suy ra IP/nguồn khách chưa được lưu trước đây.
7. Thử một giao dịch mới có nội dung chuyển khoản riêng của đơn. Kiểm tra DON_HANG, GIAO_DICH và cả hai chat Telegram. Không tự tạo đơn thanh toán giả trong dữ liệu thật để kiểm tra.

Backend kiểm tra protocolVersion trước khi gửi đơn để không gửi payload mới vào Apps Script cũ đang lỗi. Python tự thử lại cập nhật Sheet/Telegram còn thiếu mỗi 30 giây; trình duyệt giữ các đơn chờ đồng bộ trong localStorage và thử lại khi online. PHP thử đồng bộ khi đơn được ghi/kiểm tra hoặc webhook tới; có thể dùng nút đồng bộ Admin nếu cần gửi lại sau lỗi mạng. Phản hồi no-cors từ trình duyệt không được coi là xác nhận ghi thành công.

Việc triển khai lên tài khoản Google cần phiên đăng nhập/quyền sở hữu Apps Script. File local không tự thay đổi Web App đã triển khai. Khi kiểm tra ngày 23/10/2026, Web App hiện tại vẫn trả health bản cũ, chưa có protocolVersion. Chat mới đã nhận được một tin kiểm tra kết nối (message_id 4).

Kiểm thử tại thư mục project:

    node tests/test_apps_script.cjs
    node tests/test_checkout.cjs
    python -m unittest discover -s tests -p test_payment_flow.py -v

Các kiểm thử dùng dữ liệu tạm/mô phỏng, không gửi đơn/email/Telegram thật và không sửa orders.json thực tế.


Cập nhật bổ sung nguồn khách và thống kê theo link:

- Link khác (kể cả chỉ dùng ref/source hoặc chỉ đổi chiến dịch) tạo ngữ cảnh truy cập mới; không dùng nguồn và UTM của link trước. Tải lại cùng link giữ phiên trong 30 phút; bộ nhớ phiên cũ được làm mới tự động.
- Đơn giữ link, nguồn và chiến dịch tại lúc tạo. Khi khách quay lại từ ngân hàng hoặc mở link khác, bước hoàn tất không ghi đè nguồn của đơn bằng phiên mới.
- Nhật ký truy cập backend giữ nhãn nguồn và toàn bộ UTM. Admin lọc tên miền không dùng tổng lượt truy cập toàn hệ thống; nguồn tùy chỉnh vào nhóm Khác, không bị gộp thành trực tiếp/X hoặc tự gắn nhãn quảng cáo.
- Telegram giữ URL chiến dịch thông thường dài hơn 90 ký tự. Tin quá dài vẫn được rút gọn có dấu … để vừa giới hạn; Google Sheet giữ URL đầy đủ. Thay đổi Telegram cần dán và triển khai lại Apps Script, dù health vẫn là protocolVersion 2/40 cột.
- Không tự sửa dữ liệu đơn cũ hoặc gửi lại thông báo cũ: cần link gốc để đối chiếu, không suy đoán dữ liệu bị thiếu.
- Kiểm thử bổ sung: node tests/test_attribution.cjs.

- Để xác nhận đúng bản sửa nguồn khách mới nhất, health cần có thêm build: 2026-10-23-attribution.
