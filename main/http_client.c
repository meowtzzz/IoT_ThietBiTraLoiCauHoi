#include "http_client.h"

#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#define ANSWER_URL "http://192.168.1.100:5000/answer"
#define STATE_URL "http://192.168.1.100:5000/device/state"
#define MAX_RESPONSE_SIZE 384
#define MAX_MSSV_LENGTH 20

static const char *TAG = "HTTP";
static char current_mssv[MAX_MSSV_LENGTH + 1];

typedef struct
{
    char body[MAX_RESPONSE_SIZE];
    size_t length;
    int status;
} http_response_t;

static esp_err_t capture_http_event(esp_http_client_event_t *event)
{
    if (event->event_id == HTTP_EVENT_ON_DATA &&
        event->data != NULL &&
        event->data_len > 0)
    {
        http_response_t *response = event->user_data;
        if (response != NULL)
        {
            size_t available = sizeof(response->body) - response->length - 1;
            size_t copy_len = (size_t)event->data_len;
            if (copy_len > available)
            {
                copy_len = available;
            }
            if (copy_len > 0)
            {
                memcpy(response->body + response->length, event->data, copy_len);
                response->length += copy_len;
                response->body[response->length] = '\0';
            }
        }
    }
    return ESP_OK;
}

static esp_err_t perform_request(
    const char *url,
    esp_http_client_method_t method,
    const char *post_data,
    http_response_t *response)
{
    memset(response, 0, sizeof(*response));

    esp_http_client_config_t config = {
        .url = url,
        .method = method,
        .timeout_ms = 5000,
        .event_handler = capture_http_event,
        .user_data = response,
        .buffer_size = 512,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL)
    {
        ESP_LOGE(TAG, "Khong tao duoc HTTP client");
        return ESP_ERR_NO_MEM;
    }

    if (post_data != NULL)
    {
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, post_data, (int)strlen(post_data));
    }

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK)
    {
        response->status = esp_http_client_get_status_code(client);
    }
    else
    {
        ESP_LOGW(TAG, "HTTP request that bai: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return err;
}

void http_set_student_mssv(const char *mssv)
{
    if (mssv == NULL)
    {
        current_mssv[0] = '\0';
        return;
    }

    snprintf(current_mssv, sizeof(current_mssv), "%s", mssv);
}

esp_err_t http_get_quiz_state(quiz_state_info_t *state)
{
    if (state == NULL)
    {
        return ESP_ERR_INVALID_ARG;
    }

    state->active = false;
    state->accepting_answers = false;
    state->session_id = -1;
    state->question_id = -1;
    state->question_number = -1;

    char url[128];
    if (current_mssv[0] != '\0')
    {
        /* MSSV is entered as digits by this keypad. */
        snprintf(url, sizeof(url), "%s?mssv=%s", STATE_URL, current_mssv);
    }
    else
    {
        snprintf(url, sizeof(url), "%s", STATE_URL);
    }

    http_response_t response;
    esp_err_t err = perform_request(url, HTTP_METHOD_GET, NULL, &response);
    if (err != ESP_OK)
    {
        return err;
    }
    if (response.status != 200)
    {
        ESP_LOGW(TAG, "GET /device/state tra HTTP %d", response.status);
        return ESP_FAIL;
    }

    cJSON *root = cJSON_Parse(response.body);
    if (root == NULL)
    {
        ESP_LOGE(TAG, "JSON /device/state khong hop le");
        return ESP_FAIL;
    }

    cJSON *active = cJSON_GetObjectItemCaseSensitive(root, "active");
    if (cJSON_IsTrue(active))
    {
        cJSON *session_id = cJSON_GetObjectItemCaseSensitive(root, "session_id");
        cJSON *question_id = cJSON_GetObjectItemCaseSensitive(root, "question_id");
        cJSON *question_number = cJSON_GetObjectItemCaseSensitive(root, "question_number");
        cJSON *accepting = cJSON_GetObjectItemCaseSensitive(root, "accepting_answers");

        state->active = true;
        state->session_id = cJSON_IsNumber(session_id) ? session_id->valueint : -1;
        state->question_id = cJSON_IsNumber(question_id) ? question_id->valueint : -1;
        state->question_number = cJSON_IsNumber(question_number) ? question_number->valueint : -1;
        state->accepting_answers = cJSON_IsTrue(accepting);
    }
    else if (!cJSON_IsFalse(active))
    {
        cJSON_Delete(root);
        ESP_LOGE(TAG, "JSON /device/state thieu truong active");
        return ESP_FAIL;
    }

    cJSON_Delete(root);
    return ESP_OK;
}

static http_answer_result_t parse_answer_result(
    const http_response_t *response,
    char *previous_answer,
    size_t previous_answer_size)
{
    if (previous_answer != NULL && previous_answer_size > 0)
    {
        previous_answer[0] = '\0';
    }

    cJSON *root = cJSON_Parse(response->body);
    cJSON *code_item = root ? cJSON_GetObjectItemCaseSensitive(root, "code") : NULL;
    const char *code = cJSON_IsString(code_item) ? code_item->valuestring : "";

    http_answer_result_t result = HTTP_ANSWER_SERVER_ERROR;
    if (response->status == 200)
    {
        result = HTTP_ANSWER_ACCEPTED;
    }
    else if (strcmp(code, "ALREADY_ANSWERED") == 0)
    {
        result = HTTP_ANSWER_ALREADY_ANSWERED;
        cJSON *answer = cJSON_GetObjectItemCaseSensitive(root, "answer");
        if (cJSON_IsString(answer) && previous_answer != NULL && previous_answer_size > 1)
        {
            snprintf(previous_answer, previous_answer_size, "%s", answer->valuestring);
        }
    }
    else if (strcmp(code, "NO_ACTIVE_SESSION") == 0)
    {
        result = HTTP_ANSWER_NO_ACTIVE_SESSION;
    }
    else if (strcmp(code, "ANSWERS_CLOSED") == 0)
    {
        result = HTTP_ANSWER_CLOSED;
    }
    else if (strcmp(code, "QUESTION_CHANGED") == 0)
    {
        result = HTTP_ANSWER_QUESTION_CHANGED;
    }
    else if (strcmp(code, "STATE_NOT_CONFIRMED") == 0)
    {
        result = HTTP_ANSWER_STATE_NOT_CONFIRMED;
    }
    else if (response->status == 403)
    {
        result = HTTP_ANSWER_CLOSED;
    }
    else if (response->status == 409)
    {
        result = HTTP_ANSWER_NO_ACTIVE_SESSION;
    }

    if (root != NULL)
    {
        cJSON_Delete(root);
    }
    return result;
}

http_answer_result_t http_send_answer(
    const char *mssv,
    const char *answer,
    char *previous_answer,
    size_t previous_answer_size)
{
    if (mssv == NULL || answer == NULL)
    {
        return HTTP_ANSWER_SERVER_ERROR;
    }

    char json_data[128];
    snprintf(json_data, sizeof(json_data),
             "{\"mssv\":\"%s\",\"answer\":\"%s\"}",
             mssv, answer);

    http_response_t response;
    esp_err_t err = perform_request(
        ANSWER_URL,
        HTTP_METHOD_POST,
        json_data,
        &response);
    if (err != ESP_OK)
    {
        return HTTP_ANSWER_NETWORK_ERROR;
    }

    ESP_LOGI(TAG, "POST /answer tra HTTP %d", response.status);
    return parse_answer_result(&response, previous_answer, previous_answer_size);
}
