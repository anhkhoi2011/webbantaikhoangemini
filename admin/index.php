<?php
// Tự động load trang quản trị admin trên hosting Nginx / Apache / LiteSpeed
if (file_exists(__DIR__ . '/index.html')) {
    include __DIR__ . '/index.html';
} else if (file_exists(__DIR__ . '/../admin.html')) {
    include __DIR__ . '/../admin.html';
}
