from flask import Flask, render_template, request, jsonify, session, redirect
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
from datetime import date, datetime
from threading import Lock

load_dotenv()

from database import get_db_connection, get_db_cursor, ensure_student_dashboard_tables
from student import student_dashboard_bp
from admin import admin_bp


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend"),
    static_folder=os.path.join(BASE_DIR, "frontend"),
    static_url_path="/static"
)

app.secret_key = os.getenv("FLASK_SECRET_KEY") or "share-sync-dev-secret"

student_request_lock = Lock()


@app.before_request
def check_authentication():
    allowed_routes = {
        "home",
        "register_page",
        "login",
        "register",
        "student_logout",
        "admin.admin_login_page",
        "admin.admin_login",
        "admin.admin_logout"
    }

    if request.endpoint in allowed_routes:
        return

    if request.path.startswith("/static/"):
        return

    if request.path.startswith("/api/student-dashboard"):
        return

    if "student_id" not in session and "admin_id" not in session:
        return redirect("/")

    if "student_id" in session and request.path.startswith("/admin-dashboard"):
        return redirect("/student-dashboard")

    if "admin_id" in session and request.path.startswith("/student-dashboard"):
        return redirect("/admin-dashboard")


def is_student_session():
    return (
        "student_id" in session
        and session.get("student_role") == "STUDENT"
    )


def normalize_share_item_name(resource_name):
    return " ".join(resource_name.split()).casefold()


@app.route("/")
def home():
    return render_template("login.html")


@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Email and password are required."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = get_db_cursor(connection)

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

        if user["role"] != "STUDENT":
            return jsonify({
                "success": False,
                "message": "Please use the admin login page."
            }), 403

        if user["verification_status"] != "VERIFIED":
            return jsonify({
                "success": False,
                "message": "Your account is not verified yet."
            }), 403

        session.clear()
        session["student_id"] = user["student_id"]
        session["student_role"] = user["role"]

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
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    college_id = str(data.get("collegeId", "")).strip()
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))

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

        cursor.execute(
            """
            INSERT INTO students
            (student_id, student_name, email, password_hash,
             role, verification_status)
            VALUES (%s, %s, %s, %s, 'STUDENT', 'PENDING')
            """,
            (student_id, name, email, password_hash)
        )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Registered successfully! Wait for Admin's approval."
        })

    except mysql.connector.IntegrityError:
        if connection:
            connection.rollback()

        return jsonify({
            "success": False,
            "message": "College ID or email already exists."
        }), 409

    except mysql.connector.Error as error:
        print("Register error:", error)

        if connection:
            connection.rollback()

        return jsonify({
            "success": False,
            "message": "Database error occurred."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/student-logout")
def student_logout():
    session.clear()
    return redirect("/")


# Register the student dashboard and admin blueprints.
app.register_blueprint(student_dashboard_bp)
app.register_blueprint(admin_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
