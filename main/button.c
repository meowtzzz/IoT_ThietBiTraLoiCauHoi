#include "button.h"

#include "driver/gpio.h"
#include "esp_err.h"

#define BUTTON_PIN GPIO_NUM_0

void button_init(void)
{
    gpio_config_t config = {
        .pin_bit_mask = (1ULL << BUTTON_PIN),
        .mode = GPIO_MODE_INPUT,

        // BOOT thường đã có pull-up trên board,
        // nhưng bật pull-up nội thêm cũng được
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,

        .intr_type = GPIO_INTR_DISABLE
    };

    ESP_ERROR_CHECK(gpio_config(&config));
}

bool button_is_pressed(void)
{
    return gpio_get_level(BUTTON_PIN) == 0;
}