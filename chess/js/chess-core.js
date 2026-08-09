/*
 * chess-core.js — vollstaendige Schachregeln auf 0x88-Basis.
 * Laeuft im Hauptthread (<script>) und im Worker (importScripts).
 *
 * Feldindizes: a8 = 0, h8 = 7, a1 = 112, h1 = 119.
 * Weiss zieht in Richtung kleinerer Indizes (-16).
 */
(function (global) {
  'use strict';

  var WHITE = 0, BLACK = 1;
  var PAWN = 1, KNIGHT = 2, BISHOP = 3, ROOK = 4, QUEEN = 5, KING = 6;

  var CASTLE_WK = 1, CASTLE_WQ = 2, CASTLE_BK = 4, CASTLE_BQ = 8;

  var KNIGHT_OFFSETS = [-33, -31, -18, -14, 14, 18, 31, 33];
  var BISHOP_OFFSETS = [-17, -15, 15, 17];
  var ROOK_OFFSETS = [-16, -1, 1, 16];
  var KING_OFFSETS = [-17, -16, -15, -1, 1, 15, 16, 17];

  var PIECE_LETTER = ['', 'p', 'n', 'b', 'r', 'q', 'k'];
  var LETTER_PIECE = { p: PAWN, n: KNIGHT, b: BISHOP, r: ROOK, q: QUEEN, k: KING };

  /* ------------------------------------------------------------------ *
   * Zug-Kodierung (32 Bit)
   *   0-7    from
   *   8-15   to
   *   16-18  Umwandlungsfigur (0 = keine)
   *   19-22  geschlagene Figur (Typ, 0 = keine)
   *   23     en passant
   *   24     kurze Rochade
   *   25     lange Rochade
   *   26     Doppelschritt
   * ------------------------------------------------------------------ */
  var F_EP = 1 << 23, F_CASTLE_K = 1 << 24, F_CASTLE_Q = 1 << 25, F_DOUBLE = 1 << 26;

  function encodeMove(from, to, promo, captured, flags) {
    return (from & 0xff) | ((to & 0xff) << 8) | ((promo & 7) << 16) |
      ((captured & 7) << 19) | flags;
  }
  function moveFrom(m) { return m & 0xff; }
  function moveTo(m) { return (m >> 8) & 0xff; }
  function movePromo(m) { return (m >> 16) & 7; }
  function moveCaptured(m) { return (m >> 19) & 7; }
  function isCapture(m) { return ((m >> 19) & 7) !== 0; }

  /* ------------------------------------------------------------------ *
   * Feld-Hilfen
   * ------------------------------------------------------------------ */
  function fileOf(sq) { return sq & 7; }
  function rankOf(sq) { return 7 - (sq >> 4); }      // 0 = 1. Reihe
  function rowOf(sq) { return sq >> 4; }              // 0 = 8. Reihe
  function offBoard(sq) { return (sq & 0x88) !== 0; }
  function squareName(sq) { return 'abcdefgh'[sq & 7] + (8 - (sq >> 4)); }
  function squareFromName(name) {
    if (!name || name.length < 2) return -1;
    var f = 'abcdefgh'.indexOf(name[0]);
    var r = parseInt(name[1], 10);
    if (f < 0 || !(r >= 1 && r <= 8)) return -1;
    return (8 - r) * 16 + f;
  }
  function isLightSquare(sq) { return ((sq >> 4) + (sq & 7)) % 2 === 0; }

  /* ------------------------------------------------------------------ *
   * Zobrist-Hashes (deterministischer PRNG, damit Partien reproduzierbar sind)
   * ------------------------------------------------------------------ */
  function makeRng(seed) {
    var s = seed >>> 0;
    return function () {
      s ^= s << 13; s >>>= 0;
      s ^= s >>> 17;
      s ^= s << 5; s >>>= 0;
      return s >>> 0;
    };
  }
  var ZOB_PIECE_HI = new Int32Array(16 * 128);
  var ZOB_PIECE_LO = new Int32Array(16 * 128);
  var ZOB_CASTLE_HI = new Int32Array(16);
  var ZOB_CASTLE_LO = new Int32Array(16);
  var ZOB_EP_HI = new Int32Array(8);
  var ZOB_EP_LO = new Int32Array(8);
  var ZOB_SIDE_HI, ZOB_SIDE_LO;
  (function () {
    var rnd = makeRng(0x1a2b3c4d);
    for (var i = 0; i < ZOB_PIECE_HI.length; i++) { ZOB_PIECE_HI[i] = rnd() | 0; ZOB_PIECE_LO[i] = rnd() | 0; }
    for (var c = 0; c < 16; c++) { ZOB_CASTLE_HI[c] = rnd() | 0; ZOB_CASTLE_LO[c] = rnd() | 0; }
    for (var e = 0; e < 8; e++) { ZOB_EP_HI[e] = rnd() | 0; ZOB_EP_LO[e] = rnd() | 0; }
    ZOB_SIDE_HI = rnd() | 0; ZOB_SIDE_LO = rnd() | 0;
  }());

  /* ------------------------------------------------------------------ *
   * Position
   * ------------------------------------------------------------------ */
  function Position(fen) {
    this.board = new Int8Array(128);
    this.turn = WHITE;
    this.castling = 0;
    this.ep = -1;
    this.half = 0;
    this.full = 1;
    this.kings = [-1, -1];
    this.hashHi = 0;
    this.hashLo = 0;
    this.undoStack = [];
    this.setFen(fen || Position.START_FEN);
  }

  Position.START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

  Position.prototype.clone = function () {
    var p = Object.create(Position.prototype);
    p.board = this.board.slice();
    p.turn = this.turn;
    p.castling = this.castling;
    p.ep = this.ep;
    p.half = this.half;
    p.full = this.full;
    p.kings = [this.kings[0], this.kings[1]];
    p.hashHi = this.hashHi;
    p.hashLo = this.hashLo;
    p.undoStack = [];
    return p;
  };

  Position.prototype.setFen = function (fen) {
    var parts = String(fen).trim().split(/\s+/);
    if (parts.length < 4) throw new Error('Ungueltige FEN: ' + fen);
    this.board.fill(0);
    this.kings = [-1, -1];

    var rows = parts[0].split('/');
    if (rows.length !== 8) throw new Error('Ungueltige FEN (Reihen): ' + fen);
    for (var r = 0; r < 8; r++) {
      var file = 0;
      var row = rows[r];
      for (var i = 0; i < row.length; i++) {
        var ch = row[i];
        if (ch >= '1' && ch <= '8') { file += parseInt(ch, 10); continue; }
        var type = LETTER_PIECE[ch.toLowerCase()];
        if (!type) throw new Error('Unbekannte Figur in FEN: ' + ch);
        var color = ch === ch.toUpperCase() ? WHITE : BLACK;
        var sq = r * 16 + file;
        this.board[sq] = (color << 3) | type;
        if (type === KING) this.kings[color] = sq;
        file++;
      }
    }

    this.turn = parts[1] === 'b' ? BLACK : WHITE;
    this.castling = 0;
    if (parts[2].indexOf('K') >= 0) this.castling |= CASTLE_WK;
    if (parts[2].indexOf('Q') >= 0) this.castling |= CASTLE_WQ;
    if (parts[2].indexOf('k') >= 0) this.castling |= CASTLE_BK;
    if (parts[2].indexOf('q') >= 0) this.castling |= CASTLE_BQ;
    this.ep = parts[3] === '-' ? -1 : squareFromName(parts[3]);
    this.half = parts.length > 4 ? parseInt(parts[4], 10) || 0 : 0;
    this.full = parts.length > 5 ? parseInt(parts[5], 10) || 1 : 1;
    this.undoStack = [];
    this.recomputeHash();
    return this;
  };

  Position.prototype.getFen = function () {
    var out = '';
    for (var r = 0; r < 8; r++) {
      var empty = 0;
      for (var f = 0; f < 8; f++) {
        var p = this.board[r * 16 + f];
        if (!p) { empty++; continue; }
        if (empty) { out += empty; empty = 0; }
        var letter = PIECE_LETTER[p & 7];
        out += (p >> 3) === WHITE ? letter.toUpperCase() : letter;
      }
      if (empty) out += empty;
      if (r < 7) out += '/';
    }
    var cast = '';
    if (this.castling & CASTLE_WK) cast += 'K';
    if (this.castling & CASTLE_WQ) cast += 'Q';
    if (this.castling & CASTLE_BK) cast += 'k';
    if (this.castling & CASTLE_BQ) cast += 'q';
    return out + ' ' + (this.turn === WHITE ? 'w' : 'b') + ' ' + (cast || '-') +
      ' ' + (this.ep >= 0 ? squareName(this.ep) : '-') + ' ' + this.half + ' ' + this.full;
  };

  Position.prototype.recomputeHash = function () {
    var hi = 0, lo = 0;
    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var sq = r * 16 + f;
        var p = this.board[sq];
        if (!p) continue;
        var idx = p * 128 + sq;
        hi ^= ZOB_PIECE_HI[idx]; lo ^= ZOB_PIECE_LO[idx];
      }
    }
    hi ^= ZOB_CASTLE_HI[this.castling]; lo ^= ZOB_CASTLE_LO[this.castling];
    if (this.ep >= 0) { hi ^= ZOB_EP_HI[this.ep & 7]; lo ^= ZOB_EP_LO[this.ep & 7]; }
    if (this.turn === BLACK) { hi ^= ZOB_SIDE_HI; lo ^= ZOB_SIDE_LO; }
    this.hashHi = hi | 0; this.hashLo = lo | 0;
  };

  Position.prototype.key = function () {
    return ((this.hashHi >>> 0) * 4294967296) + (this.hashLo >>> 0);
  };

  /* --------------------------- Angriffe ----------------------------- */
  Position.prototype.isSquareAttacked = function (sq, byColor) {
    var b = this.board, s, p, d, i;

    // Bauern: ein weisser Bauer auf sq+15 / sq+17 greift sq an.
    var p1 = byColor === WHITE ? sq + 15 : sq - 15;
    var p2 = byColor === WHITE ? sq + 17 : sq - 17;
    if (!offBoard(p1)) { p = b[p1]; if (p && (p >> 3) === byColor && (p & 7) === PAWN) return true; }
    if (!offBoard(p2)) { p = b[p2]; if (p && (p >> 3) === byColor && (p & 7) === PAWN) return true; }

    for (i = 0; i < 8; i++) {
      s = sq + KNIGHT_OFFSETS[i];
      if (offBoard(s)) continue;
      p = b[s];
      if (p && (p >> 3) === byColor && (p & 7) === KNIGHT) return true;
    }
    for (i = 0; i < 8; i++) {
      s = sq + KING_OFFSETS[i];
      if (offBoard(s)) continue;
      p = b[s];
      if (p && (p >> 3) === byColor && (p & 7) === KING) return true;
    }
    for (i = 0; i < 4; i++) {
      d = BISHOP_OFFSETS[i]; s = sq + d;
      while (!offBoard(s)) {
        p = b[s];
        if (p) {
          if ((p >> 3) === byColor) { var t = p & 7; if (t === BISHOP || t === QUEEN) return true; }
          break;
        }
        s += d;
      }
    }
    for (i = 0; i < 4; i++) {
      d = ROOK_OFFSETS[i]; s = sq + d;
      while (!offBoard(s)) {
        p = b[s];
        if (p) {
          if ((p >> 3) === byColor) { var t2 = p & 7; if (t2 === ROOK || t2 === QUEEN) return true; }
          break;
        }
        s += d;
      }
    }
    return false;
  };

  Position.prototype.inCheck = function (color) {
    if (color === undefined) color = this.turn;
    var k = this.kings[color];
    if (k < 0) return false;
    return this.isSquareAttacked(k, color ^ 1);
  };

  /* ------------------------ Zuggenerierung -------------------------- */
  Position.prototype.generateMoves = function (capturesOnly) {
    var moves = [];
    var b = this.board, us = this.turn, them = us ^ 1;
    var pushDir = us === WHITE ? -16 : 16;
    var startRow = us === WHITE ? 6 : 1;
    var promoRow = us === WHITE ? 0 : 7;

    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var from = r * 16 + f;
        var piece = b[from];
        if (!piece || (piece >> 3) !== us) continue;
        var type = piece & 7;

        if (type === PAWN) {
          var one = from + pushDir;
          if (!offBoard(one) && !b[one]) {
            if (!capturesOnly) {
              if ((one >> 4) === promoRow) {
                moves.push(encodeMove(from, one, QUEEN, 0, 0));
                moves.push(encodeMove(from, one, ROOK, 0, 0));
                moves.push(encodeMove(from, one, BISHOP, 0, 0));
                moves.push(encodeMove(from, one, KNIGHT, 0, 0));
              } else {
                moves.push(encodeMove(from, one, 0, 0, 0));
                var two = one + pushDir;
                if (r === startRow && !b[two]) moves.push(encodeMove(from, two, 0, 0, F_DOUBLE));
              }
            } else if ((one >> 4) === promoRow) {
              moves.push(encodeMove(from, one, QUEEN, 0, 0));
            }
          }
          var caps = [from + pushDir - 1, from + pushDir + 1];
          for (var ci = 0; ci < 2; ci++) {
            var to = caps[ci];
            if (offBoard(to)) continue;
            // Ueberlauf ueber den Rand vermeiden
            if (Math.abs((to & 7) - f) !== 1) continue;
            var target = b[to];
            if (target && (target >> 3) === them) {
              if ((to >> 4) === promoRow) {
                moves.push(encodeMove(from, to, QUEEN, target & 7, 0));
                moves.push(encodeMove(from, to, ROOK, target & 7, 0));
                moves.push(encodeMove(from, to, BISHOP, target & 7, 0));
                moves.push(encodeMove(from, to, KNIGHT, target & 7, 0));
              } else {
                moves.push(encodeMove(from, to, 0, target & 7, 0));
              }
            } else if (!target && to === this.ep) {
              moves.push(encodeMove(from, to, 0, PAWN, F_EP));
            }
          }
          continue;
        }

        if (type === KNIGHT || type === KING) {
          var offs = type === KNIGHT ? KNIGHT_OFFSETS : KING_OFFSETS;
          for (var i = 0; i < 8; i++) {
            var s = from + offs[i];
            if (offBoard(s)) continue;
            var t = b[s];
            if (t) {
              if ((t >> 3) === them) moves.push(encodeMove(from, s, 0, t & 7, 0));
            } else if (!capturesOnly) {
              moves.push(encodeMove(from, s, 0, 0, 0));
            }
          }
          continue;
        }

        var dirs = type === BISHOP ? BISHOP_OFFSETS : type === ROOK ? ROOK_OFFSETS : KING_OFFSETS;
        var count = type === QUEEN ? 8 : 4;
        for (var di = 0; di < count; di++) {
          var dd = dirs[di], ss = from + dd;
          while (!offBoard(ss)) {
            var tt = b[ss];
            if (tt) {
              if ((tt >> 3) === them) moves.push(encodeMove(from, ss, 0, tt & 7, 0));
              break;
            }
            if (!capturesOnly) moves.push(encodeMove(from, ss, 0, 0, 0));
            ss += dd;
          }
        }
      }
    }

    if (!capturesOnly) this._addCastling(moves);
    return moves;
  };

  Position.prototype._addCastling = function (moves) {
    var us = this.turn, them = us ^ 1, b = this.board;
    var kSq = us === WHITE ? 116 : 4;
    if (this.kings[us] !== kSq) return;
    if (this.isSquareAttacked(kSq, them)) return;

    var kRight = us === WHITE ? CASTLE_WK : CASTLE_BK;
    var qRight = us === WHITE ? CASTLE_WQ : CASTLE_BQ;

    if (this.castling & kRight) {
      if (!b[kSq + 1] && !b[kSq + 2] &&
        !this.isSquareAttacked(kSq + 1, them) && !this.isSquareAttacked(kSq + 2, them)) {
        moves.push(encodeMove(kSq, kSq + 2, 0, 0, F_CASTLE_K));
      }
    }
    if (this.castling & qRight) {
      if (!b[kSq - 1] && !b[kSq - 2] && !b[kSq - 3] &&
        !this.isSquareAttacked(kSq - 1, them) && !this.isSquareAttacked(kSq - 2, them)) {
        moves.push(encodeMove(kSq, kSq - 2, 0, 0, F_CASTLE_Q));
      }
    }
  };

  Position.prototype.generateLegalMoves = function () {
    var pseudo = this.generateMoves(false);
    var legal = [];
    for (var i = 0; i < pseudo.length; i++) {
      if (this.makeMove(pseudo[i])) { this.undoMove(); legal.push(pseudo[i]); }
    }
    return legal;
  };

  /* --------------------------- Zug ausfuehren ----------------------- */
  var CASTLE_MASK = new Int8Array(128);
  (function () {
    CASTLE_MASK.fill(15);
    CASTLE_MASK[116] = 15 & ~(CASTLE_WK | CASTLE_WQ); // e1
    CASTLE_MASK[119] = 15 & ~CASTLE_WK;               // h1
    CASTLE_MASK[112] = 15 & ~CASTLE_WQ;               // a1
    CASTLE_MASK[4] = 15 & ~(CASTLE_BK | CASTLE_BQ);   // e8
    CASTLE_MASK[7] = 15 & ~CASTLE_BK;                 // h8
    CASTLE_MASK[0] = 15 & ~CASTLE_BQ;                 // a8
  }());

  Position.prototype._xorPiece = function (piece, sq) {
    var idx = piece * 128 + sq;
    this.hashHi ^= ZOB_PIECE_HI[idx];
    this.hashLo ^= ZOB_PIECE_LO[idx];
  };

  /** Fuehrt den Zug aus. Gibt false zurueck (und nimmt zurueck), wenn er den eigenen Koenig im Schach laesst. */
  Position.prototype.makeMove = function (m) {
    var b = this.board;
    var from = m & 0xff, to = (m >> 8) & 0xff;
    var promo = (m >> 16) & 7;
    var us = this.turn, them = us ^ 1;
    var piece = b[from];
    var type = piece & 7;

    this.undoStack.push({
      move: m, castling: this.castling, ep: this.ep, half: this.half,
      full: this.full, hashHi: this.hashHi, hashLo: this.hashLo,
      kingW: this.kings[0], kingB: this.kings[1]
    });

    // altes en-passant / Rochaderechte aus dem Hash nehmen
    if (this.ep >= 0) { this.hashHi ^= ZOB_EP_HI[this.ep & 7]; this.hashLo ^= ZOB_EP_LO[this.ep & 7]; }
    this.hashHi ^= ZOB_CASTLE_HI[this.castling]; this.hashLo ^= ZOB_CASTLE_LO[this.castling];

    // Schlagen
    if (m & F_EP) {
      var capSq = us === WHITE ? to + 16 : to - 16;
      this._xorPiece(b[capSq], capSq);
      b[capSq] = 0;
    } else if (b[to]) {
      this._xorPiece(b[to], to);
    }

    // Figur bewegen
    this._xorPiece(piece, from);
    b[from] = 0;
    var placed = promo ? ((us << 3) | promo) : piece;
    b[to] = placed;
    this._xorPiece(placed, to);

    if (type === KING) this.kings[us] = to;

    // Turm bei Rochade
    if (m & F_CASTLE_K) {
      var rf = to + 1, rt = to - 1;
      var rook = b[rf];
      this._xorPiece(rook, rf); b[rf] = 0;
      b[rt] = rook; this._xorPiece(rook, rt);
    } else if (m & F_CASTLE_Q) {
      var rf2 = to - 2, rt2 = to + 1;
      var rook2 = b[rf2];
      this._xorPiece(rook2, rf2); b[rf2] = 0;
      b[rt2] = rook2; this._xorPiece(rook2, rt2);
    }

    // Zustand fortschreiben
    this.castling &= CASTLE_MASK[from] & CASTLE_MASK[to];
    this.ep = (m & F_DOUBLE) ? (from + (us === WHITE ? -16 : 16)) : -1;
    this.half = (type === PAWN || moveCaptured(m)) ? 0 : this.half + 1;
    if (us === BLACK) this.full++;
    this.turn = them;

    this.hashHi ^= ZOB_CASTLE_HI[this.castling]; this.hashLo ^= ZOB_CASTLE_LO[this.castling];
    if (this.ep >= 0) { this.hashHi ^= ZOB_EP_HI[this.ep & 7]; this.hashLo ^= ZOB_EP_LO[this.ep & 7]; }
    this.hashHi ^= ZOB_SIDE_HI; this.hashLo ^= ZOB_SIDE_LO;

    if (this.isSquareAttacked(this.kings[us], them)) {
      this.undoMove();
      return false;
    }
    return true;
  };

  Position.prototype.undoMove = function () {
    var u = this.undoStack.pop();
    if (!u) return false;
    var m = u.move, b = this.board;
    var from = m & 0xff, to = (m >> 8) & 0xff;
    var promo = (m >> 16) & 7;
    var captured = (m >> 19) & 7;

    this.turn ^= 1;
    var us = this.turn, them = us ^ 1;

    var moved = b[to];
    b[from] = promo ? ((us << 3) | PAWN) : moved;
    b[to] = 0;

    if (m & F_EP) {
      var capSq = us === WHITE ? to + 16 : to - 16;
      b[capSq] = (them << 3) | PAWN;
    } else if (captured) {
      b[to] = (them << 3) | captured;
    }

    if (m & F_CASTLE_K) {
      var rook = b[to - 1]; b[to - 1] = 0; b[to + 1] = rook;
    } else if (m & F_CASTLE_Q) {
      var rook2 = b[to + 1]; b[to + 1] = 0; b[to - 2] = rook2;
    }

    this.castling = u.castling;
    this.ep = u.ep;
    this.half = u.half;
    this.full = u.full;
    this.hashHi = u.hashHi;
    this.hashLo = u.hashLo;
    this.kings[0] = u.kingW;
    this.kings[1] = u.kingB;
    return true;
  };

  /** Null-Zug fuer Null-Move-Pruning. */
  Position.prototype.makeNullMove = function () {
    this.undoStack.push({
      move: 0, castling: this.castling, ep: this.ep, half: this.half,
      full: this.full, hashHi: this.hashHi, hashLo: this.hashLo,
      kingW: this.kings[0], kingB: this.kings[1], nullMove: true
    });
    if (this.ep >= 0) { this.hashHi ^= ZOB_EP_HI[this.ep & 7]; this.hashLo ^= ZOB_EP_LO[this.ep & 7]; }
    this.ep = -1;
    this.turn ^= 1;
    this.hashHi ^= ZOB_SIDE_HI; this.hashLo ^= ZOB_SIDE_LO;
  };

  Position.prototype.undoNullMove = function () {
    var u = this.undoStack.pop();
    this.turn ^= 1;
    this.castling = u.castling; this.ep = u.ep; this.half = u.half; this.full = u.full;
    this.hashHi = u.hashHi; this.hashLo = u.hashLo;
    this.kings[0] = u.kingW; this.kings[1] = u.kingB;
  };

  /* ----------------------------- SAN / UCI -------------------------- */
  Position.prototype.moveToUci = function (m) {
    var s = squareName(m & 0xff) + squareName((m >> 8) & 0xff);
    var promo = (m >> 16) & 7;
    return promo ? s + PIECE_LETTER[promo] : s;
  };

  Position.prototype.moveFromUci = function (uci) {
    if (!uci || uci.length < 4) return 0;
    var from = squareFromName(uci.slice(0, 2));
    var to = squareFromName(uci.slice(2, 4));
    var promo = uci.length > 4 ? (LETTER_PIECE[uci[4].toLowerCase()] || 0) : 0;
    var legal = this.generateLegalMoves();
    for (var i = 0; i < legal.length; i++) {
      var m = legal[i];
      if ((m & 0xff) === from && ((m >> 8) & 0xff) === to && (promo === 0 || ((m >> 16) & 7) === promo)) return m;
    }
    return 0;
  };

  Position.prototype.moveToSan = function (m, legalMoves) {
    var from = m & 0xff, to = (m >> 8) & 0xff;
    var piece = this.board[from];
    var type = piece & 7;
    var san;

    if (m & F_CASTLE_K) san = 'O-O';
    else if (m & F_CASTLE_Q) san = 'O-O-O';
    else if (type === PAWN) {
      san = moveCaptured(m) ? 'abcdefgh'[from & 7] + 'x' + squareName(to) : squareName(to);
      if ((m >> 16) & 7) san += '=' + PIECE_LETTER[(m >> 16) & 7].toUpperCase();
    } else {
      var legal = legalMoves || this.generateLegalMoves();
      var sameFile = false, sameRank = false, ambiguous = false;
      for (var i = 0; i < legal.length; i++) {
        var o = legal[i];
        if (o === m) continue;
        if (((o >> 8) & 0xff) !== to) continue;
        var op = this.board[o & 0xff];
        if ((op & 7) !== type || (op >> 3) !== (piece >> 3)) continue;
        ambiguous = true;
        if (((o & 0xff) & 7) === (from & 7)) sameFile = true;
        if (((o & 0xff) >> 4) === (from >> 4)) sameRank = true;
      }
      san = PIECE_LETTER[type].toUpperCase();
      if (ambiguous) {
        if (!sameFile) san += 'abcdefgh'[from & 7];
        else if (!sameRank) san += String(8 - (from >> 4));
        else san += squareName(from);
      }
      if (moveCaptured(m)) san += 'x';
      san += squareName(to);
    }

    // Schach / Matt anhaengen
    if (this.makeMove(m)) {
      if (this.inCheck()) san += this.generateLegalMoves().length === 0 ? '#' : '+';
      this.undoMove();
    }
    return san;
  };

  Position.prototype.moveFromSan = function (san) {
    var clean = String(san).replace(/[+#?!]+$/g, '').replace(/[!?]/g, '').trim();
    if (!clean) return 0;
    var legal = this.generateLegalMoves();
    for (var i = 0; i < legal.length; i++) {
      var candidate = this.moveToSan(legal[i], legal).replace(/[+#]/g, '');
      if (candidate === clean) return legal[i];
    }
    // Toleranz fuer 0-0 / 0-0-0 und andere Schreibweisen
    var alt = clean.replace(/0/g, 'O');
    for (var j = 0; j < legal.length; j++) {
      if (this.moveToSan(legal[j], legal).replace(/[+#]/g, '') === alt) return legal[j];
    }
    return 0;
  };

  /* ------------------------- Materialabfragen ----------------------- */
  Position.prototype.pieceList = function (color) {
    var list = [];
    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var sq = r * 16 + f, p = this.board[sq];
        if (p && (color === undefined || (p >> 3) === color)) {
          list.push({ square: sq, type: p & 7, color: p >> 3 });
        }
      }
    }
    return list;
  };

  Position.prototype.hasInsufficientMaterial = function () {
    var pieces = this.pieceList();
    var bishops = [], knights = 0, others = 0;
    for (var i = 0; i < pieces.length; i++) {
      var t = pieces[i].type;
      if (t === KING) continue;
      if (t === BISHOP) bishops.push(pieces[i]);
      else if (t === KNIGHT) knights++;
      else others++;
    }
    if (others > 0) return false;
    if (bishops.length === 0 && knights === 0) return true;               // K vs K
    if (bishops.length === 0 && knights === 1) return true;               // K+N vs K
    if (bishops.length === 1 && knights === 0) return true;               // K+B vs K
    if (knights === 0 && bishops.length > 1) {                            // nur gleichfarbige Laeufer
      var light = isLightSquare(bishops[0].square);
      for (var b = 1; b < bishops.length; b++) {
        if (isLightSquare(bishops[b].square) !== light) return false;
      }
      return true;
    }
    return false;
  };

  /* ------------------------------------------------------------------ *
   * Game — Position + Zughistorie + Regeln fuer Partieende
   * ------------------------------------------------------------------ */
  function Game(fen) {
    this.reset(fen);
  }

  Game.prototype.reset = function (fen) {
    this.startFen = fen || Position.START_FEN;
    this.position = new Position(this.startFen);
    this.history = [];                 // { move, san, fenBefore, fenAfter, uci }
    this.keyCounts = Object.create(null);
    // Zobrist-Paare (lo, hi) aller Stellungen des Partieverlaufs — die Suche
    // braucht sie, um Zugwiederholungen korrekt zu erkennen.
    this.keyHistory = [this.position.hashLo, this.position.hashHi];
    this._countKey();
    return this;
  };

  /** Schluesselverlauf inkl. aktueller Stellung (fuer Searcher.repetitionKeys). */
  Game.prototype.repetitionKeys = function () { return this.keyHistory.slice(); };

  Game.prototype._countKey = function () {
    var k = this.position.getFen().split(' ').slice(0, 4).join(' ');
    this.keyCounts[k] = (this.keyCounts[k] || 0) + 1;
    return this.keyCounts[k];
  };

  Game.prototype._uncountKey = function () {
    var k = this.position.getFen().split(' ').slice(0, 4).join(' ');
    if (this.keyCounts[k]) this.keyCounts[k]--;
  };

  Game.prototype.legalMoves = function () { return this.position.generateLegalMoves(); };

  Game.prototype.turn = function () { return this.position.turn; };
  Game.prototype.fen = function () { return this.position.getFen(); };

  /** Fuehrt einen Zug aus (int, UCI-String oder SAN-String). Gibt den Eintrag oder null zurueck. */
  Game.prototype.move = function (input) {
    var m = 0;
    if (typeof input === 'number') m = input;
    else if (typeof input === 'string') {
      m = /^[a-h][1-8][a-h][1-8][qrbn]?$/i.test(input.trim())
        ? this.position.moveFromUci(input.trim())
        : this.position.moveFromSan(input);
    } else if (input && input.from !== undefined) {
      var uci = squareName(input.from) + squareName(input.to) + (input.promotion || '');
      m = this.position.moveFromUci(uci);
    }
    if (!m) return null;

    var fenBefore = this.position.getFen();
    var legal = this.position.generateLegalMoves();
    if (legal.indexOf(m) < 0) return null;
    var san = this.position.moveToSan(m, legal);
    var uciStr = this.position.moveToUci(m);
    if (!this.position.makeMove(m)) return null;

    var entry = {
      move: m, san: san, uci: uciStr,
      from: moveFrom(m), to: moveTo(m),
      promotion: movePromo(m) ? PIECE_LETTER[movePromo(m)] : '',
      captured: moveCaptured(m) ? PIECE_LETTER[moveCaptured(m)] : '',
      color: this.position.turn ^ 1,
      fenBefore: fenBefore,
      fenAfter: this.position.getFen(),
      castle: !!(m & (F_CASTLE_K | F_CASTLE_Q)),
      enPassant: !!(m & F_EP),
      check: this.position.inCheck()
    };
    this.history.push(entry);
    this.keyHistory.push(this.position.hashLo, this.position.hashHi);
    this._countKey();
    return entry;
  };

  Game.prototype.undo = function () {
    if (!this.history.length) return null;
    this._uncountKey();
    var entry = this.history.pop();
    this.position.undoMove();
    this.keyHistory.length -= 2;
    return entry;
  };

  Game.prototype.repetitionCount = function () {
    var k = this.position.getFen().split(' ').slice(0, 4).join(' ');
    return this.keyCounts[k] || 0;
  };

  /** { over, result: '1-0'|'0-1'|'1/2-1/2', reason: string } */
  Game.prototype.status = function () {
    var legal = this.position.generateLegalMoves();
    var check = this.position.inCheck();
    if (legal.length === 0) {
      if (check) {
        var winner = this.position.turn === WHITE ? BLACK : WHITE;
        return {
          over: true, result: winner === WHITE ? '1-0' : '0-1',
          reason: 'schachmatt', winner: winner,
          text: 'Schachmatt — ' + (winner === WHITE ? 'Weiss' : 'Schwarz') + ' gewinnt'
        };
      }
      return { over: true, result: '1/2-1/2', reason: 'patt', winner: null, text: 'Patt — Remis' };
    }
    if (this.position.half >= 100) {
      return { over: true, result: '1/2-1/2', reason: '50-zuege', winner: null, text: '50-Zuege-Regel — Remis' };
    }
    if (this.repetitionCount() >= 3) {
      return { over: true, result: '1/2-1/2', reason: 'stellungswiederholung', winner: null, text: 'Dreifache Stellungswiederholung — Remis' };
    }
    if (this.position.hasInsufficientMaterial()) {
      return { over: true, result: '1/2-1/2', reason: 'material', winner: null, text: 'Ungenuegendes Material — Remis' };
    }
    return { over: false, result: null, reason: check ? 'schach' : null, winner: null, text: check ? 'Schach!' : '' };
  };

  Game.prototype.pgn = function (headers) {
    var out = '';
    var h = headers || {};
    var keys = ['Event', 'Site', 'Date', 'Round', 'White', 'Black', 'Result'];
    for (var i = 0; i < keys.length; i++) {
      out += '[' + keys[i] + ' "' + (h[keys[i]] || (keys[i] === 'Result' ? (this.status().result || '*') : '?')) + '"]\n';
    }
    if (this.startFen !== Position.START_FEN) {
      out += '[SetUp "1"]\n[FEN "' + this.startFen + '"]\n';
    }
    out += '\n';
    var startFull = parseInt(this.startFen.split(' ')[5], 10) || 1;
    var startBlack = this.startFen.split(' ')[1] === 'b';
    var line = '';
    for (var j = 0; j < this.history.length; j++) {
      var moveNo = startFull + Math.floor((j + (startBlack ? 1 : 0)) / 2);
      if ((j + (startBlack ? 1 : 0)) % 2 === 0) line += moveNo + '. ';
      else if (j === 0) line += moveNo + '... ';
      line += this.history[j].san + ' ';
    }
    line += this.status().result || '*';
    return out + wrapText(line, 80) + '\n';
  };

  function wrapText(text, width) {
    var words = text.split(' '), lines = [], cur = '';
    for (var i = 0; i < words.length; i++) {
      if (cur.length + words[i].length + 1 > width) { lines.push(cur.trim()); cur = ''; }
      cur += words[i] + ' ';
    }
    if (cur.trim()) lines.push(cur.trim());
    return lines.join('\n');
  }

  /* ------------------------------- PGN ------------------------------ */
  function parsePgn(pgnText) {
    var text = String(pgnText || '');
    var headers = {};
    var headerRe = /\[\s*(\w+)\s*"([^"]*)"\s*\]/g, hm;
    while ((hm = headerRe.exec(text))) headers[hm[1]] = hm[2];

    var body = text.replace(/\[\s*\w+\s*"[^"]*"\s*\]/g, ' ');
    body = body.replace(/\{[^}]*\}/g, ' ');          // Kommentare
    body = body.replace(/;[^\n]*/g, ' ');            // Zeilenkommentare
    body = stripVariations(body);
    body = body.replace(/\$\d+/g, ' ');              // NAGs
    body = body.replace(/\b\d+\.(\.\.)?/g, ' ');     // Zugnummern
    body = body.replace(/(1-0|0-1|1\/2-1\/2|\*)/g, ' ');

    var tokens = body.split(/\s+/).filter(function (t) {
      return t && /^[a-hKQRBNO0][a-h1-8xKQRBNO\-=+#]*$/.test(t);
    });

    var startFen = headers.FEN && headers.SetUp !== '0' ? headers.FEN : Position.START_FEN;
    var game = new Game(startFen);
    var applied = [], failedAt = -1;
    for (var i = 0; i < tokens.length; i++) {
      var entry = game.move(tokens[i]);
      if (!entry) { failedAt = i; break; }
      applied.push(entry);
    }
    return { headers: headers, game: game, moves: applied, tokens: tokens, failedAt: failedAt };
  }

  function stripVariations(s) {
    var out = '', depth = 0;
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (c === '(') { depth++; continue; }
      if (c === ')') { if (depth > 0) depth--; continue; }
      if (depth === 0) out += c;
    }
    return out;
  }

  /* ------------------------------ Export ----------------------------- */
  var api = {
    WHITE: WHITE, BLACK: BLACK,
    PAWN: PAWN, KNIGHT: KNIGHT, BISHOP: BISHOP, ROOK: ROOK, QUEEN: QUEEN, KING: KING,
    CASTLE_WK: CASTLE_WK, CASTLE_WQ: CASTLE_WQ, CASTLE_BK: CASTLE_BK, CASTLE_BQ: CASTLE_BQ,
    F_EP: F_EP, F_CASTLE_K: F_CASTLE_K, F_CASTLE_Q: F_CASTLE_Q, F_DOUBLE: F_DOUBLE,
    KNIGHT_OFFSETS: KNIGHT_OFFSETS, BISHOP_OFFSETS: BISHOP_OFFSETS,
    ROOK_OFFSETS: ROOK_OFFSETS, KING_OFFSETS: KING_OFFSETS,
    PIECE_LETTER: PIECE_LETTER, LETTER_PIECE: LETTER_PIECE,
    Position: Position, Game: Game,
    encodeMove: encodeMove, moveFrom: moveFrom, moveTo: moveTo,
    movePromo: movePromo, moveCaptured: moveCaptured, isCapture: isCapture,
    squareName: squareName, squareFromName: squareFromName,
    fileOf: fileOf, rankOf: rankOf, rowOf: rowOf, offBoard: offBoard,
    isLightSquare: isLightSquare,
    parsePgn: parsePgn,
    START_FEN: Position.START_FEN
  };

  global.ChessCore = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}(typeof self !== 'undefined' ? self : this));
