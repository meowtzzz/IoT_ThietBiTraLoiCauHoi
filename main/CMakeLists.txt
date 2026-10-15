idf_component_register(
    SRCS
        "main.c"
        "wifi.c"
        "keypad.c"
        "http_client.c"
        "oled.c"

    INCLUDE_DIRS "."

    REQUIRES
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_http_client
        esp_driver_gpio
        esp_driver_i2c
)