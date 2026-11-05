// The landing page's opening scene: about 50,000 graduation caps in a slowly
// turning spiral galaxy in RamHub green: soft mint at the core shading to
// Farmingdale green at the rim, with graduation caps streaking across the sky.
//
//   * Drag to rotate. Pinch (or Ctrl + scroll) to zoom. A plain scroll wheel
//     is left alone, so the page always scrolls past the hero.
//   * On phones, one finger scrolls the page and two fingers rotate and zoom.
//   * The galaxy leans toward the cursor, so near caps sweep further than far
//     ones, and caps part gently around it, trailing a little behind.
//   * Scrolling flies the camera into the galaxy, then hands over to the
//     existing hero. Reduced motion keeps a still galaxy you can still drag.
//   * Drawing stops while the galaxy is off screen or the tab is hidden.
//   * No WebGL, a blocked CDN, or no JavaScript: the CSS fallback glow and the
//     headline still render, so nothing on the page depends on this file.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const stage = document.querySelector("[data-galaxy]");
const mount = stage && stage.querySelector("[data-galaxy-canvas]");

// Colours from the design tokens in static/src/input.css.
const CORE = new THREE.Color("#a3d7b8"); // --color-accent-200
const RIM = new THREE.Color("#3f9e6d"); // --color-accent-400
const BACKGROUND = 0x0d0f12; // --color-neutral-950, the landing page background
const STREAK = new THREE.Color("#d0ebda"); // --color-accent-100
const SHAPE = { radius: 6, arms: 4, spin: 1.05, scatter: 0.38, scatterPower: 3 };
// Sit the core below the headline, like a horizon, so the text stays clear.
const GALAXY_Y = -1.9;


// A white mortarboard on a soft glow. The shader tints it per particle.
function capTexture() {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const g = canvas.getContext("2d");

  const glow = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  glow.addColorStop(0, "rgba(255,255,255,0.32)");
  glow.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = glow;
  g.fillRect(0, 0, size, size);

  // Cap base, drawn first and dimmer so the board reads on top of it.
  g.fillStyle = "rgba(255,255,255,0.72)";
  g.beginPath();
  g.moveTo(38, 62);
  g.lineTo(38, 84);
  g.quadraticCurveTo(64, 99, 90, 84);
  g.lineTo(90, 62);
  g.closePath();
  g.fill();

  // The board: a flat diamond seen from slightly above.
  g.fillStyle = "#ffffff";
  g.beginPath();
  g.moveTo(64, 28);
  g.lineTo(114, 50);
  g.lineTo(64, 72);
  g.lineTo(14, 50);
  g.closePath();
  g.fill();

  // Tassel.
  g.strokeStyle = "#ffffff";
  g.lineWidth = 4;
  g.lineCap = "round";
  g.beginPath();
  g.moveTo(64, 50);
  g.lineTo(100, 58);
  g.lineTo(100, 86);
  g.stroke();
  g.fillRect(96, 84, 8, 14);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function buildGalaxy(count) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const scales = new Float32Array(count);
  const angles = new Float32Array(count);
  const color = new THREE.Color();
  const jitter = (r) =>
    Math.pow(Math.random(), SHAPE.scatterPower) * (Math.random() < 0.5 ? 1 : -1) * SHAPE.scatter * r;

  for (let i = 0; i < count; i++) {
    // Denser toward the core, like a real galaxy.
    const r = Math.pow(Math.random(), 1.35) * SHAPE.radius;
    const arm = ((i % SHAPE.arms) / SHAPE.arms) * Math.PI * 2;
    const twist = r * SHAPE.spin;

    positions[i * 3] = Math.cos(arm + twist) * r + jitter(r);
    positions[i * 3 + 1] = jitter(r) * 0.55;
    positions[i * 3 + 2] = Math.sin(arm + twist) * r + jitter(r);

    color.copy(CORE).lerp(RIM, Math.min(1, r / SHAPE.radius));
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    // A handful of big caps so the shape is recognisable before you zoom.
    scales[i] = (0.55 + Math.random() * 1.05) * (Math.random() < 0.004 ? 2.6 : 1);
    angles[i] = Math.random() * Math.PI * 2;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute("aScale", new THREE.BufferAttribute(scales, 1));
  geometry.setAttribute("aAngle", new THREE.BufferAttribute(angles, 1));
  return geometry;
}

const vertexShader = /* glsl */ `
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uTime;
  uniform vec3 uPointer;        // cursor position, in the galaxy's own space
  uniform float uPointerForce;  // 0 when the cursor is away, eased up to 1
  attribute float aScale;
  attribute float aAngle;
  varying vec3 vColor;
  varying float vAngle;

  void main() {
    // Caps near the cursor are pushed outward and lifted a little, so the
    // galaxy parts around it. The push fades smoothly to nothing at the edge.
    vec3 p = position;
    vec2 away = p.xz - uPointer.xz;
    float reach = length(away);
    float influence = (1.0 - smoothstep(0.0, 1.1, reach)) * uPointerForce;
    p.xz += normalize(away + 1e-4) * influence * 0.55;
    p.y += influence * 0.18;

    vec4 viewPosition = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * viewPosition;
    gl_PointSize = min(uSize * aScale * uPixelRatio / -viewPosition.z, 96.0);
    vColor = color * (1.0 + influence * 0.5); // a little brighter where the cursor is
    // Each cap rocks gently around its own tilt.
    vAngle = aAngle + sin(uTime * 0.7 + aAngle * 5.0) * 0.22;
  }
`;

const fragmentShader = /* glsl */ `
  uniform sampler2D uMap;
  varying vec3 vColor;
  varying float vAngle;

  void main() {
    vec2 p = gl_PointCoord - 0.5;
    float c = cos(vAngle);
    float s = sin(vAngle);
    vec2 uv = mat2(c, -s, s, c) * p + 0.5;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;
    vec4 cap = texture2D(uMap, uv);
    if (cap.a < 0.02) discard;
    // Dimmed so thousands of overlapping caps add up to colour, not white.
    gl_FragColor = vec4(vColor * cap.rgb * 0.85, cap.a);
    #include <colorspace_fragment>
  }
`;

// ── Shooting caps ──────────────────────────────────────────────────────────
// Caps that streak across the sky with a fading tail, at different depths,
// sizes, and speeds; now and then a small shower of several at once. They live
// in the camera's own space, so they always cross the screen however you orbit.
function createShootingCaps(camera, texture) {
  const group = new THREE.Group();
  camera.add(group);

  const trailMaterial = () =>
    new THREE.ShaderMaterial({
      uniforms: { uColor: { value: STREAK }, uOpacity: { value: 0 } },
      vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: /* glsl */ `
        uniform vec3 uColor;
        uniform float uOpacity;
        varying vec2 vUv;
        void main() {
          // Bright at the head (right end), thinning and fading toward the tail.
          float along = pow(vUv.x, 2.2);
          float across = 1.0 - abs(vUv.y - 0.5) * 2.0;
          gl_FragColor = vec4(uColor, along * across * uOpacity * 0.8);
          #include <colorspace_fragment>
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

  const pool = Array.from({ length: 12 }, () => {
    const head = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: texture,
        color: STREAK,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        opacity: 0,
      })
    );
    const trail = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), trailMaterial());
    group.add(head, trail);
    return {
      head, trail, life: 0, duration: 0, active: false,
      x: 0, y: 0, dx: 0, dy: 0, length: 0, depth: 14, spin: 5,
    };
  });

  let wait = 0.8;

  function launch(cap, shower) {
    // Farther caps are smaller and slower, which gives the sky some depth.
    cap.depth = 10 + Math.random() * 12;
    const near = 1 - (cap.depth - 10) / 12;
    const halfHeight = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * cap.depth;
    const halfWidth = halfHeight * camera.aspect;
    const fromLeft = shower ? shower.fromLeft : Math.random() < 0.5;
    const angle = THREE.MathUtils.degToRad((shower ? shower.angle : 12 + Math.random() * 30) + (Math.random() - 0.5) * 6);
    const speed = (9 + near * 9) * (0.85 + Math.random() * 0.3);
    cap.x = (fromLeft ? -1 : 1) * halfWidth * (0.3 + Math.random() * 0.8);
    cap.y = halfHeight * (0.05 + Math.random() * 0.9);
    cap.dx = (fromLeft ? 1 : -1) * Math.cos(angle) * speed;
    cap.dy = -Math.sin(angle) * speed;
    cap.length = (1.8 + Math.random() * 2) * (0.6 + near * 0.6);
    cap.duration = 1 + Math.random() * 0.8;
    cap.spin = (Math.random() < 0.5 ? -1 : 1) * (3 + Math.random() * 5);
    cap.life = 0;
    cap.active = true;
    cap.head.scale.setScalar(0.45 + near * 0.55);
    cap.trail.rotation.z = Math.atan2(cap.dy, cap.dx);
    cap.trail.scale.set(cap.length, 0.04 + near * 0.05, 1);
  }

  return function update(delta, visibility) {
    wait -= delta;
    if (wait <= 0) {
      // Usually one cap; about one launch in five is a shower of three to five.
      const shower =
        Math.random() < 0.2
          ? { fromLeft: Math.random() < 0.5, angle: 15 + Math.random() * 25 }
          : null;
      const count = shower ? 3 + Math.floor(Math.random() * 3) : 1;
      pool.filter((cap) => !cap.active).slice(0, count).forEach((cap) => launch(cap, shower));
      wait = shower ? 2.4 + Math.random() * 1.6 : 0.5 + Math.random() * 1.3;
    }
    for (const cap of pool) {
      if (!cap.active) continue;
      cap.life += delta;
      const t = cap.life / cap.duration;
      if (t >= 1) {
        cap.active = false;
        cap.head.material.opacity = 0;
        cap.trail.material.uniforms.uOpacity.value = 0;
        continue;
      }
      cap.x += cap.dx * delta;
      cap.y += cap.dy * delta;
      const fade = Math.sin(Math.PI * t) * visibility;
      const dir = Math.hypot(cap.dx, cap.dy);
      cap.head.position.set(cap.x, cap.y, -cap.depth);
      cap.head.material.opacity = fade;
      cap.head.material.rotation += delta * cap.spin; // the cap tumbles as it falls
      cap.trail.position.set(
        cap.x - (cap.dx / dir) * cap.length * 0.5,
        cap.y - (cap.dy / dir) * cap.length * 0.5,
        -cap.depth
      );
      cap.trail.material.uniforms.uOpacity.value = fade;
    }
  };
}

function start() {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
  } catch (error) {
    return; // No WebGL: the CSS glow behind the headline stays.
  }
  renderer.setClearColor(BACKGROUND, 1);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.domElement.classList.add("galaxy-canvas");
  renderer.domElement.setAttribute("aria-hidden", "true");
  mount.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, 1, 0.05, 100);
  camera.position.set(0, 4.6, 10.5);

  const count = window.innerWidth < 768 ? 24000 : 50000;
  const uniforms = {
    uTime: { value: 0 },
    uSize: { value: 26 },
    uPixelRatio: { value: renderer.getPixelRatio() },
    uMap: { value: capTexture() },
    uPointer: { value: new THREE.Vector3(999, 0, 999) },
    uPointerForce: { value: 0 },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader,
    fragmentShader,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const galaxy = new THREE.Points(buildGalaxy(count), material);

  // The galaxy sits in a "world" group that the dive scales and lifts.
  const world = new THREE.Group();
  world.rotation.x = 0.08;
  world.position.y = GALAXY_Y;
  world.add(galaxy);
  scene.add(world);

  // Camera-space effects need the camera in the scene graph.
  scene.add(camera);
  const shootingCaps = reducedMotion ? null : createShootingCaps(camera, uniforms.uMap.value);

  // ── Controls ─────────────────────────────────────────────────────────────
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enablePan = false;
  controls.enableDamping = !reducedMotion;
  controls.dampingFactor = 0.06;
  controls.rotateSpeed = 0.55;
  controls.zoomSpeed = 0.8;
  controls.minDistance = 1.2;
  controls.maxDistance = 16;
  controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_ROTATE };

  // A plain wheel scrolls the page; only pinch / Ctrl + wheel zooms. The
  // capture listener runs before OrbitControls' own, which then ignores it.
  renderer.domElement.addEventListener(
    "wheel",
    (event) => {
      controls.enableZoom = event.ctrlKey;
    },
    { capture: true, passive: true }
  );
  renderer.domElement.addEventListener("pointerdown", () => {
    controls.enableZoom = true; // touch pinch
  });
  // OrbitControls sets touch-action: none, which would trap phones in the hero.
  renderer.domElement.style.touchAction = "pan-y";

  // ── Cursor: caps part around it ──────────────────────────────────────────
  // Track the mouse over the hero (the overlay text ignores the pointer, so
  // this works over the headline too). Each frame, cast the cursor into the
  // galaxy's plane in its own rotating space, so the effect stays under the
  // cursor while the galaxy turns. Mouse and pen only: touch has no hover.
  const pointer = { x: 0, y: 0, over: false };
  const raycaster = new THREE.Raycaster();
  const galaxyPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const toGalaxy = new THREE.Matrix4();
  const hit = new THREE.Vector3();
  const pointerTarget = new THREE.Vector3(999, 0, 999);
  let forceTarget = 0;

  if (!reducedMotion) {
    stage.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch") return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      pointer.over = true;
    });
    stage.addEventListener("pointerleave", () => {
      pointer.over = false;
    });
  }

  // How quickly the effect catches up with the cursor, per second. Lower is a
  // longer trail: at 2.5 it covers most of the gap in about half a second.
  const FOLLOW_RATE = 2.5;
  const FADE_RATE = 2;
  // The whole galaxy leans toward the cursor, slowly, like a heavy object.
  const LEAN_RATE = 1.6;
  const lean = { x: 0, y: 0 };

  function followPointer(delta) {
    forceTarget = 0;
    if (pointer.over) {
      raycaster.setFromCamera(pointer, camera);
      toGalaxy.copy(galaxy.matrixWorld).invert();
      raycaster.ray.applyMatrix4(toGalaxy);
      if (raycaster.ray.intersectPlane(galaxyPlane, hit)) {
        pointerTarget.copy(hit);
        forceTarget = 1;
      }
    }
    // Ease both by elapsed time (the same feel at 60 or 120 Hz), so the effect
    // trails the cursor rather than sitting on it. When it has faded out, jump
    // straight to the cursor so it never sweeps in from afar.
    const follow = 1 - Math.exp(-FOLLOW_RATE * delta);
    const fade = 1 - Math.exp(-FADE_RATE * delta);
    if (uniforms.uPointerForce.value < 0.02) uniforms.uPointer.value.copy(pointerTarget);
    else uniforms.uPointer.value.lerp(pointerTarget, follow);
    uniforms.uPointerForce.value += (forceTarget - uniforms.uPointerForce.value) * fade;

    const ease = 1 - Math.exp(-LEAN_RATE * delta);
    lean.x += ((pointer.over ? pointer.x : 0) - lean.x) * ease;
    lean.y += ((pointer.over ? pointer.y : 0) - lean.y) * ease;
    world.rotation.x = 0.08 - lean.y * 0.14;
    world.rotation.z = -lean.x * 0.1;
    world.position.x = lean.x * 0.4;
  }

  // ── Size ─────────────────────────────────────────────────────────────────
  function resize() {
    const width = mount.clientWidth;
    const height = mount.clientHeight;
    if (!width || !height) return;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    uniforms.uPixelRatio.value = renderer.getPixelRatio();
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (reducedMotion) render();
  }
  new ResizeObserver(resize).observe(mount);
  window.addEventListener("resize", resize);

  // ── Scroll: fly into the galaxy ──────────────────────────────────────────
  // ScrollTrigger reports where we are in the pinned hero; the frame loop
  // eases toward it so the dive stays smooth even on a jumpy wheel.
  let flyTarget = 0;
  let fly = 0;
  if (!reducedMotion && window.gsap && window.ScrollTrigger) {
    stage.classList.add("galaxy-pinned");
    window.ScrollTrigger.create({
      trigger: stage,
      start: "top top",
      end: "bottom bottom",
      onUpdate: (self) => {
        flyTarget = self.progress;
      },
    });
    window.ScrollTrigger.refresh();
  }

  // ── Frames ───────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();

  function render() {
    renderer.render(scene, camera);
  }

  function frame() {
    const delta = Math.min(clock.getDelta(), 0.05);
    uniforms.uTime.value += delta;
    galaxy.rotation.y += delta * 0.045;

    fly += (flyTarget - fly) * 0.08;
    // The world swells past the camera, so the dive reads as flying in.
    world.scale.setScalar(1 + fly * fly * 7);
    // Rise to meet the camera while diving in.
    world.position.y = GALAXY_Y * (1 - fly);
    if (shootingCaps) shootingCaps(delta, Math.max(0, 1 - fly * 2));
    stage.style.setProperty("--fly", fly.toFixed(4));

    controls.update();
    galaxy.updateMatrixWorld();
    followPointer(delta);
    render();
  }

  if (reducedMotion) {
    controls.addEventListener("change", render);
    resize();
    render();
  } else {
    let onScreen = true;
    const sync = () => {
      renderer.setAnimationLoop(onScreen && !document.hidden ? frame : null);
      if (onScreen) clock.getDelta(); // don't jump after a pause
    };
    new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      sync();
    }).observe(stage);
    document.addEventListener("visibilitychange", sync);
    resize();
    sync();
  }

  // Fade in once the first frame is on screen, so there's no black flash.
  requestAnimationFrame(() => stage.classList.add("galaxy-ready"));
}

// Last, so the shader strings above exist before start() reads them.
if (stage && mount) start();
