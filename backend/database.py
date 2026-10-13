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