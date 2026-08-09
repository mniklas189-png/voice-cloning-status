/*
 * engine-worker.js — laesst die Suche im Hintergrund laufen,
 * damit die Oberflaeche waehrend des Rechnens fluessig bleibt.
 */
/* global importScripts, ChessCore, ChessEngine */
importScripts('chess-core.js', 'engine.js');

var searcher = new ChessEngine.Searcher();

self.onmessage = function (event) {
  var msg = event.data || {};

  if (msg.type === 'reset') {
    searcher.reset();
    return;
  }

  if (msg.type !== 'search') return;

  var pos;
  try {
    pos = new ChessCore.Position(msg.fen);
  } catch (err) {
    self.postMessage({ type: 'error', id: msg.id, message: 'Ungueltige Stellung: ' + err.message });
    return;
  }

  if (msg.freshTable) searcher.reset();

  var level = typeof msg.level === 'number' ? msg.level : 10;
  var levelInfo = ChessEngine.LEVELS[Math.max(0, Math.min(ChessEngine.LEVELS.length - 1, level))];
  var movetime = msg.movetime || levelInfo.movetime;
  var maxDepth = msg.maxDepth || levelInfo.depth;

  var started = Date.now();
  var result;
  try {
    result = searcher.search(pos, {
      movetime: movetime,
      maxDepth: maxDepth,
      repetitionKeys: msg.repetitionKeys || [],
      onProgress: msg.wantProgress ? function (info) {
        self.postMessage({
          type: 'progress', id: msg.id,
          depth: info.depth, score: info.score, nodes: info.nodes, san: info.san
        });
      } : null
    });
  } catch (err) {
    self.postMessage({ type: 'error', id: msg.id, message: String(err && err.message || err) });
    return;
  }

  // Zug entsprechend der Spielstaerke waehlen (Analyse nutzt immer den besten).
  var chosen = msg.applyLevel ? ChessEngine.pickWithSkill(result, level, Math.random) : result.bestMove;
  var chosenInfo = null;
  for (var i = 0; i < result.rootMoves.length; i++) {
    if (result.rootMoves[i].move === chosen) { chosenInfo = result.rootMoves[i]; break; }
  }

  self.postMessage({
    type: 'result',
    id: msg.id,
    fen: msg.fen,
    best: { move: result.bestMove, san: result.bestSan, uci: result.bestUci, score: result.score },
    chosen: chosenInfo
      ? { move: chosenInfo.move, san: chosenInfo.san, uci: chosenInfo.uci, score: chosenInfo.score }
      : { move: result.bestMove, san: result.bestSan, uci: result.bestUci, score: result.score },
    depth: result.depth,
    nodes: result.nodes,
    elapsed: Date.now() - started,
    pv: result.pv.map(function (p) { return { san: p.san, uci: p.uci }; }),
    rootMoves: result.rootMoves.slice(0, 6).map(function (m) {
      return { san: m.san, uci: m.uci, score: m.score, move: m.move };
    })
  });
};
