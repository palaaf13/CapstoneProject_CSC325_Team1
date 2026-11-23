// Rambo in 3D, for the Ask Rambo page. Original character, built from
// Three.js geometry: no downloaded model, no college marks.
//
//   * Spiral horns are TubeGeometry along a 3D spiral, tapered ring by ring,
//     with growth ridges and a light-to-dark green gradient.
//   * His wool is a cloud of small icospheres; his face uses a soft sheen.
//   * He breathes, blinks, flicks an ear, and looks toward the cursor.
//   * He reacts to the chat: "thinking" while Rambo looks something up, a
//     happy hop when the answer lands. Click him for a headbutt.
//
// Decorative only: the canvas is aria-hidden and nothing depends on it. With
// reduced motion he holds still. Without WebGL the flat SVG Rambo stays.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const stage = document.querySelector("[data-rambo-3d]");

const COLORS = {
  fur: 0x1c2420,
  muzzle: 0x46524b,
  wool: 0xf4f0e6,
  hornBase: 0x7cc79c,
  hornTip: 0x033a22,
  iris: 0x1d8253,
  innerEar: 0xe6b3a6,
  scarf: 0x00693e,
  spark: 0xa3d7b8,
};

function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
  } catch {
    return false;
  }
}

// -- geometry helpers --------------------------------------------------------

/** A ram horn: a spiral that sweeps back, curls down past the ear and forward. */
function hornGeometry(side) {
  const points = [];
  const steps = 140;
  const turns = 1.08;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const angle = t * turns * Math.PI * 2;
    const r = 0.52 * (1 - 0.68 * t);
    points.push(
      new THREE.Vector3(side * 0.18 * t, r * Math.cos(angle), -r * Math.sin(angle)),
    );
  }
  const curve = new THREE.CatmullRomCurve3(points);
  const tubular = 220;
  const radial = 28;
  const geo = new THREE.TubeGeometry(curve, tubular, 1, radial, false);

  // TubeGeometry puts every vertex exactly 1 unit from the curve. Scale each
  // ring to taper the horn, and ripple the radius for growth rings.
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const base = new THREE.Color(COLORS.hornBase);
  const tip = new THREE.Color(COLORS.hornTip);
  const c = new THREE.Color();
  const center = new THREE.Vector3();
  const v = new THREE.Vector3();
  for (let i = 0; i <= tubular; i++) {
    const t = i / tubular;
    curve.getPointAt(t, center);
    const radius = (0.15 * Math.pow(1 - t, 0.9) + 0.022) * (1 + 0.06 * Math.sin(t * 64));
    c.copy(base).lerp(tip, Math.pow(t, 0.7));
    for (let j = 0; j <= radial; j++) {
      const k = i * (radial + 1) + j;
      v.fromBufferAttribute(pos, k).sub(center).multiplyScalar(radius).add(center);
      pos.setXYZ(k, v.x, v.y, v.z);
      colors.set([c.r, c.g, c.b], k * 3);
    }
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return geo;
}

/** A soft wool cloud: small icospheres scattered over an ellipsoid. */
function woolCloud(material, { count, rx, ry, rz, size, seed = 1, yMin = -1 }) {
  const group = new THREE.Group();
  const geo = new THREE.IcosahedronGeometry(1, 2);
  let s = seed;
  const rand = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < count; i++) {
    const u = rand() * 2 - 1;
    const theta = rand() * Math.PI * 2;
    const ring = Math.sqrt(1 - u * u);
    const y = u;
    if (y < yMin) continue;
    const puff = new THREE.Mesh(geo, material);
    puff.position.set(ring * Math.cos(theta) * rx, y * ry, ring * Math.sin(theta) * rz);
    puff.scale.setScalar(size * (0.75 + rand() * 0.5));
    puff.castShadow = true;
    group.add(puff);
  }
  return group;
}

// -- the character -----------------------------------------------------------

function buildRambo() {
  const fur = new THREE.MeshPhysicalMaterial({
    color: COLORS.fur,
    roughness: 0.62,
    sheen: 1,
    sheenRoughness: 0.45,
    sheenColor: new THREE.Color(0x8a9a92),
  });
  const muzzle = new THREE.MeshPhysicalMaterial({ color: COLORS.muzzle, roughness: 0.55, sheen: 0.6, sheenColor: new THREE.Color(0xa3d7b8) });
  const wool = new THREE.MeshPhysicalMaterial({ color: COLORS.wool, roughness: 0.95, sheen: 1, sheenColor: new THREE.Color(0xffffff), sheenRoughness: 0.8 });
  const horn = new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.38, clearcoat: 0.8, clearcoatRoughness: 0.25, envMapIntensity: 0.55 });
  const eyeWhite = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.15, clearcoat: 1 });
  const iris = new THREE.MeshPhysicalMaterial({ color: COLORS.iris, roughness: 0.2, clearcoat: 1 });
  const pupil = new THREE.MeshStandardMaterial({ color: 0x050807, roughness: 0.1 });
  const glint = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const innerEar = new THREE.MeshStandardMaterial({ color: COLORS.innerEar, roughness: 0.7 });
  const scarf = new THREE.MeshPhysicalMaterial({ color: COLORS.scarf, roughness: 0.6, sheen: 0.8, sheenColor: new THREE.Color(0x6fbd91) });
  const dark = new THREE.MeshStandardMaterial({ color: 0x0b100d, roughness: 0.4 });

  const root = new THREE.Group();
  const body = new THREE.Group();
  root.add(body);

  // Woolly body, with a green scarf where head meets wool.
  const torso = woolCloud(wool, { count: 60, rx: 0.72, ry: 0.55, rz: 0.6, size: 0.24, seed: 7 });
  torso.position.y = -1.25;
  const core = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), wool);
  core.scale.set(0.72, 0.55, 0.62);
  core.position.y = -1.25;
  body.add(core, torso);
  const scarfRing = new THREE.Mesh(new THREE.TorusGeometry(0.46, 0.12, 20, 64), scarf);
  scarfRing.rotation.x = Math.PI / 2 - 0.12;
  scarfRing.position.set(0, -0.74, 0.02);
  scarfRing.castShadow = true;
  const tail = new THREE.Mesh(new THREE.CapsuleGeometry(0.1, 0.32, 8, 16), scarf);
  tail.position.set(0.24, -0.98, 0.45);
  tail.rotation.set(0.35, 0, 0.35);
  body.add(scarfRing, tail);

  // Head pivots at the neck so nods and tilts look natural.
  const neck = new THREE.Group();
  neck.position.y = -0.7;
  body.add(neck);
  const head = new THREE.Group();
  head.position.y = 0.72;
  neck.add(head);

  const skull = new THREE.Mesh(new THREE.SphereGeometry(1, 64, 48), fur);
  skull.scale.set(0.72, 0.68, 0.7);
  skull.castShadow = true;
  const snout = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), muzzle);
  snout.scale.set(0.46, 0.36, 0.42);
  snout.position.set(0, -0.26, 0.44);
  head.add(skull, snout);

  for (const side of [-1, 1]) {
    const nostril = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 12), dark);
    nostril.scale.set(1.3, 0.7, 0.6);
    nostril.position.set(side * 0.11, -0.2, 0.82);
    head.add(nostril);
  }
  const smile = new THREE.Mesh(new THREE.TorusGeometry(0.12, 0.018, 8, 32, Math.PI * 0.8), dark);
  smile.position.set(0, -0.36, 0.8);
  smile.rotation.set(0.25, 0, Math.PI + Math.PI * 0.1);
  head.add(smile);

  // Forehead curls.
  const tuft = woolCloud(wool, { count: 34, rx: 0.42, ry: 0.22, rz: 0.3, size: 0.12, seed: 3, yMin: -0.2 });
  tuft.position.set(0, 0.5, 0.18);
  head.add(tuft);

  // Eyes: white, green iris, pupil, a catchlight. Each eye scales for blinks.
  const eyes = [];
  const pupils = [];
  for (const side of [-1, 1]) {
    const eye = new THREE.Group();
    eye.position.set(side * 0.27, 0.07, 0.53);
    const white = new THREE.Mesh(new THREE.SphereGeometry(0.19, 32, 24), eyeWhite);
    white.scale.set(1, 1.08, 0.7);
    const look = new THREE.Group();
    const irisMesh = new THREE.Mesh(new THREE.SphereGeometry(0.1, 32, 24), iris);
    irisMesh.scale.set(1, 1, 0.45);
    irisMesh.position.z = 0.1;
    const pupilMesh = new THREE.Mesh(new THREE.SphereGeometry(0.058, 24, 16), pupil);
    pupilMesh.scale.set(1, 1, 0.45);
    pupilMesh.position.z = 0.128;
    const shine = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 8), glint);
    shine.position.set(-0.03, 0.04, 0.152);
    look.add(irisMesh, pupilMesh, shine);
    eye.add(white, look);
    eye.rotation.y = side * 0.22;
    head.add(eye);
    eyes.push(eye);
    pupils.push(look);
  }

  // Ears, angled out below the horns.
  const ears = [];
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.58, -0.28, 0.12);
    const outer = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), fur);
    outer.scale.set(0.24, 0.09, 0.13);
    outer.position.x = side * 0.14;
    const inner = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), innerEar);
    inner.scale.set(0.18, 0.05, 0.08);
    inner.position.set(side * 0.16, 0.025, 0.035);
    pivot.add(outer, inner);
    pivot.rotation.z = side * -0.45;
    head.add(pivot);
    ears.push(pivot);
  }

  // Horns.
  for (const side of [-1, 1]) {
    const mesh = new THREE.Mesh(hornGeometry(side), horn);
    mesh.position.set(side * 0.5, 0.0, -0.08);
    mesh.rotation.set(0.1, side * -1.15, side * 0.1);
    mesh.castShadow = true;
    head.add(mesh);
  }

  root.traverse((o) => {
    if (o.isMesh) o.castShadow = true;
  });
  return { root, body, neck, head, eyes, pupils, ears };
}

function sparkles() {
  const count = 90;
  const positions = new Float32Array(count * 3);
  const speeds = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    positions.set([(Math.random() - 0.5) * 5, Math.random() * 4 - 2, (Math.random() - 0.5) * 3 - 0.5], i * 3);
    speeds[i] = 0.15 + Math.random() * 0.35;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const sprite = document.createElement("canvas");
  sprite.width = sprite.height = 64;
  const ctx = sprite.getContext("2d");
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.3, "rgba(163,215,184,0.8)");
  g.addColorStop(1, "rgba(163,215,184,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  const material = new THREE.PointsMaterial({
    size: 0.09,
    map: new THREE.CanvasTexture(sprite),
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    color: COLORS.spark,
    opacity: 0.55,
  });
  const points = new THREE.Points(geo, material);
  return { points, speeds, material };
}

function groundShadow() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d");
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "rgba(2,26,16,0.35)");
  g.addColorStop(1, "rgba(2,26,16,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(3.2, 3.2),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = -1.82;
  return mesh;
}

// -- scene -------------------------------------------------------------------

function start() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.95;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute("aria-hidden", "true");
  renderer.domElement.className = "rambo-3d-canvas";

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 50);
  camera.position.set(0, 0.05, 5.7);
  camera.lookAt(0, -0.5, 0);

  scene.add(new THREE.HemisphereLight(0xeaf6ef, 0x021a10, 0.7));
  const key = new THREE.DirectionalLight(0xfff6ea, 2.4);
  key.position.set(3, 5, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.radius = 6;
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x6fbd91, 2.2);
  rim.position.set(-4, 2.5, -4);
  scene.add(rim);
  const fill = new THREE.PointLight(0xa3d7b8, 6, 12);
  fill.position.set(-3, -1, 3);
  scene.add(fill);

  const rambo = buildRambo();
  scene.add(rambo.root, groundShadow());
  const spark = sparkles();
  scene.add(spark.points);

  stage.appendChild(renderer.domElement);
  stage.classList.add("is-3d");

  function resize() {
    const { width, height } = stage.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    // Keep him the same size on narrow screens.
    camera.fov = width / height < 1 ? 36 : 28;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage);
  resize();

  // Where he looks: the cursor, eased.
  const look = { x: 0, y: 0, tx: 0, ty: 0 };
  window.addEventListener(
    "pointermove",
    (e) => {
      const r = stage.getBoundingClientRect();
      look.tx = THREE.MathUtils.clamp(((e.clientX - (r.left + r.width / 2)) / window.innerWidth) * 2.2, -1, 1);
      look.ty = THREE.MathUtils.clamp(((e.clientY - (r.top + r.height * 0.4)) / window.innerHeight) * 2.2, -1, 1);
    },
    { passive: true },
  );

  // Moods: idle, thinking (looking something up), happy (answer landed), butt.
  let mood = "idle";
  let moodStart = 0;
  const clock = new THREE.Clock();
  function setMood(next) {
    mood = next;
    moodStart = clock.getElapsedTime();
    if (reduced) render();
  }
  window.addEventListener("rambo:mood", (e) => setMood(e.detail));
  renderer.domElement.style.pointerEvents = "auto";
  stage.addEventListener("click", () => setMood("butt"));

  let nextBlink = 1.5;
  let blinkAt = -1;
  let nextFlick = 3;
  let flickAt = -1;

  function render() {
    renderer.render(scene, camera);
  }

  function tick() {
    const t = clock.getElapsedTime();
    const since = t - moodStart;
    const { root, body, neck, head, eyes, pupils, ears } = rambo;

    look.x += (look.tx - look.x) * 0.06;
    look.y += (look.ty - look.y) * 0.06;

    // Breathing and a slow float.
    body.position.y = Math.sin(t * 1.4) * 0.05;
    body.scale.setScalar(1 + Math.sin(t * 1.4 + 0.6) * 0.008);
    root.rotation.y = Math.sin(t * 0.35) * 0.08 + look.x * 0.18;

    let nodX = look.y * 0.22;
    let turnY = look.x * 0.38;
    let tiltZ = -look.x * 0.06;
    let hop = 0;

    if (mood === "thinking") {
      // Head tilted, eyes up and to the side, a slow pondering sway.
      tiltZ = 0.22 + Math.sin(t * 2.2) * 0.06;
      nodX = -0.18;
      turnY = Math.sin(t * 1.1) * 0.35;
      pupils.forEach((p) => p.position.set(0.035, 0.05, 0));
    } else if (mood === "happy") {
      hop = Math.max(0, Math.sin(Math.min(since, 1.2) * Math.PI * 2.5)) * 0.28 * Math.max(0, 1 - since / 1.2);
      nodX = -0.1 + Math.sin(since * 9) * 0.08 * Math.max(0, 1 - since);
      if (since > 1.6) mood = "idle";
    } else if (mood === "butt") {
      // Lean back, then a quick forward headbutt.
      const p = Math.min(since / 0.9, 1);
      nodX = p < 0.45 ? -0.35 * (p / 0.45) : 0.55 * Math.sin(((p - 0.45) / 0.55) * Math.PI);
      if (since > 1.1) mood = "idle";
    }
    if (mood !== "thinking") {
      pupils.forEach((p) => p.position.set(look.x * 0.035, -look.y * 0.03, 0));
    }

    root.position.y = hop;
    neck.rotation.x += (nodX - neck.rotation.x) * 0.12;
    head.rotation.y += (turnY - head.rotation.y) * 0.1;
    head.rotation.z += (tiltZ - head.rotation.z) * 0.1;

    // Blink every few seconds, sometimes twice.
    if (t > nextBlink) {
      blinkAt = t;
      nextBlink = t + 2.2 + Math.random() * 3.5;
    }
    const b = blinkAt >= 0 ? (t - blinkAt) / 0.16 : 1;
    const open = b < 1 ? Math.abs(Math.cos(b * Math.PI)) * 0.92 + 0.08 : 1;
    eyes.forEach((eye) => (eye.scale.y = open));

    // An ear flick now and then.
    if (t > nextFlick) {
      flickAt = t;
      nextFlick = t + 4 + Math.random() * 5;
    }
    const f = flickAt >= 0 ? (t - flickAt) / 0.4 : 1;
    const flick = f < 1 ? Math.sin(f * Math.PI) * 0.35 : 0;
    ears[0].rotation.z = 0.45 + flick;
    ears[1].rotation.z = -0.45 + Math.sin(t * 0.8) * 0.03;

    // Sparkles drift up; faster while he thinks.
    const pos = spark.points.geometry.attributes.position;
    const speedUp = mood === "thinking" ? 3 : 1;
    for (let i = 0; i < pos.count; i++) {
      let y = pos.getY(i) + spark.speeds[i] * 0.004 * speedUp;
      if (y > 2.2) y = -2;
      pos.setY(i, y);
    }
    pos.needsUpdate = true;
    spark.material.opacity = mood === "thinking" ? 0.9 : 0.55;

    render();
  }

  if (reduced) {
    // Hold one friendly pose. Moods still re-render, without motion.
    rambo.neck.rotation.x = -0.05;
    render();
    return;
  }

  let running = true;
  let visible = true;
  renderer.setAnimationLoop(tick);
  const sync = () => {
    const should = visible && !document.hidden;
    if (should !== running) {
      running = should;
      renderer.setAnimationLoop(should ? tick : null);
    }
  };
  new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    sync();
  }).observe(stage);
  document.addEventListener("visibilitychange", sync);
}

if (stage && webglAvailable()) {
  try {
    start();
  } catch (error) {
    // The flat SVG Rambo is still there; nothing else depends on this.
    console.warn("Rambo 3D could not start:", error);
  }
}
