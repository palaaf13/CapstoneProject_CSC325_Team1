// The cursor paints the page: a soft green aura that trails it and keeps
// shifting, gradient washes that change as it crosses the screen, and a
// flashlight that brightens the hero's wall of course codes beneath it.
//
// Performance: the aura and washes move only with transform and opacity, which
// composite without repainting. The aura's 8s gradient shift is a CSS
// animation, so it runs even while the mouse is still. The flashlight is the
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

  // ── The aura ─────────────────────────────────────────────────────────────
  var aura = document.createElement("div");
  aura.className = "cursor-aura";
  aura.setAttribute("aria-hidden", "true");
  ["a", "b"].forEach(function (name) {
    var layer = document.createElement("div");
    layer.className = "cursor-aura-layer cursor-aura-layer-" + name;
    aura.appendChild(layer);
  });
  document.body.appendChild(aura);
  gsap.set(aura, { xPercent: -50, yPercent: -50, x: window.innerWidth / 2, y: window.innerHeight / 2 });

  var auraX = gsap.quickTo(aura, "x", { duration: 0.9, ease: "power3.out" });
  var auraY = gsap.quickTo(aura, "y", { duration: 0.9, ease: "power3.out" });

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

    gsap.to(aura, { opacity: 1, duration: 0.6, overwrite: "auto" });
    auraX(x);
    auraY(y);
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
    gsap.to(aura, { opacity: 0, duration: 0.6 });
  });

  // ── Engage: anything you can act on draws the aura in a little ─────────
  document.querySelectorAll("a, button, .pillar, [data-rambo]").forEach(function (el) {
    var isRambo = el.hasAttribute("data-rambo");
    el.addEventListener("pointerenter", function () {
      gsap.to(aura, { scale: isRambo ? 1.3 : 1.12, duration: 0.8, ease: "power3.out" });
    });
    el.addEventListener("pointerleave", function () {
      gsap.to(aura, { scale: 1, duration: 1, ease: "power3.out" });
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
