from flask import Flask, render_template, request, jsonify, session, redirect

from datetime import date, datetime
from threading import Lock



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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS borrow_requests (
            request_id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            resource_name VARCHAR(150) NOT NULL,
            description TEXT,
            category VARCHAR(50),
            request_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_request_student FOREIGN KEY (student_id)
            REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resource_offers (
            offer_id INT AUTO_INCREMENT PRIMARY KEY,
            request_id INT NOT NULL,
            student_id INT NOT NULL,
            resource_name VARCHAR(150) NOT NULL,
            description TEXT,
            offer_status VARCHAR(20) NOT NULL DEFAULT 'Available',
            offered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_offer_request FOREIGN KEY (request_id)
            REFERENCES borrow_requests(request_id) ON DELETE CASCADE,
            CONSTRAINT fk_offer_student FOREIGN KEY (student_id)
            REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    ''')
    cursor.execute('''
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
            CONSTRAINT fk_transaction_request FOREIGN KEY (request_id)
            REFERENCES borrow_requests(request_id),
            CONSTRAINT fk_transaction_offer FOREIGN KEY (offer_id)
            REFERENCES resource_offers(offer_id),
            CONSTRAINT fk_transaction_borrower FOREIGN KEY (borrower_id)
            REFERENCES students(student_id),
            CONSTRAINT fk_transaction_lender FOREIGN KEY (lender_id)
            REFERENCES students(student_id)
        ) ENGINE=InnoDB
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_resources (
            resource_id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            resource_name VARCHAR(150) NOT NULL,
            description TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_student_resource_owner FOREIGN KEY (student_id)
            REFERENCES students(student_id) ON DELETE CASCADE
        )   ENGINE=InnoDB
    ''')
    cursor.execute('''
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
            CONSTRAINT fk_student_resource_requester FOREIGN KEY (student_id)
            REFERENCES students(student_id) ON DELETE CASCADE,
            CONSTRAINT fk_student_resource_requested FOREIGN KEY (resource_id)
            REFERENCES student_resources(resource_id) ON DELETE SET NULL,
            CONSTRAINT fk_student_request_acceptor FOREIGN KEY (accepted_by)
            REFERENCES students(student_id) ON DELETE SET NULL
        ) ENGINE=InnoDB
    ''')
    cursor.execute("SHOW COLUMNS FROM student_resource_requests LIKE 'accepted_by'")
    if cursor.fetchone() is None:
        cursor.execute('''
            ALTER TABLE student_resource_requests
            ADD COLUMN accepted_by INT NULL AFTER student_id,
            ADD CONSTRAINT fk_student_request_acceptor FOREIGN KEY (accepted_by)
            REFERENCES students(student_id) ON DELETE SET NULL
        ''')
    cursor.execute("SHOW COLUMNS FROM student_resource_requests LIKE 'borrow_request_id'")
    if cursor.fetchone() is None:
        cursor.execute('''
            ALTER TABLE student_resource_requests
            ADD COLUMN borrow_request_id INT NULL,
            ADD CONSTRAINT fk_student_request_legacy
            FOREIGN KEY (borrow_request_id)
            REFERENCES borrow_requests(request_id) ON DELETE SET NULL
        ''')
    cursor.execute("SHOW COLUMNS FROM student_resource_requests LIKE 'due_date'")
    if cursor.fetchone() is None:
        cursor.execute('''
            ALTER TABLE student_resource_requests
            ADD COLUMN due_date DATE NULL
        ''')
    cursor.execute("SHOW COLUMNS FROM resource_offers LIKE 'share_item_key'")
    if cursor.fetchone() is None:
        cursor.execute('''
            ALTER TABLE resource_offers
            ADD COLUMN share_item_key VARCHAR(300) NULL
        ''')
    connection.commit()
    cursor.close()


def is_student_session():
    return 'student_id' in session and session.get('student_role') == 'STUDENT'


def normalize_share_item_name(resource_name):
    return ' '.join(resource_name.split()).casefold()


@app.route('/api/student-dashboard', methods=['GET'])
def student_dashboard_data():
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        cursor = get_db_cursor(connection)
        cursor.execute('''
            SELECT q.request_id, q.student_id, q.resource_name, q.description,
                   q.category, q.due_date, q.created_at,
                   s.student_name AS requester_name
            FROM student_resource_requests q
            JOIN students s ON s.student_id = q.student_id
            WHERE q.request_status = 'OPEN'
            ORDER BY q.created_at DESC
        ''')
        board_requests = [
            {
                **dict(row),
                'due_date': str(row['due_date']) if row['due_date'] else None,
                'created_at': str(row['created_at'])
            }
            for row in cursor.fetchall()
        ]

        cursor.execute('''
            SELECT q.request_id, q.resource_name, q.description, q.category,
                   q.due_date, q.request_status, q.created_at,
                   accepter.student_name AS accepted_by_name,
                   CASE WHEN t.transaction_id IS NOT NULL
                        THEN accepter.email END AS accepted_by_email,
                   offer.offer_id,
                   offer.offer_status,
                   t.transaction_id, t.due_date AS transaction_due_date,
                   t.transaction_status
            FROM student_resource_requests q
            LEFT JOIN students accepter ON accepter.student_id = q.accepted_by
            LEFT JOIN resource_offers offer ON offer.request_id = q.borrow_request_id
            LEFT JOIN transactions t ON t.request_id = q.borrow_request_id
            WHERE q.student_id = %s
            ORDER BY q.created_at DESC
        ''', (session['student_id'],))
        requests = [
            {
                **dict(row),
                'due_date': str(row['due_date']) if row['due_date'] else None,
                'transaction_due_date': (
                    str(row['transaction_due_date'])
                    if row['transaction_due_date'] else None
                ),
                'created_at': str(row['created_at'])
            }
            for row in cursor.fetchall()
        ]

        cursor.execute('''
            SELECT q.request_id, q.resource_name, q.description, q.category,
                   q.due_date, q.request_status, q.created_at,
                   requester.student_name AS requester_name,
                   CASE WHEN t.transaction_id IS NOT NULL
                        THEN requester.email END AS requester_email,
                   offer.offer_id,
                   offer.offer_status,
                   t.transaction_id, t.due_date AS transaction_due_date,
                   t.transaction_status
            FROM student_resource_requests q
            JOIN students requester ON requester.student_id = q.student_id
            LEFT JOIN resource_offers offer ON offer.request_id = q.borrow_request_id
            LEFT JOIN transactions t ON t.request_id = q.borrow_request_id
            WHERE q.accepted_by = %s
            ORDER BY q.created_at DESC
        ''', (session['student_id'],))
        accepted_requests = [
            {
                **dict(row),
                'due_date': str(row['due_date']) if row['due_date'] else None,
                'transaction_due_date': (
                    str(row['transaction_due_date'])
                    if row['transaction_due_date'] else None
                ),
                'created_at': str(row['created_at'])
            }
            for row in cursor.fetchall()
        ]

        return jsonify({
            'success': True,
            'student_id': session['student_id'],
            'board_requests': board_requests,
            'requests': requests,
            'accepted_requests': accepted_requests
        })
    except Exception as error:
        print('Student dashboard load error:', error)
        return jsonify({'success': False, 'message': 'Unable to load dashboard data.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/student-dashboard/requests', methods=['POST'])
def create_student_resource_request():
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A valid borrow request is required.'}), 400

    resource_name = data.get('resource_name', '')
    description = data.get('description', '')
    category = data.get('category', '')
    due_date_value = data.get('due_date', '')

    if not isinstance(resource_name, str) or len(resource_name.strip()) > 150:
        return jsonify({'success': False, 'message': 'Resource name must be 150 characters or fewer.'}), 400
    if not isinstance(description, str) or len(description.strip()) > 2000:
        return jsonify({'success': False, 'message': 'Description must be 2000 characters or fewer.'}), 400
    if not isinstance(category, str) or len(category.strip()) > 50:
        return jsonify({'success': False, 'message': 'Category must be 50 characters or fewer.'}), 400
    if not isinstance(due_date_value, str):
        return jsonify({'success': False, 'message': 'A valid due date is required.'}), 400
    try:
        due_date = datetime.strptime(due_date_value, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Enter a valid due date.'}), 400
    if due_date.isoformat() != due_date_value or due_date < date.today():
        return jsonify({'success': False, 'message': 'Due date must be today or later.'}), 400
    if not resource_name.strip():
        return jsonify({'success': False, 'message': 'Resource name is required.'}), 400

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        cursor = get_db_cursor(connection)
        cursor.execute('''
            INSERT INTO student_resource_requests
                (student_id, resource_id, resource_name, description, category, due_date)
            VALUES (%s, NULL, %s, %s, %s, %s)
        ''', (
            session['student_id'],
            resource_name.strip(),
            description.strip(),
            category.strip(),
            due_date
        ))
        connection.commit()
        return jsonify({'success': True, 'message': 'Your borrow request has been sent.'}), 201

    except Exception as error:
        print('Student borrow request error:', error)
        if connection:
            connection.rollback()
        return jsonify({'success': False, 'message': 'Unable to create this borrow request.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/student-dashboard/requests/<int:request_id>/due-date', methods=['POST'])
def update_student_request_due_date(request_id):
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401

    data = request.get_json(silent=True)
    due_date_value = data.get('due_date') if isinstance(data, dict) else None
    if not isinstance(due_date_value, str):
        return jsonify({'success': False, 'message': 'A valid due date is required.'}), 400
    try:
        due_date = datetime.strptime(due_date_value, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Enter a valid due date.'}), 400
    if due_date.isoformat() != due_date_value or due_date < date.today():
        return jsonify({'success': False, 'message': 'Due date must be today or later.'}), 400

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        cursor = get_db_cursor(connection)
        cursor.execute('''
            UPDATE student_resource_requests
            SET due_date = %s
            WHERE request_id = %s AND student_id = %s AND request_status = 'OPEN'
        ''', (due_date, request_id, session['student_id']))
        if cursor.rowcount == 0:
            cursor.execute('''
                SELECT student_id, request_status, due_date
                FROM student_resource_requests
                WHERE request_id = %s
            ''', (request_id,))
            target = cursor.fetchone()
            if target is None:
                return jsonify({'success': False, 'message': 'Request not found.'}), 404
            if target['student_id'] != session['student_id']:
                return jsonify({'success': False, 'message': 'You can only update your own request.'}), 403
            if target['request_status'] != 'OPEN':
                return jsonify({'success': False, 'message': 'Only open requests can be updated.'}), 409

        connection.commit()
        return jsonify({'success': True, 'message': 'Expected return date saved.'})
    except Exception as error:
        print('Student request due date update error:', error)
        if connection:
            connection.rollback()
        return jsonify({'success': False, 'message': 'Unable to update the expected return date.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/student-dashboard/requests/<int:request_id>/accept', methods=['POST'])
def accept_student_request(request_id):
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        cursor = get_db_cursor(connection)
        with student_request_lock:
            cursor.execute('''
                SELECT student_id, request_status, due_date
                FROM student_resource_requests
                WHERE request_id = %s
                FOR UPDATE
            ''', (request_id,))
            request_row = cursor.fetchone()
            if request_row is None:
                return jsonify({'success': False, 'message': 'Request not found.'}), 404
            if request_row['student_id'] == session['student_id']:
                return jsonify({'success': False, 'message': 'You cannot accept your own request.'}), 403
            if request_row['request_status'] != 'OPEN':
                return jsonify({'success': False, 'message': 'This request has already been accepted.'}), 409
            if request_row['due_date'] is None:
                return jsonify({
                    'success': False,
                    'message': 'The requester must set an expected return date before you can accept this request.'
                }), 409

            cursor.execute('''
                UPDATE student_resource_requests
                SET request_status = 'OFFERED', accepted_by = %s
                WHERE request_id = %s AND student_id != %s
                  AND request_status = 'OPEN' AND accepted_by IS NULL
            ''', (session['student_id'], request_id, session['student_id']))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'This request has already been accepted.'}), 409

            cursor.execute('''
                SELECT student_id, resource_name, description, category, due_date
                FROM student_resource_requests
                WHERE request_id = %s
            ''', (request_id,))
            borrow_request = cursor.fetchone()
            cursor.execute('''
                INSERT INTO borrow_requests
                    (student_id, resource_name, description, category, request_status)
                VALUES (%s, %s, %s, %s, 'OPEN')
            ''', (
                borrow_request['student_id'],
                borrow_request['resource_name'],
                borrow_request['description'],
                borrow_request['category']
            ))
            legacy_request_id = cursor.lastrowid
            item_key = normalize_share_item_name(borrow_request['resource_name'])
            cursor.execute('''
                INSERT IGNORE INTO student_share_item_locks (sharer_id, item_key)
                VALUES (%s, %s)
            ''', (session['student_id'], item_key))
            cursor.execute(
                "SELECT GET_LOCK(%s, 10) AS acquired",
                ('sharesync_resource_offer_id',)
            )
            offer_lock = cursor.fetchone()
            if not offer_lock or offer_lock['acquired'] != 1:
                connection.rollback()
                return jsonify({
                    'success': False,
                    'message': 'The share offer is busy. Please try accepting again.'
                }), 503
            cursor.execute('''
                SELECT COALESCE(MAX(offer_id), 0) + 1 AS next_offer_id
                FROM resource_offers
            ''')
            offer_id = cursor.fetchone()['next_offer_id']
            cursor.execute('''
                INSERT INTO resource_offers
                    (offer_id, request_id, student_id, resource_name, description,
                     offer_status, share_item_key)
                VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
            ''', (
                offer_id,
                legacy_request_id,
                session['student_id'],
                borrow_request['resource_name'],
                borrow_request['description'],
                item_key
            ))
            cursor.execute('''
                UPDATE student_resource_requests
                SET borrow_request_id = %s
                WHERE request_id = %s
            ''', (legacy_request_id, request_id))
            connection.commit()
        return jsonify({
            'success': True,
            'message': 'Share offer sent. The requester must confirm it before a transaction is created.',
            'offer_id': offer_id
        })
    except Exception as error:
        print('Student request acceptance error:', error)
        if connection:
            connection.rollback()
        return jsonify({'success': False, 'message': 'Unable to accept this request.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/api/student-dashboard/requests/<int:request_id>/confirm-share', methods=['POST'])
def confirm_student_share(request_id):
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        cursor = get_db_cursor(connection)
        with student_request_lock:
            cursor.execute('''
                SELECT q.student_id, q.accepted_by, q.request_status,
                       q.borrow_request_id, q.due_date, q.resource_name,
                       q.description
                FROM student_resource_requests q
                WHERE q.request_id = %s
                FOR UPDATE
            ''', (request_id,))
            request_row = cursor.fetchone()
            if request_row is None:
                return jsonify({'success': False, 'message': 'Request not found.'}), 404
            if request_row['student_id'] != session['student_id']:
                return jsonify({
                    'success': False,
                    'message': 'Only the student who posted this request can confirm the share.'
                }), 403
            if request_row['request_status'] == 'UNAVAILABLE':
                return jsonify({
                    'success': False,
                    'message': 'Another borrower confirmed this item first. This share offer is no longer available.'
                }), 409
            if request_row['request_status'] != 'OFFERED':
                return jsonify({
                    'success': False,
                    'message': 'There is no pending share offer to confirm.'
                }), 409
            if request_row['due_date'] is None or request_row['borrow_request_id'] is None:
                return jsonify({
                    'success': False,
                    'message': 'The request is missing its due date or linked share offer.'
                }), 409

            cursor.execute('''
                SELECT offer_id, share_item_key, resource_name, offer_status
                FROM resource_offers
                WHERE request_id = %s AND student_id = %s
                ORDER BY offered_at DESC
                LIMIT 1
            ''', (request_row['borrow_request_id'], request_row['accepted_by']))
            offer = cursor.fetchone()
            if offer is None:
                return jsonify({
                    'success': False,
                    'message': 'The share offer could not be found.'
                }), 409

            item_key = offer['share_item_key'] or normalize_share_item_name(offer['resource_name'])
            cursor.execute('''
                INSERT IGNORE INTO student_share_item_locks (sharer_id, item_key)
                VALUES (%s, %s)
            ''', (request_row['accepted_by'], item_key))
            cursor.execute('''
                SELECT sharer_id
                FROM student_share_item_locks
                WHERE sharer_id = %s AND item_key = %s
                FOR UPDATE
            ''', (request_row['accepted_by'], item_key))
            if cursor.fetchone() is None:
                raise RuntimeError('Unable to lock the shared item for confirmation.')

            cursor.execute('''
                SELECT t.transaction_id
                FROM transactions t
                JOIN resource_offers existing_offer ON existing_offer.offer_id = t.offer_id
                WHERE t.lender_id = %s
                  AND t.transaction_status = 'ACTIVE'
                  AND (
                      existing_offer.share_item_key = %s
                      OR (
                          existing_offer.share_item_key IS NULL
                          AND LOWER(TRIM(existing_offer.resource_name)) =
                              LOWER(TRIM(%s))
                      )
                  )
                LIMIT 1
                FOR UPDATE
            ''', (
                request_row['accepted_by'],
                item_key,
                offer['resource_name']
            ))
            existing_transaction = cursor.fetchone()
            if existing_transaction is not None:
                cursor.execute('''
                    UPDATE resource_offers
                    SET offer_status = 'Unavailable'
                    WHERE offer_id = %s
                ''', (offer['offer_id'],))
                cursor.execute('''
                    UPDATE borrow_requests
                    SET request_status = 'UNAVAILABLE'
                    WHERE request_id = %s
                ''', (request_row['borrow_request_id'],))
                cursor.execute('''
                    UPDATE student_resource_requests
                    SET request_status = 'UNAVAILABLE'
                    WHERE request_id = %s AND request_status = 'OFFERED'
                ''', (request_id,))
                cursor.execute('''
                    UPDATE resource_offers
                    SET offer_status = 'Unavailable'
                    WHERE student_id = %s
                      AND share_item_key = %s
                      AND offer_status = 'Pending'
                ''', (request_row['accepted_by'], item_key))
                cursor.execute('''
                    UPDATE borrow_requests br
                    JOIN resource_offers offer ON offer.request_id = br.request_id
                    SET br.request_status = 'UNAVAILABLE'
                    WHERE offer.student_id = %s
                      AND offer.share_item_key = %s
                      AND offer.offer_status = 'Unavailable'
                ''', (request_row['accepted_by'], item_key))
                cursor.execute('''
                    UPDATE student_resource_requests board
                    JOIN resource_offers offer
                      ON offer.request_id = board.borrow_request_id
                    SET board.request_status = 'UNAVAILABLE'
                    WHERE offer.student_id = %s
                      AND offer.share_item_key = %s
                      AND offer.offer_status = 'Unavailable'
                      AND board.request_status = 'OFFERED'
                ''', (request_row['accepted_by'], item_key))
                connection.commit()
                return jsonify({
                    'success': False,
                    'message': 'Another borrower confirmed this item first. This share offer is no longer available.'
                }), 409

            cursor.execute('''
                INSERT INTO transactions
                    (request_id, offer_id, borrower_id, lender_id, due_date, transaction_status)
                VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
            ''', (
                request_row['borrow_request_id'],
                offer['offer_id'],
                request_row['student_id'],
                request_row['accepted_by'],
                request_row['due_date']
            ))
            transaction_id = cursor.lastrowid
            cursor.execute('''
                UPDATE resource_offers
                SET offer_status = 'Accepted'
                WHERE offer_id = %s
            ''', (offer['offer_id'],))
            cursor.execute('''
                UPDATE resource_offers
                SET offer_status = 'Unavailable'
                WHERE student_id = %s
                  AND share_item_key = %s
                  AND offer_status = 'Pending'
                  AND offer_id != %s
            ''', (
                request_row['accepted_by'],
                item_key,
                offer['offer_id']
            ))
            cursor.execute('''
                UPDATE borrow_requests br
                JOIN resource_offers offer ON offer.request_id = br.request_id
                SET br.request_status = 'UNAVAILABLE'
                WHERE offer.student_id = %s
                  AND offer.share_item_key = %s
                  AND offer.offer_status = 'Unavailable'
            ''', (request_row['accepted_by'], item_key))
            cursor.execute('''
                UPDATE student_resource_requests board
                JOIN resource_offers offer
                  ON offer.request_id = board.borrow_request_id
                SET board.request_status = 'UNAVAILABLE'
                WHERE offer.student_id = %s
                  AND offer.share_item_key = %s
                  AND offer.offer_status = 'Unavailable'
                  AND board.request_status = 'OFFERED'
            ''', (request_row['accepted_by'], item_key))
            cursor.execute('''
                UPDATE borrow_requests
                SET request_status = 'ACCEPTED'
                WHERE request_id = %s
            ''', (request_row['borrow_request_id'],))
            cursor.execute('''
                UPDATE student_resource_requests
                SET request_status = 'ACCEPTED'
                WHERE request_id = %s AND request_status = 'OFFERED'
            ''', (request_id,))
            if cursor.rowcount != 1:
                connection.rollback()
                return jsonify({
                    'success': False,
                    'message': 'The share offer is no longer pending.'
                }), 409
            connection.commit()

        return jsonify({
            'success': True,
            'message': f'Share confirmed. Active transaction #{transaction_id} was created.',
            'transaction_id': transaction_id
        })
    except Exception as error:
        print('Student share confirmation error:', error)
        if connection:
            connection.rollback()
        return jsonify({
            'success': False,
            'message': 'Unable to confirm this share offer.'
        }), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()



@app.route('/admin-review-student', methods=['POST'])
def admin_review_student():
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Admin login required.'}), 401
    if session.get('admin_role') != 'ADMIN':
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403

    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    action = data.get('action')

    if student_id is None:
        return jsonify({'success': False, 'message': 'Student ID is required.'}), 400

    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Student ID must be a valid number.'}), 400

    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action.'}), 400

    new_status = 'VERIFIED' if action == 'approve' else 'REJECTED'
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            '''
            UPDATE students
            SET verification_status = %s
            WHERE student_id = %s AND role = 'STUDENT' AND verification_status = 'PENDING'
            ''',
            (new_status, student_id)
        )

        if cursor.rowcount == 0:
            connection.rollback()
            return jsonify({'success': False, 'message': 'Student not found or already reviewed.'}), 404

        connection.commit()
        message = 'Student approved successfully.' if action == 'approve' else 'Student rejected successfully.'
        return jsonify({'success': True, 'message': message})
    except Exception as error:

        print('Review error:', error)
        if connection:
            connection.rollback()
        return jsonify({'success': False, 'message': 'Database error occurred.'}), 500
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
