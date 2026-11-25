# ShareSync database schema
CREATE DATABASE IF NOT EXISTS sharesync;
USE sharesync;

--STUDENTS TABLE FOR STUDENT DATA, CORE TABLE 
CREATE TABLE IF NOT EXISTS students (
    student_id INT PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(260) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'STUDENT',
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT INTO students
(
    student_id,
    student_name,
    email,
    password_hash,
    role,
    verification_status
)
VALUES
(
       999,
    'ShareSync Admin',
    'admin@sharesync.com',
    'scrypt:32768:8:1$sAaMO4qEedB3eZ0C$2787198bacbceababec8b648091d85cfe2cfc6d7dfd20a4a34bc1a88bbc08e9ffab99ea61f67baa7aa64639eee0eb7a843678c57d12469276a8e7e4814e03fa0',
    'ADMIN',
    'VERIFIED'
)
ON DUPLICATE KEY UPDATE
    student_name = VALUES(student_name),
    email = VALUES(email),
    role = VALUES(role),
    verification_status = VALUES(verification_status);

CREATE TABLE IF NOT EXISTS borrow_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    resource_name VARCHAR(150) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    request_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_request_student FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS resource_offers (
    offer_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    student_id INT NOT NULL,
    resource_name VARCHAR(150) NOT NULL,
    description TEXT,
    offer_status VARCHAR(20) NOT NULL DEFAULT 'Available',
    offered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    share_item_key VARCHAR(300) NULL,
    CONSTRAINT fk_offer_request FOREIGN KEY (request_id)
        REFERENCES borrow_requests(request_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT fk_offer_student FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;

--Transaction for when the requester confirms offer
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    offer_id INT NOT NULL,
    borrower_id INT NOT NULL,
    lender_id INT NOT NULL,
    borrowed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_date DATETIME NOT NULL,
    returned_at DATETIME NULL,
    transaction_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT fk_transaction_request
        FOREIGN KEY (request_id)
        REFERENCES borrow_requests(request_id),
    CONSTRAINT fk_transaction_offer
        FOREIGN KEY (offer_id)
        REFERENCES resource_offers(offer_id),
    CONSTRAINT fk_transaction_borrower
        FOREIGN KEY (borrower_id)
        REFERENCES students(student_id),
    CONSTRAINT fk_transaction_lender
        FOREIGN KEY (lender_id)
        REFERENCES students(student_id)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS fines (
    fine_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    reason VARCHAR(255),
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at DATETIME NULL,
    fine_status VARCHAR(20) NOT NULL DEFAULT 'UNPAID',
    CONSTRAINT fk_fine_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(transaction_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    reviewer_id INT NOT NULL,
    reviewee_id INT NOT NULL,
    rating INT NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_rating CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT fk_review_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(transaction_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_review_reviewer
        FOREIGN KEY (reviewer_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_review_reviewee
        FOREIGN KEY (reviewee_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS student_resource_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    accepted_by INT NULL,
    borrow_request_id INT NULL,
    resource_name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    due_date DATE NULL,
    request_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_student_resource_requester FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_student_request_acceptor FOREIGN KEY (accepted_by)
        REFERENCES students(student_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_student_request_legacy FOREIGN KEY (borrow_request_id)
        REFERENCES borrow_requests(request_id)
        ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS student_share_item_locks (
    sharer_id INT NOT NULL,
    item_key VARCHAR(300) NOT NULL,
    PRIMARY KEY (sharer_id, item_key),
    CONSTRAINT fk_share_item_lock_sharer FOREIGN KEY (sharer_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

--os resources table for showing resources in the os 
CREATE TABLE IF NOT EXISTS os_resources (
    resource_id INT AUTO_INCREMENT PRIMARY KEY,
    resource_name VARCHAR(150) NOT NULL,
    owner_student_id INT NULL,
    sharer_id INT NULL,
    share_item_key VARCHAR(300) NULL,
    active_transaction_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_os_resource_owner FOREIGN KEY (owner_student_id)
        REFERENCES students(student_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_os_resource_sharer FOREIGN KEY (sharer_id)
        REFERENCES students(student_id)
        ON DELETE SET NULL,
    UNIQUE KEY uq_os_resource_source (sharer_id, share_item_key)
) ENGINE=InnoDB;

--shows which resources are involed waiting for other resources 
CREATE TABLE IF NOT EXISTS os_resource_waits (
    wait_id INT AUTO_INCREMENT PRIMARY KEY,
    waiting_student_id INT NOT NULL,
    resource_id INT NOT NULL,
    request_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_os_wait_student_resource (waiting_student_id, resource_id),
    CONSTRAINT fk_os_wait_student FOREIGN KEY (waiting_student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_os_wait_resource FOREIGN KEY (resource_id)
        REFERENCES os_resources(resource_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS os_recovery_releases (
    sharer_id INT NOT NULL,
    share_item_key VARCHAR(300) NOT NULL,
    released_transaction_id INT NOT NULL,
    recovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sharer_id, share_item_key)
) ENGINE=InnoDB;
--table created to show previous deadlocks that were recovered or detected 
CREATE TABLE IF NOT EXISTS os_deadlock_history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(20) NOT NULL,
    cycle_text VARCHAR(255) NULL,
    policy VARCHAR(30) NULL,
    victim_student_id INT NULL,
    victim_name VARCHAR(100) NULL,
    cancelled_request_ids VARCHAR(255) NULL,
    item_name VARCHAR(150) NULL,
    reallocated_to_name VARCHAR(100) NULL,
    new_transaction_id INT NULL,
    triggered_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

--TABLE WILL CALCULATE THE FINE FOR LATE RETURN OF RESOURCE
CREATE TABLE IF NOT EXISTS transaction_fees (
    transaction_id INT PRIMARY KEY,
    late_days INT NOT NULL,
    fee_amount INT NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

) ENGINE=InnoDB;

--for the reviewing of transactions
CREATE TABLE IF NOT EXISTS transaction_reviews(
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    reviewer_id INT NOT NULL,
    reviewee_id INT NOT NULL,
    rating TINYINT NOT NULL,
    comment VARCHAR(500) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_review_once (transaction_id, reviewer_id)
) ENGINE=InnoDB;



--PROCEDURE FOR FOLLOWING REGISTRATION OF STUDENTS
--WILL CHANGE STATUS OF PENDING STUDENTS
DELIMITER //
DROP PROCEDURE IF EXISTS review_student_registration//
CREATE PROCEDURE review_student_registration(
    IN stu_id INT,
    IN t_action VARCHAR(10),
    OUT updated_rows INT
)
BEGIN
    DECLARE new_status VARCHAR(30);

    IF t_action IS NULL OR LOWER(t_action) NOT IN ('approve', 'reject') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Action must be approve or reject';
    END IF;

    SET new_status = CASE LOWER(t_action)
        WHEN 'approve' THEN 'VERIFIED'
        WHEN 'reject' THEN 'REJECTED'
    END;

    UPDATE students
    SET verification_status = new_status
    WHERE student_id = stu_id
      AND role = 'STUDENT'
      AND verification_status = 'PENDING';

    SET updated_rows = ROW_COUNT();
END//
DELIMITER ;



--VIEWS WE HAVE IMPLEMENTED TO SHOW INFORMATION IN A CLEAN FORMAT 
--AND FASTER FOR DEMONSTRATING 

--view for viewing pending students 

CREATE OR REPLACE VIEW view_pending_students AS
SELECT student_id, student_name, email, created_at
FROM students
WHERE role = 'STUDENT'
  AND verification_status = 'PENDING';

  --View for viewing accepted students 
CREATE OR REPLACE VIEW view_student_requests AS
SELECT q.request_id,
       q.resource_name,
       q.category,
       q.description,
       q.request_status,
       q.due_date,
       q.created_at,
       requester.student_id AS requester_id,
       requester.student_name AS requester_name,
       acceptor.student_id AS accepted_by_id,
       acceptor.student_name AS accepted_by_name
FROM student_resource_requests q
JOIN students requester
  ON requester.student_id = q.student_id
LEFT JOIN students acceptor
  ON acceptor.student_id = q.accepted_by;
  
  select * from view_student_requests;
  


--VIEW FOR SHOWING ACTIVE TRANSACTIONS FOR DASHBOARD 

CREATE OR REPLACE VIEW view_active_transactions AS
SELECT t.transaction_id,
       t.request_id,
       t.offer_id,
       borrower.student_id AS borrower_id,
       borrower.student_name AS borrower_name,
       lender.student_id AS lender_id,
       lender.student_name AS lender_name,
       o.resource_name,
       t.borrowed_at,
       t.due_date,
       t.transaction_status
FROM transactions t
JOIN students borrower
  ON borrower.student_id = t.borrower_id
JOIN students lender
  ON lender.student_id = t.lender_id
JOIN resource_offers o
  ON o.offer_id = t.offer_id
WHERE t.transaction_status = 'ACTIVE';
select * from view_active_transactions;

