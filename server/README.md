# Classroom Response server

The Flask app now keeps the ESP32 contract unchanged: `POST /answer` with JSON fields `mssv` and `answer`. The server associates that answer with the active session and current question.

## One-time database upgrade

The current schema was inspected in MariaDB `esp32_db`. Before starting this version, take a database backup and run `database/migration_v2.sql` exactly once against that database. The migration creates backup copies of `students`, `questions`, `responses`, and `quiz_state`, adds the class/quiz/session tables, and archives existing questions and answers without deleting the legacy data. It leaves `answers_backup` untouched.

Example:

```sh
mariadb -u DB_ADMIN_USER -p esp32_db < server/database/migration_v2.sql
```

Run that from the project root, or change the path if you are already in `server/`. The configured `esp32app` account currently has data-only privileges, so use an account allowed to create and alter tables for this one-time migration.

## Start

```sh
cd server
. venv/bin/activate
python server.py
```

Database defaults match the existing installation. They can be overridden with `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`. The server listens on port 5000. Set `FLASK_DEBUG=1` only for local development.

## Main routes

- `GET /` — Vietnamese classroom dashboard
- `GET, POST /api/classes` — list and create classes
- `GET /api/classes/<id>` — class details, students, quizzes, and session history
- `POST /api/classes/<id>/quizzes` — create a quiz with ordered questions
- `GET, PUT /api/quizzes/<id>` — view or edit an unused quiz
- `POST /api/quizzes/<id>/sessions` — start a new quiz session
- `GET /api/sessions/<id>` — live question and response statistics
- `POST /api/sessions/<id>/control` — `previous`, `next`, `go`, `open`, `close`, or `end`
- `GET /api/sessions/<id>/results` — session totals and student scores
- `POST /answer` — ESP32 response endpoint, unchanged payload

Compatibility routes `/api/dashboard`, `/quiz-state`, and `/questions` remain registered for older browser integrations; the new dashboard uses the versioned class, quiz, and session APIs.
