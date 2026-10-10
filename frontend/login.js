

const studentTable = document.getElementById("studentTable");
const noStudentsMessage = document.getElementById("noStudentsMessage");

if (studentTable) {
    const students = studentTable.querySelectorAll(".admin-student");
    students.forEach(function (studentElement) {

        const studentId = studentElement.dataset.studentId;

        const approveBtn =
            studentElement.querySelector(".approve-btn");
        const rejectBtn =
            studentElement.querySelector(".reject-btn");
        if (approveBtn) {
            approveBtn.addEventListener("click", function () {
                reviewStudent(
                    studentId,
                    "approve",
                    studentElement
                );
            });
        }
        if (rejectBtn) {
            rejectBtn.addEventListener("click", function () {
                reviewStudent(
                    studentId,
                    "reject",
                    studentElement
                );
            });
        }
    });
}

async function reviewStudent(studentId, action, studentElement) {

    try {
        const response = await fetch("/admin-review-student", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                student_id: studentId,
                action: action
            })
        });

        const data = await response.json();
        alert(data.message);
        if (data.success) {
            studentElement.remove();

            if (studentTable && noStudentsMessage && studentTable.children.length === 0) {
                noStudentsMessage.style.display = "block";
            }
        }
    } catch (error) {
        console.error(error);
        alert("Unable to connect to the server.");
    }
}

