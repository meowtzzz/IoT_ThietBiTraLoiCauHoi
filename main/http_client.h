#ifndef HTTP_CLIENT_H
#define HTTP_CLIENT_H

#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

typedef struct
{
    bool active;
    bool accepting_answers;
    int session_id;
    int question_id;
    int question_number;
} quiz_state_info_t;

typedef enum
{
    HTTP_ANSWER_ACCEPTED = 0,
    HTTP_ANSWER_ALREADY_ANSWERED,
    HTTP_ANSWER_NO_ACTIVE_SESSION,
    HTTP_ANSWER_CLOSED,
    HTTP_ANSWER_QUESTION_CHANGED,
    HTTP_ANSWER_STATE_NOT_CONFIRMED,
    HTTP_ANSWER_NETWORK_ERROR,
    HTTP_ANSWER_SERVER_ERROR
} http_answer_result_t;

/* Set the student used to associate /device/state observations with /answer. */
void http_set_student_mssv(const char *mssv);

esp_err_t http_get_quiz_state(quiz_state_info_t *state);

http_answer_result_t http_send_answer(
    const char *mssv,
    const char *answer,
    char *previous_answer,
    size_t previous_answer_size
);

#endif
