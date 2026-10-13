from flask import Blueprint, render_template, request, jsonify, session, redirect
from database import get_db_connection, get_db_cursor


admin_bp  = Blueprint("admin", __name__)


@admin_bp.route("/admin")
def admin_login_page():
    return render_template("admin-login.html")


@admin_bp.route("/admin-login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))

    from werkzeug.security import check_password_hash

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Admin email and password are required."
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

        admin = cursor.fetchone()

        if admin is None:
            return jsonify({
                "success": False,
                "message": "Invalid admin email or password."
            }), 401

        if not check_password_hash(admin["password_hash"], password):
            return jsonify({
                "success": False,
                "message": "Invalid admin email or password."
            }), 401

        if admin["role"] != "ADMIN":
            return jsonify({
                "success": False,
                "message": "You are not authorized as an admin."
            }), 403

        if admin["verification_status"] != "VERIFIED":
            return jsonify({
                "success": False,
                "message": "Admin account is not verified."
            }), 403

        session.clear()
        session["admin_id"] = admin["student_id"]
        session["admin_role"] = admin["role"]

        return jsonify({
            "success": True,
            "message": "Admin login successful.",
            "student_name": admin["student_name"],
            "role": admin["role"]
        })

    except Exception as error:
        print("Admin login error:", error)

        return jsonify({
            "success": False,
            "message": "Database error occurred."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@admin_bp.route("/admin-logout")
def admin_logout():
    session.clear()
    return redirect("/admin")


@admin_bp.route("/admin-dashboard")
def admin_dashboard():
    if "admin_id" not in session:
        return redirect("/admin")

    if session.get("admin_role") != "ADMIN":
        return redirect("/admin")

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = get_db_cursor(connection)

        cursor.execute(
            """
            SELECT student_id, student_name, email, created_at
            FROM students
            WHERE role = 'STUDENT'
              AND verification_status = 'PENDING'
            ORDER BY created_at DESC
            """
        )

        pending_students = cursor.fetchall()

        return render_template(
            "admin-dashboard.html",
            students=pending_students
        )

    except Exception as error:
        print("Admin dashboard error:", error)
        return "Database error occurred.", 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@admin_bp.route("/admin-student-history")
def admin_student_history():
    if "admin_id" not in session:
        return redirect("/admin")

    if session.get("admin_role") != "ADMIN":
        return redirect("/admin")

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = get_db_cursor(connection)

        cursor.execute(
            """
            SELECT student_id, student_name, email,
                   verification_status, created_at,
                   created_at AS updated_at
            FROM students
            WHERE role = 'STUDENT'
            ORDER BY created_at DESC
            """
        )

        student_history = cursor.fetchall()

        return render_template(
            "admin-student-history.html",
            students=student_history
        )

    except Exception as error:
        print("Student history error:", error)
        return "Database error occurred.", 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@admin_bp.route("/admin-review-student", methods=["POST"])
def admin_review_student():
    if "admin_id" not in session:
        return jsonify({
            "success": False,
            "message": "Admin login required."
        }), 401

    if session.get("admin_role") != "ADMIN":
        return jsonify({
            "success": False,
            "message": "Admin access required."
        }), 403

    data = request.get_json(silent=True) or {}

    student_id = data.get("student_id")
    action = data.get("action")

    if student_id is None:
        return jsonify({
            "success": False,
            "message": "Student ID is required."
        }), 400

    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Student ID must be a valid number."
        }), 400

    if action not in ["approve", "reject"]:
        return jsonify({
            "success": False,
            "message": "Invalid action."
        }), 400

    new_status = "VERIFIED" if action == "approve" else "REJECTED"

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE students
            SET verification_status = %s
            WHERE student_id = %s
              AND role = 'STUDENT'
              AND verification_status = 'PENDING'
            """,
            (new_status, student_id)
        )

        if cursor.rowcount == 0:
            connection.rollback()

            return jsonify({
                "success": False,
                "message": "Student not found or already reviewed."
            }), 404

        connection.commit()

        message = (
            "Student approved successfully."
            if action == "approve"
            else "Student rejected successfully."
        )

        return jsonify({
            "success": True,
            "message": message
        })

    except Exception as error:
        print("Review error:", error)

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
