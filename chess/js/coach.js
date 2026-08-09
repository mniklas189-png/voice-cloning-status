/*
 * coach.js — uebersetzt Engine-Zahlen in Saetze, die Anfaengern helfen.
 * Kein Zugriff auf das DOM; reine Auswertung.
 */
(function (global) {
  'use strict';

  var C = global.ChessCore;
  var E = global.ChessEngine;
  var NAMES = { p: 'Bauer', n: 'Springer', b: 'Läufer', r: 'Turm', q: 'Dame', k: 'König' };
  var NAMES_ACC = { p: 'den Bauern', n: 'den Springer', b: 'den Läufer', r: 'den Turm', q: 'die Dame', k: 'den König' };
  var LETTER = ['', 'p', 'n', 'b', 'r', 'q', 'k'];

  function pieceName(type) { return NAMES[LETTER[type]] || 'Figur'; }
  function pieceAcc(type) { return NAMES_ACC[LETTER[type]] || 'die Figur'; }

  /* ------------------------- Bewertung anzeigen ---------------------- */

  /** Gewinnwahrscheinlichkeit in Prozent (0-100) aus Sicht der Seite am Zug. */
  function winPercent(cp) {
    if (cp > 9000) return 100;
    if (cp < -9000) return 0;
    return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
  }

  /** Mattdistanz in Zuegen, sonst null. */
  function mateIn(score) {
    if (Math.abs(score) < E.MATE - 200) return null;
    var plies = E.MATE - Math.abs(score);
    var moves = Math.ceil(plies / 2);
    return score > 0 ? moves : -moves;
  }

  /** "+1,25" oder "M3" — immer aus Sicht von Weiss, wenn whiteView gesetzt ist. */
  function formatScore(score, turn, whiteView) {
    var s = whiteView && turn === C.BLACK ? -score : score;
    var m = mateIn(s);
    if (m !== null) return (m > 0 ? 'M' : '−M') + Math.abs(m);
    var pawns = s / 100;
    return (pawns > 0 ? '+' : pawns < 0 ? '−' : '±') + Math.abs(pawns).toFixed(2).replace('.', ',');
  }

  function scoreWords(score, turn, whiteView) {
    var s = whiteView && turn === C.BLACK ? -score : score;
    var m = mateIn(s);
    if (m !== null) {
      return m > 0 ? 'Matt in ' + m + (m === 1 ? ' Zug' : ' Zügen') : 'Matt in ' + Math.abs(m) + ' gegen dich';
    }
    var abs = Math.abs(s);
    var side = s > 0 ? 'Weiß' : 'Schwarz';
    if (abs < 30) return 'Ausgeglichen';
    if (abs < 90) return side + ' steht minimal besser';
    if (abs < 250) return side + ' steht besser';
    if (abs < 600) return side + ' hat klaren Vorteil';
    return side + ' gewinnt';
  }

  /* --------------------------- Zugbewertung -------------------------- */
  var CLASSES = {
    best: { key: 'best', label: 'Bester Zug', symbol: '★', tone: 'great' },
    book: { key: 'book', label: 'Eröffnungszug', symbol: '📖', tone: 'book' },
    excellent: { key: 'excellent', label: 'Sehr gut', symbol: '✓', tone: 'great' },
    good: { key: 'good', label: 'Gut', symbol: '✓', tone: 'good' },
    inaccuracy: { key: 'inaccuracy', label: 'Ungenau', symbol: '?!', tone: 'meh' },
    mistake: { key: 'mistake', label: 'Fehler', symbol: '?', tone: 'bad' },
    blunder: { key: 'blunder', label: 'Grober Fehler', symbol: '??', tone: 'awful' },
    forced: { key: 'forced', label: 'Erzwungen', symbol: '=', tone: 'good' }
  };

  /**
   * Klassifiziert einen Zug anhand des Verlusts an Gewinnwahrscheinlichkeit.
   * scoreBefore/scoreAfter jeweils aus Sicht des Ziehenden (Zentibauern).
   */
  function classify(scoreBefore, scoreAfter, wasBest, legalCount, wasBook) {
    if (legalCount === 1) return CLASSES.forced;
    if (wasBook) return CLASSES.book;
    if (wasBest) return CLASSES.best;
    var drop = winPercent(scoreBefore) - winPercent(scoreAfter);
    if (drop < 2) return CLASSES.excellent;
    if (drop < 5) return CLASSES.good;
    if (drop < 10) return CLASSES.inaccuracy;
    if (drop < 20) return CLASSES.mistake;
    return CLASSES.blunder;
  }

  /* ------------------------- Gefahren erkennen ----------------------- */

  /**
   * Eigene Figuren, die der Gegner im naechsten Zug guenstig schlagen koennte.
   * Rueckgabe: [{ square, type, gain, attacker }] absteigend nach Verlust.
   */
  function findHangingPieces(position) {
    var pos = position;
    if (pos.inCheck()) return [];
    var found = {};
    pos.makeNullMove();
    try {
      var caps = pos.generateMoves(true);
      for (var i = 0; i < caps.length; i++) {
        var m = caps[i];
        if (!pos.makeMove(m)) continue;
        pos.undoMove();
        var gain = E.see(pos, m);
        if (gain <= 0) continue;
        var to = C.moveTo(m);
        if (!found[to] || found[to].gain < gain) {
          found[to] = {
            square: to,
            type: pos.board[to] & 7,
            gain: gain,
            attacker: C.moveFrom(m),
            attackerType: pos.board[C.moveFrom(m)] & 7
          };
        }
      }
    } finally {
      pos.undoNullMove();
    }
    return Object.keys(found).map(function (k) { return found[k]; })
      .sort(function (a, b) { return b.gain - a.gain; });
  }

  /** Gegnerische Figuren, die ich guenstig schlagen kann. */
  function findWinnableMaterial(position) {
    var pos = position;
    var caps = pos.generateMoves(true);
    var out = [];
    for (var i = 0; i < caps.length; i++) {
      var m = caps[i];
      if (!pos.makeMove(m)) continue;
      pos.undoMove();
      var gain = E.see(pos, m);
      if (gain >= 100) {
        out.push({ move: m, square: C.moveTo(m), gain: gain, type: pos.board[C.moveTo(m)] & 7 });
      }
    }
    return out.sort(function (a, b) { return b.gain - a.gain; });
  }

  /** Felder, die eine Figur nach ihrem Zug angreift (nur wertvolle Ziele). */
  function attackedTargets(pos, square) {
    var piece = pos.board[square];
    if (!piece) return [];
    var type = piece & 7, us = piece >> 3, them = us ^ 1;
    var targets = [];
    var i, s, d;

    function consider(sq) {
      var t = pos.board[sq];
      if (t && (t >> 3) === them) targets.push({ square: sq, type: t & 7 });
    }

    if (type === C.PAWN) {
      var dir = us === C.WHITE ? -16 : 16;
      [square + dir - 1, square + dir + 1].forEach(function (sq) {
        if (!C.offBoard(sq) && Math.abs((sq & 7) - (square & 7)) === 1) consider(sq);
      });
    } else if (type === C.KNIGHT) {
      for (i = 0; i < 8; i++) { s = square + C.KNIGHT_OFFSETS[i]; if (!C.offBoard(s)) consider(s); }
    } else if (type === C.KING) {
      for (i = 0; i < 8; i++) { s = square + C.KING_OFFSETS[i]; if (!C.offBoard(s)) consider(s); }
    } else {
      var dirs = type === C.BISHOP ? C.BISHOP_OFFSETS : type === C.ROOK ? C.ROOK_OFFSETS : C.KING_OFFSETS;
      var n = type === C.QUEEN ? 8 : 4;
      for (i = 0; i < n; i++) {
        d = dirs[i]; s = square + d;
        while (!C.offBoard(s)) {
          if (pos.board[s]) { consider(s); break; }
          s += d;
        }
      }
    }
    return targets;
  }

  /* ------------------------ Zug in Worte fassen ---------------------- */

  /**
   * Kurze Begruendung, warum ein Zug gut ist.
   * pos: Stellung VOR dem Zug (wird nicht veraendert)
   */
  function explainMove(pos, move) {
    var reasons = [];
    var from = C.moveFrom(move), to = C.moveTo(move);
    var piece = pos.board[from];
    if (!piece) return 'Zug spielen.';
    var type = piece & 7, us = piece >> 3;
    var captured = C.moveCaptured(move);
    var promo = C.movePromo(move);

    // Stand die ziehende Figur vorher in Gefahr?
    var hangingBefore = findHangingPieces(pos);
    var wasHanging = hangingBefore.filter(function (h) { return h.square === from; })[0];

    if (!pos.makeMove(move)) return 'Zug spielen.';
    var givesCheck = pos.inCheck();
    var isMate = givesCheck && pos.generateLegalMoves().length === 0;
    var newTargets = attackedTargets(pos, to);
    // Steht die Figur nach dem Zug selbst sicher?
    var afterHanging = findHangingPieces(pos.turn === us ? pos : pos);
    var nowHanging = afterHanging.filter(function (h) { return h.square === to; })[0];
    pos.undoMove();

    if (isMate) return 'Setzt matt — die Partie ist damit gewonnen.';

    if (promo) reasons.push('wandelt den Bauern in ' + (promo === C.QUEEN ? 'eine Dame' : 'einen ' + pieceName(promo)) + ' um');
    if (captured) {
      reasons.push('schlägt ' + pieceAcc(captured) + ' auf ' + C.squareName(to));
    }
    if (givesCheck) reasons.push('gibt Schach');

    if (move & (C.F_CASTLE_K | C.F_CASTLE_Q)) {
      reasons.push('rochiert: der König kommt in Sicherheit und der Turm ins Spiel');
    }

    if (wasHanging && !captured) {
      reasons.push('bringt ' + pieceAcc(type) + ' aus der Schusslinie (sonst drohte Verlust von etwa ' +
        (wasHanging.gain / 100).toFixed(1).replace('.', ',') + ' Bauerneinheiten)');
    }

    // Gabel / Doppelangriff
    var valuable = newTargets.filter(function (t) { return t.type !== C.PAWN; });
    if (valuable.length >= 2) {
      reasons.push('greift gleichzeitig ' + valuable.slice(0, 2).map(function (t) {
        return pieceAcc(t.type) + ' auf ' + C.squareName(t.square);
      }).join(' und ') + ' an');
    } else if (valuable.length === 1 && !captured) {
      var v = valuable[0];
      if (E.VAL_SIMPLE[v.type] > E.VAL_SIMPLE[type]) {
        reasons.push('greift ' + pieceAcc(v.type) + ' auf ' + C.squareName(v.square) + ' an');
      }
    }

    if (!reasons.length) {
      var toRow = to >> 4, toFile = to & 7;
      var central = toFile >= 2 && toFile <= 5 && toRow >= 2 && toRow <= 5;
      var backRank = us === C.WHITE ? 7 : 0;
      if ((from >> 4) === backRank && (type === C.KNIGHT || type === C.BISHOP)) {
        reasons.push('entwickelt den ' + pieceName(type) + ' ins Spiel');
      } else if (type === C.PAWN && central) {
        reasons.push('nimmt Raum im Zentrum');
      } else if (central) {
        reasons.push('stellt den ' + pieceName(type) + ' aktiver');
      } else if (type === C.ROOK) {
        reasons.push('bringt den Turm auf eine bessere Linie');
      } else {
        reasons.push('verbessert die Stellung');
      }
    }

    if (nowHanging) {
      reasons.push('Achtung: die Figur kann danach geschlagen werden — die Engine hält den Zug trotzdem für richtig');
    }

    var text = reasons[0];
    if (reasons.length > 1) text += ', ' + reasons.slice(1).join(' und ');
    return text.charAt(0).toUpperCase() + text.slice(1) + '.';
  }

  /** Warnung vor dem eigenen Zug: was ist gerade bedroht? */
  function situationHints(pos) {
    var hints = [];
    if (pos.inCheck()) {
      hints.push({
        tone: 'awful', title: 'Du stehst im Schach',
        text: 'Du musst den König retten: wegziehen, dazwischenziehen oder den Angreifer schlagen.'
      });
      return hints;
    }
    var hanging = findHangingPieces(pos);
    if (hanging.length) {
      var h = hanging[0];
      hints.push({
        tone: h.gain >= 300 ? 'awful' : 'bad',
        title: pieceName(h.type) + ' auf ' + C.squareName(h.square) + ' steht in Gefahr',
        text: 'Der Gegner kann dort etwa ' + (h.gain / 100).toFixed(1).replace('.', ',') +
          ' Bauerneinheiten gewinnen. Wegziehen, decken oder Gegendruck aufbauen.',
        squares: hanging.slice(0, 3).map(function (x) { return x.square; })
      });
    }
    var winnable = findWinnableMaterial(pos);
    if (winnable.length && winnable[0].gain >= 200) {
      hints.push({
        tone: 'great',
        title: 'Du kannst Material gewinnen',
        text: 'Auf ' + C.squareName(winnable[0].square) + ' steht ' + pieceAcc(winnable[0].type) +
          ' ungenügend gedeckt.',
        squares: [winnable[0].square]
      });
    }
    return hints;
  }

  /* ---------------------------- Eroeffnungen -------------------------- */
  var OPENINGS = [
    ['e4 e5 Nf3 Nc6 Bb5', 'Spanische Partie (Ruy Lopez)'],
    ['e4 e5 Nf3 Nc6 Bc4', 'Italienische Partie'],
    ['e4 e5 Nf3 Nc6 d4', 'Schottische Partie'],
    ['e4 e5 Nf3 Nf6', 'Russische Verteidigung (Petrow)'],
    ['e4 e5 Nf3 d6', 'Philidor-Verteidigung'],
    ['e4 e5 f4', 'Königsgambit'],
    ['e4 e5 Nc3', 'Wiener Partie'],
    ['e4 e5', 'Offene Partie'],
    ['e4 c5 Nf3 d6', 'Sizilianisch (Najdorf-Aufbau)'],
    ['e4 c5 Nf3 Nc6', 'Sizilianisch (Klassisch)'],
    ['e4 c5', 'Sizilianische Verteidigung'],
    ['e4 e6', 'Französische Verteidigung'],
    ['e4 c6', 'Caro-Kann-Verteidigung'],
    ['e4 d5', 'Skandinavische Verteidigung'],
    ['e4 d6', 'Pirc-Verteidigung'],
    ['e4 Nf6', 'Aljechin-Verteidigung'],
    ['e4 g6', 'Moderne Verteidigung'],
    ['d4 d5 c4 e6', 'Damengambit (angenommen/abgelehnt)'],
    ['d4 d5 c4 c6', 'Slawische Verteidigung'],
    ['d4 d5 c4 dxc4', 'Angenommenes Damengambit'],
    ['d4 d5 c4', 'Damengambit'],
    ['d4 d5 Nf3', 'Geschlossene Partie'],
    ['d4 Nf6 c4 e6', 'Indische Verteidigung (Nimzo/Damenindisch)'],
    ['d4 Nf6 c4 g6', 'Königsindische Verteidigung'],
    ['d4 Nf6 c4 c5', 'Benoni-Verteidigung'],
    ['d4 Nf6 c4', 'Indische Systeme'],
    ['d4 Nf6', 'Indische Verteidigung'],
    ['d4 f5', 'Holländische Verteidigung'],
    ['d4 d5', 'Geschlossene Partie'],
    ['c4', 'Englische Eröffnung'],
    ['Nf3 d5', 'Réti-Eröffnung'],
    ['Nf3', 'Zukertort-Eröffnung'],
    ['b3', 'Larsen-Eröffnung'],
    ['g3', 'Benko-Eröffnung'],
    ['f4', 'Bird-Eröffnung'],
    ['e4', 'Königsbauerneröffnung'],
    ['d4', 'Damenbauerneröffnung']
  ];

  /** Name der Eroeffnung aus der SAN-Zugliste (laengste Uebereinstimmung gewinnt). */
  function openingName(sanList) {
    var line = sanList.slice(0, 12).join(' ');
    var best = null;
    for (var i = 0; i < OPENINGS.length; i++) {
      var prefix = OPENINGS[i][0];
      if (line === prefix || line.indexOf(prefix + ' ') === 0) {
        if (!best || prefix.length > best[0].length) best = OPENINGS[i];
      }
    }
    return best ? { name: best[1], moves: best[0].split(' ').length } : null;
  }

  /** Ist der Zug noch Teil einer bekannten Eroeffnung? */
  function isBookMove(sanListIncludingMove) {
    var op = openingName(sanListIncludingMove);
    return !!(op && op.moves >= sanListIncludingMove.length);
  }

  /* ------------------------- Anfaenger-Grundregeln -------------------- */
  var PRINCIPLES = [
    { phase: 'opening', text: 'Bringe zuerst die Bauern ins Zentrum (e4/d4 bzw. e5/d5).' },
    { phase: 'opening', text: 'Entwickle Springer und Läufer, bevor du die Dame herausbringst.' },
    { phase: 'opening', text: 'Rochiere früh — ein sicherer König erspart dir die meisten Niederlagen.' },
    { phase: 'opening', text: 'Ziehe nicht zweimal mit derselben Figur, solange andere noch zu Hause stehen.' },
    { phase: 'middle', text: 'Vor jedem Zug: Was droht der Gegner? Welche meiner Figuren steht ungedeckt?' },
    { phase: 'middle', text: 'Türme gehören auf offene Linien.' },
    { phase: 'middle', text: 'Tausche ab, wenn du mehr Material hast — vereinfache in Richtung Gewinn.' },
    { phase: 'middle', text: 'Suche nach Gabeln, Fesselungen und Spießen — dort entsteht Materialgewinn.' },
    { phase: 'end', text: 'Im Endspiel gehört der König aktiv ins Zentrum.' },
    { phase: 'end', text: 'Freibauern sind Gold wert — schiebe sie vor und stelle den Turm dahinter.' }
  ];

  function phaseOf(pos) {
    var material = 0;
    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var p = pos.board[r * 16 + f];
        if (!p) continue;
        var t = p & 7;
        if (t !== C.PAWN && t !== C.KING) material += E.VAL_SIMPLE[t];
      }
    }
    if (material >= 6000) return 'opening';
    if (material >= 2400) return 'middle';
    return 'end';
  }

  function principleFor(pos, moveCount) {
    var phase = moveCount < 12 ? 'opening' : phaseOf(pos);
    var pool = PRINCIPLES.filter(function (p) { return p.phase === phase; });
    return pool[moveCount % pool.length].text;
  }

  global.ChessCoach = {
    winPercent: winPercent,
    mateIn: mateIn,
    formatScore: formatScore,
    scoreWords: scoreWords,
    classify: classify,
    CLASSES: CLASSES,
    findHangingPieces: findHangingPieces,
    findWinnableMaterial: findWinnableMaterial,
    attackedTargets: attackedTargets,
    explainMove: explainMove,
    situationHints: situationHints,
    openingName: openingName,
    isBookMove: isBookMove,
    principleFor: principleFor,
    phaseOf: phaseOf,
    pieceName: pieceName,
    pieceAcc: pieceAcc
  };
}(typeof self !== 'undefined' ? self : this));
