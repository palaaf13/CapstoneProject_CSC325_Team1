// The cursor paints the starry frame behind every page but the landing page,
// the way it paints the landing page (static/js/cursor.js):
//
//   * the background crossfades between two gradients as the cursor moves
//     from the left edge of the screen to the right;
//   * a soft green glow follows the cursor;
//   * three watercolor pools trail it at different speeds, so they stretch
//     apart while it moves and settle back together when it stops.
//
// All of it lives in the fixed backdrop behind the page's content sheet, so
// only the starry sides change and the text never gets tinted. Plain
// JavaScript (no animation library), and it only moves transform and opacity.
// The loop sleeps once everything has caught up with the cursor.
//
// Decorative: it takes no clicks and never hides the cursor. Touch screens get
// a slow drift from CSS instead; reduced motion gets none of this.
(function () {
  "use strict";

  var frame = document.querySelector(".frame .star-frame");
  if (!frame) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var glow = frame.querySelector("[data-frame-glow]");
  var washB = frame.querySelector("[data-frame-wash-b]");
  var aura = frame.querySelector("[data-frame-aura]");
  if (!glow || !washB || !aura) return;

  if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    frame.classList.add("is-drifting");
    return;
  }

  // Each follower eases toward the cursor with its own lag in seconds, like
  // the landing page's (1.1s, 1.9s, 2.8s for the pools; the glow is quicker).
  function follower(el, lag, offsetX, offsetY) {
    return { el: el, lag: lag, ox: offsetX, oy: offsetY, x: innerWidth / 2, y: innerHeight / 2 };
  }

  var followers = [follower(glow, 0.9, 0, 0)];
  [
    { name: "a", lag: 1.1, offset: [0, 0] },
    { name: "b", lag: 1.9, offset: [-48, 32] },
    { name: "c", lag: 2.8, offset: [56, -24] },
  ].forEach(function (spec) {
    var wash = document.createElement("div");
    wash.className = "cursor-wash cursor-wash-" + spec.name;
    var shape = document.createElement("div");
    shape.className = "cursor-wash-shape";
    wash.appendChild(shape);
    aura.appendChild(wash);
    followers.push(follower(wash, spec.lag, spec.offset[0], spec.offset[1]));
  });

  var target = { x: innerWidth / 2, y: innerHeight / 2 };
  var mix = { now: 0, to: 0 };
  var running = false;
  var last = 0;

  function place(f) {
    f.el.style.transform =
      "translate3d(" + f.x.toFixed(1) + "px," + f.y.toFixed(1) + "px,0) translate(-50%,-50%)";
  }
  followers.forEach(place);

  function frameStep(time) {
    var dt = last ? Math.min((time - last) / 1000, 0.1) : 0.016;
    last = time;
    var moving = false;

    followers.forEach(function (f) {
      var k = 1 - Math.exp(-dt / (f.lag / 3));
      var tx = target.x + f.ox;
      var ty = target.y + f.oy;
      f.x += (tx - f.x) * k;
      f.y += (ty - f.y) * k;
      if (Math.abs(tx - f.x) > 0.5 || Math.abs(ty - f.y) > 0.5) moving = true;
      place(f);
    });

    // Left edge shows the first gradient, right edge the second.
    mix.now += (mix.to - mix.now) * (1 - Math.exp(-dt / 0.8));
    washB.style.opacity = mix.now.toFixed(3);
    if (Math.abs(mix.to - mix.now) > 0.002) moving = true;

    if (moving && !document.hidden) {
      requestAnimationFrame(frameStep);
    } else {
      running = false;
      last = 0;
    }
  }

  function wake() {
    if (!running) {
      running = true;
      requestAnimationFrame(frameStep);
    }
  }

  window.addEventListener(
    "pointermove",
    function (event) {
      target.x = event.clientX;
      target.y = event.clientY;
      mix.to = Math.min(Math.max(event.clientX / innerWidth, 0), 1);
      aura.classList.add("is-active");
      wake();
    },
    { passive: true },
  );

  document.documentElement.addEventListener("pointerleave", function () {
    aura.classList.remove("is-active");
  });
})();
