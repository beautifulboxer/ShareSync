from flask import Flask, render_template, request, jsonify, session, redirect
import mysql.connector
from werkzeug.security  import  generate_password_hash,  check_password_hash
from dotenv import load_dotenv
import os
load_dotenv()
from student_dash import student_dashboard_bp
from datetime import date, datetime
from database import get_db_connection, get_db_cursor, ensure_student_dashboard_tables


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend"),
    static_folder=os.path.join(BASE_DIR, "frontend"),
    static_url_path="/static"
)

app.secret_key = os.getenv('FLASK_SECRET_KEY') or 'share-sync-dev-secret'

@app.before_request
def check_authentication():
    allowed_routes = {
        'home',
        'login','register_page','register',
        'admin_login_page',
        'admin_login','student_logout', 'admin_logout'
    }
    if request.endpoint in allowed_routes:
        return
    if request.path.startswith('/static/'):
        return
    if request.path.startswith('/api/student-dashboard'):
        return

    if 'student_id' not in session and 'admin_id' not in session:
        return redirect('/')
    if 'student_id' in session and request.path.startswith('/admin-dashboard'):
        return redirect('/student-dashboard')
    if 'admin_id' in session and request.path.startswith('/student-dashboard'):
        return redirect('/admin-dashboard')


app.register_blueprint(student_dashboard_bp)

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Email and password are required."
        }), 400
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT student_id, student_name, email, password_hash,
                   role, verification_status
            FROM students
            WHERE email = %s
            """,
            (email,)
        )
        user = cursor.fetchone()

        if user is None:
            return jsonify({
                "success": False,
                "message": "Invalid email or password."
            }), 401

        if not check_password_hash(user["password_hash"], password):
            return jsonify({
                "success": False,
                "message": "Invalid email or password."
            }), 401

        if user["verification_status"] != "VERIFIED":
            return jsonify({
                "success": False,
                "message": "Your account is not verified yet."
            }), 403

        return jsonify({
            "success": True,
            "message": "Welcome to ShareSync!",
            "student_name": user["student_name"],
            "role": user["role"]
        })

    except mysql.connector.Error as error:
        print("Database error:", error)
        return jsonify({
            "success": False,
            "message": "Database error occurred."
        }), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def normalize_share_item_name(resource_name):
    return ' '.join(resource_name.split()).casefold()

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


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    college_id = str(data.get('collegeId', '')).strip()
    email = str(data.get('email', '')).strip()
    password = str(data.get('password', ''))
    if not name or not college_id or not email or not password:
        return jsonify({'success': False, 'message': 'Please fill all fields.'}), 400

    try:
        student_id = int(college_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'College ID must be a number.'}), 400

    password_hash = generate_password_hash(password)
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            '''
            INSERT INTO students
            (student_id, student_name, email, password_hash, role, verification_status)
            VALUES (%s, %s, %s, %s, 'STUDENT', 'PENDING')
            ''',
            (student_id, name, email, password_hash)
        )
        connection.commit()
        return jsonify({'success': True, 'message': "Registered successfully! Wait for Admin's approval."})
    except mysql.connector.IntegrityError:
        return jsonify({'success': False, 'message': 'College ID or email already exists.'}), 409
    except Exception as error:
        print('Register error:', error)
        return jsonify({'success': False, 'message': 'Database error occurred.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/admin")
def admin_login_page():
    return render_template("admin-login.html")

@app.route('/admin-login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip()
    password = str(data.get('password', ''))

    if not email or not password:
        return jsonify({'success': False, 'message': 'Admin email and password are required.'}), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = get_db_cursor(connection)

        cursor.execute('''
            SELECT student_id, student_name, email, password_hash, role, verification_status
            FROM students
            WHERE email = %s
        ''', (email,))
        admin = cursor.fetchone()

        if admin is None:
            return  jsonify({'success': False, 'message': 'Invalid admin email or password.'}), 401

        if not check_password_hash(admin['password_hash'], password):
            return  jsonify({'success': False, 'message': 'Invalid admin email or password.'}), 401

        if admin['role'] != 'ADMIN':
            return  jsonify({'success': False, 'message': 'You are not authorized as an admin.'}), 403

        if admin['verification_status'] != 'VERIFIED':
            return  jsonify({'success': False, 'message': 'Admin account is not verified.'}), 403

        session.clear()
        session['admin_id'] = admin['student_id']
        session['admin_role'] = admin['role']

        return jsonify({
            'success': True,
            'message': 'Admin login successful.',
            'student_name': admin['student_name'],
            'role': admin['role']
        })
    except Exception as error:
        print('Admin login error:', error)
        return jsonify({'success': False, 'message': 'Database error occurred.'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/student-logout')
def student_logout():
    session.clear()
    return redirect('/')


@app.route('/admin-logout')
def admin_logout():
    session.clear()
    return redirect('/admin')



@app.route('/admin-dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/admin')
    if session.get('admin_role') != 'ADMIN':
        return redirect('/admin')

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = get_db_cursor(connection)
        cursor.execute('''
            SELECT student_id, student_name, email, created_at
            FROM students
            WHERE role = 'STUDENT' AND verification_status = 'PENDING'
            ORDER BY created_at DESC
        ''')
        pending_students = cursor.fetchall()
        return render_template('admin-dashboard.html', students=pending_students)
    except Exception as error:
        print('Admin dashboard error:', error)
        return 'Database error occurred.', 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/admin-student-history')
def admin_student_history():
    if 'admin_id' not in session:
        return redirect('/admin')
    if session.get('admin_role') != 'ADMIN':
        return redirect('/admin')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = get_db_cursor(connection)
        cursor.execute('''
            SELECT student_id, student_name, email, verification_status, created_at, created_at AS updated_at
            FROM students
            WHERE role = 'STUDENT'
            ORDER BY created_at DESC
        ''')
        student_history = cursor.fetchall()
        return render_template('admin-student-history.html', students=student_history)
    except Exception as error:
        print('Student history error:', error)
        return 'Database error occurred.', 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
