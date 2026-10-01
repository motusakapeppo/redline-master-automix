/**
 * games.js — "Pausa gioco": small, self-contained mini-games to pass the time
 * while a long render runs. Purely presentational: this module NEVER touches
 * the render pipeline, the 9 rack modules, or any engine event. No network,
 * no audio, no external dependencies.
 *
 * Loaded as a plain (non-module) script before app.js in index.html, so it
 * must not use import/export. Exposes `window.RedlineGames`.
 *
 * The core update logic of each game is a set of PURE functions
 * (createSnakeState/stepSnake, createPacmanState/stepPacman,
 * createGalagaState/stepGalaga, spawnWave, waveSpeed) that are DOM-free and
 * unit-tested under tests/js/games.test.mjs. The rendering/input layer below
 * is a thin shell around them and is a no-op when there is no DOM (Node).
 */
(function (global) {
  "use strict";

  // =========================================================================
  // Pure game logic (DOM-free, unit-tested)
  // =========================================================================

  // --- Snake ---------------------------------------------------------------

  function spawnFood(snake, cols, rows, rng) {
    const free = [];
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (!snake.some((p) => p.x === x && p.y === y)) free.push({ x: x, y: y });
      }
    }
    if (!free.length) return null;
    const r = typeof rng === "function" ? rng() : Math.random();
    const idx = Math.min(free.length - 1, Math.max(0, Math.floor(r * free.length)));
    return free[idx];
  }

  function createSnakeState(opts) {
    opts = opts || {};
    const cols = opts.cols || 12;
    const rows = opts.rows || 12;
    const rng = typeof opts.rng === "function" ? opts.rng : Math.random;
    const cx = Math.floor(cols / 2);
    const cy = Math.floor(rows / 2);
    const snake = [
      { x: cx, y: cy },
      { x: cx - 1, y: cy },
      { x: cx - 2, y: cy },
    ];
    return {
      cols: cols,
      rows: rows,
      snake: snake,
      dir: { x: 1, y: 0 },
      food: spawnFood(snake, cols, rows, rng),
      score: 0,
      alive: true,
      rng: rng,
    };
  }

  function stepSnake(state, dir) {
    const cols = state.cols;
    const rows = state.rows;
    let d = state.dir || { x: 1, y: 0 };
    if (dir && typeof dir.x === "number" && typeof dir.y === "number") {
      const isReverse = dir.x === -d.x && dir.y === -d.y;
      if (!isReverse || state.snake.length < 2) d = { x: dir.x, y: dir.y };
    }
    const head = state.snake[0];
    const newHead = { x: head.x + d.x, y: head.y + d.y };

    if (newHead.x < 0 || newHead.x >= cols || newHead.y < 0 || newHead.y >= rows) {
      return Object.assign({}, state, { dir: d, alive: false });
    }
    const eating = !!state.food && newHead.x === state.food.x && newHead.y === state.food.y;
    const body = eating ? state.snake : state.snake.slice(0, -1);
    if (body.some((p) => p.x === newHead.x && p.y === newHead.y)) {
      return Object.assign({}, state, { dir: d, alive: false });
    }
    const newSnake = [newHead].concat(state.snake);
    if (!eating) newSnake.pop();
    return Object.assign({}, state, {
      dir: d,
      snake: newSnake,
      food: eating ? spawnFood(newSnake, cols, rows, state.rng) : state.food,
      score: eating ? state.score + 1 : state.score,
      alive: true,
    });
  }

  // --- Pac-Man -------------------------------------------------------------

  // A rectangular, wall-bordered grid: '#' wall, '.' dot, ' ' empty. Horizontal
  // corridors at rows 1/3/5/7/9 joined by vertical connectors at cols 1/5/9/13,
  // so every open cell is reachable (the ghost's BFS always finds a path).
  const PACMAN_MAZE = [
    "###############",
    "#.............#",
    "#.###.###.###.#",
    "#.............#",
    "#.###.###.###.#",
    "#.............#",
    "#.###.###.###.#",
    "#.............#",
    "#.###.###.###.#",
    "#.............#",
    "###############",
  ];

  function createPacmanState() {
    const maze = PACMAN_MAZE.map((row) => row.split(""));
    const rows = maze.length;
    const cols = maze[0].length;
    const dots = maze.map((row) => row.map((c) => c === "."));
    let dotsLeft = 0;
    for (const row of dots) for (const d of row) if (d) dotsLeft++;
    return {
      maze: maze,
      dots: dots,
      dotsLeft: dotsLeft,
      pacman: { x: 7, y: 9 },
      ghost: { x: 1, y: 9 },
      score: 0,
      alive: true,
      won: false,
      cols: cols,
      rows: rows,
    };
  }

  // Breadth-first shortest path on open cells; returns the FIRST step from
  // `from` toward `to`, or null when unreachable / already there.
  function bfsStep(maze, from, to) {
    const rows = maze.length;
    const cols = maze[0].length;
    if (from.x === to.x && from.y === to.y) return null;
    const key = (x, y) => y * cols + x;
    const prev = new Map();
    const visited = new Set([key(from.x, from.y)]);
    const queue = [from];
    const dirs = [{ x: 1, y: 0 }, { x: -1, y: 0 }, { x: 0, y: 1 }, { x: 0, y: -1 }];
    let found = false;
    while (queue.length) {
      const cur = queue.shift();
      if (cur.x === to.x && cur.y === to.y) { found = true; break; }
      for (const d of dirs) {
        const nx = cur.x + d.x;
        const ny = cur.y + d.y;
        if (nx < 0 || nx >= cols || ny < 0 || ny >= rows) continue;
        if (maze[ny][nx] === "#") continue;
        const k = key(nx, ny);
        if (visited.has(k)) continue;
        visited.add(k);
        prev.set(k, cur);
        queue.push({ x: nx, y: ny });
      }
    }
    if (!found) return null;
    let cur = to;
    while (true) {
      const p = prev.get(key(cur.x, cur.y));
      if (!p) return null;
      if (p.x === from.x && p.y === from.y) return cur;
      cur = p;
    }
  }

  function stepPacman(state, dir) {
    const maze = state.maze;
    const rows = state.rows;
    const cols = state.cols;
    const dots = state.dots.map((row) => row.slice());
    let pacman = { x: state.pacman.x, y: state.pacman.y };
    let score = state.score;
    let dotsLeft = state.dotsLeft;
    let won = state.won;

    if (dir && typeof dir.x === "number" && typeof dir.y === "number") {
      const nx = pacman.x + dir.x;
      const ny = pacman.y + dir.y;
      if (nx >= 0 && nx < cols && ny >= 0 && ny < rows && maze[ny][nx] !== "#") {
        pacman = { x: nx, y: ny };
        if (dots[ny][nx]) {
          dots[ny][nx] = false;
          dotsLeft--;
          score += 10;
        }
      }
    }
    if (dotsLeft <= 0) won = true;

    let ghost = { x: state.ghost.x, y: state.ghost.y };
    const gstep = bfsStep(maze, ghost, pacman);
    if (gstep) ghost = gstep;

    let alive = state.alive;
    if (ghost.x === pacman.x && ghost.y === pacman.y) alive = false;

    return Object.assign({}, state, {
      dots: dots,
      pacman: pacman,
      ghost: ghost,
      score: score,
      dotsLeft: dotsLeft,
      alive: alive,
      won: won,
    });
  }

  // --- Galaga --------------------------------------------------------------

  function spawnWave(wave, opts) {
    opts = opts || {};
    const cols = opts.cols || 15;
    const rows = opts.rows || 18;
    const w = Math.max(1, Math.floor(wave) || 1);
    const enemyRows = Math.min(2 + w, 5);
    const enemyCols = Math.min(3 + w, Math.max(1, cols - 2));
    const startX = Math.floor((cols - enemyCols) / 2);
    const enemies = [];
    for (let r = 0; r < enemyRows; r++) {
      for (let c = 0; c < enemyCols; c++) {
        enemies.push({ x: startX + c, y: 1 + r, alive: true });
      }
    }
    return enemies;
  }

  // Ticks between enemy descents: fewer = faster. Never below 2.
  function waveSpeed(wave) {
    const w = Math.max(1, Math.floor(wave) || 1);
    return Math.max(2, 12 - w * 2);
  }

  function createGalagaState(opts) {
    opts = opts || {};
    const cols = opts.cols || 15;
    const rows = opts.rows || 18;
    return {
      cols: cols,
      rows: rows,
      ship: { x: Math.floor(cols / 2) },
      bullets: [],
      enemies: spawnWave(1, { cols: cols, rows: rows }),
      wave: 1,
      score: 0,
      alive: true,
      tick: 0,
      cooldown: 0,
      waveCleared: false,
    };
  }

  function stepGalaga(state, input) {
    input = input || {};
    const cols = state.cols;
    const rows = state.rows;

    const ship = { x: state.ship.x };
    if (input.right && !input.left) ship.x = Math.min(cols - 1, ship.x + 1);
    else if (input.left && !input.right) ship.x = Math.max(0, ship.x - 1);

    let cooldown = Math.max(0, (state.cooldown || 0) - 1);
    let bullets = state.bullets.map((b) => ({ x: b.x, y: b.y }));
    if (input.fire && cooldown === 0) {
      bullets.push({ x: ship.x, y: rows - 2 });
      cooldown = 2;
    }
    bullets = bullets.map((b) => ({ x: b.x, y: b.y - 1 })).filter((b) => b.y >= 0);

    let enemies = state.enemies.map((e) => ({ x: e.x, y: e.y, alive: e.alive }));
    let score = state.score;

    for (const b of bullets) {
      const idx = enemies.findIndex((e) => e.alive && e.x === b.x && e.y === b.y);
      if (idx !== -1) {
        enemies.splice(idx, 1);
        score += 100;
        b.y = -999; // consumed
      }
    }
    bullets = bullets.filter((b) => b.y >= 0);

    const tick = (state.tick || 0) + 1;
    if (tick % waveSpeed(state.wave) === 0) {
      enemies = enemies.map((e) => ({ x: e.x, y: e.y + 1, alive: e.alive }));
    }

    let alive = state.alive;
    if (enemies.some((e) => e.y >= rows - 1)) alive = false;

    let wave = state.wave;
    let waveCleared = false;
    if (enemies.length === 0 && alive) {
      wave = state.wave + 1;
      enemies = spawnWave(wave, { cols: cols, rows: rows });
      waveCleared = true;
    }

    return Object.assign({}, state, {
      ship: ship,
      bullets: bullets,
      enemies: enemies,
      score: score,
      alive: alive,
      tick: tick,
      cooldown: cooldown,
      wave: wave,
      waveCleared: waveCleared,
    });
  }

  // =========================================================================
  // Shared helpers
  // =========================================================================

  const GAMES = [
    { id: "snake", label: "Snake", hint: "Frecce o WASD per muoverti. Mangia i punti rossi senza toccare i bordi." },
    { id: "pacman", label: "Pac-Man", hint: "Frecce o WASD per muoverti. Mangia tutti i punti evitando il fantasma." },
    { id: "galaga", label: "Galaga", hint: "Frecce o WASD per muoverti, Spazio per sparare. Elimina l'ondata." },
  ];

  function dirFromKey(key) {
    if (typeof key !== "string") return null;
    switch (key) {
      case "ArrowUp": case "w": case "W": return { x: 0, y: -1 };
      case "ArrowDown": case "s": case "S": return { x: 0, y: 1 };
      case "ArrowLeft": case "a": case "A": return { x: -1, y: 0 };
      case "ArrowRight": case "d": case "D": return { x: 1, y: 0 };
      default: return null;
    }
  }

  function hasDom() {
    return typeof document !== "undefined" && !!document.getElementById;
  }

  function reducedMotion() {
    try {
      return !!(global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (e) {
      return false;
    }
  }

  // =========================================================================
  // UI shell (no-op without a DOM)
  // =========================================================================

  const GAME_INTERVALS = { snake: 120, pacman: 170, galaga: 90 };

  let _open = false;
  let _paused = false;
  let _gameOver = false;
  let _current = "snake";
  let _state = null;
  let _dir = { x: 1, y: 0 };
  let _keys = { left: false, right: false, fire: false };
  let _raf = null;
  let _last = 0;
  let _acc = 0;
  let _domReady = false;

  function initDom() {
    if (!hasDom() || _domReady) return;
    _domReady = true;
    const overlay = document.getElementById("game-break-overlay");
    if (!overlay) return;

    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("keyup", onKeyUp, true);

    overlay.querySelectorAll(".game-break-tab").forEach((tab) => {
      tab.addEventListener("click", () => startGame(tab.dataset.game));
    });
    const closeBtn = document.getElementById("game-break-close");
    if (closeBtn) closeBtn.addEventListener("click", close);
    const pauseBtn = document.getElementById("game-break-pause-btn");
    if (pauseBtn) pauseBtn.addEventListener("click", togglePause);
    const restartBtn = document.getElementById("game-break-restart");
    if (restartBtn) restartBtn.addEventListener("click", () => startGame(_current));
    const pauseOverlay = document.getElementById("game-break-pause");
    if (pauseOverlay) pauseOverlay.addEventListener("click", resume);
  }

  function onKeyDown(e) {
    if (!_open) return;
    const k = e.key;
    if (k === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
    if (k === "p" || k === "P") { e.preventDefault(); e.stopPropagation(); togglePause(); return; }
    if (k === "r" || k === "R") { e.preventDefault(); e.stopPropagation(); startGame(_current); return; }
    const dir = dirFromKey(k);
    if (dir) {
      e.preventDefault();
      e.stopPropagation();
      if (_current === "galaga") {
        if (dir.x < 0) _keys.left = true;
        if (dir.x > 0) _keys.right = true;
      } else {
        _dir = dir;
      }
      return;
    }
    if (k === " " || k === "Spacebar") {
      e.preventDefault();
      e.stopPropagation();
      if (_current === "galaga") _keys.fire = true;
    }
  }

  function onKeyUp(e) {
    if (!_open) return;
    const dir = dirFromKey(e.key);
    if (dir && _current === "galaga") {
      if (dir.x < 0) _keys.left = false;
      if (dir.x > 0) _keys.right = false;
    }
    if (e.key === " " || e.key === "Spacebar") _keys.fire = false;
  }

  function startGame(name) {
    if (!hasDom()) return;
    const id = GAMES.some((g) => g.id === name) ? name : "snake";
    _current = id;
    _gameOver = false;
    _paused = false;
    _acc = 0;
    _last = 0;
    _dir = { x: 1, y: 0 };
    _keys = { left: false, right: false, fire: false };

    if (id === "snake") _state = createSnakeState({ cols: 12, rows: 12 });
    else if (id === "pacman") _state = createPacmanState();
    else _state = createGalagaState({ cols: 15, rows: 18 });

    document.querySelectorAll(".game-break-tab").forEach((t) => {
      const on = t.dataset.game === id;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    const hint = document.getElementById("game-break-hint");
    const meta = GAMES.find((g) => g.id === id);
    if (hint && meta) hint.textContent = meta.hint;

    updateScore();
    updatePauseOverlay();
    if (!_raf) _raf = global.requestAnimationFrame(loop);
  }

  function tick() {
    if (_current === "snake") {
      _state = stepSnake(_state, _dir);
      if (!_state.alive) _gameOver = true;
    } else if (_current === "pacman") {
      _state = stepPacman(_state, _dir);
      if (!_state.alive || _state.won) _gameOver = true;
    } else {
      _state = stepGalaga(_state, { left: _keys.left, right: _keys.right, fire: _keys.fire });
      if (!_state.alive) _gameOver = true;
    }
    updateScore();
  }

  function loop(ts) {
    if (!_open) { _raf = null; return; }
    _raf = global.requestAnimationFrame(loop);
    if (!_last) _last = ts;
    const dt = Math.min(120, ts - _last);
    _last = ts;
    if (_paused || _gameOver) { render(); return; }
    _acc += dt;
    const interval = GAME_INTERVALS[_current] || 120;
    let guard = 0;
    while (_acc >= interval && guard < 5) {
      _acc -= interval;
      guard++;
      tick();
    }
    render();
  }

  function updateScore() {
    const el = document.getElementById("game-break-score");
    if (el && _state) el.textContent = String(_state.score || 0);
  }

  function updatePauseOverlay() {
    const el = document.getElementById("game-break-pause");
    if (el) el.classList.toggle("hidden", !_paused);
    const btn = document.getElementById("game-break-pause-btn");
    if (btn) btn.textContent = _paused ? "Riprendi" : "Pausa";
  }

  function open(name) {
    if (!hasDom()) return;
    initDom();
    const overlay = document.getElementById("game-break-overlay");
    if (!overlay) return;
    overlay.classList.remove("hidden");
    _open = true;
    startGame(name || _current || "snake");
    const canvas = document.getElementById("game-break-canvas");
    if (canvas) {
      canvas.setAttribute("tabindex", "0");
      if (canvas.focus) canvas.focus();
    }
  }

  function close() {
    if (!hasDom()) return;
    _open = false;
    _paused = false;
    if (_raf) { global.cancelAnimationFrame(_raf); _raf = null; }
    const overlay = document.getElementById("game-break-overlay");
    if (overlay) overlay.classList.add("hidden");
  }

  function pause() {
    if (!_open) return;
    _paused = true;
    updatePauseOverlay();
  }

  function resume() {
    if (!_open) return;
    _paused = false;
    _last = 0;
    updatePauseOverlay();
  }

  function togglePause() {
    if (!_open) return;
    if (_paused) resume(); else pause();
  }

  function isOpen() {
    return _open;
  }

  // --- Rendering -----------------------------------------------------------

  function layout(state, w, h) {
    const cell = Math.floor(Math.min(w / state.cols, h / state.rows));
    return {
      cell: cell,
      ox: Math.floor((w - cell * state.cols) / 2),
      oy: Math.floor((h - cell * state.rows) / 2),
    };
  }

  function renderSnake(ctx, state, w, h) {
    ctx.fillStyle = "#0A0A0A";
    ctx.fillRect(0, 0, w, h);
    const L = layout(state, w, h);
    ctx.strokeStyle = "rgba(255,0,63,0.07)";
    ctx.lineWidth = 1;
    for (let x = 0; x <= state.cols; x++) {
      ctx.beginPath();
      ctx.moveTo(L.ox + x * L.cell, L.oy);
      ctx.lineTo(L.ox + x * L.cell, L.oy + state.rows * L.cell);
      ctx.stroke();
    }
    for (let y = 0; y <= state.rows; y++) {
      ctx.beginPath();
      ctx.moveTo(L.ox, L.oy + y * L.cell);
      ctx.lineTo(L.ox + state.cols * L.cell, L.oy + y * L.cell);
      ctx.stroke();
    }
    if (state.food) {
      ctx.fillStyle = "#FF003F";
      if (!reducedMotion()) { ctx.shadowColor = "#FF003F"; ctx.shadowBlur = 10; }
      ctx.beginPath();
      ctx.arc(L.ox + state.food.x * L.cell + L.cell / 2, L.oy + state.food.y * L.cell + L.cell / 2, L.cell * 0.28, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    state.snake.forEach((p, i) => {
      ctx.fillStyle = i === 0 ? "#FF003F" : "rgba(255,0,63,0.5)";
      ctx.fillRect(L.ox + p.x * L.cell + 1, L.oy + p.y * L.cell + 1, L.cell - 2, L.cell - 2);
    });
  }

  function renderPacman(ctx, state, w, h) {
    ctx.fillStyle = "#0A0A0A";
    ctx.fillRect(0, 0, w, h);
    const L = layout(state, w, h);
    for (let y = 0; y < state.rows; y++) {
      for (let x = 0; x < state.cols; x++) {
        const px = L.ox + x * L.cell;
        const py = L.oy + y * L.cell;
        if (state.maze[y][x] === "#") {
          ctx.fillStyle = "rgba(255,0,63,0.28)";
          ctx.fillRect(px + 1, py + 1, L.cell - 2, L.cell - 2);
        } else if (state.dots[y][x]) {
          ctx.fillStyle = "rgba(255,255,255,0.55)";
          ctx.beginPath();
          ctx.arc(px + L.cell / 2, py + L.cell / 2, Math.max(1.5, L.cell * 0.1), 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    const pcx = L.ox + state.pacman.x * L.cell + L.cell / 2;
    const pcy = L.oy + state.pacman.y * L.cell + L.cell / 2;
    ctx.fillStyle = "#FF003F";
    if (!reducedMotion()) { ctx.shadowColor = "#FF003F"; ctx.shadowBlur = 12; }
    ctx.beginPath();
    ctx.arc(pcx, pcy, L.cell * 0.38, 0.25 * Math.PI, 1.75 * Math.PI);
    ctx.lineTo(pcx, pcy);
    ctx.closePath();
    ctx.fill();
    ctx.shadowBlur = 0;

    const gcx = L.ox + state.ghost.x * L.cell + L.cell / 2;
    const gcy = L.oy + state.ghost.y * L.cell + L.cell / 2;
    ctx.fillStyle = "#EAEAEA";
    ctx.beginPath();
    ctx.arc(gcx, gcy, L.cell * 0.34, Math.PI, 0);
    ctx.lineTo(gcx + L.cell * 0.34, gcy + L.cell * 0.34);
    ctx.lineTo(gcx - L.cell * 0.34, gcy + L.cell * 0.34);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#0A0A0A";
    ctx.beginPath(); ctx.arc(gcx - L.cell * 0.12, gcy - L.cell * 0.05, L.cell * 0.06, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(gcx + L.cell * 0.12, gcy - L.cell * 0.05, L.cell * 0.06, 0, Math.PI * 2); ctx.fill();
  }

  function renderGalaga(ctx, state, w, h) {
    ctx.fillStyle = "#0A0A0A";
    ctx.fillRect(0, 0, w, h);
    const L = layout(state, w, h);
    ctx.fillStyle = "rgba(255,255,255,0.12)";
    for (let i = 0; i < 40; i++) {
      ctx.fillRect(L.ox + ((i * 97) % (state.cols * L.cell)), L.oy + ((i * 53) % (state.rows * L.cell)), 1, 1);
    }
    state.enemies.forEach((e) => {
      const ex = L.ox + e.x * L.cell;
      const ey = L.oy + e.y * L.cell;
      ctx.fillStyle = "#FF003F";
      ctx.fillRect(ex + 2, ey + 2, L.cell - 4, L.cell - 4);
      ctx.fillStyle = "rgba(10,10,10,0.8)";
      ctx.fillRect(ex + L.cell * 0.3, ey + L.cell * 0.3, L.cell * 0.12, L.cell * 0.12);
      ctx.fillRect(ex + L.cell * 0.58, ey + L.cell * 0.3, L.cell * 0.12, L.cell * 0.12);
    });
    ctx.fillStyle = "#fff";
    state.bullets.forEach((b) => {
      ctx.fillRect(L.ox + b.x * L.cell + L.cell * 0.4, L.oy + b.y * L.cell, Math.max(2, L.cell * 0.2), L.cell * 0.6);
    });
    const sx = L.ox + state.ship.x * L.cell + L.cell / 2;
    const sy = L.oy + (state.rows - 1) * L.cell;
    ctx.fillStyle = "#FF003F";
    if (!reducedMotion()) { ctx.shadowColor = "#FF003F"; ctx.shadowBlur = 12; }
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx - L.cell * 0.45, sy + L.cell * 0.9);
    ctx.lineTo(sx + L.cell * 0.45, sy + L.cell * 0.9);
    ctx.closePath();
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  function drawGameOver(ctx, w, h) {
    ctx.fillStyle = "rgba(10,10,10,0.72)";
    ctx.fillRect(0, 0, w, h);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const won = _current === "pacman" && _state && _state.won;
    ctx.fillStyle = "#FF003F";
    ctx.font = "bold 28px Consolas, monospace";
    ctx.fillText(won ? "HAI VINTO" : "GAME OVER", w / 2, h / 2 - 14);
    ctx.fillStyle = "#EAEAEA";
    ctx.font = "14px Consolas, monospace";
    ctx.fillText("Premi R per ricominciare", w / 2, h / 2 + 20);
  }

  function render() {
    const canvas = document.getElementById("game-break-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    if (_current === "snake") renderSnake(ctx, _state, w, h);
    else if (_current === "pacman") renderPacman(ctx, _state, w, h);
    else renderGalaga(ctx, _state, w, h);
    if (_gameOver) drawGameOver(ctx, w, h);
  }

  // =========================================================================
  // Export
  // =========================================================================

  global.RedlineGames = {
    GAMES: GAMES,
    dirFromKey: dirFromKey,
    createSnakeState: createSnakeState,
    stepSnake: stepSnake,
    createPacmanState: createPacmanState,
    stepPacman: stepPacman,
    PACMAN_MAZE: PACMAN_MAZE,
    createGalagaState: createGalagaState,
    stepGalaga: stepGalaga,
    spawnWave: spawnWave,
    waveSpeed: waveSpeed,
    open: open,
    close: close,
    pause: pause,
    resume: resume,
    togglePause: togglePause,
    isOpen: isOpen,
  };

  if (hasDom()) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initDom);
    } else {
      initDom();
    }
  }
})(typeof window !== "undefined" ? window : globalThis);
