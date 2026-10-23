# Windows compatibility entrypoint. All payment handling lives in server.py.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = "1"
& python (Join-Path $PSScriptRoot "server.py")
exit $LASTEXITCODE
