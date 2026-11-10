// Account pages: show/hide password buttons and the typing line.
// Adapted from Sara's prototype (prototypes/ramhub_login/script.js). The forms
// themselves are plain Django forms and submit normally.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    const field = document.getElementById(button.dataset.togglePassword);
    if (!field) return;
    button.hidden = false;
    button.addEventListener("click", () => {
      const show = field.type === "password";
      field.type = show ? "text" : "password";
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.setAttribute("aria-pressed", String(show));
    });
  });

  // Never submit with a password still showing as plain text, so the browser
  // treats it as a password (and offers to save it).
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      form.querySelectorAll("[data-toggle-password]").forEach((button) => {
        const field = document.getElementById(button.dataset.togglePassword);
        if (field) field.type = "password";
      });
    });
  });

  const typed = document.querySelector("[data-type-text]");
  if (!typed) return;
  const prompts = [
    "✨ What's the vibe on campus today?",
    "📅 What's happening around FSC this week?",
    "📚 Any underrated study spots on campus?",
    "🎓 Which professor should I take for CSC 325?",
    "🚗 Is parking a nightmare today?",
    "🎭 Which FSC clubs are worth joining?",
    "⭐ What do students think of this course?",
    "💡 Any tips for next semester?",
  ];
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    typed.textContent = prompts[0];
    return;
  }
  let index = 0;
  let count = 0;
  let deleting = false;
  function typeNext() {
    const chars = Array.from(prompts[index]);
    count += deleting ? -1 : 1;
    typed.textContent = chars.slice(0, count).join("");
    if (!deleting && count === chars.length) {
      deleting = true;
      setTimeout(typeNext, 1900);
    } else if (deleting && count === 0) {
      deleting = false;
      index = (index + 1) % prompts.length;
      setTimeout(typeNext, 350);
    } else {
      setTimeout(typeNext, deleting ? 25 : 55);
    }
  }
  setTimeout(typeNext, 450);
});
