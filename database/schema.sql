#making the database#
create database sharesync;

use sharesync;

 create table students(
    -> student_id int primary key,
    -> student_name varchar(100) not null,
    -> email varchar(100) not null unique,
    -> password_hash varchar(255) not null,
    -> role varchar(20) not null default 'STUDENT',
    -> verification_status varchar(20) not null default 'PENDING',
    -> created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -> )ENGINE =InnoDB;

create table borrow_requests(
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    -> student_id INT NOT NULL,
    -> resource_name varchar(150) NOT NULL,
    -> description TEXT,
    -> category VARCHAR(50),
    -> request_status varchar(20) NOT NULL DEFAULT 'OPEN',
    -> created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ->
    -> CONSTRAINT fk_request_student FOREIGN KEY (student_id) REFERENCES students(student_id)
    -> ON DELETE CASCADE
    -> ON UPDATE cascade
    -> ) ENGINE =InnoDB;

    mysql> create table resource_offers(
    -> offer_id int primary key,
    -> request_id int not null,
    -> student_id int not null,
    -> resource_name varchar(150) not null,
    -> description TEXT,
    -> offer_status varchar(20) not null default 'Available',
    -> offered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -> Constraint fk_offer_request foreign key(request_id)
    -> references borrow_requests(request_id)
    -> on delete cascade
    -> on update cascade,
    -> Constraint fk_offer_student FOREIGN KEY (student_id) REFERENCES students(student_id)
    -> on delete cascade
    -> on update cascade
    -> )ENGINE =InnoDB;
#Transactions table to s
    mysql> CREATE TABLE transactions (
    ->     transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    ->     request_id INT NOT NULL,
    ->     offer_id INT NOT NULL,
    ->     borrower_id INT NOT NULL,
    ->     lender_id INT NOT NULL,
    ->
    ->     borrowed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ->     due_date DATETIME NOT NULL,
    ->     returned_at DATETIME NULL,
    ->
    ->     transaction_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    ->
    ->     CONSTRAINT fk_transaction_request
    ->         FOREIGN KEY (request_id)
    ->         REFERENCES borrow_requests(request_id),
    ->
    ->     CONSTRAINT fk_transaction_offer
    ->         FOREIGN KEY (offer_id)
    ->         REFERENCES resource_offers(offer_id),
    ->
    ->     CONSTRAINT fk_transaction_borrower
    ->         FOREIGN KEY (borrower_id)
    ->         REFERENCES students(student_id),
    ->
    ->     CONSTRAINT fk_transaction_lender
    ->         FOREIGN KEY (lender_id)
    ->         REFERENCES students(student_id)
    -> ) ENGINE=InnoDB;


mysql> create table fines (
    -> fine_id INT AUTO_INCREMENT PRIMARY KEY,
    -> transaction_id int not null,
    -> amount decimal(10,2) not null,
    -> reason varchar(255),
    -> issued_at TIMESTAMP default current_timestamp,
    -> paid_at datetime null,
    -> fine_status varchar(20) not null default 'UNPAID',
    -> Constraint fk_fine_transaction
    -> foreign key (transaction_id) references transactions(transaction_id)
    -> on delete cascade
    -> on update cascade
    -> )ENGINE=InnoDB;



mysql> CREATE TABLE reviews (
    ->     review_id INT AUTO_INCREMENT PRIMARY KEY,
    ->     transaction_id INT NOT NULL,
    ->     reviewer_id INT NOT NULL,
    ->     reviewee_id INT NOT NULL,
    ->     rating INT NOT NULL,
    ->     comment TEXT,
    ->     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ->
    ->     CONSTRAINT chk_rating
    ->         CHECK (rating BETWEEN 1 AND 5),
    ->
    ->     CONSTRAINT fk_review_transaction
    ->         FOREIGN KEY (transaction_id)
    ->         REFERENCES transactions(transaction_id)
    ->         ON DELETE CASCADE,
    ->
    ->     CONSTRAINT fk_review_reviewer
    ->         FOREIGN KEY (reviewer_id)
    ->         REFERENCES students(student_id)
    ->         ON DELETE CASCADE,
    ->
    ->     CONSTRAINT fk_review_reviewee
    ->         FOREIGN KEY (reviewee_id)
    ->         REFERENCES students(student_id)
    ->         ON DELETE CASCADE
    -> ) ENGINE=InnoDB;
