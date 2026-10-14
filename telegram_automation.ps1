# Telegram Automation Script - Gemini Enterprise CRM
param(
    [ValidateSet("daily_report", "low_stock", "payment_success", "test_all")]
    [string]$Mode = "test_all"
)

$sender = Join-Path $PSScriptRoot "telegram_sender.py"
& python $sender --type $Mode
