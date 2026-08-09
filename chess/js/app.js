/*
 * app.js — verbindet Brett, Engine, Coach und Chess.com-Daten.
 */
(function () {
  'use strict';

  var C = window.ChessCore;
  var E = window.ChessEngine;
  var Coach = window.ChessCoach;
  var Api = window.ChessCom;

  /* ============================ Hilfsmittel ============================ */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function el(tag, cls, parent) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (parent) parent.appendChild(node);
    return node;
  }

  function store(key, value) {
    try {
      if (value === undefined) {
        var raw = localStorage.getItem('schachcoach:' + key);
        return raw === null ? undefined : JSON.parse(raw);
      }
      localStorage.setItem('schachcoach:' + key, JSON.stringify(value));
    } catch (err) { /* privater Modus o.ae. */ }
    return undefined;
  }

  /* ------------------------------ Klaenge ------------------------------ */
  var Sound = (function () {
    var ctx = null;
    var enabled = store('sound') !== false;

    function context() {
      if (!ctx && (window.AudioContext || window.webkitAudioContext)) {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
      }
      return ctx;
    }
    function tone(freq, duration, type, gainValue) {
      if (!enabled) return;
      var ac = context();
      if (!ac) return;
      if (ac.state === 'suspended') ac.resume();
      var osc = ac.createOscillator();
      var gain = ac.createGain();
      osc.type = type || 'sine';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, ac.currentTime);
      gain.gain.exponentialRampToValueAtTime(gainValue || 0.08, ac.currentTime + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + duration);
      osc.connect(gain); gain.connect(ac.destination);
      osc.start(); osc.stop(ac.currentTime + duration + 0.02);
    }
    return {
      move: function () { tone(320, 0.07, 'triangle', 0.06); },
      capture: function () { tone(180, 0.11, 'square', 0.05); },
      check: function () { tone(700, 0.13, 'triangle', 0.07); },
      end: function () { tone(520, 0.18, 'sine', 0.07); setTimeout(function () { tone(392, 0.3, 'sine', 0.06); }, 130); },
      alert: function () { tone(240, 0.16, 'sawtooth', 0.04); },
      isEnabled: function () { return enabled; },
      toggle: function (value) { enabled = value; store('sound', value); }
    };
  }());

  /* ========================= Engine-Anbindung ========================= */
  function EngineClient() {
    this.nextId = 1;
    this.pending = Object.create(null);
    this.worker = null;
    this.fallback = null;
    this.ready = false;
    this.init();
  }

  EngineClient.prototype.init = function () {
    var self = this;
    try {
      // Gegen die Basis-URL aufloesen, damit der Pfad auch in Unterverzeichnissen stimmt.
      this.worker = new Worker(new URL('js/engine-worker.js', document.baseURI));
      this.worker.onmessage = function (e) { self._onMessage(e.data); };
      this.worker.onerror = function () { self._useFallback(); };
      this.ready = true;
    } catch (err) {
      this._useFallback();
    }
  };

  /** Ohne Worker (z. B. bei lokal geoeffneter Datei) rechnet die Engine im Hauptthread. */
  EngineClient.prototype._useFallback = function () {
    if (this.fallback) return;
    if (this.worker) { try { this.worker.terminate(); } catch (e) { /* egal */ } this.worker = null; }
    this.fallback = new E.Searcher();
    this.ready = true;
    var banner = $('#worker-fallback');
    if (banner) banner.hidden = false;
  };

  EngineClient.prototype._onMessage = function (data) {
    var entry = this.pending[data.id];
    if (!entry) return;
    if (data.type === 'progress') { if (entry.onProgress) entry.onProgress(data); return; }
    delete this.pending[data.id];
    if (data.type === 'error') entry.reject(new Error(data.message));
    else entry.resolve(data);
  };

  /**
   * options: { movetime, maxDepth, level, applyLevel, repetitionKeys, onProgress, freshTable }
   */
  EngineClient.prototype.search = function (fen, options) {
    var opts = options || {};
    var id = this.nextId++;
    var self = this;

    if (this.fallback) {
      return new Promise(function (resolve, reject) {
        setTimeout(function () {
          try { resolve(self._searchSync(id, fen, opts)); } catch (err) { reject(err); }
        }, 10);
      });
    }

    return new Promise(function (resolve, reject) {
      self.pending[id] = { resolve: resolve, reject: reject, onProgress: opts.onProgress };
      self.worker.postMessage({
        type: 'search', id: id, fen: fen,
        movetime: opts.movetime, maxDepth: opts.maxDepth,
        level: opts.level, applyLevel: !!opts.applyLevel,
        repetitionKeys: opts.repetitionKeys || [],
        wantProgress: !!opts.onProgress,
        freshTable: !!opts.freshTable
      });
    });
  };

  EngineClient.prototype._searchSync = function (id, fen, opts) {
    var pos = new C.Position(fen);
    var level = typeof opts.level === 'number' ? opts.level : 10;
    var info = E.LEVELS[Math.max(0, Math.min(E.LEVELS.length - 1, level))];
    if (opts.freshTable) this.fallback.reset();
    var started = Date.now();
    var result = this.fallback.search(pos, {
      movetime: opts.movetime || info.movetime,
      maxDepth: opts.maxDepth || info.depth,
      repetitionKeys: opts.repetitionKeys || []
    });
    var chosen = opts.applyLevel ? E.pickWithSkill(result, level, Math.random) : result.bestMove;
    var chosenInfo = result.rootMoves.filter(function (m) { return m.move === chosen; })[0];
    return {
      type: 'result', id: id, fen: fen,
      best: { move: result.bestMove, san: result.bestSan, uci: result.bestUci, score: result.score },
      chosen: chosenInfo || { move: result.bestMove, san: result.bestSan, uci: result.bestUci, score: result.score },
      depth: result.depth, nodes: result.nodes, elapsed: Date.now() - started,
      pv: result.pv, rootMoves: result.rootMoves.slice(0, 6)
    };
  };

  var engine = new EngineClient();

  /* =========================== Gemeinsame UI =========================== */
  function legalMoveObjects(pos) {
    return pos.generateLegalMoves().map(function (m) {
      return {
        from: C.moveFrom(m), to: C.moveTo(m),
        promotion: C.movePromo(m) ? C.PIECE_LETTER[C.movePromo(m)] : '',
        color: pos.turn, raw: m
      };
    });
  }

  function renderEvalBar(barEl, textEl, score, turn) {
    if (!barEl) return;
    var white = turn === C.WHITE ? score : -score;
    var pct = Coach.winPercent(white);
    barEl.style.setProperty('--white-share', pct.toFixed(1) + '%');
    barEl.setAttribute('aria-label', 'Stellungsbewertung: ' + Coach.scoreWords(score, turn, true));
    barEl.dataset.value = Coach.formatScore(score, turn, true);
    if (textEl) textEl.textContent = Coach.formatScore(score, turn, true);
  }

  function moveListHtml(history, currentPly, classifications) {
    var rows = '';
    for (var i = 0; i < history.length; i += 2) {
      var no = Math.floor(i / 2) + 1;
      rows += '<div class="move-row"><span class="move-no">' + no + '.</span>' +
        moveCell(history[i], i, currentPly, classifications) +
        (history[i + 1] ? moveCell(history[i + 1], i + 1, currentPly, classifications) : '<span class="move-empty"></span>') +
        '</div>';
    }
    return rows || '<p class="empty-note">Noch keine Züge.</p>';
  }

  function moveCell(entry, ply, currentPly, classifications) {
    var cls = classifications && classifications[ply];
    return '<button type="button" class="move-cell' + (ply === currentPly ? ' active' : '') +
      (cls ? ' tone-' + cls.tone : '') + '" data-ply="' + ply + '">' +
      escapeHtml(entry.san) +
      (cls && cls.symbol && cls.key !== 'good' && cls.key !== 'excellent' && cls.key !== 'forced'
        ? '<span class="move-mark">' + cls.symbol + '</span>' : '') +
      '</button>';
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function capturedMaterial(pos) {
    var counts = { w: {}, b: {} };
    var startCount = { p: 8, n: 2, b: 2, r: 2, q: 1 };
    ['w', 'b'].forEach(function (c) {
      Object.keys(startCount).forEach(function (t) { counts[c][t] = startCount[t]; });
    });
    for (var r = 0; r < 8; r++) {
      for (var f = 0; f < 8; f++) {
        var p = pos.board[r * 16 + f];
        if (!p) continue;
        var letter = C.PIECE_LETTER[p & 7];
        if (letter === 'k') continue;
        var color = (p >> 3) === C.WHITE ? 'w' : 'b';
        if (counts[color][letter] !== undefined) counts[color][letter]--;
      }
    }
    // negative Werte entstehen durch Umwandlungen — auf 0 begrenzen
    ['w', 'b'].forEach(function (c) {
      Object.keys(counts[c]).forEach(function (t) { if (counts[c][t] < 0) counts[c][t] = 0; });
    });
    var value = { w: 0, b: 0 };
    ['w', 'b'].forEach(function (c) {
      Object.keys(counts[c]).forEach(function (t) {
        value[c] += counts[c][t] * E.VAL_SIMPLE[C.LETTER_PIECE[t]];
      });
    });
    return { counts: counts, advantage: Math.round((value.b - value.w) / 100) };
  }

  function capturedHtml(counts, color) {
    var order = ['q', 'r', 'b', 'n', 'p'];
    var html = '';
    order.forEach(function (t) {
      for (var i = 0; i < (counts[color][t] || 0); i++) {
        html += '<span class="captured-piece">' + window.ChessPieces.svg(t, color) + '</span>';
      }
    });
    return html;
  }

  /* ============================ Spielen-Ansicht ======================== */
  var play = {
    game: new C.Game(),
    board: null,
    level: store('level') === undefined ? 3 : store('level'),
    playerColor: store('playerColor') || 'w',
    autoHint: store('autoHint') === undefined ? true : store('autoHint'),
    warnBlunders: store('warnBlunders') === undefined ? true : store('warnBlunders'),
    showDanger: store('showDanger') === undefined ? true : store('showDanger'),
    analysis: null,
    thinking: false,
    lastMove: null,
    classifications: {},
    pendingUndo: null,
    scoreHistory: [],
    finished: false
  };

  function playInit() {
    play.board = new window.ChessBoard($('#play-board'), {
      orientation: play.playerColor === 'w' ? 'white' : 'black',
      onMove: onPlayerMove
    });

    var levelSelect = $('#level-select');
    E.LEVELS.forEach(function (lvl, i) {
      var opt = el('option', null, levelSelect);
      opt.value = String(i);
      opt.textContent = (i + 1) + ' · ' + lvl.name + ' (' + lvl.elo + ')';
    });
    levelSelect.value = String(play.level);
    levelSelect.addEventListener('change', function () {
      play.level = Number(levelSelect.value);
      store('level', play.level);
      $('#level-note').textContent = E.LEVELS[play.level].name + ' — Spielstärke etwa ' + E.LEVELS[play.level].elo + ' Elo.';
    });
    $('#level-note').textContent = E.LEVELS[play.level].name + ' — Spielstärke etwa ' + E.LEVELS[play.level].elo + ' Elo.';

    $$('input[name="player-color"]').forEach(function (input) {
      input.checked = input.value === play.playerColor;
      input.addEventListener('change', function () {
        if (!input.checked) return;
        play.playerColor = input.value;
        store('playerColor', play.playerColor);
      });
    });

    bindToggle('#toggle-auto-hint', 'autoHint');
    bindToggle('#toggle-warn', 'warnBlunders');
    bindToggle('#toggle-danger', 'showDanger');

    var soundToggle = $('#toggle-sound');
    soundToggle.checked = Sound.isEnabled();
    soundToggle.addEventListener('change', function () { Sound.toggle(soundToggle.checked); });

    $('#btn-new-game').addEventListener('click', newGame);
    $('#btn-undo').addEventListener('click', undoPlayerMove);
    $('#btn-flip').addEventListener('click', function () { play.board.flip(); });
    $('#btn-hint').addEventListener('click', showHint);
    $('#btn-resign').addEventListener('click', function () {
      if (play.finished) return;
      play.finished = true;
      setPlayStatus('Aufgegeben', 'Du hast aufgegeben. Kein Problem — starte einfach eine neue Partie.', 'bad');
      play.board.setInteractive(false);
    });
    $('#btn-copy-pgn').addEventListener('click', function () {
      var pgn = play.game.pgn({
        Event: 'Schach-Coach Übungspartie',
        White: play.playerColor === 'w' ? 'Du' : 'Coach-Engine Stufe ' + (play.level + 1),
        Black: play.playerColor === 'b' ? 'Du' : 'Coach-Engine Stufe ' + (play.level + 1),
        Date: new Date().toISOString().slice(0, 10).replace(/-/g, '.')
      });
      copyText(pgn, $('#btn-copy-pgn'));
    });

    $('#play-moves').addEventListener('click', function (e) {
      var btn = e.target.closest('.move-cell');
      if (btn) jumpPlayTo(Number(btn.dataset.ply));
    });

    newGame();
  }

  function bindToggle(selector, key) {
    var input = $(selector);
    if (!input) return;
    input.checked = play[key];
    input.addEventListener('change', function () {
      play[key] = input.checked;
      store(key, input.checked);
      refreshPlayView();
      if (key === 'autoHint' && input.checked) requestAnalysis();
    });
  }

  function copyText(text, button) {
    var done = function () {
      var original = button.textContent;
      button.textContent = 'Kopiert ✓';
      setTimeout(function () { button.textContent = original; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text, done); });
    } else fallbackCopy(text, done);
  }

  function fallbackCopy(text, done) {
    var area = el('textarea', 'visually-hidden', document.body);
    area.value = text;
    area.select();
    try { document.execCommand('copy'); done(); } catch (err) { /* nichts zu tun */ }
    area.remove();
  }

  function newGame() {
    play.game.reset();
    play.analysis = null;
    play.lastMove = null;
    play.classifications = {};
    play.pendingUndo = null;
    play.scoreHistory = [0];
    play.finished = false;
    play.viewPly = null;
    play.board.setOrientation(play.playerColor === 'w' ? 'white' : 'black');
    play.board.setPosition(play.game.fen(), { instant: true });
    play.board.setArrows([]);
    play.board.setInteractive(true);
    engine.search(C.START_FEN, { movetime: 1, maxDepth: 1, freshTable: true }).catch(function () { });
    setPlayStatus('Neue Partie', 'Viel Erfolg! Der Coach meldet sich vor jedem Zug.', 'neutral');
    refreshPlayView();
    maybeEngineMove();
  }

  function playerToMove() {
    return play.game.turn() === (play.playerColor === 'w' ? C.WHITE : C.BLACK);
  }

  function refreshPlayView() {
    var pos = play.game.position;
    var atLive = play.viewPly === null || play.viewPly === play.game.history.length - 1;

    play.board.setLegalMoves(atLive && playerToMove() && !play.finished ? legalMoveObjects(pos) : []);
    play.board.setInteractive(atLive && playerToMove() && !play.finished);

    var highlights = {};
    if (play.lastMove) highlights.lastMove = [play.lastMove.from, play.lastMove.to];
    if (pos.inCheck()) highlights.check = pos.kings[pos.turn];
    if (play.showDanger && playerToMove() && !play.finished) {
      var hanging = Coach.findHangingPieces(pos);
      highlights.danger = hanging.slice(0, 3).map(function (h) { return h.square; });
    }
    play.board.setHighlights(highlights);

    $('#play-moves').innerHTML = moveListHtml(play.game.history, play.game.history.length - 1, play.classifications);
    var movesBox = $('#play-moves');
    movesBox.scrollTop = movesBox.scrollHeight;

    var mat = capturedMaterial(pos);
    var topColor = play.board.orientation === 'white' ? 'b' : 'w';
    var bottomColor = topColor === 'w' ? 'b' : 'w';
    $('#play-captured-top').innerHTML = capturedHtml(mat.counts, topColor);
    $('#play-captured-bottom').innerHTML = capturedHtml(mat.counts, bottomColor);
    var advTop = topColor === 'w' ? -mat.advantage : mat.advantage;
    $('#play-adv-top').textContent = advTop > 0 ? '+' + advTop : '';
    $('#play-adv-bottom').textContent = advTop < 0 ? '+' + (-advTop) : '';

    $('#play-name-top').textContent = play.playerColor === 'w'
      ? 'Coach-Engine · Stufe ' + (play.level + 1) : 'Du';
    $('#play-name-bottom').textContent = play.playerColor === 'w'
      ? 'Du' : 'Coach-Engine · Stufe ' + (play.level + 1);

    var opening = Coach.openingName(play.game.history.map(function (h) { return h.san; }));
    $('#play-opening').textContent = opening ? opening.name : '';

    renderCoachPanel();
  }

  function setPlayStatus(title, text, tone) {
    var box = $('#play-status');
    box.className = 'status-banner tone-' + (tone || 'neutral');
    $('#play-status-title').textContent = title;
    $('#play-status-text').textContent = text;
  }

  function renderCoachPanel() {
    var panel = $('#coach-content');
    var pos = play.game.position;
    panel.innerHTML = '';

    if (play.finished) {
      var done = el('p', 'coach-line', panel);
      done.textContent = 'Partie beendet. Über „Analyse“ kannst du die Partie Zug für Zug durchgehen.';
      return;
    }

    if (!playerToMove()) {
      var wait = el('p', 'coach-line', panel);
      wait.textContent = play.thinking ? 'Die Engine denkt nach …' : 'Der Gegner ist am Zug.';
      return;
    }

    Coach.situationHints(pos).forEach(function (hint) {
      var card = el('div', 'coach-hint tone-' + hint.tone, panel);
      el('strong', null, card).textContent = hint.title;
      el('p', null, card).textContent = hint.text;
    });

    if (play.analysis) {
      var a = play.analysis;
      var evalLine = el('div', 'coach-hint tone-info', panel);
      el('strong', null, evalLine).textContent = Coach.scoreWords(a.best.score, pos.turn, true) +
        ' (' + Coach.formatScore(a.best.score, pos.turn, true) + ')';

      if (play.autoHint) {
        var body = el('p', null, evalLine);
        body.innerHTML = 'Bester Zug: <b>' + escapeHtml(a.best.san) + '</b> — ' +
          escapeHtml(Coach.explainMove(pos, a.best.move));
      } else {
        el('p', null, evalLine).textContent = 'Tippe auf „Tipp zeigen“, wenn du nicht weiterkommst.';
      }
    } else {
      el('p', 'coach-line', panel).textContent = 'Der Coach prüft die Stellung …';
    }

    var principle = el('div', 'coach-principle', panel);
    el('span', null, principle).textContent = 'Merksatz';
    el('p', null, principle).textContent = Coach.principleFor(pos, play.game.history.length);
  }

  /** Analyse der aktuellen Stellung anstossen (fuer Tipps + Fehlerwarnung). */
  function requestAnalysis() {
    if (play.finished || !playerToMove()) return;
    var fen = play.game.fen();
    play.analysis = null;
    renderCoachPanel();
    engine.search(fen, {
      movetime: 550, maxDepth: 12,
      repetitionKeys: play.game.repetitionKeys()
    }).then(function (result) {
      if (play.game.fen() !== fen) return;              // Stellung hat sich geaendert
      play.analysis = result;
      renderEvalBar($('#play-eval'), $('#play-eval-text'), result.best.score, play.game.turn());
      if (play.autoHint) {
        play.board.setArrows([{ from: C.moveFrom(result.best.move), to: C.moveTo(result.best.move) }]);
      }
      renderCoachPanel();
    }).catch(function () { /* Analyse ist optional */ });
  }

  function showHint() {
    if (!play.analysis) { requestAnalysis(); return; }
    var move = play.analysis.best.move;
    play.board.setArrows([{ from: C.moveFrom(move), to: C.moveTo(move) }]);
    var pos = play.game.position;
    setPlayStatus('Tipp: ' + play.analysis.best.san,
      Coach.explainMove(pos, move), 'info');
  }

  function onPlayerMove(moveObj) {
    if (play.finished || !playerToMove()) return;
    var pos = play.game.position;
    var scoreBefore = play.analysis ? play.analysis.best.score : null;
    var bestMove = play.analysis ? play.analysis.best.move : null;
    var legalCount = pos.generateLegalMoves().length;
    var sanList = play.game.history.map(function (h) { return h.san; });

    applyMove(moveObj.raw, function (entry) {
      var ply = play.game.history.length - 1;
      sanList.push(entry.san);
      var wasBook = Coach.isBookMove(sanList);

      // Bewertung nach dem Zug holen, um den Zug einzuordnen
      engine.search(play.game.fen(), {
        movetime: 500, maxDepth: 12,
        repetitionKeys: play.game.repetitionKeys()
      }).then(function (after) {
        var scoreAfter = -after.best.score;                 // wieder aus Sicht des Spielers
        play.scoreHistory[ply + 1] = play.game.turn() === C.WHITE ? after.best.score : -after.best.score;
        if (scoreBefore !== null) {
          var cls = Coach.classify(scoreBefore, scoreAfter, entry.move === bestMove, legalCount, wasBook);
          play.classifications[ply] = cls;
          refreshPlayView();
          if (play.warnBlunders && (cls.key === 'blunder' || cls.key === 'mistake')) {
            offerTakeback(cls, scoreBefore, scoreAfter, bestMove, entry);
            return;
          }
        }
        continueAfterPlayerMove();
      }).catch(continueAfterPlayerMove);
    });
  }

  function continueAfterPlayerMove() {
    if (play.pendingUndo) return;
    refreshPlayView();
    maybeEngineMove();
  }

  function offerTakeback(cls, scoreBefore, scoreAfter, bestMove, entry) {
    var posBefore = new C.Position(entry.fenBefore);
    play.pendingUndo = true;
    Sound.alert();
    var box = $('#play-status');
    box.className = 'status-banner tone-' + cls.tone;
    $('#play-status-title').textContent = cls.label + ': ' + entry.san;
    $('#play-status-text').textContent = bestMove
      ? 'Besser war ' + posBefore.moveToSan(bestMove) + ' — ' + Coach.explainMove(posBefore, bestMove)
      : 'Dieser Zug verschlechtert deine Stellung deutlich.';

    var actions = $('#play-status-actions');
    actions.innerHTML = '';
    actions.hidden = false;

    var again = el('button', 'btn btn-small btn-primary', actions);
    again.type = 'button';
    again.textContent = 'Zug zurücknehmen';
    again.addEventListener('click', function () {
      actions.hidden = true;
      play.pendingUndo = null;
      play.game.undo();
      delete play.classifications[play.game.history.length];
      play.lastMove = play.game.history.length
        ? play.game.history[play.game.history.length - 1] : null;
      play.board.setPosition(play.game.fen(), { instant: true });
      setPlayStatus('Noch einmal', 'Versuche einen anderen Zug. Der Tipp-Knopf hilft dir weiter.', 'info');
      refreshPlayView();
      requestAnalysis();
    });

    var keep = el('button', 'btn btn-small', actions);
    keep.type = 'button';
    keep.textContent = 'Trotzdem weiterspielen';
    keep.addEventListener('click', function () {
      actions.hidden = true;
      play.pendingUndo = null;
      continueAfterPlayerMove();
    });
  }

  function applyMove(rawMove, callback) {
    var entry = play.game.move(rawMove);
    if (!entry) return;
    play.lastMove = entry;
    play.board.setArrows([]);
    play.board.setPosition(play.game.fen(), { move: { from: entry.from, to: entry.to } });
    if (entry.check) Sound.check();
    else if (entry.captured) Sound.capture();
    else Sound.move();
    refreshPlayView();

    var status = play.game.status();
    if (status.over) {
      play.finished = true;
      play.board.setInteractive(false);
      Sound.end();
      var tone = status.result === '1/2-1/2' ? 'info'
        : (status.winner === (play.playerColor === 'w' ? C.WHITE : C.BLACK)) ? 'great' : 'bad';
      setPlayStatus(status.text, status.result === '1/2-1/2'
        ? 'Remis — beide Seiten teilen den Punkt.'
        : (tone === 'great' ? 'Gut gespielt!' : 'Beim nächsten Mal klappt es besser.'), tone);
      refreshPlayView();
      return;
    }
    if (callback) callback(entry);
  }

  function maybeEngineMove() {
    if (play.finished || playerToMove()) {
      requestAnalysis();
      return;
    }
    play.thinking = true;
    renderCoachPanel();
    var fen = play.game.fen();
    engine.search(fen, {
      level: play.level, applyLevel: true,
      repetitionKeys: play.game.repetitionKeys()
    }).then(function (result) {
      play.thinking = false;
      if (play.game.fen() !== fen || play.finished) return;
      applyMove(result.chosen.move, function () {
        requestAnalysis();
      });
      if (!play.finished) requestAnalysis();
    }).catch(function () {
      play.thinking = false;
      setPlayStatus('Engine-Problem', 'Die Engine konnte keinen Zug berechnen. Starte die Partie neu.', 'bad');
    });
  }

  function undoPlayerMove() {
    if (!play.game.history.length) return;
    $('#play-status-actions').hidden = true;
    play.pendingUndo = null;
    play.finished = false;
    // Zwei Halbzuege zurueck, damit der Spieler wieder am Zug ist
    play.game.undo();
    if (play.game.history.length && !playerToMove()) play.game.undo();
    delete play.classifications[play.game.history.length];
    play.lastMove = play.game.history.length ? play.game.history[play.game.history.length - 1] : null;
    play.board.setPosition(play.game.fen(), { instant: true });
    play.board.setInteractive(true);
    setPlayStatus('Zug zurückgenommen', 'Du bist wieder am Zug.', 'info');
    refreshPlayView();
    requestAnalysis();
  }

  function jumpPlayTo(ply) {
    // Nur Anzeige: Brett auf den gewaehlten Halbzug stellen
    var entry = play.game.history[ply];
    if (!entry) return;
    play.viewPly = ply;
    play.board.setPosition(entry.fenAfter, { instant: true });
    play.board.setHighlights({ lastMove: [entry.from, entry.to] });
    play.board.setInteractive(false);
    $('#play-moves').innerHTML = moveListHtml(play.game.history, ply, play.classifications);
    $('#btn-back-live').hidden = ply === play.game.history.length - 1;
  }

  /* ========================= Analyse / Review ========================== */
  function ReviewView(prefix) {
    this.prefix = prefix;
    this.game = null;
    this.positions = [];       // FEN vor jedem Halbzug + Endstellung
    this.moves = [];
    this.analyses = [];
    this.classifications = {};
    this.ply = 0;
    this.board = null;
    this.running = false;
    this.cancelled = false;
    this.headers = {};
    this.playerColor = 'w';
  }

  ReviewView.prototype.id = function (suffix) { return '#' + this.prefix + '-' + suffix; };

  ReviewView.prototype.mount = function () {
    var self = this;
    this.board = new window.ChessBoard($(this.id('board')), { interactive: false });
    $(this.id('prev')).addEventListener('click', function () { self.goTo(self.ply - 1); });
    $(this.id('next')).addEventListener('click', function () { self.goTo(self.ply + 1); });
    $(this.id('first')).addEventListener('click', function () { self.goTo(0); });
    $(this.id('last')).addEventListener('click', function () { self.goTo(self.moves.length); });
    $(this.id('flip')).addEventListener('click', function () { self.board.flip(); });
    var movesBox = $(this.id('moves'));
    movesBox.addEventListener('click', function (e) {
      var btn = e.target.closest('.move-cell');
      if (btn) self.goTo(Number(btn.dataset.ply) + 1);
    });
    document.addEventListener('keydown', function (e) {
      if (!$(self.id('panel')) || $(self.id('panel')).closest('.tab-panel').hidden) return;
      if (e.target.matches('input, textarea, select')) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); self.goTo(self.ply - 1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); self.goTo(self.ply + 1); }
    });
  };

  ReviewView.prototype.load = function (game, headers, playerColor) {
    this.game = game;
    this.headers = headers || {};
    this.playerColor = playerColor || 'w';
    this.moves = game.history.slice();
    this.analyses = new Array(this.moves.length + 1);
    this.classifications = {};
    this.cancelled = false;

    this.positions = [game.startFen];
    for (var i = 0; i < this.moves.length; i++) this.positions.push(this.moves[i].fenAfter);

    this.board.setOrientation(playerColor === 'b' ? 'black' : 'white');
    this.goTo(0);
    $(this.id('summary')).hidden = true;
    $(this.id('progress-wrap')).hidden = false;
    this.runAnalysis();
  };

  ReviewView.prototype.goTo = function (ply) {
    if (!this.moves) return;
    this.ply = Math.max(0, Math.min(this.moves.length, ply));
    var fen = this.positions[this.ply];
    this.board.setPosition(fen, { instant: true });

    var highlights = {};
    if (this.ply > 0) {
      var m = this.moves[this.ply - 1];
      highlights.lastMove = [m.from, m.to];
    }
    var pos = new C.Position(fen);
    if (pos.inCheck()) highlights.check = pos.kings[pos.turn];
    this.board.setHighlights(highlights);

    this.renderMoves();
    this.renderDetail(pos);
  };

  ReviewView.prototype.renderMoves = function () {
    $(this.id('moves')).innerHTML = moveListHtml(this.moves, this.ply - 1, this.classifications);
    var active = $(this.id('moves')).querySelector('.move-cell.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
  };

  ReviewView.prototype.renderDetail = function (pos) {
    var box = $(this.id('detail'));
    box.innerHTML = '';
    var analysisBefore = this.analyses[this.ply - 1];
    var analysisHere = this.analyses[this.ply];

    if (analysisHere) {
      renderEvalBar($(this.id('eval')), $(this.id('eval-text')), analysisHere.best.score, pos.turn);
    }

    if (this.ply === 0) {
      var intro = el('div', 'coach-hint tone-info', box);
      el('strong', null, intro).textContent = 'Startstellung';
      el('p', null, intro).textContent = 'Blättere mit den Pfeiltasten oder klicke auf einen Zug in der Liste.';
    } else {
      var move = this.moves[this.ply - 1];
      var cls = this.classifications[this.ply - 1];
      var posBefore = new C.Position(move.fenBefore);
      var card = el('div', 'coach-hint tone-' + (cls ? cls.tone : 'info'), box);
      el('strong', null, card).textContent = move.san + (cls ? ' — ' + cls.label : '');

      if (analysisBefore) {
        var bestSan = analysisBefore.best.san;
        if (cls && (cls.key === 'blunder' || cls.key === 'mistake' || cls.key === 'inaccuracy')) {
          var p = el('p', null, card);
          p.innerHTML = 'Besser war <b>' + escapeHtml(bestSan) + '</b>: ' +
            escapeHtml(Coach.explainMove(posBefore, analysisBefore.best.move));
          var showBtn = el('button', 'btn btn-small', card);
          showBtn.type = 'button';
          showBtn.textContent = 'Besseren Zug auf dem Brett zeigen';
          var self = this;
          showBtn.addEventListener('click', function () {
            self.board.setPosition(move.fenBefore, { instant: true });
            self.board.setArrows([{ from: C.moveFrom(analysisBefore.best.move), to: C.moveTo(analysisBefore.best.move) }]);
            self.board.setHighlights({ hint: [C.moveFrom(analysisBefore.best.move), C.moveTo(analysisBefore.best.move)] });
          });
        } else {
          el('p', null, card).textContent = Coach.explainMove(posBefore, move.move);
        }
      } else {
        el('p', null, card).textContent = 'Wird analysiert …';
      }
    }

    if (analysisHere) {
      var lines = el('div', 'engine-lines', box);
      el('h4', null, lines).textContent = 'Engine-Vorschläge';
      var list = el('ol', null, lines);
      (analysisHere.rootMoves || []).slice(0, 3).forEach(function (rm) {
        var li = el('li', null, list);
        el('span', 'line-score', li).textContent = Coach.formatScore(rm.score, pos.turn, true);
        el('span', 'line-move', li).textContent = rm.san;
      });
      if (analysisHere.pv && analysisHere.pv.length > 1) {
        var pv = el('p', 'pv-line', lines);
        pv.textContent = 'Fortsetzung: ' + analysisHere.pv.map(function (p) { return p.san; }).join(' ');
      }
    }

    var hints = Coach.situationHints(pos);
    hints.forEach(function (hint) {
      var card2 = el('div', 'coach-hint tone-' + hint.tone, box);
      el('strong', null, card2).textContent = hint.title;
      el('p', null, card2).textContent = hint.text;
    });
  };

  ReviewView.prototype.runAnalysis = function () {
    var self = this;
    var total = this.positions.length;
    var index = 0;
    this.running = true;

    var bar = $(this.id('progress'));
    var label = $(this.id('progress-label'));
    var cancelBtn = $(this.id('cancel'));
    if (cancelBtn) {
      cancelBtn.hidden = false;
      cancelBtn.onclick = function () { self.cancelled = true; };
    }

    function step() {
      if (self.cancelled || index >= total) {
        self.running = false;
        if (cancelBtn) cancelBtn.hidden = true;
        $(self.id('progress-wrap')).hidden = true;
        if (!self.cancelled) self.renderSummary();
        return;
      }
      var fen = self.positions[index];
      var current = index;
      engine.search(fen, { movetime: 260, maxDepth: 12, freshTable: current === 0 })
        .then(function (result) {
          self.analyses[current] = result;
          self.classifyPly(current - 1);
          var pct = Math.round(((current + 1) / total) * 100);
          bar.style.width = pct + '%';
          label.textContent = 'Analysiere Zug ' + Math.min(current + 1, total) + ' von ' + total + ' (' + pct + ' %)';
          if (current === self.ply || current === self.ply - 1) {
            self.renderDetail(new C.Position(self.positions[self.ply]));
          }
          self.renderMoves();
          index++;
          setTimeout(step, 0);
        })
        .catch(function () { index++; setTimeout(step, 0); });
    }
    bar.style.width = '0%';
    step();
  };

  ReviewView.prototype.classifyPly = function (ply) {
    if (ply < 0 || ply >= this.moves.length) return;
    var before = this.analyses[ply];
    var after = this.analyses[ply + 1];
    if (!before || !after) return;
    var scoreBefore = before.best.score;
    var scoreAfter = -after.best.score;
    var posBefore = new C.Position(this.moves[ply].fenBefore);
    var legalCount = posBefore.generateLegalMoves().length;
    var sanList = this.moves.slice(0, ply + 1).map(function (m) { return m.san; });
    this.classifications[ply] = Coach.classify(
      scoreBefore, scoreAfter, this.moves[ply].move === before.best.move,
      legalCount, Coach.isBookMove(sanList)
    );
  };

  ReviewView.prototype.renderSummary = function () {
    var box = $(this.id('summary'));
    if (!box) return;
    box.hidden = false;
    box.innerHTML = '';

    var counts = { w: {}, b: {} };
    var keys = ['best', 'book', 'excellent', 'good', 'inaccuracy', 'mistake', 'blunder', 'forced'];
    ['w', 'b'].forEach(function (c) { keys.forEach(function (k) { counts[c][k] = 0; }); });

    var lossSum = { w: 0, b: 0 }, lossCount = { w: 0, b: 0 };
    for (var ply = 0; ply < this.moves.length; ply++) {
      var cls = this.classifications[ply];
      if (!cls) continue;
      var side = this.moves[ply].color === C.WHITE ? 'w' : 'b';
      counts[side][cls.key]++;
      var before = this.analyses[ply], after = this.analyses[ply + 1];
      if (before && after) {
        var loss = Math.max(0, before.best.score - (-after.best.score));
        lossSum[side] += Math.min(loss, 1000);
        lossCount[side]++;
      }
    }

    el('h3', null, box).textContent = 'Auswertung';
    var table = el('div', 'summary-table', box);
    var head = el('div', 'summary-row summary-head', table);
    el('span', null, head).textContent = '';
    el('span', null, head).textContent = escapeHtml(this.headers.White || 'Weiß');
    el('span', null, head).textContent = escapeHtml(this.headers.Black || 'Schwarz');

    var labels = [
      ['best', 'Beste Züge'], ['book', 'Eröffnungszüge'], ['excellent', 'Sehr gut'],
      ['good', 'Gut'], ['inaccuracy', 'Ungenau'], ['mistake', 'Fehler'], ['blunder', 'Grobe Fehler']
    ];
    labels.forEach(function (pair) {
      var row = el('div', 'summary-row', table);
      el('span', null, row).textContent = pair[1];
      el('span', 'tone-' + Coach.CLASSES[pair[0]].tone, row).textContent = String(counts.w[pair[0]]);
      el('span', 'tone-' + Coach.CLASSES[pair[0]].tone, row).textContent = String(counts.b[pair[0]]);
    });

    var accuracyRow = el('div', 'summary-row summary-total', table);
    el('span', null, accuracyRow).textContent = 'Ø Verlust je Zug';
    ['w', 'b'].forEach(function (side) {
      var avg = lossCount[side] ? Math.round(lossSum[side] / lossCount[side]) : 0;
      el('span', null, accuracyRow).textContent = (avg / 100).toFixed(2).replace('.', ',') + ' B';
    });

    this.renderGraph(box);

    var worst = this.worstMoves();
    if (worst.length) {
      el('h4', null, box).textContent = 'Die teuersten Momente';
      var list = el('ul', 'worst-list', box);
      var self = this;
      worst.forEach(function (item) {
        var li = el('li', null, list);
        var btn = el('button', 'btn btn-small', li);
        btn.type = 'button';
        btn.textContent = 'Zug ' + (Math.floor(item.ply / 2) + 1) +
          (item.ply % 2 === 0 ? '. ' : '... ') + item.san + ' (' + item.cls.label + ')';
        btn.addEventListener('click', function () { self.goTo(item.ply + 1); });
      });
    }
  };

  ReviewView.prototype.worstMoves = function () {
    var out = [];
    for (var ply = 0; ply < this.moves.length; ply++) {
      var cls = this.classifications[ply];
      if (!cls || (cls.key !== 'blunder' && cls.key !== 'mistake')) continue;
      var before = this.analyses[ply], after = this.analyses[ply + 1];
      if (!before || !after) continue;
      out.push({
        ply: ply, san: this.moves[ply].san, cls: cls,
        loss: before.best.score - (-after.best.score)
      });
    }
    return out.sort(function (a, b) { return b.loss - a.loss; }).slice(0, 5);
  };

  /** Verlauf der Gewinnwahrscheinlichkeit aus Sicht von Weiss. */
  ReviewView.prototype.renderGraph = function (box) {
    var points = [];
    for (var i = 0; i < this.analyses.length; i++) {
      var a = this.analyses[i];
      if (!a) { points.push(null); continue; }
      var turn = new C.Position(this.positions[i]).turn;
      var whiteScore = turn === C.WHITE ? a.best.score : -a.best.score;
      points.push(Coach.winPercent(whiteScore));
    }
    var valid = points.filter(function (p) { return p !== null; });
    if (valid.length < 2) return;

    var width = 100, height = 30;
    var path = '';
    var self = this;
    points.forEach(function (p, i) {
      if (p === null) return;
      var x = (i / (points.length - 1)) * width;
      var y = height - (p / 100) * height;
      path += (path ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2) + ' ';
    });

    var wrap = el('div', 'eval-graph', box);
    wrap.innerHTML =
      '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" role="img" ' +
      'aria-label="Verlauf der Gewinnwahrscheinlichkeit für Weiß über die ganze Partie">' +
      '<rect x="0" y="0" width="' + width + '" height="' + (height / 2) + '" class="graph-black"/>' +
      '<rect x="0" y="' + (height / 2) + '" width="' + width + '" height="' + (height / 2) + '" class="graph-white"/>' +
      '<path d="' + path + '" class="graph-line"/>' +
      '<line x1="0" y1="' + (height / 2) + '" x2="' + width + '" y2="' + (height / 2) + '" class="graph-mid"/>' +
      '</svg>';
    wrap.addEventListener('click', function (e) {
      var rect = wrap.getBoundingClientRect();
      var ratio = (e.clientX - rect.left) / rect.width;
      self.goTo(Math.round(ratio * self.moves.length));
    });
  };

  /* ========================== Chess.com-Ansicht ======================== */
  var ccReview = new ReviewView('cc');
  var analyseReview = new ReviewView('an');

  function chesscomInit() {
    var form = $('#cc-form');
    var input = $('#cc-username');
    var saved = store('chesscomUser');
    if (saved) input.value = saved;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      loadChesscom(input.value);
    });

    $('#cc-games').addEventListener('click', function (e) {
      var btn = e.target.closest('.game-item');
      if (btn) openChesscomGame(Number(btn.dataset.index));
    });

    $('#cc-back-to-list').addEventListener('click', function () {
      $('#cc-review').hidden = true;
      $('#cc-list-view').hidden = false;
      ccReview.cancelled = true;
    });

    ccReview.mount();
  }

  var ccState = { games: [], user: '' };

  function loadChesscom(username) {
    var user = Api.normalizeUser(username);
    if (!user) return;
    store('chesscomUser', user);
    ccState.user = user;

    var statusBox = $('#cc-status');
    statusBox.hidden = false;
    statusBox.className = 'status-banner tone-info';
    $('#cc-status-title').textContent = 'Lade Daten …';
    $('#cc-status-text').textContent = 'Profil und Partien von ' + user + ' werden abgerufen.';
    $('#cc-profile').hidden = true;
    $('#cc-games').innerHTML = '';

    Api.profile(user)
      .then(function (profile) {
        renderProfile(profile, user);
        return Promise.all([
          Api.stats(user).catch(function () { return null; }),
          Api.recentGames(user, 30)
        ]);
      })
      .then(function (results) {
        renderRatings(results[0]);
        ccState.games = results[1].games;
        renderGameList(results[1].games);
        if (results[1].skippedVariants) {
          statusBox.hidden = false;
          statusBox.className = 'status-banner tone-meh';
          $('#cc-status-title').textContent = results[1].skippedVariants +
            (results[1].skippedVariants === 1 ? ' Partie ausgelassen' : ' Partien ausgelassen');
          $('#cc-status-text').textContent =
            'Varianten wie Chess960 oder King of the Hill folgen anderen Regeln — die Engine dieser Seite ' +
            'kennt nur Standardschach und würde sie falsch bewerten.';
        } else {
          statusBox.hidden = true;
        }
      })
      .catch(function (err) {
        statusBox.hidden = false;
        statusBox.className = 'status-banner tone-bad';
        if (err.kind === 'notfound') {
          $('#cc-status-title').textContent = 'Benutzer nicht gefunden';
          $('#cc-status-text').textContent = 'Auf Chess.com gibt es kein Konto mit dem Namen „' + user + '“. Tippfehler?';
        } else if (err.kind === 'ratelimit') {
          $('#cc-status-title').textContent = 'Zu viele Anfragen';
          $('#cc-status-text').textContent = 'Chess.com bremst gerade. Warte einen Moment und versuche es erneut.';
        } else {
          $('#cc-status-title').textContent = 'Verbindung fehlgeschlagen';
          $('#cc-status-text').textContent = err.message ||
            'Chess.com ist nicht erreichbar. Du kannst stattdessen unter „Analyse“ eine PGN einfügen.';
        }
      });
  }

  function renderProfile(profile, user) {
    var box = $('#cc-profile');
    box.hidden = false;
    var avatar = $('#cc-avatar');
    if (profile.avatar) { avatar.src = profile.avatar; avatar.hidden = false; }
    else avatar.hidden = true;
    $('#cc-name').textContent = profile.name || profile.username || user;
    $('#cc-handle').textContent = '@' + (profile.username || user);
    var meta = [];
    if (profile.title) meta.push(profile.title);
    if (profile.country) meta.push(String(profile.country).split('/').pop());
    if (profile.followers) meta.push(profile.followers.toLocaleString('de-DE') + ' Follower');
    if (profile.joined) meta.push('Dabei seit ' + new Date(profile.joined * 1000).getFullYear());
    $('#cc-meta').textContent = meta.join(' · ');
    var link = $('#cc-profile-link');
    link.href = profile.url || ('https://www.chess.com/member/' + user);
  }

  function renderRatings(statsData) {
    var box = $('#cc-ratings');
    box.innerHTML = '';
    var list = Api.ratingList(statsData);
    if (!list.length) { box.innerHTML = '<p class="empty-note">Keine Wertungen gefunden.</p>'; return; }
    list.forEach(function (item) {
      var card = el('div', 'rating-card', box);
      el('span', 'rating-label', card).textContent = item.label;
      el('strong', 'rating-value', card).textContent = item.rating;
      if (item.note) el('span', 'rating-note', card).textContent = item.note;
    });
  }

  function renderGameList(games) {
    var box = $('#cc-games');
    box.innerHTML = '';
    if (!games.length) {
      box.innerHTML = '<p class="empty-note">Keine abgeschlossenen Partien in den letzten Monaten gefunden.</p>';
      return;
    }
    games.forEach(function (game, index) {
      var btn = el('button', 'game-item outcome-' + game.outcome, box);
      btn.type = 'button';
      btn.dataset.index = String(index);

      var head = el('div', 'game-head', btn);
      el('span', 'game-result', head).textContent = game.resultLabel;
      el('span', 'game-class', head).textContent = game.timeClassLabel;
      if (game.rated) el('span', 'game-rated', head).textContent = 'Gewertet';

      var body = el('div', 'game-body', btn);
      el('span', 'game-color', body).textContent = game.playerIsWhite ? 'Weiß' : 'Schwarz';
      el('span', 'game-vs', body).textContent = 'gegen ' + game.opponent +
        (game.opponentRating ? ' (' + game.opponentRating + ')' : '');

      var footParts = [];
      if (game.endTime) {
        footParts.push(game.endTime.toLocaleDateString('de-DE', { day: '2-digit', month: 'short', year: 'numeric' }));
      }
      if (game.reason) footParts.push(game.reason);
      el('div', 'game-foot', btn).textContent = footParts.join(' · ');
    });
  }

  function openChesscomGame(index) {
    var game = ccState.games[index];
    if (!game || !game.pgn) return;
    var parsed;
    try { parsed = C.parsePgn(game.pgn); } catch (err) { parsed = null; }
    if (!parsed || !parsed.moves.length) {
      var box = $('#cc-status');
      box.hidden = false;
      box.className = 'status-banner tone-bad';
      $('#cc-status-title').textContent = 'Partie nicht lesbar';
      $('#cc-status-text').textContent = 'Die Notation dieser Partie konnte nicht ausgewertet werden.';
      return;
    }

    // Eine unvollstaendig gelesene Partie darf nicht so aussehen, als waere sie vollstaendig.
    var note = $('#cc-review-note');
    if (parsed.failedAt >= 0) {
      note.hidden = false;
      $('#cc-review-note-text').textContent =
        'Nur die ersten ' + parsed.moves.length + ' Halbzüge konnten gelesen werden — ab „' +
        parsed.tokens[parsed.failedAt] + '“ passt die Notation nicht zu den Standardregeln. ' +
        'Die Auswertung bezieht sich nur auf diesen Teil.';
    } else {
      note.hidden = true;
    }

    $('#cc-list-view').hidden = true;
    $('#cc-review').hidden = false;
    $('#cc-review-title').textContent =
      (parsed.headers.White || '?') + ' vs. ' + (parsed.headers.Black || '?');
    $('#cc-review-sub').textContent = game.timeClassLabel + ' · ' + game.resultLabel +
      (game.reason ? ' (' + game.reason + ')' : '') +
      (game.endTime ? ' · ' + game.endTime.toLocaleDateString('de-DE') : '');
    var link = $('#cc-review-link');
    link.href = game.url || '#';
    link.hidden = !game.url;
    ccReview.load(parsed.game, parsed.headers, game.playerColor);
  }

  /* ============================ Analyse-Tab ============================ */
  function analyseInit() {
    analyseReview.mount();

    $('#an-load-pgn').addEventListener('click', function () {
      var text = $('#an-pgn').value.trim();
      if (!text) return;
      var parsed;
      try { parsed = C.parsePgn(text); } catch (err) { parsed = null; }
      if (!parsed || !parsed.moves.length) {
        setAnalyseNote('Die PGN konnte nicht gelesen werden. Prüfe, ob die Züge vollständig sind.', 'bad');
        return;
      }
      var note = parsed.failedAt >= 0
        ? 'Achtung: ab Zug „' + parsed.tokens[parsed.failedAt] + '“ war die Notation nicht lesbar — ' +
          parsed.moves.length + ' Züge wurden übernommen.'
        : parsed.moves.length + ' Halbzüge geladen. Die Analyse läuft.';
      setAnalyseNote(note, parsed.failedAt >= 0 ? 'meh' : 'info');
      analyseReview.load(parsed.game, parsed.headers, 'w');
    });

    $('#an-load-fen').addEventListener('click', function () {
      var fen = $('#an-fen').value.trim();
      if (!fen) return;
      var game;
      try { game = new C.Game(fen); } catch (err) {
        setAnalyseNote('Diese FEN ist nicht gültig.', 'bad');
        return;
      }
      setAnalyseNote('Stellung geladen.', 'info');
      analyseReview.load(game, { White: 'Weiß', Black: 'Schwarz' },
        game.turn() === C.WHITE ? 'w' : 'b');
    });

    $('#an-load-current').addEventListener('click', function () {
      if (!play.game.history.length) {
        setAnalyseNote('Du hast noch keine Partie gespielt.', 'meh');
        return;
      }
      var replay = new C.Game(play.game.startFen);
      play.game.history.forEach(function (h) { replay.move(h.move); });
      setAnalyseNote('Deine laufende Übungspartie wird analysiert.', 'info');
      analyseReview.load(replay, { White: 'Weiß', Black: 'Schwarz' }, play.playerColor);
      switchTab('analyse');
    });
  }

  function setAnalyseNote(text, tone) {
    var box = $('#an-note');
    box.hidden = false;
    box.className = 'status-banner tone-' + (tone || 'info');
    $('#an-note-text').textContent = text;
  }

  /* ============================== Tabs ================================ */
  function switchTab(name) {
    $$('.tab-button').forEach(function (btn) {
      var active = btn.dataset.tab === name;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    $$('.tab-panel').forEach(function (panel) {
      panel.hidden = panel.dataset.tab !== name;
    });
    store('tab', name);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function tabsInit() {
    $$('.tab-button').forEach(function (btn) {
      btn.addEventListener('click', function () { switchTab(btn.dataset.tab); });
    });
    switchTab(store('tab') || 'spielen');
  }

  /* ============================== Start =============================== */
  function init() {
    tabsInit();
    playInit();
    chesscomInit();
    analyseInit();

    $('#year').textContent = String(new Date().getFullYear());

    $$('[data-goto-tab]').forEach(function (node) {
      node.addEventListener('click', function (e) {
        e.preventDefault();
        switchTab(node.dataset.gotoTab);
      });
    });

    $('#btn-back-live').addEventListener('click', function () {
      play.viewPly = null;
      play.board.setPosition(play.game.fen(), { instant: true });
      $('#btn-back-live').hidden = true;
      refreshPlayView();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());
