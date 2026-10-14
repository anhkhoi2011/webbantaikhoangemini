@echo off
chcp 65001 >nul
set "PATH=C:\Users\Admin\MinGit\cmd;C:\Users\Admin\MinGit\mingw64\bin;%PATH%"
title ĐẨY MÃ NGUỒN LÊN GITHUB - ANHKHOI2011/WEBBANTAIKHOANGEMINI
echo =====================================================================
echo  HỆ THỐNG ĐẨY MÃ NGUỒN LÊN GITHUB: anhkhoi2011/webbantaikhoangemini
echo =====================================================================
echo.
echo Đang kết nối tới GitHub...
echo (Vui lòng bấm 'Authorize' trên cửa sổ trình duyệt bật lên)
echo.
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo 🎉 THÀNH CÔNG RỰC RỠ!
    echo Mã nguồn đã được tải lên: https://github.com/anhkhoi2011/webbantaikhoangemini
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo Hoặc bạn có thể dán mã GitHub Personal Access Token (PAT) để đẩy lên ngay:
    echo =====================================================================
    set /p token="Dán mã GitHub Token (ghp_...): "
    if defined token (
        git push https://anhkhoi2011:%token%@github.com/anhkhoi2011/webbantaikhoangemini.git main --force
    )
)
echo.
pause
