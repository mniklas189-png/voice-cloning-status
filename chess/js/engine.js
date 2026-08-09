/*
 * engine.js — Stellungsbewertung + Alpha-Beta-Suche.
 * Benoetigt chess-core.js. Laeuft im Worker und im Hauptthread.
 */
(function (global) {
  'use strict';

  var C = global.ChessCore || (typeof require === 'function' ? require('./chess-core.js') : null);
  if (!C) throw new Error('chess-core.js fehlt');

  var WHITE = C.WHITE, BLACK = C.BLACK;
  var PAWN = C.PAWN, KNIGHT = C.KNIGHT, BISHOP = C.BISHOP, ROOK = C.ROOK, QUEEN = C.QUEEN, KING = C.KING;
  var moveFrom = C.moveFrom, moveTo = C.moveTo, movePromo = C.movePromo, moveCaptured = C.moveCaptured;

  var MATE = 30000;
  var INF = 1000000;

  /* --------------------------- Figurenwerte -------------------------- */
  var VAL_MG = [0, 100, 325, 340, 500, 975, 0];
  var VAL_EG = [0, 120, 300, 320, 540, 960, 0];
  /** Grobe Werte fuer Tausch-Rechnungen und Anfaenger-Erklaerungen. */
  var VAL_SIMPLE = [0, 100, 300, 320, 500, 900, 20000];

  /* ------------------------ Positionstabellen ------------------------
   * Alle Tabellen aus Sicht von Weiss, Index 0 = a8 (passt direkt zum
   * 0x88-Layout: idx = (sq >> 4) * 8 + (sq & 7)).
   * ------------------------------------------------------------------ */
  var PST_PAWN = [
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0
  ];
  var PST_PAWN_EG = [
    0, 0, 0, 0, 0, 0, 0, 0,
    90, 90, 90, 90, 90, 90, 90, 90,
    55, 55, 55, 55, 55, 55, 55, 55,
    30, 30, 30, 30, 30, 30, 30, 30,
    18, 18, 18, 18, 18, 18, 18, 18,
    8, 8, 8, 8, 8, 8, 8, 8,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0
  ];
  var PST_KNIGHT = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50
  ];
  var PST_BISHOP = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20
  ];
  var PST_ROOK = [
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, 10, 10, 10, 10, 5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    0, 0, 0, 5, 5, 0, 0, 0
  ];
  var PST_QUEEN = [
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20
  ];
  var PST_KING_MG = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20
  ];
  var PST_KING_EG = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50
  ];

  var PST_MG = [null, PST_PAWN, PST_KNIGHT, PST_BISHOP, PST_ROOK, PST_QUEEN, PST_KING_MG];
  var PST_EG = [null, PST_PAWN_EG, PST_KNIGHT, PST_BISHOP, PST_ROOK, PST_QUEEN, PST_KING_EG];

  function pstIndex(sq, color) {
    var row = sq >> 4, file = sq & 7;
    return color === WHITE ? row * 8 + file : (7 - row) * 8 + file;
  }

  var PASSED_BONUS = [0, 8, 16, 32, 60, 100, 150, 0];   // nach Reihe (0 = eigene Grundreihe)

  /* --------------------------- Bewertung ----------------------------- */
  function evaluate(pos) {
    var b = pos.board;
    var mg = 0, eg = 0, phase = 0;
    var pawnFiles = [new Int8Array(8), new Int8Array(8)];
    var pawnSquares = [[], []];
    var bishops = [0, 0];
    var rooks = [[], []];
    var material = [0, 0];
    var sq, p, color, type, i, f;

    for (var r = 0; r < 8; r++) {
      for (f = 0; f < 8; f++) {
        sq = r * 16 + f;
        p = b[sq];
        if (!p) continue;
        color = p >> 3; type = p & 7;
        var sign = color === WHITE ? 1 : -1;
        var idx = pstIndex(sq, color);

        mg += sign * (VAL_MG[type] + PST_MG[type][idx]);
        eg += sign * (VAL_EG[type] + PST_EG[type][idx]);

        if (type === PAWN) { pawnFiles[color][f]++; pawnSquares[color].push(sq); }
        else if (type === BISHOP) bishops[color]++;
        else if (type === ROOK) rooks[color].push(sq);

        if (type !== KING && type !== PAWN) {
          material[color] += VAL_SIMPLE[type];
          phase += type === QUEEN ? 4 : type === ROOK ? 2 : 1;
        }
      }
    }

    // Laeuferpaar
    if (bishops[WHITE] >= 2) { mg += 30; eg += 45; }
    if (bishops[BLACK] >= 2) { mg -= 30; eg -= 45; }

    // Bauernstruktur
    for (color = 0; color < 2; color++) {
      var sgn = color === WHITE ? 1 : -1;
      var own = pawnFiles[color], opp = pawnFiles[color ^ 1];
      for (f = 0; f < 8; f++) {
        if (own[f] > 1) { mg -= sgn * 14 * (own[f] - 1); eg -= sgn * 22 * (own[f] - 1); }
        if (own[f] > 0) {
          var isolated = (f === 0 || own[f - 1] === 0) && (f === 7 || own[f + 1] === 0);
          if (isolated) { mg -= sgn * 16; eg -= sgn * 20; }
        }
      }
      for (i = 0; i < pawnSquares[color].length; i++) {
        sq = pawnSquares[color][i];
        f = sq & 7;
        var rank = color === WHITE ? 7 - (sq >> 4) : (sq >> 4);   // 0 = Grundreihe
        var blocked = false;
        for (var df = -1; df <= 1; df++) {
          var nf = f + df;
          if (nf < 0 || nf > 7) continue;
          if (opp[nf] === 0) continue;
          // steht ein gegnerischer Bauer noch vor diesem Bauern?
          for (var k = 0; k < pawnSquares[color ^ 1].length; k++) {
            var osq = pawnSquares[color ^ 1][k];
            if ((osq & 7) !== nf) continue;
            var orank = color === WHITE ? 7 - (osq >> 4) : (osq >> 4);
            if (orank > rank) { blocked = true; break; }
          }
          if (blocked) break;
        }
        if (!blocked) { mg += sgn * (PASSED_BONUS[rank] >> 1); eg += sgn * PASSED_BONUS[rank]; }
      }
      // Tuerme auf offenen Linien
      for (i = 0; i < rooks[color].length; i++) {
        f = rooks[color][i] & 7;
        if (own[f] === 0) { mg += sgn * (opp[f] === 0 ? 22 : 11); eg += sgn * (opp[f] === 0 ? 12 : 6); }
      }
    }

    // Koenigssicherheit: Bauernschild im Mittelspiel
    for (color = 0; color < 2; color++) {
      var ksq = pos.kings[color];
      if (ksq < 0) continue;
      var shield = 0;
      var dir = color === WHITE ? -16 : 16;
      for (var d = -1; d <= 1; d++) {
        var s1 = ksq + dir + d;
        if (!C.offBoard(s1) && b[s1] === ((color << 3) | PAWN)) shield += 12;
        var s2 = ksq + dir * 2 + d;
        if (!C.offBoard(s2) && b[s2] === ((color << 3) | PAWN)) shield += 5;
      }
      mg += (color === WHITE ? 1 : -1) * shield;
    }

    // Mobilitaet (leichte Gewichtung, beide Seiten getrennt)
    mg += 3 * (countMobility(pos, WHITE) - countMobility(pos, BLACK));

    // Tempo
    var tempo = pos.turn === WHITE ? 12 : -12;
    mg += tempo;

    // Tapered Eval: 24 = volles Mittelspiel.
    // Math.trunc statt Math.round, damit die Bewertung exakt spiegelsymmetrisch bleibt.
    if (phase > 24) phase = 24;
    var score = Math.trunc((mg * phase + eg * (24 - phase)) / 24);
    return pos.turn === WHITE ? score : -score;
  }

  function countMobility(pos, color) {
    var b = pos.board, count = 0;
    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var sq = r * 16 + f, p = b[sq];
        if (!p || (p >> 3) !== color) continue;
        var type = p & 7;
        if (type === PAWN || type === KING) continue;
        if (type === KNIGHT) {
          for (var i = 0; i < 8; i++) {
            var s = sq + C.KNIGHT_OFFSETS[i];
            if (!C.offBoard(s) && (!b[s] || (b[s] >> 3) !== color)) count++;
          }
          continue;
        }
        var dirs = type === BISHOP ? C.BISHOP_OFFSETS : type === ROOK ? C.ROOK_OFFSETS : C.KING_OFFSETS;
        var n = type === QUEEN ? 8 : 4;
        for (var di = 0; di < n; di++) {
          var dd = dirs[di], ss = sq + dd;
          while (!C.offBoard(ss)) {
            if (b[ss]) { if ((b[ss] >> 3) !== color) count++; break; }
            count++; ss += dd;
          }
        }
      }
    }
    return count;
  }

  /* ------------------- Static Exchange Evaluation --------------------- */
  function smallestAttackerSquare(b, sq, bySide) {
    var i, s, p, d;
    // Bauern
    var pd = bySide === WHITE ? [15, 17] : [-15, -17];
    for (i = 0; i < 2; i++) {
      s = sq + pd[i];
      if (C.offBoard(s)) continue;
      p = b[s];
      if (p && (p >> 3) === bySide && (p & 7) === PAWN) return s;
    }
    for (i = 0; i < 8; i++) {
      s = sq + C.KNIGHT_OFFSETS[i];
      if (C.offBoard(s)) continue;
      p = b[s];
      if (p && (p >> 3) === bySide && (p & 7) === KNIGHT) return s;
    }
    var bishopHit = -1, rookHit = -1, queenHit = -1;
    for (i = 0; i < 4; i++) {
      d = C.BISHOP_OFFSETS[i]; s = sq + d;
      while (!C.offBoard(s)) {
        p = b[s];
        if (p) {
          if ((p >> 3) === bySide) {
            if ((p & 7) === BISHOP && bishopHit < 0) bishopHit = s;
            else if ((p & 7) === QUEEN && queenHit < 0) queenHit = s;
          }
          break;
        }
        s += d;
      }
    }
    if (bishopHit >= 0) return bishopHit;
    for (i = 0; i < 4; i++) {
      d = C.ROOK_OFFSETS[i]; s = sq + d;
      while (!C.offBoard(s)) {
        p = b[s];
        if (p) {
          if ((p >> 3) === bySide) {
            if ((p & 7) === ROOK && rookHit < 0) rookHit = s;
            else if ((p & 7) === QUEEN && queenHit < 0) queenHit = s;
          }
          break;
        }
        s += d;
      }
    }
    if (rookHit >= 0) return rookHit;
    if (queenHit >= 0) return queenHit;
    for (i = 0; i < 8; i++) {
      s = sq + C.KING_OFFSETS[i];
      if (C.offBoard(s)) continue;
      p = b[s];
      if (p && (p >> 3) === bySide && (p & 7) === KING) return s;
    }
    return -1;
  }

  /** Materialgewinn/-verlust eines Schlagzugs nach vollstaendigem Abtausch (Zentibauern). */
  function see(pos, move) {
    var b = pos.board;
    var to = moveTo(move), from = moveFrom(move);
    var restore = [];
    function setSq(sq, val) { restore.push([sq, b[sq]]); b[sq] = val; }

    var gain = [];
    var capturedType = moveCaptured(move);
    gain[0] = capturedType ? VAL_SIMPLE[capturedType] : 0;
    var onTarget = VAL_SIMPLE[b[from] & 7];
    if (movePromo(move)) {
      gain[0] += VAL_SIMPLE[movePromo(move)] - VAL_SIMPLE[PAWN];
      onTarget = VAL_SIMPLE[movePromo(move)];
    }

    setSq(to, b[from]);
    setSq(from, 0);
    if (move & C.F_EP) setSq(pos.turn === WHITE ? to + 16 : to - 16, 0);

    var side = pos.turn ^ 1;
    var d = 0;
    while (true) {
      var aSq = smallestAttackerSquare(b, to, side);
      if (aSq < 0) break;
      d++;
      gain[d] = onTarget - gain[d - 1];
      if (Math.max(-gain[d - 1], gain[d]) < 0) break;
      onTarget = VAL_SIMPLE[b[aSq] & 7];
      setSq(to, b[aSq]);
      setSq(aSq, 0);
      side ^= 1;
    }
    while (d > 0) { gain[d - 1] = -Math.max(-gain[d - 1], gain[d]); d--; }

    for (var i = restore.length - 1; i >= 0; i--) b[restore[i][0]] = restore[i][1];
    return gain[0];
  }

  /* ------------------------ Transpositionstabelle --------------------- */
  var TT_SIZE = 1 << 19;               // 524288 Eintraege
  var TT_MASK = TT_SIZE - 1;
  var TT_FLAG_EXACT = 0, TT_FLAG_LOWER = 1, TT_FLAG_UPPER = 2;

  function TranspositionTable() {
    this.hi = new Int32Array(TT_SIZE);
    this.lo = new Int32Array(TT_SIZE);
    this.score = new Int32Array(TT_SIZE);
    this.move = new Int32Array(TT_SIZE);
    this.depth = new Int8Array(TT_SIZE);
    this.flag = new Int8Array(TT_SIZE);
    this.used = new Uint8Array(TT_SIZE);
  }
  TranspositionTable.prototype.clear = function () { this.used.fill(0); };
  TranspositionTable.prototype.probe = function (hi, lo) {
    var i = (lo >>> 0) & TT_MASK;
    if (!this.used[i] || this.hi[i] !== hi || this.lo[i] !== lo) return null;
    return { score: this.score[i], move: this.move[i], depth: this.depth[i], flag: this.flag[i] };
  };
  TranspositionTable.prototype.store = function (hi, lo, depth, flag, score, move) {
    var i = (lo >>> 0) & TT_MASK;
    if (this.used[i] && this.depth[i] > depth && this.hi[i] === hi && this.lo[i] === lo) return;
    this.hi[i] = hi; this.lo[i] = lo;
    this.depth[i] = depth; this.flag[i] = flag;
    this.score[i] = score; this.move[i] = move;
    this.used[i] = 1;
  };

  /* ------------------------------- Suche ------------------------------ */
  function Searcher() {
    this.tt = new TranspositionTable();
    this.killers = [];
    this.history = new Int32Array(128 * 128);
    this.nodes = 0;
    this.stopAt = 0;
    this.aborted = false;
    this.repetitionKeys = [];
  }

  Searcher.prototype.reset = function () {
    this.tt.clear();
    this.killers = [];
    this.history.fill(0);
  };

  Searcher.prototype.timeUp = function () {
    if (this.aborted) return true;
    if (this.stopAt && (this.nodes & 1023) === 0 && Date.now() >= this.stopAt) {
      this.aborted = true;
      return true;
    }
    return false;
  };

  Searcher.prototype.scoreMove = function (pos, m, ttMove, ply) {
    if (m === ttMove) return 2000000;
    var promo = movePromo(m);
    var cap = moveCaptured(m);
    if (cap) {
      var victim = VAL_SIMPLE[cap];
      var attacker = VAL_SIMPLE[pos.board[moveFrom(m)] & 7];
      var base = 1000000 + victim * 16 - attacker;
      if (promo) base += 5000;
      return base;
    }
    if (promo) return 900000 + VAL_SIMPLE[promo];
    var k = this.killers[ply];
    if (k) {
      if (k[0] === m) return 800000;
      if (k[1] === m) return 790000;
    }
    return this.history[(moveFrom(m) & 127) * 128 + (moveTo(m) & 127)];
  };

  Searcher.prototype.orderMoves = function (pos, moves, ttMove, ply) {
    var scored = new Array(moves.length);
    for (var i = 0; i < moves.length; i++) {
      scored[i] = { m: moves[i], s: this.scoreMove(pos, moves[i], ttMove, ply) };
    }
    scored.sort(function (a, b) { return b.s - a.s; });
    for (var j = 0; j < scored.length; j++) moves[j] = scored[j].m;
    return moves;
  };

  /**
   * repetitionKeys enthaelt Paare (lo, hi) fuer jede Stellung des Pfades,
   * inklusive der aktuellen. Der letzte Eintrag ist also die Stellung selbst
   * und muss uebersprungen werden — sonst faende jede Suche sofort eine
   * "Wiederholung" und gaebe 0 zurueck.
   */
  Searcher.prototype.isRepetition = function (pos) {
    var lo = pos.hashLo, hi = pos.hashHi;
    // Weiter zurueck als bis zum letzten irreversiblen Zug kann nichts wiederholt sein.
    var limit = Math.max(0, this.repetitionKeys.length - 2 - pos.half * 2);
    for (var i = this.repetitionKeys.length - 4; i >= limit; i -= 2) {
      if (this.repetitionKeys[i] === lo && this.repetitionKeys[i + 1] === hi) return true;
    }
    return false;
  };

  Searcher.prototype.quiescence = function (pos, alpha, beta, ply) {
    this.nodes++;
    if (this.timeUp()) return 0;

    var standPat = evaluate(pos);
    if (standPat >= beta) return beta;
    if (standPat > alpha) alpha = standPat;
    if (ply > 40) return standPat;

    var moves = pos.generateMoves(true);
    this.orderMoves(pos, moves, 0, ply);

    for (var i = 0; i < moves.length; i++) {
      var m = moves[i];
      // Delta-Pruning + SEE: klar verlierende Abtausche ueberspringen
      if (moveCaptured(m) && !movePromo(m)) {
        if (standPat + VAL_SIMPLE[moveCaptured(m)] + 200 < alpha) continue;
        if (see(pos, m) < 0) continue;
      }
      if (!pos.makeMove(m)) continue;
      var score = -this.quiescence(pos, -beta, -alpha, ply + 1);
      pos.undoMove();
      if (this.aborted) return 0;
      if (score >= beta) return beta;
      if (score > alpha) alpha = score;
    }
    return alpha;
  };

  Searcher.prototype.negamax = function (pos, depth, alpha, beta, ply, canNull) {
    this.nodes++;
    if (this.timeUp()) return 0;

    var inCheck = pos.inCheck();
    if (inCheck) depth++;                                   // Schacherweiterung

    if (depth <= 0) return this.quiescence(pos, alpha, beta, ply);

    if (ply > 0) {
      if (pos.half >= 100 || this.isRepetition(pos)) return 0;
      // Mate-Distance-Pruning
      var mateAlpha = Math.max(alpha, -MATE + ply);
      var mateBeta = Math.min(beta, MATE - ply - 1);
      if (mateAlpha >= mateBeta) return mateAlpha;
      alpha = mateAlpha; beta = mateBeta;
    }

    var alphaOrig = alpha;
    var ttMove = 0;
    var entry = this.tt.probe(pos.hashHi, pos.hashLo);
    if (entry) {
      ttMove = entry.move;
      if (ply > 0 && entry.depth >= depth) {
        if (entry.flag === TT_FLAG_EXACT) return entry.score;
        if (entry.flag === TT_FLAG_LOWER && entry.score > alpha) alpha = entry.score;
        else if (entry.flag === TT_FLAG_UPPER && entry.score < beta) beta = entry.score;
        if (alpha >= beta) return entry.score;
      }
    }

    var staticEval = inCheck ? -INF : evaluate(pos);

    // Null-Move-Pruning
    if (canNull && !inCheck && depth >= 3 && ply > 0 && hasNonPawnMaterial(pos, pos.turn) &&
      staticEval >= beta) {
      var R = depth > 6 ? 3 : 2;
      pos.makeNullMove();
      this.repetitionKeys.push(pos.hashLo, pos.hashHi);
      var nullScore = -this.negamax(pos, depth - R - 1, -beta, -beta + 1, ply + 1, false);
      this.repetitionKeys.length -= 2;
      pos.undoNullMove();
      if (this.aborted) return 0;
      if (nullScore >= beta && Math.abs(nullScore) < MATE - 100) return beta;
    }

    // Reverse Futility Pruning
    if (!inCheck && depth <= 3 && Math.abs(beta) < MATE - 100 &&
      staticEval - 130 * depth >= beta) return staticEval;

    var moves = pos.generateMoves(false);
    this.orderMoves(pos, moves, ttMove, ply);

    var best = -INF, bestMove = 0, legalCount = 0;

    for (var i = 0; i < moves.length; i++) {
      var m = moves[i];
      if (!pos.makeMove(m)) continue;
      legalCount++;
      this.repetitionKeys.push(pos.hashLo, pos.hashHi);

      var score;
      var quiet = !moveCaptured(m) && !movePromo(m);
      if (legalCount === 1) {
        score = -this.negamax(pos, depth - 1, -beta, -alpha, ply + 1, true);
      } else {
        // Late Move Reduction
        var reduction = 0;
        if (depth >= 3 && legalCount > 3 && quiet && !inCheck) {
          reduction = legalCount > 8 ? 2 : 1;
        }
        score = -this.negamax(pos, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1, true);
        if (score > alpha && reduction > 0) {
          score = -this.negamax(pos, depth - 1, -alpha - 1, -alpha, ply + 1, true);
        }
        if (score > alpha && score < beta) {
          score = -this.negamax(pos, depth - 1, -beta, -alpha, ply + 1, true);
        }
      }

      this.repetitionKeys.length -= 2;
      pos.undoMove();
      if (this.aborted) return 0;

      if (score > best) { best = score; bestMove = m; }
      if (score > alpha) {
        alpha = score;
        if (quiet) {
          this.history[(moveFrom(m) & 127) * 128 + (moveTo(m) & 127)] += depth * depth;
        }
      }
      if (alpha >= beta) {
        if (quiet) {
          if (!this.killers[ply]) this.killers[ply] = [0, 0];
          if (this.killers[ply][0] !== m) {
            this.killers[ply][1] = this.killers[ply][0];
            this.killers[ply][0] = m;
          }
        }
        break;
      }
    }

    if (legalCount === 0) return inCheck ? -MATE + ply : 0;

    var flag = best <= alphaOrig ? TT_FLAG_UPPER : best >= beta ? TT_FLAG_LOWER : TT_FLAG_EXACT;
    this.tt.store(pos.hashHi, pos.hashLo, depth, flag, best, bestMove);
    return best;
  };

  function hasNonPawnMaterial(pos, color) {
    var b = pos.board;
    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var p = b[r * 16 + f];
        if (!p || (p >> 3) !== color) continue;
        var t = p & 7;
        if (t !== PAWN && t !== KING) return true;
      }
    }
    return false;
  }

  /**
   * Hauptvariante zusammensetzen. Der erste Zug wird uebergeben, weil die
   * Wurzelstellung selbst nie in der Transpositionstabelle abgelegt wird.
   */
  Searcher.prototype.extractPv = function (pos, maxLen, firstMove) {
    var pv = [], made = 0;
    var next = firstMove || 0;
    for (var i = 0; i < (maxLen || 12); i++) {
      var mv = next;
      next = 0;
      if (!mv) {
        var e = this.tt.probe(pos.hashHi, pos.hashLo);
        if (!e || !e.move) break;
        mv = e.move;
      }
      var legal = pos.generateLegalMoves();
      if (legal.indexOf(mv) < 0) break;
      pv.push({ move: mv, san: pos.moveToSan(mv, legal), uci: pos.moveToUci(mv) });
      pos.makeMove(mv); made++;
    }
    while (made-- > 0) pos.undoMove();
    return pv;
  };

  /**
   * Sucht den besten Zug.
   * options: { maxDepth, movetime, onProgress, repetitionKeys }
   * Rueckgabe: { bestMove, score, depth, nodes, pv, rootMoves: [{move, san, uci, score}] }
   */
  Searcher.prototype.search = function (pos, options) {
    var opt = options || {};
    var maxDepth = opt.maxDepth || 64;
    var movetime = opt.movetime || 1000;

    this.nodes = 0;
    this.aborted = false;
    this.stopAt = movetime > 0 ? Date.now() + movetime : 0;
    this.killers = [];
    this.repetitionKeys = (opt.repetitionKeys || []).slice();

    var rootMoves = pos.generateLegalMoves();
    if (rootMoves.length === 0) {
      return { bestMove: 0, score: pos.inCheck() ? -MATE : 0, depth: 0, nodes: 0, pv: [], rootMoves: [] };
    }

    var sanCache = {};
    for (var s = 0; s < rootMoves.length; s++) {
      sanCache[rootMoves[s]] = pos.moveToSan(rootMoves[s], rootMoves);
    }

    var bestMove = rootMoves[0], bestScore = 0, completedDepth = 0;
    var lastScores = {};

    for (var depth = 1; depth <= maxDepth; depth++) {
      var alpha = -INF, beta = INF;
      var iterBest = 0, iterScore = -INF;
      var scoresThisIter = {};

      // TT-Zug zuerst
      this.orderMoves(pos, rootMoves, bestMove, 0);

      for (var i = 0; i < rootMoves.length; i++) {
        var m = rootMoves[i];
        if (!pos.makeMove(m)) continue;
        this.repetitionKeys.push(pos.hashLo, pos.hashHi);
        var score;
        if (i === 0) {
          score = -this.negamax(pos, depth - 1, -beta, -alpha, 1, true);
        } else {
          score = -this.negamax(pos, depth - 1, -alpha - 1, -alpha, 1, true);
          if (score > alpha) score = -this.negamax(pos, depth - 1, -beta, -alpha, 1, true);
        }
        this.repetitionKeys.length -= 2;
        pos.undoMove();

        if (this.aborted) break;
        scoresThisIter[m] = score;
        if (score > iterScore) { iterScore = score; iterBest = m; }
        if (score > alpha) alpha = score;
      }

      if (this.aborted) break;

      bestMove = iterBest || bestMove;
      bestScore = iterScore;
      completedDepth = depth;
      lastScores = scoresThisIter;

      if (opt.onProgress) {
        opt.onProgress({
          depth: depth, score: bestScore, nodes: this.nodes,
          bestMove: bestMove, san: sanCache[bestMove]
        });
      }

      // Matt gefunden -> abbrechen
      if (Math.abs(bestScore) >= MATE - 100) break;
      // Zeitbudget fast aufgebraucht -> naechste Iteration lohnt nicht
      if (this.stopAt && Date.now() + (Date.now() - (this.stopAt - movetime)) / 2 > this.stopAt) break;
    }

    var rootList = [];
    for (var r = 0; r < rootMoves.length; r++) {
      var mv = rootMoves[r];
      if (lastScores[mv] === undefined) continue;
      rootList.push({ move: mv, san: sanCache[mv], uci: pos.moveToUci(mv), score: lastScores[mv] });
    }
    rootList.sort(function (a, b) { return b.score - a.score; });

    return {
      bestMove: bestMove,
      bestSan: sanCache[bestMove],
      bestUci: pos.moveToUci(bestMove),
      score: bestScore,
      depth: completedDepth,
      nodes: this.nodes,
      pv: this.extractPv(pos, 10, bestMove),
      rootMoves: rootList
    };
  };

  /* ------------------------- Spielstaerke ----------------------------- */
  /**
   * Stufen 0-10. Niedrige Stufen suchen flacher und waehlen bewusst
   * nicht immer den besten Zug, damit Anfaenger eine Chance haben.
   */
  var LEVELS = [
    { name: 'Ganz neu', elo: '~250', depth: 1, movetime: 60, slack: 900 },
    { name: 'Anfaenger', elo: '~450', depth: 1, movetime: 100, slack: 650 },
    { name: 'Einsteiger', elo: '~700', depth: 2, movetime: 150, slack: 450 },
    { name: 'Hobby', elo: '~900', depth: 3, movetime: 250, slack: 300 },
    { name: 'Vereinsluft', elo: '~1100', depth: 4, movetime: 400, slack: 200 },
    { name: 'Solide', elo: '~1300', depth: 5, movetime: 600, slack: 130 },
    { name: 'Stark', elo: '~1500', depth: 6, movetime: 800, slack: 80 },
    { name: 'Sehr stark', elo: '~1700', depth: 8, movetime: 1200, slack: 40 },
    { name: 'Klubmeister', elo: '~1900', depth: 10, movetime: 1800, slack: 15 },
    { name: 'Experte', elo: '~2100', depth: 14, movetime: 2600, slack: 0 },
    { name: 'Maximum', elo: '~2300', depth: 30, movetime: 4000, slack: 0 }
  ];

  function pickWithSkill(result, level, rng) {
    var lvl = LEVELS[Math.max(0, Math.min(LEVELS.length - 1, level))];
    var moves = result.rootMoves;
    if (!moves || moves.length <= 1 || lvl.slack <= 0) return result.bestMove;

    var best = moves[0].score;
    // Bei klarem Matt oder grossem Vorteil nicht absichtlich verpatzen
    if (Math.abs(best) >= MATE - 100) return result.bestMove;

    var pool = moves.filter(function (m) { return best - m.score <= lvl.slack; });
    if (pool.length <= 1) return result.bestMove;

    // Gewichtung: bessere Zuege bleiben wahrscheinlicher
    var weights = pool.map(function (m) {
      var drop = best - m.score;
      return Math.pow(1 - drop / (lvl.slack + 1), 2) + 0.08;
    });
    var total = weights.reduce(function (a, b) { return a + b; }, 0);
    var pick = (rng ? rng() : Math.random()) * total;
    for (var i = 0; i < pool.length; i++) {
      pick -= weights[i];
      if (pick <= 0) return pool[i].move;
    }
    return pool[pool.length - 1].move;
  }

  /* ------------------------------ Export ------------------------------ */
  var api = {
    MATE: MATE,
    VAL_SIMPLE: VAL_SIMPLE,
    LEVELS: LEVELS,
    evaluate: evaluate,
    see: see,
    smallestAttackerSquare: smallestAttackerSquare,
    Searcher: Searcher,
    pickWithSkill: pickWithSkill,
    hasNonPawnMaterial: hasNonPawnMaterial
  };
  global.ChessEngine = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}(typeof self !== 'undefined' ? self : this));
