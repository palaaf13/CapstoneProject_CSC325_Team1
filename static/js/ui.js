// Small bits of behaviour that HTMX is not the right tool for.
// Anything that talks to the server should be an HTMX attribute instead.
(function () {
  "use strict";

  // Mobile navigation toggle.
  var toggle = document.querySelector("[data-menu-toggle]");
  var menu = document.getElementById("mobile-menu");
  if (!toggle || !menu) return;

  var iconOpen = toggle.querySelector("[data-menu-icon-open]");
  var iconClose = toggle.querySelector("[data-menu-icon-close]");

  function setOpen(open) {
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (iconOpen) iconOpen.hidden = open;
    if (iconClose) iconClose.hidden = !open;
  }

  toggle.addEventListener("click", function () {
    setOpen(menu.hidden);
  });

  // Escape closes the menu and returns focus to the toggle.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !menu.hidden) {
      setOpen(false);
      toggle.focus();
    }
  });

  // Reset state if the viewport grows past the mobile breakpoint.
  window.matchMedia("(min-width: 768px)").addEventListener("change", function (event) {
    if (event.matches) setOpen(false);
  });
})();

// Club directory: two places where the page has to be scrolled for you.
(function () {
  "use strict";

  // 1. On a phone the categories are a sideways row of chips. Arriving with a
  //    category already chosen — a shared link, the back button — its chip can
  //    be off the right edge, and nothing on screen says which filter is on.
  //    Centre it. Only the row itself moves, never the page.
  function revealSelectedCategory() {
    var checked = document.querySelector(".club-filter-input:checked");
    var list = checked && checked.closest(".club-filter-list");
    if (!list || list.scrollWidth <= list.clientWidth) return;

    var chip = checked.parentElement.getBoundingClientRect();
    var row = list.getBoundingClientRect();
    list.scrollLeft += chip.left - row.left - (row.width - chip.width) / 2;
  }

  revealSelectedCategory();

  // htmx re-runs this file when it restores a page from history; the listeners
  // below must only be added once.
  if (window.ramhubClubDirectory) return;
  window.ramhubClubDirectory = true;

  document.addEventListener("htmx:historyRestore", revealSelectedCategory);

  // 2. The category rail is sticky, so a category can be picked from deep in a
  //    long list. The new list is shorter, and without this you are left
  //    looking at its last row or the footer. It only ever scrolls up, and only
  //    when the top of the results has gone above the header — typing in the
  //    search box on a phone, where the results sit below the box, never moves
  //    the page. "Load more" swaps a list item, not #club-results, so it is
  //    left alone.
  document.addEventListener("htmx:afterSwap", function (event) {
    if (!event.detail.target || event.detail.target.id !== "club-results") return;

    var results = document.getElementById("club-results");
    var header = document.querySelector("header");
    if (!results) return;

    // .club-results sets scroll-margin-top, so this stops clear of the header.
    if (results.getBoundingClientRect().top < (header ? header.offsetHeight : 0)) {
      results.scrollIntoView({ block: "start" });
    }
  });
})();
