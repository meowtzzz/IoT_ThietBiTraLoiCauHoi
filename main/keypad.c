#include "keypad.h"

#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define ROW1 GPIO_NUM_14
#define ROW2 GPIO_NUM_27
#define ROW3 GPIO_NUM_26
#define ROW4 GPIO_NUM_25

#define COL1 GPIO_NUM_33
#define COL2 GPIO_NUM_32
#define COL3 GPIO_NUM_21
#define COL4 GPIO_NUM_22

static const gpio_num_t row_pins[4] = {
    ROW1, ROW2, ROW3, ROW4
};

static const gpio_num_t col_pins[4] = {
    COL1, COL2, COL3, COL4
};

static const char key_map[4][4] = {
    {'1', '2', '3', 'A'},
    {'4', '5', '6', 'B'},
    {'7', '8', '9', 'C'},
    {'*', '0', '#', 'D'}
};

void keypad_init(void)
{
    // Cấu hình 4 hàng là OUTPUT
    for (int i = 0; i < 4; i++)
    {
        gpio_reset_pin(row_pins[i]);
        gpio_set_direction(row_pins[i], GPIO_MODE_OUTPUT);
        gpio_set_level(row_pins[i], 1);   // mặc định kéo lên 1
    }

    // Cấu hình 4 cột là INPUT + PULL-UP
    for (int i = 0; i < 4; i++)
    {
        gpio_reset_pin(col_pins[i]);
        gpio_set_direction(col_pins[i], GPIO_MODE_INPUT);
        gpio_set_pull_mode(col_pins[i], GPIO_PULLUP_ONLY);
    }
}

char keypad_get_key(void)
{
    for (int row = 0; row < 4; row++)
    {
        // Đưa tất cả row lên mức 1
        for (int i = 0; i < 4; i++)
        {
            gpio_set_level(row_pins[i], 1);
        }

        // Kéo row hiện tại xuống 0
        gpio_set_level(row_pins[row], 0);

        // Chờ tín hiệu ổn định
        vTaskDelay(pdMS_TO_TICKS(1));

        // Đọc 4 cột
        for (int col = 0; col < 4; col++)
        {
            if (gpio_get_level(col_pins[col]) == 0)
            {
                // chống dội phím
                vTaskDelay(pdMS_TO_TICKS(20));

                if (gpio_get_level(col_pins[col]) == 0)
                {
                    // chờ thả nút
                    while (gpio_get_level(col_pins[col]) == 0)
                    {
                        vTaskDelay(pdMS_TO_TICKS(10));
                    }

                    return key_map[row][col];
                }
            }
        }
    }

    return '\0';
}