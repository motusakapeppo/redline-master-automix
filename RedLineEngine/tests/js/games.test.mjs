// Node built-in test runner: `node --test tests/js`
// games.js is a plain browser script (no import/export) that attaches its
// helpers to the global object -- importing it here runs that side effect.
// The pure game-logic functions are deliberately DOM-free, so they run in
// Node exactly as they do in the browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import "../../app/web/games.js";

const G = globalThis.RedlineGames;

// ---------------------------------------------------------------------------
// Public surface
// ---------------------------------------------------------------------------

test("exposes the public API (open/close/pause/resume)", () => {
  assert.equal(typeof G.open, "function");
  assert.equal(typeof G.close, "function");
  assert.equal(typeof G.pause, "function");
  assert.equal(typeof G.resume, "function");
  assert.equal(typeof G.togglePause, "function");
  assert.equal(typeof G.isOpen, "function");
});

test("GAMES lists snake, pacman and galaga with Italian labels + hints", () => {
  assert.deepEqual(G.GAMES.map((g) => g.id), ["snake", "pacman", "galaga"]);
  for (const g of G.GAMES) {
    assert.equal(typeof g.label, "string");
    assert.ok(g.label.length > 0, "label must not be empty");
    assert.equal(typeof g.hint, "string");
    assert.ok(g.hint.length > 0, "hint must not be empty");
  }
});

test("dirFromKey maps arrows and WASD, null for anything else", () => {
  assert.deepEqual(G.dirFromKey("ArrowUp"), { x: 0, y: -1 });
  assert.deepEqual(G.dirFromKey("w"), { x: 0, y: -1 });
  assert.deepEqual(G.dirFromKey("W"), { x: 0, y: -1 });
  assert.deepEqual(G.dirFromKey("ArrowDown"), { x: 0, y: 1 });
  assert.deepEqual(G.dirFromKey("s"), { x: 0, y: 1 });
  assert.deepEqual(G.dirFromKey("ArrowLeft"), { x: -1, y: 0 });
  assert.deepEqual(G.dirFromKey("a"), { x: -1, y: 0 });
  assert.deepEqual(G.dirFromKey("ArrowRight"), { x: 1, y: 0 });
  assert.deepEqual(G.dirFromKey("d"), { x: 1, y: 0 });
  assert.equal(G.dirFromKey("q"), null);
  assert.equal(G.dirFromKey(""), null);
  assert.equal(G.dirFromKey(null), null);
});

test("UI entry points are safe no-ops without a DOM (Node import)", () => {
  assert.doesNotThrow(() => G.open("snake"));
  assert.doesNotThrow(() => G.pause());
  assert.doesNotThrow(() => G.resume());
  assert.doesNotThrow(() => G.togglePause());
  assert.doesNotThrow(() => G.close());
  assert.equal(G.isOpen(), false);
});

// ---------------------------------------------------------------------------
// Snake
// ---------------------------------------------------------------------------

test("createSnakeState: centered 3-segment snake heading right, food off-body", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  assert.equal(s.cols, 12);
  assert.equal(s.rows, 12);
  assert.equal(s.snake.length, 3);
  assert.deepEqual(s.snake[0], { x: 6, y: 6 });
  assert.deepEqual(s.snake[1], { x: 5, y: 6 });
  assert.deepEqual(s.snake[2], { x: 4, y: 6 });
  assert.deepEqual(s.dir, { x: 1, y: 0 });
  assert.equal(s.score, 0);
  assert.equal(s.alive, true);
  // rng() === 0 pins the deterministic first free cell (row-major scan).
  assert.deepEqual(s.food, { x: 0, y: 0 });
  assert.ok(!s.snake.some((p) => p.x === s.food.x && p.y === s.food.y));
});

test("stepSnake moves the head and keeps length without food", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  const next = G.stepSnake(s, { x: 1, y: 0 });
  assert.deepEqual(next.snake[0], { x: 7, y: 6 });
  assert.equal(next.snake.length, 3);
  assert.equal(next.alive, true);
  assert.equal(next.score, 0);
});

test("stepSnake grows and scores when eating food", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  const withFood = { ...s, food: { x: 7, y: 6 } };
  const next = G.stepSnake(withFood, { x: 1, y: 0 });
  assert.equal(next.score, 1);
  assert.equal(next.snake.length, 4);
  assert.deepEqual(next.snake[0], { x: 7, y: 6 });
  assert.ok(next.food, "a new food must be spawned");
  assert.ok(!next.snake.some((p) => p.x === next.food.x && p.y === next.food.y));
});

test("stepSnake ignores a reversal into its own body", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  const next = G.stepSnake(s, { x: -1, y: 0 });
  assert.deepEqual(next.dir, { x: 1, y: 0 });
  assert.deepEqual(next.snake[0], { x: 7, y: 6 });
  assert.equal(next.alive, true);
});

test("stepSnake dies on a wall", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  const atEdge = { ...s, snake: [{ x: 11, y: 6 }, { x: 10, y: 6 }, { x: 9, y: 6 }] };
  const next = G.stepSnake(atEdge, { x: 1, y: 0 });
  assert.equal(next.alive, false);
});

test("stepSnake dies on self-collision", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  const coiled = {
    ...s,
    snake: [
      { x: 5, y: 5 }, { x: 4, y: 5 }, { x: 4, y: 6 },
      { x: 5, y: 6 }, { x: 6, y: 6 }, { x: 6, y: 5 },
    ],
    dir: { x: 0, y: 1 },
  };
  const next = G.stepSnake(coiled, { x: 0, y: 1 });
  assert.equal(next.alive, false);
});

test("stepSnake tolerates a null/invalid direction", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  const next = G.stepSnake(s, null);
  assert.deepEqual(next.dir, { x: 1, y: 0 });
  assert.equal(next.alive, true);
  assert.deepEqual(next.snake[0], { x: 7, y: 6 });
});

test("stepSnake does not mutate the input state", () => {
  const s = G.createSnakeState({ cols: 12, rows: 12, rng: () => 0 });
  // Compare serialized forms: the state carries an `rng` function that
  // JSON.stringify drops, so both sides must be normalized the same way.
  const snapshot = JSON.parse(JSON.stringify(s));
  G.stepSnake(s, { x: 1, y: 0 });
  assert.deepEqual(JSON.parse(JSON.stringify(s)), snapshot);
});

// ---------------------------------------------------------------------------
// Pac-Man
// ---------------------------------------------------------------------------

test("PACMAN_MAZE is a rectangular, wall-bordered grid", () => {
  const maze = G.PACMAN_MAZE;
  assert.ok(Array.isArray(maze) && maze.length >= 9);
  const w = maze[0].length;
  for (const row of maze) {
    assert.equal(row.length, w, "every row must have the same width");
    assert.equal(row[0], "#");
    assert.equal(row[w - 1], "#");
  }
  assert.ok(maze[0].split("").every((c) => c === "#"), "top border all walls");
  assert.ok(maze[maze.length - 1].split("").every((c) => c === "#"), "bottom border all walls");
});

test("createPacmanState starts pacman and ghost on open dotted cells", () => {
  const s = G.createPacmanState();
  assert.equal(s.alive, true);
  assert.equal(s.won, false);
  assert.equal(s.score, 0);
  assert.ok(s.dotsLeft > 0);
  assert.equal(s.maze[s.pacman.y][s.pacman.x], ".");
  assert.equal(s.maze[s.ghost.y][s.ghost.x], ".");
  assert.notDeepEqual(s.pacman, s.ghost);
  assert.equal(s.dots[s.pacman.y][s.pacman.x], true);
});

test("stepPacman moves into an open cell", () => {
  const s = G.createPacmanState();
  const next = G.stepPacman(s, { x: 1, y: 0 });
  assert.deepEqual(next.pacman, { x: s.pacman.x + 1, y: s.pacman.y });
});

test("stepPacman is blocked by a wall", () => {
  const s = G.createPacmanState();
  // pacman starts on the bottom corridor; moving down hits the border wall.
  const next = G.stepPacman(s, { x: 0, y: 1 });
  assert.deepEqual(next.pacman, s.pacman);
});

test("stepPacman eats a dot and scores", () => {
  const s = G.createPacmanState();
  const next = G.stepPacman(s, { x: 1, y: 0 });
  assert.equal(next.score, 10);
  assert.equal(next.dotsLeft, s.dotsLeft - 1);
  assert.equal(next.dots[next.pacman.y][next.pacman.x], false);
});

test("stepPacman ghost closes the distance when pacman is blocked", () => {
  const s = G.createPacmanState();
  const next = G.stepPacman(s, { x: 0, y: 1 }); // blocked by the bottom wall
  const d = (a, b) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
  assert.ok(
    d(next.ghost, next.pacman) < d(s.ghost, s.pacman),
    "ghost must take a shortest-path step toward pacman"
  );
});

test("stepPacman catches pacman when the ghost lands on it", () => {
  const s = G.createPacmanState();
  const adjacent = { ...s, ghost: { x: s.pacman.x + 1, y: s.pacman.y } };
  const next = G.stepPacman(adjacent, { x: 0, y: 1 }); // pacman blocked, ghost steps onto it
  assert.equal(next.alive, false);
});

test("stepPacman wins when the last dot is eaten", () => {
  const s = G.createPacmanState();
  const dots = s.dots.map((row) => row.map(() => false));
  dots[s.pacman.y][s.pacman.x + 1] = true;
  const last = { ...s, dots, dotsLeft: 1 };
  const next = G.stepPacman(last, { x: 1, y: 0 });
  assert.equal(next.dotsLeft, 0);
  assert.equal(next.won, true);
  assert.equal(next.score, 10);
});

test("stepPacman does not mutate the input state", () => {
  const s = G.createPacmanState();
  const snapshot = JSON.parse(JSON.stringify(s));
  G.stepPacman(s, { x: 1, y: 0 });
  assert.deepEqual(s, snapshot);
});

// ---------------------------------------------------------------------------
// Galaga
// ---------------------------------------------------------------------------

test("spawnWave is deterministic and grows with the wave number", () => {
  const w1 = G.spawnWave(1, { cols: 15, rows: 18 });
  const w1b = G.spawnWave(1, { cols: 15, rows: 18 });
  assert.deepEqual(w1, w1b);
  assert.ok(w1.length > 0);
  for (const e of w1) {
    assert.ok(e.x >= 0 && e.x < 15);
    assert.ok(e.y >= 0 && e.y < 18);
    assert.equal(e.alive, true);
  }
  const w5 = G.spawnWave(5, { cols: 15, rows: 18 });
  assert.ok(w5.length > w1.length, "later waves must be denser");
});

test("waveSpeed increases (fewer ticks per move) with the wave number", () => {
  assert.ok(G.waveSpeed(2) < G.waveSpeed(1));
  assert.ok(G.waveSpeed(9) >= 2);
});

test("createGalagaState centers the ship with a wave-1 formation", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  assert.equal(s.ship.x, 7);
  assert.equal(s.wave, 1);
  assert.equal(s.score, 0);
  assert.equal(s.alive, true);
  assert.deepEqual(s.bullets, []);
  assert.equal(s.enemies.length, G.spawnWave(1, { cols: 15, rows: 18 }).length);
});

test("stepGalaga moves the ship and clamps at the edges", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  assert.equal(G.stepGalaga(s, { right: true }).ship.x, 8);
  assert.equal(G.stepGalaga(s, { left: true }).ship.x, 6);
  assert.equal(G.stepGalaga({ ...s, ship: { x: 0 } }, { left: true }).ship.x, 0);
  assert.equal(G.stepGalaga({ ...s, ship: { x: 14 } }, { right: true }).ship.x, 14);
});

test("stepGalaga fires a bullet and respects the cooldown", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  const fired = G.stepGalaga(s, { fire: true });
  assert.equal(fired.bullets.length, 1);
  assert.equal(fired.bullets[0].x, s.ship.x);
  assert.ok(fired.bullets[0].y < s.rows - 1, "bullet must be on the field");
  const again = G.stepGalaga(fired, { fire: true });
  assert.equal(again.bullets.length, 1, "cooldown blocks a second shot");
});

test("stepGalaga bullets travel upward and leave the field", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  const fired = G.stepGalaga(s, { fire: true });
  const moved = G.stepGalaga(fired, {});
  assert.equal(moved.bullets[0].y, fired.bullets[0].y - 1);
  const gone = { ...s, bullets: [{ x: 7, y: 0 }] };
  assert.equal(G.stepGalaga(gone, {}).bullets.length, 0);
});

test("stepGalaga scores when a bullet hits an enemy", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  const target = s.enemies[0];
  // The bullet moves one cell up before the collision check, so aim one
  // cell below the target.
  const aimed = { ...s, bullets: [{ x: target.x, y: target.y + 1 }] };
  const next = G.stepGalaga(aimed, {});
  assert.equal(next.score, 100);
  assert.ok(!next.enemies.some((e) => e.x === target.x && e.y === target.y));
});

test("stepGalaga ends when an enemy reaches the bottom", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  const invaded = { ...s, enemies: [{ x: 3, y: s.rows - 1, alive: true }] };
  assert.equal(G.stepGalaga(invaded, {}).alive, false);
});

test("stepGalaga advances to the next wave when cleared", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  const cleared = { ...s, enemies: [] };
  const next = G.stepGalaga(cleared, {});
  assert.equal(next.wave, 2);
  assert.ok(next.enemies.length > 0, "a fresh formation must spawn");
  assert.equal(next.waveCleared, true);
});

test("stepGalaga does not mutate the input state", () => {
  const s = G.createGalagaState({ cols: 15, rows: 18 });
  const snapshot = JSON.parse(JSON.stringify(s));
  G.stepGalaga(s, { left: true, fire: true });
  assert.deepEqual(s, snapshot);
});
