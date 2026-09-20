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


