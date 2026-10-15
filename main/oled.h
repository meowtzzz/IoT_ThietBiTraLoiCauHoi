#ifndef OLED_H
#define OLED_H

#include "esp_err.h"

esp_err_t oled_init(void);

void oled_clear(void);

void oled_set_cursor(int x, int page);

void oled_write_char(char c);

void oled_write_string(const char *str);

#endif