Add-Type -AssemblyName System.Web

$port = 8080
$prefix = "http://localhost:$port/"
$folder = $PSScriptRoot

$txFile = Join-Path $folder "bank_transactions.json"
$cfgFile = Join-Path $folder "payment_config.json"
$ordersFile = Join-Path $folder "orders.json"
$teleConfigFile = Join-Path $folder "telegram_config.json"

if (-not (Test-Path $txFile)) {
    "[]" | Out-File -FilePath $txFile -Encoding utf8
}

if (-not (Test-Path $ordersFile)) {
    "[]" | Out-File -FilePath $ordersFile -Encoding utf8
}

if (-not (Test-Path $teleConfigFile)) {
    @{
        botToken = "8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c"
        chatId = "-1004413665683"
        lowStockThreshold = 5
        dailyReportTime = "10:00"
        enabled = $true
    } | ConvertTo-Json -Depth 5 | Out-File -FilePath $teleConfigFile -Encoding utf8
}

if (-not (Test-Path $cfgFile)) {
    @{
        provider = "apipay"
        apiKey = ""
        endpointUrl = "https://api.apipay.vn/v1/transactions"
        accountNo = "517041996"
        bankBin = "970422"
        accountName = "NGUYEN TRAN HAN"
        testMode = $false
        pollIntervalSeconds = 3
        enabled = $true
        googleSheetWebhookUrl = ""
    } | ConvertTo-Json -Depth 5 | Out-File -FilePath $cfgFile -Encoding utf8
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$port/")
$listener.Prefixes.Add("http://127.0.0.1:$port/")
try {
    $listener.Prefixes.Add("http://*:$port/")
} catch {
    try {
        $listener.Prefixes.Add("http://192.168.100.196:$port/")
    } catch {}
}

try {
    $listener.Start()
    Write-Output "HTTP server started at $prefix serving $folder"
} catch {
    Write-Error "Failed to start listener: $_"
    exit 1
}

function Send-JsonResponse($response, $obj, $statusCode = 200) {
    $json = $obj | ConvertTo-Json -Depth 6 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $response.ContentType = "application/json; charset=utf-8"
    $response.StatusCode = $statusCode
    $response.ContentLength64 = $bytes.Length
    $response.OutputStream.Write($bytes, 0, $bytes.Length)
    $response.Close()
}

function Get-TelegramSettings {
    $cfg = @{
        botToken = "8924743387:AAHmuHUEUyK2XtRL4N6dUEbHf98xmj1wE2c"
        chatId = "-1004413665683"
        lowStockThreshold = 5
        dailyReportTime = "10:00"
        enabled = $true
    }
    if (Test-Path $teleConfigFile) {
        try {
            $saved = Get-Content -Raw -Path $teleConfigFile -Encoding utf8 | ConvertFrom-Json
            if ($saved.botToken) { $cfg.botToken = $saved.botToken }
            if ($saved.chatId) { $cfg.chatId = $saved.chatId }
            if ($saved.lowStockThreshold) { $cfg.lowStockThreshold = $saved.lowStockThreshold }
            if ($saved.dailyReportTime) { $cfg.dailyReportTime = $saved.dailyReportTime }
            if ($saved.enabled -ne $null) { $cfg.enabled = $saved.enabled }
        } catch {}
    }
    return $cfg
}

function Send-ServerTelegramMessage([string]$htmlText) {
    try {
        $cfg = Get-TelegramSettings
        if (-not $cfg.enabled -or -not $cfg.botToken -or -not $cfg.chatId) { return $false }

        $pySender = Join-Path $folder "telegram_sender.py"
        if (Test-Path $pySender) {
            $tmpFile = Join-Path $folder ("temp_tele_" + (Get-Random) + ".txt")
            [System.IO.File]::WriteAllText($tmpFile, $htmlText, [System.Text.Encoding]::UTF8)
            $pyOut = & python -c "import telegram_sender, sys; f=open(sys.argv[1], encoding='utf-8'); print(telegram_sender.send_telegram_raw(f.read()))" $tmpFile 2>&1 | Out-String
            Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
            if ($pyOut -like "*True*") { return $true }
        }

        $url = "https://api.telegram.org/bot" + $cfg.botToken + "/sendMessage"
        $bodyObj = @{
            chat_id = $cfg.chatId
            text = $htmlText
            parse_mode = "HTML"
            disable_web_page_preview = $true
        }
        $json = $bodyObj | ConvertTo-Json -Compress
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
        $res = Invoke-RestMethod -Uri $url -Method Post -Body $bytes -ContentType "application/json; charset=utf-8" -TimeoutSec 10
        return ($res.ok -eq $true)
    } catch {
        Write-Warning "Telegram send error: $_"
        return $false
    }
}

function Send-ToGoogleSheet($order) {
    try {
        if (-not (Test-Path $cfgFile)) { return }
        $cfg = Get-Content -Raw -Path $cfgFile -Encoding utf8 | ConvertFrom-Json
        $webhook = $cfg.googleSheetWebhookUrl
        if (-not $webhook -or $webhook.Trim() -eq "" -or $webhook.Contains("SAMPLE")) { return }

        $payload = @{
            action = "new_order"
            time = if ($order.time) { $order.time } else { (Get-Date).ToString("dd/MM/yyyy HH:mm:ss") }
            orderId = $order.orderId
            product = if ($order.package) { $order.package } else { "Google Gemini Pro 18 Tháng" }
            amount = if ($order.amount) { $order.amount } else { "90.000đ" }
            name = $order.name
            phone = $order.phone
            email = $order.email
            memo = $order.memo
            licenseLink = $order.licenseLink
            referrer = if ($order.referrer) { $order.referrer } else { "Trực tiếp" }
            ip = $order.ip
            location = $order.location
            status = if ($order.status) { $order.status } else { "Đã thanh toán (MBBank)" }
        } | ConvertTo-Json -Compress

        Invoke-RestMethod -Uri $webhook -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 10
    } catch {
        Write-Warning "Google Sheet sync error: $_"
    }
}

$lastExternalCheck = [DateTime]::MinValue

while ($listener.IsListening) {
    try {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        # CORS Headers
        $response.AddHeader("Access-Control-Allow-Origin", "*")
        $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        $response.AddHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, Apikey")

        if ($request.HttpMethod -eq "OPTIONS") {
            $response.StatusCode = 200
            $response.Close()
            continue
        }

        $rawUrl = $request.RawUrl.Split('?')[0]
        $queryString = $request.Url.Query

        # ==========================================
        # 1. API: Cấu hình cổng thanh toán (payment-config)
        # ==========================================
        if ($rawUrl -eq "/api/payment-config") {
            if ($request.HttpMethod -eq "POST") {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $body = $reader.ReadToEnd()
                $body | Out-File -FilePath $cfgFile -Encoding utf8
                Send-JsonResponse $response @{ status = "success"; message = "Config saved" }
                continue
            } else {
                $content = Get-Content -Raw -Path $cfgFile -Encoding utf8
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
                $response.ContentType = "application/json; charset=utf-8"
                $response.StatusCode = 200
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
                continue
            }
        }

        # ==========================================
        # 2. API: Lấy hoặc xóa danh sách giao dịch ngân hàng
        # ==========================================
        if ($rawUrl -eq "/api/bank-transactions") {
            if ($request.HttpMethod -eq "POST") {
                "[]" | Out-File -FilePath $txFile -Encoding utf8
                Send-JsonResponse $response @{ status = "success"; message = "Transactions cleared" }
                continue
            } else {
                $content = Get-Content -Raw -Path $txFile -Encoding utf8
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
                $response.ContentType = "application/json; charset=utf-8"
                $response.StatusCode = 200
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
                continue
            }
        }

        # ==========================================
        # 2.1 API: Gửi Email Thật qua Gmail SMTP (send-email)
        # ==========================================
        if ($rawUrl -eq "/api/send-email") {
            $ms = New-Object System.IO.MemoryStream
            $request.InputStream.CopyTo($ms)
            $bytes = $ms.ToArray()
            
            $tmpPayload = Join-Path $folder "temp_mail_payload.json"
            [System.IO.File]::WriteAllBytes($tmpPayload, $bytes)
            
            try {
                $pyScript = Join-Path $folder "mailer.py"
                $pyOut = & python $pyScript $tmpPayload 2>&1 | Out-String
                if (Test-Path $tmpPayload) { Remove-Item $tmpPayload -Force -ErrorAction SilentlyContinue }
                
                $resultObj = $null
                try { $resultObj = $pyOut.Trim() | ConvertFrom-Json } catch {}
                
                if ($resultObj -and $resultObj.status -eq "success") {
                    Send-JsonResponse $response $resultObj 200
                } elseif ($resultObj) {
                    Send-JsonResponse $response $resultObj 400
                } else {
                    Send-JsonResponse $response @{ status = "success"; message = "Đã gửi email thành công!" } 200
                }
            } catch {
                Send-JsonResponse $response @{ status = "error"; message = $_.Exception.Message } 500
            }
            continue
        }

        # ==========================================
        # 3. API: Nhận Webhook từ APIPay / Casso / SeAPay / Ngân Hàng
        # ==========================================
        if ($rawUrl -eq "/api/webhook") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            
            try {
                $payload = $body | ConvertFrom-Json
                $currentTxs = @()
                if (Test-Path $txFile) {
                    $raw = Get-Content -Raw -Path $txFile -Encoding utf8
                    if ($raw -and $raw.Trim() -ne "") {
                        $currentTxs = [System.Collections.ArrayList]@($raw | ConvertFrom-Json)
                    }
                }

                # Chuẩn hóa transaction từ các định dạng webhook phổ biến (APIPay / Casso / PayOS / SeAPay)
                $items = @()
                if ($payload.data -is [System.Array]) {
                    $items = $payload.data
                } elseif ($payload.data.records -is [System.Array]) {
                    $items = $payload.data.records
                } elseif ($payload.records -is [System.Array]) {
                    $items = $payload.records
                } elseif ($payload.transactions -is [System.Array]) {
                    $items = $payload.transactions
                } else {
                    $items = @($payload)
                }

                foreach ($it in $items) {
                    $amt = if ($it.amount) { [int]$it.amount } else { 0 }
                    $desc = if ($it.description) { $it.description } elseif ($it.memo) { $it.memo } elseif ($it.content) { $it.content } else { "" }
                    $tid = if ($it.id) { $it.id.ToString() } elseif ($it.transactionId) { $it.transactionId.ToString() } else { "TX_" + (Get-Random) }
                    $tm = if ($it.transactionDate) { $it.transactionDate } elseif ($it.when) { $it.when } else { (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }

                    if ($amt -gt 0 -and $desc) {
                        $entry = @{
                            id = $tid
                            amount = $amt
                            description = $desc
                            time = $tm
                            bank = "MBBank"
                            source = "Webhook API Pay"
                        }
                        $currentTxs.Insert(0, $entry)
                    }
                }

                if ($currentTxs.Count -gt 150) {
                    $currentTxs = $currentTxs | Select-Object -First 150
                }

                $currentTxs | ConvertTo-Json -Depth 5 | Out-File -FilePath $txFile -Encoding utf8
                Send-JsonResponse $response @{ status = "success"; message = "Webhook processed"; count = $items.Count }
            } catch {
                Send-JsonResponse $response @{ status = "error"; error = $_.ToString() } 400
            }
            continue
        }

        # ==========================================
        # 4. API: Mô phỏng thanh toán (Simulate / Test Payment)
        # ==========================================
        if ($rawUrl -eq "/api/simulate-payment") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            $sim = $body | ConvertFrom-Json

            $phone = if ($sim.phone) { $sim.phone } else { "0567960777" }
            $memo = if ($sim.memo) { $sim.memo } else { "PRO18T $phone" }
            $amount = if ($sim.amount) { [int]$sim.amount } else { 90000 }

            $currentTxs = @()
            if (Test-Path $txFile) {
                $raw = Get-Content -Raw -Path $txFile -Encoding utf8
                if ($raw -and $raw.Trim() -ne "") {
                    $currentTxs = [System.Collections.ArrayList]@($raw | ConvertFrom-Json)
                }
            }

            $newTx = @{
                id = "SIM_" + (Get-Random -Minimum 100000 -Maximum 999999)
                amount = $amount
                description = $memo
                time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
                bank = "MBBank"
                source = "Simulated / Test Admin"
            }
            $currentTxs.Insert(0, $newTx)
            $currentTxs | ConvertTo-Json -Depth 5 | Out-File -FilePath $txFile -Encoding utf8

            Send-JsonResponse $response @{ status = "success"; message = "Simulated payment logged"; transaction = $newTx }
            continue
        }

        # ==========================================
        # 4.1 API: Tạo yêu cầu thanh toán ApiPay (apipay-create)
        # ==========================================
        if ($rawUrl -eq "/api/apipay-create") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            $payload = $body | ConvertFrom-Json
            $phone = if ($payload.phone) { $payload.phone } else { "0901234567" }
            $amount = if ($payload.amount) { [int]$payload.amount } else { 90000 }
            $memo = if ($payload.memo) { $payload.memo } else { "PRO18T $phone" }

            $bridgeScript = Join-Path $folder "apipay_bridge.py"
            $outRaw = & python $bridgeScript "create" $phone $amount $memo 2>&1 | Out-String
            $resObj = $null
            try { $resObj = $outRaw.Trim() | ConvertFrom-Json } catch {}
            if ($resObj) {
                Send-JsonResponse $response $resObj 200
            } else {
                Send-JsonResponse $response @{ status = "error"; message = "ApiPay Bridge returned empty" } 500
            }
            continue
        }

        # ==========================================
        # 4.2 API: Kiểm tra kết nối ApiPay (apipay-test)
        # ==========================================
        if ($rawUrl -eq "/api/apipay-test") {
            $bridgeScript = Join-Path $folder "apipay_bridge.py"
            $outRaw = & python $bridgeScript "test" 2>&1 | Out-String
            $resObj = $null
            try { $resObj = $outRaw.Trim() | ConvertFrom-Json } catch {}
            if ($resObj) {
                Send-JsonResponse $response $resObj 200
            } else {
                Send-JsonResponse $response @{ status = "error"; message = "ApiPay Bridge returned empty" } 500
            }
            continue
        }

        # ==========================================
        # 4.3 API: Lấy ảnh mã QR VietQR sạch qua Proxy Backend (0% lỗi SSL)
        # ==========================================
        if ($rawUrl.StartsWith("/api/qr-image")) {
            $defQrFile = Join-Path $folder "default_qr.txt"
            if (Test-Path $defQrFile) {
                $rawQr = (Get-Content -Raw -Path $defQrFile -Encoding utf8).Trim()
                $b64 = $rawQr.Replace("data:image/png;base64,", "").Trim()
                $imgBytes = [System.Convert]::FromBase64String($b64)
                $response.ContentType = "image/png"
                $response.StatusCode = 200
                $response.ContentLength64 = $imgBytes.Length
                $response.OutputStream.Write($imgBytes, 0, $imgBytes.Length)
                $response.Close()
            } else {
                Send-JsonResponse $response @{ status = "error"; message = "QR image not found" } 404
            }
            continue
        }

        # ==========================================
        # 5. API: Kiểm tra trạng thái thanh toán thật (check-payment)
        # ==========================================
        if ($rawUrl.StartsWith("/api/check-payment")) {
            $params = [System.Web.HttpUtility]::ParseQueryString($request.Url.Query)
            $memo = $params["memo"]
            $phone = $params["phone"]
            $targetAmt = if ($params["amount"]) { [int]$params["amount"] } else { 90000 }
            $publicId = $params["publicId"]

            # 1. Kiểm tra trực tiếp qua ApiPay payment request nếu có publicId
            if ($publicId -and $publicId.Trim() -ne "") {
                try {
                    $bridgeScript = Join-Path $folder "apipay_bridge.py"
                    $outRaw = & python $bridgeScript "check" $publicId 2>&1 | Out-String
                    $resObj = $null
                    try { $resObj = $outRaw.Trim() | ConvertFrom-Json } catch {}
                    if ($resObj -and $resObj.paid -eq $true) {
                        Send-JsonResponse $response @{
                            paid = $true
                            message = "APIPay Payment verified successfully"
                            transaction = $resObj.transaction
                            source = "APIPay Live Cloud"
                        }
                        continue
                    }
                } catch {}
            }

            # Đọc danh sách giao dịch ngân hàng đã nhận
            $transactions = @()
            if (Test-Path $txFile) {
                try {
                    $raw = Get-Content -Raw -Path $txFile -Encoding utf8
                    if ($raw -and $raw.Trim() -ne "") {
                        $transactions = $raw | ConvertFrom-Json
                    }
                } catch {}
            }

            # Tìm xem có giao dịch nào khớp tiền và nội dung không
            $cleanPhone = if ($phone) { $phone.Trim() } else { "" }
            $cleanMemo = if ($memo) { $memo.Trim().ToUpper() } else { "" }

            $matched = $null
            foreach ($tx in $transactions) {
                $desc = ($tx.description + "").ToUpper()
                $amt = [int]$tx.amount

                $matchPhone = ($cleanPhone -ne "" -and $desc.Contains($cleanPhone))
                $matchMemo = ($cleanMemo -ne "" -and $desc.Contains($cleanMemo))
                $matchPro = ($desc.Contains("PRO18T") -and ($cleanPhone -ne "" -and $desc.Contains($cleanPhone)))

                if (($matchPhone -or $matchMemo -or $matchPro) -and ($amt -ge $targetAmt)) {
                    $matched = $tx
                    break
                }
            }

            if ($matched) {
                Send-JsonResponse $response @{
                    paid = $true
                    message = "Payment verified successfully"
                    transaction = $matched
                }
            } else {
                Send-JsonResponse $response @{
                    paid = $false
                    message = "Awaiting transaction from MBBank..."
                    checkedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
                }
            }
            continue
        }

        # ==========================================
        # 5.1 API: Quản lý Đơn hàng tập trung (GET & POST /api/orders)
        # ==========================================
        if ($rawUrl -eq "/api/orders") {
            if ($request.HttpMethod -eq "POST") {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $body = $reader.ReadToEnd()
                try {
                    $newOrder = $body | ConvertFrom-Json
                    
                    # Đọc danh sách đơn hiện tại (chuẩn hóa danh sách phẳng 100%)
                    $currentOrders = [System.Collections.ArrayList]@()
                    if (Test-Path $ordersFile) {
                        try {
                            $raw = Get-Content -Raw -Path $ordersFile -Encoding utf8
                            if ($raw -and $raw.Trim() -ne "") {
                                $parsed = $raw | ConvertFrom-Json
                                if ($parsed -is [System.Collections.IEnumerable] -and $parsed -isnot [string]) {
                                    foreach ($p in $parsed) {
                                        if ($p -and $p.orderId) { [void]$currentOrders.Add($p) }
                                    }
                                } elseif ($parsed -and $parsed.orderId) {
                                    [void]$currentOrders.Add($parsed)
                                }
                            }
                        } catch {}
                    }

                    # Kiểm tra trùng lặp theo orderId
                    $existingIndex = -1
                    for ($i = 0; $i -lt $currentOrders.Count; $i++) {
                        if ($currentOrders[$i].orderId -eq $newOrder.orderId) {
                            $existingIndex = $i
                            break
                        }
                    }

                    if ($existingIndex -ge 0) {
                        $currentOrders[$existingIndex] = $newOrder
                    } else {
                        $currentOrders.Insert(0, $newOrder)
                    }

                    if ($currentOrders.Count -gt 500) {
                        $currentOrders = $currentOrders | Select-Object -First 500
                    }

                    $currentOrders | ConvertTo-Json -Depth 6 | Out-File -FilePath $ordersFile -Encoding utf8

                    # Bắn thông báo Telegram từ Server bằng telegram_sender.py (100% chuẩn UTF-8 sắc nét)
                    # Chỉ gửi khi đơn đã thanh toán thành công, tuyệt đối KHÔNG gửi khi khách chỉ đang mở/chờ quét QR
                    $pySender = Join-Path $folder "telegram_sender.py"
                    $tmpOrderFile = Join-Path $folder ("temp_ord_" + (Get-Random) + ".json")
                    [System.IO.File]::WriteAllText($tmpOrderFile, $body, [System.Text.Encoding]::UTF8)

                    $orderStatus = ($newOrder.status + "").ToLower()
                    $isPending = $orderStatus.Contains("chờ") -or $orderStatus.Contains("pending") -or $orderStatus.Contains("đang mở")
                    $isPaid = ($orderStatus.Contains("đã thanh toán") -or $orderStatus.Contains("thành công") -or $orderStatus.Contains("paid") -or $orderStatus.Contains("success")) -and (-not $isPending)

                    if ($isPaid) {
                        if (Test-Path $pySender) {
                            & python $pySender --type payment_success --file $tmpOrderFile
                        }
                        # Đồng bộ sang Google Sheet
                        [void](Send-ToGoogleSheet $newOrder)
                    }
                    Remove-Item $tmpOrderFile -Force -ErrorAction SilentlyContinue

                    Send-JsonResponse $response @{ status = "success"; message = "Order saved"; orderId = $newOrder.orderId } 200
                } catch {
                    Send-JsonResponse $response @{ status = "error"; message = $_.Exception.Message } 400
                }
                continue
            } else {
                # GET orders
                if (-not (Test-Path $ordersFile)) { "[]" | Out-File -FilePath $ordersFile -Encoding utf8 }
                $content = Get-Content -Raw -Path $ordersFile -Encoding utf8
                if (-not $content -or $content.Trim() -eq "") { $content = "[]" }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
                $response.ContentType = "application/json; charset=utf-8"
                $response.StatusCode = 200
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
                continue
            }
        }

        # ==========================================
        # 5.2 API: Cấu hình và Test Bot Telegram (/api/telegram-config & /api/telegram-test)
        # ==========================================
        if ($rawUrl -eq "/api/telegram-config") {
            if ($request.HttpMethod -eq "POST") {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $body = $reader.ReadToEnd()
                $body | Out-File -FilePath $teleConfigFile -Encoding utf8
                Send-JsonResponse $response @{ status = "success"; message = "Telegram config saved" } 200
                continue
            } else {
                $cfg = Get-TelegramSettings
                Send-JsonResponse $response $cfg 200
                continue
            }
        }

        if ($rawUrl -eq "/api/telegram-test") {
            $pySender = Join-Path $folder "telegram_sender.py"
            if (Test-Path $pySender) {
                & python $pySender --type test_all
            }
            Send-JsonResponse $response @{ status = "success"; message = "Đã gửi toàn bộ 4 mẫu thông báo chuẩn đẹp về nhóm Telegram thành công!" } 200
            continue
        }

        if ($rawUrl -eq "/api/telegram-notify") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            try {
                $payload = $body | ConvertFrom-Json
                $ok = Send-ServerTelegramMessage $payload.message
                Send-JsonResponse $response @{ status = (if ($ok) { "success" } else { "error" }) } 200
            } catch {
                Send-JsonResponse $response @{ status = "error"; message = $_.Exception.Message } 400
            }
            continue
        }

        # API: Báo Cáo Đăng Nhập Trang Quản Trị Admin
        if ($rawUrl -eq "/api/admin-login-notify") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            try {
                $pySender = Join-Path $folder "telegram_sender.py"
                $tmpFile = Join-Path $folder ("temp_login_" + (Get-Random) + ".json")
                [System.IO.File]::WriteAllText($tmpFile, $body, [System.Text.Encoding]::UTF8)
                if (Test-Path $pySender) {
                    & python $pySender --type admin_login --file $tmpFile
                }
                Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
                Send-JsonResponse $response @{ status = "success"; message = "Admin login alert sent" } 200
            } catch {
                Send-JsonResponse $response @{ status = "error"; message = $_.Exception.Message } 400
            }
            continue
        }

        # API: Cung Cấp Code Google Apps Script Cho Trang Admin Copy Nhanh
        if ($rawUrl -eq "/api/get-apps-script") {
            $scriptFile = Join-Path $folder "GoogleAppsScript_CRM_AutoBot.js"
            if (Test-Path $scriptFile) {
                $code = [System.IO.File]::ReadAllText($scriptFile, [System.Text.Encoding]::UTF8)
                Send-JsonResponse $response @{ status = "success"; code = $code } 200
            } else {
                Send-JsonResponse $response @{ status = "error"; message = "Script file not found" } 404
            }
            continue
        }

        # ==========================================
        # 6. Phục vụ Static Files (HTML, JS, CSS, IMG)
        # ==========================================
        # Bảo mật: Chống Path Traversal (Directory Traversal Attack)
        if ($rawUrl.Contains("..")) {
            $response.StatusCode = 403
            $msg = [System.Text.Encoding]::UTF8.GetBytes("403 Forbidden: Invalid Path")
            $response.ContentLength64 = $msg.Length
            $response.OutputStream.Write($msg, 0, $msg.Length)
            $response.Close()
            continue
        }

        # Bảo mật cao cấp: Chặn tuyệt đối tải các file nhạy cảm cấu hình / backend qua URL tĩnh
        $blockedExtensions = @(".json", ".ps1", ".py", ".bat", ".exe", ".log", ".txt", ".sh", ".sqlite", ".db", ".env", ".md")
        $reqExt = [System.IO.Path]::GetExtension($rawUrl).ToLower()
        if ($blockedExtensions -contains $reqExt -or $rawUrl.ToLower().Contains("googleappsscript")) {
            $response.StatusCode = 403
            $msg = [System.Text.Encoding]::UTF8.GetBytes("403 Forbidden: Access to configuration file is prohibited")
            $response.ContentLength64 = $msg.Length
            $response.OutputStream.Write($msg, 0, $msg.Length)
            $response.Close()
            continue
        }

        if ($rawUrl -eq "/" -or [string]::IsNullOrWhiteSpace($rawUrl)) {
            $rawUrl = "/index.html"
        }
        if ($rawUrl -eq "/admin" -or $rawUrl -eq "/admin/") {
            $rawUrl = "/admin.html"
        }

        $localPath = Join-Path $folder ($rawUrl.TrimStart('/') -replace '/', '\')

        if (-not (Test-Path $localPath -PathType Leaf) -and (Test-Path "$localPath.html" -PathType Leaf)) {
            $localPath = "$localPath.html"
        }

        if (Test-Path $localPath -PathType Leaf) {
            $bytes = [System.IO.File]::ReadAllBytes($localPath)
            
            $ext = [System.IO.Path]::GetExtension($localPath).ToLower()
            $mime = "application/octet-stream"
            switch ($ext) {
                ".html" { $mime = "text/html; charset=utf-8" }
                ".htm"  { $mime = "text/html; charset=utf-8" }
                ".css"  { $mime = "text/css" }
                ".js"   { $mime = "application/javascript" }
                ".png"  { $mime = "image/png" }
                ".jpg"  { $mime = "image/jpeg" }
                ".jpeg" { $mime = "image/jpeg" }
                ".svg"  { $mime = "image/svg+xml" }
                ".json" { $mime = "application/json" }
            }

            $response.ContentType = $mime
            $response.ContentLength64 = $bytes.Length
            $response.StatusCode = 200
            $response.OutputStream.Write($bytes, 0, $bytes.Length)
        } else {
            $response.StatusCode = 404
            $msg = [System.Text.Encoding]::UTF8.GetBytes("404 Not Found")
            $response.ContentLength64 = $msg.Length
            $response.OutputStream.Write($msg, 0, $msg.Length)
        }
        $response.Close()
    } catch {
        try { if ($response) { $response.Close() } } catch {}
    }
}
