/**
 * ==============================================================================================
 * HỆ THỐNG CRM & BOT TELEGRAM & GỬI EMAIL TỰ ĐỘNG - GOOGLE GEMINI PRO 18 THÁNG (CHUẨN DOANH NGHIỆP)
 * ==============================================================================================
 * BẢNG GOOGLE SHEETS LIÊN KẾT:
 * URL: https://docs.google.com/spreadsheets/d/17JXfu0NcYQ2sJ9AQn8ZR-gOIYDQBgTquT4bu9pM6QrE/edit?gid=0#gid=0
 * ID: 17JXfu0NcYQ2sJ9AQn8ZR-gOIYDQBgTquT4bu9pM6QrE
 * 
 * THỨ TỰ 12 CỘT CHUẨN ĐƠN HÀNG:
 * [Ngày Giờ] | [Mã Đơn Hàng] | [Sản Phẩm] | [Giá Tiền] | [Họ Tên Khách] | [SĐT (Zalo)] | [Gmail] 
 * | [Nội Dung CK] | [Link Bản Quyền Đã Cấp] | [Nguồn Khách] | [IP & Vị Trí] | [Trạng Thái]
 * ==============================================================================================
 */

// ============================== 1. CẤU HÌNH THÔNG TIN DOANH NGHIỆP & BẢNG TÍNH ==============================
const BOT_CONFIG = {
  // Bảng tính Google Sheets mục tiêu:
  SPREADSHEET_ID: "17JXfu0NcYQ2sJ9AQn8ZR-gOIYDQBgTquT4bu9pM6QrE",
  SPREADSHEET_URL: "https://docs.google.com/spreadsheets/d/17JXfu0NcYQ2sJ9AQn8ZR-gOIYDQBgTquT4bu9pM6QrE/edit?gid=0#gid=0",

  // Token Bot Telegram thông báo đơn hàng:
  TELEGRAM_BOT_TOKEN: "8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c", 
  
  // ID Nhóm chat Telegram nhận thông báo:
  TELEGRAM_CHAT_ID: "-1004413665683", 

  // Tên thương hiệu hiển thị trong email:
  BRAND_NAME: "TRẠM CÔNG NGHỆ - Gemini Pro",
  HOTLINE: "0567.960.777",
  ZALO_SUPPORT: "https://zalo.me/0567960777"
};

// API Pay fallback cho website tĩnh: không cần PHP/Python trên hosting.
const APIPAY_ACCESS_KEY = "5a03a2c11ed56ea65b7e7e11107f638ec8acfb95165a6a50225c91a477a157c2";
const APIPAY_SECRET_KEY = "LK00NYGOmyz8i7MhhNOD/gz0YcMBjUS4+DfD/l1zXmKcKXo1v5ScvycSlu8DcngsKUSLWJzF+fS+eysDi0B3gQ==";

function jsonOutput_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  const action = (e && e.parameter && e.parameter.action) || "health";
  if (action !== "check_payment") return jsonOutput_({ status: "success", service: "Gemini CRM Apps Script" });

  const memo = String((e.parameter && e.parameter.memo) || "").replace(/\s+/g, "").toUpperCase();
  const phone = String((e.parameter && e.parameter.phone) || "").replace(/\D/g, "").replace(/^84/, "0");
  const requestedAmount = Number(String((e.parameter && e.parameter.amount) || "0").replace(/\D/g, "")) || 0;
  try {
    const auth = Utilities.base64Encode(APIPAY_ACCESS_KEY + ":" + APIPAY_SECRET_KEY);
    const response = UrlFetchApp.fetch("https://app.apipay.vn/v1/client/payment-requests", {
      method: "get", muteHttpExceptions: true,
      headers: { Authorization: "Bearer " + auth, Accept: "application/json" }
    });
    const payload = JSON.parse(response.getContentText() || "{}");
    const rows = payload && payload.data && Array.isArray(payload.data.data) ? payload.data.data : [];
    for (const row of rows) {
      const status = String(row.status || "").toUpperCase();
      if (!["PAID", "COMPLETED", "SUCCESS"].includes(status)) continue;
      const content = String(row.content || "").replace(/\s+/g, "").toUpperCase();
      const amount = Number(String(row.amount || "0").replace(/\D/g, "")) || 0;
      if (requestedAmount && amount && amount < requestedAmount) continue;
      if ((memo && content.indexOf(memo) >= 0) || (phone && content.indexOf(phone) >= 0)) {
        return jsonOutput_({ paid: true, message: "Payment verified via API Pay", transaction: row, source: "Google Apps Script API Pay" });
      }
    }
    return jsonOutput_({ paid: false, message: "Chưa có giao dịch hoàn tất" });
  } catch (err) {
    return jsonOutput_({ paid: false, status: "error", message: String(err) });
  }
}

// Thứ tự 12 cột chuẩn
const ORDER_COLUMNS = [
  "Ngày Giờ",
  "Mã Đơn Hàng",
  "Sản Phẩm",
  "Giá Tiền (VNĐ)",
  "Họ Tên Khách Hàng",
  "Số Điện Thoại (Zalo)",
  "Gmail Nhận Quyền",
  "Nội Dung Chuyển Khoản",
  "Link Bản Quyền Đã Cấp",
  "Nguồn Khách",
  "IP & Địa Chỉ",
  "Trạng Thái"
];

// Hàm lấy đối tượng Spreadsheet chính xác
function getSpreadsheet() {
  if (BOT_CONFIG.SPREADSHEET_ID && BOT_CONFIG.SPREADSHEET_ID.trim() !== "") {
    try {
      return SpreadsheetApp.openById(BOT_CONFIG.SPREADSHEET_ID);
    } catch (err) {
      Logger.log("openById warning: " + err.message);
    }
  }
  return SpreadsheetApp.getActiveSpreadsheet();
}

// Hàm lấy Sheet Đơn Hàng (Ưu tiên gid=0 hoặc DON_HANG)
function getOrdersSheet(ss) {
  let sheet = ss.getSheetByName("DON_HANG");
  if (!sheet) {
    const sheets = ss.getSheets();
    if (sheets.length > 0) {
      sheet = sheets[0]; // Lấy ngay sheet đầu tiên (gid=0)
      if (sheet.getName() === "Sheet1" || sheet.getName() === "Trang tính1") {
        try { sheet.setName("DON_HANG"); } catch(e) {}
      }
    } else {
      sheet = ss.insertSheet("DON_HANG");
    }
  }
  return sheet;
}

// ============================== 2. TẠO MENU VÀ KHỞI TẠO BẢNG TỰ ĐỘNG ==============================
function onOpen() {
  try {
    const ui = SpreadsheetApp.getUi();
    ui.createMenu("🚀 Gemini Pro CRM")
      .addItem("⚡ Khởi tạo cấu trúc bảng chuẩn 12 cột (1-Click)", "initDatabaseSheets")
      .addItem("🧪 Ghi thử 1 đơn hàng mẫu (Test Data)", "testAppendSampleOrder")
      .addSeparator()
      .addItem("🔔 Bắn thông báo test Telegram Bot", "testTelegramAlert")
      .addToUi();
  } catch(e) {}
}

function initDatabaseSheets() {
  const ss = getSpreadsheet();

  // 1. Khởi tạo Sheet Đơn Hàng (DON_HANG - gid=0)
  let sheetOrders = getOrdersSheet(ss);
  
  // Tự động kiểm tra: nếu dòng 1 đã có đơn hàng mà chưa có tiêu đề, chèn thêm 1 dòng trước dòng 1
  const firstVal = sheetOrders.getLastRow() > 0 ? sheetOrders.getRange(1, 1).getValue().toString().trim() : "";
  if (firstVal !== ORDER_COLUMNS[0]) {
    if (sheetOrders.getLastRow() > 0) {
      sheetOrders.insertRowBefore(1);
    }
  }

  sheetOrders.getRange(1, 1, 1, ORDER_COLUMNS.length).setValues([ORDER_COLUMNS]);
  
  // Định dạng Header chuyên nghiệp
  const headerRange = sheetOrders.getRange(1, 1, 1, ORDER_COLUMNS.length);
  headerRange
    .setBackground("#0f172a") // Slate 900 Dark Navy
    .setFontColor("#ffffff")
    .setFontWeight("bold")
    .setFontSize(10)
    .setHorizontalAlignment("center")
    .setVerticalAlignment("middle");
  
  sheetOrders.setRowHeight(1, 38);
  sheetOrders.setFrozenRows(1);

  // Định dạng độ rộng cột
  const colWidths = [160, 110, 230, 110, 150, 130, 190, 150, 280, 120, 180, 150];
  for (let c = 0; c < colWidths.length; c++) {
    sheetOrders.setColumnWidth(c + 1, colWidths[c]);
  }

  // 2. Tạo Sheet Kho Tài Nguyên nếu chưa có
  let sheetInventory = ss.getSheetByName("KHO_TAI_NGUYEN");
  if (!sheetInventory) {
    sheetInventory = ss.insertSheet("KHO_TAI_NGUYEN");
    sheetInventory.appendRow(["STT", "Link Bản Quyền 18T", "Trạng Thái", "Khách Hàng Nhận", "Gmail Khách", "Thời Gian Cấp"]);
    sheetInventory.getRange(1, 1, 1, 6)
      .setBackground("#065f46")
      .setFontColor("#ffffff")
      .setFontWeight("bold")
      .setFontSize(10)
      .setHorizontalAlignment("center");
    sheetInventory.setRowHeight(1, 35);
    sheetInventory.setFrozenRows(1);
    
    sheetInventory.appendRow([1, "https://one.google.com/promo/gemini-pro-enterprise/ACT-GEMINI-VIP01", "CHƯA DÙNG", "", "", ""]);
    sheetInventory.appendRow([2, "https://one.google.com/promo/gemini-pro-enterprise/ACT-GEMINI-VIP02", "CHƯA DÙNG", "", "", ""]);
    sheetInventory.appendRow([3, "https://one.google.com/promo/gemini-pro-enterprise/ACT-GEMINI-VIP03", "CHƯA DÙNG", "", "", ""]);
    
    sheetInventory.setColumnWidth(1, 60);
    sheetInventory.setColumnWidth(2, 320);
    sheetInventory.setColumnWidth(3, 110);
    sheetInventory.setColumnWidth(4, 150);
    sheetInventory.setColumnWidth(5, 190);
    sheetInventory.setColumnWidth(6, 150);
  }

  // 3. Tạo Sheet Thống Kê Truy Cập
  let sheetTraffic = ss.getSheetByName("TRUY_CAP");
  if (!sheetTraffic) {
    sheetTraffic = ss.insertSheet("TRUY_CAP");
    sheetTraffic.appendRow(["Thời Gian", "IP Khách", "Tỉnh Thành", "Thiết Bị", "Trình Duyệt", "Nguồn Giới Thiệu (Referrer)"]);
    sheetTraffic.getRange(1, 1, 1, 6).setBackground("#334155").setFontColor("#ffffff").setFontWeight("bold");
    sheetTraffic.setFrozenRows(1);
  }

  Logger.log("Đã khởi tạo hoàn tất cấu trúc bảng Google Sheet: " + BOT_CONFIG.SPREADSHEET_ID);
}

// ============================== 3. WEBHOOK NHẬN DỮ LIỆU TỪ WEBSITE (doPost) ==============================
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const ss = getSpreadsheet();

    // KIỂU 0: KHỞI TẠO TIÊU ĐỀ BẢNG (INIT HEADERS)
    if (data.action === "init_headers" || data.action === "create_headers") {
      initDatabaseSheets();
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        message: "Đã tạo tiêu đề 12 cột thành công vào Google Sheet!",
        sheetUrl: BOT_CONFIG.SPREADSHEET_URL
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // KIỂU 1: GHI NHẬN LƯỢT TRUY CẬP (TRAFFIC ANALYTICS)
    if (data.action === "track_visit") {
      const sheetTraffic = ss.getSheetByName("TRUY_CAP") || ss.getActiveSheet();
      sheetTraffic.appendRow([
        Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss"),
        data.ip || "Không rõ",
        data.location || "Việt Nam",
        data.device || "Không rõ",
        data.browser || "Không rõ",
        data.referrer || "Truy cập trực tiếp"
      ]);
      return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "Traffic logged" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // KIỂU 2: GIAO DỊCH ĐƠN HÀNG MỚI (NEW ORDER / SUCCESS PAYMENT)
    if (data.action === "new_order" || data.action === "payment_success") {
      const sheetOrders = getOrdersSheet(ss);

      // Tự động kiểm tra và tạo dòng tiêu đề nếu dòng 1 chưa có tiêu đề "Ngày Giờ"
      const firstVal = sheetOrders.getLastRow() > 0 ? sheetOrders.getRange(1, 1).getValue().toString().trim() : "";
      if (firstVal !== ORDER_COLUMNS[0]) {
        if (sheetOrders.getLastRow() > 0) {
          sheetOrders.insertRowBefore(1);
        }
        sheetOrders.getRange(1, 1, 1, ORDER_COLUMNS.length).setValues([ORDER_COLUMNS]);
        sheetOrders.getRange(1, 1, 1, ORDER_COLUMNS.length)
          .setBackground("#0f172a")
          .setFontColor("#ffffff")
          .setFontWeight("bold")
          .setFontSize(10)
          .setHorizontalAlignment("center")
          .setVerticalAlignment("middle");
        sheetOrders.setRowHeight(1, 38);
        sheetOrders.setFrozenRows(1);
        const colWidths = [160, 110, 230, 110, 150, 130, 190, 150, 280, 120, 180, 150];
        for (let c = 0; c < colWidths.length; c++) {
          sheetOrders.setColumnWidth(c + 1, colWidths[c]);
        }
      }

      const timeNow = data.time || Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss");
      const orderId = data.orderId || ("#GEM-" + Math.floor(1000 + Math.random() * 9000));
      const product = data.product || data.package || "Google Gemini Pro 18 Tháng (5TB Cloud)";
      const amount = data.amount || "90.000 VNĐ";
      const name = data.name || "Khách hàng";
      const rawPhone = data.phone ? data.phone.toString().replace(/^'/, '').trim() : "";
      const sheetPhone = rawPhone ? ("'" + rawPhone) : "";
      const email = data.email || "";
      const memo = data.memo || `PRO18T ${rawPhone}`;
      let rawAllocated = data.licenseLink || "";
      if (!rawAllocated || rawAllocated.includes("GEMINI-VIP-DEMO") || rawAllocated.includes("geminiactivation.com")) {
        rawAllocated = allocateLicenseFromInventory(name, email);
      }
      const hasRealLink = rawAllocated && rawAllocated.startsWith("http") && !rawAllocated.includes("ACT-GEMINI-VIP-BACKUP") && !rawAllocated.includes("geminiactivation.com");
      const allocatedLink = hasRealLink ? rawAllocated : "";
      const referrer = data.referrer || "Truy cập trực tiếp";
      const ipLocation = data.ipLocation || `${data.ip || '127.0.0.1'} (${data.location || 'Việt Nam'})`;
      const status = data.status || (hasRealLink ? "Đã thanh toán (MBBank)" : "Chờ cấp link (Hết kho)");

      // Ghi 12 cột chuẩn xác
      sheetOrders.appendRow([
        timeNow,
        orderId,
        product,
        amount,
        name,
        sheetPhone,
        email,
        memo,
        allocatedLink,
        referrer,
        ipLocation,
        status
      ]);

      // Định dạng dòng vừa thêm cho đẹp
      const lastRow = sheetOrders.getLastRow();
      sheetOrders.getRange(lastRow, 1, 1, ORDER_COLUMNS.length).setVerticalAlignment("middle");
      sheetOrders.getRange(lastRow, 4).setHorizontalAlignment("right").setFontWeight("bold"); // Cột Giá
      sheetOrders.getRange(lastRow, 6).setHorizontalAlignment("left"); // Cột SĐT giữ nguyên số 0 đầu
      sheetOrders.getRange(lastRow, 12).setHorizontalAlignment("center"); // Cột Trạng Thái

      // Gửi email hóa đơn tự động bằng Gmail CHỈ KHI CÓ LINK THỰC SỰ
      // Trường hợp hết link kho: Không gửi email rác, Admin mua bot https://t.me/shopxoainon_bot rồi gửi sau
      if (email && email.includes("@") && hasRealLink) {
        try {
          sendInvoiceEmail(name, email, rawPhone, orderId, allocatedLink);
        } catch(err) {
          Logger.log("Email send error: " + err.message);
        }
      }

      // Bắn thông báo Telegram Bot siêu gọn (1 icon)
      try {
        sendTelegramAlert(orderId, name, rawPhone, email, amount, memo, allocatedLink, timeNow);
      } catch(err) {
        Logger.log("Telegram alert error: " + err.message);
      }

      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        orderId: orderId,
        allocatedLink: allocatedLink,
        sheetUrl: BOT_CONFIG.SPREADSHEET_URL,
        message: "Order successfully synced to Google Sheet!"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({ status: "ignored" })).setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", error: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ============================== 4. HÀM TỰ ĐỘNG BỐC LINK TỪ KHO ==============================
function allocateLicenseFromInventory(customerName, customerEmail) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName("KHO_TAI_NGUYEN");
  if (!sheet) return "";

  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (data[i][2] === "CHƯA DÙNG" && data[i][1] && data[i][1].toString().trim().startsWith("http")) {
      const link = data[i][1].toString().trim();
      const row = i + 1;
      sheet.getRange(row, 3).setValue("ĐÃ DÙNG").setBackground("#dcfce7").setFontColor("#15803d");
      sheet.getRange(row, 4).setValue(customerName);
      sheet.getRange(row, 5).setValue(customerEmail);
      sheet.getRange(row, 6).setValue(Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss"));
      return link;
    }
  }

  return "";
}

// ============================== 5. GỬI EMAIL TỰ ĐỘNG TỪ GMAIL CHUẨN HTML ==============================
function sendInvoiceEmail(name, email, phone, orderId, link) {
  const subject = `[Gemini Enterprise] Kích hoạt thành công gói Google Gemini Pro 18T (Đơn ${orderId})`;
  const htmlBody = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #ffffff;">
      <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 24px; text-align: center; color: #ffffff;">
        <h1 style="margin: 0; font-size: 20px; font-weight: 800;">GOOGLE GEMINI PRO 18 THÁNG</h1>
        <p style="margin: 6px 0 0; font-size: 13px; opacity: 0.9;">Xác Nhận Kích Hoạt Quyền Sử Dụng Thành Công</p>
      </div>

      <div style="padding: 24px;">
        <p style="font-size: 14px; color: #334155; margin-top: 0;">Xin chào <strong>${name}</strong>,</p>
        <p style="font-size: 13px; color: #475569; line-height: 1.6;">
          Hệ thống API Pay & Ngân hàng MBBank đã ghi nhận thành công giao dịch <strong>90.000 VNĐ</strong> của bạn.
        </p>

        <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
          <p style="margin: 0 0 10px; font-size: 12px; color: #64748b; font-weight: 700; text-transform: uppercase;">Link Bản Quyền Riêng Biệt Của Bạn:</p>
          <a href="${link}" target="_blank" style="display: inline-block; background: #16a34a; color: #ffffff; padding: 12px 24px; border-radius: 8px; font-weight: 800; font-size: 14px; text-decoration: none;">
            👉 BẤM VÀO ĐÂY ĐỂ KÍCH HOẠT NGAY
          </a>
          <p style="margin: 10px 0 0; font-size: 11px; color: #94a3b8; word-break: break-all;">${link}</p>
        </div>

        <div style="font-size: 12px; background: #f1f5f9; padding: 12px; border-radius: 6px; margin-bottom: 20px;">
          <div><strong>Mã đơn hàng:</strong> ${orderId}</div>
          <div><strong>SĐT Zalo:</strong> ${phone}</div>
          <div><strong>Gmail nhận quyền:</strong> ${email}</div>
          <div><strong>Bảo hành:</strong> 30 Ngày (Cam kết 1 đổi 1)</div>
          <div><strong>Hỗ trợ Zalo:</strong> <a href="${BOT_CONFIG.ZALO_SUPPORT}">0567.960.777</a></div>
        </div>
      </div>
      <div style="background: #f8fafc; padding: 12px; text-align: center; font-size: 11px; color: #94a3b8;">
        © 2026 ${BOT_CONFIG.BRAND_NAME}.
      </div>
    </div>
  `;

  GmailApp.sendEmail(email, subject, "Vui lòng mở email ở chế độ HTML.", {
    htmlBody: htmlBody,
    name: BOT_CONFIG.BRAND_NAME
  });
}

// ============================== 6. GỬI THÔNG BÁO TELEGRAM CHUẨN GỌN GÀNG (1 ICON) ==============================
function sendTelegramAlert(orderId, name, phone, email, amount, memo, link, timeStr) {
  if (!BOT_CONFIG.TELEGRAM_BOT_TOKEN || !BOT_CONFIG.TELEGRAM_CHAT_ID) return;

  const cleanPhone = phone ? phone.toString().replace(/^'/, '') : "N/A";
  const hasRealLink = link && link.toString().trim().startsWith("http") && !link.includes("ACT-GEMINI-VIP-BACKUP") && !link.includes("geminiactivation.com");

  let linkDisplay = hasRealLink 
    ? `<code>${link}</code>` 
    : `⚠️ <b>KHO ĐÃ HẾT LINK!</b>\n👉 <b>VÀO BOT MUA NGAY:</b> <a href="https://t.me/shopxoainon_bot">https://t.me/shopxoainon_bot</a>\n(Sau khi mua vào Admin CRM dán link & bấm gửi Zalo/Gmail cho khách)`;

  const htmlMsg = 
    `🟢 <b>ĐƠN HÀNG MỚI (${amount})</b>\n` +
    `Mã đơn: <code>${orderId}</code> • ${timeStr}\n` +
    `Khách: <b>${name}</b> | <code>${cleanPhone}</code>\n` +
    `Gmail: <code>${email}</code>\n` +
    `Nội dung: <code>${memo}</code>\n` +
    `Link cấp: ${linkDisplay}`;

  const url = `https://api.telegram.org/bot${BOT_CONFIG.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const payload = {
    chat_id: BOT_CONFIG.TELEGRAM_CHAT_ID,
    text: htmlMsg,
    parse_mode: "HTML",
    disable_web_page_preview: true
  };

  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

// Hàm Test ghi thử dữ liệu mẫu
function testAppendSampleOrder() {
  const e = {
    postData: {
      contents: JSON.stringify({
        action: "new_order",
        time: Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss"),
        orderId: "#GEM-TEST99",
        product: "Google Gemini Pro 18 Tháng (5TB Cloud)",
        amount: "90.000 VNĐ",
        name: "Trần Anh Khoa",
        phone: "0908889999",
        email: "khoa.test@gmail.com",
        memo: "PRO18T 0908889999",
        licenseLink: "https://one.google.com/promo/gemini-pro/ACT-TEST-VIP99",
        referrer: "Facebook Ads",
        ipLocation: "113.161.42.18 (TP. Hồ Chí Minh)",
        status: "Đã thanh toán (MBBank)"
      })
    }
  };
  doPost(e);
}

// Hàm Test Telegram
function testTelegramAlert() {
  sendTelegramAlert(
    "#GEM-TEST-ALERT",
    "Nguyễn Hoàng Nam",
    "0912345678",
    "hoangnam.ai@gmail.com",
    "90.000 VNĐ",
    "PRO18T 0912345678",
    "https://one.google.com/promo/gemini-pro/ACT-NAM7492",
    Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss")
  );
}
