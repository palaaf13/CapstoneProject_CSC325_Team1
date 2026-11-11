// The cursor paints the page: a broad watercolor wash that drifts after it
// like silk, background gradients that change as it crosses the screen, and a
// flashlight that brightens the hero's wall of course codes beneath it.
//
// Performance: the watercolor and background move only with transform and
// opacity, which composite without repainting. Each wash's 8s cloudlike drift
// is a CSS animation, so it keeps moving while the mouse is still. The flashlight is the
// one repaint, and it is confined to the hero's code wall.
//
// Decorative only: nothing here takes clicks or hides the system cursor.
// Touch devices get a slow ambient drift instead. Reduced motion gets a still,
// centred background and none of this.
(function () {
  "use strict";

  if (!window.gsap) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var glow = document.querySelector("[data-spotlight-glow]");
  var washB = document.querySelector("[data-spotlight-wash-b]");
  if (!glow || !washB) return;

  gsap.set(glow, { xPercent: -50, yPercent: -50, x: window.innerWidth / 2, y: window.innerHeight / 2 });

  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  // ── Touch: nothing to follow, so the light drifts on its own ─────────────
  if (!finePointer) {
    gsap.to(glow, {
      x: window.innerWidth * 0.7,
      y: window.innerHeight * 0.35,
      duration: 9,
      ease: "sine.inOut",
      yoyo: true,
      repeat: -1,
    });
    gsap.to(washB, { opacity: 0.8, duration: 11, ease: "sine.inOut", yoyo: true, repeat: -1 });
    return;
  }

  // ── The watercolor ───────────────────────────────────────────────────────
  // Three soft pools of deep green. Each trails the mouse at its own pace (the
  // last is the laziest), so they stretch apart while it moves and settle
  // back together, overlapping, when it stops.
  var aura = document.createElement("div");
  aura.className = "cursor-aura";
  aura.setAttribute("aria-hidden", "true");
  var washes = [
    { name: "a", lag: 1.1, offset: [0, 0] },
    { name: "b", lag: 1.9, offset: [-48, 32] },
    { name: "c", lag: 2.8, offset: [56, -24] },
  ].map(function (spec) {
    var wash = document.createElement("div");
    wash.className = "cursor-wash cursor-wash-" + spec.name;
    var shape = document.createElement("div");
    shape.className = "cursor-wash-shape";
    wash.appendChild(shape);
    aura.appendChild(wash);
    gsap.set(wash, {
      xPercent: -50,
      yPercent: -50,
      x: window.innerWidth / 2 + spec.offset[0],
      y: window.innerHeight / 2 + spec.offset[1],
    });
    return {
      el: wash,
      offset: spec.offset,
      x: gsap.quickTo(wash, "x", { duration: spec.lag, ease: "sine.out" }),
      y: gsap.quickTo(wash, "y", { duration: spec.lag, ease: "sine.out" }),
    };
  });
  document.body.appendChild(aura);

  var washMix = gsap.quickTo(washB, "opacity", { duration: 2.4, ease: "power2.out" });

  // ── The flashlight over the hero's code wall ─────────────────────────────
  var wall = document.querySelector("[data-flashlight]");
  var light = { x: 50, y: 50, r: 0 };
  var paintWall = function () {
    wall.style.setProperty("--fx", light.x + "%");
    wall.style.setProperty("--fy", light.y + "%");
    wall.style.setProperty("--fr", light.r + "px");
  };

  window.addEventListener("pointermove", function (event) {
    var x = event.clientX;
    var y = event.clientY;

    gsap.to(aura, { opacity: 1, duration: 1.2, overwrite: "auto" });
    washes.forEach(function (wash) {
      wash.x(x + wash.offset[0]);
      wash.y(y + wash.offset[1]);
    });
    // Left edge shows the first gradient, right edge the second.
    washMix(Math.min(Math.max(x / window.innerWidth, 0), 1));

    if (wall) {
      var box = wall.getBoundingClientRect();
      var inside = y >= box.top && y <= box.bottom;
      gsap.to(light, {
        x: ((x - box.left) / box.width) * 100,
        y: ((y - box.top) / box.height) * 100,
        r: inside ? 260 : 0,
        duration: 1.2,
        ease: "power3.out",
        overwrite: "auto",
        onUpdate: paintWall,
      });
    }
  });

  document.addEventListener("pointerleave", function () {
    gsap.to(aura, { opacity: 0, duration: 1.2 });
  });

  // ── Engage: anything you can act on lets the colour bloom a little ──────
  var washEls = washes.map(function (wash) {
    return wash.el;
  });
  document.querySelectorAll("a, button, .pillar, [data-rambo]").forEach(function (el) {
    var isRambo = el.hasAttribute("data-rambo");
    el.addEventListener("pointerenter", function () {
      gsap.to(washEls, { scale: isRambo ? 1.2 : 1.08, duration: 1.4, ease: "sine.out" });
    });
    el.addEventListener("pointerleave", function () {
      gsap.to(washEls, { scale: 1, duration: 1.8, ease: "sine.out" });
    });
  });

  // ── Buttons lean gently toward the pointer ───────────────────────────────
  document.querySelectorAll("[data-magnetic]").forEach(function (el) {
    el.addEventListener("pointermove", function (event) {
      var box = el.getBoundingClientRect();
      gsap.to(el, {
        x: (event.clientX - box.left - box.width / 2) * 0.18,
        y: (event.clientY - box.top - box.height / 2) * 0.3,
        duration: 0.8,
        ease: "power3.out",
      });
    });
    el.addEventListener("pointerleave", function () {
      gsap.to(el, { x: 0, y: 0, duration: 1.2, ease: "elastic.out(1, 0.5)" });
    });
  });
})();
