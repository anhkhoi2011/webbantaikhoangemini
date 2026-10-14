@echo off
chcp 65001 >nul
title ĐẨY MÃ NGUỒN LÊN GITHUB - ANHKHOI2011/WEBBANTAIKHOANGEMINI
echo =====================================================================
echo  HỆ THỐNG ĐẨY MÃ NGUỒN LÊN GITHUB: anhkhoi2011/webbantaikhoangemini
echo =====================================================================
echo.
echo Repo đích: https://github.com/anhkhoi2011/webbantaikhoangemini.git
echo.
echo Chọn hình thức đẩy mã nguồn:
echo [1] Đăng nhập bằng Trình duyệt Web (GitHub Browser Login)
echo [2] Dán mã GitHub Personal Access Token (PAT)
echo.
set /p opt="Lựa chọn của bạn (1 hoặc 2): "

if "%opt%"=="2" (
    echo.
    set /p token="Dán mã GitHub Token (ghp_...): "
    echo.
    echo Đang đẩy mã nguồn lên GitHub bằng Token...
    "C:\Users\Admin\MinGit\cmd\git.exe" push https://anhkhoi2011:%token%@github.com/anhkhoi2011/webbantaikhoangemini.git main --force
) else (
    echo.
    echo Đang kết nối GitHub... (Vui lòng xác nhận đăng nhập nếu có cửa sổ hiện ra)
    "C:\Users\Admin\MinGit\cmd\git.exe" push -u origin main
)

echo.
echo =====================================================================
echo Hoàn tất! Vui lòng kiểm tra tại: https://github.com/anhkhoi2011/webbantaikhoangemini
echo =====================================================================
pause
