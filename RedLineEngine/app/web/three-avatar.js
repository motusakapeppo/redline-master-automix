/**
 * three-avatar.js — Three.js 3D stylized skull avatar with reactive ring,
 * earrings, particles, bloom, and cinematic post-processing.
 *
 * ES module, loaded via importmap. Exposes window.avatarAPI.
 */

import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// ─── Module state ───────────────────────────────────────────────────────────

let scene, camera, renderer, composer;
let skull, craniumMesh, eyeLeft, eyeRight, noseCavity;
let ring, ringOriginalPositions = null;
let ringGlowParticles = null;
let earrings = [];
let particles, particleVelocities, particlePhases;
let animFrameId = null;
let clock = new THREE.Clock();
// DSP state variables (decay per frame)
let compressionIntensity = 0;
let deesserFlash = 0;
let bpmPhase = 0;
let bpmInterval = 0.5;
let listeningMode = false;
let deepScanMode = false;
let activityLevel = 0.5;
let ringWaveDecay = 0.92;
const ringColorTarget = new THREE.Color('#FF003F');
const ringColorCurrent = new THREE.Color('#FF003F');
let ringRotationSpeed = 0.003;
let particleOrbitSpeed = 0.0008;
const skullVibrateOffset = new THREE.Vector3();
let systemReadyPulse = 0;
let celebrationWave = 0;
let auditionTilt = 0;
let idleFloatPhase = 0;

// The skull GLB ships as a fully rigged, animated character (baked clips:
// Idle, Yes, No, Bite_Front, Bite_InPlace, Dance, HitRecieve, ...) --
// playing those directly through an AnimationMixer is what makes this
// read as alive (natural idle sway, a real head nod/shake, an actual bite/
// mouth-open motion) instead of hand-rolled bone-rotation guesses.
let mixer = null;
let skullActions = {};
let currentAction = null;

// Natural head glances: real people don't slowly and constantly swivel
// their head, they hold still, then snap a quick glance somewhere, hold
// again. State machine below alternates HOLD (still) and TURN (moving
// toward a new random target) phases with randomized durations/angles.
let lookPhase = 'hold'; // 'hold' | 'turn'
let lookPhaseStartTime = 0;
let lookPhaseEndTime = 0;
let lookFromY = 0, lookFromX = 0;
let lookTargetY = 0, lookTargetX = 0;
let lookCurrentY = 0, lookCurrentX = 0;

// ─── Constants ─────────────────────────────────────────────────────────────

const RING_SEGMENTS = 72;
const RING_RADIUS = 1.8;
const RING_TUBE = 0.025;
const PARTICLE_COUNT = 5000;
const PARTICLE_INNER = 1.8;
const PARTICLE_OUTER = 4.0;
const GLOW_PARTICLE_COUNT = 120;

// ─── Initialization ─────────────────────────────────────────────────────────

function init(canvasId) {
  try {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
      console.warn('[three-avatar] Canvas #' + canvasId + ' not found');
      return;
    }

    scene = new THREE.Scene();
    // Transparent background -- no solid fill means no visible "box" behind
    // the skull; it reads as a cutout sitting directly on the page instead
    // of a rendered rectangle.
    scene.background = null;
    scene.fog = new THREE.Fog('#0A0A0A', 5, 8);

    camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 10);
    // z must clear PARTICLE_OUTER (4.0) -- at 3.8 the camera sat *inside*
    // the particle shell, with additive-blended particles between the lens
    // and the skull (and behind it) washing the whole frame into a single
    // blown-out bloom blob with no visible geometry. 4.8 clears the shell
    // with margin while staying mostly ahead of the fog's near falloff (5).
    camera.position.set(0, 0.3, 4.8);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    // Was 1.2 + strong bloom -- blew every material out to solid white with
    // no visible skull detail (eye sockets, teeth, jaw all disappeared into
    // the glow). Pulled both way down.
    renderer.toneMappingExposure = 0.75;

    // Environment map
    const pmremGenerator = new THREE.PMREMGenerator(renderer);
    const envTexture = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTexture;
    pmremGenerator.dispose();

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x222244, 0.3);
    scene.add(ambientLight);

    const rimLight = new THREE.DirectionalLight(0xFF003F, 0.6);
    rimLight.position.set(-2, 1, -2);
    scene.add(rimLight);

    const keyLight = new THREE.DirectionalLight(0xFFFFFF, 0.8);
    keyLight.position.set(2, 1, 2);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x4488FF, 0.3);
    fillLight.position.set(0, -1, 2);
    scene.add(fillLight);

    // Composer -- bloom + vignette dropped for now. UnrealBloomPass composites
    // additively and reliably breaks canvas alpha transparency (the whole
    // point of the transparent-background change above), and combined with
    // 5000 additive-blended particles it was blowing every material out to
    // solid white -- no skull detail (eye sockets, teeth, jaw) was visible,
    // just a bright blob. Plain render+output keeps the actual geometry
    // visible; bloom can come back later, tuned much lower, once alpha
    // compositing through it is verified to actually work in this Three
    // version.
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    composer.addPass(new OutputPass());

    // buildRing() dropped per direct feedback ("elimina quella linea rossa")
    // -- every reference to `ring` elsewhere is already null-guarded, so
    // simply never constructing it removes the ring cleanly with no
    // further changes needed. buildRingGlowParticles() / buildParticles()
    // were dropped earlier in the same pass (visual clutter, not
    // atmosphere, once the background went transparent).
    buildSkull();
    // buildEarrings() dropped per direct feedback ("evitiamo di metterli,
    // davvero, non ci servono") -- every `for (const e of earrings)` loop
    // elsewhere just iterates an empty array, so skipping this removes
    // them cleanly with no other changes needed.

    clock = new THREE.Clock();
    animate();

    console.log('[three-avatar] Initialized');
  } catch (err) {
    console.error('[three-avatar] Init error:', err);
  }
}

// ─── Skull Geometry ─────────────────────────────────────────────────────────

const SKULL_MODEL_URL = 'assets/skull.glb';
// A faint warm-bone tint multiplied over the source asset's own painted
// texture -- not a flat override. The original material was being replaced
// entirely with one flat silver color, which is why the model rendered as
// a nearly featureless white shape: it discarded the asset's actual
// texture map (shading, cracks, tonal variation) instead of keeping it.
// Cool silver-grey rather than a warm bone tone -- the source texture's own
// warm/khaki base color read as off-palette against the rest of the UI
// (black/red/silver). This multiplies toward that cooler, more metallic
// range while still preserving the texture's own shading/detail/variation.
const SKULL_TINT = '#AEB4C2';

function buildSkull(onReady) {
  const group = new THREE.Group();
  skull = group;
  scene.add(skull);

  new GLTFLoader().load(
    SKULL_MODEL_URL,
    (gltf) => {
      const model = gltf.scene;
      model.traverse((child) => {
        if (child.isMesh) {
          const sourceMap = child.material && child.material.map ? child.material.map : null;
          if (sourceMap) sourceMap.colorSpace = THREE.SRGBColorSpace;
          // Rebuilt as MeshStandardMaterial (the source used
          // KHR_materials_unlit, flat/shadeless) so it actually responds
          // to the rim/key/fill lighting already set up in the scene,
          // while keeping the real texture map for genuine surface detail
          // and color variation instead of one uniform flat tone.
          child.material = new THREE.MeshStandardMaterial({
            map: sourceMap,
            color: SKULL_TINT,
            metalness: 0.15,
            roughness: 0.65,
            envMapIntensity: 1.0,
          });
        }
      });

      // Normalize scale/position: the source asset's own units/origin are
      // arbitrary (typical for a downloaded asset) -- center it and scale
      // it to a consistent ~1.4-unit-tall footprint so the existing
      // camera framing, earring placement, and reaction animations (which
      // were all tuned against that scale) still line up.
      const box = new THREE.Box3().setFromObject(model);
      const size = new THREE.Vector3();
      box.getSize(size);
      const center = new THREE.Vector3();
      box.getCenter(center);
      const targetHeight = 1.4;
      const scale = targetHeight / Math.max(size.y, 0.001);
      model.scale.setScalar(scale);

      // Re-measure after scaling to center it precisely at the origin.
      const scaledBox = new THREE.Box3().setFromObject(model);
      const scaledCenter = new THREE.Vector3();
      scaledBox.getCenter(scaledCenter);
      model.position.sub(scaledCenter);

      craniumMesh = model;
      group.add(model);

      // Small emissive markers for the reactive "eye glow" (de-esser flash,
      // deep-scan pulse, etc.) -- positioned at an approximate eye-socket
      // location relative to the model's own (now-normalized) bounding box
      // rather than baked-in coordinates tuned for the old procedural mesh.
      const eyeMat = new THREE.MeshStandardMaterial({
        color: '#FF003F',
        emissive: '#FF003F',
        emissiveIntensity: 0.5,
      });
      const eyeY = scaledBox.max.y * 0.35;
      const eyeZ = scaledBox.max.z * 0.7;
      const eyeX = size.x * scale * 0.16;

      eyeLeft = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 12), eyeMat);
      eyeLeft.position.set(-eyeX, eyeY, eyeZ);
      group.add(eyeLeft);

      eyeRight = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 12), eyeMat.clone());
      eyeRight.position.set(eyeX, eyeY, eyeZ);
      group.add(eyeRight);

      // Set up the baked animation clips on the model's own armature.
      if (gltf.animations && gltf.animations.length > 0) {
        mixer = new THREE.AnimationMixer(model);
        for (const clip of gltf.animations) {
          skullActions[clip.name] = mixer.clipAction(clip);
        }
        playSkullAction('Idle', { loop: true });
      }

      if (typeof onReady === 'function') onReady();
    },
    undefined,
    (err) => {
      console.error('[three-avatar] Failed to load skull model:', err);
      if (typeof onReady === 'function') onReady();
    }
  );
}

// ─── Props (headphones, vinyl, cassette, instruments) ──────────────────────
//
// Same normalize-then-tint treatment as the skull (bounding-box scale to a
// consistent height, keep the source texture but tint it toward the
// black/red/silver palette instead of a flat recolor) so these read as
// belonging to the same character instead of a dropped-in stock asset.
// All hidden by default; shown/hidden by the DSP-driven hooks below.

const PROP_CONFIGS = {
  headphones: { url: 'assets/headphones.glb', targetHeight: 1.7, position: [0, 0.75, 0], tint: '#9098A8' },
  vinyl: { url: 'assets/vinyl.glb', targetHeight: 1.3, position: [1.5, -0.2, -0.3], tint: '#7A8290', spin: true },
  cassette: { url: 'assets/cassette.glb', targetHeight: 0.9, position: [1.4, -0.1, 0], tint: '#8890A0' },
  music_note: { url: 'assets/music_note.glb', targetHeight: 0.8, position: [-1.4, 0.6, 0], tint: '#C85068' },
  guitar: { url: 'assets/guitar.glb', targetHeight: 1.9, position: [-1.5, -0.6, 0], tint: '#8890A0' },
  bass: { url: 'assets/bass_guitar.glb', targetHeight: 1.9, position: [-1.5, -0.6, 0], tint: '#8890A0' },
  piano: { url: 'assets/piano.glb', targetHeight: 1.4, position: [-1.5, -0.5, 0], tint: '#8890A0' },
  wind: { url: 'assets/kazoo.glb', targetHeight: 0.9, position: [-1.4, -0.2, 0], tint: '#8890A0' },
};

const INSTRUMENT_CYCLE_ORDER = ['guitar', 'bass', 'piano', 'wind'];
const INSTRUMENT_CYCLE_INTERVAL_MS = 1800;

const _props = {}; // name -> THREE.Group, added to scene, .visible toggled
const _propLoading = {}; // name -> true while a load is in flight (avoid double-loading)
let _instrumentCycleTimer = null;

function _loadProp(name, onReady) {
  if (_props[name] || _propLoading[name]) {
    if (_props[name] && typeof onReady === 'function') onReady(_props[name]);
    return;
  }
  const config = PROP_CONFIGS[name];
  if (!config) return;
  _propLoading[name] = true;

  new GLTFLoader().load(
    config.url,
    (gltf) => {
      const model = gltf.scene;
      const tintMaterial = new THREE.MeshStandardMaterial({
        map: null,
        color: config.tint,
        metalness: 0.3,
        roughness: 0.55,
        envMapIntensity: 1.0,
      });
      model.traverse((child) => {
        if (child.isMesh) {
          const sourceMap = child.material && child.material.map ? child.material.map : null;
          if (sourceMap) sourceMap.colorSpace = THREE.SRGBColorSpace;
          child.material = tintMaterial.clone();
          child.material.map = sourceMap;
        }
      });

      const box = new THREE.Box3().setFromObject(model);
      const size = new THREE.Vector3();
      box.getSize(size);
      const scale = config.targetHeight / Math.max(size.y, 0.001);
      model.scale.setScalar(scale);

      const scaledBox = new THREE.Box3().setFromObject(model);
      const center = new THREE.Vector3();
      scaledBox.getCenter(center);
      model.position.sub(center);

      const group = new THREE.Group();
      group.add(model);
      group.position.set(...config.position);
      group.visible = false;
      scene.add(group);

      _props[name] = group;
      delete _propLoading[name];
      if (typeof onReady === 'function') onReady(group);
    },
    undefined,
    (err) => {
      console.error(`[three-avatar] Failed to load prop "${name}":`, err);
      delete _propLoading[name];
    }
  );
}

function _hideAllPropVisuals() {
  for (const group of Object.values(_props)) group.visible = false;
}

function _hideAllProps() {
  _hideAllPropVisuals();
  if (_instrumentCycleTimer !== null) {
    clearInterval(_instrumentCycleTimer);
    _instrumentCycleTimer = null;
  }
}

function _showProp(name, keepCycleTimer = false) {
  if (keepCycleTimer) {
    _hideAllPropVisuals(); // called from the cycle's own tick -- don't cancel itself
  } else {
    _hideAllProps(); // any other trigger (headphones, cassette, single instrument) stops a running cycle
  }
  _loadProp(name, (group) => {
    group.visible = true;
  });
}

// See `lookPhase` state comment above. A real head turn accelerates into
// the motion and decelerates out of it (ease-in-out), over roughly half a
// second to a second -- not a linear snap, and not the 0.25s "flick" this
// used to do. Holds for 1.5-5s between glances.
function updateNaturalLook(time) {
  if (!skull) return;

  if (time >= lookPhaseEndTime) {
    if (lookPhase === 'hold') {
      lookPhase = 'turn';
      lookFromY = lookCurrentY;
      lookFromX = lookCurrentX;
      lookTargetY = (Math.random() - 0.5) * 0.7; // ~±20°
      lookTargetX = (Math.random() - 0.5) * 0.25; // ~±7°, heads tilt less than they turn
      lookPhaseStartTime = time;
      lookPhaseEndTime = time + 0.6 + Math.random() * 0.5;
    } else {
      lookPhase = 'hold';
      lookPhaseEndTime = time + 1.5 + Math.random() * 3.5;
    }
  }

  if (lookPhase === 'turn') {
    const span = Math.max(lookPhaseEndTime - lookPhaseStartTime, 0.001);
    const t = Math.min(1, Math.max(0, (time - lookPhaseStartTime) / span));
    // Smoothstep-style ease-in-out: accelerates into the turn, decelerates
    // out of it -- a linear/ease-out-only curve is what read as jerky.
    const eased = t * t * (3 - 2 * t);
    lookCurrentY = lookFromY + (lookTargetY - lookFromY) * eased;
    lookCurrentX = lookFromX + (lookTargetX - lookFromX) * eased;
  }

  skull.rotation.y = lookCurrentY;
  skull.rotation.x = lookCurrentX;
}

// Crossfades to a named baked clip. `loop: true` keeps it running (Idle);
// otherwise it plays once and falls back to Idle when it finishes -- a
// "gesture" (Yes/No/Bite_Front/Dance) that interrupts the idle sway
// briefly, the way a real head does, rather than replacing it forever.
function playSkullAction(name, { loop = false, fadeSeconds = 0.3 } = {}) {
  if (!mixer || !skullActions[name]) return;
  const next = skullActions[name];
  if (next === currentAction) return;

  next.reset();
  next.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, loop ? Infinity : 1);
  next.clampWhenFinished = !loop;
  next.fadeIn(fadeSeconds);
  next.play();

  if (currentAction) currentAction.fadeOut(fadeSeconds);
  currentAction = next;

  if (!loop) {
    const durationMs = (next.getClip().duration / next.timeScale) * 1000;
    setTimeout(() => {
      if (currentAction === next) playSkullAction('Idle', { loop: true });
    }, durationMs);
  }
}

// ─── Reactive Ring ──────────────────────────────────────────────────────────

function buildRing() {
  const geo = new THREE.TorusGeometry(RING_RADIUS, RING_TUBE, 8, RING_SEGMENTS);
  const mat = new THREE.MeshStandardMaterial({
    color: '#FF003F',
    emissive: '#FF003F',
    emissiveIntensity: 1.0,
    metalness: 0.3,
    roughness: 0.4,
  });
  ring = new THREE.Mesh(geo, mat);
  ring.position.y = 0.3;
  ring.rotation.x = Math.PI / 2;
  scene.add(ring);

  const pos = ring.geometry.attributes.position;
  ringOriginalPositions = new Float32Array(pos.array);
}

function deformRing(amplitudes) {
  if (!ring || !ringOriginalPositions) return;
  const pos = ring.geometry.attributes.position;
  const array = pos.array;
  const segCount = RING_SEGMENTS;

  for (let i = 0; i < segCount; i++) {
    const amp = amplitudes[i] || 0;
    for (let j = 0; j < 8; j++) {
      const idx = (i * 8 + j) * 3;
      array[idx + 1] = ringOriginalPositions[idx + 1] + amp;
    }
  }
  pos.needsUpdate = true;
  ring.geometry.computeVertexNormals();
}

// ─── Ring Glow Particles ────────────────────────────────────────────────────

function buildRingGlowParticles() {
  const positions = new Float32Array(GLOW_PARTICLE_COUNT * 3);
  const colors = new Float32Array(GLOW_PARTICLE_COUNT * 3);
  const sizes = new Float32Array(GLOW_PARTICLE_COUNT);

  const color = new THREE.Color();

  for (let i = 0; i < GLOW_PARTICLE_COUNT; i++) {
    const angle = (i / GLOW_PARTICLE_COUNT) * Math.PI * 2;
    const radius = RING_RADIUS + (Math.random() - 0.5) * 0.3;
    const yOff = (Math.random() - 0.5) * 0.2;

    positions[i * 3] = Math.cos(angle) * radius;
    positions[i * 3 + 1] = 0.3 + yOff;
    positions[i * 3 + 2] = Math.sin(angle) * radius;

    color.setHSL(0.0, 1, 0.4 + Math.random() * 0.4);
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    sizes[i] = 0.015 + Math.random() * 0.025;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const mat = new THREE.PointsMaterial({
    size: 0.02,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
  });

  ringGlowParticles = new THREE.Points(geo, mat);
  scene.add(ringGlowParticles);
}

// ─── Earrings ────────────────────────────────────────────────────────────────

function buildEarrings() {
  const earMat = new THREE.MeshStandardMaterial({
    color: '#D4A017',
    metalness: 0.95,
    roughness: 0.1,
    envMapIntensity: 1.5,
  });

  const earGeo = new THREE.TorusGeometry(0.09, 0.018, 10, 14);

  // 3 on left side at different heights
  const leftPositions = [
    [-0.55, 0.5, 0.1],
    [-0.55, 0.28, 0.1],
    [-0.55, 0.06, 0.1],
  ];
  for (const pos of leftPositions) {
    const mesh = new THREE.Mesh(earGeo.clone(), earMat);
    mesh.position.set(pos[0], pos[1], pos[2]);
    mesh.userData.jingleIntensity = 0;
    mesh.userData.jinglePhase = Math.random() * Math.PI * 2;
    scene.add(mesh);
    earrings.push(mesh);
  }

  // 1 on right side
  const mesh = new THREE.Mesh(earGeo.clone(), earMat);
  mesh.position.set(0.55, 0.28, 0.1);
  mesh.userData.jingleIntensity = 0;
  mesh.userData.jinglePhase = Math.random() * Math.PI * 2;
  scene.add(mesh);
  earrings.push(mesh);
}

// ─── Particle System ────────────────────────────────────────────────────────

function buildParticles() {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const colors = new Float32Array(PARTICLE_COUNT * 3);
  const sizes = new Float32Array(PARTICLE_COUNT);
  particleVelocities = new Float32Array(PARTICLE_COUNT);
  particlePhases = new Float32Array(PARTICLE_COUNT);

  const colorA = new THREE.Color('#1A0005');
  const colorB = new THREE.Color('#FF003F');
  const colorC = new THREE.Color('#FF6600');

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = PARTICLE_INNER + Math.random() * (PARTICLE_OUTER - PARTICLE_INNER);

    positions[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
    positions[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * r;
    positions[i * 3 + 2] = Math.cos(phi) * r;

    const t = Math.random();
    const c = t < 0.7
      ? colorA.clone().lerp(colorB, t * 1.4)
      : colorB.clone().lerp(colorC, (t - 0.7) * 3.3);
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;

    sizes[i] = 0.008 + Math.random() * 0.035;
    particleVelocities[i] = 0.15 + Math.random() * 0.6;
    particlePhases[i] = Math.random() * Math.PI * 2;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const mat = new THREE.PointsMaterial({
    size: 0.025,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
  });

  particles = new THREE.Points(geo, mat);
  scene.add(particles);
}

// ─── Animation Loop ────────────────────────────────────────────────────────

function animate() {
  animFrameId = requestAnimationFrame(animate);
  const delta = Math.min(clock.getDelta(), 0.05);
  const time = clock.elapsedTime;

  // Decay state variables
  compressionIntensity *= ringWaveDecay;
  deesserFlash *= 0.85;
  if (systemReadyPulse > 0) systemReadyPulse -= delta * 1.5;
  if (celebrationWave > 0) celebrationWave -= delta * 0.4;

  // Idle floating
  idleFloatPhase += delta * 0.5;
  const floatY = Math.sin(idleFloatPhase) * 0.015;

  // Baked-clip playback (Idle/Yes/No/Bite_Front/Dance/...) drives the
  // actual body motion now -- this loop only adds the subtle vertical
  // breathing float and the natural, intermittent head glance below.
  if (mixer) mixer.update(delta);
  skull.position.y = -0.1 + floatY;
  updateNaturalLook(time);

  if (_props.vinyl && _props.vinyl.visible) {
    _props.vinyl.rotation.z -= delta * 2.2; // steady spin, independent of the skull's own motion
  }

  // Skull vibration from compression
  if (compressionIntensity > 0.01) {
    const amp = compressionIntensity * 0.04;
    skullVibrateOffset.set(
      (Math.random() - 0.5) * amp,
      (Math.random() - 0.5) * amp,
      (Math.random() - 0.5) * amp * 0.5
    );
    skull.position.x = skullVibrateOffset.x;
    skull.position.z = skullVibrateOffset.z;
  } else {
    skull.position.x += (0 - skull.position.x) * 0.05;
    skull.position.z += (0 - skull.position.z) * 0.05;
  }

  // Ring deformation
  updateRingDeformation(time, delta);

  // Ring color lerp
  ringColorCurrent.lerp(ringColorTarget, 0.05);
  if (ring) {
    ring.material.color.copy(ringColorCurrent);
    ring.material.emissive.copy(ringColorCurrent);
    ring.material.emissiveIntensity = 0.8 + compressionIntensity * 2 + deesserFlash * 1.5;
  }

  // Ring glow particles orbit
  if (ringGlowParticles) {
    const gp = ringGlowParticles.geometry.attributes.position;
    const ga = gp.array;
    const speed = ringRotationSpeed * 1.5;
    for (let i = 0; i < GLOW_PARTICLE_COUNT; i++) {
      const idx = i * 3;
      const x = ga[idx];
      const z = ga[idx + 2];
      const theta = Math.atan2(z, x) + speed * delta * 20;
      const r = Math.sqrt(x * x + z * z);
      ga[idx] = Math.cos(theta) * r;
      ga[idx + 2] = Math.sin(theta) * r;
      ga[idx + 1] += Math.sin(time * 2 + i) * delta * 0.1;
    }
    gp.needsUpdate = true;
  }

  // Eye socket glow
  updateEyes(time);

  // Particles
  updateParticles(delta, time);

  // Earrings jingle
  updateEarrings(delta, time);

  // Audition tilt
  if (Math.abs(auditionTilt) > 0.001) {
    skull.rotation.z += (auditionTilt - skull.rotation.z) * 0.05;
  }

  composer.render();
}

function updateRingDeformation(time, delta) {
  if (!ring) return;

  const amplitudes = new Array(RING_SEGMENTS).fill(0);

  // Compression wave
  if (compressionIntensity > 0.01) {
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle * 2 - time * 5) * compressionIntensity * 0.2;
      amplitudes[i] += Math.sin(angle * 3 + time * 3) * compressionIntensity * 0.08;
    }
  }

  // BPM pulse
  if (bpmInterval > 0) {
    bpmPhase += delta / bpmInterval;
    const pulse = Math.max(0, Math.sin(bpmPhase * Math.PI * 2));
    const pulseSharp = pulse * pulse * pulse;
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle + time * 2) * pulseSharp * 0.2;
      amplitudes[i] += Math.sin(angle * 4 - time * 4) * pulse * 0.05;
    }
  }

  // De-esser flash ripple
  if (deesserFlash > 0.01) {
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      const ripple = Math.sin(angle * 6 - time * 10) * deesserFlash * 0.12;
      amplitudes[i] += ripple;
    }
  }

  // Celebration wave
  if (celebrationWave > 0) {
    const wavePhase = (time * 4) % (Math.PI * 2);
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle * 3 - wavePhase) * celebrationWave * 0.25;
      amplitudes[i] += Math.sin(angle * 5 + wavePhase * 1.5) * celebrationWave * 0.1;
    }
  }

  // System ready pulse
  if (systemReadyPulse > 0) {
    const pulse = Math.sin(time * 8) * systemReadyPulse;
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += pulse * 0.12;
      amplitudes[i] += Math.sin(angle * 2 + time * 6) * systemReadyPulse * 0.06;
    }
  }

  // Activity level ambient motion
  if (activityLevel > 0) {
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle * 3 + time * 1.2) * activityLevel * 0.025;
      amplitudes[i] += Math.sin(angle * 7 + time * 2.5) * activityLevel * 0.01;
    }
  }

  deformRing(amplitudes);
}

function updateEyes(time) {
  if (!eyeLeft || !eyeRight) return;

  let intensity = 0.6;

  if (deesserFlash > 0.01) {
    intensity += deesserFlash * 2.5;
  }

  if (deepScanMode) {
    intensity += 0.4 + Math.sin(time * 5) * 0.25;
  }

  if (systemReadyPulse > 0) {
    intensity += systemReadyPulse * 0.8;
  }

  if (celebrationWave > 0) {
    intensity += celebrationWave * 0.5;
  }

  // Pulse slightly with BPM
  if (bpmInterval > 0) {
    const bpmPulse = Math.max(0, Math.sin(bpmPhase * Math.PI * 2));
    intensity += bpmPulse * 0.15;
  }

  eyeLeft.material.emissiveIntensity = intensity;
  eyeRight.material.emissiveIntensity = intensity;
}

function updateParticles(delta, time) {
  if (!particles) return;

  const pos = particles.geometry.attributes.position;
  const array = pos.array;

  const speed = particleOrbitSpeed
    * (listeningMode ? 0.2 : 1)
    * (deepScanMode ? 3 : 1)
    * (0.3 + activityLevel * 0.7);

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const idx = i * 3;
    const x = array[idx];
    const z = array[idx + 2];

    const theta = Math.atan2(z, x) + speed * delta * particleVelocities[i];
    const r = Math.sqrt(x * x + z * z);
    array[idx] = Math.cos(theta) * r;
    array[idx + 2] = Math.sin(theta) * r;

    // Vertical oscillation with phase
    array[idx + 1] += Math.sin(time * 0.5 + particlePhases[i]) * delta * 0.03;

    // Radial breathing on compression
    if (compressionIntensity > 0.05) {
      const breathe = 1 + Math.sin(time * 3 + particlePhases[i]) * compressionIntensity * 0.02;
      array[idx] *= breathe;
      array[idx + 2] *= breathe;
    }
  }

  pos.needsUpdate = true;
}

function updateEarrings(_delta, time) {
  for (const e of earrings) {
    let intensity = e.userData.jingleIntensity || 0;
    intensity *= 0.93;
    e.userData.jingleIntensity = intensity;

    const phase = e.userData.jinglePhase || 0;
    const swing = Math.sin(time * 3 + phase) * (0.015 + intensity * 0.1);
    e.rotation.z = swing;
    e.rotation.x = Math.sin(time * 2.5 + phase * 1.3) * (0.01 + intensity * 0.06);
    e.rotation.y = Math.sin(time * 2 + phase * 0.7) * (0.005 + intensity * 0.04);
  }
}

// ─── DSP Event Handlers ─────────────────────────────────────────────────────

function onSystemReady() {
  systemReadyPulse = 1.0;

  if (eyeLeft) eyeLeft.material.emissiveIntensity = 2.0;
  if (eyeRight) eyeRight.material.emissiveIntensity = 2.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.material.emissiveIntensity = 0.6;
    if (eyeRight) eyeRight.material.emissiveIntensity = 0.6;
  }, 1200);

  // Particles burst
  if (particles) {
    const pos = particles.geometry.attributes.position;
    const array = pos.array;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;
      const burst = 1.6;
      array[idx] *= burst;
      array[idx + 1] *= burst;
      array[idx + 2] *= burst;
    }
    pos.needsUpdate = true;
  }
}

function onCompression(ratio, releaseMs) {
  const amplitude = Math.min(0.35, (ratio - 1) * 0.06);
  compressionIntensity = amplitude;
  ringWaveDecay = Math.max(0.85, 1 - (releaseMs || 150) / 2000);

  // Earrings jingle
  for (const e of earrings) {
    e.userData.jingleIntensity = Math.min(1, (e.userData.jingleIntensity || 0) + amplitude * 2);
  }
}

function onGlueCompression(ratio) {
  const amplitude = Math.min(0.4, (ratio - 1) * 0.35);
  compressionIntensity = Math.max(compressionIntensity, amplitude);
  if (amplitude > 0.2) playSkullAction('HitRecieve');

  ringColorTarget.set('#FF3366');
  setTimeout(() => { ringColorTarget.set('#FF003F'); }, 250);

  // Strong earring jingle
  for (const e of earrings) {
    e.userData.jingleIntensity = Math.min(1, (e.userData.jingleIntensity || 0) + 0.5);
  }
}

function onDeesser() {
  deesserFlash = 1.0;
  playSkullAction('Bite_Front');

  if (eyeLeft) eyeLeft.material.emissiveIntensity = 3.0;
  if (eyeRight) eyeRight.material.emissiveIntensity = 3.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.material.emissiveIntensity = 0.6;
    if (eyeRight) eyeRight.material.emissiveIntensity = 0.6;
  }, 200);
}

function onBpm(bpm) {
  if (bpm && bpm > 0) {
    bpmInterval = 60.0 / bpm;
    bpmPhase = 0;
  }
}

function onListening(on) {
  listeningMode = on;
  if (on) {
    _showProp('headphones');
  } else {
    _hideAllProps();
  }
}

// Which instrument the avatar "plays along with" while a given stem is
// being processed -- purely cosmetic, mirrors whatever
// mixengine._guess_instrument() decided from the stem's role/filename.
// "cycle" means a single combined instrumental stem: rotate through all
// of them instead of guessing (and likely getting wrong) just one.
function onInstrument(instrument) {
  if (!instrument) {
    _hideAllProps();
    return;
  }
  if (instrument === 'cycle') {
    _hideAllProps(); // stop any previous cycle before starting a new one
    let i = 0;
    _showProp(INSTRUMENT_CYCLE_ORDER[0], true);
    _instrumentCycleTimer = setInterval(() => {
      i = (i + 1) % INSTRUMENT_CYCLE_ORDER.length;
      _showProp(INSTRUMENT_CYCLE_ORDER[i], true);
    }, INSTRUMENT_CYCLE_INTERVAL_MS);
    return;
  }
  if (PROP_CONFIGS[instrument]) {
    _showProp(instrument);
  }
}

function onDeepScan() {
  deepScanMode = true;
  ringColorTarget.set('#FF0044');
  playSkullAction('Bite_InPlace', { loop: true });
}

function onDeepScanDone() {
  deepScanMode = false;
  ringColorTarget.set('#FF003F');
  playSkullAction('Idle', { loop: true });
}

function onStep() {
  compressionIntensity = Math.max(compressionIntensity, 0.04);
}

function onApprove() {
  playSkullAction('Yes');
}

function onReject() {
  playSkullAction('No');
}

function onDone() {
  celebrationWave = 1.0;
  playSkullAction('Dance');

  if (particles) {
    const pos = particles.geometry.attributes.position;
    const array = pos.array;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;
      array[idx] *= 1.4;
      array[idx + 1] *= 1.4;
      array[idx + 2] *= 1.4;
    }
    pos.needsUpdate = true;
  }

  if (eyeLeft) eyeLeft.material.emissiveIntensity = 2.5;
  if (eyeRight) eyeRight.material.emissiveIntensity = 2.5;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.material.emissiveIntensity = 0.6;
    if (eyeRight) eyeRight.material.emissiveIntensity = 0.6;
  }, 400);

  // The vinyl is the "here's the finished record" beat -- shown briefly at
  // the end, not left up permanently (this function doesn't run again
  // until the next full render, so a plain timeout is enough here).
  _showProp('vinyl');
  setTimeout(() => { _hideAllProps(); }, 6000);
}

function onAuditionState(state) {
  if (state === 'BEFORE') {
    auditionTilt = 0.06;
    ringColorTarget.set('#FF6600');
    _showProp('cassette');
  } else if (state === 'AFTER') {
    auditionTilt = -0.04;
    ringColorTarget.set('#FF003F');
    _showProp('cassette');
  } else {
    auditionTilt = 0;
    ringColorTarget.set('#FF003F');
    _hideAllProps();
  }
}

function setActivity(level) {
  activityLevel = Math.max(0, Math.min(1, level));
  if (!listeningMode && !deepScanMode) {
    ringRotationSpeed = 0.001 + activityLevel * 0.004;
    particleOrbitSpeed = 0.0002 + activityLevel * 0.0012;
  }
}

// ─── Resize / Dispose ──────────────────────────────────────────────────────

function resize(width, height) {
  if (!camera || !renderer || !composer) return;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
  composer.setSize(width, height);
}

function dispose() {
  if (animFrameId !== null) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
  if (renderer) renderer.dispose();
  if (composer) composer.dispose();
  if (scene) {
    scene.traverse((child) => {
      if (child.isMesh || child.isPoints) {
        child.geometry?.dispose();
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => { m.dispose(); });
        } else {
          child.material?.dispose();
        }
      }
    });
  }
  scene = null;
  camera = null;
  renderer = null;
  composer = null;
  ring = null;
  ringOriginalPositions = null;
  ringGlowParticles = null;
  particles = null;
  earrings = [];
  if (_instrumentCycleTimer !== null) {
    clearInterval(_instrumentCycleTimer);
    _instrumentCycleTimer = null;
  }
  for (const key of Object.keys(_props)) delete _props[key];
}

// ─── Export API ─────────────────────────────────────────────────────────────

window.avatarAPI = {
  init,
  resize,
  dispose,
  onSystemReady,
  onCompression,
  onGlueCompression,
  onDeesser,
  onBpm,
  onListening,
  onDeepScan,
  onDeepScanDone,
  onStep,
  onDone,
  onAuditionState,
  onApprove,
  onReject,
  onInstrument,
  setActivity,
};
