// Rambo in 3D, for the Ask Rambo page: the same Rambo as the landing page
// (templates/partials/rambo.html), built in Three.js.
//
//   * The horns follow the SVG's own spiral paths, coordinate for coordinate,
//     extruded into tapered, ridged tubes in the same light-to-dark green, and
//     they grow in when he appears, like the SVG's horns draw on.
//   * The long tapered face is sculpted as a signed distance field and meshed
//     with MarchingCubes, dark charcoal like the SVG's face gradient. The
//     SVG's green outline becomes a green rim light on every edge.
//   * White eyes whose pupils follow the cursor, lids that blink, green brows,
//     a snout with vertical nostrils and a green smile, leaf-shaped ears.
//   * He floats and breathes, tilts his head while Rambo is thinking, nods
//     when an answer lands, and headbutts when you click him.
//
// Decorative only: the canvas is aria-hidden. With reduced motion he holds
// still. Without WebGL the flat SVG Rambo stays.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { MarchingCubes } from "three/addons/objects/MarchingCubes.js";

const stage = document.querySelector("[data-rambo-3d]");

// The site's own palette (static/src/input.css).
const NEUTRAL_50 = 0xf8f9fa;
const NEUTRAL_800 = 0x272c34;
const NEUTRAL_950 = 0x0d0f12;
const ACCENT_200 = 0xa3d7b8;
const ACCENT_300 = 0x6fbd91;
const ACCENT_400 = 0x3f9e6d;
const ACCENT_500 = 0x1d8253;

/** SVG coordinates (viewBox around x=200, y=200) to 3D units: 100 px = 1 unit, y up. */
const svg = (x, y, z = 0) => new THREE.Vector3((x - 200) / 100, (200 - y) / 100, z);

function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
  } catch {
    return false;
  }
}

// -- materials ------------------------------------------------------------------

/** The SVG outlines its face, ears and snout in accent-400. In 3D that becomes
 *  a rim light: green where a surface turns away from the camera. */
function withRim(material, color = ACCENT_400, strength = 1.4, power = 2.6) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uRimColor = { value: new THREE.Color(color) };
    shader.uniforms.uRim = { value: strength };
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform vec3 uRimColor; uniform float uRim;")
      .replace(
        "#include <emissivemap_fragment>",
        `#include <emissivemap_fragment>
float rimFacing = 1.0 - clamp(dot(normal, normalize(vViewPosition)), 0.0, 1.0);
totalEmissiveRadiance += uRimColor * uRim * pow(rimFacing, ${power.toFixed(1)});`,
      );
  };
  material.customProgramCacheKey = () => `rambo-rim-${color}-${strength}-${power}`;
  return material;
}

// -- the face, sculpted ---------------------------------------------------------

function ellipsoid(c, r) {
  return (x, y, z) => {
    const px = (x - c[0]) / r[0];
    const py = (y - c[1]) / r[1];
    const pz = (z - c[2]) / r[2];
    const k0 = Math.hypot(px, py, pz);
    const k1 = Math.hypot(px / r[0], py / r[1], pz / r[2]);
    return k1 === 0 ? -Math.min(...r) : (k0 * (k0 - 1)) / k1;
  };
}

function smin(a, b, k) {
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.min(a, b) - h * h * k * 0.25;
}

/** Polygonize an SDF in a cube of half-width `extent` around `center`. Normals
 *  come out of MarchingCubes as raw gradients, so they are normalized here. */
function sculpt(sdf, { resolution, extent, center, colorAt }) {
  const mc = new MarchingCubes(resolution, new THREE.MeshBasicMaterial(), false, false, 120000);
  const iso = mc.isolation;
  const gain = 600 / extent;
  const [cx, cy, cz] = center;
  const { size, size2, halfsize, field } = mc;
  for (let z = 0; z < size; z++) {
    const pz = ((z - halfsize) / halfsize) * extent + cz;
    for (let y = 0; y < size; y++) {
      const py = ((y - halfsize) / halfsize) * extent + cy;
      for (let x = 0; x < size; x++) {
        const px = ((x - halfsize) / halfsize) * extent + cx;
        field[z * size2 + y * size + x] = THREE.MathUtils.clamp(iso - sdf(px, py, pz) * gain, 0, iso * 2);
      }
    }
  }
  mc.update();
  const count = mc.count;
  const positions = mc.positionArray.slice(0, count * 3);
  const normals = mc.normalArray.slice(0, count * 3);
  const colors = new Float32Array(count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < count * 3; i += 3) {
    positions[i] = positions[i] * extent + cx;
    positions[i + 1] = positions[i + 1] * extent + cy;
    positions[i + 2] = positions[i + 2] * extent + cz;
    const len = Math.hypot(normals[i], normals[i + 1], normals[i + 2]) || 1;
    normals[i] /= len;
    normals[i + 1] /= len;
    normals[i + 2] /= len;
    colorAt(positions[i], positions[i + 1], positions[i + 2], c);
    colors.set([c.r, c.g, c.b], i);
  }
  mc.geometry.dispose();
  mc.material.dispose();
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.computeBoundingSphere();
  return geo;
}

/** The SVG's long, tapered face: broad across the brow (x 148–252), narrowing
 *  to a rounded chin at y 318. */
function faceGeometry() {
  const shapes = [
    ellipsoid([0, 0.5, -0.08], [0.53, 0.38, 0.4]), // brow
    ellipsoid([0, 0.08, -0.02], [0.47, 0.5, 0.4]), // cheeks
    ellipsoid([0, -0.42, 0.02], [0.37, 0.42, 0.36]), // lower face
    ellipsoid([0, -0.86, 0.05], [0.23, 0.3, 0.3]), // chin
  ];
  const sdf = (x, y, z) => shapes.reduce((d, shape) => smin(d, shape(x, y, z), 0.22), Infinity);
  const top = new THREE.Color(NEUTRAL_800);
  const edge = new THREE.Color(NEUTRAL_950);
  return sculpt(sdf, {
    resolution: 80,
    extent: 1.1,
    center: [0, -0.15, 0],
    // Like the SVG's radial gradient: lightest just above the eyes, darker outward.
    colorAt(x, y, z, c) {
      const d = Math.hypot(x / 0.55, (y - 0.25) / 0.9);
      c.copy(top).lerp(edge, THREE.MathUtils.smoothstep(d, 0.2, 1.15));
    },
  });
}

// -- horns ----------------------------------------------------------------------

/** One horn, from the SVG path. `side` -1 is Rambo's right (screen left). The
 *  spiral sits in the face plane like the drawing, and curls gently back in
 *  depth so it reads as a solid horn from any angle. */
function hornGeometry(side) {
  // Left horn path from the SVG; the right one is its mirror (x -> 400 - x).
  const segments = [
    [[168, 138], [132, 82], [58, 92], [50, 160]],
    [[50, 160], [43, 222], [106, 256], [138, 214]],
    [[138, 214], [160, 184], [134, 150], [104, 168]],
    [[104, 168], [86, 180], [94, 208], [116, 206]],
  ];
  const path = new THREE.CurvePath();
  const total = segments.length;
  segments.forEach((points, s) => {
    const [a, b, c, d] = points.map(([x, y], i) => {
      const t = (s + i / 3) / total;
      // Depth: out from the skull, bowing back behind the ear, then the inner
      // coil comes forward a touch.
      const z = -0.32 * Math.sin(Math.min(t * 1.6, 1) * Math.PI) + 0.12 * t;
      const sx = side < 0 ? x : 400 - x;
      return svg(sx, y, z);
    });
    path.add(new THREE.CubicBezierCurve3(a, b, c, d));
  });

  const tubular = 300;
  const radial = 28;
  const geo = new THREE.TubeGeometry(path, tubular, 1, radial, false);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const center = new THREE.Vector3();
  const v = new THREE.Vector3();
  const light = new THREE.Color(ACCENT_200);
  const dark = new THREE.Color(ACCENT_500);
  const c = new THREE.Color();
  for (let i = 0; i <= tubular; i++) {
    const t = i / tubular;
    path.getPointAt(t, center);
    // Thick at the skull, tapering to a rounded tip; ridges on the outer sweep
    // only, as in the SVG.
    const ridges = t < 0.55 ? Math.pow(Math.abs(Math.sin(t * Math.PI * 26)), 3) : 0;
    const radius = (0.115 * Math.pow(1 - t, 0.55) + 0.03) * (1 - 0.06 * ridges);
    c.copy(light).lerp(dark, Math.min(1, t * 1.25)).multiplyScalar(1 - 0.28 * ridges);
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

// -- the character ----------------------------------------------------------------

function buildRambo() {
  const faceMat = withRim(
    new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.42, clearcoat: 0.35, clearcoatRoughness: 0.4 }),
  );
  const darkMat = withRim(
    new THREE.MeshPhysicalMaterial({ color: NEUTRAL_800, roughness: 0.45, clearcoat: 0.3 }),
    ACCENT_400,
    1.6,
    2.2,
  );
  const hornMat = new THREE.MeshPhysicalMaterial({
    vertexColors: true,
    roughness: 0.3,
    clearcoat: 1,
    clearcoatRoughness: 0.15,
  });
  const lineMat = new THREE.MeshStandardMaterial({
    color: ACCENT_300,
    emissive: ACCENT_300,
    emissiveIntensity: 0.35,
    roughness: 0.4,
  });
  const eyeMat = new THREE.MeshPhysicalMaterial({ color: NEUTRAL_50, roughness: 0.12, clearcoat: 1 });
  const blackMat = new THREE.MeshPhysicalMaterial({ color: NEUTRAL_950, roughness: 0.2, clearcoat: 1 });
  const lidMat = new THREE.MeshStandardMaterial({ color: NEUTRAL_800, roughness: 0.5 });

  const root = new THREE.Group();
  const head = new THREE.Group();
  root.add(head);

  const face = new THREE.Mesh(faceGeometry(), faceMat);
  face.castShadow = true;
  head.add(face);

  // Snout: the SVG ellipse at (200, 284), 68 x 48, pushed out from the chin.
  const snout = new THREE.Mesh(new THREE.SphereGeometry(1, 64, 40), darkMat);
  snout.scale.set(0.34, 0.25, 0.26);
  snout.position.copy(svg(200, 284, 0.28));
  head.add(snout);
  for (const x of [188, 212]) {
    const nostril = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), blackMat);
    nostril.scale.set(0.04, 0.06, 0.03);
    nostril.position.copy(svg(x, 282, 0.52));
    head.add(nostril);
  }
  const mouth = new THREE.QuadraticBezierCurve3(svg(186, 298, 0.47), svg(200, 307, 0.52), svg(214, 298, 0.47));
  head.add(new THREE.Mesh(new THREE.TubeGeometry(mouth, 24, 0.016, 8, false), lineMat));

  // Brows: the SVG's two arcs above the eyes, which lift when he's thinking.
  const brows = [];
  for (const side of [-1, 1]) {
    const x0 = side < 0 ? 166 : 234;
    const xm = side < 0 ? 182 : 218;
    const x1 = side < 0 ? 196 : 204;
    const curve = new THREE.QuadraticBezierCurve3(svg(x0, 176, 0.31), svg(xm, 166, 0.36), svg(x1, 176, 0.36));
    const brow = new THREE.Mesh(new THREE.TubeGeometry(curve, 20, 0.022, 8, false), lineMat);
    head.add(brow);
    brows.push(brow);
  }

  // Eyes at (180, 198) and (220, 198): white, a pupil that follows the
  // cursor, and a lid that closes for a blink.
  const pupils = [];
  const lids = [];
  for (const x of [180, 220]) {
    const eye = new THREE.Group();
    eye.position.copy(svg(x, 198, 0.3));
    const white = new THREE.Mesh(new THREE.SphereGeometry(0.115, 40, 28), eyeMat);
    const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.052, 28, 20), blackMat);
    pupil.scale.z = 0.55;
    pupil.position.z = 0.1;
    const glint = new THREE.Mesh(
      new THREE.SphereGeometry(0.013, 12, 8),
      new THREE.MeshBasicMaterial({ color: 0xffffff }),
    );
    glint.position.set(-0.018, 0.02, 0.03);
    pupil.add(glint);
    const lid = new THREE.Mesh(
      new THREE.SphereGeometry(0.122, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2),
      lidMat,
    );
    lid.rotation.x = -1.35; // open: folded back over the top of the eye
    eye.add(white, pupil, lid);
    head.add(eye);
    pupils.push(pupil);
    lids.push(lid);
  }

  // Ears: the SVG's leaf shapes, pointing out and a little down under the horns.
  const ears = [];
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.copy(svg(side < 0 ? 152 : 248, 184, -0.05));
    const ear = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 20), darkMat);
    ear.scale.set(0.27, 0.085, 0.12);
    ear.position.x = side * 0.24;
    pivot.add(ear);
    pivot.rotation.z = side * -0.18;
    head.add(pivot);
    ears.push({ pivot, side });
  }

  // Horns.
  const horns = [];
  for (const side of [-1, 1]) {
    const horn = new THREE.Mesh(hornGeometry(side), hornMat);
    horn.castShadow = true;
    head.add(horn);
    horns.push(horn);
  }

  return { root, head, pupils, lids, brows, ears, horns };
}

function groundShadow() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d");
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "rgba(2,26,16,0.28)");
  g.addColorStop(1, "rgba(2,26,16,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(2.6, 1.3),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = -1.55;
  return mesh;
}

// -- scene ----------------------------------------------------------------------

function start() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.domElement.setAttribute("aria-hidden", "true");
  renderer.domElement.className = "rambo-3d-canvas";

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.6;

  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
  camera.position.set(0, 0.1, 5.3);
  camera.lookAt(0, -0.2, 0);

  scene.add(new THREE.HemisphereLight(0xeaf6ef, 0x021a10, 0.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(2, 3, 5);
  scene.add(key);
  const rim = new THREE.DirectionalLight(ACCENT_300, 2.4);
  rim.position.set(-3, 2, -4);
  scene.add(rim);

  const rambo = buildRambo();
  scene.add(rambo.root, groundShadow());

  stage.appendChild(renderer.domElement);
  stage.classList.add("is-3d");

  function resize() {
    const { width, height } = stage.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    // The horns make him wide: on narrow screens, pull back so they fit.
    camera.fov = width / height < 1.3 ? 42 : 30;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage);
  resize();

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

  let mood = "idle";
  let moodStart = 0;
  const clock = new THREE.Clock();
  const render = () => renderer.render(scene, camera);
  window.addEventListener("rambo:mood", (e) => {
    mood = e.detail;
    moodStart = clock.getElapsedTime();
    if (reduced) render();
  });
  stage.addEventListener("click", () => {
    mood = "butt";
    moodStart = clock.getElapsedTime();
  });

  // The horns grow in, root to tip, like the SVG's horns draw on.
  const hornIndexCount = rambo.horns[0].geometry.index.count;
  const growFor = 1.4;

  let nextBlink = 1.4;
  let blinkAt = -10;
  let nextFlick = 3;
  let flickAt = -10;
  let flickSide = 0;

  function tick() {
    const t = clock.getElapsedTime();
    const since = t - moodStart;
    const { root, head, pupils, lids, brows, ears, horns } = rambo;

    const grown = Math.min(1, t / growFor);
    const eased = 1 - Math.pow(1 - grown, 3);
    const draw = Math.floor((hornIndexCount * eased) / 6) * 6;
    horns.forEach((horn) => horn.geometry.setDrawRange(0, draw));

    look.x += (look.tx - look.x) * 0.06;
    look.y += (look.ty - look.y) * 0.06;

    // A slow float and a breath.
    root.position.y = Math.sin(t * 1.3) * 0.05;
    head.scale.setScalar(1 + Math.sin(t * 1.3 + 0.8) * 0.006);

    let turnY = look.x * 0.45;
    let nodX = look.y * 0.22;
    let tiltZ = -look.x * 0.08;
    let browLift = 0;
    if (mood === "thinking") {
      tiltZ = 0.2 + Math.sin(t * 2) * 0.05;
      nodX = -0.15;
      turnY = Math.sin(t * 1.1) * 0.3;
      browLift = 0.05;
    } else if (mood === "happy") {
      root.position.y += Math.max(0, Math.sin(Math.min(since, 1) * Math.PI * 2.5)) * 0.22 * Math.max(0, 1 - since);
      nodX = Math.sin(since * 10) * 0.12 * Math.max(0, 1 - since);
      if (since > 1.3) mood = "idle";
    } else if (mood === "butt") {
      const p = Math.min(since / 0.9, 1);
      nodX = p < 0.45 ? -0.32 * (p / 0.45) : 0.5 * Math.sin(((p - 0.45) / 0.55) * Math.PI);
      browLift = -0.03;
      if (since > 1.1) mood = "idle";
    }
    head.rotation.y += (turnY - head.rotation.y) * 0.1;
    head.rotation.x += (nodX - head.rotation.x) * 0.1;
    head.rotation.z += (tiltZ - head.rotation.z) * 0.1;
    brows.forEach((brow) => (brow.position.y += (browLift - brow.position.y) * 0.15));

    // Pupils follow the cursor; while thinking, they look up and away.
    const px = mood === "thinking" ? 0.035 : look.x * 0.04;
    const py = mood === "thinking" ? 0.045 : -look.y * 0.035;
    pupils.forEach((pupil) => pupil.position.set(px, py, 0.1));

    if (t > nextBlink) {
      blinkAt = t;
      nextBlink = t + 2.2 + Math.random() * 3.5;
    }
    const b = (t - blinkAt) / 0.18;
    const closed = b >= 0 && b < 1 ? Math.sin(b * Math.PI) : 0;
    lids.forEach((lid) => (lid.rotation.x = -1.35 + closed * 1.55));

    if (t > nextFlick) {
      flickAt = t;
      flickSide = Math.random() < 0.5 ? 0 : 1;
      nextFlick = t + 3.5 + Math.random() * 5;
    }
    const f = (t - flickAt) / 0.35;
    ears.forEach(({ pivot, side }, i) => {
      const flick = i === flickSide && f >= 0 && f < 1 ? Math.sin(f * Math.PI) * 0.35 : 0;
      pivot.rotation.z = side * (-0.18 + flick);
    });

    render();
  }

  if (reduced) {
    rambo.horns.forEach((horn) => horn.geometry.setDrawRange(0, Infinity));
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
    console.warn("Rambo 3D could not start:", error);
  }
}
