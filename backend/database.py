from threading import Lock
import os
import mysql.connector

student_request_lock = Lock()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )
    
def get_db_cursor(connection):
    return connection.cursor(dictionary=True)

def ensure_student_dashboard_tables(connection):
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_share_item_locks (
            sharer_id INT NOT NULL,
            item_key VARCHAR(300) NOT NULL,
            PRIMARY KEY (sharer_id, item_key),
            CONSTRAINT fk_share_item_lock_sharer FOREIGN KEY (sharer_id)
            REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    ''')
    
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS borrow_requests (
                request_id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                resource_name VARCHAR(150) NOT NULL,
                description TEXT,
                category VARCHAR(50),
                request_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_request_student
                    FOREIGN KEY (student_id)
                    REFERENCES students(student_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
    
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS resource_offers (
                offer_id INT AUTO_INCREMENT PRIMARY KEY,
                request_id INT NOT NULL,
                student_id INT NOT NULL,
                resource_name VARCHAR(150) NOT NULL,
                description TEXT,
                offer_status VARCHAR(20) NOT NULL DEFAULT 'Available',
                offered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_offer_request
                    FOREIGN KEY (request_id)
                    REFERENCES borrow_requests(request_id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_offer_student
                    FOREIGN KEY (student_id)
                    REFERENCES students(student_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
    
    
    cursor.execute("""
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
            ) ENGINE=InnoDB
        """)
    
    
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_resources (
                resource_id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                resource_name VARCHAR(150) NOT NULL,
                description TEXT NOT NULL,
                category VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_student_resource_owner
                    FOREIGN KEY (student_id)
                    REFERENCES students(student_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
    

    
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_resource_requests (
                request_id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                resource_id INT NULL,
                accepted_by INT NULL,
                resource_name VARCHAR(150) NOT NULL,
                description TEXT NOT NULL,
                category VARCHAR(50) NOT NULL,
                request_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_student_resource_requester
                    FOREIGN KEY (student_id)
                    REFERENCES students(student_id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_student_resource_requested
                    FOREIGN KEY (resource_id)
                    REFERENCES student_resources(resource_id)
                    ON DELETE SET NULL,
                CONSTRAINT fk_student_request_acceptor
                    FOREIGN KEY (accepted_by)
                    REFERENCES students(student_id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB
        """) 
    
    # Add columns needed by older versions of the table.
    cursor.execute("""
            SHOW COLUMNS FROM student_resource_requests
            LIKE 'accepted_by'
        """)
    if cursor.fetchone() is None:
            cursor.execute("""
                ALTER TABLE student_resource_requests
                ADD COLUMN accepted_by INT NULL AFTER student_id,
                ADD CONSTRAINT fk_student_request_acceptor
                    FOREIGN KEY (accepted_by)
                    REFERENCES students(student_id)
                    ON DELETE SET NULL
            """)