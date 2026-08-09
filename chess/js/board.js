/*
 * board.js — interaktives Schachbrett (DOM + SVG-Overlay).
 * Unabhaengig von der Engine; kennt nur Feldindizes im 0x88-Format.
 */
(function (global) {
  'use strict';

  var C = global.ChessCore;
  var P = global.ChessPieces;
  var FILES = 'abcdefgh';

  function el(tag, cls, parent) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (parent) parent.appendChild(node);
    return node;
  }

  function ChessBoard(root, options) {
    var opts = options || {};
    this.root = root;
    this.orientation = opts.orientation === 'black' ? 'black' : 'white';
    this.interactive = opts.interactive !== false;
    this.onMove = opts.onMove || function () { };
    this.onSelectionChange = opts.onSelectionChange || function () { };
    this.showCoordinates = opts.showCoordinates !== false;

    this.legalMoves = [];
    this.legalByFrom = {};
    this.selected = -1;
    this.pieceEls = {};
    this.dragging = null;
    this.pendingPromotion = null;
    this.highlights = {};

    this._build();
    this._bindEvents();
  }

  ChessBoard.prototype._build = function () {
    this.root.classList.add('cb-root');
    this.root.innerHTML = '';

    this.squaresLayer = el('div', 'cb-squares', this.root);
    this.markLayer = el('div', 'cb-marks', this.root);
    this.piecesLayer = el('div', 'cb-pieces', this.root);

    this.arrowSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    this.arrowSvg.setAttribute('class', 'cb-arrows');
    this.arrowSvg.setAttribute('viewBox', '0 0 8 8');
    this.arrowSvg.setAttribute('aria-hidden', 'true');
    this.root.appendChild(this.arrowSvg);

    this.squares = {};
    for (var row = 0; row < 8; row++) {
      for (var col = 0; col < 8; col++) {
        var sq = row * 16 + col;
        var node = el('div', 'cb-square ' + (((row + col) % 2 === 0) ? 'cb-light' : 'cb-dark'), this.squaresLayer);
        node.dataset.square = String(sq);
        node.setAttribute('role', 'gridcell');
        this.squares[sq] = node;
      }
    }
    this._layoutSquares();

    this.promotionLayer = el('div', 'cb-promotion hidden', this.root);
  };

  /** Reihenfolge der Feld-Divs an die Brettdrehung anpassen. */
  ChessBoard.prototype._layoutSquares = function () {
    var flipped = this.orientation === 'black';
    var frag = document.createDocumentFragment();
    for (var i = 0; i < 64; i++) {
      var visRow = Math.floor(i / 8), visCol = i % 8;
      var row = flipped ? 7 - visRow : visRow;
      var col = flipped ? 7 - visCol : visCol;
      var sq = row * 16 + col;
      var node = this.squares[sq];
      node.innerHTML = '';
      if (this.showCoordinates) {
        if (visCol === 0) {
          var rank = el('span', 'cb-coord cb-coord-rank', node);
          rank.textContent = String(8 - row);
        }
        if (visRow === 7) {
          var file = el('span', 'cb-coord cb-coord-file', node);
          file.textContent = FILES[col];
        }
      }
      node.setAttribute('aria-label', FILES[col] + (8 - row));
      frag.appendChild(node);
    }
    this.squaresLayer.appendChild(frag);
    this._repositionAll();
  };

  ChessBoard.prototype.setOrientation = function (orientation) {
    var next = orientation === 'black' ? 'black' : 'white';
    if (next === this.orientation) return;
    this.orientation = next;
    this._layoutSquares();
    this.renderHighlights();
    this.renderArrows();
  };

  ChessBoard.prototype.flip = function () {
    this.setOrientation(this.orientation === 'white' ? 'black' : 'white');
  };

  /** Bildschirmposition (Spalte/Zeile 0-7) eines Feldes. */
  ChessBoard.prototype.visualOf = function (sq) {
    var row = sq >> 4, col = sq & 7;
    return this.orientation === 'black'
      ? { col: 7 - col, row: 7 - row }
      : { col: col, row: row };
  };

  ChessBoard.prototype.squareAtPoint = function (clientX, clientY) {
    var rect = this.squaresLayer.getBoundingClientRect();
    if (!rect.width) return -1;
    var col = Math.floor((clientX - rect.left) / (rect.width / 8));
    var row = Math.floor((clientY - rect.top) / (rect.height / 8));
    if (col < 0 || col > 7 || row < 0 || row > 7) return -1;
    var realCol = this.orientation === 'black' ? 7 - col : col;
    var realRow = this.orientation === 'black' ? 7 - row : row;
    return realRow * 16 + realCol;
  };

  /* --------------------------- Figuren ------------------------------- */
  function parseFenBoard(fen) {
    var map = {};
    var rows = String(fen).split(' ')[0].split('/');
    for (var r = 0; r < 8; r++) {
      var file = 0;
      for (var i = 0; i < rows[r].length; i++) {
        var ch = rows[r][i];
        if (ch >= '1' && ch <= '8') { file += parseInt(ch, 10); continue; }
        map[r * 16 + file] = (ch === ch.toUpperCase() ? 'w' : 'b') + ch.toLowerCase();
        file++;
      }
    }
    return map;
  }

  ChessBoard.prototype._makePiece = function (code, sq) {
    var node = el('div', 'cb-piece', this.piecesLayer);
    node.dataset.piece = code;
    node.dataset.square = String(sq);
    node.innerHTML = P.svg(code[1], code[0]);
    this._place(node, sq);
    return node;
  };

  ChessBoard.prototype._place = function (node, sq) {
    var v = this.visualOf(sq);
    node.style.transform = 'translate(' + (v.col * 100) + '%, ' + (v.row * 100) + '%)';
    node.dataset.square = String(sq);
  };

  ChessBoard.prototype._repositionAll = function () {
    for (var sq in this.pieceEls) {
      if (this.pieceEls[sq]) this._place(this.pieceEls[sq], Number(sq));
    }
  };

  /**
   * Stellung setzen.
   * opts.move = { from, to } sorgt fuer eine fluessige Animation.
   */
  ChessBoard.prototype.setPosition = function (fen, opts) {
    var options = opts || {};
    var target = parseFenBoard(fen);
    var self = this;

    if (options.move && this.pieceEls[options.move.from]) {
      var from = options.move.from, to = options.move.to;
      var mover = this.pieceEls[options.move.from];
      var captured = this.pieceEls[to];
      if (captured) { captured.classList.add('cb-captured'); this._fadeOut(captured); }
      delete this.pieceEls[from];
      this.pieceEls[to] = mover;
      mover.classList.add('cb-moving');
      this._place(mover, to);
      global.setTimeout(function () { mover.classList.remove('cb-moving'); self._sync(target); }, 190);
      // Rochade-Turm und en-passant-Bauer sofort nachziehen
      this._syncExtras(target, from, to);
      return;
    }
    this._sync(target, options.instant);
  };

  ChessBoard.prototype._syncExtras = function (target, from, to) {
    // Alles ausser dem gerade animierten Feld angleichen (ohne Animation).
    for (var sq in this.pieceEls) {
      var n = Number(sq);
      if (n === to) continue;
      if (!target[n] || target[n] !== this.pieceEls[sq].dataset.piece) {
        this._fadeOut(this.pieceEls[sq]);
        delete this.pieceEls[sq];
      }
    }
    for (var s in target) {
      var ns = Number(s);
      if (ns === to) continue;
      if (!this.pieceEls[ns]) this.pieceEls[ns] = this._makePiece(target[s], ns);
    }
  };

  ChessBoard.prototype._sync = function (target, instant) {
    for (var sq in this.pieceEls) {
      var n = Number(sq);
      if (!target[n] || target[n] !== this.pieceEls[sq].dataset.piece) {
        if (instant) { this.pieceEls[sq].remove(); } else { this._fadeOut(this.pieceEls[sq]); }
        delete this.pieceEls[sq];
      }
    }
    for (var s in target) {
      var ns = Number(s);
      if (!this.pieceEls[ns]) this.pieceEls[ns] = this._makePiece(target[s], ns);
      else this._place(this.pieceEls[ns], ns);
    }
  };

  ChessBoard.prototype._fadeOut = function (node) {
    node.classList.add('cb-fading');
    global.setTimeout(function () { if (node.parentNode) node.remove(); }, 180);
  };

  /* -------------------------- Markierungen --------------------------- */
  ChessBoard.prototype.setLegalMoves = function (moves) {
    this.legalMoves = moves || [];
    this.legalByFrom = {};
    for (var i = 0; i < this.legalMoves.length; i++) {
      var m = this.legalMoves[i];
      (this.legalByFrom[m.from] || (this.legalByFrom[m.from] = [])).push(m);
    }
    if (this.selected >= 0 && !this.legalByFrom[this.selected]) this.clearSelection();
    else this.renderHighlights();
  };

  ChessBoard.prototype.setHighlights = function (h) {
    this.highlights = h || {};
    this.renderHighlights();
  };

  ChessBoard.prototype.clearSelection = function () {
    this.selected = -1;
    this.renderHighlights();
    this.onSelectionChange(-1);
  };

  ChessBoard.prototype.renderHighlights = function () {
    this.markLayer.innerHTML = '';
    var h = this.highlights || {};
    var self = this;

    function mark(sq, cls) {
      if (sq === undefined || sq === null || sq < 0) return;
      var node = el('div', 'cb-mark ' + cls, self.markLayer);
      var v = self.visualOf(sq);
      node.style.transform = 'translate(' + (v.col * 100) + '%, ' + (v.row * 100) + '%)';
      return node;
    }

    if (h.lastMove) { mark(h.lastMove[0], 'cb-mark-last'); mark(h.lastMove[1], 'cb-mark-last'); }
    if (h.hint) { mark(h.hint[0], 'cb-mark-hint'); mark(h.hint[1], 'cb-mark-hint'); }
    (h.danger || []).forEach(function (sq) { mark(sq, 'cb-mark-danger'); });
    if (h.check >= 0 && h.check !== undefined && h.check !== null) mark(h.check, 'cb-mark-check');
    if (this.selected >= 0) mark(this.selected, 'cb-mark-selected');

    if (this.selected >= 0) {
      var targets = this.legalByFrom[this.selected] || [];
      var seen = {};
      for (var i = 0; i < targets.length; i++) {
        var to = targets[i].to;
        if (seen[to]) continue;
        seen[to] = true;
        mark(to, this.pieceEls[to] ? 'cb-mark-capture' : 'cb-mark-target');
      }
    }
  };

  /* ----------------------------- Pfeile ------------------------------ */
  ChessBoard.prototype.setArrows = function (arrows) {
    this.arrows = arrows || [];
    this.renderArrows();
  };

  ChessBoard.prototype.renderArrows = function () {
    var svg = this.arrowSvg;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var list = this.arrows || [];
    if (!list.length) return;

    var defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    svg.appendChild(defs);

    for (var i = 0; i < list.length; i++) {
      var a = list[i];
      var f = this.visualOf(a.from), t = this.visualOf(a.to);
      var x1 = f.col + 0.5, y1 = f.row + 0.5;
      var x2 = t.col + 0.5, y2 = t.row + 0.5;
      var dx = x2 - x1, dy = y2 - y1;
      var len = Math.sqrt(dx * dx + dy * dy) || 1;
      var head = 0.30;
      // Linie vor der Spitze enden lassen
      var ex = x2 - (dx / len) * head, ey = y2 - (dy / len) * head;

      var markerId = 'cb-arrowhead-' + i;
      var marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
      marker.setAttribute('id', markerId);
      marker.setAttribute('viewBox', '0 0 10 10');
      marker.setAttribute('refX', '4');
      marker.setAttribute('refY', '5');
      marker.setAttribute('markerWidth', '3.2');
      marker.setAttribute('markerHeight', '3.2');
      marker.setAttribute('orient', 'auto-start-reverse');
      var tip = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      tip.setAttribute('d', 'M0 1L8 5L0 9z');
      // currentColor wuerde hier gegen das <svg> aufgeloest, nicht gegen die Linie.
      tip.setAttribute('fill', a.color || (a.className === 'cb-arrow-warn' ? '#ff6482' : '#2ee08f'));
      marker.appendChild(tip);
      defs.appendChild(marker);

      var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x1); line.setAttribute('y1', y1);
      line.setAttribute('x2', ex); line.setAttribute('y2', ey);
      line.setAttribute('class', 'cb-arrow ' + (a.className || 'cb-arrow-best'));
      line.setAttribute('marker-end', 'url(#' + markerId + ')');
      svg.appendChild(line);
    }
  };

  /* -------------------------- Interaktion ---------------------------- */
  ChessBoard.prototype._bindEvents = function () {
    var self = this;

    this.root.addEventListener('pointerdown', function (e) {
      if (!self.interactive || self.pendingPromotion) return;
      var sq = self.squareAtPoint(e.clientX, e.clientY);
      if (sq < 0) return;

      // Zug abschliessen, wenn bereits ein Feld gewaehlt ist
      if (self.selected >= 0 && self.selected !== sq) {
        var candidates = (self.legalByFrom[self.selected] || []).filter(function (m) { return m.to === sq; });
        if (candidates.length) { e.preventDefault(); self._commit(candidates); return; }
      }

      if (!self.legalByFrom[sq]) {
        if (self.selected >= 0) self.clearSelection();
        return;
      }

      e.preventDefault();
      self.selected = sq;
      self.renderHighlights();
      self.onSelectionChange(sq);

      var node = self.pieceEls[sq];
      if (!node) return;
      var rect = self.squaresLayer.getBoundingClientRect();
      self.dragging = {
        from: sq, node: node, startX: e.clientX, startY: e.clientY,
        size: rect.width / 8, moved: false, pointerId: e.pointerId
      };
      node.classList.add('cb-dragging');
      try { self.root.setPointerCapture(e.pointerId); } catch (err) { /* nicht kritisch */ }
    });

    this.root.addEventListener('pointermove', function (e) {
      var d = self.dragging;
      if (!d || e.pointerId !== d.pointerId) return;
      var dx = e.clientX - d.startX, dy = e.clientY - d.startY;
      if (!d.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
      d.moved = true;
      var v = self.visualOf(d.from);
      d.node.style.transform =
        'translate(' + (v.col * 100) + '%, ' + (v.row * 100) + '%) translate(' + dx + 'px, ' + dy + 'px)';
      var over = self.squareAtPoint(e.clientX, e.clientY);
      if (over !== d.hover) {
        d.hover = over;
        self.markLayer.querySelectorAll('.cb-hover').forEach(function (n) { n.classList.remove('cb-hover'); });
        if (over >= 0 && (self.legalByFrom[d.from] || []).some(function (m) { return m.to === over; })) {
          var v2 = self.visualOf(over);
          var hover = el('div', 'cb-mark cb-mark-hover cb-hover', self.markLayer);
          hover.style.transform = 'translate(' + (v2.col * 100) + '%, ' + (v2.row * 100) + '%)';
        }
      }
    });

    function endDrag(e) {
      var d = self.dragging;
      if (!d || (e.pointerId !== undefined && e.pointerId !== d.pointerId)) return;
      self.dragging = null;
      d.node.classList.remove('cb-dragging');
      self._place(d.node, d.from);
      self.markLayer.querySelectorAll('.cb-hover').forEach(function (n) { n.remove(); });
      try { self.root.releasePointerCapture(d.pointerId); } catch (err) { /* egal */ }
      if (!d.moved) return;                       // reiner Klick -> Auswahl bleibt

      var to = self.squareAtPoint(e.clientX, e.clientY);
      var candidates = (self.legalByFrom[d.from] || []).filter(function (m) { return m.to === to; });
      if (candidates.length) self._commit(candidates);
      else self.clearSelection();
    }

    this.root.addEventListener('pointerup', endDrag);
    this.root.addEventListener('pointercancel', endDrag);
    this.root.addEventListener('contextmenu', function (e) {
      if (self.selected >= 0) { e.preventDefault(); self.clearSelection(); }
    });
  };

  ChessBoard.prototype._commit = function (candidates) {
    var self = this;
    var needsPromotion = candidates.length > 1 && candidates.some(function (m) { return m.promotion; });
    if (!needsPromotion) {
      var move = candidates[0];
      this.clearSelection();
      this.onMove(move);
      return;
    }
    this._askPromotion(candidates[0].to, candidates[0].color, function (piece) {
      var chosen = candidates.filter(function (m) { return m.promotion === piece; })[0] || candidates[0];
      self.clearSelection();
      self.onMove(chosen);
    });
  };

  ChessBoard.prototype._askPromotion = function (sq, color, callback) {
    var self = this;
    var layer = this.promotionLayer;
    layer.innerHTML = '';
    layer.classList.remove('hidden');
    this.pendingPromotion = true;

    var v = this.visualOf(sq);
    var picker = el('div', 'cb-promotion-picker', layer);
    picker.style.left = (v.col * 12.5) + '%';
    var fromTop = v.row <= 3;
    picker.style[fromTop ? 'top' : 'bottom'] = '0';

    var order = fromTop ? ['q', 'n', 'r', 'b'] : ['b', 'r', 'n', 'q'];
    order.forEach(function (type) {
      var btn = el('button', 'cb-promotion-option', picker);
      btn.type = 'button';
      btn.title = P.NAMES_DE[type];
      btn.setAttribute('aria-label', 'Umwandeln in ' + P.NAMES_DE[type]);
      btn.innerHTML = P.svg(type, color === 1 ? 'b' : 'w');
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        close();
        callback(type);
      });
    });

    function close() {
      layer.classList.add('hidden');
      layer.innerHTML = '';
      self.pendingPromotion = null;
    }
    layer.addEventListener('pointerdown', function (e) {
      if (e.target === layer) { close(); self.clearSelection(); }
    });
  };

  ChessBoard.prototype.setInteractive = function (value) {
    this.interactive = !!value;
    this.root.classList.toggle('cb-locked', !value);
    if (!value) this.clearSelection();
  };

  global.ChessBoard = ChessBoard;
}(typeof self !== 'undefined' ? self : this));
