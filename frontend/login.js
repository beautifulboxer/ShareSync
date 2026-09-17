const loginForm = document.getElementById("loginForm");
const passwordInput = document.getElementById("password");
const passwordToggle = document.getElementById("passwordToggle");

passwordToggle.addEventListener("click", function () {
   const isVisible = passwordInput.type === "text";
   passwordInput.type = isVisible ? "password" : "text";
   passwordToggle.setAttribute("aria-label", isVisible ? "Show password" : "Hide password");
   passwordToggle.setAttribute("title", isVisible ? "Show password" : "Hide password");
   passwordToggle.classList.toggle("is-visible", !isVisible);
});

loginForm.addEventListener("submit", function (event){
    event.preventDefault();
    const email=document.getElementById("email").value;
   const password=passwordInput.value;

     if (email=== ""|| password=== ""){
        alert("Enter email and password.");
        return;
     }
     alert("Welcome User!!")
});

