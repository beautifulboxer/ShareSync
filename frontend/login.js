const loginForm = document.getElementById("loginForm");
const passwordInput = document.getElementById("password");
const passwordToggle = document.getElementById("passwordToggle");

if (passwordToggle && passwordInput) {
    passwordToggle.addEventListener("click", function () {
        const isVisible = passwordInput.type === "text";
        passwordInput.type = isVisible ? "password" : "text";
        passwordToggle.setAttribute("aria-label", isVisible ? "Show password" : "Hide password");
        passwordToggle.setAttribute("title", isVisible ? "Show password" : "Hide password");
        passwordToggle.classList.toggle("is-visible", !isVisible);
    });
}

if (loginForm) {
    loginForm.addEventListener("submit", function (event) {
        event.preventDefault();

        const email = document.getElementById("email").value;
        const password = passwordInput ? passwordInput.value : "";

        if (email === "" || password === "") {
            alert("Enter email and password.");
            return;
        }

        alert("Welcome User!!");
    });
}

const registerForm = document.getElementById("registerForm");
if (registerForm) {
    registerForm.addEventListener("submit", function (event) {
        event.preventDefault();

        const name = document.getElementById("name").value;
        const collegeId = document.getElementById("collegeId").value;
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;

        if (name === "" || collegeId === "" || 
         email === "" || 
         password === "") {
            alert("Please fill all fields");
            return;
        }

        alert("Registered Successfully!! Wait for Admin's Approval..");
    });
}