from flask import Flask, render_template, request, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(
    __name__,
    template_folder="../frontend",
    static_folder="../frontend",
    static_url_path="/static"
)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="paste_password_here",
        database="sharesync"
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000 ,debug=True)