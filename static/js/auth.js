(function () {
  async function postJSON(url, data) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json().then((j) => ({ ok: res.ok, data: j }));
  }

  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      console.log("Login form submitted!");

      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;
      const data = { email, password };

      const flash = document.getElementById("flash");
      if (flash) flash.textContent = "Logging in...";

      try {
        const r = await postJSON("/api/auth/login", data);
        console.log("Login response:", r);

        if (!r.ok) {
          if (flash) flash.textContent = r.data.msg || "Login failed";
          console.error("Login failed:", r.data);
          return;
        }

        const token = r.data.access_token || r.data.token;
        if (!token) {
          if (flash) flash.textContent = "No token received from server";
          console.error("No token in login response:", r.data);
          return;
        }

        // Store token under multiple keys so other pages find it immediately
        localStorage.setItem("tv_token", token);
        localStorage.setItem("token", token);
        localStorage.setItem("access_token", token);

        // optional: set a cookie (short-lived) to help some flows (path=/)
        try {
          document.cookie = "tv_token=" + encodeURIComponent(token) + ";path=/";
        } catch (e) {}

        if (flash) flash.textContent = "Login successful, redirecting...";
        // redirect to dashboard
        window.location.replace("/dashboard");

      } catch (error) {
        if (flash) flash.textContent = "Network error. Please try again.";
        console.error("Login error:", error);
      }
    });
  }

  const regForm = document.getElementById("registerForm");
  if (regForm) {
    regForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("name").value;
      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;
      
      const flash = document.getElementById("flash");
      if (flash) flash.textContent = "Registering...";

      try {
        const r = await postJSON("/api/auth/register", { name, email, password });
        
        if (!r.ok) {
          if (flash) flash.textContent = r.data.msg || "Registration failed";
          return;
        }
        
        if (flash) flash.textContent = "Success! Redirecting to login...";
        setTimeout(() => {
          window.location.replace("/login");
        }, 500);
      } catch (error) {
        if (flash) flash.textContent = "Network error. Please try again.";
        console.error("Registration error:", error);
      }
    });
  }

  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      const token = localStorage.getItem("tv_token") || localStorage.getItem("token");
      if (token) {
        try {
          await fetch("/api/auth/logout", {
            method: "POST",
            headers: { Authorization: "Bearer " + token },
          });
        } catch (error) {
          console.error("Logout error:", error);
        }
        localStorage.removeItem("tv_token");
        localStorage.removeItem("token");
        localStorage.removeItem("access_token");
      }
      // clear cookie copies
      try {
        document.cookie = "tv_token=;max-age=0;path=/";
        document.cookie = "token=;max-age=0;path=/";
      } catch (e) {}
      window.location.replace("/login");
    });
  }
})();