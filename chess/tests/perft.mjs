/*
 * Perft-Test fuer chess-core.js — vergleicht die Zuganzahl mit den
 * bekannten Referenzwerten der Chess Programming Wiki.
 * Aufruf:  node chess/tests/perft.mjs
 */
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const Chess = require('../js/chess-core.js');

function perft(pos, depth) {
  if (depth === 0) return 1;
  const moves = pos.generateMoves(false);
  let nodes = 0;
  for (let i = 0; i < moves.length; i++) {
    if (!pos.makeMove(moves[i])) continue;
    nodes += depth === 1 ? 1 : perft(pos, depth - 1);
    pos.undoMove();
  }
  return nodes;
}

const SUITES = [
  {
    name: 'Startstellung',
    fen: Chess.START_FEN,
    expect: [1, 20, 400, 8902, 197281, 4865609]
  },
  {
    name: 'Kiwipete',
    fen: 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1',
    expect: [1, 48, 2039, 97862, 4085603]
  },
  {
    name: 'Position 3 (Endspiel/en passant)',
    fen: '8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1',
    expect: [1, 14, 191, 2812, 43238, 674624]
  },
  {
    name: 'Position 4 (Umwandlungen)',
    fen: 'r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1',
    expect: [1, 6, 264, 9467, 422333]
  },
  {
    name: 'Position 5',
    fen: 'rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8',
    expect: [1, 44, 1486, 62379, 2103487]
  },
  {
    name: 'Position 6',
    fen: 'r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10',
    expect: [1, 46, 2079, 89890, 3894594]
  }
];

let failures = 0;
let totalNodes = 0;
const started = Date.now();

for (const suite of SUITES) {
  const pos = new Chess.Position(suite.fen);
  for (let depth = 1; depth < suite.expect.length; depth++) {
    const t0 = Date.now();
    const got = perft(pos, depth);
    const ms = Date.now() - t0;
    totalNodes += got;
    const ok = got === suite.expect[depth];
    if (!ok) failures++;
    console.log(
      `${ok ? 'OK  ' : 'FAIL'}  ${suite.name.padEnd(30)} d=${depth}  ` +
      `${String(got).padStart(9)}${ok ? '' : ` (erwartet ${suite.expect[depth]})`}  ${ms}ms`
    );
  }
  // Stellung muss nach allen Ruecknahmen unveraendert sein
  if (pos.getFen() !== suite.fen) {
    console.log(`FAIL  ${suite.name}: FEN nach undo veraendert -> ${pos.getFen()}`);
    failures++;
  }
}

/* ---------------------- SAN / PGN / Regel-Checks --------------------- */
function check(name, cond, extra = '') {
  if (cond) { console.log(`OK    ${name}`); return; }
  console.log(`FAIL  ${name} ${extra}`);
  failures++;
}

{
  const g = new Chess.Game();
  const line = ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6', 'Ba4', 'Nf6', 'O-O', 'Be7'];
  let ok = true;
  for (const san of line) if (!g.move(san)) { ok = false; break; }
  check('SAN: Spanische Eroeffnung spielbar', ok);
  check('SAN: Historie vollstaendig', g.history.length === 10, `(${g.history.length})`);
  check('SAN: Rochade als O-O notiert', g.history[8].san === 'O-O', g.history[8].san);
}

{
  // Narrenmatt
  const g = new Chess.Game();
  ['f3', 'e5', 'g4', 'Qh4'].forEach((m) => g.move(m));
  const st = g.status();
  check('Matt: Narrenmatt erkannt', st.over && st.reason === 'schachmatt' && st.result === '0-1', JSON.stringify(st));
  check('Matt: SAN endet auf #', g.history[3].san === 'Qh4#', g.history[3].san);
}

{
  // Patt
  const g = new Chess.Game('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1');
  const st = g.status();
  check('Patt erkannt', st.over && st.reason === 'patt', JSON.stringify(st));
}

{
  // En passant
  const g = new Chess.Game('rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3');
  const e = g.move('exf6');
  check('En passant schlagbar', !!e && e.enPassant, e ? e.san : 'null');
  check('En passant: geschlagener Bauer verschwindet von f5',
    g.fen().split(' ')[0] === 'rnbqkbnr/ppp1p1pp/5P2/3p4/8/8/PPPP1PPP/RNBQKBNR', g.fen());
}

{
  // Umwandlung
  const g = new Chess.Game('8/P6k/8/8/8/8/7K/8 w - - 0 1');
  const e = g.move('a8=Q');
  check('Umwandlung in Dame', !!e && e.promotion === 'q', e ? e.san : 'null');
}

{
  // Rochade durch Schach verboten
  const pos = new Chess.Position('r3k2r/8/8/8/8/8/8/4R2K b kq - 0 1');
  const sans = pos.generateLegalMoves().map((m) => pos.moveToSan(m));
  check('Rochade bei Schach auf e8 verboten', !sans.includes('O-O') && !sans.includes('O-O-O'), sans.join(','));
}

{
  // Dreifache Stellungswiederholung
  const g = new Chess.Game();
  ['Nf3', 'Nf6', 'Ng1', 'Ng8', 'Nf3', 'Nf6', 'Ng1', 'Ng8'].forEach((m) => g.move(m));
  const st = g.status();
  check('Dreifache Wiederholung erkannt', st.over && st.reason === 'stellungswiederholung', JSON.stringify(st));
}

{
  // Ungenuegendes Material
  const g = new Chess.Game('8/8/4k3/8/8/3KB3/8/8 w - - 0 1');
  check('K+L vs K ist Remis', g.status().reason === 'material');
  const g2 = new Chess.Game('8/8/4k3/8/8/3KR3/8/8 w - - 0 1');
  check('K+T vs K ist kein Remis', !g2.status().over);
}

{
  // FEN Roundtrip
  const fens = [
    'r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3',
    '8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1',
    'rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8'
  ];
  let ok = true;
  for (const f of fens) if (new Chess.Position(f).getFen() !== f) { ok = false; console.log('   -> ' + f); }
  check('FEN Roundtrip', ok);
}

{
  // PGN parsen (inkl. Kommentare, Varianten, NAGs)
  const pgn = `[Event "Test"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 {guter Zug} e5 2. Nf3 $1 (2. f4 exf4) 2... Nc6 3. Bb5 a6 1-0`;
  const parsed = Chess.parsePgn(pgn);
  check('PGN: Header gelesen', parsed.headers.White === 'A' && parsed.headers.Result === '1-0');
  check('PGN: 6 Hauptzuege trotz Varianten/Kommentaren', parsed.moves.length === 6, String(parsed.moves.length));
  check('PGN: Variantenzug f4 nicht uebernommen',
    parsed.moves.map((m) => m.san).join(' ') === 'e4 e5 Nf3 Nc6 Bb5 a6',
    parsed.moves.map((m) => m.san).join(' '));
  check('PGN: kein Parse-Abbruch', parsed.failedAt === -1, String(parsed.failedAt));
}

{
  // PGN-Ausgabe wieder einlesbar
  const g = new Chess.Game();
  ['d4', 'd5', 'c4', 'e6', 'Nc3', 'Nf6', 'Bg5', 'Be7'].forEach((m) => g.move(m));
  const round = Chess.parsePgn(g.pgn({ White: 'X', Black: 'Y' }));
  check('PGN: Export/Import Roundtrip', round.moves.length === 8, String(round.moves.length));
}

console.log(
  `\n${failures === 0 ? 'ALLE TESTS BESTANDEN' : failures + ' TEST(S) FEHLGESCHLAGEN'} — ` +
  `${totalNodes.toLocaleString('de-DE')} Knoten in ${((Date.now() - started) / 1000).toFixed(1)}s`
);
process.exit(failures === 0 ? 0 : 1);
