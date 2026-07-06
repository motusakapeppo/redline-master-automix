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
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

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
    scene.background = new THREE.Color('#0A0A0A');
    scene.fog = new THREE.Fog('#0A0A0A', 5, 8);

    camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 10);
    camera.position.set(0, 0.3, 3.8);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;

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

    // Composer
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));

    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(canvas.clientWidth, canvas.clientHeight),
      0.6, 0.4, 0.1
    );
    composer.addPass(bloomPass);

    // Vignette shader
    const vignettePass = new ShaderPass({
      uniforms: {
        tDiffuse: { value: null },
        offset: { value: 0.4 },
        darkness: { value: 0.6 },
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float offset;
        uniform float darkness;
        varying vec2 vUv;
        uniform sampler2D tDiffuse;
        void main() {
          vec4 texel = texture2D(tDiffuse, vUv);
          vec2 uv = (vUv - vec2(0.5)) * vec2(offset);
          gl_FragColor = vec4(mix(texel.rgb, vec3(0.0), dot(uv, uv) * darkness), texel.a);
        }
      `,
    });
    composer.addPass(vignettePass);
    composer.addPass(new OutputPass());

    buildSkull();
    buildRing();
    buildRingGlowParticles();
    buildEarrings();
    buildParticles();

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

  // Cranium: LatheGeometry with detailed skull profile
  const profilePoints = [];
  const profile = [
    [0.0, 0.0],
    [0.15, -0.02],
    [0.3, 0.0],
    [0.42, 0.05],
    [0.52, 0.12],
    [0.6, 0.2],
    [0.65, 0.28],
    [0.7, 0.38],
    [0.72, 0.48],
    [0.7, 0.58],
    [0.65, 0.68],
    [0.58, 0.78],
    [0.48, 0.88],
    [0.35, 0.95],
    [0.2, 1.0],
    [0.0, 1.02],
  ];
  for (const [x, y] of profile) {
    profilePoints.push(new THREE.Vector2(x, y));
  }
  const latheGeo = new THREE.LatheGeometry(profilePoints, 32);

  // Jaw: half sphere
  const jawGeo = new THREE.SphereGeometry(0.38, 16, 10, 0, Math.PI, 0, Math.PI / 2);
  jawGeo.rotateX(Math.PI);
  jawGeo.translate(0, -0.12, 0);

  // Cheekbone protrusions
  const cheekGeo = new THREE.SphereGeometry(0.12, 8, 8);
  cheekGeo.scale(1, 0.5, 0.6);
  cheekGeo.translate(-0.55, 0.15, 0.3);
  const cheekGeo2 = cheekGeo.clone();
  cheekGeo2.translate(1.1, 0, 0);

  // Merge
  const merged = mergeGeometries([latheGeo, jawGeo, cheekGeo, cheekGeo2]);
  merged.computeVertexNormals();

  // Vertex displacement for organic bone texture
  const pos = merged.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    const noise = Math.sin(x * 12) * Math.cos(y * 10) * Math.sin(z * 8) * 0.008;
    const scale = 1 + noise;
    pos.setXYZ(i, x * scale, y * scale, z * scale);
  }
  pos.needsUpdate = true;
  merged.computeVertexNormals();

  // Skull material with custom onBeforeCompile for fresnel-like effect
  const material = new THREE.MeshStandardMaterial({
    color: '#C8C8D0',
    metalness: 0.6,
    roughness: 0.3,
    envMapIntensity: 1.2,
  });

  craniumMesh = new THREE.Mesh(merged, material);
  craniumMesh.position.y = -0.1;
  group.add(craniumMesh);

  // Eye sockets: emissive red with glow
  const eyeMat = new THREE.MeshStandardMaterial({
    color: '#FF003F',
    emissive: '#FF003F',
    emissiveIntensity: 0.6,
  });

  eyeLeft = new THREE.Mesh(new THREE.SphereGeometry(0.28, 14, 14), eyeMat);
  eyeLeft.position.set(-0.35, 0.25, 0.5);
  eyeLeft.scale.set(1, 0.85, 0.7);
  group.add(eyeLeft);

  eyeRight = new THREE.Mesh(new THREE.SphereGeometry(0.28, 14, 14), eyeMat);
  eyeRight.position.set(0.35, 0.25, 0.5);
  eyeRight.scale.set(1, 0.85, 0.7);
  group.add(eyeRight);

  // Eye socket rims (darker rings around eyes)
  const rimMat = new THREE.MeshStandardMaterial({
    color: '#1A1A1A',
    metalness: 0.3,
    roughness: 0.8,
  });
  const rimGeo = new THREE.TorusGeometry(0.3, 0.03, 8, 20);
  const rimLeft = new THREE.Mesh(rimGeo, rimMat);
  rimLeft.position.set(-0.35, 0.25, 0.48);
  rimLeft.scale.set(1, 0.85, 0.7);
  group.add(rimLeft);
  const rimRight = new THREE.Mesh(rimGeo.clone(), rimMat);
  rimRight.position.set(0.35, 0.25, 0.48);
  rimRight.scale.set(1, 0.85, 0.7);
  group.add(rimRight);

  // Nose cavity
  const noseMat = new THREE.MeshStandardMaterial({
    color: '#0D0000',
    emissive: '#1A0005',
    emissiveIntensity: 0.15,
  });
  noseCavity = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.15, 8), noseMat);
  noseCavity.position.set(0, 0.05, 0.55);
  noseCavity.rotation.x = Math.PI / 2;
  group.add(noseCavity);

  // Nose bridge ridge
  const bridgeMat = new THREE.MeshStandardMaterial({
    color: '#B0B0B8',
    metalness: 0.5,
    roughness: 0.35,
  });
  const bridgeGeo = new THREE.CylinderGeometry(0.02, 0.06, 0.25, 6);
  bridgeGeo.rotateX(0.3);
  const bridge = new THREE.Mesh(bridgeGeo, bridgeMat);
  bridge.position.set(0, 0.2, 0.5);
  group.add(bridge);

  // Teeth row
  const teethMat = new THREE.MeshStandardMaterial({
    color: '#E8E8E0',
    metalness: 0.1,
    roughness: 0.6,
  });
  const teethGroup = new THREE.Group();
  for (let i = 0; i < 6; i++) {
    const t = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.06, 0.03), teethMat);
    const angle = (i / 6 - 0.5) * 0.8;
    t.position.set(Math.sin(angle) * 0.2, -0.08, 0.35 + Math.cos(angle) * 0.05 - 0.02);
    t.rotation.z = angle * 0.3;
    teethGroup.add(t);
  }
  group.add(teethGroup);

  // Temporal lines (subtle ridges on sides)
  const lineMat = new THREE.MeshStandardMaterial({
    color: '#A0A0A8',
    metalness: 0.4,
    roughness: 0.5,
  });
  for (let side = -1; side <= 1; side += 2) {
    const lineGeo = new THREE.CylinderGeometry(0.01, 0.015, 0.3, 4);
    lineGeo.rotateZ(side * 0.3);
    const line = new THREE.Mesh(lineGeo, lineMat);
    line.position.set(side * 0.55, 0.5, 0.1);
    group.add(line);
  }

  skull = group;
  scene.add(skull);
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
  idlePhase += delta;

  // Decay state variables
  compressionIntensity *= ringWaveDecay;
  deesserFlash *= 0.85;
  if (systemReadyPulse > 0) systemReadyPulse -= delta * 1.5;
  if (celebrationWave > 0) celebrationWave -= delta * 0.4;

  // Idle floating
  idleFloatPhase += delta * 0.5;
  const floatY = Math.sin(idleFloatPhase) * 0.015;
  const floatRotX = Math.sin(idleFloatPhase * 0.7) * 0.005;
  const floatRotZ = Math.sin(idleFloatPhase * 0.9) * 0.003;

  // Skull slow rotation + idle float
  skull.rotation.y += ringRotationSpeed;
  skull.position.y = -0.1 + floatY;
  skull.rotation.x += (floatRotX - skull.rotation.x) * 0.02;
  skull.rotation.z += (floatRotZ - skull.rotation.z) * 0.02;

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

  ringColorTarget.set('#FF3366');
  setTimeout(() => { ringColorTarget.set('#FF003F'); }, 250);

  // Strong earring jingle
  for (const e of earrings) {
    e.userData.jingleIntensity = Math.min(1, (e.userData.jingleIntensity || 0) + 0.5);
  }
}

function onDeesser() {
  deesserFlash = 1.0;

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
    ringRotationSpeed = 0.0008;
    particleOrbitSpeed = 0.0002;
  } else {
    ringRotationSpeed = 0.002 + activityLevel * 0.003;
    particleOrbitSpeed = 0.0003 + activityLevel * 0.001;
  }
}

function onDeepScan() {
  deepScanMode = true;
  ringRotationSpeed = 0.01;
  ringColorTarget.set('#FF0044');
  particleOrbitSpeed = 0.003;
}

function onDeepScanDone() {
  deepScanMode = false;
  ringRotationSpeed = 0.002 + activityLevel * 0.003;
  ringColorTarget.set('#FF003F');
  particleOrbitSpeed = 0.0003 + activityLevel * 0.001;
}

function onStep() {
  compressionIntensity = Math.max(compressionIntensity, 0.04);
}

function onDone() {
  celebrationWave = 1.0;

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
}

function onAuditionState(state) {
  if (state === 'BEFORE') {
    auditionTilt = 0.06;
    ringColorTarget.set('#FF6600');
  } else if (state === 'AFTER') {
    auditionTilt = -0.04;
    ringColorTarget.set('#FF003F');
  } else {
    auditionTilt = 0;
    ringColorTarget.set('#FF003F');
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
