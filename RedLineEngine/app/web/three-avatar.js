/**
 * three-avatar.js — Three.js 3D stylized skull avatar, reactive to the
 * engine's narration/DSP events and interactive via pointer raycasting.
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
let skull, craniumMesh, eyeLeft, eyeRight;
let rimLight = null;
let animFrameId = null;
let clock = new THREE.Clock();
// DSP state variables (decay per frame)
let compressionIntensity = 0;
let compressionDecay = 0.92;
let deesserFlash = 0;
let bpmPhase = 0;
let bpmInterval = 0.5;
let deepScanMode = false;
let activityLevel = 0.5;
// Accent color: the avatar's single reactive hue, lerped per frame and applied
// to the eye lights + rim light. Replaces the old ring color channel (the ring
// itself was removed) so every color-driven reaction still has a visible target.
const accentTarget = new THREE.Color('#FF003F');
const accentCurrent = new THREE.Color('#FF003F');
const skullVibrateOffset = new THREE.Vector3();
let systemReadyPulse = 0;
let celebrationWave = 0;
// Sustained eye-glow boost for the RedLine Mode easter egg -- unlike the
// other one-shot effects below, this needs to hold near-full brightness for
// several seconds rather than decay immediately, hence a duration-driven
// end time instead of a per-frame multiplicative decay.
let raveEyeGlowUntil = 0;
let auditionTilt = 0;
let idleFloatPhase = 0;
// Live character-processor prop reaction (onProcessor): a decaying spin
// impulse applied to the music_note prop while it is visible. Decays per
// frame in animate() so the note does a quick twirl then settles.
let processorSpin = 0;
// Punch-scale: a quick squash/stretch impulse on hard hits (glue
// compression slam, de-esser bite, done celebration) so those moments read
// as a snappy "hit" instead of only the subtler continuous vibration/glow.
let punchScale = 0;
// Ordered two-stage eye-glow decay for onDone (see below) -- tracked so a
// repeated onDone cancels the previous sequence instead of letting two
// independent timer chains clobber each other.
let doneEyeTimer = null;

// Narration-driven reaction state (onStep). `stepEyeBoost` decays per frame;
// `lastStepIntent`/`lastStepReactTime` throttle the dozens of onStep calls a
// real render fires per second so the avatar reacts to *changes* in intent
// rather than re-triggering on every line.
let stepEyeBoost = 0;
let lastStepIntent = null;
let lastStepReactTime = -1;
let stepAccentTimer = null;
let rejectAccentTimer = null;
let clickAccentTimer = null;

// Pointer interactivity (raycaster against the skull mesh).
let raycaster = null;
let pointerNDC = null;
let hovering = false;
let _wasHovering = false;
let hoverGlow = 0;
let contextLost = false;

// Respect the OS-level reduced-motion preference: non-essential idle motion
// (random glances, float, punch, hover glance) is damped or disabled, while
// informative reactions (eye flashes, color) stay.
const _reduceMotion = (typeof window !== 'undefined' && typeof window.matchMedia === 'function')
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false;

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
    camera.position.set(0, 0.3, 4.8);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.75;

    // Environment map
    const pmremGenerator = new THREE.PMREMGenerator(renderer);
    const envTexture = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTexture;
    pmremGenerator.dispose();

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x222244, 0.3);
    scene.add(ambientLight);

    rimLight = new THREE.DirectionalLight(0xFF003F, 0.6);
    rimLight.position.set(-2, 1, -2);
    scene.add(rimLight);

    const keyLight = new THREE.DirectionalLight(0xFFFFFF, 0.8);
    keyLight.position.set(2, 1, 2);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x4488FF, 0.3);
    fillLight.position.set(0, -1, 2);
    scene.add(fillLight);

    // Composer -- plain render+output keeps the actual geometry visible and
    // preserves canvas alpha transparency (additive bloom reliably breaks it).
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    composer.addPass(new OutputPass());

    // Pointer interactivity: raycast against the skull mesh on the canvas.
    raycaster = new THREE.Raycaster();
    pointerNDC = new THREE.Vector2();
    canvas.addEventListener('pointermove', _onPointerMove);
    canvas.addEventListener('pointerleave', _onPointerLeave);
    canvas.addEventListener('pointerdown', _onPointerDown);

    // WebGL context loss: without preventDefault() the context is never
    // restored and the canvas stays permanently black. On restore we rebuild
    // the composer (its render targets are invalidated) and restart the loop.
    canvas.addEventListener('webglcontextlost', _onContextLost, false);
    canvas.addEventListener('webglcontextrestored', _onContextRestored, false);

    // Keep the renderer in step with the canvas' real layout size: the window
    // can be resized (and the avatar panel reflows at the <=900px breakpoint)
    // long after init, and without this the 3D view stayed at its init size.
    window.addEventListener('resize', _onWindowResize);
    if (typeof ResizeObserver === 'function') {
      _resizeObserver = new ResizeObserver(_onWindowResize);
      _resizeObserver.observe(canvas);
    }

    buildSkull();

    clock = new THREE.Clock();
    animate();

    // One post-init sync: the canvas may have been laid out differently
    // between the initial setSize() above and this point (fonts, flex, the
    // boot overlay), so re-read the real client size once everything is up.
    _syncCanvasSize();

    console.log('[three-avatar] Initialized');
  } catch (err) {
    console.error('[three-avatar] Init error:', err);
  }
}

// ─── Skull Geometry ─────────────────────────────────────────────────────────

const SKULL_MODEL_URL = 'assets/skull.glb';
// Cool silver-grey, multiplied over the source texture. Multiply can only
// scale each channel, not shift hue -- so multiplying this over the source
// asset's own warm khaki/olive-painted texture still reads as khaki (just a
// darker khaki), not silver, because R/G/B keep their original ratio. See
// _desaturateMaterial below: the texture is grayscaled first so this tint
// actually determines the final hue instead of just dimming the wrong one.
const SKULL_TINT = '#AEB4C2';

// GPU-side desaturation of a material's texture map, so a colored material
// tint (multiply blend) actually produces that color instead of a darker
// version of whatever hue the source texture happened to be painted.
//
// A previous version of this did the desaturation on the CPU via
// canvas.getImageData() pixel readback. That works fine served over
// http://, but the packaged desktop app loads this page from a file:// URL
// (see app/main.py's `.as_uri()` window URL) where canvas pixel readback is
// subject to stricter/less consistent cross-origin tainting rules across
// browser engines -- confirmed in practice: the skull (and everything else
// in the group, since the failure happened inside the mesh-building loop)
// stopped appearing at all once that code shipped. This version instead
// patches the compiled fragment shader to desaturate the sampled texel on
// the GPU at render time (standard three.js `onBeforeCompile` technique) --
// it never touches a single pixel on the CPU, so there is no canvas/origin
// interaction to fail regardless of http:// vs file://.
function _desaturateMaterial(material) {
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <map_fragment>',
      `
      #ifdef USE_MAP
        vec4 sampledDiffuseColor = texture2D( map, vMapUv );
        float _redlineGray = dot( sampledDiffuseColor.rgb, vec3( 0.299, 0.587, 0.114 ) );
        sampledDiffuseColor.rgb = vec3( _redlineGray );
        diffuseColor *= sampledDiffuseColor;
      #endif
      `
    );
  };
  material.needsUpdate = true;
}

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
          // Whole rebuild wrapped defensively -- a cosmetic tint failure
          // must never be the reason the whole avatar fails to appear; the
          // mesh just keeps its original (unlit, khaki-tinted) material and
          // the model/eyes/mixer below still get added to the scene.
          try {
            const sourceMap = child.material && child.material.map ? child.material.map : null;
            if (sourceMap) sourceMap.colorSpace = THREE.SRGBColorSpace;
            // Rebuilt as MeshStandardMaterial (the source used
            // KHR_materials_unlit, flat/shadeless) so it actually responds
            // to the rim/key/fill lighting already set up in the scene,
            // while keeping the real texture map for genuine surface detail
            // and color variation instead of one uniform flat tone.
            const rebuilt = new THREE.MeshStandardMaterial({
              map: sourceMap,
              color: SKULL_TINT,
              metalness: 0.15,
              roughness: 0.65,
              envMapIntensity: 1.0,
            });
            if (sourceMap) _desaturateMaterial(rebuilt);
            child.material = rebuilt;
          } catch (err) {
            console.warn('[three-avatar] Skull material rebuild failed, keeping original material:', err);
          }
        }
      });

      // Normalize scale/position: the source asset's own units/origin are
      // arbitrary (typical for a downloaded asset) -- center it and scale
      // it to a consistent ~1.4-unit-tall footprint so the existing
      // camera framing and reaction animations (which were all tuned
      // against that scale) still line up.
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

      // Eye glow: the model already has real, sculpted eye-socket cavities
      // (visible as the natural dark hollows on its own geometry) -- an
      // earlier version bolted two small red-glowing spheres on top of
      // them, which read as two floating dots rather than "the skull's own
      // eyes lighting up" (direct feedback: remove the dots). A PointLight
      // has no visible geometry of its own, so instead of adding an object,
      // it lights the *existing* socket cavities red from within -- the
      // reactive glow now comes from the skull's real geometry, nothing
      // extra is rendered on top of it. Positioned at the same approximate
      // eye-socket location as before (bounding-box derived, no named
      // eye-socket bone/mesh to anchor to), short `distance` so it only
      // lights the immediate socket area rather than washing the whole face.
      // scaledBox/scaledCenter were measured BEFORE model.position.sub()
      // shifted the model into centered space above -- using scaledBox.max
      // directly here (as an earlier version did) ignored that shift and
      // placed the lights well above actual eye level, reading as
      // eyebrows instead. Re-express the box edges relative to the same
      // center that was just subtracted from the model.
      const centeredMaxY = scaledBox.max.y - scaledCenter.y;
      const centeredMinY = scaledBox.min.y - scaledCenter.y;
      const centeredMaxZ = scaledBox.max.z - scaledCenter.z;
      const headHeight = centeredMaxY - centeredMinY;
      const eyeY = centeredMaxY - headHeight * 0.42; // ~42% down from the crown -- eye level, not brow level
      const eyeZ = centeredMaxZ * 0.85;
      const eyeX = size.x * scale * 0.16;

      // A short, sharply-falling-off point light (distance 0.4, decay 2)
      // still reads as a bright, tightly-bounded hotspot on the surface --
      // visually indistinguishable from a small glowing ball, exactly what
      // was being avoided. A longer reach + gentler decay spreads the same
      // light over a wider area of the socket instead of concentrating it
      // into one bright point, reading as "this whole area is lit red"
      // rather than "there is a red dot here".
      eyeLeft = new THREE.PointLight('#FF003F', 0.4, 1.1, 1);
      eyeLeft.position.set(-eyeX, eyeY, eyeZ);
      group.add(eyeLeft);

      eyeRight = new THREE.PointLight('#FF003F', 0.4, 1.1, 1);
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
      // Without this, a failed GLB load (e.g. a resource-loading quirk
      // specific to the desktop app's file:// context, different from the
      // http:// dev server this was tested against) left `group` completely
      // empty -- no mesh, no eyes, nothing -- which is exactly "the avatar
      // doesn't appear at all" with no visible clue why. A simple placeholder
      // sphere + eyes means something always renders, and the console error
      // still identifies the real cause for debugging.
      console.error('[three-avatar] Failed to load skull model, showing placeholder:', err);
      const placeholder = new THREE.Mesh(
        new THREE.SphereGeometry(0.7, 24, 24),
        new THREE.MeshStandardMaterial({ color: SKULL_TINT, metalness: 0.15, roughness: 0.65 })
      );
      group.add(placeholder);
      // This placeholder has no sculpted eye sockets to light from within
      // (it's a plain sphere, unlike the real model above) -- static glow
      // dots are the only way to show "eyes" at all here, so this rare
      // fallback path keeps them as meshes instead of the PointLight
      // approach used for the real model. They won't animate via
      // updateEyes()'s eyeLeft.intensity calls (meshes have no .intensity),
      // which is an acceptable fidelity loss for a load-failure fallback.
      const eyeMat = new THREE.MeshStandardMaterial({ color: '#FF003F', emissive: '#FF003F', emissiveIntensity: 0.5, depthTest: false });
      eyeLeft = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 12), eyeMat);
      eyeLeft.position.set(-0.22, 0.15, 0.6);
      eyeLeft.renderOrder = 999;
      group.add(eyeLeft);
      eyeRight = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 12), eyeMat.clone());
      eyeRight.position.set(0.22, 0.15, 0.6);
      eyeRight.renderOrder = 999;
      group.add(eyeRight);
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
  guitar: { url: 'assets/guitar.glb', targetHeight: 1.9, position: [-1.5, -0.6, 0], tint: '#8890A0' },
  bass: { url: 'assets/bass_guitar.glb', targetHeight: 1.9, position: [-1.5, -0.6, 0], tint: '#8890A0' },
  piano: { url: 'assets/piano.glb', targetHeight: 1.4, position: [-1.5, -0.5, 0], tint: '#8890A0' },
  wind: { url: 'assets/kazoo.glb', targetHeight: 0.9, position: [-1.4, -0.2, 0], tint: '#8890A0' },
  // Live character-processor prop: a music note that pops in (with a spin)
  // whenever a built-in processor is applied to a stem (onProcessor below).
  // Mirrored to the right side, opposite the instrument props on the left.
  music_note: { url: 'assets/music_note.glb', targetHeight: 1.0, position: [1.5, 0.1, 0], tint: '#FF3366' },
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
          try {
            const sourceMap = child.material && child.material.map ? child.material.map : null;
            if (sourceMap) sourceMap.colorSpace = THREE.SRGBColorSpace;
            const propMaterial = tintMaterial.clone();
            propMaterial.map = sourceMap;
            if (sourceMap) _desaturateMaterial(propMaterial);
            child.material = propMaterial;
          } catch (err) {
            console.warn(`[three-avatar] Prop "${name}" material rebuild failed, keeping original material:`, err);
          }
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
      // console.warn, not console.error: a missing/failed prop asset is a
      // cosmetic degradation (the prop simply stays hidden), not an app
      // error -- and the QA harness counts console.error as a failure.
      console.warn(`[three-avatar] Failed to load prop "${name}" (staying hidden):`, err);
      delete _propLoading[name];
    }
  );
}

function _hideAllPropVisuals() {
  for (const group of Object.values(_props)) group.visible = false;
  processorSpin = 0;
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
      // More activity -> shorter holds -> more frequent glances, so the
      // avatar visibly "wakes up" while a render is running.
      const holdScale = 1.2 - activityLevel * 0.6;
      lookPhaseEndTime = time + (1.5 + Math.random() * 3.5) * holdScale;
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

// Forces an immediate 'turn' toward a target using the same easing as an
// organic glance -- shared by onSaturation, onStep intents and hover.
function _glanceTo(targetY, targetX, duration) {
  if (!skull) return;
  const time = clock.elapsedTime;
  lookPhase = 'turn';
  lookFromY = lookCurrentY;
  lookFromX = lookCurrentX;
  lookTargetY = targetY;
  lookTargetX = targetX;
  lookPhaseStartTime = time;
  lookPhaseEndTime = time + duration;
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

// ─── Pointer interactivity ──────────────────────────────────────────────────

// All handlers no-op safely when WebGL failed or the skull mesh isn't loaded
// yet -- app.js removes `pointer-events: none` from .fx-canvas, so these
// receive real events, but a missing renderer/mesh must never throw.
function _onPointerMove(e) {
  if (!renderer || !craniumMesh || !raycaster || !camera) return;
  const rect = renderer.domElement.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return;
  pointerNDC.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointerNDC.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  try {
    raycaster.setFromCamera(pointerNDC, camera);
    hovering = raycaster.intersectObject(craniumMesh, true).length > 0;
  } catch (err) {
    hovering = false;
  }
}

function _onPointerLeave() {
  hovering = false;
}

function _onPointerDown(e) {
  if (!renderer || !craniumMesh || !raycaster || !camera) return;
  _onPointerMove(e);
  if (!hovering) return;
  _triggerClickReaction();
}

// A distinct "punch" reaction on click: squash impulse, eye flash, a white
// accent pop and the skull's own HitRecieve clip.
function _triggerClickReaction() {
  punchScale = Math.max(punchScale, 0.6);
  stepEyeBoost = Math.max(stepEyeBoost, 1.6);
  accentTarget.set('#FFFFFF');
  clearTimeout(clickAccentTimer);
  clickAccentTimer = setTimeout(() => { accentTarget.set('#FF003F'); }, 180);
  playSkullAction('HitRecieve');
  if (!_reduceMotion) _glanceTo((Math.random() < 0.5 ? -1 : 1) * 0.2, 0.05, 0.3);
}

// ─── WebGL context loss ─────────────────────────────────────────────────────

function _onContextLost(e) {
  // Without preventDefault() the browser never fires webglcontextrestored
  // and the canvas stays permanently black.
  e.preventDefault();
  contextLost = true;
  if (animFrameId !== null) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
}

function _onContextRestored() {
  contextLost = false;
  try {
    if (renderer && scene && camera) {
      // The composer's render targets are invalidated by the context loss --
      // rebuild it against the (now restored) renderer.
      composer = new EffectComposer(renderer);
      composer.addPass(new RenderPass(scene, camera));
      composer.addPass(new OutputPass());
      const el = renderer.domElement;
      composer.setSize(el.clientWidth || 1, el.clientHeight || 1);
    }
  } catch (err) {
    console.warn('[three-avatar] Context restore re-init failed:', err);
  }
  if (animFrameId === null) animate();
}

// ─── Animation Loop ────────────────────────────────────────────────────────

function animate() {
  animFrameId = requestAnimationFrame(animate);
  if (!renderer || !composer || !skull || contextLost) return;

  const delta = Math.min(clock.getDelta(), 0.05);
  const time = clock.elapsedTime;

  // Decay state variables
  compressionIntensity *= compressionDecay;
  deesserFlash *= 0.85;
  stepEyeBoost *= 0.9;
  if (systemReadyPulse > 0) systemReadyPulse -= delta * 1.5;
  if (celebrationWave > 0) celebrationWave -= delta * 0.4;

  // Idle floating -- amplitude and speed track the current activity level so
  // the avatar visibly comes alive while a render runs and settles at rest.
  idleFloatPhase += delta * (0.3 + activityLevel * 0.5);
  const floatAmp = _reduceMotion ? 0.004 : (0.008 + activityLevel * 0.02);
  const floatY = Math.sin(idleFloatPhase) * floatAmp;

  // Baked-clip playback (Idle/Yes/No/Bite_Front/Dance/...) drives the
  // actual body motion now -- this loop only adds the subtle vertical
  // breathing float and the natural, intermittent head glance below.
  if (mixer) mixer.update(delta);
  skull.position.y = -0.1 + floatY;
  updateNaturalLook(time);

  if (_props.vinyl && _props.vinyl.visible) {
    _props.vinyl.rotation.z -= delta * 2.2; // steady spin, independent of the skull's own motion
  }

  // Live processor prop: a decaying spin impulse (onProcessor) plus a gentle
  // idle bob so the note reads as "just popped in" rather than a static decal.
  if (_props.music_note && _props.music_note.visible) {
    if (processorSpin > 0.001) {
      _props.music_note.rotation.y += delta * processorSpin * 9;
      processorSpin *= Math.max(0, 1 - delta * 3.5);
    } else {
      processorSpin = 0;
    }
    _props.music_note.position.y = PROP_CONFIGS.music_note.position[1] + Math.sin(time * 2.4) * 0.05;
  }

  // Hover glow: smooth toward the current hover state; a fresh hover also
  // earns a subtle glance toward the pointer.
  hoverGlow += ((hovering ? 1 : 0) - hoverGlow) * 0.1;
  if (hovering && !_wasHovering && !_reduceMotion && pointerNDC) {
    _glanceTo(pointerNDC.x * 0.3, -pointerNDC.y * 0.1, 0.4);
  }
  _wasHovering = hovering;

  // Skull vibration from compression -- amplitude bumped up (was 0.04) so
  // a hard-hitting glue/multiband moment actually reads as a visible shake
  // instead of a barely-perceptible jitter.
  if (compressionIntensity > 0.01) {
    const amp = compressionIntensity * 0.09;
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

  // Punch-scale decay: quick snap up then settle back to 1.0 (critically
  // damped feel via exponential decay of the offset from rest).
  if (punchScale > 0.001) {
    punchScale *= Math.max(0, 1 - delta * 10);
    const s = 1 + punchScale * 0.18;
    skull.scale.set(s, 1 - punchScale * 0.10, s);
  } else if (skull.scale.x !== 1) {
    skull.scale.set(1, 1, 1);
  }

  // Accent color lerp -- applied to the eye lights and rim light so every
  // color-driven reaction (approve/reject/glitch/easter egg/...) stays visible.
  accentCurrent.lerp(accentTarget, 0.08);
  if (eyeLeft && eyeLeft.color) eyeLeft.color.copy(accentCurrent);
  if (eyeRight && eyeRight.color) eyeRight.color.copy(accentCurrent);
  if (rimLight) rimLight.color.copy(accentCurrent);

  // Eye socket glow
  updateEyes(time);

  // Audition tilt
  if (Math.abs(auditionTilt) > 0.001) {
    skull.rotation.z += (auditionTilt - skull.rotation.z) * 0.05;
  }

  composer.render();
}

function updateEyes(time) {
  if (!eyeLeft || !eyeRight) return;

  // Near-zero at rest (was a permanent 0.6 baseline) -- a light source
  // sitting in the socket is visible as a distinct glowing shape no matter
  // how it's tuned, which read as "two red dots stuck on all the time"
  // rather than a reactive cue. A small activity-linked baseline keeps the
  // eyes faintly alive while the engine is busy without becoming a fixture.
  let intensity = 0.05 + activityLevel * 0.08;

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

  // Narration-intent and hover boosts (both decay/smooth per frame).
  intensity += stepEyeBoost * 1.5;
  intensity += hoverGlow * 0.8;

  // Capped at the same magnitude as the de-esser's proven-visible flash
  // (deesserFlash * 2.5, max ~2.5) rather than a bigger jump -- a much
  // higher boost pushes this saturated red material's rendered color
  // toward white under ACES tone mapping instead of reading as "more red".
  if (time < raveEyeGlowUntil) {
    intensity += 2.8;
  }

  eyeLeft.intensity = intensity;
  eyeRight.intensity = intensity;
}

// ─── DSP Event Handlers ─────────────────────────────────────────────────────

function onSystemReady() {
  systemReadyPulse = 1.0;
  _hideAllProps(); // a fresh session starts clean -- no stale processor prop

  if (eyeLeft) eyeLeft.intensity = 2.0;
  if (eyeRight) eyeRight.intensity = 2.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.intensity = 0.05;
    if (eyeRight) eyeRight.intensity = 0.05;
  }, 1200);
}

function onCompression(ratio, releaseMs) {
  // Cap and multiplier both raised (was 0.35 / 0.06) -- the old range
  // topped out so subtly that most real compressor ratios (2:1-6:1) barely
  // moved the needle visually.
  const amplitude = Math.min(0.5, (ratio - 1) * 0.09);
  compressionIntensity = amplitude;
  compressionDecay = Math.max(0.85, 1 - (releaseMs || 150) / 2000);
}

function onGlueCompression(ratio) {
  const amplitude = Math.min(0.6, (ratio - 1) * 0.5);
  compressionIntensity = Math.max(compressionIntensity, amplitude);
  if (amplitude > 0.15) {
    playSkullAction('HitRecieve');
    punchScale = Math.min(1, amplitude * 1.5);
  }

  accentTarget.set('#FF3366');
  setTimeout(() => { accentTarget.set('#FF003F'); }, 250);
}

function onDeesser() {
  deesserFlash = 1.0;
  playSkullAction('Bite_Front');
  punchScale = Math.max(punchScale, 0.55);

  if (eyeLeft) eyeLeft.intensity = 4.0;
  if (eyeRight) eyeRight.intensity = 4.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.intensity = 0.05;
    if (eyeRight) eyeRight.intensity = 0.05;
  }, 220);
}

function onBpm(bpm) {
  if (bpm && bpm > 0) {
    bpmInterval = 60.0 / bpm;
    bpmPhase = 0;
  }
}

function onListening(on) {
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

// Live character-processor reaction: a built-in processor (distortion,
// saturation, ...) was applied to a stem -- pop in the music_note prop with
// a spin impulse and a small eye/accent beat. Called by app.js's
// character_processor case (guarded). The prop is hidden again by onDone /
// onSystemReady via _hideAllProps, so it never stays up forever.
function onProcessor(processorName) {
  _showProp('music_note');
  processorSpin = 1.0;
  stepEyeBoost = Math.max(stepEyeBoost, 0.8);
  accentTarget.set('#FF3366');
  clearTimeout(stepAccentTimer);
  stepAccentTimer = setTimeout(() => { accentTarget.set('#FF003F'); }, 500);
  if (!_reduceMotion) _glanceTo(0.3, 0.05, 0.4);
}

function onDeepScan() {
  deepScanMode = true;
  accentTarget.set('#FF0044');
  playSkullAction('Bite_InPlace', { loop: true });
}

function onDeepScanDone() {
  deepScanMode = false;
  accentTarget.set('#FF003F');
  playSkullAction('Idle', { loop: true });
}

// Lightweight intent classifier over the engine's Italian narration text.
// Returns a coarse intent tag (or null) -- deliberately cheap, no allocation
// beyond the regex tests, since onStep fires dozens of times per second.
function _classifyStep(text) {
  if (!text) return null;
  if (/errore|error|fallit|fail/.test(text)) return 'error';
  if (/caric|load/.test(text)) return 'load';
  if (/analiz|analys|bpm|tonalit|loudness/.test(text)) return 'analyze';
  if (/master/.test(text)) return 'master';
  if (/mix/.test(text)) return 'mix';
  if (/controllo|\bqc\b|verific/.test(text)) return 'qc';
  if (/fatto|complet|finit|done/.test(text)) return 'done';
  return null;
}

// Distinct, cheap reaction per intent: an accent color, an eye-glow boost and
// (unless reduced-motion) a small glance. Throttled by onStep so a burst of
// same-intent lines doesn't retrigger the glance every frame.
function _applyStepIntent(intent) {
  stepEyeBoost = Math.max(stepEyeBoost, 0.6);
  switch (intent) {
    case 'load':
      accentTarget.set('#FF003F');
      if (!_reduceMotion) _glanceTo(-0.25, -0.08, 0.5);
      break;
    case 'analyze':
      accentTarget.set('#FF6600');
      stepEyeBoost = Math.max(stepEyeBoost, 0.9);
      if (!_reduceMotion) _glanceTo((Math.random() < 0.5 ? -1 : 1) * 0.3, 0.05, 0.45);
      break;
    case 'mix':
      accentTarget.set('#FF003F');
      if (!_reduceMotion) _glanceTo(0.15, 0.06, 0.4);
      break;
    case 'master':
      accentTarget.set('#FF3366');
      stepEyeBoost = Math.max(stepEyeBoost, 1.0);
      if (!_reduceMotion) _glanceTo(0, -0.1, 0.5);
      break;
    case 'qc':
      accentTarget.set('#33FF88');
      if (!_reduceMotion) _glanceTo(0.2, 0.04, 0.35);
      break;
    case 'done':
      accentTarget.set('#33FF88');
      stepEyeBoost = Math.max(stepEyeBoost, 1.2);
      break;
    case 'error':
      accentTarget.set('#FF3300');
      stepEyeBoost = Math.max(stepEyeBoost, 1.5);
      if (!_reduceMotion) _glanceTo((Math.random() < 0.5 ? -1 : 1) * 0.35, 0.08, 0.3);
      break;
    default:
      return;
  }
  clearTimeout(stepAccentTimer);
  stepAccentTimer = setTimeout(() => { accentTarget.set('#FF003F'); }, 600);
}

function onStep(msg) {
  // Keep the existing micro-pulse so every narration line still nudges the
  // avatar, then layer the intent-driven reaction on top.
  compressionIntensity = Math.max(compressionIntensity, 0.04);

  const text = typeof msg === 'string' ? msg.toLowerCase() : '';
  const intent = _classifyStep(text);
  if (!intent) return;

  const time = clock.elapsedTime;
  if (intent === lastStepIntent && time - lastStepReactTime < 0.4) return;
  lastStepIntent = intent;
  lastStepReactTime = time;
  _applyStepIntent(intent);
}

function onApprove() {
  playSkullAction('Yes');
  accentTarget.set('#33FF88');
  setTimeout(() => { accentTarget.set('#FF003F'); }, 500);
  punchScale = Math.max(punchScale, 0.35);
}

// Dismissive reject reaction: the skull's own "No" head-shake clip plus a
// short group-level side-to-side shake, an orange accent flash and a punch.
// Exported for app.js to wire up (not called by the current app.js yet).
function onReject() {
  playSkullAction('No');
  accentTarget.set('#FF3300');
  clearTimeout(rejectAccentTimer);
  rejectAccentTimer = setTimeout(() => { accentTarget.set('#FF003F'); }, 500);
  punchScale = Math.max(punchScale, 0.35);
  stepEyeBoost = Math.max(stepEyeBoost, 1.0);
  if (!_reduceMotion) {
    _glanceTo(0.4, 0.05, 0.18);
    setTimeout(() => _glanceTo(-0.4, 0.05, 0.18), 180);
    setTimeout(() => _glanceTo(0, 0, 0.2), 360);
  }
}

function onDone() {
  celebrationWave = 1.0;
  punchScale = 1.0;
  playSkullAction('Dance');
  processorSpin = 0; // the processor prop's reaction ends with the render

  // Ordered two-stage eye decay: bright flash -> softer glow -> rest. The
  // second stage is scheduled from inside the first timeout so the two
  // resets can't clobber each other (previously both were scheduled at
  // once, so the 400ms reset killed the 600ms glow before it ever showed).
  if (eyeLeft) eyeLeft.intensity = 5.0;
  if (eyeRight) eyeRight.intensity = 5.0;
  clearTimeout(doneEyeTimer);
  doneEyeTimer = setTimeout(() => {
    if (eyeLeft) eyeLeft.intensity = 2.5;
    if (eyeRight) eyeRight.intensity = 2.5;
    doneEyeTimer = setTimeout(() => {
      if (eyeLeft) eyeLeft.intensity = 0.05;
      if (eyeRight) eyeRight.intensity = 0.05;
      doneEyeTimer = null;
    }, 400);
  }, 600);

  // The vinyl is the "here's the finished record" beat -- shown briefly at
  // the end, not left up permanently (this function doesn't run again
  // until the next full render, so a plain timeout is enough here).
  _showProp('vinyl');
  setTimeout(() => { _hideAllProps(); }, 6000);
}

function onAuditionState(state) {
  if (state === 'BEFORE') {
    auditionTilt = 0.06;
    accentTarget.set('#FF6600');
    _showProp('cassette');
  } else if (state === 'AFTER') {
    auditionTilt = -0.04;
    accentTarget.set('#FF003F');
    _showProp('cassette');
  } else {
    auditionTilt = 0;
    accentTarget.set('#FF003F');
    _hideAllProps();
  }
}

// Reuses the natural-glance state machine (updateNaturalLook above) instead
// of a separate animation path -- forces an immediate 'turn' toward a side
// biased by the saturation drive amount, same easing as an organic glance.
function onSaturation(drive) {
  if (!skull) return;
  const amount = Math.max(0, Math.min(1, (drive || 0) / 4));
  _glanceTo(
    (Math.random() < 0.5 ? -1 : 1) * (0.35 + amount * 0.35),
    0.05,
    0.5 + amount * 0.3
  );
  if (eyeLeft) eyeLeft.intensity = 3.0;
  if (eyeRight) eyeRight.intensity = 3.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.intensity = 0.05;
    if (eyeRight) eyeRight.intensity = 0.05;
  }, 260);
}

// Distinct from the rack's CSS glitch (app.js triggerGlitch) -- this is the
// avatar's own reaction to a DSP-level anomaly/correction: a sharp color
// flash + tiny punch, no head movement (a glitch reads as sudden, not as
// a considered glance).
function onGlitch() {
  accentTarget.set('#FFFFFF');
  setTimeout(() => { accentTarget.set('#FF003F'); }, 90);
  punchScale = Math.max(punchScale, 0.25);
}

// Easter egg ("RedLine Mode"): secret key combo (Ctrl+Alt+R, see app.js
// keydown listener) triggers a ~4.5s celebratory burst -- eyes burning red,
// the skull's own Dance clip, a white-to-red accent flash, and a fading
// "REDLINE MODE" label. No canvas overlay drawing (an earlier version drew a
// Lissajous curve here; dropped per feedback -- read as distracting neon
// circles rather than a clean reaction).
function onEasterEgg() {
  const label = document.getElementById('easter-egg-label');
  const durationMs = 4500;

  // Label: retrigger the CSS fade-in/out animation from the start even if
  // the combo is mashed repeatedly mid-animation.
  if (label) {
    label.classList.remove('playing');
    void label.offsetWidth;
    label.classList.add('playing');
  }

  // Skull celebration: same Dance clip as a finished render, plus a punch.
  playSkullAction('Dance');
  punchScale = 1.0;

  // Eyes burn bright red for the whole duration -- routed through
  // updateEyes()'s per-frame formula (raveEyeGlowUntil), not a direct
  // assignment: updateEyes() overwrites intensity every single frame from
  // its own state flags, so a one-off direct set here would have been
  // clobbered again within the next ~16ms and never actually seen.
  raveEyeGlowUntil = clock.elapsedTime + durationMs / 1000;

  // Accent flashes to white-hot for an instant, then settles back to the
  // house accent color -- same beat as onGlueCompression's slam, just held
  // a little longer to match the eyes.
  accentTarget.set('#FFFFFF');
  setTimeout(() => { accentTarget.set('#FF003F'); }, 300);
}

// Called by app.js (startup + repeatedly during a render). The main loop
// reads `activityLevel` every frame, so idle motion intensity tracks it
// continuously instead of only reflecting the single startup value.
function setActivity(level) {
  activityLevel = Math.max(0, Math.min(1, level));
}

// ─── Resize / Dispose ──────────────────────────────────────────────────────

// __AVATAR_SIZING_HELPER_START__
// Pure sizing math, extracted so it can be unit-tested in Node without a DOM
// or WebGL (see tests/js/avatar_sizing.test.mjs). Guards every degenerate
// input (0, negative, NaN, non-numeric) to a 1px minimum so a hidden or
// not-yet-laid-out canvas can never produce a division by zero / NaN aspect
// that would blank the renderer.
function computeAvatarSize(width, height) {
  const w = Number(width);
  const h = Number(height);
  const safeW = Number.isFinite(w) && w > 0 ? w : 1;
  const safeH = Number.isFinite(h) && h > 0 ? h : 1;
  return { width: safeW, height: safeH, aspect: safeW / safeH };
}
// __AVATAR_SIZING_HELPER_END__

function resize(width, height) {
  if (!camera || !renderer || !composer) return;
  const size = computeAvatarSize(width, height);
  camera.aspect = size.aspect;
  camera.updateProjectionMatrix();
  renderer.setSize(size.width, size.height, false);
  composer.setSize(size.width, size.height);
}

// Reads the canvas' CURRENT layout size and applies it. resize() existed but
// was never called, so the 3D view stayed frozen at its init-time size while
// the window/panel around it changed -- this is the missing call site.
function _syncCanvasSize() {
  if (!renderer || !renderer.domElement) return;
  const canvas = renderer.domElement;
  const size = computeAvatarSize(canvas.clientWidth, canvas.clientHeight);
  resize(size.width, size.height);
}

// Coalesces bursts of resize events (window drags fire dozens per second)
// into one rAF-sized update instead of resizing the render targets per event.
let _resizeRaf = null;
function _onWindowResize() {
  if (_resizeRaf !== null) return;
  _resizeRaf = requestAnimationFrame(() => {
    _resizeRaf = null;
    _syncCanvasSize();
  });
}

let _resizeObserver = null;

function dispose() {
  if (animFrameId !== null) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
  if (_resizeRaf !== null) {
    cancelAnimationFrame(_resizeRaf);
    _resizeRaf = null;
  }
  window.removeEventListener('resize', _onWindowResize);
  if (_resizeObserver) {
    _resizeObserver.disconnect();
    _resizeObserver = null;
  }
  if (renderer && renderer.domElement) {
    const canvas = renderer.domElement;
    canvas.removeEventListener('pointermove', _onPointerMove);
    canvas.removeEventListener('pointerleave', _onPointerLeave);
    canvas.removeEventListener('pointerdown', _onPointerDown);
    canvas.removeEventListener('webglcontextlost', _onContextLost);
    canvas.removeEventListener('webglcontextrestored', _onContextRestored);
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
  clearTimeout(doneEyeTimer);
  clearTimeout(stepAccentTimer);
  clearTimeout(rejectAccentTimer);
  clearTimeout(clickAccentTimer);
  scene = null;
  camera = null;
  renderer = null;
  composer = null;
  skull = null;
  craniumMesh = null;
  eyeLeft = null;
  eyeRight = null;
  rimLight = null;
  raycaster = null;
  pointerNDC = null;
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
  onProcessor,
  onSaturation,
  onGlitch,
  onEasterEgg,
  setActivity,
};
