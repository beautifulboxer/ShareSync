const loginForm = document.getElementById("loginForm");
const passwordInput = document.getElementById("password");
const passwordToggle = document.getElementById("passwordToggle");

if (passwordToggle && passwordInput) {
    passwordToggle.addEventListener("click", function () {
        const isVisible = passwordInput.type === "text";

        passwordInput.type = isVisible ? "password" : "text";

        passwordToggle.setAttribute(
            "aria-label",
            isVisible ? "Show password" : "Hide password"
        );

        passwordToggle.setAttribute(
            "title",
            isVisible ? "Show password" : "Hide password"
        );

        passwordToggle.classList.toggle("is-visible", !isVisible);
    });
}

if (loginForm) {
    loginForm.addEventListener("submit", async function (event) {
        event.preventDefault();

        const email = document.getElementById("email").value.trim();
        const password = passwordInput.value;

        if (email === "" || password === "") {
            alert("Enter email and password.");
            return;
        }

        try {
            const response = await fetch("/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    email: email,
                    password: password
                })
            });

            const data = await response.json();

            alert(data.message);

        } catch (error) {
            console.error(error);
            alert("Unable to connect to the server.");
        }
    });
}


const registerForm = document.getElementById("registerForm");

if (registerForm) {
    registerForm.addEventListener("submit", async function (event) {
        event.preventDefault();

        const name = document.getElementById("name").value.trim();
        const collegeId = document.getElementById("collegeId").value.trim();
        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;

        if (
            name === "" ||
            collegeId === "" ||
            email === "" ||
            password === ""
        ) {
            alert("Please fill all fields.");
            return;
        }

        try {
            const response = await fetch("/register", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    name: name,
                    collegeId: collegeId,
                    email: email,
                    password: password
                })
            });

            const data = await response.json();

            alert(data.message);

            if (data.success) {
                registerForm.reset();
            }

        } catch (error) {
            console.error(error);
            alert("Unable to connect to the server.");
        }
    });
}