/* General UI helpers: sidebar, confirmations, flash auto-dismiss. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // Sidebar toggle (mobile)
    var toggle = document.querySelector(".sidebar-toggle");
    var sidebar = document.querySelector(".sidebar");
    var backdrop = document.querySelector(".sidebar-backdrop");
    if (toggle && sidebar) {
      toggle.addEventListener("click", function () {
        sidebar.classList.toggle("open");
        if (backdrop) backdrop.classList.toggle("show");
      });
    }
    if (backdrop) {
      backdrop.addEventListener("click", function () {
        sidebar.classList.remove("open");
        backdrop.classList.remove("show");
      });
    }

    // Confirm before destructive actions: add data-confirm="message"
    document.querySelectorAll("[data-confirm]").forEach(function (el) {
      el.addEventListener("click", function (event) {
        if (!window.confirm(el.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });

    // Auto-dismiss flash messages
    document.querySelectorAll(".flash-stack .alert").forEach(function (alert) {
      window.setTimeout(function () {
        alert.style.transition = "opacity .4s ease, transform .4s ease";
        alert.style.opacity = "0";
        alert.style.transform = "translateY(-6px)";
        window.setTimeout(function () { alert.remove(); }, 420);
      }, 5000);
    });
  });

  // CSRF-aware JSON POST helper used across the app.
  window.apiPost = function (url, payload) {
    var token = document.querySelector('meta[name="csrf-token"]');
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": token ? token.getAttribute("content") : "",
      },
      body: JSON.stringify(payload || {}),
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
    });
  };
})();
