/*
 * pieces.js — eigene SVG-Figuren (viewBox 45x45).
 * Farben kommen ueber CSS-Variablen, damit ein Satz fuer beide Seiten reicht.
 */
(function (global) {
  'use strict';

  var BODY = 'fill="var(--piece-fill)" stroke="var(--piece-edge)" stroke-width="1.4" stroke-linejoin="round"';
  var DETAIL = 'fill="none" stroke="var(--piece-edge)" stroke-width="1.9" stroke-linecap="round"';

  var SHAPES = {
    p:
      '<circle cx="22.5" cy="13.8" r="5.7" ' + BODY + '/>' +
      '<path d="M22.5 18.6c4.7 0 7.9 3.5 7.9 7.6 0 3.3-2 5.8-4.3 7.3h-7.2c-2.3-1.5-4.3-4-4.3-7.3 0-4.1 3.2-7.6 7.9-7.6z" ' + BODY + '/>' +
      '<path d="M14.2 32.6h16.6v3.1H14.2z" ' + BODY + '/>' +
      '<path d="M11.6 35.4h21.8v3.9H11.6z" ' + BODY + '/>',

    r:
      '<path d="M9.5 11h5v3.2h5.5V11h5v3.2h5.5V11h5v8.5l-3 2.5v9l3 2.5V38h-26v-4.5l3-2.5v-9l-3-2.5z" ' + BODY + '/>' +
      '<path d="M12.5 22h20M12.5 31h20" ' + DETAIL + ' stroke-width="1.3"/>' +
      '<path d="M8.5 38h28v3.4h-28z" ' + BODY + '/>',

    b:
      '<path d="M22.5 7.4c1.6 0 2.9 1.3 2.9 2.9 0 .9-.4 1.7-1.1 2.2 4.1 2.9 7.4 7.2 7.4 12.1 0 3.8-2.1 6.4-4.4 7.9H17.7c-2.3-1.5-4.4-4.1-4.4-7.9 0-4.9 3.3-9.2 7.4-12.1-.7-.5-1.1-1.3-1.1-2.2 0-1.6 1.3-2.9 2.9-2.9z" ' + BODY + '/>' +
      // Diagonaler Schlitz — so bleibt der Laeufer klar vom Koenig unterscheidbar.
      '<path d="M19.4 22.6L25.6 16.4" ' + DETAIL + '/>' +
      '<path d="M13.7 31.4h17.6v3.1H13.7z" ' + BODY + '/>' +
      '<path d="M10.8 34.2h23.4v4.1H10.8z" ' + BODY + '/>',

    n:
      '<path d="M13.5 38c0-6.5 1.6-10.4 5.2-13.6 2.2-2 3.7-3.6 4.4-5.6l-5.2 3.7-3.9-1.1-1.4-3.7 2.2-3.1 3-2.2 1.3-3.6 2.6 2 2.1-3.2 1.1 3.6c6 1.4 10 6.2 10.4 12.4.3 3.9.3 7.5.3 14.4z" ' + BODY + '/>' +
      '<circle cx="19.2" cy="15.6" r="1.5" fill="var(--piece-edge)"/>' +
      '<path d="M26.5 15.5c2.6 1.6 4.2 4.3 4.6 8" ' + DETAIL + ' stroke-width="1.3"/>' +
      '<path d="M10.5 38h24v3.4h-24z" ' + BODY + '/>',

    q:
      '<path d="M8.5 15.5L12.5 30h20l4-14.5L32 20l-4-9-2.7 8L22.5 8.8 19.7 19l-2.7-8-4 9z" ' + BODY + '/>' +
      '<circle cx="8.5" cy="14.2" r="2.2" ' + BODY + '/>' +
      '<circle cx="17" cy="9.8" r="2.2" ' + BODY + '/>' +
      '<circle cx="22.5" cy="7.4" r="2.4" ' + BODY + '/>' +
      '<circle cx="28" cy="9.8" r="2.2" ' + BODY + '/>' +
      '<circle cx="36.5" cy="14.2" r="2.2" ' + BODY + '/>' +
      '<path d="M11.8 31h21.4v3.1H11.8z" ' + BODY + '/>' +
      '<path d="M9.5 33.8h26v4.2h-26z" ' + BODY + '/>' +
      '<path d="M8.5 38h28v3.4h-28z" ' + BODY + '/>',

    k:
      '<path d="M22.5 4v9.4M18.3 7.9h8.4" ' + DETAIL + ' stroke-width="2.7"/>' +
      '<path d="M22.5 13.4c-5.7 0-10.4 3.8-11.9 8.9L12.4 31h20.2l1.8-8.7c-1.5-5.1-6.2-8.9-11.9-8.9z" ' + BODY + '/>' +
      '<path d="M12.9 26.6h19.2" ' + DETAIL + ' stroke-width="1.5"/>' +
      '<path d="M11.8 31h21.4v3.1H11.8z" ' + BODY + '/>' +
      '<path d="M9.5 33.8h26v4.2h-26z" ' + BODY + '/>' +
      '<path d="M8.5 38h28v3.4h-28z" ' + BODY + '/>'
  };

  var NAMES = {
    p: 'Bauer', n: 'Springer', b: 'Laeufer', r: 'Turm', q: 'Dame', k: 'Koenig'
  };
  var NAMES_DE = {
    p: 'Bauer', n: 'Springer', b: 'Läufer', r: 'Turm', q: 'Dame', k: 'König'
  };

  /** SVG-Markup fuer eine Figur. type: 'p'..'k', color: 'w' | 'b' */
  function svg(type, color) {
    var t = String(type).toLowerCase();
    if (!SHAPES[t]) return '';
    return '<svg class="piece-svg ' + (color === 'w' ? 'piece-white' : 'piece-black') + '" ' +
      'viewBox="0 0 45 45" aria-hidden="true" focusable="false">' + SHAPES[t] + '</svg>';
  }

  global.ChessPieces = { svg: svg, NAMES: NAMES, NAMES_DE: NAMES_DE, SHAPES: SHAPES };
}(typeof self !== 'undefined' ? self : this));
