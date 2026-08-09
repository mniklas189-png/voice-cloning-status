/*
 * chesscom.js — Zugriff auf die oeffentliche Chess.com-API (Published-Data API).
 *
 * Diese API ist bewusst NUR lesend: Profil, Wertungen und gespielte Partien.
 * Chess.com bietet keine oeffentliche Schnittstelle zum Spielen an, und
 * Engine-Hilfe waehrend laufender Partien verstoesst gegen die Fair-Play-Regeln.
 * Deshalb liest diese Datei ausschliesslich abgeschlossene Partien.
 */
(function (global) {
  'use strict';

  var BASE = 'https://api.chess.com/pub';
  var cache = new Map();

  function cacheKey(url) { return 'cc:' + url; }

  function readCache(url, maxAgeMs) {
    var mem = cache.get(url);
    if (mem && Date.now() - mem.time < maxAgeMs) return mem.data;
    try {
      var raw = global.sessionStorage && global.sessionStorage.getItem(cacheKey(url));
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (Date.now() - parsed.time > maxAgeMs) return null;
      cache.set(url, parsed);
      return parsed.data;
    } catch (err) {
      return null;
    }
  }

  function writeCache(url, data) {
    var entry = { time: Date.now(), data: data };
    cache.set(url, entry);
    try {
      if (global.sessionStorage) global.sessionStorage.setItem(cacheKey(url), JSON.stringify(entry));
    } catch (err) { /* Speicher voll oder gesperrt — nicht kritisch */ }
  }

  function ApiError(message, kind, status) {
    var e = new Error(message);
    e.kind = kind;
    e.status = status || 0;
    return e;
  }

  function fetchJson(url, maxAgeMs) {
    var cached = readCache(url, maxAgeMs === undefined ? 300000 : maxAgeMs);
    if (cached) return Promise.resolve(cached);

    return global.fetch(url, { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (response.status === 404) throw ApiError('Nicht gefunden', 'notfound', 404);
        if (response.status === 429) throw ApiError('Zu viele Anfragen — bitte kurz warten', 'ratelimit', 429);
        if (!response.ok) throw ApiError('Chess.com antwortet mit Status ' + response.status, 'http', response.status);
        return response.json();
      })
      .then(function (data) { writeCache(url, data); return data; })
      .catch(function (err) {
        if (err && err.kind) throw err;
        throw ApiError(
          'Chess.com ist gerade nicht erreichbar. Das kann an der Internetverbindung liegen ' +
          'oder daran, dass der Browser die Anfrage blockiert.', 'network', 0);
      });
  }

  function normalizeUser(name) {
    return String(name || '').trim().toLowerCase().replace(/^@/, '');
  }

  function profile(username) {
    var u = normalizeUser(username);
    if (!u) return Promise.reject(ApiError('Bitte einen Benutzernamen eingeben', 'input'));
    return fetchJson(BASE + '/player/' + encodeURIComponent(u), 600000);
  }

  function stats(username) {
    return fetchJson(BASE + '/player/' + encodeURIComponent(normalizeUser(username)) + '/stats', 300000);
  }

  function archives(username) {
    return fetchJson(BASE + '/player/' + encodeURIComponent(normalizeUser(username)) + '/games/archives', 300000)
      .then(function (data) { return (data && data.archives) || []; });
  }

  /**
   * Laedt die zuletzt beendeten Partien (neueste zuerst).
   * Geht die Monatsarchive von hinten durch, bis genug Partien beisammen sind.
   *
   * Varianten (Chess960, King of the Hill, Bughouse …) werden ausgelassen:
   * die Engine dieser Seite kennt nur die Standardregeln, eine Analyse waere
   * dort schlicht falsch. Ihre Anzahl wird zurueckgemeldet.
   */
  function recentGames(username, limit) {
    var want = limit || 20;
    var user = normalizeUser(username);
    return archives(user).then(function (list) {
      if (!list.length) return { games: [], skippedVariants: 0 };
      var months = list.slice(-6).reverse();
      var collected = [];
      var skipped = 0;

      function next(index) {
        if (index >= months.length || collected.length >= want) {
          return { games: collected.slice(0, want), skippedVariants: skipped };
        }
        return fetchJson(months[index], 120000).then(function (data) {
          var games = (data && data.games) || [];
          for (var i = games.length - 1; i >= 0; i--) {
            if ((games[i].rules || 'chess') !== 'chess') { skipped++; continue; }
            collected.push(toGame(games[i], user));
          }
          return next(index + 1);
        }).catch(function () { return next(index + 1); });
      }
      return next(0);
    });
  }

  var TIME_CLASS_DE = {
    bullet: 'Bullet', blitz: 'Blitz', rapid: 'Schnellschach', daily: 'Fernschach'
  };

  function toGame(raw, user) {
    var whiteName = (raw.white && raw.white.username) || '?';
    var blackName = (raw.black && raw.black.username) || '?';
    var playerIsWhite = whiteName.toLowerCase() === user;
    var me = playerIsWhite ? raw.white : raw.black;
    var opponent = playerIsWhite ? raw.black : raw.white;

    var outcome = 'draw';
    if (me && me.result === 'win') outcome = 'win';
    else if (me && ['agreed', 'repetition', 'stalemate', 'insufficient', '50move', 'timevsinsufficient']
      .indexOf(me.result) < 0) outcome = 'loss';

    return {
      url: raw.url,
      pgn: raw.pgn || '',
      fen: raw.fen,
      rules: raw.rules || 'chess',
      timeClass: raw.time_class,
      timeClassLabel: TIME_CLASS_DE[raw.time_class] || raw.time_class || '—',
      timeControl: raw.time_control,
      rated: !!raw.rated,
      endTime: raw.end_time ? new Date(raw.end_time * 1000) : null,
      playerIsWhite: playerIsWhite,
      playerColor: playerIsWhite ? 'w' : 'b',
      playerRating: me && me.rating,
      opponent: opponent ? opponent.username : '?',
      opponentRating: opponent && opponent.rating,
      resultRaw: me && me.result,
      outcome: outcome,
      resultLabel: outcome === 'win' ? 'Sieg' : outcome === 'loss' ? 'Niederlage' : 'Remis',
      // Bei einem Sieg sagt der eigene Status nur "Gewonnen" — interessant ist,
      // woran der Gegner gescheitert ist (aufgegeben, Zeit, matt).
      reason: RESULT_DE[(outcome === 'win' ? (opponent && opponent.result) : (me && me.result)) || ''] || ''
    };
  }

  var RESULT_DE = {
    win: 'Gewonnen',
    checkmated: 'Schachmatt',
    agreed: 'Remis vereinbart',
    repetition: 'Stellungswiederholung',
    timeout: 'Zeit überschritten',
    resigned: 'Aufgegeben',
    stalemate: 'Patt',
    lose: 'Verloren',
    insufficient: 'Ungenügendes Material',
    '50move': '50-Züge-Regel',
    abandoned: 'Partie verlassen',
    kingofthehill: 'King of the Hill',
    threecheck: 'Drei Schachs',
    timevsinsufficient: 'Zeit gegen ungenügendes Material',
    bughousepartnerlose: 'Partner verloren'
  };

  /** Wertungen aus dem /stats-Endpunkt in eine anzeigbare Liste bringen. */
  function ratingList(statsData) {
    if (!statsData) return [];
    var map = [
      ['chess_rapid', 'Schnellschach'],
      ['chess_blitz', 'Blitz'],
      ['chess_bullet', 'Bullet'],
      ['chess_daily', 'Fernschach'],
      ['tactics', 'Taktik'],
      ['puzzle_rush', 'Puzzle Rush']
    ];
    var out = [];
    map.forEach(function (pair) {
      var entry = statsData[pair[0]];
      if (!entry) return;
      if (pair[0] === 'tactics') {
        if (entry.highest && entry.highest.rating) out.push({ label: pair[1], rating: entry.highest.rating, note: 'Bestwert' });
        return;
      }
      if (pair[0] === 'puzzle_rush') {
        if (entry.best && entry.best.score) out.push({ label: pair[1], rating: entry.best.score, note: 'Bestleistung' });
        return;
      }
      if (!entry.last || !entry.last.rating) return;
      var record = entry.record || {};
      var total = (record.win || 0) + (record.loss || 0) + (record.draw || 0);
      out.push({
        label: pair[1],
        rating: entry.last.rating,
        note: total ? record.win + 'S / ' + record.loss + 'N / ' + record.draw + 'R' : ''
      });
    });
    return out;
  }

  global.ChessCom = {
    profile: profile,
    stats: stats,
    archives: archives,
    recentGames: recentGames,
    ratingList: ratingList,
    normalizeUser: normalizeUser,
    RESULT_DE: RESULT_DE
  };
}(typeof self !== 'undefined' ? self : this));
