#include "wifi.h"

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "nvs_flash.h"


#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "WIFI";

static EventGroupHandle_t wifi_event_group;


/* =========================================================
   XỬ LÝ EVENT WIFI
   ========================================================= */
static void wifi_event_handler(void *arg,
                               esp_event_base_t event_base,
                               int32_t event_id,
                               void *event_data)
{
    // Wi-Fi Station vừa khởi động
    if (event_base == WIFI_EVENT &&
        event_id == WIFI_EVENT_STA_START)
    {
        ESP_LOGI(TAG, "Dang ket noi WiFi...");

        esp_wifi_connect();
    }

    // Mất kết nối Wi-Fi
    else if (event_base == WIFI_EVENT &&
             event_id == WIFI_EVENT_STA_DISCONNECTED)
    {
        ESP_LOGW(TAG, "Mat WiFi, dang ket noi lai...");

        xEventGroupClearBits(
            wifi_event_group,
            WIFI_CONNECTED_BIT
        );

        esp_wifi_connect();
    }

    // ESP32 đã nhận được IP
    else if (event_base == IP_EVENT &&
             event_id == IP_EVENT_STA_GOT_IP)
    {
        ip_event_got_ip_t *event =
            (ip_event_got_ip_t *)event_data;

        ESP_LOGI(TAG, "Ket noi WiFi thanh cong!");

        ESP_LOGI(TAG,
                 "IP ESP32: " IPSTR,
                 IP2STR(&event->ip_info.ip));

        // Báo cho chương trình chính biết Wi-Fi đã sẵn sàng
        xEventGroupSetBits(
            wifi_event_group,
            WIFI_CONNECTED_BIT
        );
    }
}


/* =========================================================
   KẾT NỐI WIFI
   ========================================================= */
void wifi_connect(const char *ssid, const char *password)
{
    /* -------------------------
       1. Khởi tạo NVS
       ------------------------- */

    esp_err_t ret = nvs_flash_init();

    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND)
    {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }


    /* -------------------------
       2. Event Group
       ------------------------- */

    wifi_event_group = xEventGroupCreate();


    /* -------------------------
       3. Khởi tạo TCP/IP
       ------------------------- */

    ESP_ERROR_CHECK(
        esp_netif_init()
    );


    /* -------------------------
       4. Event loop
       ------------------------- */

    ESP_ERROR_CHECK(
        esp_event_loop_create_default()
    );


    /* -------------------------
       5. Tạo Wi-Fi Station
       ------------------------- */

    esp_netif_create_default_wifi_sta();


    /* -------------------------
       6. Khởi tạo Wi-Fi driver
       ------------------------- */

    wifi_init_config_t cfg =
        WIFI_INIT_CONFIG_DEFAULT();

    ESP_ERROR_CHECK(
        esp_wifi_init(&cfg)
    );


    /* -------------------------
       7. Đăng ký event Wi-Fi
       ------------------------- */

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            WIFI_EVENT,
            ESP_EVENT_ANY_ID,
            &wifi_event_handler,
            NULL
        )
    );


    /* -------------------------
       8. Đăng ký event IP
       ------------------------- */

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            &wifi_event_handler,
            NULL
        )
    );


    /* -------------------------
       9. Cấu hình Wi-Fi
       ------------------------- */

    wifi_config_t wifi_config = {0};

    strncpy(
        (char *)wifi_config.sta.ssid,
        ssid,
        sizeof(wifi_config.sta.ssid) - 1
    );

    strncpy(
        (char *)wifi_config.sta.password,
        password,
        sizeof(wifi_config.sta.password) - 1
    );


    /* -------------------------
       10. Chế độ Station
       ------------------------- */

    ESP_ERROR_CHECK(
        esp_wifi_set_mode(WIFI_MODE_STA)
    );


    ESP_ERROR_CHECK(
        esp_wifi_set_config(
            WIFI_IF_STA,
            &wifi_config
        )
    );


    /* -------------------------
       11. Start Wi-Fi
       ------------------------- */

    ESP_ERROR_CHECK(
        esp_wifi_start()
    );


    /* -------------------------
       12. Chờ tới khi có IP
       ------------------------- */

    xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,
        pdTRUE,
        portMAX_DELAY
    );
}