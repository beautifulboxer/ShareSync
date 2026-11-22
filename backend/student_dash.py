from flask import Blueprint, render_template, session, redirect, request, jsonify
from datetime import date, datetime
import mysql.connector
from database import (
    get_db_connection,
    get_db_cursor,
    ensure_student_dashboard_tables,
    student_request_lock
)
from os_deadlock import (
    detect_os_deadlock,
    recover_os_deadlock,
    get_os_deadlock_history
)
student_dashboard_bp = Blueprint(
    "student_dashboard",
    __name__
)
# Late-fee rate (rupees) charged for every day a loan is returned after its due date.
LATE_FEE_PER_DAY = 5
def ensure_review_fee_tables(connection):
    """Create the late-fee and review tables if they do not exist yet."""
    cursor = connection.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transaction_fees (
                transaction_id INT PRIMARY KEY,
                late_days INT NOT NULL,
                fee_amount INT NOT NULL,
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transaction_reviews (
                review_id INT AUTO_INCREMENT PRIMARY KEY,
                transaction_id INT NOT NULL,
                reviewer_id INT NOT NULL,
                reviewee_id INT NOT NULL,
                rating TINYINT NOT NULL,
                comment VARCHAR(500) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_review_once (transaction_id, reviewer_id)
            ) ENGINE=InnoDB
        ''')
        connection.commit()
    finally:
        cursor.close()
def late_days_for(due_value, on_date=None):
    """Whole days between the due date and today (0 if not late or no date)."""
    if not due_value:
        return 0
    due = date.fromisoformat(str(due_value)[:10])
    return max(0, ((on_date or date.today()) - due).days)
@student_dashboard_bp.route("/student-dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect("/")
    if session.get("student_role") != "STUDENT":
        return redirect("/")
    return render_template(
        "student-dashboard.html",
        student_name=session.get("student_name"),
        student_id=session.get("student_id")
    )
def is_student_session():
    return 'student_id' in session and session.get('student_role') == 'STUDENT'
@student_dashboard_bp.route('/api/student-dashboard/os-deadlock', methods=['GET'])
def detect_deadlock_api():
    """Detect deadlock. Only the OS tracking tables are refreshed; no loans or requests change."""
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401
    connection = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        result = detect_os_deadlock(
            connection, requested_by=session['student_id']
        )
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    except Exception as error:
        if connection:
            connection.rollback()
        print('OS deadlock detection error:', error)
        return jsonify({
            'success': False,
            'message': 'Unable to run deadlock detection. Check the database tables and backend logs.'
        }), 500
    finally:
        if connection:
            connection.close()
@student_dashboard_bp.route('/api/student-dashboard/os-deadlock/recover', methods=['POST'])
def recover_deadlock_api():
    """Recover deadlock: cancel victim request, end victim loan, reallocate item to the waiter."""
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401
    connection = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        body = request.get_json(silent=True)
        policy = body.get('policy') if isinstance(body, dict) else None
        result = recover_os_deadlock(
            connection,
            requested_by=session['student_id'],
            policy=policy
        )
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    except Exception as error:
        if connection:
            connection.rollback()
        print('OS deadlock recovery error:', error)
        return jsonify({
            'success': False,
            'message': 'Unable to run deadlock recovery. Check the database tables and backend logs.'
        }), 500
    finally:
        if connection:
            connection.close()
@student_dashboard_bp.route('/api/student-dashboard/os-deadlock/history', methods=['GET'])
def deadlock_history_api():
    """Return the latest deadlock detections and recoveries."""
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401
    connection = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        return jsonify(get_os_deadlock_history(connection, limit=20))
    except Exception as error:
        print('OS deadlock history error:', error)
        return jsonify({
            'success': False,
            'message': 'Unable to load deadlock history.'
        }), 500
    finally:
        if connection:
            connection.close()
@student_dashboard_bp.route('/api/student-dashboard/transactions/<int:transaction_id>/return', methods=['POST'])
def return_student_transaction(transaction_id):
    """Mark an ACTIVE transaction as returned (borrower or lender) and record any late fee."""
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        ensure_review_fee_tables(connection)
        cursor = get_db_cursor(connection)
        with student_request_lock:
            cursor.execute('''
                SELECT transaction_id, borrower_id, lender_id, transaction_status, due_date
                FROM transactions
                WHERE transaction_id = %s
                FOR UPDATE
            ''', (transaction_id,))
            transaction = cursor.fetchone()
            if transaction is None:
                return jsonify({'success': False, 'message': 'Transaction not found.'}), 404
            if session['student_id'] not in (
                transaction['borrower_id'], transaction['lender_id']
            ):
                return jsonify({
                    'success': False,
                    'message': 'Only the borrower or the lender can mark this item as returned.'
                }), 403
            if transaction['transaction_status'] != 'ACTIVE':
                return jsonify({
                    'success': False,
                    'message': 'This transaction is not active.'
                }), 409
            cursor.execute('''
                UPDATE transactions
                SET transaction_status = 'RETURNED', returned_at = NOW()
                WHERE transaction_id = %s AND transaction_status = 'ACTIVE'
            ''', (transaction_id,))
            if cursor.rowcount != 1:
                connection.rollback()
                return jsonify({
                    'success': False,
                    'message': 'This transaction is not active.'
                }), 409
            late_days = late_days_for(transaction['due_date'])
            late_fee = late_days * LATE_FEE_PER_DAY
            if late_days > 0:
                cursor.execute('''
                    INSERT INTO transaction_fees (transaction_id, late_days, fee_amount)
                    VALUES (%s, %s, %s)
                ''', (transaction_id, late_days, late_fee))
            connection.commit()
        message = f'Transaction #{transaction_id} was marked as returned.'
        if late_days > 0:
            message += f' Returned {late_days} day(s) late: late fee Rs. {late_fee}.'
        return jsonify({
            'success': True,
            'message': message,
            'late_days': late_days,
            'late_fee': late_fee
        })
    except Exception as error:
        print('Student return error:', error)
        if connection:
            connection.rollback()
        return jsonify({
            'success': False,
            'message': 'Unable to mark this item as returned.'
        }), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
@student_dashboard_bp.route('/api/student-dashboard/transactions/<int:transaction_id>/review', methods=['POST'])
def review_student_transaction(transaction_id):
    """Let the borrower or lender review the other student after a return."""
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A valid review is required.'}), 400
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Rating must be a number from 1 to 5.'}), 400
    comment = data.get('comment', '')
    if not 1 <= rating <= 5:
        return jsonify({'success': False, 'message': 'Rating must be a number from 1 to 5.'}), 400
    if not isinstance(comment, str) or len(comment.strip()) > 500:
        return jsonify({'success': False, 'message': 'Comment must be 500 characters or fewer.'}), 400
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        ensure_review_fee_tables(connection)
        cursor = get_db_cursor(connection)
        cursor.execute('''
            SELECT borrower_id, lender_id, transaction_status
            FROM transactions
            WHERE transaction_id = %s
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        if transaction is None:
            return jsonify({'success': False, 'message': 'Transaction not found.'}), 404
        me = session['student_id']
        if me not in (transaction['borrower_id'], transaction['lender_id']):
            return jsonify({
                'success': False,
                'message': 'Only the borrower or the lender can review this transaction.'
            }), 403
        if transaction['transaction_status'] != 'RETURNED':
            return jsonify({
                'success': False,
                'message': 'You can leave a review after the item is returned.'
            }), 409
        reviewee = (
            transaction['lender_id']
            if me == transaction['borrower_id']
            else transaction['borrower_id']
        )
        cursor.execute('''
            INSERT INTO transaction_reviews
                (transaction_id, reviewer_id, reviewee_id, rating, comment)
            VALUES (%s, %s, %s, %s, %s)
        ''', (transaction_id, me, reviewee, rating, comment.strip()))
        connection.commit()
        return jsonify({'success': True, 'message': 'Thanks! Your review was saved.'})
    except mysql.connector.IntegrityError:
        if connection:
            connection.rollback()
        return jsonify({
            'success': False,
            'message': 'You have already reviewed this transaction.'
        }), 409
    except Exception as error:
        print('Student review error:', error)
        if connection:
            connection.rollback()
        return jsonify({'success': False, 'message': 'Unable to save this review.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
def normalize_share_item_name(resource_name):
    return ' '.join(resource_name.split()).casefold()
@student_dashboard_bp.route('/api/student-dashboard', methods=['GET'])
def student_dashboard_data():
    if not is_student_session():
        return jsonify({'success': False, 'message': 'Student login required.'}), 401
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        ensure_student_dashboard_tables(connection)
        ensure_review_fee_tables(connection)
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
        transaction_rows = requests + accepted_requests
        transaction_ids = {
            row['transaction_id']
            for row in transaction_rows
            if row.get('transaction_id')
        }
        fees = {}
        reviewed = set()
        if transaction_ids:
            marks = ', '.join(['%s'] * len(transaction_ids))
            cursor.execute(f'''
                SELECT transaction_id, late_days, fee_amount
                FROM transaction_fees
                WHERE transaction_id IN ({marks})
            ''', tuple(transaction_ids))
            fees = {row['transaction_id']: row for row in cursor.fetchall()}
            cursor.execute(f'''
                SELECT transaction_id
                FROM transaction_reviews
                WHERE reviewer_id = %s AND transaction_id IN ({marks})
            ''', (session['student_id'], *transaction_ids))
            reviewed = {row['transaction_id'] for row in cursor.fetchall()}
        for row in transaction_rows:
            tx_id = row.get('transaction_id')
            if not tx_id:
                continue
            row['already_reviewed'] = tx_id in reviewed
            if row.get('transaction_status') == 'ACTIVE':
                days = late_days_for(row.get('transaction_due_date'))
                row['late_days'] = days
                row['late_fee'] = days * LATE_FEE_PER_DAY
            elif tx_id in fees:
                row['late_days'] = fees[tx_id]['late_days']
                row['late_fee'] = fees[tx_id]['fee_amount']
        cursor.execute('''
            SELECT COUNT(*) AS review_count, AVG(rating) AS average_rating
            FROM transaction_reviews
            WHERE reviewee_id = %s
        ''', (session['student_id'],))
        summary = cursor.fetchone()
        my_rating = {
            'count': summary['review_count'],
            'average': (
                round(float(summary['average_rating']), 2)
                if summary['average_rating'] is not None else None
            )
        }
        return jsonify({
            'success': True,
            'student_id': session['student_id'],
            'board_requests': board_requests,
            'requests': requests,
            'accepted_requests': accepted_requests,
            'my_rating': my_rating,
            'late_fee_per_day': LATE_FEE_PER_DAY
        })
    except Exception as error:
        print('Student dashboard load error:', error)
        return jsonify({'success': False, 'message': 'Unable to load dashboard data.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
@student_dashboard_bp.route('/api/student-dashboard/requests', methods=['POST'])
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
@student_dashboard_bp.route('/api/student-dashboard/requests/<int:request_id>/due-date', methods=['POST'])
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
@student_dashboard_bp.route('/api/student-dashboard/requests/<int:request_id>/accept', methods=['POST'])
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
@student_dashboard_bp.route('/api/student-dashboard/requests/<int:request_id>/confirm-share', methods=['POST'])
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