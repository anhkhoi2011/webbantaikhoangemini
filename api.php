<?php
/**
 * API Handler for PHP Hosting (cPanel, Apache, Nginx, Hostinger, Vietnix, AZDIGI)
 * Google Gemini Pro 18 Tháng CRM
 */

header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With");
header("Content-Type: application/json; charset=utf-8");

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

$requestUri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$method = $_SERVER['REQUEST_METHOD'];
date_default_timezone_set('Asia/Ho_Chi_Minh');

function readJsonFile($filename, $default = []) {
    $fullPath = __DIR__ . '/' . basename($filename);
    if (file_exists($fullPath)) {
        $content = file_get_contents($fullPath);
        $data = json_decode($content, true);
        $data = $data !== null ? $data : $default;
        $section = ['payment_config.json' => 'payment', 'telegram_config.json' => 'telegram'][basename($filename)] ?? null;
        if ($section && is_array($data)) {
            $privatePath = __DIR__ . '/runtime_secrets.json';
            $private = file_exists($privatePath) ? (json_decode(file_get_contents($privatePath), true) ?: []) : [];
            $data = array_replace($data, array_filter($private[$section] ?? []));
            if ($section === 'payment') {
                if (getenv('APIPAY_ACCESS_KEY')) $data['accessKey'] = $data['apiKey'] = getenv('APIPAY_ACCESS_KEY');
                if (getenv('APIPAY_SECRET_KEY')) $data['secretKey'] = getenv('APIPAY_SECRET_KEY');
            }
            if (getenv('TELEGRAM_BOT_TOKEN')) $data[$section === 'telegram' ? 'botToken' : 'telegramBotToken'] = getenv('TELEGRAM_BOT_TOKEN');
        }
        return $data;
    }
    return $default;
}

function writeJsonFile($filename, $data) {
    $sections = ['payment_config.json' => ['payment', ['apiKey','accessKey','secretKey','telegramBotToken']], 'telegram_config.json' => ['telegram', ['botToken']]];
    if (isset($sections[basename($filename)]) && is_array($data)) {
        list($section, $fields) = $sections[basename($filename)];
        $privatePath = __DIR__ . '/runtime_secrets.json';
        $private = file_exists($privatePath) ? (json_decode(file_get_contents($privatePath), true) ?: []) : [];
        foreach ($fields as $field) {
            if (!empty($data[$field])) $private[$section][$field] = $data[$field];
            if (array_key_exists($field, $data)) $data[$field] = '';
        }
        if ($private) file_put_contents($privatePath, json_encode($private, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE), LOCK_EX);
    }
    $fullPath = __DIR__ . '/' . basename($filename);
    file_put_contents($fullPath, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

function getPostJson() {
    $raw = file_get_contents('php://input');
    return json_decode($raw, true) ?: [];
}

// ============================================
// KHO LICENSE TẬP TRUNG (ĐỒNG BỘ MỌI THIẾT BỊ)
// ============================================
$LICENSES_FILE = __DIR__ . '/licenses.json';

function normalizeLicense($item) {
    if (!is_array($item)) return null;
    $link = isset($item['link']) ? trim($item['link']) : '';
    if ($link === '' || strpos($link, 'GM-STOCK-') !== false || strpos($link, 'GM-KEY-') !== false) return null;
    if (!preg_match('/^https?:\/\//i', $link)) return null;
    return [
        'id' => isset($item['id']) ? intval($item['id']) : 0,
        'link' => $link,
        'status' => (isset($item['status']) && $item['status'] === 'Đã cấp') ? 'Đã cấp' : 'Sẵn sàng',
        'assignedTo' => isset($item['assignedTo']) ? substr($item['assignedTo'], 0, 300) : '-'
    ];
}

function readLicenses() {
    global $LICENSES_FILE;
    if (!file_exists($LICENSES_FILE)) return [];
    $data = json_decode(file_get_contents($LICENSES_FILE), true);
    if (!is_array($data)) return [];
    $out = [];
    foreach ($data as $item) {
        $n = normalizeLicense($item);
        if ($n) $out[] = $n;
    }
    return $out;
}

function writeLicenses($items) {
    global $LICENSES_FILE;
    file_put_contents($LICENSES_FILE, json_encode(array_values($items), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

function nextLicenseId($items) {
    $max = 0;
    foreach ($items as $i) { if (($i['id'] ?? 0) > $max) $max = $i['id']; }
    return $max + 1;
}

function licenseStock($items) {
    $c = 0; foreach ($items as $i) if (($i['status'] ?? '') === 'Sẵn sàng') $c++;
    return $c;
}

// 0. API: Kho License Tập Trung (Server-Side Shared Inventory)
if (strpos($requestUri, '/api/licenses') !== false) {
    if ($method === 'GET') {
        $items = readLicenses();
        echo json_encode(["status" => "success", "items" => $items, "available" => licenseStock($items)]);
        exit();
    }

    if ($method === 'POST') {
        $body = getPostJson();
        $action = strtolower(trim($body['action'] ?? ''));

        // 0.1 Nạp hàng loạt
        if ($action === 'bulk_add' || $action === 'add' || $action === 'import') {
            $newItems = $body['items'] ?? ($body['links'] ?? []);
            if (is_array($newItems) && isset($newItems[0]) && !is_array($newItems[0])) {
                $newItems = array_map(function($l) { return ['link' => $l]; }, $newItems);
            }
            $items = readLicenses();
            $existing = array_column($items, 'link');
            $added = 0; $skipped = [];
            foreach ($newItems as $raw) {
                $n = normalizeLicense($raw);
                if (!$n || in_array($n['link'], $existing)) { $skipped[] = is_array($raw) ? ($raw['link'] ?? json_encode($raw)) : $raw; continue; }
                $n['id'] = nextLicenseId($items);
                $items[] = $n; $existing[] = $n['link']; $added++;
            }
            writeLicenses($items);
            echo json_encode(["status" => "success", "items" => $items, "added" => $added, "skipped" => $skipped, "available" => licenseStock($items)]);
            exit();
        }

        // 0.2 Xóa 1 mã
        if ($action === 'delete') {
            $id = intval($body['id'] ?? 0);
            $items = readLicenses();
            $before = count($items);
            $items = array_filter($items, function($i) use ($id) { return ($i['id'] ?? 0) !== $id; });
            if (count($items) === $before) { http_response_code(404); echo json_encode(["status" => "error", "message" => "Không tìm thấy license"]); exit(); }
            writeLicenses($items);
            echo json_encode(["status" => "success", "items" => array_values($items), "available" => licenseStock($items)]);
            exit();
        }

        // 0.3 Xóa toàn bộ
        if ($action === 'clear') {
            writeLicenses([]);
            echo json_encode(["status" => "success", "items" => [], "available" => 0]);
            exit();
        }

        // 0.4 Cấp phát FIFO (không trùng lặp)
        if ($action === 'claim' || strpos($requestUri, '/api/licenses/claim') !== false) {
            $items = readLicenses();
            $avail = array_filter($items, function($i) { return ($i['status'] ?? '') === 'Sẵn sàng'; });
            usort($avail, function($a, $b) { return ($a['id'] ?? 0) - ($b['id'] ?? 0); });
            if (empty($avail)) {
                http_response_code(409);
                echo json_encode(["status" => "out_of_stock", "message" => "Kho hiện đã hết license", "available" => 0]);
                exit();
            }
            $selected = $avail[0];
            $name = substr($body['name'] ?? 'Khách hàng', 0, 120);
            $orderId = substr($body['orderId'] ?? '', 0, 80);
            $selected['status'] = 'Đã cấp';
            $selected['assignedTo'] = $orderId ? "$name ($orderId)" : $name;
            foreach ($items as $k => $it) { if (($it['id'] ?? 0) === ($selected['id'] ?? 0)) { $items[$k] = $selected; break; } }
            writeLicenses($items);
            echo json_encode(["status" => "success", "license" => $selected, "licenseLink" => $selected['link'], "available" => licenseStock($items)]);
            exit();
        }

        // 0.5 Cấp lại link cụ thể (Admin Reissue)
        if ($action === 'reissue' || strpos($requestUri, '/api/licenses/reissue') !== false) {
            $id = intval($body['id'] ?? 0);
            $items = readLicenses();
            $selected = null;
            foreach ($items as $k => $it) {
                if (($it['id'] ?? 0) === $id && ($it['status'] ?? '') === 'Sẵn sàng') { $selected = $it; $idx = $k; break; }
            }
            if (!$selected) { http_response_code(409); echo json_encode(["status" => "out_of_stock", "message" => "Không tìm thấy license sẵn sàng"]); exit(); }
            $name = substr($body['name'] ?? 'Khách hàng', 0, 120);
            $orderId = substr($body['orderId'] ?? '', 0, 80);
            $items[$idx]['status'] = 'Đã cấp';
            $items[$idx]['assignedTo'] = $orderId ? "$name ($orderId)" : $name;
            writeLicenses($items);
            echo json_encode(["status" => "success", "license" => $items[$idx], "licenseLink" => $items[$idx]['link'], "available" => licenseStock($items)]);
            exit();
        }

        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Action kho license không hợp lệ"]);
        exit();
    }
}

// 0.6 API: Auto-claim (Cấp + TỰ MUA khi hết kho)
// PHP hosting không chạy được Telethon Userbot -> trả trạng thái rõ ràng.
// Cấp thử từ kho trước; nếu hết thì báo userbot_runtime_unavailable.
if (strpos($requestUri, '/api/licenses/auto-claim') !== false && $method === 'POST') {
    $body = getPostJson();
    $name = substr($body['name'] ?? 'Khách hàng', 0, 120);
    $orderId = substr($body['orderId'] ?? '', 0, 80);
    $items = readLicenses();
    $avail = array_filter($items, function($i) { return ($i['status'] ?? '') === 'Sẵn sàng'; });
    usort($avail, function($a, $b) { return ($a['id'] ?? 0) - ($b['id'] ?? 0); });
    if (!empty($avail)) {
        $selected = $avail[0];
        $selected['status'] = 'Đã cấp';
        $selected['assignedTo'] = $orderId ? "$name ($orderId)" : $name;
        foreach ($items as $k => $it) { if (($it['id'] ?? 0) === ($selected['id'] ?? 0)) { $items[$k] = $selected; break; } }
        writeLicenses($items);
        echo json_encode(["status" => "success", "source" => "stock", "license" => $selected, "licenseLink" => $selected['link'], "available" => licenseStock($items)]);
        exit();
    }
    echo json_encode([
        "status" => "userbot_runtime_unavailable",
        "message" => "Kho hết link. Tự mua tự động chỉ hoạt động trên Python server (server.py) đã đăng nhập Userbot. Vui lòng nạp kho thủ công hoặc chạy server.py.",
        "available" => 0
    ]);
    exit();
}

// 1. API: Cấu hình cổng thanh toán

if (strpos($requestUri, '/api/payment-config') !== false) {
    if ($method === 'POST') {
        $body = getPostJson();
        writeJsonFile('payment_config.json', $body);
        echo json_encode(["status" => "success", "message" => "Payment config saved"]);
    } else {
        $cfg = readJsonFile('payment_config.json', []);
        foreach (['apiKey','accessKey','secretKey','googleSheetWebhookUrl','googleSheetUrl','appsScriptProjectUrl','telegramBotToken','telegramChatId'] as $secretKey) unset($cfg[$secretKey]);
        echo json_encode($cfg);
    }
    exit();
}

// 2. API: Lấy hoặc xóa biến động số dư
if (strpos($requestUri, '/api/bank-transactions') !== false) {
    if ($method === 'POST') {
        writeJsonFile('bank_transactions.json', []);
        echo json_encode(["status" => "success", "message" => "Transactions cleared"]);
    } else {
        echo json_encode(readJsonFile('bank_transactions.json', []));
    }
    exit();
}

// 2.1 API: Thống kê lượt truy cập tập trung (PHP hosting)
if (strpos($requestUri, '/api/track-visit') !== false && $method === 'POST') {
    $data = readJsonFile('visits.json', [
        'totalVisits' => 0, 'todayVisits' => 0, 'lastDate' => date('d/m/Y'),
        'devices' => ['mobile' => 0, 'desktop' => 0, 'other' => 0],
        'sources' => ['facebook' => 0, 'tiktok' => 0, 'google' => 0, 'zalo' => 0, 'direct' => 0, 'other' => 0],
        'visits' => []
    ]);
    $today = date('d/m/Y');
    if (($data['lastDate'] ?? '') !== $today) { $data['lastDate'] = $today; $data['todayVisits'] = 0; }
    $data['totalVisits'] = intval($data['totalVisits'] ?? 0) + 1;
    $data['todayVisits'] = intval($data['todayVisits'] ?? 0) + 1;
    $body = getPostJson();
    $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
    $device = trim($body['device'] ?? '') ?: (preg_match('/Mobile|Android|iPhone|iPad/i', $ua) ? 'Điện thoại' : 'Máy tính');
    $deviceKey = preg_match('/Mobile|Android|iPhone|iPad|Điện thoại/i', $device) ? 'mobile' : (preg_match('/Máy tính|PC|Desktop/i', $device) ? 'desktop' : 'other');
    $data['devices'][$deviceKey] = intval($data['devices'][$deviceKey] ?? 0) + 1;
    $refLabel = trim($body['referrer'] ?? '');
    $ref = strtolower($refLabel ?: ($body['rawReferrer'] ?? ''));
    parse_str(parse_url($body['fullUrl'] ?? '', PHP_URL_QUERY) ?: '', $query);
    if (strpos($ref, 'facebook') !== false || in_array($ref, ['fb', 'meta'], true) || (!$refLabel && isset($query['fbclid']))) { $source = 'facebook'; $refLabel = $refLabel ?: 'Facebook'; }
    elseif (strpos($ref, 'tiktok') !== false || (!$refLabel && isset($query['ttclid']))) { $source = 'tiktok'; $refLabel = $refLabel ?: 'TikTok'; }
    elseif (strpos($ref, 'google') !== false || (!$refLabel && isset($query['gclid']))) { $source = 'google'; $refLabel = $refLabel ?: 'Tìm kiếm Google'; }
    elseif (strpos($ref, 'zalo') !== false) { $source = 'zalo'; $refLabel = $refLabel ?: 'Zalo Chat'; }
    elseif (!$ref || strpos($ref, 'trực tiếp') !== false || in_array($ref, ['direct', 'truc tiep'], true)) { $source = 'direct'; $refLabel = $refLabel ?: 'Truy cập trực tiếp'; }
    else { $source = 'other'; $refLabel = $refLabel ?: 'Khác'; }
    $data['sources'][$source] = intval($data['sources'][$source] ?? 0) + 1;
    $entry = ['time' => $body['time'] ?? date('H:i:s d/m/Y'), 'ip' => $body['ip'] ?? ($_SERVER['REMOTE_ADDR'] ?? ''), 'location' => $body['location'] ?? 'Việt Nam', 'device' => $device, 'browser' => $body['browser'] ?? 'Trình duyệt Web', 'domain' => $body['domain'] ?? '', 'referrer' => $refLabel, 'fullUrl' => $body['fullUrl'] ?? '', 'rawReferrer' => $body['rawReferrer'] ?? ''];
    foreach (['utmSource', 'utmMedium', 'utmCampaign', 'utmContent', 'utmTerm', 'fbclid', 'gclid', 'ttclid', 'sessionId', 'visitId', 'visitedAt', 'landingAt', 'userAgent'] as $key) $entry[$key] = $body[$key] ?? '';
    array_unshift($data['visits'], $entry); $data['visits'] = array_slice($data['visits'], 0, 1000);
    writeJsonFile('visits.json', $data);
    echo json_encode(['status' => 'success', 'totalVisits' => $data['totalVisits'], 'todayVisits' => $data['todayVisits']]); exit();
}
if (strpos($requestUri, '/api/visits') !== false) {
    if ($method === 'POST' && (($body = getPostJson())['action'] ?? '') === 'clear') {
        writeJsonFile('visits.json', ['totalVisits' => 0, 'todayVisits' => 0, 'lastDate' => date('d/m/Y'), 'devices' => ['mobile'=>0,'desktop'=>0,'other'=>0], 'sources' => ['facebook'=>0,'tiktok'=>0,'google'=>0,'zalo'=>0,'direct'=>0,'other'=>0], 'visits' => []]);
        echo json_encode(['status' => 'success', 'message' => 'Visits cleared']); exit();
    }
    echo json_encode(readJsonFile('visits.json', [])); exit();
}

function orderIsPaid($order) {
    return preg_match('/đã thanh toán|da thanh toan|thành công|thanh cong|^(paid|completed|success)$/iu', $order['status'] ?? '') === 1;
}
function amountValue($value) {
    if (is_int($value) || is_float($value)) return intval($value);
    $text = trim((string)$value);
    if (preg_match('/^-?\d+[.,]\d{1,2}$/', $text)) return intval(str_replace(',', '.', $text));
    return (strpos($text, '-') === 0 ? -1 : 1) * intval(preg_replace('/[^0-9]/', '', $text));
}
function normalizeMemo($value) { return strtoupper(preg_replace('/\s+/', '', (string)$value)); }
function paymentKey($tx) {
    $amount = amountValue($tx['amount'] ?? $tx['creditAmount'] ?? $tx['transferAmount'] ?? 0);
    $content = normalizeMemo($tx['description'] ?? $tx['content'] ?? $tx['memo'] ?? '');
    $reference = $tx['bankReference'] ?? $tx['referenceCode'] ?? $tx['transactionReference'] ?? '';
    if (!$reference && preg_match('/PRO18T\d+$/', $content)) $reference = $tx['publicId'] ?? $tx['transactionId'] ?? $tx['paidAt'] ?? $tx['completedAt'] ?? $tx['transactionDateTime'] ?? $tx['time'] ?? $tx['createdAt'] ?? '';
    return hash('sha256', $reference . '|' . $amount . '|' . $content);
}
function paymentIsCurrent($tx, $order) {
    if (!preg_match('/^PRO18T\s*\d+$/i', $order['memo'] ?? '') || empty($order['createdAt'])) return true;
    $parse = function($value) {
        $text = (string)$value;
        if (preg_match('/^\d{2}\/\d{2}\/\d{4} /', $text)) {
            $date = DateTimeImmutable::createFromFormat('d/m/Y H:i:s', $text);
            return $date ? floatval($date->format('U.u')) : false;
        }
        try { return $text !== '' ? floatval((new DateTimeImmutable($text))->format('U.u')) : false; }
        catch (Exception $error) { return false; }
    };
    $created = $parse($order['createdAt']);
    $paid = $parse($tx['paidAt'] ?? $tx['completedAt'] ?? $tx['transactionDateTime'] ?? $tx['time'] ?? $tx['updatedAt'] ?? $tx['createdAt'] ?? '');
    return $created !== false && $paid !== false && $paid >= $created;
}
function syncSheetOrder($order) {
    $cfg = readJsonFile('payment_config.json', []);
    $webhook = $cfg['googleSheetWebhookUrl'] ?? '';
    if (!$webhook || strpos($webhook, 'SAMPLE') !== false) return ['status' => 'disabled'];
    $ctx = stream_context_create(['http' => ['timeout' => 15, 'ignore_errors' => true]]);
    $health = json_decode(@file_get_contents($webhook . '?action=health', false, $ctx), true);
    if (($health['protocolVersion'] ?? 0) !== 2) return ['status' => 'error', 'message' => 'Cần triển khai Apps Script v2 trước khi đồng bộ'];
    $payload = $order;
    foreach (['paidNotified','telegramSent','emailSent','sheetSyncError','sheetSyncedHash'] as $key) unset($payload[$key]);
    $payload['action'] = !empty($order['paidNotified']) ? 'sync_order' : (orderIsPaid($order) ? 'new_order' : 'pending_order');
    $payload['product'] = $order['package'] ?? $order['product'] ?? 'Google Gemini Pro 18 Tháng';
    $ctx = stream_context_create(['http' => ['method' => 'POST', 'header' => "Content-Type: application/json; charset=utf-8\r\n", 'content' => json_encode($payload, JSON_UNESCAPED_UNICODE), 'timeout' => 25, 'ignore_errors' => true]]);
    $result = json_decode(@file_get_contents($webhook, false, $ctx), true) ?: ['status' => 'error', 'message' => 'Google Sheet chưa xác nhận'];
    if (isset($result['notificationsComplete']) && $result['notificationsComplete'] === false) { $result['status'] = 'error'; $result['message'] = 'Sheet đã ghi, còn chat Telegram cần gửi lại'; }
    return $result;
}
function saveOrder($body, $verifiedPayment = false) {
    $handle = fopen(__DIR__ . '/orders.json', 'c+');
    if (!$handle || !flock($handle, LOCK_EX)) throw new RuntimeException('Không khóa được kho đơn');
    try {
        $orders = json_decode(stream_get_contents($handle), true) ?: [];
        $orderId = $body['orderId'] ?? ('#GEM-' . strtoupper(bin2hex(random_bytes(12))));
        $index = null; $previous = [];
        foreach ($orders as $i => $item) if (($item['orderId'] ?? '') === $orderId) { $index = $i; $previous = $item; break; }
        foreach (['paidNotified','telegramSent','emailSent','sheetSyncError','sheetSyncedHash','couponCounted'] as $flag) unset($body[$flag]);
        $order = array_replace($previous, array_filter($body, function($value) { return $value !== '' && $value !== null; }));
        if (!empty($previous['fullUrl'])) {
            foreach (['fullUrl','domain','referrer','rawReferrer','utmSource','utmMedium','utmCampaign','utmContent','utmTerm','fbclid','gclid','ttclid','sessionId','visitId','visitedAt','landingAt','isFromAd','attributionVersion','attributionUpdatedAt'] as $key) {
                $order[$key] = $previous[$key] ?? '';
            }
        } elseif (!empty($order['fullUrl'])) {
            $order['domain'] = strtolower(parse_url($order['fullUrl'], PHP_URL_HOST) ?: '');
        }
        if (orderIsPaid($order) && !orderIsPaid($previous) && !$verifiedPayment) throw new RuntimeException('Payment must be verified by the server before confirming the order');
        $order['orderId'] = $orderId;
        $order['createdAt'] = $previous['createdAt'] ?? $body['createdAt'] ?? date('c');
        if (empty($order['ip']) || in_array($order['ip'], ['127.0.0.1','::1'])) {
            $observedIp = trim(explode(',', $_SERVER['HTTP_CF_CONNECTING_IP'] ?? $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '')[0]);
            $order['ip'] = filter_var($observedIp, FILTER_VALIDATE_IP) ? $observedIp : '';
        }
        if (empty($order['userAgent'])) $order['userAgent'] = $_SERVER['HTTP_USER_AGENT'] ?? '';
        if (orderIsPaid($previous)) foreach (['status','paidAt','paymentTxId','paymentKey','licenseLink','amount','amountRaw'] as $key) if (!empty($previous[$key])) $order[$key] = $previous[$key];
        if (orderIsPaid($order)) {
            foreach ($orders as $other) {
                if (($other['orderId'] ?? '') === $orderId || !orderIsPaid($other)) continue;
                if ((!empty($order['paymentTxId']) && ($other['paymentTxId'] ?? '') === $order['paymentTxId']) || (!empty($order['paymentKey']) && ($other['paymentKey'] ?? '') === $order['paymentKey'])) throw new RuntimeException('Giao dịch đã thuộc đơn khác');
            }
            $order['paidAt'] = $previous['paidAt'] ?? $order['paidAt'] ?? date('c');
        }
        if ($index !== null) $orders[$index] = $order; else array_unshift($orders, $order);
        rewind($handle); ftruncate($handle, 0);
        if (fwrite($handle, json_encode(array_slice($orders, 0, 500), JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)) === false) throw new RuntimeException('Không lưu được đơn');
        fflush($handle);
        return $order;
    } finally { flock($handle, LOCK_UN); fclose($handle); }
}
// One owner sends notifications: Apps Script updates the Sheet and both Telegram chats.
if (strpos($requestUri, '/api/orders') !== false) {
    if ($method === 'POST') {
        try {
            $order = saveOrder(getPostJson());
            $sync = syncSheetOrder($order);
            echo json_encode(['status' => 'success', 'orderId' => $order['orderId'], 'order' => $order, 'sheetSync' => $sync['status'], 'sheetMessage' => $sync['message'] ?? '']);
        } catch (Throwable $error) {
            http_response_code(409);
            echo json_encode(['status' => 'error', 'message' => $error->getMessage()]);
        }
    } else echo json_encode(readJsonFile('orders.json', []));
    exit();
}
if (strpos($requestUri, '/api/check-payment') !== false) {
    $memo = normalizeMemo($_GET['memo'] ?? '');
    $orderId = $_GET['orderId'] ?? '';
    $orders = readJsonFile('orders.json', []);
    $order = null;
    foreach ($orders as $item) if (($item['orderId'] ?? '') === $orderId) { $order = $item; break; }
    if (!$order) { echo json_encode(['paid' => false, 'message' => 'Không tìm thấy đơn']); exit(); }
    if (orderIsPaid($order)) {
        syncSheetOrder($order);
        echo json_encode(['paid' => true, 'transaction' => $order, 'order' => $order, 'source' => 'Order Database']); exit();
    }
    $memo = normalizeMemo($order['memo'] ?? '');
    $expected = intval(preg_replace('/[^0-9]/', '', (string)($order['amountRaw'] ?? $order['amount'] ?? 0)));
    $pendingMatches = array_filter($orders, function($candidate) use ($order) { return !orderIsPaid($candidate) && normalizeMemo($candidate['memo'] ?? '') === normalizeMemo($order['memo'] ?? ''); });
    if (count($pendingMatches) > 1) { echo json_encode(['paid' => false]); exit(); }
    foreach (readJsonFile('bank_transactions.json', []) as $tx) {
        if (!paymentIsCurrent($tx, $order)) continue;
        if (strpos((string)($tx['id'] ?? ''), 'SIM_') === 0 && (readJsonFile('payment_config.json', [])['testMode'] ?? false) !== true) continue;
        $desc = normalizeMemo($tx['description'] ?? $tx['content'] ?? $tx['memo'] ?? '');
        $amount = intval($tx['amount'] ?? 0);
        if (!$memo || strpos($desc, $memo) === false || $amount < $expected || $amount <= 0 || !in_array(strtoupper($tx['status'] ?? 'COMPLETED'), ['PAID','COMPLETED','SUCCESS','CREDIT']) || (($tx['used_by_order'] ?? $orderId) !== $orderId)) continue;
        $key = $tx['paymentKey'] ?? paymentKey($tx);
        $used = false;
        foreach ($orders as $other) if (($other['orderId'] ?? '') !== $orderId && orderIsPaid($other) && (($other['paymentKey'] ?? '') === $key || ($other['paymentTxId'] ?? '') === ($tx['id'] ?? ''))) { $used = true; break; }
        if ($used) continue;
        $order['status'] = empty($order['licenseLink']) ? 'Đã thanh toán (Chờ cấp link)' : 'Đã thanh toán (BIDV)';
        $order['paymentTxId'] = $tx['id']; $order['paymentKey'] = $key;
        $order['paymentSource'] = $tx['source'] ?? 'Bank webhook';
        $order['paidAt'] = $tx['time'] ?? date('c');
        $order['amountRaw'] = $amount;
        $order = saveOrder($order, true); syncSheetOrder($order);
        echo json_encode(['paid' => true, 'transaction' => $tx, 'order' => $order, 'source' => $order['paymentSource']]); exit();
    }
    echo json_encode(['paid' => false]); exit();
}

// 5. API: Mô phỏng thanh toán
if (strpos($requestUri, '/api/simulate-payment') !== false) {
    if ((readJsonFile('payment_config.json', [])['testMode'] ?? false) !== true) { http_response_code(403); echo json_encode(['status' => 'error', 'message' => 'Simulation is disabled for live payments']); exit(); }
    $body = getPostJson();
    $phone = $body['phone'] ?? '0901234567';
    $memo = $body['memo'] ?? "PRO18T {$phone}";
    $simTx = [
        "id" => "SIM_" . rand(100000, 999999),
        "amount" => intval($body['amount'] ?? 129000),
        "description" => $memo,
        "bank" => "BIDV",
        "time" => date('Y-m-d H:i:s'),
        "source" => "Simulated / Test Admin"
    ];
    $txs = readJsonFile('bank_transactions.json', []);
    array_unshift($txs, $simTx);
    writeJsonFile('bank_transactions.json', array_slice($txs, 0, 150));
    echo json_encode(["status" => "success", "transaction" => $simTx]);
    exit();
}

// 6. API: Telegram Notify
if (strpos($requestUri, '/api/telegram-notify') !== false) {
    $body = getPostJson();
    $teleCfg = readJsonFile('telegram_config.json', []);
    $botToken = $teleCfg['botToken'] ?? '';
    $chatId = $teleCfg['chatId'] ?? '-5585627393';
    if ((string)$chatId === '-1004413665683') $chatId = '-5585627393';
    
    $res = @file_get_contents("https://api.telegram.org/bot{$botToken}/sendMessage?" . http_build_query([
        'chat_id' => $chatId,
        'text' => $body['message'] ?? '',
        'parse_mode' => 'HTML',
        'disable_web_page_preview' => 'true'
    ]));
    echo json_encode(["status" => $res ? "success" : "error"]);
    exit();
}

// 7. API: Admin Login Notify
if (strpos($requestUri, '/api/admin-login-notify') !== false) {
    $body = getPostJson();
    $teleCfg = readJsonFile('telegram_config.json', []);
    $botToken = $teleCfg['botToken'] ?? '';
    $chatId = $teleCfg['chatId'] ?? '-5585627393';
    if ((string)$chatId === '-1004413665683') $chatId = '-5585627393';

    $msg = "🛡️ <b>ĐĂNG NHẬP ADMIN THÀNH CÔNG</b>\n" .
           "Thời gian: " . ($body['time'] ?? date('d/m/Y H:i:s')) . "\n" .
           "IP: <code>" . ($body['ip'] ?? '127.0.0.1') . "</code> (" . ($body['location'] ?? 'VN') . ")\n" .
           "Thiết bị: " . ($body['device'] ?? 'Desktop');

    @file_get_contents("https://api.telegram.org/bot{$botToken}/sendMessage?" . http_build_query([
        'chat_id' => $chatId,
        'text' => $msg,
        'parse_mode' => 'HTML',
        'disable_web_page_preview' => 'true'
    ]));
    echo json_encode(["status" => "success"]);
    exit();
}

// 8. API: Cấu hình Telegram (Lấy và Lưu Bot Token & Chat ID)
if (strpos($requestUri, '/api/telegram-config') !== false) {
    if ($method === 'POST') {
        $body = getPostJson();
        if (($body['chatId'] ?? '') === '-1004413665683') $body['chatId'] = '-5585627393';
        if (isset($body['chatIds']) && is_array($body['chatIds'])) $body['chatIds'] = array_values(array_filter(array_map('strval', $body['chatIds']), function ($id) { return $id !== '-1004413665683'; }));
        writeJsonFile('telegram_config.json', $body);
        echo json_encode(["status" => "success", "message" => "Telegram config saved"]);
    } else {
        $cfg = readJsonFile('telegram_config.json', []);
        unset($cfg['botToken'], $cfg['chatId']);
        echo json_encode($cfg);
    }
    exit();
}

// 9. API: Get Apps Script
if (strpos($requestUri, '/api/get-apps-script') !== false) {
    $scriptFile = __DIR__ . '/GoogleAppsScript_CRM_AutoBot.js';
    if (file_exists($scriptFile)) {
        echo json_encode(["status" => "success", "code" => file_get_contents($scriptFile)]);
    } else {
        echo json_encode(["status" => "error", "message" => "File not found"]);
    }
    exit();
}

// 10. API: Nhận Webhook từ APIPay / Casso / SeAPay / Ngân Hàng
if (strpos($requestUri, '/api/webhook') !== false) {
    $payload = getPostJson();
    $items = [];
    if (isset($payload['data']) && is_array($payload['data'])) {
        $bankData = $payload['data'];
        $items = isset($bankData['records']) && is_array($bankData['records']) ? $bankData['records'] : (array_keys($bankData) === range(0, count($bankData) - 1) ? $bankData : [$bankData]);
    } elseif (isset($payload['records']) && is_array($payload['records'])) {
        $items = $payload['records'];
    } elseif (isset($payload['transactions']) && is_array($payload['transactions'])) {
        $items = $payload['transactions'];
    } elseif (!empty($payload)) {
        $items = isset($payload[0]) ? $payload : [$payload];
    }

    $currentTxs = readJsonFile('bank_transactions.json', []);
    foreach ($items as $it) {
        $amt = amountValue($it['amount'] ?? $it['creditAmount'] ?? $it['transferAmount'] ?? 0);
        $desc = isset($it['description']) ? $it['description'] : ($it['memo'] ?? ($it['content'] ?? ''));
        if ($amt > 0 && in_array(strtoupper($it['status'] ?? 'COMPLETED'), ['PAID','COMPLETED','SUCCESS','CREDIT']) && !in_array(strtolower($it['transferType'] ?? $it['direction'] ?? ''), ['out','debit'])) {
            $key = paymentKey($it);
            $duplicate = false;
            foreach ($currentTxs as $old) if (($old['paymentKey'] ?? paymentKey($old)) === $key) { $duplicate = true; break; }
            if ($duplicate) continue;
            array_unshift($currentTxs, [
                'paymentKey' => $key,
                'status' => strtoupper($it['status'] ?? 'COMPLETED'),
                "id" => isset($it['id']) ? (string)$it['id'] : $key,
                "amount" => $amt,
                "description" => $desc,
                "bank" => isset($it['bank']) ? $it['bank'] : "BIDV",
                "time" => $it['paidAt'] ?? $it['completedAt'] ?? $it['transactionDateTime'] ?? $it['time'] ?? $it['updatedAt'] ?? date('c'),
                "source" => "Webhook API Pay"
            ]);
        }
    }
    writeJsonFile('bank_transactions.json', array_slice($currentTxs, 0, 150));
    $pendingOrders = readJsonFile('orders.json', []);
    foreach ($pendingOrders as $pending) {
        if (orderIsPaid($pending) || empty($pending['memo'])) continue;
        $shared = array_filter($pendingOrders, function($other) use ($pending) { return !orderIsPaid($other) && normalizeMemo($other['memo'] ?? '') === normalizeMemo($pending['memo']); });
        if (count($shared) > 1) continue;
        foreach ($currentTxs as $tx) {
            if (!paymentIsCurrent($tx, $pending)) continue;
            if (strpos(normalizeMemo($tx['description'] ?? ''), normalizeMemo($pending['memo'])) === false) continue;
            $expected = intval(preg_replace('/[^0-9]/', '', (string)($pending['amountRaw'] ?? $pending['amount'] ?? 0)));
            if (intval($tx['amount'] ?? 0) < $expected || !in_array(strtoupper($tx['status'] ?? 'COMPLETED'), ['PAID','COMPLETED','SUCCESS','CREDIT'])) continue;
            $pending['paymentTxId'] = $tx['id']; $pending['paymentKey'] = $tx['paymentKey'] ?? paymentKey($tx);
            $pending['paidAt'] = $tx['time'] ?? date('c');
            $pending['paymentSource'] = $tx['source'] ?? 'Bank Webhook';
            $pending['status'] = empty($pending['licenseLink']) ? 'Đã thanh toán (Chờ cấp link)' : 'Đã thanh toán (BIDV)';
            try { syncSheetOrder(saveOrder($pending, true)); } catch (Throwable $error) { error_log('Payment reconciliation: ' . $error->getMessage()); }
            break;
        }
    }

    echo json_encode(["status" => "success", "message" => "Webhook processed", "count" => count($items)]);
    exit();
}

echo json_encode(["status" => "not_found"], 404);

