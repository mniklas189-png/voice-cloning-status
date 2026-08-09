/*
 * Engine-Test.
 *
 * Statt geratener Puzzle-FENs pruefen wir Eigenschaften, die sich mit dem
 * (per Perft verifizierten) Regelwerk selbst nachweisen lassen:
 *   - behauptete Mattfolgen werden nachgespielt und muessen wirklich matt sein
 *   - haengendes Material muss geschlagen werden
 *   - die Bewertung muss spiegelsymmetrisch sein
 *
 * Aufruf:  node chess/tests/engine.mjs
 */
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const Chess = require('../js/chess-core.js');
globalThis.ChessCore = Chess;
const Engine = require('../js/engine.js');

let failures = 0;
function check(name, cond, extra = '') {
  if (cond) { console.log(`OK    ${name}`); return true; }
  console.log(`FAIL  ${name}${extra ? '  — ' + extra : ''}`);
  failures++;
  return false;
}

const searcher = new Engine.Searcher();
function bestMove(fen, movetime = 1000, maxDepth = 30) {
  const pos = new Chess.Position(fen);
  searcher.reset();
  return { pos, result: searcher.search(pos, { movetime, maxDepth }) };
}

/* ------------------------------------------------------------------ *
 * 1. Mattfolgen: Behauptung wird nachgespielt und ueberprueft.
 * ------------------------------------------------------------------ */
function expectForcedMate(name, fen, maxPlies) {
  const { pos, result } = bestMove(fen, 2000);
  const claimed = Engine.MATE - Math.abs(result.score);
  if (!check(`${name}: Engine meldet erzwungenes Matt`,
    Math.abs(result.score) >= Engine.MATE - 100 && result.score > 0,
    `Bewertung ${result.score}`)) return;
  check(`${name}: Matt in <= ${maxPlies} Halbzuegen`, claimed <= maxPlies, `gemeldet ${claimed}`);

  // Hauptvariante nachspielen — am Ende muss echtes Schachmatt stehen.
  const g = new Chess.Game(fen);
  let played = 0;
  for (const step of result.pv) {
    if (!g.move(step.move)) break;
    played++;
    if (g.status().over) break;
  }
  const st = g.status();
  check(`${name}: Hauptvariante endet wirklich im Matt`,
    st.over && st.reason === 'schachmatt',
    `nach ${played} Zuegen: ${st.text || 'kein Ende'} (${result.pv.map((p) => p.san).join(' ')})`);
}

// Turm-Grundreihenmatt: schwarzer Koenig g8, Bauern f7/g7/h7 versperren die Flucht.
expectForcedMate('Grundreihenmatt', '6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1', 1);
// Koenig+Turm gegen Koenig in der Ecke: Th7-h8 ist matt, b6 deckt a7/b7/b8.
expectForcedMate('Turmmatt in der Ecke', 'k7/7R/1K6/8/8/8/8/8 w - - 0 1', 1);
// Damenmatt: der eigene Koenig auf g6 versperrt die g-Linie, daher Matt in 2 (3 Halbzuege).
expectForcedMate('Damenmatt', '7k/8/6K1/8/8/8/8/6Q1 w - - 0 1', 3);
// Zwei Tuerme setzen mit der Treppe matt (Matt in 2).
expectForcedMate('Treppenmatt zweier Tuerme', '7k/8/8/8/8/8/R7/1R5K w - - 0 1', 3);
// Narrenmatt-Stellung: Schwarz hat Dh4 matt.
expectForcedMate('Schwarz setzt matt', 'rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2', 1);

/* ------------------------------------------------------------------ *
 * 2. Haengendes Material muss geschlagen werden.
 * ------------------------------------------------------------------ */
function expectMove(name, fen, expected, movetime = 1200) {
  const { result } = bestMove(fen, movetime);
  check(`${name}`, expected.includes(result.bestSan),
    `gespielt ${result.bestSan}, erwartet ${expected.join('/')} (Bew ${result.score}, d${result.depth})`);
}

expectMove('Freien Springer schlagen', '4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1', ['Rxd5']);
expectMove('Freie Dame schlagen', '4k3/8/8/3q4/2P5/8/8/4K3 w - - 0 1', ['cxd5']);
expectMove('Springergabel gewinnt Turm', 'r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1', ['Nc7+']);
expectMove('Bauer schlaegt statt zu verlieren', 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2', ['exd5']);

/* ------------------------------------------------------------------ *
 * 3. Bewertung muss spiegelsymmetrisch sein.
 * ------------------------------------------------------------------ */
function mirrorFen(fen) {
  const [board, turn, castling, ep, half, full] = fen.split(/\s+/);
  const rows = board.split('/').reverse().map((row) =>
    row.replace(/[a-zA-Z]/g, (c) => (c === c.toUpperCase() ? c.toLowerCase() : c.toUpperCase())));
  const cast = castling === '-' ? '-'
    : castling.replace(/[a-zA-Z]/g, (c) => (c === c.toUpperCase() ? c.toLowerCase() : c.toUpperCase()))
      .split('').sort((a, b) => 'KQkq'.indexOf(a) - 'KQkq'.indexOf(b)).join('');
  const epMirror = ep === '-' ? '-' : ep[0] + String(9 - parseInt(ep[1], 10));
  return `${rows.join('/')} ${turn === 'w' ? 'b' : 'w'} ${cast} ${epMirror} ${half} ${full}`;
}

const MIRROR_FENS = [
  Chess.START_FEN,
  'r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3',
  'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1',
  '8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1',
  'r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10',
  '4k3/pp4pp/8/8/8/8/PP4PP/4K3 w - - 0 1'
];
let mirrorOk = true;
for (const fen of MIRROR_FENS) {
  const a = Engine.evaluate(new Chess.Position(fen));
  const b = Engine.evaluate(new Chess.Position(mirrorFen(fen)));
  if (a !== b) { mirrorOk = false; console.log(`   ${fen}\n   -> ${a} vs gespiegelt ${b}`); }
}
check('Bewertung ist spiegelsymmetrisch (Farbtausch aendert nichts)', mirrorOk);

check('Startstellung nahe ausgeglichen', Math.abs(Engine.evaluate(new Chess.Position(Chess.START_FEN))) < 60,
  String(Engine.evaluate(new Chess.Position(Chess.START_FEN))));
check('Dame mehr wird klar bevorzugt',
  Engine.evaluate(new Chess.Position('rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')) > 700);

/* ------------------------------------------------------------------ *
 * 4. Static Exchange Evaluation
 * ------------------------------------------------------------------ */
function checkSee(name, fen, san, predicate, expectation) {
  const pos = new Chess.Position(fen);
  const m = pos.moveFromSan(san);
  if (!m) { check(`SEE ${name}`, false, `Zug ${san} nicht legal`); return; }
  const v = Engine.see(pos, m);
  check(`SEE ${name} (${san} = ${v})`, predicate(v), expectation);
}
checkSee('gedeckter Bauer kostet den Turm', '4k3/8/3p4/4p3/8/8/8/4R1K1 w - - 0 1', 'Rxe5',
  (v) => v <= -350, 'etwa -400 erwartet');
checkSee('freier Bauer ist Gewinn', '4k3/4p3/8/4p3/8/8/8/4R1K1 w - - 0 1', 'Rxe5',
  (v) => v >= 100, '+100 erwartet');
checkSee('ungedeckte Dame', '4k3/8/8/3q4/2P5/8/8/4K3 w - - 0 1', 'cxd5',
  (v) => v >= 800, '>= 800 erwartet');
checkSee('gleichwertiger Abtausch', '4k3/8/8/4n3/8/5N2/8/4K3 w - - 0 1', 'Nxe5',
  (v) => v >= 250, 'Springerwert erwartet');

/* ------------------------------------------------------------------ *
 * 5. Suche: tiefer darf nicht schlechter werden, Stellung bleibt intakt
 * ------------------------------------------------------------------ */
{
  const fen = 'r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3';
  const pos = new Chess.Position(fen);
  searcher.reset();
  searcher.search(pos, { movetime: 800, maxDepth: 20 });
  check('Suche laesst die Stellung unveraendert zurueck', pos.getFen() === fen, pos.getFen());
  check('Undo-Stack ist leer', pos.undoStack.length === 0, String(pos.undoStack.length));
}
{
  const fen = '4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1';
  const shallow = bestMove(fen, 50, 2).result;
  const deep = bestMove(fen, 1500, 20).result;
  check('Tiefere Suche erreicht mindestens die flache Bewertung', deep.score >= shallow.score - 30,
    `${shallow.score} -> ${deep.score}`);
  check('Hauptvariante ist nicht leer', deep.pv.length > 0);
}

/* ------------------------------------------------------------------ *
 * 6. Spielstaerke-Stufen
 * ------------------------------------------------------------------ */
{
  const { pos, result } = bestMove('6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1', 500);
  const legal = pos.generateLegalMoves();
  let alwaysMate = true, allLegal = true;
  for (let i = 0; i < 50; i++) if (Engine.pickWithSkill(result, 10, Math.random) !== result.bestMove) alwaysMate = false;
  for (let lvl = 0; lvl <= 10; lvl++) {
    for (let i = 0; i < 40; i++) {
      if (legal.indexOf(Engine.pickWithSkill(result, lvl, Math.random)) < 0) allLegal = false;
    }
  }
  check('Hoechste Stufe verpasst nie ein Matt in 1', alwaysMate);
  check('Alle 11 Stufen liefern ausschliesslich legale Zuege', allLegal);
  check('Stufenliste ist vollstaendig', Engine.LEVELS.length === 11, String(Engine.LEVELS.length));
}

/* ------------------------------------------------------------------ *
 * 7. Vollstaendige Selbstpartien — nie ein illegaler Zug, Partie endet
 * ------------------------------------------------------------------ */
{
  let illegal = 0, finished = 0, totalPlies = 0;
  for (let round = 0; round < 3; round++) {
    const g = new Chess.Game();
    const s = new Engine.Searcher();
    let plies = 0;
    while (!g.status().over && plies < 260) {
      s.reset();
      const keys = [];
      const replay = new Chess.Game();
      keys.push(replay.position.hashLo, replay.position.hashHi);
      for (const h of g.history) { replay.move(h.move); keys.push(replay.position.hashLo, replay.position.hashHi); }
      const r = s.search(g.position, { movetime: 30, maxDepth: 4, repetitionKeys: keys });
      if (!r.bestMove) break;
      if (!g.move(Engine.pickWithSkill(r, 5, Math.random))) { illegal++; break; }
      plies++;
    }
    totalPlies += plies;
    if (g.status().over) finished++;
  }
  check('Selbstpartien ohne illegalen Zug', illegal === 0, `${illegal} illegale Zuege`);
  check('Selbstpartien erreichen ein regulaeres Ende', finished === 3, `${finished}/3 beendet, ${totalPlies} Halbzuege gesamt`);
}

console.log(`\n${failures === 0 ? 'ALLE ENGINE-TESTS BESTANDEN' : failures + ' TEST(S) FEHLGESCHLAGEN'}`);
process.exit(failures === 0 ? 0 : 1);
