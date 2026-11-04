// The landing page's opening scene: about 50,000 graduation caps in a slowly
// turning spiral galaxy in RamHub green: soft mint at the core shading to
// Farmingdale green at the rim. A hologram graduate in cap and gown stands at
// the centre, and every few seconds a cap streaks across the sky.
//
//   * Drag to rotate. Pinch (or Ctrl + scroll) to zoom. A plain scroll wheel
//     is left alone, so the page always scrolls past the hero.
//   * On phones, one finger scrolls the page and two fingers rotate and zoom.
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
const HOLOGRAM = new THREE.Color("#d0ebda"); // --color-accent-100
const STREAK = new THREE.Color("#d0ebda"); // --color-accent-100
const SHAPE = { radius: 6, arms: 4, spin: 1.05, scatter: 0.38, scatterPower: 3 };
// Sit the core below the headline, like a horizon, so the text stays clear.
const GALAXY_Y = -3.8;
// Radius of the empty centre where the hologram graduate stands.
const EYE = 1.0;


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
    // Denser toward the core, but with a small empty eye for the hologram.
    const r = EYE + Math.pow(Math.random(), 1.35) * (SHAPE.radius - EYE);
    const arm = ((i % SHAPE.arms) / SHAPE.arms) * Math.PI * 2;
    const twist = r * SHAPE.spin;

    positions[i * 3] = Math.cos(arm + twist) * r + jitter(r);
    positions[i * 3 + 1] = jitter(r) * 0.55;
    positions[i * 3 + 2] = Math.sin(arm + twist) * r + jitter(r);

    color.copy(CORE).lerp(RIM, Math.min(1, r / SHAPE.radius));
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    // A handful of big caps so the shape is recognisable before you zoom;
    // caps near the eye are smaller, so the hologram glows against dark space.
    const nearEye = Math.min(1, (r - EYE) / 1.4);
    scales[i] = (0.55 + Math.random() * 1.05) * (Math.random() < 0.004 ? 2.6 : 1) * (0.35 + 0.65 * nearEye);
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
  attribute float aScale;
  attribute float aAngle;
  varying vec3 vColor;
  varying float vAngle;

  void main() {
    vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * viewPosition;
    gl_PointSize = min(uSize * aScale * uPixelRatio / -viewPosition.z, 96.0);
    vColor = color;
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

// ── Hologram graduate ───────────────────────────────────────────────────────
// Built from simple shapes (gown, arms, head, mortarboard, diploma) and drawn
// with one hologram shader: glowing edges, rolling scan lines, a rare flicker.
const hologramVertex = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vNormal = normalize(mat3(modelMatrix) * normal);
    vView = normalize(cameraPosition - world.xyz);
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const hologramFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uTime;
  uniform float uOpacity;
  varying vec3 vNormal;
  varying vec3 vView;

  float random(float n) { return fract(sin(n) * 43758.5453); }

  void main() {
    float rim = pow(1.0 - abs(dot(normalize(vNormal), normalize(vView))), 2.2);
    float scan = 0.6 + 0.4 * sin(gl_FragCoord.y * 0.7 - uTime * 5.0);
    float glitch = step(0.94, random(floor(uTime * 9.0)));
    float flicker = 1.0 - glitch * (0.35 + 0.35 * sin(uTime * 80.0));
    float alpha = (0.22 + rim * 1.6) * scan * flicker * uOpacity;
    gl_FragColor = vec4(uColor * (0.7 + rim * 1.8), alpha);
    #include <colorspace_fragment>
  }
`;

const beamFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec2 vUv;
  void main() {
    // Brightest at the pad, fading out as the light rises.
    float alpha = pow(1.0 - vUv.y, 1.6) * 0.22 * uOpacity;
    gl_FragColor = vec4(uColor, alpha);
    #include <colorspace_fragment>
  }
`;

function buildHologram(uniforms) {
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: hologramVertex,
    fragmentShader: hologramFragment,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });
  const figure = new THREE.Group();
  const part = (geometry, x, y, z) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    figure.add(mesh);
    return mesh;
  };

  // Gown: a bell shape from the hem up to the shoulders.
  const gownProfile = [
    [0.0, 0.0], [0.44, 0.0], [0.42, 0.08], [0.35, 0.55], [0.29, 0.92],
    [0.27, 1.08], [0.24, 1.2], [0.13, 1.29], [0.0, 1.31],
  ].map(([radius, height]) => new THREE.Vector2(radius, height));
  part(new THREE.LatheGeometry(gownProfile, 40), 0, 0, 0);

  // Arms hang from pivots at the shoulders. The right one raises the diploma.
  const arm = (side, lift) => {
    const pivot = new THREE.Group();
    pivot.position.set(0.25 * side, 1.18, 0);
    pivot.rotation.z = lift * side;
    const sleeve = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.11, 0.56, 16, 1, true), material);
    sleeve.position.y = -0.28;
    pivot.add(sleeve);
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.055, 12, 10), material);
    hand.position.y = -0.6;
    pivot.add(hand);
    figure.add(pivot);
    return pivot;
  };
  arm(-1, 0.32); // left arm relaxed at the side
  const raised = arm(1, 2.55); // right arm up, holding the diploma
  const diploma = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.32, 14), material);
  diploma.position.set(0, -0.62, 0);
  diploma.rotation.z = Math.PI / 2;
  raised.add(diploma);

  part(new THREE.CylinderGeometry(0.06, 0.07, 0.1, 14), 0, 1.34, 0); // neck
  part(new THREE.SphereGeometry(0.15, 24, 18), 0, 1.52, 0); // head
  part(new THREE.CylinderGeometry(0.155, 0.15, 0.09, 24), 0, 1.63, 0); // cap

  const board = part(new THREE.BoxGeometry(0.48, 0.022, 0.48), 0, 1.69, 0); // mortarboard
  board.rotation.set(0.06, Math.PI / 4, 0);
  part(new THREE.SphereGeometry(0.022, 10, 8), 0, 1.705, 0); // button
  part(new THREE.CylinderGeometry(0.008, 0.008, 0.2, 6), 0.33, 1.6, 0); // tassel cord
  part(new THREE.CylinderGeometry(0.025, 0.012, 0.07, 10), 0.33, 1.48, 0); // tassel

  // Projector: a glowing pad and a soft beam rising through the figure.
  const pad = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.56, 48), material);
  pad.rotation.x = -Math.PI / 2;
  figure.add(pad);
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.62, 0.5, 2.1, 40, 1, true),
    new THREE.ShaderMaterial({
      uniforms: { uColor: uniforms.uColor, uOpacity: uniforms.uOpacity },
      vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: beamFragment,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    })
  );
  beam.position.y = 1.05;
  figure.add(beam);

  return figure;
}

// ── Shooting caps ──────────────────────────────────────────────────────────
// A few caps that streak across the sky with a fading tail. They live in the
// camera's own space, so they always cross the screen however you orbit.
function createShootingCaps(camera, texture) {
  const group = new THREE.Group();
  camera.add(group);
  const DEPTH = 14;

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

  const pool = Array.from({ length: 3 }, () => {
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
    head.scale.setScalar(0.75);
    const trail = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), trailMaterial());
    group.add(head, trail);
    return { head, trail, life: 0, duration: 0, active: false, x: 0, y: 0, dx: 0, dy: 0, length: 0 };
  });

  let wait = 1.5;

  function launch(cap) {
    const halfHeight = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * DEPTH;
    const halfWidth = halfHeight * camera.aspect;
    const fromLeft = Math.random() < 0.5;
    const angle = THREE.MathUtils.degToRad(18 + Math.random() * 20);
    const speed = 13 + Math.random() * 6;
    cap.x = (fromLeft ? -1 : 1) * halfWidth * (0.4 + Math.random() * 0.7);
    cap.y = halfHeight * (0.15 + Math.random() * 0.75);
    cap.dx = (fromLeft ? 1 : -1) * Math.cos(angle) * speed;
    cap.dy = -Math.sin(angle) * speed;
    cap.length = 2.6 + Math.random() * 1.6;
    cap.duration = 1.1 + Math.random() * 0.6;
    cap.life = 0;
    cap.active = true;
    cap.trail.rotation.z = Math.atan2(cap.dy, cap.dx);
    cap.trail.scale.set(cap.length, 0.07, 1);
  }

  return function update(delta, visibility) {
    wait -= delta;
    if (wait <= 0) {
      const idle = pool.find((cap) => !cap.active);
      if (idle) launch(idle);
      wait = 2.2 + Math.random() * 3.5;
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
      cap.head.position.set(cap.x, cap.y, -DEPTH);
      cap.head.material.opacity = fade;
      cap.head.material.rotation += delta * 5; // the cap tumbles as it falls
      cap.trail.position.set(
        cap.x - (cap.dx / dir) * cap.length * 0.5,
        cap.y - (cap.dy / dir) * cap.length * 0.5,
        -DEPTH
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

  // The galaxy and the hologram share one "world", so the dive scales both.
  const world = new THREE.Group();
  world.rotation.x = 0.08;
  world.position.y = GALAXY_Y;
  world.add(galaxy);
  scene.add(world);

  const hologramUniforms = {
    uColor: { value: HOLOGRAM },
    uTime: uniforms.uTime,
    uOpacity: { value: 1 },
  };
  const hologram = buildHologram(hologramUniforms);
  hologram.scale.setScalar(2.1);
  world.add(hologram);

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
    // The graduate turns slowly and floats on the beam.
    hologram.rotation.y += delta * 0.35;
    hologram.position.y = 0.06 + Math.sin(uniforms.uTime.value * 1.3) * 0.04;

    fly += (flyTarget - fly) * 0.08;
    // The world swells past the camera, so the dive reads as flying in.
    world.scale.setScalar(1 + fly * fly * 7);
    // Rise to meet the camera while diving in.
    world.position.y = GALAXY_Y * (1 - fly);
    // The hologram fades as you pass through it.
    hologramUniforms.uOpacity.value = Math.max(0, 1 - fly * 1.6);
    if (shootingCaps) shootingCaps(delta, Math.max(0, 1 - fly * 2));
    stage.style.setProperty("--fly", fly.toFixed(4));

    controls.update();
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
