import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request
import mysql.connector

app = Flask(__name__)

# The ESP32 polls with its MSSV. Keep the last observed session/question so a
# delayed POST cannot be assigned to a question opened after the student viewed it.
_DEVICE_STATE_TTL_SECONDS = 10
_device_state_lock = threading.Lock()
_device_state_seen = {}


def remember_device_state(mssv, session_id, question_id):
    if not mssv:
        return
    now = time.monotonic()
    with _device_state_lock:
        expired = [key for key, value in _device_state_seen.items()
                   if now - value[2] > _DEVICE_STATE_TTL_SECONDS]
        for key in expired:
            _device_state_seen.pop(key, None)
        if session_id is None:
            _device_state_seen.pop(mssv, None)
        else:
            _device_state_seen[mssv] = (session_id, question_id, now)


def get_device_observation(mssv):
    now = time.monotonic()
    with _device_state_lock:
        observation = _device_state_seen.get(mssv)
        if observation and now - observation[2] <= _DEVICE_STATE_TTL_SECONDS:
            return observation[:2]
        _device_state_seen.pop(mssv, None)
        return None


def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "esp32app"),
        password=os.getenv("DB_PASSWORD", "esp32password"),
        database=os.getenv("DB_NAME", "esp32_db"),
    )


def db_cursor(dictionary=True):
    conn = get_db()
    return conn, conn.cursor(dictionary=dictionary)


def close_db(conn, cursor):
    try:
        cursor.close()
    finally:
        conn.close()


def error(message, status=400):
    return jsonify({"status": "error", "message": message}), status


def json_body():
    return request.get_json(silent=True) or {}


def class_summary(cursor, class_id):
    cursor.execute("""
        SELECT c.id, c.class_code, c.class_name, c.description, c.created_at,
               (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS student_count,
               (SELECT COUNT(*) FROM quizzes q WHERE q.class_id=c.id) AS quiz_count
        FROM classes c WHERE c.id=%s
    """, (class_id,))
    return cursor.fetchone()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ESP32 protocol remains exactly {"mssv": "...", "answer": "A"}.
@app.route("/answer", methods=["POST"])
def receive_answer():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status":"error","code":"INVALID_JSON","message":"Thiếu dữ liệu JSON."}), 400
    mssv = str(data.get("mssv", "")).strip()
    answer = str(data.get("answer", "")).strip().upper()
    if not mssv:
        return jsonify({"status":"error","code":"MISSING_MSSV","message":"Thiếu MSSV."}), 400
    if len(mssv) > 20:
        return jsonify({"status":"error","code":"INVALID_MSSV","message":"MSSV tối đa 20 ký tự."}), 400
    if answer not in ("A", "B", "C", "D"):
        return jsonify({"status":"error","code":"INVALID_ANSWER","message":"Đáp án phải là A, B, C hoặc D."}), 400

    conn, cursor = db_cursor()
    try:
        # Lock the singleton before the session, matching the order used by the
        # session controls. This serializes answer acceptance with question moves.
        cursor.execute("SELECT active_session_id FROM quiz_state WHERE id=1 FOR UPDATE")
        pointer = cursor.fetchone()
        session_id = pointer["active_session_id"] if pointer else None
        if session_id is None:
            conn.rollback()
            return jsonify({"status":"error","code":"NO_ACTIVE_SESSION","message":"Hiện không có bài kiểm tra đang hoạt động."}), 409

        cursor.execute("""
            SELECT id AS session_id,class_id,quiz_id,current_question_id,
                   accepting_answers,status
            FROM quiz_sessions WHERE id=%s FOR UPDATE
        """, (session_id,))
        state = cursor.fetchone()
        if not state or state["status"] != "active":
            conn.rollback()
            return jsonify({"status":"error","code":"NO_ACTIVE_SESSION","message":"Hiện không có bài kiểm tra đang hoạt động."}), 409

        question_id = state["current_question_id"]
        if question_id is None:
            conn.rollback()
            return jsonify({"status":"error","code":"NO_ACTIVE_SESSION","message":"Phiên chưa chọn câu hỏi hiện tại."}), 409

        observed = get_device_observation(mssv)
        if observed is None:
            conn.rollback()
            return jsonify({"status":"error","code":"STATE_NOT_CONFIRMED","message":"Hãy đồng bộ trạng thái câu hỏi rồi thử lại."}), 409
        observed_session_id, observed_question_id = observed
        if observed_session_id != state["session_id"] or observed_question_id != question_id:
            conn.rollback()
            return jsonify({"status":"error","code":"QUESTION_CHANGED","message":"Câu hỏi đã thay đổi. Đáp án chưa được gửi."}), 409

        cursor.execute("SELECT id FROM questions WHERE id=%s AND quiz_id=%s", (question_id, state["quiz_id"]))
        if cursor.fetchone() is None:
            conn.rollback()
            return jsonify({"status":"error","code":"QUESTION_CHANGED","message":"Câu hỏi hiện tại không thuộc bài kiểm tra."}), 409

        cursor.execute("""
            SELECT answer FROM responses
            WHERE session_id=%s AND student_id=(SELECT id FROM students WHERE mssv=%s)
              AND question_id=%s
            LIMIT 1
        """, (state["session_id"],mssv,question_id))
        previous = cursor.fetchone()
        if previous:
            conn.rollback()
            return jsonify({"status":"error","code":"ALREADY_ANSWERED",
                            "message":"Sinh viên đã trả lời câu này.",
                            "answer":previous["answer"]}), 409

        cursor.execute("INSERT INTO students (mssv) VALUES (%s) ON DUPLICATE KEY UPDATE mssv=VALUES(mssv)", (mssv,))
        cursor.execute("SELECT id FROM students WHERE mssv=%s", (mssv,))
        student_id = cursor.fetchone()["id"]
        cursor.execute("INSERT IGNORE INTO class_students (class_id,student_id) VALUES (%s,%s)", (state["class_id"],student_id))
        cursor.execute("""
            INSERT INTO responses (session_id,student_id,question_id,answer)
            VALUES (%s,%s,%s,%s)
        """, (state["session_id"],student_id,question_id,answer))
        conn.commit()
        return jsonify({"status":"success","mssv":mssv,"question_id":question_id,"answer":answer}), 200
    except mysql.connector.IntegrityError as exc:
        conn.rollback()
        if getattr(exc,"errno",None) == 1062:
            cursor.execute("""
                SELECT answer FROM responses
                WHERE session_id=%s AND student_id=(SELECT id FROM students WHERE mssv=%s)
                  AND question_id=%s LIMIT 1
            """, (session_id,mssv,state["current_question_id"]))
            existing = cursor.fetchone()
            return jsonify({"status":"error","code":"ALREADY_ANSWERED",
                            "message":"Sinh viên đã trả lời câu này.",
                            "answer":existing["answer"] if existing else None}), 409
        app.logger.exception("Lỗi ràng buộc khi lưu đáp án ESP32")
        return jsonify({"status":"error","code":"DATABASE_ERROR","message":"Không thể lưu câu trả lời."}), 500
    except Exception:
        conn.rollback()
        app.logger.exception("Không lưu được câu trả lời ESP32")
        return jsonify({"status":"error","code":"DATABASE_ERROR","message":"Không thể lưu câu trả lời."}), 500
    finally:
        close_db(conn,cursor)

@app.route("/api/overview")
def overview():
    conn, cursor = db_cursor()
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM classes")
        classes = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM quizzes")
        quizzes = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        students = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM responses")
        responses = cursor.fetchone()["total"]
        cursor.execute("""
            SELECT s.id AS session_id, s.current_question_id, 1 AS accepting_answers,
                   c.class_name, qz.title AS quiz_title, q.question_order,
                   (SELECT COUNT(*) FROM responses r WHERE r.session_id=s.id AND r.question_id=s.current_question_id) AS answered,
                   (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=s.class_id) AS student_count
            FROM quiz_state qs JOIN quiz_sessions s ON s.id=qs.active_session_id
            JOIN classes c ON c.id=s.class_id JOIN quizzes qz ON qz.id=s.quiz_id
            LEFT JOIN questions q ON q.id=s.current_question_id
            WHERE qs.id=1 AND s.status='active'
        """)
        active = cursor.fetchone()
        if active:
            cursor.execute("SELECT COUNT(*) AS total FROM questions WHERE quiz_id=(SELECT quiz_id FROM quiz_sessions WHERE id=%s)", (active["session_id"],))
            active["question_count"] = cursor.fetchone()["total"]
        return jsonify({"classes": classes, "quizzes": quizzes, "students": students, "responses": responses, "active_session": active})
    finally:
        close_db(conn, cursor)


@app.route("/api/classes", methods=["GET", "POST"])
def classes_api():
    conn, cursor = db_cursor()
    try:
        if request.method == "GET":
            cursor.execute("""
                SELECT c.id,c.class_code,c.class_name,c.description,c.created_at,
                    (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS student_count,
                    (SELECT COUNT(*) FROM quizzes q WHERE q.class_id=c.id) AS quiz_count
                FROM classes c ORDER BY c.created_at DESC,c.id DESC
            """)
            return jsonify(cursor.fetchall())
        data = json_body()
        code = str(data.get("class_code", "")).strip()
        name = str(data.get("class_name", "")).strip()
        description = str(data.get("description", "")).strip() or None
        if not code or not name:
            return error("Vui lòng nhập mã lớp và tên lớp.")
        cursor.execute("INSERT INTO classes (class_code,class_name,description) VALUES (%s,%s,%s)", (code, name, description))
        conn.commit()
        return jsonify({"id": cursor.lastrowid, "class_code": code, "class_name": name}), 201
    except mysql.connector.IntegrityError:
        conn.rollback()
        return error("Mã lớp đã tồn tại.", 409)
    finally:
        close_db(conn, cursor)


@app.route("/api/classes/<int:class_id>")
def class_detail(class_id):
    conn, cursor = db_cursor()
    try:
        item = class_summary(cursor, class_id)
        if not item:
            return error("Không tìm thấy lớp học.", 404)
        cursor.execute("""
            SELECT q.id,q.title,q.description,q.created_at,COUNT(questions.id) AS question_count
            FROM quizzes q LEFT JOIN questions ON questions.quiz_id=q.id
            WHERE q.class_id=%s GROUP BY q.id ORDER BY q.created_at DESC,q.id DESC
        """, (class_id,))
        item["quizzes"] = cursor.fetchall()
        cursor.execute("""
            SELECT s.id,s.mssv,s.name,cs.joined_at FROM class_students cs
            JOIN students s ON s.id=cs.student_id WHERE cs.class_id=%s ORDER BY s.mssv
        """, (class_id,))
        item["students"] = cursor.fetchall()
        cursor.execute("""
            SELECT s.id,s.status,s.started_at,s.ended_at,q.title AS quiz_title,
                   (SELECT COUNT(*) FROM responses r WHERE r.session_id=s.id) AS response_count
            FROM quiz_sessions s JOIN quizzes q ON q.id=s.quiz_id
            WHERE s.class_id=%s ORDER BY s.started_at DESC,s.id DESC
        """, (class_id,))
        item["history"] = cursor.fetchall()
        return jsonify(item)
    finally:
        close_db(conn, cursor)


@app.route("/api/classes/<int:class_id>/students", methods=["POST"])
def add_class_student(class_id):
    data = json_body()
    mssv = str(data.get("mssv", "")).strip()
    name = str(data.get("name", "")).strip() or None
    if not mssv or len(mssv) > 20:
        return error("Vui lòng nhập MSSV hợp lệ (tối đa 20 ký tự).")
    conn, cursor = db_cursor()
    try:
        if not class_summary(cursor, class_id):
            return error("Không tìm thấy lớp học.", 404)
        cursor.execute("INSERT INTO students (mssv,name) VALUES (%s,%s) ON DUPLICATE KEY UPDATE name=COALESCE(VALUES(name),name)", (mssv, name))
        cursor.execute("SELECT id FROM students WHERE mssv=%s", (mssv,))
        cursor.execute("INSERT IGNORE INTO class_students (class_id,student_id) VALUES (%s,%s)", (class_id,cursor.fetchone()["id"]))
        conn.commit()
        return jsonify({"status": "success"}), 201
    finally:
        close_db(conn, cursor)


def question_payload(q):
    return {"id": q["id"], "question_order": q["question_order"], "question_text": q["question_text"],
            "option_a": q["option_a"], "option_b": q["option_b"], "option_c": q["option_c"],
            "option_d": q["option_d"], "correct_answer": q["correct_answer"]}


def validate_questions(items):
    if not isinstance(items, list) or not items:
        return "Bài kiểm tra cần ít nhất một câu hỏi."
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not str(item.get("question_text", "")).strip():
            return f"Câu {index}: vui lòng nhập nội dung câu hỏi."
        if any(not str(item.get("option_" + letter.lower(), "")).strip() for letter in "ABCD"):
            return f"Câu {index}: vui lòng nhập đủ bốn đáp án."
        if str(item.get("correct_answer", "")).upper() not in "ABCD" or len(str(item.get("correct_answer", ""))) != 1:
            return f"Câu {index}: đáp án đúng phải là A, B, C hoặc D."
    return None


def save_questions(cursor, quiz_id, items):
    for index, item in enumerate(items, 1):
        values = (quiz_id, index, str(item["question_text"]).strip(), *(str(item["option_" + letter.lower()]).strip() for letter in "ABCD"), str(item["correct_answer"]).upper())
        if item.get("id"):
            cursor.execute("""UPDATE questions SET question_order=%s,question_text=%s,option_a=%s,option_b=%s,option_c=%s,option_d=%s,correct_answer=%s WHERE id=%s AND quiz_id=%s""", (index, *values[2:], int(item["id"]), quiz_id))
        else:
            cursor.execute("""INSERT INTO questions (quiz_id,question_order,question_text,option_a,option_b,option_c,option_d,correct_answer) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", values)


@app.route("/api/classes/<int:class_id>/quizzes", methods=["GET", "POST"])
def class_quizzes(class_id):
    conn, cursor = db_cursor()
    try:
        if not class_summary(cursor, class_id):
            return error("Không tìm thấy lớp học.", 404)
        if request.method == "GET":
            cursor.execute("SELECT q.id,q.title,q.description,q.created_at,COUNT(questions.id) AS question_count FROM quizzes q LEFT JOIN questions ON questions.quiz_id=q.id WHERE q.class_id=%s GROUP BY q.id ORDER BY q.created_at DESC", (class_id,))
            return jsonify(cursor.fetchall())
        data = json_body()
        title = str(data.get("title", "")).strip()
        items = data.get("questions", [])
        validation = validate_questions(items)
        if not title:
            return error("Vui lòng nhập tên bài kiểm tra.")
        if validation:
            return error(validation)
        cursor.execute("INSERT INTO quizzes (class_id,title,description) VALUES (%s,%s,%s)", (class_id,title,str(data.get("description", "")).strip() or None))
        quiz_id = cursor.lastrowid
        save_questions(cursor, quiz_id, items)
        conn.commit()
        return jsonify({"id": quiz_id, "title": title}), 201
    except Exception:
        conn.rollback()
        app.logger.exception("Không lưu được bài kiểm tra")
        return error("Không thể lưu bài kiểm tra.", 500)
    finally:
        close_db(conn, cursor)


@app.route("/api/quizzes/<int:quiz_id>", methods=["GET", "PUT"])
def quiz_detail(quiz_id):
    conn, cursor = db_cursor()
    try:
        cursor.execute("SELECT * FROM quizzes WHERE id=%s", (quiz_id,))
        quiz = cursor.fetchone()
        if not quiz:
            return error("Không tìm thấy bài kiểm tra.", 404)
        cursor.execute("SELECT id,question_order,question_text,option_a,option_b,option_c,option_d,correct_answer FROM questions WHERE quiz_id=%s ORDER BY question_order,id", (quiz_id,))
        quiz["questions"] = cursor.fetchall()
        if request.method == "GET":
            return jsonify(quiz)
        data = json_body()
        items = data.get("questions", [])
        validation = validate_questions(items)
        if not str(data.get("title", "")).strip():
            return error("Vui lòng nhập tên bài kiểm tra.")
        if validation:
            return error(validation)
        cursor.execute("SELECT id FROM quiz_sessions WHERE quiz_id=%s LIMIT 1", (quiz_id,))
        if cursor.fetchone():
            return error("Bài đã có phiên sử dụng; không thể sửa để bảo toàn kết quả lịch sử.", 409)
        cursor.execute("UPDATE quizzes SET title=%s,description=%s WHERE id=%s", (str(data["title"]).strip(),str(data.get("description", "")).strip() or None,quiz_id))
        cursor.execute("DELETE FROM questions WHERE quiz_id=%s", (quiz_id,))
        save_questions(cursor, quiz_id, items)
        conn.commit()
        return jsonify({"status": "success"})
    except Exception:
        conn.rollback()
        app.logger.exception("Không cập nhật được bài kiểm tra")
        return error("Không thể cập nhật bài kiểm tra.", 500)
    finally:
        close_db(conn, cursor)


def set_active_session(cursor, session_id):
    cursor.execute("UPDATE quiz_state SET active_session_id=%s,current_question_id=NULL,accepting_answers=0 WHERE id=1", (session_id,))


@app.route("/api/quizzes/<int:quiz_id>/sessions", methods=["POST"])
def start_session(quiz_id):
    conn, cursor = db_cursor()
    try:
        cursor.execute("SELECT id,class_id FROM quizzes WHERE id=%s", (quiz_id,))
        quiz = cursor.fetchone()
        if not quiz:
            return error("Không tìm thấy bài kiểm tra.", 404)
        cursor.execute("SELECT id FROM questions WHERE quiz_id=%s ORDER BY question_order,id LIMIT 1", (quiz_id,))
        first = cursor.fetchone()
        if not first:
            return error("Bài kiểm tra chưa có câu hỏi.", 409)
        cursor.execute("SELECT active_session_id FROM quiz_state WHERE id=1 FOR UPDATE")
        state_row = cursor.fetchone()
        if state_row and state_row["active_session_id"]:
            cursor.execute("SELECT status FROM quiz_sessions WHERE id=%s", (state_row["active_session_id"],))
            active_row = cursor.fetchone()
            if active_row and active_row["status"] == "active":
                return error("Đang có một phiên kiểm tra khác hoạt động. Hãy kết thúc phiên đó trước.", 409)
        cursor.execute("INSERT INTO quiz_sessions (class_id,quiz_id,current_question_id,accepting_answers,status,started_at) VALUES (%s,%s,%s,1,'active',NOW())", (quiz["class_id"],quiz_id,first["id"]))
        session_id = cursor.lastrowid
        cursor.execute("INSERT INTO quiz_state (id,active_session_id,current_question_id,accepting_answers) VALUES (1,%s,%s,1) ON DUPLICATE KEY UPDATE active_session_id=VALUES(active_session_id),current_question_id=VALUES(current_question_id),accepting_answers=1", (session_id,first["id"]))
        conn.commit()
        return jsonify({"id": session_id}), 201
    except Exception:
        conn.rollback()
        app.logger.exception("Không khởi tạo được phiên kiểm tra")
        return error("Không thể bắt đầu bài kiểm tra.", 500)
    finally:
        close_db(conn, cursor)


@app.route("/api/sessions/<int:session_id>")
def session_data(session_id):
    conn, cursor = db_cursor()
    try:
        cursor.execute("""
            SELECT s.id,s.status,s.accepting_answers,s.current_question_id,s.started_at,s.ended_at,
                   c.id AS class_id,c.class_name,c.class_code,qz.id AS quiz_id,qz.title AS quiz_title
            FROM quiz_sessions s JOIN classes c ON c.id=s.class_id JOIN quizzes qz ON qz.id=s.quiz_id
            WHERE s.id=%s
        """, (session_id,))
        session = cursor.fetchone()
        if not session:
            return error("Không tìm thấy phiên kiểm tra.", 404)
        cursor.execute("SELECT id,question_order,question_text,option_a,option_b,option_c,option_d,correct_answer FROM questions WHERE quiz_id=%s ORDER BY question_order,id", (session["quiz_id"],))
        questions = cursor.fetchall()
        current = next((q for q in questions if q["id"] == session["current_question_id"]), None)
        stats = {"total": 0, "correct": 0, "wrong": 0, "correct_percent": 0}
        options = dict.fromkeys("ABCD", 0)
        responses = []
        if current:
            cursor.execute("""
                SELECT COUNT(*) AS total,COALESCE(SUM(r.answer=q.correct_answer),0) AS correct,
                       COALESCE(SUM(r.answer<>q.correct_answer),0) AS wrong
                FROM questions q LEFT JOIN responses r ON r.question_id=q.id AND r.session_id=%s
                WHERE q.id=%s GROUP BY q.id
            """, (session_id,current["id"]))
            row = cursor.fetchone() or stats
            total, correct = int(row["total"] or 0), int(row["correct"] or 0)
            stats = {"total": total,"correct": correct,"wrong": int(row["wrong"] or 0),"correct_percent": round(correct*100/total,1) if total else 0}
            cursor.execute("SELECT answer,COUNT(*) AS total FROM responses WHERE session_id=%s AND question_id=%s GROUP BY answer", (session_id,current["id"]))
            for row in cursor.fetchall():
                options[row["answer"]] = int(row["total"])
            cursor.execute("""
                SELECT s.mssv,r.answer,IF(r.answer=q.correct_answer,'Dung','Sai') AS result,
                       CAST(r.updated_at AS CHAR) AS updated_at
                FROM responses r JOIN students s ON s.id=r.student_id JOIN questions q ON q.id=r.question_id
                WHERE r.session_id=%s AND r.question_id=%s ORDER BY r.updated_at DESC
            """, (session_id,current["id"]))
            responses = cursor.fetchall()
        session["accepting_answers"] = 1 if session["status"] == "active" else 0
        session["started_at"] = str(session["started_at"]) if session["started_at"] else None
        session["ended_at"] = str(session["ended_at"]) if session["ended_at"] else None
        return jsonify({"session":session,"questions":questions,"current_question":current,"stats":stats,"options":options,"responses":responses})
    finally:
        close_db(conn, cursor)


@app.route("/api/sessions/<int:session_id>/control", methods=["POST"])
def control_session(session_id):
    data = json_body()
    action = data.get("action")
    conn, cursor = db_cursor()
    try:
        cursor.execute("SELECT active_session_id FROM quiz_state WHERE id=1 FOR UPDATE")
        active_pointer = cursor.fetchone()
        if not active_pointer or active_pointer["active_session_id"] != session_id:
            return error("Phiên này không còn là phiên đang hoạt động.", 409)
        cursor.execute("SELECT * FROM quiz_sessions WHERE id=%s FOR UPDATE", (session_id,))
        session = cursor.fetchone()
        if not session:
            return error("Không tìm thấy phiên kiểm tra.", 404)
        if session["status"] != "active":
            return error("Phiên kiểm tra đã kết thúc.", 409)
        cursor.execute("SELECT id FROM questions WHERE quiz_id=%s ORDER BY question_order,id", (session["quiz_id"],))
        questions = [r["id"] for r in cursor.fetchall()]
        if action in ("previous", "next", "go"):
            if action == "go":
                try:
                    target = int(data.get("question_id"))
                except (TypeError, ValueError):
                    return error("question_id không hợp lệ.")
                if target not in questions:
                    return error("Câu hỏi không thuộc bài kiểm tra.")
            else:
                index = questions.index(session["current_question_id"]) if session["current_question_id"] in questions else 0
                index = max(0, index-1) if action == "previous" else min(len(questions)-1,index+1)
                target = questions[index]
            cursor.execute("UPDATE quiz_sessions SET current_question_id=%s,accepting_answers=1 WHERE id=%s AND status='active'", (target,session_id))
            cursor.execute("UPDATE quiz_state SET current_question_id=%s,accepting_answers=1 WHERE id=1 AND active_session_id=%s", (target,session_id))
        elif action == "end":
            cursor.execute("UPDATE quiz_sessions SET status='completed',accepting_answers=0,ended_at=NOW() WHERE id=%s AND status='active'", (session_id,))
            cursor.execute("UPDATE quiz_state SET active_session_id=NULL,current_question_id=NULL,accepting_answers=0 WHERE id=1 AND active_session_id=%s", (session_id,))
        else:
            return error("Thao tác phiên không hợp lệ.")
        conn.commit()
        return jsonify({"status":"success"})
    except Exception:
        conn.rollback()
        app.logger.exception("Không điều khiển được phiên")
        return error("Không thể cập nhật phiên kiểm tra.", 500)
    finally:
        close_db(conn, cursor)


@app.route("/api/results")
def all_results():
    conn, cursor = db_cursor()
    try:
        cursor.execute("""
            SELECT s.id,s.status,s.started_at,s.ended_at,c.class_name,q.title AS quiz_title,
                   (SELECT COUNT(DISTINCT student_id) FROM responses WHERE session_id=s.id) AS participant_count,
                   (SELECT COUNT(*) FROM responses WHERE session_id=s.id) AS response_count
            FROM quiz_sessions s JOIN classes c ON c.id=s.class_id JOIN quizzes q ON q.id=s.quiz_id
            WHERE s.status='completed' ORDER BY s.ended_at DESC,s.id DESC
        """)
        rows = cursor.fetchall()
        for row in rows:
            row["started_at"] = str(row["started_at"]) if row["started_at"] else None
            row["ended_at"] = str(row["ended_at"]) if row["ended_at"] else None
        return jsonify(rows)
    finally:
        close_db(conn, cursor)


@app.route("/api/sessions/<int:session_id>/results")
def session_results(session_id):
    conn, cursor = db_cursor()
    try:
        cursor.execute("""
            SELECT s.id,s.status,s.started_at,s.ended_at,c.class_name,q.title AS quiz_title,
                   (SELECT COUNT(*) FROM questions WHERE quiz_id=s.quiz_id) AS question_count,
                   (SELECT COUNT(DISTINCT student_id) FROM responses WHERE session_id=s.id) AS participant_count,
                   (SELECT COUNT(*) FROM responses WHERE session_id=s.id) AS response_count,
                   (SELECT COALESCE(SUM(r.answer=q.correct_answer),0) FROM responses r JOIN questions q ON q.id=r.question_id WHERE r.session_id=s.id) AS correct_count
            FROM quiz_sessions s JOIN classes c ON c.id=s.class_id JOIN quizzes q ON q.id=s.quiz_id WHERE s.id=%s
        """, (session_id,))
        summary = cursor.fetchone()
        if not summary:
            return error("Không tìm thấy phiên kiểm tra.", 404)
        summary["accuracy"] = round(summary["correct_count"]*100/summary["response_count"],1) if summary["response_count"] else 0
        cursor.execute("""
            SELECT st.id AS student_id,st.mssv,st.name,COUNT(r.id) AS answered,
                   COALESCE(SUM(r.answer=q.correct_answer),0) AS correct,
                   COUNT(r.id)-COALESCE(SUM(r.answer=q.correct_answer),0) AS wrong,
                   ROUND(COALESCE(SUM(r.answer=q.correct_answer),0)*100/NULLIF(COUNT(r.id),0),1) AS accuracy
            FROM responses r JOIN students st ON st.id=r.student_id JOIN questions q ON q.id=r.question_id
            WHERE r.session_id=%s GROUP BY st.id,st.mssv,st.name ORDER BY st.mssv
        """, (session_id,))
        students = cursor.fetchall()
        summary["started_at"] = str(summary["started_at"]) if summary["started_at"] else None
        summary["ended_at"] = str(summary["ended_at"]) if summary["ended_at"] else None
        return jsonify({"summary":summary,"students":students})
    finally:
        close_db(conn, cursor)


@app.route("/api/sessions/<int:session_id>/students/<int:student_id>")
def student_results(session_id, student_id):
    conn, cursor = db_cursor()
    try:
        cursor.execute("""
            SELECT q.question_order,q.question_text,q.correct_answer,r.answer,
                   IF(r.answer=q.correct_answer,'Dung','Sai') AS result
            FROM questions q LEFT JOIN responses r ON r.question_id=q.id AND r.session_id=%s AND r.student_id=%s
            WHERE q.quiz_id=(SELECT quiz_id FROM quiz_sessions WHERE id=%s) ORDER BY q.question_order,q.id
        """, (session_id,student_id,session_id))
        return jsonify(cursor.fetchall())
    finally:
        close_db(conn, cursor)


# Compatibility with the original dashboard endpoints.
@app.route("/api/dashboard")
def legacy_dashboard():
    conn, cursor = db_cursor()
    try:
        cursor.execute("SELECT active_session_id FROM quiz_state WHERE id=1")
        row = cursor.fetchone()
        if row and row["active_session_id"]:
            data = session_data(row["active_session_id"]).get_json()
            current = data.get("current_question") or {}
            state = {
                "current_question_id": data["session"]["current_question_id"],
                "accepting_answers": data["session"]["accepting_answers"],
                "question_text": current.get("question_text"),
                "option_a": current.get("option_a"), "option_b": current.get("option_b"),
                "option_c": current.get("option_c"), "option_d": current.get("option_d"),
                "correct_answer": current.get("correct_answer"),
            }
            questions = [{"id": q["id"], "question_text": q["question_text"], "correct_answer": q["correct_answer"]} for q in data["questions"]]
            return jsonify({"state":state,"questions":questions,"stats":data["stats"],"options":data["options"],"responses":data["responses"]})
        cursor.execute("""
            SELECT qs.current_question_id,qs.accepting_answers,q.question_text,
                   q.option_a,q.option_b,q.option_c,q.option_d,q.correct_answer
            FROM quiz_state qs LEFT JOIN questions q ON q.id=qs.current_question_id WHERE qs.id=1
        """)
        state = cursor.fetchone()
        cursor.execute("SELECT id,question_text,correct_answer FROM questions WHERE quiz_id IS NULL ORDER BY id")
        questions = cursor.fetchall()
        return jsonify({"state":state,"questions":questions,"stats":{"total":0,"correct":0,"wrong":0,"correct_percent":0},"options":dict.fromkeys("ABCD",0),"responses":[]})
    finally:
        close_db(conn, cursor)

@app.route("/quiz-state", methods=["POST"])
def legacy_quiz_state():
    data = json_body()
    conn, cursor = db_cursor()
    try:
        cursor.execute("SELECT active_session_id FROM quiz_state WHERE id=1 FOR UPDATE")
        row = cursor.fetchone()
        if row and row["active_session_id"]:
            question_id = data.get("question_id")
            if not question_id:
                return error("question_id không hợp lệ.")
            cursor.execute("SELECT quiz_id,status FROM quiz_sessions WHERE id=%s", (row["active_session_id"],))
            session = cursor.fetchone()
            cursor.execute("SELECT id FROM questions WHERE id=%s AND quiz_id=%s", (question_id,session["quiz_id"] if session else None))
            if not session or session["status"] != "active" or cursor.fetchone() is None:
                return error("Câu hỏi không thuộc phiên đang hoạt động.", 404)
            cursor.execute("UPDATE quiz_sessions SET current_question_id=%s,accepting_answers=1 WHERE id=%s", (question_id,row["active_session_id"]))
            cursor.execute("UPDATE quiz_state SET current_question_id=%s,accepting_answers=1 WHERE id=1", (question_id,))
            conn.commit()
            return jsonify({"status":"success","question_id":question_id,"accepting_answers":True})
        question_id = data.get("question_id")
        if not question_id:
            return error("question_id không hợp lệ.")
        accepting = bool(data.get("accepting_answers", False))
        cursor.execute("UPDATE quiz_state SET current_question_id=%s,accepting_answers=%s WHERE id=1", (question_id,accepting))
        conn.commit()
        return jsonify({"status":"success","question_id":question_id,"accepting_answers":accepting})
    finally:
        close_db(conn, cursor)


@app.route("/questions", methods=["POST"])
def legacy_add_question():
    data = json_body()
    values = [str(data.get(key," ")).strip() for key in ("question_text","option_a","option_b","option_c","option_d")]
    answer = str(data.get("correct_answer","")).upper()
    if not values[0] or any(not v for v in values[1:]) or answer not in "ABCD" or len(answer)!=1:
        return error("Vui lòng nhập câu hỏi, đủ bốn đáp án và đáp án đúng hợp lệ.")
    conn, cursor = db_cursor(dictionary=False)
    try:
        cursor.execute("INSERT INTO questions (question_text,option_a,option_b,option_c,option_d,correct_answer) VALUES (%s,%s,%s,%s,%s,%s)", (*values,answer))
        conn.commit()
        return jsonify({"status":"success","question_id":cursor.lastrowid}),201
    finally:
        close_db(conn,cursor)

@app.route("/device/state", methods=["GET"])
def device_state():
    mssv = request.args.get("mssv", "").strip()
    if len(mssv) > 20:
        return jsonify({"active":False,"code":"INVALID_MSSV"}), 400
    conn, cursor = db_cursor()
    try:
        cursor.execute("""
            SELECT s.id AS session_id,s.status,s.current_question_id AS question_id,
                   s.accepting_answers,q.question_order AS question_number
            FROM quiz_state qs
            LEFT JOIN quiz_sessions s ON s.id=qs.active_session_id
            LEFT JOIN questions q ON q.id=s.current_question_id AND q.quiz_id=s.quiz_id
            WHERE qs.id=1
        """)
        row=cursor.fetchone()
        active=bool(row and row["session_id"] is not None and row["status"]=="active")
        if not active:
            remember_device_state(mssv,None,None)
            return jsonify({"active":False}),200
        remember_device_state(mssv,row["session_id"],row["question_id"])
        return jsonify({"active":True,"session_id":row["session_id"],
                        "question_id":row["question_id"],
                        "question_number":row["question_number"],
                        "accepting_answers":True}),200
    finally:
        close_db(conn,cursor)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1")
