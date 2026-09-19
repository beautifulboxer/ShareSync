const loginForm = document.getElementById("loginForm");
const passwordInput = document.getElementById("password");
const passwordToggle = document.getElementById("passwordToggle");

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

        if (data.success) {
            alert(data.message);
        } else {
            alert(data.message);
        }
    } catch (error) {
        alert("Unable to connect to the server.");
        console.error(error);
    }
});