from flask import Blueprint, render_template, session, redirect, request, jsonify

from datetime import date, datetime

import mysql.connector

from database import (

    get_db_connection,

    get_db_cursor,

    ensure_student_dashboard_tables,

    student_request_lock

)

student_dashboard_bp = Blueprint(

    "student_dashboard",

    __name__

)

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
