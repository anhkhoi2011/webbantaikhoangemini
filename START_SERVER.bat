@echo off
chcp 65001 >nul
title Gemini Pro E-Commerce & CRM System
echo ======================================================================
echo    HE THONG BAN HANG & QUAN TRI GEMINI PRO 18 THANG (CRM REALTIME)
echo ======================================================================
echo.
echo [*] Dang khoi dong may chu Web Server tren Cong 8080...
echo [*] Trang Ban Hang: http://localhost:8080/
echo [*] Trang Quan Tri: http://localhost:8080/admin
echo.
echo [*] Dang tu dong mo trinh duyet...
start http://localhost:8080/
start http://localhost:8080/admin
echo.
echo [*] May chu dang chay. Nhan Ctrl + C hoac dong cua so nay de tat server.
powershell -ExecutionPolicy Bypass -File server.ps1
pause
