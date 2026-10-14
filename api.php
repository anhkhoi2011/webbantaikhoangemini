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

function readJsonFile($filename, $default = []) {
    $fullPath = __DIR__ . '/' . basename($filename);
    if (file_exists($fullPath)) {
        $content = file_get_contents($fullPath);
        $data = json_decode($content, true);
        return $data !== null ? $data : $default;
    }
    return $default;
}

function writeJsonFile($filename, $data) {
    $fullPath = __DIR__ . '/' . basename($filename);
    file_put_contents($fullPath, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

function getPostJson() {
    $raw = file_get_contents('php://input');
    return json_decode($raw, true) ?: [];
}

// 1. API: Cấu hình cổng thanh toán
if (strpos($requestUri, '/api/payment-config') !== false) {
    if ($method === 'POST') {
        $body = getPostJson();
        writeJsonFile('payment_config.json', $body);
        echo json_encode(["status" => "success", "message" => "Payment config saved"]);
    } else {
        echo json_encode(readJsonFile('payment_config.json', []));
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

// 3. API: Đơn hàng (Orders)
if (strpos($requestUri, '/api/orders') !== false) {
    if ($method === 'POST') {
        $body = getPostJson();
        $orders = readJsonFile('orders.json', []);
        $orderId = isset($body['orderId']) ? $body['orderId'] : ('#GEM-' . rand(1000, 9999));
        $body['orderId'] = $orderId;

        $found = false;
        foreach ($orders as $k => $o) {
            if (isset($o['orderId']) && $o['orderId'] === $orderId) {
                $orders[$k] = $body;
                $found = true;
                break;
            }
        }
        if (!$found) {
            array_unshift($orders, $body);
        }
        writeJsonFile('orders.json', array_slice($orders, 0, 500));

        // Bắn Telegram & Google Sheet nếu đã thanh toán
        $statusStr = mb_strtolower(isset($body['status']) ? $body['status'] : '');
        $isPaid = (strpos($statusStr, 'đã thanh toán') !== false || strpos($statusStr, 'thành công') !== false) && strpos($statusStr, 'chờ') === false;

        if ($isPaid) {
            $teleCfg = readJsonFile('telegram_config.json', []);
            $botToken = isset($teleCfg['botToken']) ? $teleCfg['botToken'] : '8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c';
            $chatId = isset($teleCfg['chatId']) ? $teleCfg['chatId'] : '-1004413665683';
            
            $msg = "🟢 <b>ĐƠN HÀNG MỚI (" . ($body['amount'] ?? '90.000 VNĐ') . ")</b>\n" .
                   "Mã đơn: <code>" . $orderId . "</code> • " . ($body['time'] ?? date('d/m/Y H:i:s')) . "\n" .
                   "Khách: <b>" . ($body['name'] ?? 'Khách') . "</b> | <code>" . ($body['phone'] ?? '') . "</code>\n" .
                   "Gmail: <code>" . ($body['email'] ?? '') . "</code>\n" .
                   "Nội dung: <code>" . ($body['memo'] ?? '') . "</code>\n" .
                   "Link cấp: <code>" . ($body['licenseLink'] ?? '') . "</code>";

            @file_get_contents("https://api.telegram.org/bot{$botToken}/sendMessage?" . http_build_query([
                'chat_id' => $chatId,
                'text' => $msg,
                'parse_mode' => 'HTML',
                'disable_web_page_preview' => 'true'
            ]));

            // Google Sheet Webhook
            $payCfg = readJsonFile('payment_config.json', []);
            if (!empty($payCfg['googleSheetWebhookUrl']) && strpos($payCfg['googleSheetWebhookUrl'], 'SAMPLE') === false) {
                $opts = [
                    'http' => [
                        'method' => 'POST',
                        'header' => "Content-Type: application/json\r\n",
                        'content' => json_encode([
                            'action' => 'new_order',
                            'time' => $body['time'] ?? date('d/m/Y H:i:s'),
                            'orderId' => $orderId,
                            'product' => $body['package'] ?? 'Google Gemini Pro 18 Tháng',
                            'amount' => $body['amount'] ?? '90.000 VNĐ',
                            'name' => $body['name'] ?? 'Khách',
                            'phone' => $body['phone'] ?? '',
                            'email' => $body['email'] ?? '',
                            'memo' => $body['memo'] ?? '',
                            'licenseLink' => $body['licenseLink'] ?? '',
                            'referrer' => $body['referrer'] ?? 'Trực tiếp',
                            'ipLocation' => ($body['ip'] ?? '127.0.0.1') . ' (' . ($body['location'] ?? 'VN') . ')',
                            'status' => $body['status'] ?? 'Đã thanh toán (MBBank)'
                        ])
                    ]
                ];
                @file_get_contents($payCfg['googleSheetWebhookUrl'], false, stream_context_create($opts));
            }
        }

        echo json_encode(["status" => "success", "orderId" => $orderId]);
    } else {
        echo json_encode(readJsonFile('orders.json', []));
    }
    exit();
}

// 4. API: Kiểm tra trạng thái thanh toán
if (strpos($requestUri, '/api/check-payment') !== false) {
    $memo = isset($_GET['memo']) ? strtoupper(str_replace(' ', '', $_GET['memo'])) : '';
    $phone = isset($_GET['phone']) ? str_replace(['+84', ' '], ['0', ''], $_GET['phone']) : '';

    $txs = readJsonFile('bank_transactions.json', []);
    foreach ($txs as $tx) {
        $desc = strtoupper(str_replace(' ', '', isset($tx['description']) ? $tx['description'] : ($tx['memo'] ?? '')));
        if (($phone && strpos($desc, $phone) !== false) || ($memo && strpos($desc, $memo) !== false)) {
            echo json_encode([
                "paid" => true,
                "message" => "Payment verified successfully",
                "transaction" => $tx,
                "source" => "Live Bank Feed"
            ]);
            exit();
        }
    }
    echo json_encode(["paid" => false, "message" => "Chờ quét mã thanh toán..."]);
    exit();
}

// 5. API: Mô phỏng thanh toán
if (strpos($requestUri, '/api/simulate-payment') !== false) {
    $body = getPostJson();
    $phone = $body['phone'] ?? '0901234567';
    $memo = $body['memo'] ?? "PRO18T {$phone}";
    $simTx = [
        "id" => "SIM_" . rand(100000, 999999),
        "amount" => intval($body['amount'] ?? 90000),
        "description" => $memo,
        "bank" => "MBBank",
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
    $botToken = $teleCfg['botToken'] ?? '8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c';
    $chatId = $teleCfg['chatId'] ?? '-1004413665683';
    
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
    $botToken = $teleCfg['botToken'] ?? '8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c';
    $chatId = $teleCfg['chatId'] ?? '-1004413665683';

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
        writeJsonFile('telegram_config.json', $body);
        echo json_encode(["status" => "success", "message" => "Telegram config saved"]);
    } else {
        echo json_encode(readJsonFile('telegram_config.json', []));
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
        $items = isset($payload['data']['records']) && is_array($payload['data']['records']) ? $payload['data']['records'] : $payload['data'];
    } elseif (isset($payload['records']) && is_array($payload['records'])) {
        $items = $payload['records'];
    } elseif (isset($payload['transactions']) && is_array($payload['transactions'])) {
        $items = $payload['transactions'];
    } elseif (!empty($payload)) {
        $items = isset($payload[0]) ? $payload : [$payload];
    }

    $currentTxs = readJsonFile('bank_transactions.json', []);
    foreach ($items as $it) {
        $amt = isset($it['amount']) ? intval($it['amount']) : 0;
        $desc = isset($it['description']) ? $it['description'] : ($it['memo'] ?? ($it['content'] ?? ''));
        if ($amt > 0) {
            array_unshift($currentTxs, [
                "id" => isset($it['id']) ? (string)$it['id'] : ("TX_" . rand(100000, 999999)),
                "amount" => $amt,
                "description" => $desc,
                "bank" => isset($it['bank']) ? $it['bank'] : "MBBank",
                "time" => isset($it['time']) ? $it['time'] : (isset($it['transactionDateTime']) ? $it['transactionDateTime'] : date('Y-m-d H:i:s')),
                "source" => "Webhook API Pay"
            ]);
        }
    }
    writeJsonFile('bank_transactions.json', array_slice($currentTxs, 0, 150));
    echo json_encode(["status" => "success", "message" => "Webhook processed", "count" => count($items)]);
    exit();
}

echo json_encode(["status" => "not_found"], 404);

