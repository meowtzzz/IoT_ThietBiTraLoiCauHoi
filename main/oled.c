#include "oled.h"

#include <stdio.h>
#include <string.h>

#include "driver/i2c_master.h"
#include "esp_log.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define OLED_SDA GPIO_NUM_18
#define OLED_SCL GPIO_NUM_19

#define OLED_WIDTH  128
#define OLED_HEIGHT 32

#define OLED_I2C_FREQ_HZ 400000


static const char *TAG = "OLED";

static i2c_master_bus_handle_t bus_handle;
static i2c_master_dev_handle_t oled_handle;

static uint8_t oled_address = 0x3C;


/* =========================================================
   FONT 5x7
   Chỉ cần số + chữ in hoa để test/project
   ========================================================= */

static const uint8_t font[][5] =
{
    /* space */
    {0x00,0x00,0x00,0x00,0x00},

    /* ! */
    {0x00,0x00,0x5F,0x00,0x00},

    /* " */
    {0x00,0x07,0x00,0x07,0x00},

    /* # */
    {0x14,0x7F,0x14,0x7F,0x14},

    /* $ */
    {0x24,0x2A,0x7F,0x2A,0x12},

    /* % */
    {0x23,0x13,0x08,0x64,0x62},

    /* & */
    {0x36,0x49,0x55,0x22,0x50},

    /* ' */
    {0x00,0x05,0x03,0x00,0x00},

    /* ( */
    {0x00,0x1C,0x22,0x41,0x00},

    /* ) */
    {0x00,0x41,0x22,0x1C,0x00},

    /* * */
    {0x14,0x08,0x3E,0x08,0x14},

    /* + */
    {0x08,0x08,0x3E,0x08,0x08},

    /* , */
    {0x00,0x50,0x30,0x00,0x00},

    /* - */
    {0x08,0x08,0x08,0x08,0x08},

    /* . */
    {0x00,0x60,0x60,0x00,0x00},

    /* / */
    {0x20,0x10,0x08,0x04,0x02},

    /* 0 */
    {0x3E,0x51,0x49,0x45,0x3E},

    /* 1 */
    {0x00,0x42,0x7F,0x40,0x00},

    /* 2 */
    {0x42,0x61,0x51,0x49,0x46},

    /* 3 */
    {0x21,0x41,0x45,0x4B,0x31},

    /* 4 */
    {0x18,0x14,0x12,0x7F,0x10},

    /* 5 */
    {0x27,0x45,0x45,0x45,0x39},

    /* 6 */
    {0x3C,0x4A,0x49,0x49,0x30},

    /* 7 */
    {0x01,0x71,0x09,0x05,0x03},

    /* 8 */
    {0x36,0x49,0x49,0x49,0x36},

    /* 9 */
    {0x06,0x49,0x49,0x29,0x1E},

    /* : */
    {0x00,0x36,0x36,0x00,0x00},

    /* ; */
    {0x00,0x56,0x36,0x00,0x00},

    /* < */
    {0x08,0x14,0x22,0x41,0x00},

    /* = */
    {0x14,0x14,0x14,0x14,0x14},

    /* > */
    {0x00,0x41,0x22,0x14,0x08},

    /* ? */
    {0x02,0x01,0x51,0x09,0x06},

    /* @ */
    {0x32,0x49,0x79,0x41,0x3E},

    /* A */
    {0x7E,0x11,0x11,0x11,0x7E},

    /* B */
    {0x7F,0x49,0x49,0x49,0x36},

    /* C */
    {0x3E,0x41,0x41,0x41,0x22},

    /* D */
    {0x7F,0x41,0x41,0x22,0x1C},

    /* E */
    {0x7F,0x49,0x49,0x49,0x41},

    /* F */
    {0x7F,0x09,0x09,0x09,0x01},

    /* G */
    {0x3E,0x41,0x49,0x49,0x7A},

    /* H */
    {0x7F,0x08,0x08,0x08,0x7F},

    /* I */
    {0x00,0x41,0x7F,0x41,0x00},

    /* J */
    {0x20,0x40,0x41,0x3F,0x01},

    /* K */
    {0x7F,0x08,0x14,0x22,0x41},

    /* L */
    {0x7F,0x40,0x40,0x40,0x40},

    /* M */
    {0x7F,0x02,0x0C,0x02,0x7F},

    /* N */
    {0x7F,0x04,0x08,0x10,0x7F},

    /* O */
    {0x3E,0x41,0x41,0x41,0x3E},

    /* P */
    {0x7F,0x09,0x09,0x09,0x06},

    /* Q */
    {0x3E,0x41,0x51,0x21,0x5E},

    /* R */
    {0x7F,0x09,0x19,0x29,0x46},

    /* S */
    {0x46,0x49,0x49,0x49,0x31},

    /* T */
    {0x01,0x01,0x7F,0x01,0x01},

    /* U */
    {0x3F,0x40,0x40,0x40,0x3F},

    /* V */
    {0x1F,0x20,0x40,0x20,0x1F},

    /* W */
    {0x7F,0x20,0x18,0x20,0x7F},

    /* X */
    {0x63,0x14,0x08,0x14,0x63},

    /* Y */
    {0x03,0x04,0x78,0x04,0x03},

    /* Z */
    {0x61,0x51,0x49,0x45,0x43}
};


/* =========================================================
   SEND COMMAND
   ========================================================= */

static esp_err_t oled_send_command(uint8_t command)
{
    uint8_t data[2];

    data[0] = 0x00;
    data[1] = command;

    return i2c_master_transmit(
        oled_handle,
        data,
        sizeof(data),
        100
    );
}


/* =========================================================
   SEND DATA
   ========================================================= */

static esp_err_t oled_send_data(
    const uint8_t *data,
    size_t length
)
{
    uint8_t buffer[129];

    if (length > 128)
        return ESP_ERR_INVALID_SIZE;

    buffer[0] = 0x40;

    memcpy(
        &buffer[1],
        data,
        length
    );

    return i2c_master_transmit(
        oled_handle,
        buffer,
        length + 1,
        100
    );
}


/* =========================================================
   INIT
   ========================================================= */

esp_err_t oled_init(void)
{
    i2c_master_bus_config_t bus_config = {

        .i2c_port = I2C_NUM_0,

        .sda_io_num = OLED_SDA,

        .scl_io_num = OLED_SCL,

        .clk_source =
            I2C_CLK_SRC_DEFAULT,

        .glitch_ignore_cnt = 7,

        .flags.enable_internal_pullup =
            true
    };


    ESP_ERROR_CHECK(
        i2c_new_master_bus(
            &bus_config,
            &bus_handle
        )
    );


    ESP_LOGI(
        TAG,
        "Dang tim OLED..."
    );


    if (
        i2c_master_probe(
            bus_handle,
            0x3C,
            100
        ) == ESP_OK
    )
    {
        oled_address = 0x3C;
    }

    else if (
        i2c_master_probe(
            bus_handle,
            0x3D,
            100
        ) == ESP_OK
    )
    {
        oled_address = 0x3D;
    }

    else
    {
        ESP_LOGE(
            TAG,
            "Khong tim thay OLED!"
        );

        return ESP_ERR_NOT_FOUND;
    }


    ESP_LOGI(
        TAG,
        "Tim thay OLED tai 0x%02X",
        oled_address
    );


    i2c_device_config_t dev_config = {

        .dev_addr_length =
            I2C_ADDR_BIT_LEN_7,

        .device_address =
            oled_address,

        .scl_speed_hz =
            OLED_I2C_FREQ_HZ
    };


    ESP_ERROR_CHECK(
        i2c_master_bus_add_device(
            bus_handle,
            &dev_config,
            &oled_handle
        )
    );


    vTaskDelay(
        pdMS_TO_TICKS(100)
    );


    /* SSD1306 init */

    oled_send_command(0xAE);

    oled_send_command(0x20);
    oled_send_command(0x02);

    oled_send_command(0xB0);

    oled_send_command(0xC8);

    oled_send_command(0x00);
    oled_send_command(0x10);

    oled_send_command(0x40);

    oled_send_command(0x81);
    oled_send_command(0x7F);

    oled_send_command(0xA1);

    oled_send_command(0xA6);

    oled_send_command(0xA8);
    oled_send_command(0x1F);

    oled_send_command(0xA4);

    oled_send_command(0xD3);
    oled_send_command(0x00);

    oled_send_command(0xD5);
    oled_send_command(0x80);

    oled_send_command(0xD9);
    oled_send_command(0xF1);

    oled_send_command(0xDA);
    oled_send_command(0x02);

    oled_send_command(0xDB);
    oled_send_command(0x40);

    oled_send_command(0x8D);
    oled_send_command(0x14);

    oled_send_command(0xAF);


    oled_clear();


    ESP_LOGI(
        TAG,
        "OLED khoi tao thanh cong"
    );


    return ESP_OK;
}


/* =========================================================
   CURSOR
   ========================================================= */

void oled_set_cursor(
    int x,
    int page
)
{
    oled_send_command(
        0xB0 + page
    );

    oled_send_command(
        0x00 + (x & 0x0F)
    );

    oled_send_command(
        0x10 + ((x >> 4) & 0x0F)
    );
}


/* =========================================================
   CLEAR
   ========================================================= */

void oled_clear(void)
{
    uint8_t empty[128];

    memset(
        empty,
        0x00,
        sizeof(empty)
    );


    for (
        int page = 0;
        page < 4;
        page++
    )
    {
        oled_set_cursor(
            0,
            page
        );

        oled_send_data(
            empty,
            sizeof(empty)
        );
    }


    oled_set_cursor(
        0,
        0
    );
}


/* =========================================================
   WRITE CHAR
   ========================================================= */

void oled_write_char(char c)
{
    if (
        c >= 'a'
        &&
        c <= 'z'
    )
    {
        c =
            c - 'a' + 'A';
    }


    if (
        c < 32
        ||
        c > 90
    )
    {
        c = '?';
    }


    uint8_t data[6];


    memcpy(
        data,
        font[c - 32],
        5
    );


    data[5] = 0x00;


    oled_send_data(
        data,
        sizeof(data)
    );
}


/* =========================================================
   WRITE STRING
   ========================================================= */

void oled_write_string(
    const char *str
)
{
    while (*str)
    {
        oled_write_char(
            *str
        );

        str++;
    }
}