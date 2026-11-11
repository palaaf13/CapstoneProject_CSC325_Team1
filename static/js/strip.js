// The feature strip: seven cards that move sideways as you scroll down, each
// one passing through the centre of the screen in turn.
//
// Borrowed from the Agrumea Farm reference: off-centre cards fall out of focus
// (blur + dim + slight shrink) so the middle one reads as the subject.
//
// NOT borrowed: that site hijacks scrolling outright. Here the page scrolls
// normally — the section simply holds while the strip travels, then releases,
// and with JavaScript off or reduced motion on it stays a native horizontal
// scroller you can drag, tab or scrollbar through.
(function () {
  "use strict";

  var stage = document.querySelector("[data-strip]");
  if (!stage) return;

  var viewport = stage.querySelector("[data-strip-viewport]");
  var track = stage.querySelector("[data-strip-track]");
  var items = Array.prototype.slice.call(stage.querySelectorAll("[data-strip-item]"));
  if (!viewport || !track || !items.length) return;

  var hint = stage.querySelector("[data-strip-hint]");
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // No GSAP or reduced motion: leave the native scroller alone.
  if (!window.gsap || !window.ScrollTrigger || reducedMotion) {
    if (hint) hint.textContent = "Swipe or scroll sideways";
    return;
  }

  var setters = items.map(function (item) {
    return {
      blur: gsap.quickSetter(item, "filter"),
      opacity: gsap.quickSetter(item, "opacity"),
      scale: gsap.quickSetter(item, "scale"),
    };
  });

  // Depth of field: sharp in the middle, softer toward the edges. Distance is
  // normalised against half the viewport PLUS half a card, so a card that is
  // merely next in line is only gently softened rather than fully blurred.
  function focusCards() {
    var middle = viewport.getBoundingClientRect().left + viewport.offsetWidth / 2;
    var span = viewport.offsetWidth / 2 + items[0].offsetWidth / 2;
    items.forEach(function (item, i) {
      var box = item.getBoundingClientRect();
      var away = Math.min(Math.abs(box.left + box.width / 2 - middle) / span, 1);
      setters[i].blur("blur(" + (away * 3).toFixed(2) + "px)");
      setters[i].opacity(1 - away * 0.5);
      setters[i].scale(1 - away * 0.05);
    });
  }

  function clearFocus() {
    items.forEach(function (item, i) {
      setters[i].blur("none");
      setters[i].opacity(1);
      setters[i].scale(1);
    });
  }

  // The strip travels from the first card centred to the last card centred,
  // so every card, first and last included, passes through the middle.
  function centreOf(item) {
    var box = item.getBoundingClientRect();
    return box.left + box.width / 2 - track.getBoundingClientRect().left;
  }

  function startX() {
    return viewport.offsetWidth / 2 - centreOf(items[0]);
  }

  function endX() {
    return viewport.offsetWidth / 2 - centreOf(items[items.length - 1]);
  }

  function distance() {
    return Math.max(startX() - endX(), 0);
  }

  // The section holds for exactly as long as the strip travels.
  function fitStage() {
    stage.style.height = distance() + window.innerHeight + "px";
  }

  // Phones keep the native swipeable carousel: a pinned strip driven by
  // vertical scroll is worse than the horizontal swipe a touch user expects,
  // and at 375px a card is wider than half the screen, so nothing ever sits
  // centred and every card would stay blurred.
  gsap.matchMedia().add("(min-width: 768px)", function () {
    document.documentElement.classList.add("strip-pinned");

    fitStage();
    ScrollTrigger.addEventListener("refreshInit", fitStage);

    var drift = gsap.fromTo(
      track,
      { x: startX },
      {
        x: endX,
        ease: "none",
        // Focus is recalculated on the tween's own render, not ScrollTrigger's
        // onUpdate. With scrub, onUpdate fires on the scroll event while the
        // track is still ~1s behind, so the blur froze against a stale position
        // and left the wrong card sharp.
        onUpdate: focusCards,
        scrollTrigger: {
          trigger: stage,
          start: "top top",
          end: function () {
            return "+=" + distance();
          },
          scrub: 1.1,
          pin: ".strip-sticky",
          pinSpacing: false,
          anticipatePin: 1,
          invalidateOnRefresh: true,
          onRefresh: focusCards,
        },
      }
    );

    // While pinned, the strip's position comes from the transform, so the
    // container must never scroll itself. Browsers scroll a focused child into
    // view even when overflow is hidden, which silently offset the whole strip
    // by up to its full width; undo that the moment it happens.
    viewport.addEventListener("scroll", function () {
      if (viewport.scrollLeft !== 0) viewport.scrollLeft = 0;
    });

    // Keyboard: tabbing to an off-screen card scrolls the *page* to it, since
    // that is what moves the strip. Without this, focus lands somewhere
    // invisible. Run on the next frame so it wins the race against the
    // browser's own scroll-into-view.
    items.forEach(function (item, index) {
      item.querySelector("a").addEventListener("focus", function () {
        var st = drift.scrollTrigger;
        if (!st) return;
        var progress = items.length > 1 ? index / (items.length - 1) : 0;
        var target = st.start + (st.end - st.start) * progress;
        requestAnimationFrame(function () {
          viewport.scrollLeft = 0;
          if (Math.abs(window.scrollY - target) < 8) return;
          if (window.__ramhubLenis) {
            window.__ramhubLenis.scrollTo(target, { duration: 1.1, force: true, lock: true });
          } else {
            window.scrollTo({ top: target, behavior: "smooth" });
          }
        });
      });
    });

    focusCards();

    // matchMedia cleanup: below 768px everything above is reverted.
    return function () {
      document.documentElement.classList.remove("strip-pinned");
      ScrollTrigger.removeEventListener("refreshInit", fitStage);
      stage.style.height = "";
      gsap.set(track, { x: 0 });
      clearFocus();
    };
  });

  window.addEventListener("resize", function () {
    ScrollTrigger.refresh();
  });
})();
