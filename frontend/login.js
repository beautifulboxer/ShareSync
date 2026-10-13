

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

const adminLoginForm = document.getElementById("adminLoginForm");
const adminLoginMessage = document.getElementById("adminLoginMessage");

if (adminLoginForm && adminLoginMessage) {
    adminLoginForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        adminLoginMessage.hidden = true;

        const submitButton = adminLoginForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch("/admin-login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    email: document.getElementById("adminEmail").value,
                    password: document.getElementById("adminPassword").value
                })
            });
            const data = await response.json();

            if (!response.ok || !data.success) {
                adminLoginMessage.textContent = data.message || "Admin sign in failed.";
                adminLoginMessage.hidden = false;
                return;
            }

            window.location.assign("/admin-dashboard");
        } catch (error) {
            console.error("Admin login failed:", error);
            adminLoginMessage.textContent = "Unable to connect to the server. Please try again.";
            adminLoginMessage.hidden = false;
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    });
}

const passwordToggles = [
    ["passwordToggle", "password"],
    ["adminPasswordToggle", "adminPassword"]
];

passwordToggles.forEach(function ([toggleId, inputId]) {
    const toggle = document.getElementById(toggleId);
    const input = document.getElementById(inputId);

    if (toggle && input) {
        toggle.addEventListener("click", function () {
            const showPassword = input.type === "password";
            input.type = showPassword ? "text" : "password";
            toggle.setAttribute("aria-label", showPassword ? "Hide password" : "Show password");
            toggle.setAttribute("title", showPassword ? "Hide password" : "Show password");
            toggle.classList.toggle("is-visible", showPassword);
        });
    }
});

const loginForm = document.getElementById("loginForm");
const loginMessage = document.getElementById("loginMessage");

if (loginForm && loginMessage) {
    loginForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        loginMessage.hidden = true;

        const submitButton = loginForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch("/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    email: document.getElementById("email").value,
                    password: document.getElementById("password").value
                })
            });
            const data = await response.json();

            if (!response.ok || !data.success) {
                loginMessage.textContent = data.message || "Sign in failed.";
                loginMessage.hidden = false;
                return;
            }

            window.location.assign(data.role === "ADMIN" ? "/admin-dashboard" : "/student-dashboard");
        } catch (error) {
            console.error("Login failed:", error);
            loginMessage.textContent = "Unable to connect to the server. Please try again.";
            loginMessage.hidden = false;
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    });
}

const registerForm = document.getElementById("registerForm");
const registerMessage = document.getElementById("registerMessage");

if (registerForm && registerMessage) {
    registerForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        registerMessage.hidden = true;
        registerMessage.classList.remove("is-success");

        const submitButton = registerForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch("/register", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    name: document.getElementById("name").value,
                    collegeId: document.getElementById("collegeId").value,
                    email: document.getElementById("email").value,
                    password: document.getElementById("password").value
                })
            });
            const data = await response.json();

            registerMessage.textContent = data.message || (data.success ? "Account created." : "Account creation failed.");
            registerMessage.classList.toggle("is-success", response.ok && data.success);
            registerMessage.hidden = false;

            if (response.ok && data.success) {
                registerForm.reset();
            }
        } catch (error) {
            console.error("Registration failed:", error);
            registerMessage.textContent = "Unable to connect to the server. Please try again.";
            registerMessage.hidden = false;
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    });
}
