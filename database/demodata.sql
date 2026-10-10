#only inserted demo data is placed here .


use sharesync;
INSERT INTO students
(student_id, student_name, email, password_hash, role, verification_status)
VALUES
(101, 'Vaneesh Jain', 'vaneesh@gmail.com', 'demo_hash_101', 'STUDENT', 'VERIFIED'),
(102, 'Aryan Dingoriya', 'aryan@gmail.com', 'demo_hash_102', 'STUDENT', 'VERIFIED'),
(103, 'Tawananyasha Chikwanda', 'tawana@gmail.com', 'demo_hash_103', 'STUDENT', 'VERIFIED'),
(104, 'Aarav Chauhan', 'aarav@gmail.com', 'demo_hash_104', 'STUDENT', 'VERIFIED'),
(105, 'Rahul Sharma', 'rahul@gmail.com', 'demo_hash_105', 'STUDENT', 'PENDING');
select * from students;



-- ShareSync MySQL data inspection queries
-- Select this database in MySQL Workbench before running these queries.
USE sharesync;

-- Tables used by the student dashboard and request-to-transaction flow:
--   students                  Accounts, login roles, and verification status
--   student_resource_requests Shared-board requests and their status
--   borrow_requests           Legacy request row linked to a created offer/transaction
--   resource_offers           Share offer created when another student accepts
--   transactions              Active lending transaction and expected return date
--   student_share_item_locks   Serializes confirmations for the same sharer/item
--
-- The backend does not store login passwords in readable form. Do not select
-- password_hash when inspecting student rows.

-- List all tables in the selected database.
SHOW TABLES;

-- View students without exposing password hashes.
SELECT student_id, student_name, email, role, verification_status, created_at
FROM students
ORDER BY created_at DESC;

-- View resources and the student who shared each one.
SELECT r.resource_id, r.resource_name, r.description, r.category,
       r.created_at, s.student_id, s.student_name
FROM student_resources AS r
JOIN students AS s ON s.student_id = r.student_id
ORDER BY r.created_at DESC;

-- View borrow requests, the requesting student, and (when linked) the
-- owner of the requested resource. Resource names are also kept on the
-- request row, so this still shows requests without a linked resource.

SELECT q.request_id, q.resource_name, q.description, q.category,
       q.request_status, q.due_date, q.created_at,
       borrower.student_id AS borrower_id,
       borrower.student_name AS borrower_name,
       owner.student_id AS resource_owner_id,
       owner.student_name AS resource_owner_name
FROM student_resource_requests AS q
JOIN students AS borrower ON borrower.student_id = q.student_id
LEFT JOIN student_resources AS r ON r.resource_id = q.resource_id
LEFT JOIN students AS owner ON owner.student_id = r.student_id
ORDER BY q.created_at DESC;

-- View requests for resources owned by one student.
-- Replace 101 with the resource owner's student_id.

SELECT q.request_id, q.resource_name, q.description, q.category,
       q.request_status, q.created_at, requester.student_id,
       requester.student_name AS requester_name
FROM student_resource_requests AS q
JOIN student_resources AS r ON r.resource_id = q.resource_id
JOIN students AS requester ON requester.student_id = q.student_id
WHERE r.student_id = 101
ORDER BY q.created_at DESC;

-- View the share offer and active transaction created by acceptance.

SELECT q.request_id AS board_request_id,
       br.request_id AS borrow_request_id,
       offer.offer_id, t.transaction_id,
       q.resource_name, borrower.student_name AS borrower_name,
       lender.student_name AS lender_name,
       t.transaction_status, t.borrowed_at, t.due_date
FROM student_resource_requests AS q
JOIN borrow_requests AS br ON br.request_id = q.borrow_request_id
JOIN resource_offers AS offer ON offer.request_id = br.request_id
JOIN transactions AS t ON t.offer_id = offer.offer_id
JOIN students AS borrower ON borrower.student_id = t.borrower_id
JOIN students AS lender ON lender.student_id = t.lender_id
ORDER BY t.borrowed_at DESC;

-- Check for duplicate active transactions per sharer and normalized item key.
-- This query should return no rows.
SELECT o.student_id AS sharer_id, o.share_item_key,
       COUNT(*) AS active_transactions
FROM transactions AS t
JOIN resource_offers AS o ON o.offer_id = t.offer_id
WHERE t.transaction_status = 'ACTIVE'
GROUP BY o.student_id, o.share_item_key
HAVING COUNT(*) > 1;

-- Quick raw views of the legacy request/offer/transaction records.
SELECT * FROM borrow_requests ORDER BY created_at DESC;
SELECT * FROM resource_offers ORDER BY offered_at DESC;
SELECT * FROM transactions ORDER BY borrowed_at DESC;

-- These tables are present in database/schema.sql but outside the current
-- student request-to-transaction flow.
SELECT * FROM fines ORDER BY issued_at DESC;
SELECT * FROM reviews ORDER BY created_at DESC;
