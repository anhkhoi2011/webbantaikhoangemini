Bản sửa ngày 23/10/2026 — build 2026-10-23-visit-orders

Mục tiêu: nối đúng lượt truy cập → link/nguồn → mã đơn → thanh toán → Telegram và Google Sheet.
Tài liệu này hướng dẫn tích hợp Google Sheet đang dùng. Chưa có URL hoặc cấu hình một Google Form riêng.

Dữ liệu được ghi

- DON_HANG: 41 cột. Giữ nguyên vị trí 40 cột cũ, thêm Mã lượt truy cập ở cột 41.
- TRUY_CAP: 25 cột. Giữ nguyên 18 cột cũ; thêm mã lượt, giờ vào trang, mã đơn tạo ra từ lượt này, mã đơn đã thanh toán, trạng thái từng đơn, giờ thanh toán và giờ tạo đơn. Thời gian hiển thị GMT+7.
- Một lượt có thể tạo nhiều đơn: các mã đơn và trạng thái được ghi trên cùng dòng lượt truy cập. Lượt chưa tạo đơn để trống mã đơn.
- Mỗi lần tải trang có visitId mới; tải lại cùng URL có thể giữ sessionId trong 30 phút nhưng vẫn là một lượt mới. Gửi lại dữ liệu hoặc bổ sung IP dùng cùng visitId nên không tăng lượt.
- Đơn mới có visitId đã được ghi nhận sẽ lấy link/nguồn từ lượt đó. Sau khi tạo, các lần gửi lại giữ nguyên nguồn, URL, UTM, click ID và mã lượt của đơn, kể cả UTM ban đầu trống. IP/vị trí có thể được bổ sung.
- Đơn và lượt nối bằng visitId, không dựa vào IP/số điện thoại. Dữ liệu cũ thiếu visitId chỉ nối theo sessionId + đúng URL khi duy nhất một lượt có thể khớp; trường hợp không rõ để trống.
- Telegram thông báo đơn đã thanh toán về cả -1004413665683 và -5585627393, có mã đơn, mã lượt, mã phiên, URL, nguồn, chiến dịch, giờ tạo/thanh toán/vào trang, IP/vị trí ước lượng và thông tin khách.
- Một mã đơn chỉ có một thông báo mỗi chat. Khi có link cấp sau đó, sửa tin đã gửi; lỗi một chat chỉ thử lại chat đó. Đồng bộ im lặng sync_order không gửi/sửa Telegram hay gửi email.
- Telegram có giới hạn độ dài nên thông tin quá dài có dấu …; Sheet giữ URL/UTM đầy đủ. Không tự suy ra nguồn/IP/vị trí chưa thu thập được.

Cập nhật lên hệ thống thật

1. Mở Apps Script đang dùng, thay toàn bộ nội dung bằng GoogleAppsScript_CRM_AutoBot.js rồi lưu.
2. Deploy → Manage deployments → sửa Web App hiện tại → Version: New version → Deploy. Giữ nguyên URL /exec.
3. Mở URL /exec thêm ?action=health. Phải thấy: protocolVersion: 2, build: 2026-10-23-visit-orders, columns: 41, trafficColumns: 25.
4. Trên Vibe Host, mở đúng ứng dụng và bấm Triển khai lại từ main mới nhất. Máy chủ dùng Dockerfile Python tại gốc repo. Công tắc tự triển khai hiện tắt nên Git push chưa tự cập nhật website.
5. Mở website lại để nhận JavaScript mới. Dùng URL quảng cáo có utm_source=facebook&utm_medium=paid_social; thêm chiến dịch/nhóm/mẫu trong các trường UTM tương ứng. Link sạch không đủ bằng chứng để xác nhận quảng cáo Facebook.
6. Dùng lượt truy cập và giao dịch hợp lệ tiếp theo để kiểm tra: visitId trong TRUY_CAP = visitId trong DON_HANG = Mã lượt truy cập trong Telegram; URL/nguồn phải giống nhau, mã đơn đã thanh toán chỉ có khi đã thanh toán.

Độ tin cậy và giới hạn

- Website ghi lượt ngay khi vào trang rồi bổ sung IP trên cùng mã. Backend lưu dữ liệu trước khi trả thành công và có luồng riêng thử lại đồng bộ lượt với Sheet; luồng thanh toán chạy riêng.
- Apps Script cũ chưa hỗ trợ upsert lượt sẽ không nhận lượt gửi lại từ bản mới, tránh tăng lượt ảo. Trong thời gian chờ cập nhật Google, backend giữ lượt chờ đồng bộ.
- Trình duyệt giữ lượt/đơn chưa được backend xác nhận trong localStorage và thử lại khi online hoặc theo lịch. Phản hồi no-cors không được coi là đã ghi Sheet thành công. Backend từ chối dữ liệu thì trình duyệt không chuyển vòng qua Apps Script.
- Nếu khách chặn toàn bộ tracking, xóa bộ nhớ trước khi gửi được dữ liệu, hoặc mất mạng rồi không quay lại, không thể bảo đảm thu được lượt đó. Vị trí theo IP chỉ là ước lượng.
- Backend hiện giữ tối đa 1.000 lượt và 500 đơn trong các file JSON; Sheet là nơi lưu lịch sử đã đồng bộ. Hosting chưa được xác minh có ổ lưu trữ bền qua redeploy. Cần giữ bản sao dữ liệu trước khi triển khai; bản sao orders thật đã lưu ở Downloads khi kiểm tra trước đó.
- Dán code local không tự cập nhật Web App Google. Mình chưa có phiên đăng nhập/quyền triển khai Google để làm thay thao tác này.
- Bản sửa không tự sửa lịch sử đã ghi sai nguồn từ đầu và không tự tạo link bản quyền khi kho chưa có link.

Kiểm thử local (dữ liệu tạm/mô phỏng, không tạo đơn hoặc tin Telegram thật)

    node tests/test_apps_script.cjs
    node tests/test_checkout.cjs
    node tests/test_attribution.cjs
    node tests/test_visit_sync.cjs
    node tests/test_sales_reporting.cjs
    python -m unittest discover -s tests -p test_payment_flow.py -q

Kiểm tra live ngày 23/10/2026 trước khi triển khai bản này: Apps Script vẫn báo build 2026-10-23-payments / 40 cột; cả geminigiare.io.vn và tên miền hosting chưa có JavaScript visitId/source-lock mới.
