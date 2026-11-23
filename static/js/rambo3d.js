// Rambo in 3D, for the Ask Rambo page: a realistic bighorn ram, built from
// code. No downloaded model, no college marks.
//
//   * Head and bust are sculpted as signed distance fields (skull, Roman nose,
//     muzzle, jaw, cheeks, eye sockets, neck, shoulders), blended smoothly and
//     turned into meshes with Three.js's MarchingCubes.
//   * Short fur is shell-rendered: a stack of slightly larger copies of each
//     mesh, each keeping fewer "strands", for a soft, fuzzy outline.
//   * Horns follow a full ram's curl with a flattened, ridged cross-section
//     and growth rings.
//   * Amber eyes with a ram's horizontal pupils, real eyelids that blink.
//   * He breathes, blinks, flicks an ear, and looks toward the cursor. He
//     reacts to the chat: thinking while Rambo looks something up, a nod
//     when the answer lands, and a headbutt when you click him.
//
// Decorative only: the canvas is aria-hidden. With reduced motion he holds
// still. Without WebGL the flat SVG Rambo stays.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { MarchingCubes } from "three/addons/objects/MarchingCubes.js";

const stage = document.querySelector("[data-rambo-3d]");
// Phones and low-core laptops get fewer fur shells and fewer pixels.
const LITE =
  window.matchMedia("(pointer: coarse)").matches || (navigator.hardwareConcurrency || 8) <= 4;

const HAIR = new THREE.Color(0x6b553f);
const HAIR_DARK = new THREE.Color(0x4f3f2f);
const MUZZLE = new THREE.Color(0xd8cdb8);
const NOSE = new THREE.Color(0x3b332d);
const HORN_BASE = new THREE.Color(0x7d6a4f);
const HORN_TIP = new THREE.Color(0xc4b38f);

function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
  } catch {
    return false;
  }
}

// -- signed distance fields ---------------------------------------------------

function ellipsoid(c, r, tiltX = 0) {
  const cos = Math.cos(tiltX);
  const sin = Math.sin(tiltX);
  return (x, y, z) => {
    let py = y - c[1];
    let pz = z - c[2];
    if (tiltX) [py, pz] = [py * cos - pz * sin, py * sin + pz * cos];
    const px = (x - c[0]) / r[0];
    const qy = py / r[1];
    const qz = pz / r[2];
    const k0 = Math.hypot(px, qy, qz);
    const k1 = Math.hypot(px / r[0], qy / r[1], qz / r[2]);
    return k1 === 0 ? -Math.min(...r) : (k0 * (k0 - 1)) / k1;
  };
}

function capsule(a, b, r) {
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const len2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2;
  return (x, y, z) => {
    const ap = [x - a[0], y - a[1], z - a[2]];
    const h = THREE.MathUtils.clamp((ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / len2, 0, 1);
    return Math.hypot(ap[0] - ab[0] * h, ap[1] - ab[1] * h, ap[2] - ab[2] * h) - r;
  };
}

function smin(a, b, k) {
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.min(a, b) - h * h * k * 0.25;
}

/** Union of shapes with smooth blends; `cuts` are carved out smoothly. */
function blend(shapes, k, cuts = [], kCut = 0.05) {
  return (x, y, z) => {
    let d = shapes[0](x, y, z);
    for (let i = 1; i < shapes.length; i++) d = smin(d, shapes[i](x, y, z), k);
    for (const cut of cuts) d = -smin(-d, cut(x, y, z), kCut);
    return d;
  };
}

/** Polygonize an SDF inside a cube of half-width `extent` around `center`.
 *  MarchingCubes skips the outermost cells, so keep shapes a little inside the
 *  cube or they come out sliced flat. Returns a static geometry. */
function sculpt(sdf, { resolution, extent, colorAt, center = [0, 0, 0] }) {
  const [cx, cy, cz] = center;
  const mc = new MarchingCubes(resolution, new THREE.MeshBasicMaterial(), false, false, 160000);
  const iso = mc.isolation;
  const gain = 600 / extent;
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
  for (let i = 0; i < positions.length; i += 3) {
    positions[i] = positions[i] * extent + cx;
    positions[i + 1] = positions[i + 1] * extent + cy;
    positions[i + 2] = positions[i + 2] * extent + cz;
  }
  // MarchingCubes leaves normals as raw field gradients; the fur shells push
  // along them, so they must be unit length.
  const normals = mc.normalArray.slice(0, count * 3);
  for (let i = 0; i < normals.length; i += 3) {
    const len = Math.hypot(normals[i], normals[i + 1], normals[i + 2]) || 1;
    normals[i] /= len;
    normals[i + 1] /= len;
    normals[i + 2] /= len;
  }
  const colors = new Float32Array(count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < count; i++) {
    colorAt(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2], c);
    colors.set([c.r, c.g, c.b], i * 3);
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

const smooth = THREE.MathUtils.smoothstep;

// -- fur ------------------------------------------------------------------------

/** Shell fur: N materials, each pushing the surface out a little further and
 *  keeping fewer strands, darker at the root and lighter at the tips. */
function furShells(geometry, { shells, length, density, gravity = 0.35 }) {
  const group = new THREE.Group();
  for (let i = 1; i <= shells; i++) {
    const t = i / shells;
    const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 });
    material.onBeforeCompile = (shader) => {
      shader.uniforms.uShell = { value: t };
      shader.uniforms.uLen = { value: length };
      shader.uniforms.uDensity = { value: density };
      shader.uniforms.uGravity = { value: gravity };
      shader.vertexShader = shader.vertexShader
        .replace(
          "#include <common>",
          "#include <common>\nuniform float uShell; uniform float uLen; uniform float uGravity;\nvarying vec3 vObj;",
        )
        .replace(
          "#include <begin_vertex>",
          "#include <begin_vertex>\nvObj = position;\ntransformed += normal * uShell * uLen;\ntransformed.y -= uShell * uShell * uLen * uGravity;",
        );
      shader.fragmentShader = shader.fragmentShader
        .replace(
          "#include <common>",
          `#include <common>
uniform float uShell; uniform float uDensity;
varying vec3 vObj;
float hash13(vec3 p) { p = fract(p * 0.1031); p += dot(p, p.zyx + 31.32); return fract((p.x + p.y) * p.z); }`,
        )
        .replace(
          "#include <color_fragment>",
          `#include <color_fragment>
float strand = hash13(floor(vObj * uDensity));
if (strand < uShell * 0.92) discard;
diffuseColor.rgb *= mix(0.62, 1.12, uShell);`,
        );
    };
    material.customProgramCacheKey = () => `rambo-fur-${i}-${shells}`;
    const mesh = new THREE.Mesh(geometry, material);
    mesh.renderOrder = i;
    group.add(mesh);
  }
  return group;
}

// -- parts ----------------------------------------------------------------------

function headGeometry() {
  const sdf = blend(
    [
      ellipsoid([0, 0.22, -0.28], [0.4, 0.4, 0.46]), // cranium
      ellipsoid([0, 0.16, 0.1], [0.31, 0.3, 0.44], -0.2), // brow and Roman nose
      ellipsoid([0, -0.08, 0.58], [0.175, 0.2, 0.42], -0.3), // muzzle
      ellipsoid([0, -0.18, 0.9], [0.15, 0.14, 0.13]), // nose
      ellipsoid([0, -0.3, 0.42], [0.18, 0.12, 0.34], -0.15), // lower jaw
      ellipsoid([0.24, -0.04, 0.02], [0.17, 0.24, 0.28]), // cheeks
      ellipsoid([-0.24, -0.04, 0.02], [0.17, 0.24, 0.28]),
      ellipsoid([0.22, 0.44, -0.04], [0.15, 0.12, 0.15]), // horn bases
      ellipsoid([-0.22, 0.44, -0.04], [0.15, 0.12, 0.15]),
    ],
    0.14,
    [
      ellipsoid([0.29, 0.13, 0.27], [0.1, 0.09, 0.09]), // eye sockets
      ellipsoid([-0.29, 0.13, 0.27], [0.1, 0.09, 0.09]),
    ],
  );
  return sculpt(sdf, {
    resolution: 96,
    extent: 1.05,
    center: [0, 0.08, 0.16],
    colorAt(x, y, z, c) {
      c.copy(HAIR).lerp(HAIR_DARK, smooth(y, 0.05, 0.55) * 0.8);
      // A ram's white muzzle and a pale patch under the eyes.
      const muzzle = smooth(z, 0.62, 0.8) * (1 - smooth(y, -0.04, 0.08));
      c.lerp(MUZZLE, muzzle);
      // The bare, dark nose pad at the very front of the muzzle.
      c.lerp(NOSE, smooth(z, 0.86, 0.95) * (1 - smooth(y, -0.02, 0.06)) * smooth(y, -0.36, -0.28));
    },
  });
}

function bustGeometry() {
  const sdf = blend(
    [
      capsule([0, 0.05, -0.12], [0, -0.85, -0.3], 0.27), // neck
      ellipsoid([0, -1.12, -0.18], [0.62, 0.42, 0.5]), // chest
      ellipsoid([0, -1.02, -0.6], [0.78, 0.36, 0.55]), // shoulders
    ],
    0.3,
  );
  return sculpt(sdf, {
    resolution: 64,
    extent: 1.6,
    center: [0, -0.5, -0.2],
    colorAt(x, y, z, c) {
      c.copy(HAIR).lerp(HAIR_DARK, smooth(-z, 0.2, 0.8) * 0.7);
      c.lerp(MUZZLE, smooth(z, 0.15, 0.35) * smooth(-y, 0.2, 0.45) * (1 - smooth(-y, 0.7, 0.95)) * 0.35); // pale throat
    },
  });
}

/** One horn: a full bighorn curl, flattened and ridged, root to tip. The
 *  path is laid out in head space the way the horn grows: up and back off
 *  the skull, down behind the ear, then forward around the cheek. */
function hornGeometry(side) {
  const path = [
    [0.22, 0.5, -0.02],
    [0.34, 0.68, -0.22],
    [0.46, 0.6, -0.5],
    [0.56, 0.3, -0.62],
    [0.62, -0.06, -0.52],
    [0.64, -0.3, -0.24],
    [0.6, -0.32, 0.08],
    [0.62, -0.14, 0.3],
    [0.68, 0.06, 0.36],
  ];
  const points = path.map(([x, y, z]) => new THREE.Vector3(side * x, y, z));
  const curve = new THREE.CatmullRomCurve3(points, false, "centripetal");
  const tubular = 260;
  const radial = 32;
  const geo = new THREE.TubeGeometry(curve, tubular, 1, radial, false);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const center = new THREE.Vector3();
  const v = new THREE.Vector3();
  const n = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Color();
  for (let i = 0; i <= tubular; i++) {
    const t = i / tubular;
    curve.getPointAt(t, center);
    n.copy(geo.normals[i]);
    b.copy(geo.binormals[i]);
    const base = 0.17 * Math.pow(1 - t, 0.55) + 0.02;
    // Growth: fine ridges everywhere, a deeper annual ring every so often.
    const fine = Math.pow(Math.abs(Math.sin(t * Math.PI * 34)), 0.4);
    const annual = Math.pow(Math.abs(Math.sin(t * Math.PI * 6)), 6);
    const ridge = 1 + 0.035 * fine - 0.06 * annual * (1 - t);
    c.copy(HORN_BASE).lerp(HORN_TIP, Math.pow(t, 0.8)).multiplyScalar(0.84 + 0.16 * fine - 0.18 * annual);
    for (let j = 0; j <= radial; j++) {
      const k = i * (radial + 1) + j;
      v.fromBufferAttribute(pos, k).sub(center);
      // Flatten the cross-section: a ram's horn is wider than it is deep.
      const along = v.dot(n);
      const across = v.dot(b);
      v.copy(n).multiplyScalar(along * base * ridge).addScaledVector(b, across * base * ridge * 0.8).add(center);
      pos.setXYZ(k, v.x, v.y, v.z);
      colors.set([c.r, c.g, c.b], k * 3);
    }
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return geo;
}

/** Amber iris, horizontal rectangular pupil, on an equirectangular map whose
 *  center (u=0.25, v=0.5) lands on the eyeball's +z side. */
function eyeTexture() {
  const w = 512;
  const h = 256;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#2b1d10";
  ctx.fillRect(0, 0, w, h);
  const cx = w * 0.25;
  const cy = h * 0.5;
  const iris = ctx.createRadialGradient(cx, cy, 6, cx, cy, 64);
  iris.addColorStop(0, "#f2b23a");
  iris.addColorStop(0.55, "#c98a1f");
  iris.addColorStop(0.9, "#7a4a12");
  iris.addColorStop(1, "#2b1d10");
  ctx.fillStyle = iris;
  ctx.beginPath();
  ctx.arc(cx, cy, 64, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(90,55,15,0.35)"; // iris fibers
  for (let i = 0; i < 90; i++) {
    const a = (i / 90) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * 18, cy + Math.sin(a) * 18);
    ctx.lineTo(cx + Math.cos(a) * 60, cy + Math.sin(a) * 60);
    ctx.stroke();
  }
  ctx.fillStyle = "#0b0704"; // the horizontal pupil
  ctx.beginPath();
  ctx.roundRect(cx - 34, cy - 10, 68, 20, 9);
  ctx.fill();
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

function buildRambo() {
  const hair = new THREE.MeshPhysicalMaterial({
    vertexColors: true,
    roughness: 0.92,
    sheen: 0.7,
    sheenRoughness: 0.6,
    sheenColor: new THREE.Color(0xd8c3a0),
  });
  const horn = new THREE.MeshPhysicalMaterial({
    vertexColors: true,
    roughness: 0.58,
    clearcoat: 0.25,
    clearcoatRoughness: 0.5,
  });
  const eyeMat = new THREE.MeshPhysicalMaterial({
    map: eyeTexture(),
    roughness: 0.08,
    clearcoat: 1,
    clearcoatRoughness: 0.02,
  });
  const lidMat = new THREE.MeshStandardMaterial({ color: HAIR_DARK, roughness: 0.9 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1a1410, roughness: 0.45 });
  const innerEar = new THREE.MeshStandardMaterial({ color: 0xd9b8a2, roughness: 0.8 });
  const scarf = new THREE.MeshPhysicalMaterial({
    color: 0x00693e,
    roughness: 0.75,
    sheen: 1,
    sheenColor: new THREE.Color(0x6fbd91),
  });

  const root = new THREE.Group();
  const body = new THREE.Group();
  root.add(body);

  const bustGeo = bustGeometry();
  const bust = new THREE.Mesh(bustGeo, hair);
  bust.receiveShadow = true;
  body.add(bust, furShells(bustGeo, { shells: LITE ? 4 : 8, length: 0.035, density: 180 }));

  const collar = new THREE.Mesh(new THREE.TorusGeometry(0.31, 0.075, 20, 72), scarf);
  collar.rotation.x = Math.PI / 2 + 0.25;
  collar.position.set(0, -0.48, -0.2);
  collar.castShadow = true;
  const knot = new THREE.Mesh(new THREE.SphereGeometry(0.09, 24, 16), scarf);
  knot.position.set(0.05, -0.62, 0.1);
  const tail = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.26, 8, 16), scarf);
  tail.position.set(0.1, -0.82, 0.12);
  tail.rotation.set(0.25, 0, 0.3);
  body.add(collar, knot, tail);

  // The neck pivot carries the head, so nods and tilts swing from the neck.
  const neck = new THREE.Group();
  neck.position.set(0, -0.15, -0.15);
  body.add(neck);
  const head = new THREE.Group();
  head.position.set(0, 0.42, 0.1);
  head.scale.setScalar(1.12);
  neck.add(head);

  const headGeo = headGeometry();
  const skull = new THREE.Mesh(headGeo, hair);
  skull.castShadow = true;
  skull.receiveShadow = true;
  head.add(skull, furShells(headGeo, { shells: LITE ? 5 : 10, length: 0.018, density: 280 }));

  // Nostrils and mouth.
  for (const side of [-1, 1]) {
    const nostril = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), dark);
    nostril.scale.set(0.03, 0.008, 0.012);
    nostril.position.set(side * 0.058, -0.15, 0.99);
    nostril.rotation.set(0.2, side * 0.4, side * -0.9);
    head.add(nostril);
  }
  const mouthCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-0.11, -0.31, 0.86),
    new THREE.Vector3(-0.04, -0.33, 0.95),
    new THREE.Vector3(0, -0.315, 0.965),
    new THREE.Vector3(0.04, -0.33, 0.95),
    new THREE.Vector3(0.11, -0.31, 0.86),
  ]);
  head.add(new THREE.Mesh(new THREE.TubeGeometry(mouthCurve, 40, 0.007, 8, false), dark));

  // Eyes, set to the sides like a real ram's, with upper lids for blinking.
  const lids = [];
  const eyes = [];
  for (const side of [-1, 1]) {
    const eye = new THREE.Group();
    eye.position.set(side * 0.285, 0.13, 0.27);
    eye.rotation.y = side * 0.62;
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.082, 48, 32), eyeMat);
    const lid = new THREE.Mesh(new THREE.SphereGeometry(0.089, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), lidMat);
    lid.rotation.x = -1.15; // open
    const lower = new THREE.Mesh(new THREE.TorusGeometry(0.08, 0.014, 8, 32, Math.PI), lidMat);
    lower.rotation.set(0, 0, Math.PI);
    lower.position.z = 0.012;
    eye.add(ball, lid, lower);
    head.add(eye);
    lids.push(lid);
    eyes.push(ball);
  }

  // Ears: long leaves pointing out and down, tucked under the horns.
  const ears = [];
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.38, -0.02, -0.12);
    const outer = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), hair);
    outer.scale.set(0.16, 0.05, 0.075);
    outer.position.x = side * 0.13;
    const inner = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), innerEar);
    inner.scale.set(0.12, 0.025, 0.05);
    inner.position.set(side * 0.14, 0.02, 0.018);
    pivot.add(outer, inner);
    pivot.rotation.set(0.15, side * -0.5, side * -0.55);
    head.add(pivot);
    ears.push({ pivot, side });
  }

  // Horns, rooted on the horn bases sculpted into the skull (head space).
  for (const side of [-1, 1]) {
    const mesh = new THREE.Mesh(hornGeometry(side), horn);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    head.add(mesh);
  }

  return { root, body, neck, head, lids, eyes, ears };
}

// -- scene ----------------------------------------------------------------------

function start() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, LITE ? 1.5 : 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute("aria-hidden", "true");
  renderer.domElement.className = "rambo-3d-canvas";

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;

  const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 50);
  camera.position.set(0, 0.35, 5.8);
  camera.lookAt(0, -0.05, 0);

  scene.add(new THREE.HemisphereLight(0xfff4e6, 0x2a2118, 0.45));
  const key = new THREE.DirectionalLight(0xfff0dc, 2.6);
  key.position.set(2.5, 3.5, 4);
  key.castShadow = true;
  key.shadow.mapSize.setScalar(LITE ? 1024 : 2048);
  key.shadow.radius = 5;
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xbcd6ff, 0.6);
  fill.position.set(-4, 0.5, 2);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xffe7c4, 2.2);
  rim.position.set(-2.5, 2.5, -4);
  scene.add(rim);
  const rim2 = new THREE.DirectionalLight(0xa3d7b8, 1.2); // a touch of RamHub green
  rim2.position.set(3, 1, -3);
  scene.add(rim2);

  const rambo = buildRambo();
  // Three-quarter view: shows the long face and the full curl of the near horn.
  rambo.root.rotation.y = -0.72;
  rambo.root.position.y = 0.1;
  scene.add(rambo.root);

  stage.appendChild(renderer.domElement);
  stage.classList.add("is-3d");

  function resize() {
    const { width, height } = stage.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = width / height < 1 ? 34 : 26;
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

  let nextBlink = 1.2;
  let blinkAt = -10;
  let nextFlick = 3;
  let flickAt = -10;
  let flickSide = 1;

  function tick() {
    const t = clock.getElapsedTime();
    const since = t - moodStart;
    const { body, neck, head, lids, ears } = rambo;

    look.x += (look.tx - look.x) * 0.05;
    look.y += (look.ty - look.y) * 0.05;

    // Breathing: the chest rises a touch; the whole body sways slowly.
    const breath = Math.sin(t * 1.25);
    body.scale.set(1 + breath * 0.006, 1 + breath * 0.01, 1 + breath * 0.006);
    body.rotation.y = Math.sin(t * 0.3) * 0.04;

    let nodX = look.y * 0.18;
    let turnY = look.x * 0.3;
    let tiltZ = -look.x * 0.05;
    if (mood === "thinking") {
      tiltZ = 0.16 + Math.sin(t * 1.6) * 0.04;
      nodX = -0.16;
      turnY = 0.25 + Math.sin(t * 0.9) * 0.2;
    } else if (mood === "happy") {
      nodX = Math.sin(since * 10) * 0.12 * Math.max(0, 1 - since / 1.1);
      if (since > 1.3) mood = "idle";
    } else if (mood === "butt") {
      const p = Math.min(since / 0.95, 1);
      nodX = p < 0.45 ? -0.3 * (p / 0.45) : 0.5 * Math.sin(((p - 0.45) / 0.55) * Math.PI);
      if (since > 1.1) mood = "idle";
    }
    neck.rotation.x += (nodX - neck.rotation.x) * 0.1;
    head.rotation.y += (turnY - head.rotation.y) * 0.08;
    head.rotation.z += (tiltZ - head.rotation.z) * 0.08;

    // Blink: the upper lid comes down and back up in about a fifth of a second.
    if (t > nextBlink) {
      blinkAt = t;
      nextBlink = t + 2.5 + Math.random() * 4 - (Math.random() < 0.2 ? 2 : 0);
    }
    const b = (t - blinkAt) / 0.2;
    const closed = b >= 0 && b < 1 ? Math.sin(b * Math.PI) : 0;
    lids.forEach((lid) => (lid.rotation.x = -1.15 + closed * 1.35));

    // An ear flick now and then.
    if (t > nextFlick) {
      flickAt = t;
      flickSide = Math.random() < 0.5 ? 0 : 1;
      nextFlick = t + 3.5 + Math.random() * 5;
    }
    const f = (t - flickAt) / 0.35;
    ears.forEach(({ pivot, side }, i) => {
      const flick = i === flickSide && f >= 0 && f < 1 ? Math.sin(f * Math.PI) * 0.4 : 0;
      const perk = mood === "thinking" ? 0.25 : 0;
      pivot.rotation.z = side * (-0.55 + flick + perk);
    });

    render();
  }

  if (reduced) {
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
