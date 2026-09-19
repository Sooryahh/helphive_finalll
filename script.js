document.addEventListener("DOMContentLoaded", function () {
    // Mobile navigation
    const navbar = document.querySelector(".navbar");
    const menuButton = document.querySelector(".mobile-menu");

    if (navbar && menuButton) {
        menuButton.addEventListener("click", function () {
            const open = navbar.classList.toggle("nav-open");
            menuButton.setAttribute("aria-expanded", open ? "true" : "false");
        });
    }

    // Auto-dismiss flash messages + manual close
    document.querySelectorAll(".flash").forEach(function (el) {
        const close = document.createElement("button");
        close.className = "flash-close";
        close.type = "button";
        close.setAttribute("aria-label", "Close message");
        close.textContent = "×";
        close.addEventListener("click", function () {
            el.classList.add("hide");
        });
        el.appendChild(close);

        setTimeout(function () {
            el.classList.add("hide");
        }, 4500);
    });

    // Reveal cards while scrolling
    const revealItems = document.querySelectorAll(".card, .feature, .detail-card, .form-card");
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver(
            function (entries, obs) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("visible");
                        obs.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.08 }
        );

        revealItems.forEach(function (item) {
            item.classList.add("reveal");
            observer.observe(item);
        });
    }

    // Password visibility toggle
    document.querySelectorAll('input[type="password"]').forEach(function (input) {
        const wrapper = document.createElement("div");
        wrapper.className = "password-field";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "password-toggle";
        toggle.textContent = "Show";
        toggle.addEventListener("click", function () {
            const visible = input.type === "text";
            input.type = visible ? "password" : "text";
            toggle.textContent = visible ? "Show" : "Hide";
        });

        wrapper.appendChild(toggle);
    });

    // Prevent accidental double submission
    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (form.dataset.confirmedSubmit === "1") {
                return;
            }

            const submit = form.querySelector(
                'button[type="submit"], button:not([type])'
            );

            if (submit && !submit.classList.contains("allow-multiple")) {
                setTimeout(function () {
                    submit.disabled = true;
                    submit.style.opacity = "0.7";
                    submit.textContent = "Processing...";
                }, 0);
            }
        });
    });

    // Simple ripple feedback for buttons
    document.querySelectorAll(".button, .nav-button, .small-button").forEach(function (button) {
        button.addEventListener("click", function () {
            button.animate(
                [
                    { transform: "scale(1)" },
                    { transform: "scale(.97)" },
                    { transform: "scale(1)" }
                ],
                { duration: 160 }
            );
        });
    });
});
