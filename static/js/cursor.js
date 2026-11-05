// The cursor paints the page: a trailing green ring, a green "cut" that turns
// the dark background Farmingdale green wherever it passes, gradient washes
// that shift as it crosses the screen, and a flashlight that brightens the
// hero's wall of course codes beneath it.
//
// Performance: the cut, ring and washes move only with transform and opacity,
// which composite without repainting. The flashlight is the one repaint, and
// it is confined to the hero's code wall.
//
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

  // ── The green ring ───────────────────────────────────────────────────────
  var ring = document.createElement("div");
  ring.className = "cursor-follower";
  ring.setAttribute("aria-hidden", "true");
  document.body.appendChild(ring);

  var ringX = gsap.quickTo(ring, "x", { duration: 0.8, ease: "power3.out" });
  var ringY = gsap.quickTo(ring, "y", { duration: 0.8, ease: "power3.out" });

  // ── The green cut ────────────────────────────────────────────────────────
  // A crisp green circle that trails the cursor. It blends with "screen", so
  // it turns the dark page green but leaves white text white. When you move
  // fast it stretches along the direction of travel, then rounds out again.
  var cut = document.createElement("div");
  cut.className = "cursor-cut";
  cut.setAttribute("aria-hidden", "true");
  var cutShape = document.createElement("div");
  cutShape.className = "cursor-cut-shape";
  cut.appendChild(cutShape);
  document.body.appendChild(cut);
  gsap.set(cut, { xPercent: -50, yPercent: -50, x: window.innerWidth / 2, y: window.innerHeight / 2 });

  var cutX = gsap.quickTo(cut, "x", { duration: 0.9, ease: "power3.out" });
  var cutY = gsap.quickTo(cut, "y", { duration: 0.9, ease: "power3.out" });
  var stretch = gsap.quickTo(cutShape, "scaleX", { duration: 0.5, ease: "power3.out" });
  var squash = gsap.quickTo(cutShape, "scaleY", { duration: 0.5, ease: "power3.out" });
  var turn = gsap.quickTo(cutShape, "rotation", { duration: 0.5, ease: "power3.out" });
  var last = { x: 0, y: 0, t: 0 };

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

    gsap.to(ring, { opacity: 1, duration: 0.6, overwrite: "auto" });
    ringX(x - 16);
    ringY(y - 16);

    gsap.to(cut, { opacity: 1, duration: 0.6, overwrite: "auto" });
    cutX(x);
    cutY(y);
    // Speed in px per ms decides the stretch; direction decides the angle.
    var now = event.timeStamp;
    var dt = Math.max(now - last.t, 1);
    var vx = (x - last.x) / dt;
    var vy = (y - last.y) / dt;
    var speed = Math.min(Math.hypot(vx, vy), 3);
    if (speed > 0.05) turn((Math.atan2(vy, vx) * 180) / Math.PI);
    stretch(1 + speed * 0.12);
    squash(1 - speed * 0.06);
    last = { x: x, y: y, t: now };
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
    gsap.to([ring, cut], { opacity: 0, duration: 0.6 });
  });

  // Ease the stretch back to a circle once the cursor stops.
  gsap.ticker.add(function () {
    if (performance.now() - last.t > 120) {
      stretch(1);
      squash(1);
    }
  });

  // ── Engage: anything you can act on pulls the light in ───────────────────
  document.querySelectorAll("a, button, .pillar, [data-rambo]").forEach(function (el) {
    var isRambo = el.hasAttribute("data-rambo");
    el.addEventListener("pointerenter", function () {
      ring.classList.add("is-engaged");
      gsap.to(ring, { scale: isRambo ? 2.6 : 1.8, duration: 0.6, ease: "power3.out" });
      gsap.to(cut, { scale: isRambo ? 1.5 : 1.25, duration: 0.8, ease: "power3.out" });
    });
    el.addEventListener("pointerleave", function () {
      ring.classList.remove("is-engaged");
      gsap.to(ring, { scale: 1, duration: 0.6, ease: "power3.out" });
      gsap.to(cut, { scale: 1, duration: 1, ease: "power3.out" });
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
