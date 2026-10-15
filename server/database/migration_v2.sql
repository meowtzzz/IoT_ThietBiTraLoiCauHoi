-- Classroom Response v2 migration for the confirmed esp32_db legacy schema.
-- Run exactly once after taking a database backup. This migration does not drop
-- or truncate legacy tables or rows; it keeps answers_backup untouched.

CREATE TABLE students_v1_backup LIKE students;
INSERT INTO students_v1_backup SELECT * FROM students;
CREATE TABLE questions_v1_backup LIKE questions;
INSERT INTO questions_v1_backup SELECT * FROM questions;
CREATE TABLE responses_v1_backup LIKE responses;
INSERT INTO responses_v1_backup SELECT * FROM responses;
CREATE TABLE quiz_state_v1_backup LIKE quiz_state;
INSERT INTO quiz_state_v1_backup SELECT * FROM quiz_state;

CREATE TABLE classes (
    id INT NOT NULL AUTO_INCREMENT,
    class_code VARCHAR(40) NOT NULL,
    class_name VARCHAR(160) NOT NULL,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_classes_code (class_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE quizzes (
    id INT NOT NULL AUTO_INCREMENT,
    class_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_quizzes_class (class_id),
    CONSTRAINT fk_quizzes_class FOREIGN KEY (class_id) REFERENCES classes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE class_students (
    class_id INT NOT NULL,
    student_id INT NOT NULL,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (class_id, student_id),
    KEY ix_class_students_student (student_id),
    CONSTRAINT fk_class_students_class FOREIGN KEY (class_id) REFERENCES classes(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_class_students_student FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE quiz_sessions (
    id INT NOT NULL AUTO_INCREMENT,
    class_id INT NOT NULL,
    quiz_id INT NOT NULL,
    current_question_id INT NULL,
    accepting_answers TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM('active','completed') NOT NULL DEFAULT 'active',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_sessions_class_started (class_id, started_at),
    KEY ix_sessions_quiz (quiz_id),
    KEY ix_sessions_status (status),
    CONSTRAINT fk_sessions_class FOREIGN KEY (class_id) REFERENCES classes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_sessions_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

ALTER TABLE questions
    ADD COLUMN quiz_id INT NULL AFTER id,
    ADD COLUMN question_order INT NOT NULL DEFAULT 1 AFTER quiz_id,
    ADD KEY ix_questions_quiz_order (quiz_id, question_order),
    ADD CONSTRAINT fk_questions_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE quiz_sessions
    ADD CONSTRAINT fk_sessions_current_question FOREIGN KEY (current_question_id) REFERENCES questions(id)
        ON DELETE SET NULL ON UPDATE CASCADE;

-- Keep an index available to the existing student_id foreign key before replacing
-- the legacy UNIQUE(student_id, question_id) constraint.
ALTER TABLE responses ADD KEY ix_responses_student (student_id);
ALTER TABLE responses
    DROP INDEX student_id,
    ADD COLUMN session_id INT NULL AFTER id,
    ADD UNIQUE KEY uq_response_session_student_question (session_id, student_id, question_id),
    ADD KEY ix_responses_session_question (session_id, question_id),
    ADD CONSTRAINT fk_responses_session FOREIGN KEY (session_id) REFERENCES quiz_sessions(id)
        ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE quiz_state
    ADD COLUMN active_session_id INT NULL AFTER id,
    ADD KEY ix_quiz_state_active_session (active_session_id),
    ADD CONSTRAINT fk_quiz_state_active_session FOREIGN KEY (active_session_id) REFERENCES quiz_sessions(id)
        ON DELETE SET NULL ON UPDATE CASCADE;

-- Keep legacy questions and answers usable under a dedicated archive class/quiz.
INSERT INTO classes (class_code, class_name, description)
VALUES ('LEGACY', 'Dữ liệu cũ', 'Câu hỏi và lượt trả lời được giữ lại từ hệ thống trước đây.');
INSERT INTO quizzes (class_id, title, description)
SELECT id, 'Bài kiểm tra lưu trữ', 'Các câu hỏi đã có trước khi nâng cấp.'
FROM classes WHERE class_code='LEGACY';
UPDATE questions
SET quiz_id=(SELECT id FROM quizzes WHERE class_id=(SELECT id FROM classes WHERE class_code='LEGACY') LIMIT 1),
    question_order=id
WHERE quiz_id IS NULL;
INSERT IGNORE INTO class_students (class_id, student_id)
SELECT c.id, s.id FROM classes c CROSS JOIN students s WHERE c.class_code='LEGACY';

-- Group the old global responses in a completed historical session so they remain
-- visible in results, while all future responses are scoped to new sessions.
INSERT INTO quiz_sessions (class_id, quiz_id, current_question_id, accepting_answers, status, started_at, ended_at)
SELECT c.id, qz.id, NULL, 0, 'completed',
       COALESCE(MIN(r.created_at), CURRENT_TIMESTAMP),
       COALESCE(MAX(r.updated_at), CURRENT_TIMESTAMP)
FROM classes c
JOIN quizzes qz ON qz.class_id=c.id
JOIN questions q ON q.quiz_id=qz.id
JOIN responses r ON r.question_id=q.id
WHERE c.class_code='LEGACY'
GROUP BY c.id, qz.id;
UPDATE responses r
JOIN questions q ON q.id=r.question_id
JOIN quiz_sessions s ON s.quiz_id=q.quiz_id AND s.status='completed'
JOIN quizzes qz ON qz.id=q.quiz_id
JOIN classes c ON c.id=qz.class_id AND c.class_code='LEGACY'
SET r.session_id=s.id
WHERE r.session_id IS NULL;

INSERT IGNORE INTO quiz_state (id, current_question_id, accepting_answers) VALUES (1, NULL, 0);
UPDATE quiz_state SET active_session_id=NULL, accepting_answers=0 WHERE id=1;
