from flask import Blueprint, render_template, session, redirect

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