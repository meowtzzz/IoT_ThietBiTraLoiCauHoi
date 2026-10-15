#include <stdio.h>
#include <string.h>
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"

#include "wifi.h"
#include "keypad.h"
#include "http_client.h"
#include "oled.h"

#define MAX_MSSV_LENGTH 20
#define STATE_POLL_INTERVAL_MS 1000

static const char *TAG = "MAIN";

typedef enum
{
    STATE_ENTER_MSSV,
    STATE_ANSWER
} system_state_t;

static int current_session_id = -1;
static int current_question_id = -1;
static int current_question_number = -1;
static int answered_question_id = -1;

static char selected_answer = '\0';
static char confirmed_answer = '\0';

static bool session_active = false;
static bool accepting_answers = false;
static bool device_state_reachable = false;


/* =========================================================
   OLED SCREENS
   ========================================================= */

static void show_enter_mssv(const char *mssv)
{
    oled_clear();
    oled_set_cursor(0, 0);
    oled_write_string("NHAP MSSV");
    oled_set_cursor(0, 2);
    oled_write_string((mssv != NULL && mssv[0] != '\0') ? mssv : ">");
    oled_set_cursor(0, 3);
    oled_write_string("# XAC NHAN");
}

static void show_no_session(void)
{
    oled_clear();
    oled_set_cursor(0, 0);
    oled_write_string("CHUA CO PHIEN");
    oled_set_cursor(0, 2);
    oled_write_string("CHO GIANG VIEN");
    oled_set_cursor(0, 3);
    oled_write_string("BAT DAU");
}

static void show_connection_error(void)
{
    oled_clear();
    oled_set_cursor(0, 0);
    oled_write_string("LOI KET NOI");
    oled_set_cursor(0, 2);
    oled_write_string("THU LAI");
}

static void show_question_closed(int question_number)
{
    char line[24];
    oled_clear();
    snprintf(line, sizeof(line), "CAU %d", question_number);
    oled_set_cursor(0, 0);
    oled_write_string(line);
    oled_set_cursor(0, 2);
    oled_write_string("CHUA MO");
    oled_set_cursor(0, 3);
    oled_write_string("NHAN DAP AN");
}

static void show_ready(int question_number)
{
    char line[24];
    oled_clear();
    snprintf(line, sizeof(line), "CAU %d", question_number);
    oled_set_cursor(0, 0);
    oled_write_string(line);
    oled_set_cursor(0, 2);
    oled_write_string("CHON A B C D");
    oled_set_cursor(0, 3);
    oled_write_string("SAN SANG");
}

static void show_selected(int question_number, char answer)
{
    char line[24];
    oled_clear();
    snprintf(line, sizeof(line), "CAU %d", question_number);
    oled_set_cursor(0, 0);
    oled_write_string(line);
    snprintf(line, sizeof(line), "DA CHON: %c", answer);
    oled_set_cursor(0, 2);
    oled_write_string(line);
    oled_set_cursor(0, 3);
    oled_write_string("# XAC NHAN");
}

static void show_sending(int question_number, char answer)
{
    char line[24];
    oled_clear();
    snprintf(line, sizeof(line), "CAU %d", question_number);
    oled_set_cursor(0, 0);
    oled_write_string(line);
    snprintf(line, sizeof(line), "DAP AN: %c", answer);
    oled_set_cursor(0, 2);
    oled_write_string(line);
    oled_set_cursor(0, 3);
    oled_write_string("DANG GUI...");
}

static void show_answered(int question_number, char answer)
{
    char line[24];
    oled_clear();
    snprintf(line, sizeof(line), "CAU %d", question_number);
    oled_set_cursor(0, 0);
    oled_write_string(line);
    snprintf(line, sizeof(line), "DA TRA LOI: %c", answer);
    oled_set_cursor(0, 2);
    oled_write_string(line);
    oled_set_cursor(0, 3);
    oled_write_string("CHO CAU TIEP");
}

static void render_answer_screen(void)
{
    if (!device_state_reachable)
    {
        show_connection_error();
        return;
    }

    if (!session_active)
    {
        show_no_session();
        return;
    }

    if (current_question_number < 1)
    {
        oled_clear();
        oled_set_cursor(0, 0);
        oled_write_string("CHUA CO CAU");
        oled_set_cursor(0, 2);
        oled_write_string("CHO GIANG VIEN");
        return;
    }

    if (answered_question_id == current_question_id &&
        confirmed_answer >= 'A' && confirmed_answer <= 'D')
    {
        show_answered(current_question_number, confirmed_answer);
        return;
    }

    if (!accepting_answers)
    {
        show_question_closed(current_question_number);
        return;
    }

    if (selected_answer != '\0')
    {
        show_selected(current_question_number, selected_answer);
        return;
    }

    show_ready(current_question_number);
}


/* Returns true when this is a new session/question identity. */
static bool apply_quiz_state(const quiz_state_info_t *incoming)
{
    bool identity_changed =
        incoming->active != session_active ||
        (incoming->active &&
         (incoming->session_id != current_session_id ||
          incoming->question_id != current_question_id));

    if (identity_changed)
    {
        selected_answer = '\0';
        confirmed_answer = '\0';
        answered_question_id = -1;
    }

    session_active = incoming->active;
    if (incoming->active)
    {
        current_session_id = incoming->session_id;
        current_question_id = incoming->question_id;
        current_question_number = incoming->question_number;
        accepting_answers = incoming->accepting_answers;
    }
    else
    {
        current_session_id = -1;
        current_question_id = -1;
        current_question_number = -1;
        accepting_answers = false;
    }

    return identity_changed;
}

static bool refresh_quiz_state(void)
{
    quiz_state_info_t incoming;
    esp_err_t err = http_get_quiz_state(&incoming);
    if (err != ESP_OK)
    {
        device_state_reachable = false;
        ESP_LOGW(TAG, "Khong doc duoc /device/state: %s", esp_err_to_name(err));
        render_answer_screen();
        return false;
    }

    device_state_reachable = true;
    bool changed = apply_quiz_state(&incoming);
    if (changed)
    {
        ESP_LOGI(TAG, "Session/cau hien tai: %d / %d (CAU %d)",
                 current_session_id, current_question_id, current_question_number);
    }
    render_answer_screen();
    return true;
}

static bool is_answer_key(char key)
{
    return key == 'A' || key == 'B' || key == 'C' || key == 'D';
}


/* =========================================================
   MAIN
   ========================================================= */

void app_main(void)
{
    if (oled_init() != ESP_OK)
    {
        ESP_LOGE(TAG, "Khong khoi tao duoc OLED");
    }

    oled_clear();
    oled_set_cursor(0, 0);
    oled_write_string("ESP32 CLICKER");
    oled_set_cursor(0, 2);
    oled_write_string("KET NOI WIFI...");

    wifi_connect("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");
    ESP_LOGI(TAG, "WiFi da san sang!");

    oled_clear();
    oled_set_cursor(0, 1);
    oled_write_string("WIFI OK");
    vTaskDelay(pdMS_TO_TICKS(800));

    keypad_init();
    ESP_LOGI(TAG, "Keypad da san sang!");

    char mssv[MAX_MSSV_LENGTH + 1] = "";
    int mssv_length = 0;
    system_state_t state = STATE_ENTER_MSSV;
    TickType_t last_state_poll = xTaskGetTickCount();

    show_enter_mssv(mssv);
    ESP_LOGI(TAG, "Nhap MSSV, sau do nhan # de xac nhan");

    while (1)
    {
        if (state == STATE_ANSWER &&
            (xTaskGetTickCount() - last_state_poll) >= pdMS_TO_TICKS(STATE_POLL_INTERVAL_MS))
        {
            last_state_poll = xTaskGetTickCount();
            refresh_quiz_state();
        }

        char key = keypad_get_key();
        if (key == '\0')
        {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        if (state == STATE_ENTER_MSSV)
        {
            if (key >= '0' && key <= '9')
            {
                if (mssv_length < MAX_MSSV_LENGTH)
                {
                    mssv[mssv_length++] = key;
                    mssv[mssv_length] = '\0';
                    show_enter_mssv(mssv);
                }
            }
            else if (key == '*')
            {
                memset(mssv, 0, sizeof(mssv));
                mssv_length = 0;
                show_enter_mssv(mssv);
            }
            else if (key == '#')
            {
                if (mssv_length == 0)
                {
                    oled_clear();
                    oled_set_cursor(0, 1);
                    oled_write_string("CHUA NHAP MSSV");
                    vTaskDelay(pdMS_TO_TICKS(900));
                    show_enter_mssv(mssv);
                    continue;
                }

                state = STATE_ANSWER;
                http_set_student_mssv(mssv);
                last_state_poll = xTaskGetTickCount();
                ESP_LOGI(TAG, "Da xac nhan MSSV: %s", mssv);
                refresh_quiz_state();
            }
        }
        else if (state == STATE_ANSWER)
        {
            if (key == '*')
            {
                ESP_LOGI(TAG, "Doi sinh vien tu MSSV: %s", mssv);
                memset(mssv, 0, sizeof(mssv));
                mssv_length = 0;

                current_session_id = -1;
                current_question_id = -1;
                current_question_number = -1;
                answered_question_id = -1;
                selected_answer = '\0';
                confirmed_answer = '\0';
                session_active = false;
                accepting_answers = false;
                device_state_reachable = false;
                http_set_student_mssv("");

                state = STATE_ENTER_MSSV;
                show_enter_mssv(mssv);
            }
            else if (is_answer_key(key))
            {
                if (device_state_reachable && session_active &&
                    accepting_answers && current_question_id >= 0 &&
                    answered_question_id != current_question_id)
                {
                    selected_answer = key;
                    ESP_LOGI(TAG, "MSSV %s da chon %c (chua gui)", mssv, key);
                    show_selected(current_question_number, selected_answer);
                }
            }
            else if (key == '#')
            {
                if (answered_question_id == current_question_id &&
                    confirmed_answer >= 'A' && confirmed_answer <= 'D')
                {
                    render_answer_screen();
                    continue;
                }

                if (selected_answer == '\0' || !device_state_reachable ||
                    !session_active || current_question_id < 0)
                {
                    render_answer_screen();
                    continue;
                }

                const int displayed_session_id = current_session_id;
                const int displayed_question_id = current_question_id;
                const char answer_to_send = selected_answer;

                show_sending(current_question_number, answer_to_send);

                /* Required final poll prevents sending a selection for a stale question. */
                if (!refresh_quiz_state())
                {
                    continue;
                }

                if (current_session_id != displayed_session_id ||
                    current_question_id != displayed_question_id)
                {
                    ESP_LOGI(TAG, "Huy dap an cu do session/cau da thay doi");
                    continue;
                }

                if (!session_active || !accepting_answers)
                {
                    render_answer_screen();
                    continue;
                }

                char answer_text[2] = {answer_to_send, '\0'};
                char previous_answer[2] = "";
                http_answer_result_t result = http_send_answer(
                    mssv, answer_text, previous_answer, sizeof(previous_answer));

                if (result == HTTP_ANSWER_ACCEPTED)
                {
                    answered_question_id = current_question_id;
                    confirmed_answer = answer_to_send;
                    selected_answer = '\0';
                    ESP_LOGI(TAG, "Server da nhan dap an %c cho CAU %d",
                             confirmed_answer, current_question_number);
                    render_answer_screen();
                }
                else if (result == HTTP_ANSWER_ALREADY_ANSWERED)
                {
                    answered_question_id = current_question_id;
                    confirmed_answer = (previous_answer[0] >= 'A' && previous_answer[0] <= 'D')
                        ? previous_answer[0] : answer_to_send;
                    selected_answer = '\0';
                    ESP_LOGW(TAG, "Cau nay da co dap an %c", confirmed_answer);
                    render_answer_screen();
                }
                else if (result == HTTP_ANSWER_QUESTION_CHANGED ||
                         result == HTTP_ANSWER_NO_ACTIVE_SESSION)
                {
                    ESP_LOGI(TAG, "Trang thai thay doi trong luc gui; dong bo lai");
                    refresh_quiz_state();
                }
                else if (result == HTTP_ANSWER_CLOSED ||
                         result == HTTP_ANSWER_STATE_NOT_CONFIRMED)
                {
                    ESP_LOGW(TAG, "Server chua mo nhan hoac can dong bo lai");
                    if (result == HTTP_ANSWER_STATE_NOT_CONFIRMED)
                    {
                        refresh_quiz_state();
                    }
                    else
                    {
                        accepting_answers = false;
                        render_answer_screen();
                    }
                }
                else
                {
                    device_state_reachable = false;
                    show_connection_error();
                }
            }
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
