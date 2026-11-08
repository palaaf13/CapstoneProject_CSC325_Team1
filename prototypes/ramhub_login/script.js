// RamHub frontend account-screen prototype.
// No account information or passwords are sent to a server or saved locally.
document.addEventListener('DOMContentLoaded', () => {
  const views = {
    login: document.getElementById('view-login'),
    signup: document.getElementById('view-signup'),
    reset: document.getElementById('view-reset')
  };
  const info = document.getElementById('rh-info');

  function message(text) {
    info.textContent = text;
    info.hidden = false;
  }

  function changeView(viewName) {
    if (!views[viewName]) return;
    for (const [name, element] of Object.entries(views)) {
      element.hidden = name !== viewName;
    }
    // Clear passwords when moving between screens.
    document.querySelectorAll('input[type="password"], input[data-was-password]').forEach(field => {
      field.value = '';
      field.type = 'password';
      field.removeAttribute('data-was-password');
    });
    document.querySelectorAll('[data-toggle-password]').forEach(button => {
      button.setAttribute('aria-label', 'Show password');
      button.setAttribute('aria-pressed', 'false');
    });
    info.hidden = true;
    info.textContent = '';
  }

  document.querySelectorAll('[data-view]').forEach(button => {
    button.addEventListener('click', () => changeView(button.dataset.view));
  });

  document.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const field = document.getElementById(button.dataset.togglePassword);
      const isVisible = field.type === 'password';
      field.type = isVisible ? 'text' : 'password';
      if (isVisible) field.setAttribute('data-was-password', 'true');
      else field.removeAttribute('data-was-password');
      button.setAttribute('aria-label', isVisible ? 'Hide password' : 'Show password');
      button.setAttribute('aria-pressed', String(isVisible));
    });
  });

  function validCampusEmail(field) {
    const valid = field.value.trim().toLowerCase().endsWith('@farmingdale.edu');
    field.setCustomValidity(valid ? '' : 'Please use your @farmingdale.edu email address.');
    field.reportValidity();
    return valid;
  }

  document.querySelectorAll('input[type="email"]').forEach(field => {
    field.addEventListener('input', () => field.setCustomValidity(''));
  });

  document.getElementById('form-login').addEventListener('submit', event => {
    event.preventDefault();
    if (!validCampusEmail(document.getElementById('login-email'))) return;
    document.getElementById('login-password').value = '';
    message('Sign In is a preview. Your details were not submitted. Django authentication must be connected first.');
  });

  document.getElementById('form-signup').addEventListener('submit', event => {
    event.preventDefault();
    if (!validCampusEmail(document.getElementById('signup-email'))) return;
    const password = document.getElementById('signup-password');
    const confirm = document.getElementById('signup-confirm');
    if (password.value !== confirm.value) {
      confirm.setCustomValidity('Passwords do not match.');
      confirm.reportValidity();
      return;
    }
    password.value = '';
    confirm.value = '';
    message('Account setup preview complete. No account was created or saved. Django, secure password hashing, MongoDB configuration, and email verification must be connected first.');
  });
  document.getElementById('signup-confirm').addEventListener('input', event => {
    event.target.setCustomValidity('');
  });

  document.getElementById('form-reset').addEventListener('submit', event => {
    event.preventDefault();
    if (!validCampusEmail(document.getElementById('reset-email'))) return;
    message('Password reset is a preview. No email was sent. The Django password-reset service must be connected first.');
  });

  // Type and erase questions in the panel, preserving the original animation.
  const prompts = [
    "✨ What's the vibe on campus today?",
    "📅 What's happening around FSC this week?",
    "📚 Any underrated study spots on campus?",
    "🎓 Which professor should I take for CSC 325?",
    "🚗 Is parking a nightmare today?",
    "🎭 Which FSC clubs are worth joining?",
    "⭐ What do students think of this course?",
    "💡 Any tips for next semester?"
  ];
  const typedText = document.getElementById('rh-type-text');
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    typedText.textContent = prompts[0];
  } else {
    let promptIndex = 0;
    let count = 0;
    let deleting = false;
    function typeNext() {
      const chars = Array.from(prompts[promptIndex]);
      count += deleting ? -1 : 1;
      typedText.textContent = chars.slice(0, count).join('');
      if (!deleting && count === chars.length) {
        deleting = true;
        setTimeout(typeNext, 1900);
      } else if (deleting && count === 0) {
        deleting = false;
        promptIndex = (promptIndex + 1) % prompts.length;
        setTimeout(typeNext, 350);
      } else {
        setTimeout(typeNext, deleting ? 25 : 55);
      }
    }
    setTimeout(typeNext, 450);
  }
});
