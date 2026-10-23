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
  TELEGRAM_CHAT_IDS: ["-1004413665683", "-5585627393"],

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
  if (action !== "check_payment") return jsonOutput_({ status: "success", service: "Gemini CRM Apps Script", protocolVersion: 2, columns: ORDER_COLUMNS.length, trafficColumns: VISIT_COLUMNS.length, build: "2026-10-23-visit-orders" });

  const memo = String((e.parameter && e.parameter.memo) || "").replace(/\s+/g, "").toUpperCase();
  const orderId = String(e.parameter.orderId || "");
  const phone = String((e.parameter && e.parameter.phone) || "").replace(/\D/g, "").replace(/^84/, "0");
  const requestedAmount = money_((e.parameter && e.parameter.amount) || 0);
  try {
    const ss = getSpreadsheet();
    const orderSheet = ss.getSheetByName("DON_HANG");
    const orders = orderSheet && orderSheet.getLastRow() > 1 ? orderSheet.getRange(2, 1, orderSheet.getLastRow() - 1, Math.min(ORDER_COLUMNS.length, orderSheet.getMaxColumns())).getValues().map(rowToOrder_) : [];
    const approved = orders.find(order => String(order.orderId) === orderId && isPaidOrder_(order));
    if (approved) return jsonOutput_({paid: true, transaction: Object.assign({}, approved, {id: approved.paymentTxId || approved.orderId, amount: money_(approved.amountRaw || approved.amount)}), source: "Order Database"});
    const claimed = (id, key) => orders.some(order => String(order.orderId) !== orderId && isPaidOrder_(order) && ((id && order.paymentTxId === id) || (key && order.paymentKey === key)));
    const txSheet = ss.getSheetByName("GIAO_DICH");
    if (txSheet && txSheet.getLastRow() > 1) {
      const rows = txSheet.getRange(2, 1, txSheet.getLastRow() - 1, Math.min(8, txSheet.getMaxColumns())).getValues();
      for (const row of rows) {
        if ((row[7] && String(row[7]) !== orderId) || claimed(String(row[0]), row[6])) continue;
        const content = String(row[2] || "").replace(/\s+/g, "").toUpperCase();
        const amount = money_(row[1]);
        const status = String(row[3] || "").toUpperCase();
        if (["PAID", "COMPLETED", "SUCCESS", "CREDIT"].indexOf(status) < 0) continue;
        if (amount <= 0 || (requestedAmount > 0 && amount < requestedAmount)) continue;
        if ((memo ? content.indexOf(memo) >= 0 : phone && content.indexOf(phone) >= 0)) {
          return jsonOutput_({ paid: true, message: "Payment verified via API Pay webhook", transaction: { id: row[0], amount: amount, description: row[2], status: row[3], time: row[4] }, source: "Google Apps Script webhook" });
        }
      }
    }
    const auth = Utilities.base64Encode(APIPAY_ACCESS_KEY + ":" + APIPAY_SECRET_KEY);
    const response = UrlFetchApp.fetch("https://app.apipay.vn/v1/client/payment-requests", {
      method: "get", muteHttpExceptions: true,
      headers: { Authorization: "Bearer " + auth, Accept: "application/json" }
    });
    const payload = JSON.parse(response.getContentText() || "{}");
    const rows = payload && payload.data && Array.isArray(payload.data.data) ? payload.data.data : [];
    for (const row of rows) {
      if (claimed(String(row.transactionId || row.publicId || row.id || ""), paymentKey_(row, money_(row.amount), row.content || ""))) continue;
      const status = String(row.status || "").toUpperCase();
      if (!["PAID", "COMPLETED", "SUCCESS"].includes(status)) continue;
      const content = String(row.content || "").replace(/\s+/g, "").toUpperCase();
      const amount = money_(row.amount);
      if (amount <= 0 || (requestedAmount > 0 && amount < requestedAmount)) continue;
      if ((memo ? content.indexOf(memo) >= 0 : phone && content.indexOf(phone) >= 0)) {
        return jsonOutput_({ paid: true, message: "Payment verified via API Pay", transaction: Object.assign({}, row, {amount: amount}), source: "Google Apps Script API Pay" });
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
    const first = ss.getSheets()[0];
    if (first && !["GIAO_DICH", "TRUY_CAP", "KHO_TAI_NGUYEN"].includes(first.getName())) sheet = first;
    else sheet = ss.insertSheet("DON_HANG");
    if (sheet.getName() !== "DON_HANG") sheet.setName("DON_HANG");
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
  ensureOrderHeaders_(sheetOrders);
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
// All writes share one lock: retries and simultaneous callbacks update the same row.
function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(25000);
    const data = JSON.parse(e.postData.contents);
    const ss = getSpreadsheet();
    const action = String(data.action || "");
    // Website actions MUST be routed before bank payload detection (orders also contain amount).
    if (["new_order", "payment_success", "pending_order", "sync_order"].includes(action)) {
      return jsonOutput_(upsertOrder_(ss, data, action !== "sync_order" && action !== "pending_order"));
    }
    if (action === "sync_orders") {
      const results = (data.orders || []).map(order => upsertOrder_(ss, order, false));
      return jsonOutput_({status: "success", count: results.length, results: results});
    }
    if (action === "init_headers" || action === "create_headers") {
      ensureOrderHeaders_(getOrdersSheet(ss));
      return jsonOutput_({status: "success", columns: ORDER_COLUMNS.length});
    }
    if (action === "track_visit") return jsonOutput_(upsertVisit_(ss, data));
    if (action) return jsonOutput_({status: "error", message: "Unknown action"});
    const incoming = Array.isArray(data) ? data : Array.isArray(data.transactions) ? data.transactions : Array.isArray(data.records) ? data.records : data.data && Array.isArray(data.data.records) ? data.data.records : Array.isArray(data.data) ? data.data : data.data && typeof data.data === "object" ? [data.data] : [data];
    let stored = 0;
    for (const tx of incoming) {
      const amount = money_(tx.amount || tx.creditAmount || tx.transferAmount);
      const content = String(tx.content || tx.description || tx.memo || tx.comment || "").trim();
      const status = String(tx.status || "COMPLETED").toUpperCase();
      const direction = String(tx.transferType || tx.direction || "").toLowerCase();
      if (amount <= 0 || !content || ["out", "debit"].includes(direction)) continue;
      const key = paymentKey_(tx, amount, content);
      const txId = String(tx.transactionId || tx.referenceCode || tx.reference || tx.id || tx.publicId || key);
      const time = tx.paidAt || tx.completedAt || tx.transactionDateTime || tx.time || tx.updatedAt || tx.createdAt || nowVN_();
      const sheet = ss.getSheetByName("GIAO_DICH") || ss.insertSheet("GIAO_DICH");
      const headers = ["ID", "Số tiền", "Nội dung", "Trạng thái", "Thời gian", "Raw", "Khóa giao dịch", "Mã đơn"];
      ensureColumns_(sheet, headers.length);
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      const rows = sheet.getLastRow() > 1 ? sheet.getRange(2, 1, sheet.getLastRow() - 1, headers.length).getValues() : [];
      const found = rows.findIndex(row => String(row[6]) === key || String(row[0]) === txId || paymentKey_({}, money_(row[1]), String(row[2])) === key);
      const old = found >= 0 ? rows[found] : [];
      const rowNumber = found >= 0 ? found + 2 : sheet.getLastRow() + 1;
      const paid = paidStatus_(status);
      // A late PENDING event must not downgrade a completed payment.
      const nextStatus = paidStatus_(old[3]) ? old[3] : status;
      let orderId = old[7] || "";
      const orderSheet = getOrdersSheet(ss);
      ensureOrderHeaders_(orderSheet);
      const orders = orderSheet.getLastRow() > 1 ? orderSheet.getRange(2, 1, orderSheet.getLastRow() - 1, ORDER_COLUMNS.length).getValues().map(rowToOrder_) : [];
      if (paid) {
        const candidates = orders.filter(order => orderId ? order.orderId === orderId : !isPaidOrder_(order) && order.memo && normalizeMemo_(content).includes(normalizeMemo_(order.memo)) && amount >= money_(order.amountRaw || order.amount));
        // Ambiguous legacy phone-only transfers need manual reconciliation.
        if (candidates.length === 1) {
          const order = candidates[0];
          orderId = order.orderId;
          order.paymentTxId = txId;
          order.paymentKey = key;
          order.paidAt = time;
          order.paymentSource = "APIPay Webhook";
          order.amountRaw = amount;
          order.amount = amount;
          order.status = order.licenseLink ? "Đã thanh toán (MBBank)" : "Đã thanh toán (Chờ cấp link)";
          upsertOrder_(ss, order, true);
        }
      }
      sheet.getRange(rowNumber, 1, 1, headers.length).setValues([[txId, amount, content, nextStatus, time, JSON.stringify(tx), key, orderId].map(sheetText_)]);
      stored++;
    }
    // Raw bank events stay in GIAO_DICH. Only a matched customer order sends an alert.
    return jsonOutput_({status: "success", count: stored});
  } catch (error) {
    return jsonOutput_({status: "error", message: String(error)});
  } finally {
    if (lock.hasLock()) { SpreadsheetApp.flush(); lock.releaseLock(); }
  }
}

const ORDER_EXTRA_FIELDS = ["domain", "createdAt", "paidAt", "ip", "location", "device", "browser", "fullUrl", "rawReferrer", "utmSource", "utmMedium", "utmCampaign", "utmContent", "utmTerm", "fbclid", "gclid", "ttclid", "paymentTxId", "paymentKey", "paymentSource", "couponCode", "discountAmount", "sessionId", "landingAt", "userAgent", "amountRaw", "telegramSent", "emailSent", "visitId"];
ORDER_COLUMNS.push("Tên miền", "Tạo đơn lúc", "Thanh toán lúc (GMT+7)", "IP", "Vị trí IP (ước lượng)", "Thiết bị", "Trình duyệt", "URL truy cập", "Referrer gốc", "UTM Source", "UTM Medium", "UTM Campaign", "UTM Content", "UTM Term", "FB Click ID", "Google Click ID", "TikTok Click ID", "Mã giao dịch", "Khóa giao dịch", "Cổng thanh toán", "Voucher", "Giảm giá", "Session ID", "Vào trang lúc", "User Agent", "Số tiền thực", "Telegram đã gửi", "Email đã gửi", "Mã lượt truy cập");
const VISIT_COLUMNS = ["Thời Gian", "IP Khách", "Vị trí (ước lượng)", "Thiết Bị", "Trình Duyệt", "Nguồn", "URL truy cập", "FB Click ID", "UTM Source", "UTM Campaign", "Tên Miền", "Referrer gốc", "UTM Medium", "UTM Content", "UTM Term", "Google Click ID", "TikTok Click ID", "Session ID", "Mã lượt truy cập", "Vào trang lúc (GMT+7)", "Mã đơn từ lượt này", "Mã đơn đã thanh toán", "Trạng thái từng đơn", "Thanh toán lúc (GMT+7)", "Tạo đơn lúc (GMT+7)"];
function getVisitsSheet_(ss) {
  const sheet = ss.getSheetByName("TRUY_CAP") || ss.insertSheet("TRUY_CAP");
  ensureColumns_(sheet, VISIT_COLUMNS.length);
  sheet.getRange(1, 1, 1, VISIT_COLUMNS.length).setValues([VISIT_COLUMNS]);
  return sheet;
}
function visitMatchesOrder_(row, order, rows) {
  if (order.visitId) return String(row[18]) === String(order.visitId);
  const linked = String(row[20] || "").split("\n");
  if (linked.includes(String(order.orderId))) return true;
  // For old data only match a session+URL if there is exactly one possible visit.
  if (!order.sessionId || !order.fullUrl) return false;
  const candidates = rows.filter(r => String(r[17]) === String(order.sessionId) && String(r[6]) === String(order.fullUrl));
  return candidates.length === 1 && candidates[0] === row;
}
function refreshVisitOrders_(ss, sheet, rowNumber, row, rows) {
  const ordersSheet = getOrdersSheet(ss);
  const orders = ordersSheet.getLastRow() > 1 ? ordersSheet.getRange(2, 1, ordersSheet.getLastRow() - 1, ORDER_COLUMNS.length).getValues().map(rowToOrder_) : [];
  const linked = orders.filter(order => visitMatchesOrder_(row, order, rows));
  const paid = linked.filter(isPaidOrder_);
  const values = [linked.map(o => o.orderId).join("\n"), paid.map(o => o.orderId).join("\n"), linked.map(o => o.orderId + ": " + o.status).join("\n"), paid.map(o => o.orderId + ": " + displayTime_(o.paidAt)).join("\n"), linked.map(o => o.orderId + ": " + displayTime_(o.createdAt)).join("\n")];
  sheet.getRange(rowNumber, 21, 1, values.length).setValues([values.map(sheetText_)]);
}
function linkOrderVisit_(ss, order) {
  const sheet = ss.getSheetByName("TRUY_CAP");
  if (!sheet || sheet.getLastRow() < 2) return;
  getVisitsSheet_(ss);
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, VISIT_COLUMNS.length).getValues();
  rows.forEach((row, i) => {
    if (visitMatchesOrder_(row, order, rows)) refreshVisitOrders_(ss, sheet, i + 2, row, rows);
  });
}
function upsertVisit_(ss, data) {
  const sheet = getVisitsSheet_(ss);
  const rows = sheet.getLastRow() > 1 ? sheet.getRange(2, 1, sheet.getLastRow() - 1, VISIT_COLUMNS.length).getValues() : [];
  const index = data.visitId ? rows.findIndex(row => String(row[18]) === String(data.visitId)) : -1;
  const prior = index >= 0 ? rows[index] : null;
  let values = [displayTime_(data.visitedAt || data.landingAt) || nowVN_(), data.ip || "Không xác định", data.location || "Không xác định", data.device || "", data.browser || "", data.referrer || "", data.fullUrl || "", data.fbclid || "", data.utmSource || "", data.utmCampaign || "", data.domain || "", data.rawReferrer || "", data.utmMedium || "", data.utmContent || "", data.utmTerm || "", data.gclid || "", data.ttclid || "", data.sessionId || "", data.visitId || "", displayTime_(data.landingAt || data.visitedAt), "", "", "", "", ""];
  if (prior) {
    // Retry/enrichment owns only missing IP/location and device details, never a new visit/source.
    values = prior.slice();
    ["ip", "location", "device", "browser"].forEach((key, i) => { if (data[key]) values[i + 1] = data[key]; });
  }
  const rowNumber = index >= 0 ? index + 2 : sheet.getLastRow() + 1;
  sheet.getRange(rowNumber, 1, 1, VISIT_COLUMNS.length).setValues([values.map(sheetText_)]);
  const updatedRows = sheet.getRange(2, 1, sheet.getLastRow() - 1, VISIT_COLUMNS.length).getValues();
  refreshVisitOrders_(ss, sheet, rowNumber, updatedRows[rowNumber - 2], updatedRows);
  return {status: "success", visitId: data.visitId || "", duplicate: index >= 0};
}
function displayTime_(value) {
  if (!value) return "";
  const parsed = value instanceof Date ? value : /^\d{4}-\d{2}-\d{2}T/.test(String(value)) ? new Date(value) : null;
  return parsed && !isNaN(parsed.getTime()) ? Utilities.formatDate(parsed, "GMT+7", "dd/MM/yyyy HH:mm:ss") : String(value);
}
function nowVN_() { return Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss"); }
function money_(value) {
  if (typeof value === "number") return Math.trunc(value);
  const text = String(value || "0").trim();
  if (/^-?\d+[.,]\d{1,2}$/.test(text)) return Math.trunc(Number(text.replace(",", ".")));
  return (text.startsWith("-") ? -1 : 1) * Number(text.replace(/[^0-9]/g, ""));
}
function normalizeMemo_(value) { return String(value || "").replace(/\s+/g, "").toUpperCase(); }
function paidStatus_(status) { return ["PAID", "COMPLETED", "SUCCESS", "CREDIT"].includes(String(status || "").toUpperCase()); }
function isPaidOrder_(order) { return /đã thanh toán|da thanh toan|thành công|thanh cong|^(paid|completed|success)$/i.test(order.status || ""); }
function sheetText_(value) { return typeof value === "string" && /^[=+@-]/.test(value) ? "'" + value : value === undefined || value === null ? "" : value; }
function html_(value) { return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function paymentKey_(tx, amount, content) {
  // Provider delivery IDs can change on retry. Bank reference/content are stable.
  const reference = tx.bankReference || tx.referenceCode || tx.transactionReference || "";
  const seed = [reference, amount, normalizeMemo_(content)].join("|");
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, seed).map(b => ("0" + ((b + 256) % 256).toString(16)).slice(-2)).join("");
}
function ensureColumns_(sheet, count) { if (sheet.getMaxColumns() < count) sheet.insertColumnsAfter(sheet.getMaxColumns(), count - sheet.getMaxColumns()); }
function ensureOrderHeaders_(sheet) {
  ensureColumns_(sheet, ORDER_COLUMNS.length);
  if (sheet.getLastRow() && String(sheet.getRange(1, 2).getValue()).startsWith("#")) sheet.insertRowBefore(1);
  sheet.getRange(1, 1, 1, ORDER_COLUMNS.length).setValues([ORDER_COLUMNS]).setBackground("#0f172a").setFontColor("#ffffff").setFontWeight("bold");
  sheet.setFrozenRows(1);
}
function rowToOrder_(row) {
  const order = {time: row[0], orderId: row[1], product: row[2], amount: row[3], name: row[4], phone: String(row[5] || "").replace(/^'/, ""), email: row[6], memo: row[7], licenseLink: row[8], referrer: row[9], ipLocation: row[10], status: row[11]};
  ORDER_EXTRA_FIELDS.forEach((key, i) => order[key] = row[12 + i] || "");
  return order;
}
function upsertOrder_(ss, data, notify) {
  if (!data.orderId) throw new Error("Missing orderId");
  const sheet = getOrdersSheet(ss);
  ensureOrderHeaders_(sheet);
  const rows = sheet.getLastRow() > 1 ? sheet.getRange(2, 1, sheet.getLastRow() - 1, ORDER_COLUMNS.length).getValues() : [];
  const index = rows.findIndex(row => String(row[1]) === String(data.orderId) || (data.paymentKey && String(row[30]) === String(data.paymentKey)) || (data.paymentTxId && String(row[29]) === String(data.paymentTxId)));
  const previous = index >= 0 ? rowToOrder_(rows[index]) : {};
  if (previous.orderId && String(previous.orderId) !== String(data.orderId)) return {status: "error", message: "Giao dịch đã thuộc đơn khác", orderId: previous.orderId};
  const order = Object.assign({}, previous);
  Object.keys(data).forEach(key => { if (data[key] !== "" && data[key] !== null && data[key] !== undefined) order[key] = data[key]; });
  if (!previous.orderId && order.visitId) {
    const traffic = ss.getSheetByName("TRUY_CAP");
    if (traffic && traffic.getLastRow() > 1) {
      getVisitsSheet_(ss);
      const visits = traffic.getRange(2, 1, traffic.getLastRow() - 1, VISIT_COLUMNS.length).getValues();
      const visit = visits.find(row => String(row[18]) === String(order.visitId));
      if (visit && visit[6]) {
        const fields = {fullUrl: 6, domain: 10, referrer: 5, rawReferrer: 11, utmSource: 8, utmMedium: 12, utmCampaign: 9, utmContent: 13, utmTerm: 14, fbclid: 7, gclid: 15, ttclid: 16, sessionId: 17, visitId: 18, landingAt: 19};
        Object.keys(fields).forEach(key => order[key] = visit[fields[key]] || "");
        if (visit[1] && visit[1] !== "Không xác định") order.ip = visit[1];
        if (visit[2] && visit[2] !== "Không xác định") order.location = visit[2];
      }
    }
  }
  if (previous.orderId) order.orderId = previous.orderId;
  if (previous.fullUrl) {
    // The original visit owns attribution even when later payloads contain different links.
    ["fullUrl", "domain", "referrer", "rawReferrer", "utmSource", "utmMedium", "utmCampaign", "utmContent", "utmTerm", "fbclid", "gclid", "ttclid", "sessionId", "landingAt", "visitId"].forEach(key => {
      order[key] = previous[key] || "";
    });
  }
  if (isPaidOrder_(previous) && !isPaidOrder_(data)) order.status = previous.status;
  order.telegramSent = previous.telegramSent || "";
  order.emailSent = previous.emailSent || "";
  order.time = order.time || nowVN_();
  order.createdAt = previous.createdAt || data.createdAt || order.time;
  if (isPaidOrder_(order)) order.paidAt = previous.paidAt || data.paidAt || nowVN_();
  if (isPaidOrder_(order)) order.time = order.paidAt;
  order.product = order.product || order.package || "Google Gemini Pro 18 Tháng";
  order.fullUrl = order.fullUrl || order.adLink || "";
  order.utmCampaign = order.utmCampaign || order.adCampaign || "";
  const rowNumber = index >= 0 ? index + 2 : sheet.getLastRow() + 1;
  const write = () => {
    const values = [displayTime_(order.time), order.orderId, order.product, order.amount, order.name, String(order.phone || ""), order.email, order.memo, order.licenseLink, order.referrer || "Không xác định", order.ipLocation || [order.ip || "Không xác định", order.location || "Không xác định"].join(" - "), order.status].concat(ORDER_EXTRA_FIELDS.map(key => ["createdAt", "paidAt", "landingAt"].includes(key) ? displayTime_(order[key]) : order[key] || ""));
    sheet.getRange(rowNumber, 1, 1, values.length).setValues([values.map(sheetText_)]);
  };
  write();
  linkOrderVisit_(ss, order);
  if (!isPaidOrder_(order) && data.action !== "sync_order" && order.memo) {
    const txSheet = ss.getSheetByName("GIAO_DICH");
    if (txSheet && txSheet.getLastRow() > 1) {
      const transactions = txSheet.getRange(2, 1, txSheet.getLastRow() - 1, 8).getValues();
      const matches = transactions.map((row, i) => ({row: row, number: i + 2})).filter(item => paidStatus_(item.row[3]) && (!item.row[7] || String(item.row[7]) === String(order.orderId)) && normalizeMemo_(item.row[2]).includes(normalizeMemo_(order.memo)) && money_(item.row[1]) >= money_(order.amountRaw || order.amount));
      if (matches.length === 1) {
        const tx = matches[0];
        order.paymentTxId = tx.row[0]; order.paymentKey = tx.row[6]; order.paidAt = tx.row[4];
        order.amountRaw = money_(tx.row[1]); order.amount = order.amountRaw;
        order.paymentSource = "APIPay Webhook";
        order.status = order.licenseLink ? "Đã thanh toán (MBBank)" : "Đã thanh toán (Chờ cấp link)";
        txSheet.getRange(tx.number, 8).setValue(order.orderId);
        return upsertOrder_(ss, order, true);
      }
    }
  }
  let notificationsComplete = true;
  if (notify && isPaidOrder_(order)) {
    const sent = order.telegramSent ? JSON.parse(order.telegramSent) : {};
    const text = orderTelegramText_(order);
    const hash = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, text).map(b => ("0" + ((b + 256) % 256).toString(16)).slice(-2)).join("");
    for (const chatId of Array.from(new Set(BOT_CONFIG.TELEGRAM_CHAT_IDS || [BOT_CONFIG.TELEGRAM_CHAT_ID]))) {
      const receipt = sent[chatId];
      const messageId = receipt && typeof receipt === "object" ? receipt.messageId : receipt;
      if (receipt && receipt.contentHash === hash) continue;
      const result = sendOrderTelegram_(order, chatId, messageId, text);
      if (result.ok) {
        sent[chatId] = {messageId: messageId || result.result.message_id, contentHash: hash};
        order.telegramSent = JSON.stringify(sent); write();
      } else notificationsComplete = false;
    }
    if (order.email && order.licenseLink && !order.emailSent && data.skipEmail !== true) {
      try { sendInvoiceEmail(order.name, order.email, order.phone, order.orderId, order.licenseLink); order.emailSent = nowVN_(); write(); } catch (err) { Logger.log(String(err)); }
    }
  }
  return {status: "success", notificationsComplete: notificationsComplete, orderId: order.orderId, duplicate: index >= 0, allocatedLink: order.licenseLink || "", columns: ORDER_COLUMNS.length};
}
function orderTelegramText_(order) {
  const fields = [["Mã đơn", order.orderId], ["Mã lượt truy cập", order.visitId], ["Mã phiên", order.sessionId], ["Khách", order.name], ["SĐT", order.phone], ["Email", order.email], ["Thanh toán lúc (GMT+7)", order.paidAt], ["Tạo đơn lúc", order.createdAt], ["Vào trang lúc", order.landingAt], ["IP", order.ip || "Không xác định"], ["Vị trí IP (ước lượng)", order.location || "Không xác định"], ["Thiết bị / Trình duyệt", [order.device, order.browser].filter(Boolean).join(" / ")], ["Nguồn khách", order.referrer || "Không xác định"], ["Tên miền", order.domain], ["URL vào trang", order.fullUrl], ["Referrer gốc", order.rawReferrer], ["UTM Source / Medium", [order.utmSource, order.utmMedium].filter(Boolean).join(" / ")], ["Chiến dịch", order.utmCampaign], ["UTM Content / Term", [order.utmContent, order.utmTerm].filter(Boolean).join(" / ")], ["FB / Google / TikTok Click ID", [order.fbclid, order.gclid, order.ttclid].filter(Boolean).join(" / ")], ["Nội dung CK", order.memo], ["Mã giao dịch", order.paymentTxId], ["Cổng thanh toán", order.paymentSource], ["Voucher", order.couponCode], ["Link cấp", order.licenseLink || "Chờ cấp link"], ["Trạng thái", order.status]];
  const title = "🟢 <b>ĐƠN HÀNG ĐÃ THANH TOÁN (" + html_(money_(order.amountRaw || order.amount).toLocaleString("vi-VN")) + "đ)</b>\n";
  const entries = fields.filter(pair => pair[1]).map(pair => ({
    label: pair[0], value: String(pair[0].includes("lúc") ? displayTime_(pair[1]) : pair[1]),
    limit: ["URL vào trang", "Link cấp"].includes(pair[0]) ? 1500 : pair[0] === "Referrer gốc" ? 300 : 120
  }));
  const render = () => title + entries.map(entry => "<b>" + entry.label + ":</b> <code>" + html_(entry.value.length > entry.limit ? entry.value.slice(0, entry.limit) + "…" : entry.value) + "</code>").join("\n");
  let text = render();
  // Preserve ordinary complete campaign URLs while keeping Telegram's message within its size limit.
  while (text.length > 4000) {
    const entry = entries.filter(item => item.limit > 8 && item.value.length > 8).sort((a, b) => Math.min(b.limit, b.value.length) - Math.min(a.limit, a.value.length))[0];
    if (!entry) break;
    entry.limit = Math.max(8, Math.min(entry.limit, entry.value.length) - Math.max(16, Math.ceil((text.length - 4000) / 4)));
    text = render();
  }
  return text;
}
function sendOrderTelegram_(order, chatId, messageId, text) {
  const payload = {chat_id: chatId, text: text || orderTelegramText_(order), parse_mode: "HTML", disable_web_page_preview: true};
  if (messageId) payload.message_id = messageId;
  const method = messageId ? "editMessageText" : "sendMessage";
  const response = UrlFetchApp.fetch("https://api.telegram.org/bot" + BOT_CONFIG.TELEGRAM_BOT_TOKEN + "/" + method, {method: "post", contentType: "application/json", muteHttpExceptions: true, payload: JSON.stringify(payload)});
  const result = JSON.parse(response.getContentText() || "{}");
  if (messageId && !result.ok && /message is not modified/i.test(String(result.description))) return {ok: true, result: {message_id: messageId}};
  if (!result.ok) Logger.log("Telegram " + chatId + ": " + String(result.description));
  return result;
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
          Hệ thống API Pay & Ngân hàng MBBank đã ghi nhận thành công giao dịch <strong>119.000 VNĐ</strong> của bạn.
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
        amount: "119.000 VNĐ",
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
    "119.000 VNĐ",
    "PRO18T 0912345678",
    "https://one.google.com/promo/gemini-pro/ACT-NAM7492",
    Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss")
  );
}
