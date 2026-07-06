/**
 * three-avatar.js — Three.js 3D stylized skull avatar with reactive ring,
 * earrings, particles, and bloom post-processing.
 *
 * ES module, loaded via importmap. Exposes window.avatarAPI.
 */

import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// ─── Module state ───────────────────────────────────────────────────────────

let scene, camera, renderer, composer;
let skull, craniumMesh, eyeLeft, eyeRight, noseCavity;
let ring, ringOriginalPositions = null;
let earrings = [];
let particles, particleVelocities;
let animFrameId = null;
let clock = new THREE.Clock();

// DSP state variables (decay per frame)
let compressionIntensity = 0;
let deesserFlash = 0;
let bpmPhase = 0;
let bpmInterval = 0.5; // seconds
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

// ─── Constants ─────────────────────────────────────────────────────────────

const RING_SEGMENTS = 64;
const RING_RADIUS = 1.8;
const RING_TUBE = 0.03;
const PARTICLE_COUNT = 2000;
const PARTICLE_INNER = 2.0;
const PARTICLE_OUTER = 3.5;

// ─── Initialization ─────────────────────────────────────────────────────────

function init(canvasId) {
  try {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
      console.warn(`[three-avatar] Canvas #${canvasId} not found`);
      return;
    }

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color('#0A0A0A');

    // Camera
    camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 10);
    camera.position.set(0, 0.5, 4);
    camera.lookAt(0, 0, 0);

    // Renderer
    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: true,
      alpha: false,
    });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;

    // Environment map
    const pmremGenerator = new THREE.PMREMGenerator(renderer);
    const envTexture = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTexture;
    pmremGenerator.dispose();

    // Composer
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(canvas.clientWidth, canvas.clientHeight),
      0.5, 0.3, 0.15
    );
    composer.addPass(bloomPass);
    composer.addPass(new OutputPass());

    // Build scene objects
    buildSkull();
    buildRing();
    buildEarrings();
    buildParticles();

    // Start animation
    clock = new THREE.Clock();
    animate();

    console.log('[three-avatar] Initialized');
  } catch (err) {
    console.error('[three-avatar] Init error:', err);
  }
}

// ─── Skull Geometry ─────────────────────────────────────────────────────────

function buildSkull() {
  const group = new THREE.Group();

  // Cranium: LatheGeometry with skull profile
  const profilePoints = [];
  const profile = [
    [0.0, 0.0],     // base center
    [0.3, 0.0],     // base right
    [0.5, 0.1],     // jaw corner
    [0.6, 0.2],     // cheek
    [0.7, 0.35],    // temple
    [0.75, 0.5],    // mid cranium
    [0.7, 0.7],     // upper cranium
    [0.6, 0.85],    // crown
    [0.4, 0.95],    // top
    [0.0, 1.0],     // apex
  ];
  for (const [x, y] of profile) {
    profilePoints.push(new THREE.Vector2(x, y));
  }
  const latheGeo = new THREE.LatheGeometry(profilePoints, 24);

  // Jaw: half sphere
  const jawGeo = new THREE.SphereGeometry(0.35, 12, 8, 0, Math.PI, 0, Math.PI / 2);
  jawGeo.rotateX(Math.PI);
  jawGeo.translate(0, -0.15, 0);

  // Merge cranium + jaw
  const merged = mergeGeometries([latheGeo, jawGeo]);
  merged.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    color: '#D4D4D8',
    metalness: 0.7,
    roughness: 0.25,
  });

  craniumMesh = new THREE.Mesh(merged, material);
  craniumMesh.position.y = -0.1;
  group.add(craniumMesh);

  // Eye sockets: dark emissive red spheres
  const eyeMat = new THREE.MeshStandardMaterial({
    color: '#FF003F',
    emissive: '#FF003F',
    emissiveIntensity: 0.5,
  });

  eyeLeft = new THREE.Mesh(new THREE.SphereGeometry(0.3, 12, 12), eyeMat);
  eyeLeft.position.set(-0.35, 0.25, 0.5);
  group.add(eyeLeft);

  eyeRight = new THREE.Mesh(new THREE.SphereGeometry(0.3, 12, 12), eyeMat);
  eyeRight.position.set(0.35, 0.25, 0.5);
  group.add(eyeRight);

  // Nose cavity
  const noseMat = new THREE.MeshStandardMaterial({
    color: '#1A0005',
    emissive: '#1A0005',
    emissiveIntensity: 0.1,
  });
  noseCavity = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.12, 6), noseMat);
  noseCavity.position.set(0, 0.05, 0.55);
  noseCavity.rotation.x = Math.PI / 2;
  group.add(noseCavity);

  skull = group;
  scene.add(skull);
}

// ─── Reactive Ring ──────────────────────────────────────────────────────────

function buildRing() {
  const geo = new THREE.TorusGeometry(RING_RADIUS, RING_TUBE, 8, RING_SEGMENTS);
  const mat = new THREE.MeshStandardMaterial({
    color: '#FF003F',
    emissive: '#FF003F',
    emissiveIntensity: 0.8,
  });
  ring = new THREE.Mesh(geo, mat);
  ring.position.y = 0.3;
  ring.rotation.x = Math.PI / 2;
  scene.add(ring);

  // Store original vertex positions for deformation
  const pos = ring.geometry.attributes.position;
  ringOriginalPositions = new Float32Array(pos.array);
}

/**
 * Deform ring segments by Y offset amplitudes.
 * @param {number[]} amplitudes - Array of Y offsets, one per segment
 */
function deformRing(amplitudes) {
  if (!ring || !ringOriginalPositions) return;
  const pos = ring.geometry.attributes.position;
  const array = pos.array;
  const segCount = RING_SEGMENTS;

  for (let i = 0; i < segCount; i++) {
    // Each segment has 8 vertices (tube resolution)
    const amp = amplitudes[i] || 0;
    for (let j = 0; j < 8; j++) {
      const idx = (i * 8 + j) * 3;
      // Y is at index + 1
      array[idx + 1] = ringOriginalPositions[idx + 1] + amp;
    }
  }
  pos.needsUpdate = true;
  ring.geometry.computeVertexNormals();
}

// ─── Earrings ────────────────────────────────────────────────────────────────

function buildEarrings() {
  const earMat = new THREE.MeshStandardMaterial({
    color: '#D4A017',
    metalness: 0.9,
    roughness: 0.15,
  });

  const earGeo = new THREE.TorusGeometry(0.08, 0.015, 8, 12);

  // 3 on left side
  const leftPositions = [
    [-0.55, 0.45, 0.15],
    [-0.55, 0.25, 0.15],
    [-0.55, 0.05, 0.15],
  ];
  for (const pos of leftPositions) {
    const mesh = new THREE.Mesh(earGeo.clone(), earMat);
    mesh.position.set(pos[0], pos[1], pos[2]);
    mesh.userData.baseRotation = new THREE.Euler(0, 0, 0);
    mesh.userData.jingleIntensity = 0;
    scene.add(mesh);
    earrings.push(mesh);
  }

  // 1 on right side
  const rightPos = [0.55, 0.25, 0.15];
  const mesh = new THREE.Mesh(earGeo.clone(), earMat);
  mesh.position.set(rightPos[0], rightPos[1], rightPos[2]);
  mesh.userData.baseRotation = new THREE.Euler(0, 0, 0);
  mesh.userData.jingleIntensity = 0;
  scene.add(mesh);
  earrings.push(mesh);
}

// Earrings animate via updateEarrings() with natural decay

// ─── Particle System ────────────────────────────────────────────────────────

function buildParticles() {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const colors = new Float32Array(PARTICLE_COUNT * 3);
  const sizes = new Float32Array(PARTICLE_COUNT);
  particleVelocities = new Float32Array(PARTICLE_COUNT);

  const colorA = new THREE.Color('#1A0005');
  const colorB = new THREE.Color('#FF003F');

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    // Spherical shell distribution
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = PARTICLE_INNER + Math.random() * (PARTICLE_OUTER - PARTICLE_INNER);

    positions[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
    positions[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * r;
    positions[i * 3 + 2] = Math.cos(phi) * r;

    // Color lerp between dark red and bright red
    const t = Math.random();
    const c = colorA.clone().lerp(colorB, t);
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;

    sizes[i] = 0.01 + Math.random() * 0.03;
    particleVelocities[i] = 0.2 + Math.random() * 0.5;
  }

  particlePositions = positions;

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const mat = new THREE.PointsMaterial({
    size: 0.03,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.8,
  });

  particles = new THREE.Points(geo, mat);
  scene.add(particles);
}

// ─── Animation Loop ────────────────────────────────────────────────────────

function animate() {
  animFrameId = requestAnimationFrame(animate);
  const delta = clock.getDelta();

  // Decay state variables
  compressionIntensity *= ringWaveDecay;
  deesserFlash *= 0.85;
  if (systemReadyPulse > 0) systemReadyPulse -= delta * 2;
  if (celebrationWave > 0) celebrationWave -= delta * 0.5;

  // Skull slow rotation
  skull.rotation.y += ringRotationSpeed;

  // Skull vibration from compression
  if (compressionIntensity > 0.01) {
    skullVibrateOffset.set(
      (Math.random() - 0.5) * compressionIntensity * 0.05,
      (Math.random() - 0.5) * compressionIntensity * 0.05,
      0
    );
    skull.position.copy(skullVibrateOffset);
  } else {
    skull.position.lerp(new THREE.Vector3(0, -0.1, 0), 0.1);
  }

  // Ring deformation
      updateRingDeformation();

  // Ring color lerp
  ringColorCurrent.lerp(ringColorTarget, 0.05);
  if (ring) {
    ring.material.color.copy(ringColorCurrent);
    ring.material.emissive.copy(ringColorCurrent);
  }

  // Eye socket glow
    updateEyes();

  // Particles
  updateParticles(delta);

  // Earrings jingle
  updateEarrings(delta);

  // Audition tilt
  if (Math.abs(auditionTilt) > 0.001) {
    skull.rotation.z += (auditionTilt - skull.rotation.z) * 0.05;
  }

  // Render
  composer.render();
}

function updateRingDeformation() {
  if (!ring) return;

  const amplitudes = new Array(RING_SEGMENTS).fill(0);
  const time = clock.elapsedTime;

  // Base wave from compression
  if (compressionIntensity > 0.01) {
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle - time * 4) * compressionIntensity * 0.15;
    }
  }

  // BPM pulse
  if (bpmInterval > 0) {
    bpmPhase += delta / bpmInterval;
    const pulse = Math.sin(bpmPhase * Math.PI * 2) * 0.5 + 0.5;
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle + time * 2) * pulse * 0.15;
    }
  }

  // De-esser flash ripple
  if (deesserFlash > 0.01) {
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle) * deesserFlash * 0.1;
    }
  }

  // Celebration wave
  if (celebrationWave > 0) {
    const wavePhase = (time * 3) % (Math.PI * 2);
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle * 2 - wavePhase) * celebrationWave * 0.2;
    }
  }

  // System ready pulse
  if (systemReadyPulse > 0) {
    const pulse = Math.sin(time * 6) * systemReadyPulse;
    for (let i = 0; i < RING_SEGMENTS; i++) {
      amplitudes[i] += pulse * 0.1;
    }
  }

  // Activity level ambient motion
  if (activityLevel > 0) {
    for (let i = 0; i < RING_SEGMENTS; i++) {
      const angle = (i / RING_SEGMENTS) * Math.PI * 2;
      amplitudes[i] += Math.sin(angle * 3 + time * 1.5) * activityLevel * 0.03;
    }
  }

  deformRing(amplitudes);
}

function updateEyes() {
  if (!eyeLeft || !eyeRight) return;

  let intensity = 0.5; // base

  if (deesserFlash > 0.01) {
    intensity += deesserFlash * 2;
  }

  if (deepScanMode) {
    intensity += 0.3 + Math.sin(clock.elapsedTime * 4) * 0.2;
  }

  if (systemReadyPulse > 0) {
    intensity += systemReadyPulse * 0.5;
  }

  eyeLeft.material.emissiveIntensity = intensity;
  eyeRight.material.emissiveIntensity = intensity;
}

function updateParticles(delta) {
  if (!particles) return;

  const pos = particles.geometry.attributes.position;
  const array = pos.array;
  const time = clock.elapsedTime;

  const speed = particleOrbitSpeed * (listeningMode ? 0.3 : 1) * (deepScanMode ? 2.5 : 1) * (0.5 + activityLevel * 0.5);

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const idx = i * 3;
    const x = array[idx];
    const z = array[idx + 2];

    // Orbit around Y axis
    const theta = Math.atan2(z, x) + speed * delta * particleVelocities[i];
    const r = Math.sqrt(x * x + z * z);
    array[idx] = Math.cos(theta) * r;
    array[idx + 2] = Math.sin(theta) * r;

    // Slight vertical oscillation
    array[idx + 1] += Math.sin(time + i) * delta * 0.02;
  }

  pos.needsUpdate = true;
}

function updateEarrings(_delta) {
  const time = clock.elapsedTime;
  for (const e of earrings) {
    let intensity = e.userData.jingleIntensity || 0;
    intensity *= 0.95; // decay
    e.userData.jingleIntensity = intensity;

    const swing = Math.sin(time * 3 + e.position.x * 10) * (0.02 + intensity * 0.08);
    e.rotation.z = swing;
    e.rotation.x = Math.sin(time * 2.5 + e.position.y * 5) * (0.01 + intensity * 0.05);
  }
}

// ─── DSP Event Handlers ─────────────────────────────────────────────────────

function onSystemReady() {
  // 3 expanding pulses on ring
  systemReadyPulse = 1.0;

  // Eye sockets glow brighter
  if (eyeLeft) eyeLeft.material.emissiveIntensity = 1.5;
  if (eyeRight) eyeRight.material.emissiveIntensity = 1.5;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.material.emissiveIntensity = 0.5;
    if (eyeRight) eyeRight.material.emissiveIntensity = 0.5;
  }, 1000);

  // Particles burst outward then settle
  if (particles) {
    const pos = particles.geometry.attributes.position;
    const array = pos.array;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;
      const burst = 1.5;
      array[idx] *= burst;
      array[idx + 1] *= burst;
      array[idx + 2] *= burst;
    }
    pos.needsUpdate = true;
  }
}

function onCompression(ratio, releaseMs) {
  const amplitude = Math.min(0.3, (ratio - 1) * 0.05);
  compressionIntensity = amplitude;
  ringWaveDecay = Math.max(0.85, 1 - (releaseMs || 150) / 2000);

  // Skull vibration
  skullVibrateOffset.set(
    (Math.random() - 0.5) * amplitude * 0.1,
    (Math.random() - 0.5) * amplitude * 0.1,
    0
  );
}

function onGlueCompression(ratio) {
  const amplitude = Math.min(0.3, (ratio - 1) * 0.3);
  compressionIntensity = Math.max(compressionIntensity, amplitude);

  // Ring color brightens momentarily
  ringColorTarget.set('#FF3366');
  setTimeout(() => {
    ringColorTarget.set('#FF003F');
  }, 200);
}

function onDeesser() {
  deesserFlash = 1.0;

  // Eye sockets flash bright red
  if (eyeLeft) eyeLeft.material.emissiveIntensity = 2.0;
  if (eyeRight) eyeRight.material.emissiveIntensity = 2.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.material.emissiveIntensity = 0.5;
    if (eyeRight) eyeRight.material.emissiveIntensity = 0.5;
  }, 150);
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
    ringRotationSpeed = 0.001;
    particleOrbitSpeed = 0.0003;
  } else {
    ringRotationSpeed = 0.003;
    particleOrbitSpeed = 0.0008;
  }
}

function onDeepScan(_stemCount) {
  deepScanMode = true;
  ringRotationSpeed = 0.008;
  ringColorTarget.set('#FF0044');
  particleOrbitSpeed = 0.002;
}

function onDeepScanDone() {
  deepScanMode = false;
  ringRotationSpeed = 0.003;
  ringColorTarget.set('#FF003F');
  particleOrbitSpeed = 0.0008;
}

function onStep(_text) {
  // Small ring ripple
  compressionIntensity = Math.max(compressionIntensity, 0.05);
}

function onDone() {
  // Celebration wave: 3 full ripples
  celebrationWave = 1.0;

  // Particles burst
  if (particles) {
    const pos = particles.geometry.attributes.position;
    const array = pos.array;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;
      array[idx] *= 1.3;
      array[idx + 1] *= 1.3;
      array[idx + 2] *= 1.3;
    }
    pos.needsUpdate = true;
  }

  // Eye sockets flash
  if (eyeLeft) eyeLeft.material.emissiveIntensity = 2.0;
  if (eyeRight) eyeRight.material.emissiveIntensity = 2.0;
  setTimeout(() => {
    if (eyeLeft) eyeLeft.material.emissiveIntensity = 0.5;
    if (eyeRight) eyeRight.material.emissiveIntensity = 0.5;
  }, 300);
}

function onAuditionState(state) {
  if (state === 'BEFORE') {
    auditionTilt = 0.05;
    ringColorTarget.set('#FF6600');
  } else if (state === 'AFTER') {
    auditionTilt = -0.03;
    ringColorTarget.set('#FF003F');
  } else {
    auditionTilt = 0;
    ringColorTarget.set('#FF003F');
  }
}

function setActivity(level) {
  activityLevel = Math.max(0, Math.min(1, level));
  ringRotationSpeed = 0.001 + activityLevel * 0.004;
  particleOrbitSpeed = 0.0003 + activityLevel * 0.001;
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
  if (renderer) {
    renderer.dispose();
  }
  if (composer) {
    composer.dispose();
  }
  // Remove objects from scene
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
  particles = null;
  earrings = [];
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
  setActivity,
};
