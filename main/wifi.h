#ifndef WIFI_H
#define WIFI_H

/**
 * @brief Kết nối ESP32 vào Wi-Fi.
 *
 * Hàm sẽ chờ cho tới khi ESP32 nhận được địa chỉ IP.
 *
 * @param ssid Tên Wi-Fi
 * @param password Mật khẩu Wi-Fi
 */
void wifi_connect(const char *ssid, const char *password);

#endif