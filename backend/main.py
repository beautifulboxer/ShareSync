from flask import Flask, render_template, request, jsonify
import mysql.connector
from werkzeug.security  import  generate_password_hash,  check_password_hash
from dotenv import load_dotenv
import os
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend"),
    static_folder=os.path.join(BASE_DIR, "frontend"),
    static_url_path="/static"
)

app.secret_key = os.getenv('FLASK_SECRET_KEY') or 'share-sync-dev-secret'
student_request_lock = Lock()

app.register_blueprint(student_dashboard_bp)



def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )

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

        query = """
            SELECT student_id, student_name, email, password_hash,
                   role, verification_status
            FROM students
            WHERE email = %s
        """

        cursor.execute(query, (email,))
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


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    name = data.get("name", "").strip()
    college_id = data.get("collegeId", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not name or not college_id or not email or not password:
        return jsonify({
            "success": False,
            "message": "Please fill all fields."
        }), 400

    try:
        student_id = int(college_id)
    except ValueError:
        return jsonify({
            "success": False,
            "message": "College ID must be a number."
        }), 400

    password_hash = generate_password_hash(password)

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            INSERT INTO students
            (student_id, student_name, email, password_hash, role, verification_status)
            VALUES (%s, %s, %s, %s, 'STUDENT', 'PENDING')
        """

        cursor.execute(
            query,
            (student_id, name, email, password_hash)
        )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Registered successfully! Wait for Admin's approval."
        })

    except mysql.connector.IntegrityError as error:
        print("Integrity error:", error)

        return jsonify({
            "success": False,
            "message": "College ID or email already exists."
        }), 409

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




if __name__ == "__main__":

    app.run( host="0.0.0.0",port=8000,debug=True)

 