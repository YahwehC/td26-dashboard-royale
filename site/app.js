/* ==========================================================================
   The Gilded Ace — static dashboard application
   Vanilla ES2020, no build step. Plotly is the only external library.

   Sections
     1. State, constants and small utilities
     2. Data loading and row metadata
     3. Shared computations (per-machine aggregates, IPF, luck, attribution)
     4. Theme tokens, Plotly helpers, chart/table card factories
     5. Global filter bar, hash routing and shell
     6. Tab renderers (verdict, machines, demand, downtime, players, comps,
        plan, model, evidence)
     7. Boot and window.__selftest()
   ========================================================================== */

'use strict';

/* -------------------------------------------------------------------------
   1. State, constants and small utilities
   ------------------------------------------------------------------------- */

const TABS = ['verdict', 'machines', 'demand', 'downtime', 'players', 'comps', 'plan', 'model', 'evidence'];
const TAB_LABELS = {
  verdict: 'Verdict', machines: 'Machines', demand: 'Demand', downtime: 'Downtime',
  players: 'Players', comps: 'Comps', plan: 'Plan', model: 'Model', evidence: 'Evidence'
};

const MIN_DATE = '2025-01-01';
const MAX_DATE = '2025-06-30';
const DEFAULT_STATE = {
  tab: 'verdict',
  from: MIN_DATE,
  to: MAX_DATE,
  zone: 'all',
  bank: 'all'
};

const PRESETS = {
  full: { from: '2025-01-01', to: '2025-06-30' },
  q1: { from: '2025-01-01', to: '2025-03-31' },
  q2: { from: '2025-04-01', to: '2025-06-30' },
  train: { from: '2025-01-01', to: '2025-04-30' },
  holdout: { from: '2025-05-01', to: '2025-06-30' }
};

const state = Object.assign({}, DEFAULT_STATE, {
  mSearch: '',
  mSort: { key: 'hw', dir: 'asc' },
  pTier: 'all',
  pAge: 'all',
  pRegion: 'all',
  trafficZones: null
});

let DATA = null;
let dataPromise = null;
const computedCache = { key: null, res: null };

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function append(parent, ...children) {
  for (const child of children) if (child) parent.appendChild(child);
  return parent;
}

function sum(arr) {
  let s = 0;
  for (let i = 0; i < arr.length; i++) s += arr[i];
  return s;
}

function argmaxObject(obj) {
  let bestKey = null;
  let bestVal = -Infinity;
  for (const key in obj) {
    if (obj[key] > bestVal) { bestVal = obj[key]; bestKey = key; }
  }
  return bestKey;
}

function round2(v) { return Math.round((v + Number.EPSILON) * 100) / 100; }
function round3(v) { return Math.round((v + Number.EPSILON) * 1000) / 1000; }

const formatterCache = new Map();
function nf(dec) {
  const key = String(dec);
  if (!formatterCache.has(key)) {
    formatterCache.set(key, new Intl.NumberFormat('en-US', {
      minimumFractionDigits: dec, maximumFractionDigits: dec
    }));
  }
  return formatterCache.get(key);
}

function fmtMoney(v, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const sign = v < 0 ? '-' : '';
  return sign + '$' + nf(dec).format(Math.abs(v));
}

function fmtSignedMoney(v, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const sign = v > 0 ? '+' : (v < 0 ? '-' : '');
  return sign + '$' + nf(dec).format(Math.abs(v));
}

function fmtNum(v, dec = 2) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return nf(dec).format(v);
}

function fmtPct(v, dec = 1) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return nf(dec).format(v * 100) + '%';
}

function fmtPctPoints(v, dec = 1) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return nf(dec).format(v) + '%';
}

function fmtRate(v, dec = 2) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return '$' + nf(dec).format(v) + '/h';
}

function fmtCompactUSD(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e6) return (v < 0 ? '-' : '') + '$' + nf(2).format(a / 1e6) + 'M';
  if (a >= 1e3) return (v < 0 ? '-' : '') + '$' + nf(1).format(a / 1e3) + 'k';
  return fmtMoney(v);
}

function fmtDateShort(iso) {
  if (!iso) return '—';
  const d = new Date(iso + 'T00:00:00Z');
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function addDays(iso, days) {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function daysBetween(a, b) {
  const da = new Date(a + 'T00:00:00Z').getTime();
  const db = new Date(b + 'T00:00:00Z').getTime();
  return Math.round((db - da) / 86400000);
}

function monthEnd(month) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(Date.UTC(y, m, 0));
  return d.toISOString().slice(0, 10);
}

function monthsInPeriod(from, to) {
  const months = (DATA && DATA.players && DATA.players.months) || [];
  return months.filter(m => (m + '-01') <= to && monthEnd(m) >= from);
}

function weeksInPeriod(weekly, from, to) {
  return weekly.filter(w => addDays(w.week_start, 6) >= from && w.week_start <= to);
}

function eventsInPeriod(from, to) {
  return (DATA.core.events || []).filter(e => e.start <= to && e.end >= from);
}

function validDate(v) {
  if (!(typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && v >= MIN_DATE && v <= MAX_DATE)) return null;
  if (DATA && DATA.core && DATA.core.dates.indexOf(v) === -1) return null;
  return v;
}

function comparisonValue(a, b) {
  if (a === b) return 0;
  if (a === null || a === undefined || a === '') return 1;
  if (b === null || b === undefined || b === '') return -1;
  return a < b ? -1 : 1;
}

function formatGeneric(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return nf(Number.isInteger(v) ? 0 : 2).format(v);
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function statusClass(status) {
  return 'chip chip-' + (status || 'neutral');
}

function chip(label, status) {
  return el('span', statusClass(status), label);
}

function makeKpi(label, value, sub) {
  const tile = el('div', 'kpi');
  append(tile, el('div', 'kpi-label', label), el('div', 'kpi-value', value));
  if (sub) tile.appendChild(el('div', 'kpi-sub', sub));
  return tile;
}

function pendingCard(title, message) {
  const card = el('section', 'card');
  card.appendChild(el('h2', null, title));
  card.appendChild(el('div', 'pending', message || 'Content pending — the analyst has not written this section yet.'));
  return card;
}

function emptyCard(title, message) {
  const card = el('section', 'card');
  card.appendChild(el('h2', null, title));
  card.appendChild(el('p', 'muted', message || 'No data in the selected period and scope.'));
  return card;
}

function callout(htmlLikeTextParts) {
  const box = el('div', 'callout');
  for (const part of htmlLikeTextParts) {
    if (part instanceof Node) box.appendChild(part);
    else box.appendChild(document.createTextNode(String(part)));
  }
  return box;
}

/* -------------------------------------------------------------------------
   2. Data loading and row metadata
   ------------------------------------------------------------------------- */

async function fetchJSON(name, optional) {
  const url = 'data/' + name + '.json';
  let response;
  try {
    response = await fetch(url, { cache: 'no-store' });
  } catch (err) {
    if (optional) return null;
    throw new Error('Could not fetch ' + url + ' (' + err.message + ')');
  }
  if (!response.ok) {
    if (optional) return null;
    throw new Error('Could not fetch ' + url + ' (HTTP ' + response.status + ')');
  }
  try {
    return await response.json();
  } catch (err) {
    if (optional) return null;
    throw new Error('Invalid JSON in ' + url + ' (' + err.message + ')');
  }
}

async function ensureData() {
  if (DATA) return DATA;
  if (dataPromise) return dataPromise;
  dataPromise = (async () => {
    const [core, players, ops, analysis, model, story, plan, claims] = await Promise.all([
      fetchJSON('core'),
      fetchJSON('players'),
      fetchJSON('ops'),
      fetchJSON('analysis'),
      fetchJSON('model'),
      fetchJSON('story', true),
      fetchJSON('plan', true),
      fetchJSON('claims', true)
    ]);
    DATA = { core, players, ops, analysis, model, story, plan, claims };
    prepareRowMetadata();
    return DATA;
  })();
  return dataPromise;
}

function prepareRowMetadata() {
  const core = DATA.core;
  const md = core.md;
  const n = md.d.length;
  const zoneOfBank = core.banks.map(b => core.zones[b.zone]);
  const zoneById = Object.create(null);
  const bankById = Object.create(null);
  core.zones.forEach(z => { zoneById[z.id] = z; });
  core.banks.forEach(b => { bankById[b.id] = b; });

  const closureStart = core.dates.indexOf('2025-03-03');
  const closureEnd = core.dates.indexOf('2025-04-06');
  const rowZoneId = new Array(n);
  const rowBankId = new Array(n);
  const rowZoneLevel = new Array(n);

  for (let i = 0; i < n; i++) {
    const b = core.banks[md.b[i]];
    const z = zoneOfBank[md.b[i]];
    rowZoneId[i] = z.id;
    rowBankId[i] = b.id;
    rowZoneLevel[i] = (z.id === 'Z-B40' && md.d[i] >= closureStart && md.d[i] <= closureEnd)
      ? 'Z-B40#closed'
      : z.id;
  }

  DATA.derived = {
    zoneOfBank, zoneById, bankById, rowZoneId, rowBankId, rowZoneLevel,
    closureStart, closureEnd,
    machineIndexById: Object.create(null)
  };
  core.machines.forEach((m, i) => { DATA.derived.machineIndexById[m.id] = i; });
}

/* -------------------------------------------------------------------------
   3. Shared computations
   ------------------------------------------------------------------------- */

/**
 * Gamma quantile for the 10%/90% posterior interval.
 * Wilson–Hilferty for shape > 30; normal approximation on the rate otherwise.
 */
function gammaQuantile(p, shape, rate) {
  if (!Number.isFinite(shape) || !Number.isFinite(rate) || shape <= 0 || rate <= 0) return 0;
  const z = p < 0.5 ? -1.2815515655446004 : 1.2815515655446004;
  if (shape > 30) {
    const base = 1 - 1 / (9 * shape) + z / (3 * Math.sqrt(shape));
    const q = shape * base * base * base / rate;
    return Math.max(0, q);
  }
  return Math.max(0, shape / rate + z * Math.sqrt(shape) / rate);
}

/**
 * Full shared computation for a date-index range [lo, hi].
 * Returns machine records, the zone × config IPF fit, GM list and totals.
 */
function computeAll(lo, hi) {
  const key = lo + '|' + hi;
  if (computedCache.key === key && computedCache.res) return computedCache.res;

  const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  const core = DATA.core;
  const md = core.md;
  const derived = DATA.derived;
  const nMachines = core.machines.length;
  const nRows = md.d.length;
  const ndays = hi - lo + 1;

  /* ---- 3a. Per-machine aggregation over the period (all machines) ---- */
  const agg = new Array(nMachines);
  for (let m = 0; m < nMachines; m++) {
    agg[m] = {
      idx: m, days: 0, ah: 0, sh: 0, oh: 0, ci: 0, hw: 0, th: 0, v: 0,
      sp: 0, hs: 0, f: 0, rc: 0, cost: 0, e: 0,
      bankAh: Object.create(null), cfgAh: Object.create(null)
    };
  }

  let totalAh = 0;
  let totalSh = 0;
  let totalOh = 0;
  let totalCi = 0;
  let totalHw = 0;
  let totalTh = 0;
  let totalV = 0;
  let totalCost = 0;

  for (let i = 0; i < nRows; i++) {
    const d = md.d[i];
    if (d < lo || d > hi) continue;
    const m = md.m[i];
    const a = agg[m];
    a.days += 1;
    a.ah += md.ah[i];
    a.sh += md.sh[i];
    a.oh += md.oh[i];
    a.ci += md.ci[i];
    a.hw += md.hw[i];
    a.th += md.th[i];
    a.v += md.v[i];
    a.sp += md.sp[i];
    a.hs += md.hs[i];
    a.f += md.f[i];
    a.rc += md.rc[i];
    a.cost += md.cost[i];

    totalAh += md.ah[i];
    totalSh += md.sh[i];
    totalOh += md.oh[i];
    totalCi += md.ci[i];
    totalHw += md.hw[i];
    totalTh += md.th[i];
    totalV += md.v[i];
    totalCost += md.cost[i];

    const b = md.b[i];
    a.bankAh[b] = (a.bankAh[b] || 0) + md.ah[i];
    const c = md.c[i];
    a.cfgAh[c] = (a.cfgAh[c] || 0) + md.ah[i];
  }

  /* ---- 3b. Zone × config IPF (30 iterations), C weighted-mean 1 ---- */
  const Z = Object.create(null);
  const C = Object.create(null);
  for (let i = 0; i < nRows; i++) {
    const d = md.d[i];
    if (d < lo || d > hi) continue;
    const z = derived.rowZoneLevel[i];
    if (Z[z] === undefined) Z[z] = 1;
    const c = md.c[i];
    if (C[c] === undefined) C[c] = 1;
  }

  const iter = 30;
  for (let it = 0; it < iter; it++) {
    const numZ = Object.create(null);
    const denZ = Object.create(null);
    for (let i = 0; i < nRows; i++) {
      const d = md.d[i];
      if (d < lo || d > hi) continue;
      const z = derived.rowZoneLevel[i];
      const c = md.c[i];
      const ah = md.ah[i];
      numZ[z] = (numZ[z] || 0) + md.th[i];
      denZ[z] = (denZ[z] || 0) + ah * C[c];
    }
    for (const z in Z) Z[z] = denZ[z] > 0 ? numZ[z] / denZ[z] : 1;

    const numC = Object.create(null);
    const denC = Object.create(null);
    for (let i = 0; i < nRows; i++) {
      const d = md.d[i];
      if (d < lo || d > hi) continue;
      const z = derived.rowZoneLevel[i];
      const c = md.c[i];
      const ah = md.ah[i];
      numC[c] = (numC[c] || 0) + md.th[i];
      denC[c] = (denC[c] || 0) + ah * Z[z];
    }
    for (const c in C) C[c] = denC[c] > 0 ? numC[c] / denC[c] : 1;

    // Normalise C to availability-weighted mean 1 and put the scale into Z,
    // preserving the fitted products Z*C.
    let weightedC = 0;
    for (let i = 0; i < nRows; i++) {
      const d = md.d[i];
      if (d < lo || d > hi) continue;
      weightedC += md.ah[i] * C[md.c[i]];
    }
    const meanC = totalAh > 0 ? weightedC / totalAh : 1;
    if (meanC > 0) {
      for (const c in C) C[c] /= meanC;
      for (const z in Z) Z[z] *= meanC;
    }
  }

  // Availability-weighted mean of Z over P (closed level keeps its own level).
  let weightedZ = 0;
  for (let i = 0; i < nRows; i++) {
    const d = md.d[i];
    if (d < lo || d > hi) continue;
    weightedZ += md.ah[i] * Z[derived.rowZoneLevel[i]];
  }
  const zbar = totalAh > 0 ? weightedZ / totalAh : 0;

  const schedHours = sum(core.sched_h.slice(lo, hi + 1));
  const floorAvailability = totalSh > 0 ? totalAh / totalSh : 0;
  const ahRef = schedHours * floorAvailability;

  /* ---- 3c. Expected theo per machine from the fit ---- */
  for (let i = 0; i < nRows; i++) {
    const d = md.d[i];
    if (d < lo || d > hi) continue;
    agg[md.m[i]].e += md.ah[i] * Z[derived.rowZoneLevel[i]] * C[md.c[i]];
  }

  /* ---- 3d. Ops downtime hours by machine in P (for the full table) ---- */
  const downH = new Array(nMachines).fill(0);
  const faultN = new Array(nMachines).fill(0);
  if (DATA.ops && DATA.ops.faults) {
    const f = DATA.ops.faults;
    for (let j = 0; j < f.m.length; j++) {
      const d = f.d[j];
      if (d < lo || d > hi) continue;
      downH[f.m[j]] += f.down_h[j] || 0;
      faultN[f.m[j]] += 1;
    }
  }

  /* ---- 3e. Machine records, verdicts and attribution ---- */
  const k = Number(DATA.model && DATA.model.A && DATA.model.A.k) || 20000;
  const records = [];
  const byIdx = new Array(nMachines).fill(null);

  for (let m = 0; m < nMachines; m++) {
    const a = agg[m];
    if (a.days === 0) continue;

    const bankIdx = Number(argmaxObject(a.bankAh));
    const cfgIdx = Number(argmaxObject(a.cfgAh));
    const bankRec = core.banks[bankIdx];
    const zone = core.zones[bankRec.zone];
    const cfg = core.configs[cfgIdx];

    const t = a.th;
    const e = a.e;
    const U = (t + k) / (e + k);
    // Quasi-Poisson interval: theo is dollars, not counts, so scale by the dispersion phi
    // estimated in pipeline/model.py (≈ 32 $ per unit of mean). Without it the interval is far too narrow.
    const phi = Number(DATA.model && DATA.model.A && DATA.model.A.full && DATA.model.A.full.phi) || 32;
    const shape = (t + k) / phi;
    const rate = (e + k) / phi;
    const lo80 = gammaQuantile(0.1, shape, rate);
    const hi80 = gammaQuantile(0.9, shape, rate);

    const luck = a.hw - t;
    const zLuck = a.v > 0 ? luck / Math.sqrt(a.v) : null;
    const p = cfg.hit_p;
    const hitZ = (a.sp > 0 && p > 0 && p < 1)
      ? (a.hs - a.sp * p) / Math.sqrt(a.sp * p * (1 - p))
      : null;

    const exposure = ahRef > 0 ? a.ah / ahRef : 0;
    const location = zbar > 0 ? (Z[zone.id] / zbar) : 1;
    const game = C[cfgIdx];
    const luckFactor = t > 0 ? a.hw / t : null;

    const logExposure = exposure > 0 ? Math.log(exposure) : null;
    const logLocation = location > 0 ? Math.log(location) : null;
    const logGame = game > 0 ? Math.log(game) : null;
    const logMachine = U > 0 ? Math.log(U) : null;
    const logLuck = (luckFactor !== null && luckFactor > 0) ? Math.log(luckFactor) : null;

    let verdict;
    let status;
    if (hitZ !== null && Math.abs(hitZ) >= 5) {
      verdict = 'Leak? Inspect';
      status = 'critical';
    } else if (a.days < 0.6 * ndays) {
      verdict = 'Short exposure';
      status = 'warning';
    } else if (hi80 < 0.92) {
      verdict = 'Truly weak';
      status = 'serious';
    } else {
      const drags = [
        ['Location', logLocation],
        ['Game math', logGame],
        ['Bad luck', logLuck],
        ['Downtime/exposure', logExposure]
      ].filter(d => d[1] !== null && Number.isFinite(d[1]));
      let worst = null;
      for (const d of drags) if (worst === null || d[1] < worst[1]) worst = d;
      if (worst && worst[1] < -0.05) {
        verdict = worst[0];
        status = 'good';
      } else {
        verdict = 'Fine';
        status = 'good';
      }
    }

    const rec = {
      idx: m,
      id: core.machines[m].id,
      mfr: core.machines[m].mfr,
      install: core.machines[m].install,
      retire: core.machines[m].retire,
      theme: cfg.theme,
      rtp: cfg.rtp,
      hitP: p,
      cfgId: cfg.id,
      zone: zone.id,
      zoneName: zone.name,
      bank: bankRec.id,
      days: a.days,
      ah: a.ah,
      sh: a.sh,
      oh: a.oh,
      ci: a.ci,
      hw: a.hw,
      th: t,
      v: a.v,
      sp: a.sp,
      hs: a.hs,
      faults: a.f,
      repairCost: a.rc,
      cost: a.cost,
      e,
      U,
      lo80,
      hi80,
      luck,
      zLuck,
      hitZ,
      exposure,
      location,
      game,
      luckFactor,
      logExposure,
      logLocation,
      logGame,
      logMachine,
      logLuck,
      verdict,
      status,
      downH: downH[m],
      faultTickets: faultN[m],
      avail: a.sh > 0 ? a.ah / a.sh : 0,
      occ: a.ah > 0 ? a.oh / a.ah : 0,
      contribution: a.hw - a.cost,
      theoRate: a.ah > 0 ? t / a.ah : 0
    };
    records.push(rec);
    byIdx[m] = rec;
  }

  const gm = records.slice().sort((x, y) => x.hw - y.hw).slice(0, 10);
  const leakIds = records.filter(r => r.hitZ !== null && Math.abs(r.hitZ) >= 5).map(r => r.id);

  const res = {
    lo, hi, ndays,
    Z, C, zbar, ahRef, schedHours, floorAvailability,
    perMachine: records,
    byIdx,
    gm,
    leakIds,
    totals: {
      ah: totalAh, sh: totalSh, oh: totalOh, ci: totalCi, hw: totalHw,
      th: totalTh, v: totalV, cost: totalCost
    }
  };

  computedCache.key = key;
  computedCache.res = res;
  const t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  if (typeof console !== 'undefined' && console.debug) {
    console.debug('[dashboard] shared computation', ndays, 'days', Math.round(t1 - t0) + 'ms');
  }
  return res;
}

/* ---- Scope helpers ---- */

function inScope(rec) {
  return (state.zone === 'all' || rec.zone === state.zone)
    && (state.bank === 'all' || rec.bank === state.bank);
}

function scopedMachines(res) {
  return res.perMachine.filter(r => r.days > 0 && inScope(r));
}

function scopedTotals(records) {
  const totals = { ah: 0, sh: 0, oh: 0, ci: 0, hw: 0, th: 0, cost: 0, days: 0 };
  for (const r of records) {
    totals.ah += r.ah;
    totals.sh += r.sh;
    totals.oh += r.oh;
    totals.ci += r.ci;
    totals.hw += r.hw;
    totals.th += r.th;
    totals.cost += r.cost;
    totals.days += r.days;
  }
  return totals;
}

function rowInScope(i) {
  const d = DATA.derived;
  return (state.zone === 'all' || d.rowZoneId[i] === state.zone)
    && (state.bank === 'all' || d.rowBankId[i] === state.bank);
}

/** Daily series for the selected date range and zone/bank scope. */
function dailyScoped(lo, hi) {
  const core = DATA.core;
  const md = core.md;
  const n = hi - lo + 1;
  const out = {
    dates: core.dates.slice(lo, hi + 1),
    ci: new Array(n).fill(0),
    hw: new Array(n).fill(0),
    th: new Array(n).fill(0),
    ah: new Array(n).fill(0),
    sh: new Array(n).fill(0),
    oh: new Array(n).fill(0),
    rows: new Array(n).fill(0)
  };
  for (let i = 0; i < md.d.length; i++) {
    const d = md.d[i];
    if (d < lo || d > hi) continue;
    if (!rowInScope(i)) continue;
    const j = d - lo;
    out.ci[j] += md.ci[i];
    out.hw[j] += md.hw[i];
    out.th[j] += md.th[i];
    out.ah[j] += md.ah[i];
    out.sh[j] += md.sh[i];
    out.oh[j] += md.oh[i];
    out.rows[j] += 1;
  }
  return out;
}

function scopeDescription() {
  const zone = state.zone === 'all'
    ? 'all zones'
    : (DATA.derived.zoneById[state.zone] || { name: state.zone }).name;
  const bank = state.bank === 'all' ? 'all banks' : state.bank;
  return zone + ' · ' + bank;
}

/* -------------------------------------------------------------------------
   4. Theme tokens, Plotly helpers, chart/table card factories
   ------------------------------------------------------------------------- */

function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const get = name => cs.getPropertyValue(name).trim();
  const cat = [];
  for (let i = 1; i <= 8; i++) cat.push(get('--cat-' + i));
  return {
    surface: get('--surface'), page: get('--page'), ink: get('--ink'),
    ink2: get('--ink-2'), muted: get('--muted'), grid: get('--grid'), axis: get('--axis'),
    cat,
    good: get('--good'), warning: get('--warning'), serious: get('--serious'), critical: get('--critical')
  };
}

function baseLayout(extra) {
  const t = tokens();
  const base = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif', color: t.ink, size: 12 },
    margin: { l: 58, r: 18, t: 12, b: 50 },
    xaxis: {
      gridcolor: t.grid, zerolinecolor: t.grid, linecolor: t.axis,
      tickfont: { color: t.ink2, size: 11 },
      title: { font: { color: t.ink2, size: 12 } },
      automargin: true
    },
    yaxis: {
      gridcolor: t.grid, zerolinecolor: t.grid, linecolor: t.axis,
      tickfont: { color: t.ink2, size: 11 },
      title: { font: { color: t.ink2, size: 12 } },
      automargin: true
    },
    legend: {
      orientation: 'h', x: 0, y: -0.2, xanchor: 'left', yanchor: 'top',
      font: { color: t.ink2, size: 11 }, bgcolor: 'rgba(0,0,0,0)'
    },
    hoverlabel: {
      bgcolor: t.surface, bordercolor: t.axis,
      font: { color: t.ink, size: 12 }
    },
    showlegend: false,
    hovermode: 'closest',
    bargap: 0.25
  };
  const out = Object.assign({}, base, extra || {});
  out.xaxis = Object.assign({}, base.xaxis, (extra && extra.xaxis) || {});
  out.yaxis = Object.assign({}, base.yaxis, (extra && extra.yaxis) || {});
  out.margin = Object.assign({}, base.margin, (extra && extra.margin) || {});
  if (extra && extra.legend) out.legend = Object.assign({}, base.legend, extra.legend);
  return out;
}

function plotInto(node, figure, ariaLabel) {
  if (!window.Plotly) {
    clear(node);
    node.appendChild(el('p', 'pending', 'Plotly did not load. Check the cdnjs script reference or the network.'));
    return;
  }
  node.setAttribute('role', 'img');
  node.setAttribute('aria-label', ariaLabel || 'Chart');
  window.Plotly.newPlot(node, figure.data, figure.layout, {
    displayModeBar: false, responsive: true, scrollZoom: false
  });
}

function renderTable(container, spec) {
  if (!spec || !spec.columns || !spec.rows) return;
  const wrap = el('div', 'table-wrap');
  const table = el('table');
  if (spec.caption) {
    const cap = el('caption', 'sr-only', spec.caption);
    table.appendChild(cap);
  }
  const thead = el('thead');
  const headRow = el('tr');
  for (const col of spec.columns) {
    const th = el('th', col.num ? 'num' : (col.wrap ? 'wrap' : null), col.label);
    th.scope = 'col';
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = el('tbody');
  for (const row of spec.rows) {
    const tr = el('tr');
    for (const col of spec.columns) {
      const raw = col.get ? col.get(row) : row[col.key];
      const td = el('td', col.num ? 'num' : (col.wrap ? 'wrap' : null));
      if (raw instanceof Node) td.appendChild(raw);
      else td.textContent = col.fmt ? col.fmt(raw, row) : formatGeneric(raw);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);
}

/**
 * Chart card factory: heading (finding), how-to-read, chart, Table toggle,
 * optional controls/footer, and a Source footnote.
 */
function chartCard(parent, opts) {
  const card = el('section', 'card');
  const head = el('div', 'card-head');
  const headText = el('div');
  append(headText,
    el('h2', null, opts.title),
    el('p', 'how', opts.how)
  );
  head.appendChild(headText);

  const actions = el('div', 'head-actions');
  const tableBtn = el('button', 'btn btn-sm', 'Table');
  tableBtn.type = 'button';
  tableBtn.setAttribute('aria-expanded', 'false');
  actions.appendChild(tableBtn);
  head.appendChild(actions);
  card.appendChild(head);

  if (opts.controls) card.appendChild(opts.controls);

  const chart = el('div', 'chart');
  if (opts.height) chart.style.minHeight = opts.height + 'px';
  card.appendChild(chart);

  const tableBox = el('div', 'table-toggle');
  tableBox.hidden = true;
  tableBox.id = 'table-' + Math.random().toString(36).slice(2, 9);

  tableBtn.addEventListener('click', () => {
    if (tableBox.hidden) {
      if (!tableBox.dataset.built) {
        if (opts.table) renderTable(tableBox, opts.table());
        tableBox.dataset.built = '1';
      }
      tableBox.hidden = false;
      tableBtn.textContent = 'Hide table';
      tableBtn.setAttribute('aria-expanded', 'true');
      tableBtn.setAttribute('aria-controls', tableBox.id);
    } else {
      tableBox.hidden = true;
      tableBtn.textContent = 'Table';
      tableBtn.setAttribute('aria-expanded', 'false');
    }
  });

  card.appendChild(tableBox);
  if (opts.footer) card.appendChild(opts.footer);

  const source = el('p', 'source');
  source.textContent = 'Source: ' + opts.source;
  card.appendChild(source);

  parent.appendChild(card);
  try {
    const figure = opts.build();
    if (opts.height && figure.layout && figure.layout.height === undefined) {
      figure.layout.height = opts.height;
    }
    plotInto(chart, figure, opts.title);
  } catch (err) {
    clear(chart);
    chart.appendChild(el('p', 'pending', 'Chart could not be drawn: ' + err.message));
    console.error(err);
  }
  return card;
}

function traceLine(x, y, name, color, hovertemplate, extra) {
  return Object.assign({
    type: 'scatter', mode: 'lines', x, y, name,
    line: { width: 2, color },
    hovertemplate
  }, extra || {});
}

function traceBar(x, y, name, color, hovertemplate, extra) {
  return Object.assign({
    type: 'bar', x, y, name,
    marker: { color },
    hovertemplate
  }, extra || {});
}

function legendLayout(extra) {
  return baseLayout(Object.assign({ showlegend: true }, extra || {}));
}

function periodBounds() {
  const lo = DATA.core.dates.indexOf(state.from);
  const hi = DATA.core.dates.indexOf(state.to);
  return { lo, hi };
}

/* -------------------------------------------------------------------------
   5. Global filter bar, hash routing and shell
   ------------------------------------------------------------------------- */

function parseHash() {
  const raw = location.hash.replace(/^#/, '');
  if (!raw) return;
  const params = new URLSearchParams(raw);
  const tab = params.get('tab');
  if (tab && TABS.includes(tab)) state.tab = tab;
  const from = validDate(params.get('from'));
  const to = validDate(params.get('to'));
  if (from) state.from = from;
  if (to) state.to = to;
  if (state.from > state.to) {
    const tmp = state.from;
    state.from = state.to;
    state.to = tmp;
  }
  const zone = params.get('zone');
  if (zone && (zone === 'all' || DATA.derived.zoneById[zone])) state.zone = zone;
  const bank = params.get('bank');
  if (bank && bank !== 'all' && DATA.derived.bankById[bank]) {
    state.bank = bank;
    state.zone = DATA.core.zones[DATA.derived.bankById[bank].zone].id;
  } else {
    state.bank = 'all';
  }
  if (state.bank !== 'all') {
    const bankRec = DATA.derived.bankById[state.bank];
    if (!bankRec || DATA.core.zones[bankRec.zone].id !== state.zone) state.bank = 'all';
  }
}

function syncHash() {
  const params = new URLSearchParams();
  params.set('tab', state.tab);
  params.set('from', state.from);
  params.set('to', state.to);
  params.set('zone', state.zone);
  if (state.bank !== 'all') params.set('bank', state.bank);
  const hash = '#' + params.toString();
  if (location.hash !== hash) {
    try {
      history.replaceState(null, '', hash);
    } catch (err) {
      location.hash = hash;
    }
  }
}

function buildZoneOptions() {
  const sel = $('#zoneSel');
  if (!sel) return;
  clear(sel);
  sel.appendChild(new Option('All zones', 'all'));
  for (const z of DATA.core.zones) sel.appendChild(new Option(z.name, z.id));
}

function buildBankOptions() {
  const sel = $('#bankSel');
  if (!sel) return;
  clear(sel);
  sel.appendChild(new Option(state.zone === 'all' ? 'All banks (select a zone first)' : 'All banks', 'all'));
  if (state.zone === 'all') {
    sel.disabled = true;
    sel.title = 'Choose a zone to narrow the banks';
    sel.setAttribute('aria-label', 'Bank filter (choose a zone first)');
    state.bank = 'all';
    return;
  }
  sel.disabled = false;
  sel.removeAttribute('title');
  sel.setAttribute('aria-label', 'Bank filter');
  const bankIds = DATA.core.banks
    .map((b, i) => ({ b, i }))
    .filter(x => DATA.core.zones[x.b.zone].id === state.zone)
    .map(x => x.b);
  for (const b of bankIds) sel.appendChild(new Option(b.id, b.id));
}

function syncControls() {
  const fromInput = $('#fromDate');
  const toInput = $('#toDate');
  if (fromInput) fromInput.value = state.from;
  if (toInput) toInput.value = state.to;
  const zoneSel = $('#zoneSel');
  if (zoneSel) zoneSel.value = state.zone;
  buildBankOptions();
  const bankSel = $('#bankSel');
  if (bankSel) bankSel.value = state.bank;
  $$('.preset').forEach(btn => {
    const p = PRESETS[btn.dataset.preset];
    btn.setAttribute('aria-pressed', p && p.from === state.from && p.to === state.to ? 'true' : 'false');
  });
}

function applyStateToView() {
  $$('#tabnav .tabbtn').forEach(btn => {
    if (btn.dataset.tab === state.tab) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });
}

function commitControls() {
  let from = $('#fromDate').value || MIN_DATE;
  let to = $('#toDate').value || MAX_DATE;
  if (from < MIN_DATE) from = MIN_DATE;
  if (from > MAX_DATE) from = MAX_DATE;
  if (to < MIN_DATE) to = MIN_DATE;
  if (to > MAX_DATE) to = MAX_DATE;
  if (from > to) {
    const tmp = from;
    from = to;
    to = tmp;
  }
  state.from = from;
  state.to = to;
  state.zone = $('#zoneSel').value || 'all';
  if (state.zone === 'all') state.bank = 'all';
  else {
    const bank = $('#bankSel').disabled ? 'all' : ($('#bankSel').value || 'all');
    state.bank = bank;
  }
  syncControls();
  syncHash();
  render();
}

function setupShell() {
  buildZoneOptions();
  buildBankOptions();
  syncControls();

  $('#fromDate').addEventListener('change', commitControls);
  $('#toDate').addEventListener('change', commitControls);

  $('#zoneSel').addEventListener('change', () => {
    state.zone = $('#zoneSel').value;
    state.bank = 'all';
    state.trafficZones = state.zone === 'all' ? null : [state.zone];
    buildBankOptions();
    syncControls();
    commitControls();
  });

  $('#bankSel').addEventListener('change', () => {
    state.bank = $('#bankSel').value;
    commitControls();
  });

  $$('.preset').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = PRESETS[btn.dataset.preset];
      if (!p) return;
      state.from = p.from;
      state.to = p.to;
      syncControls();
      syncHash();
      render();
    });
  });

  $('#resetBtn').addEventListener('click', () => {
    state.from = DEFAULT_STATE.from;
    state.to = DEFAULT_STATE.to;
    state.zone = DEFAULT_STATE.zone;
    state.bank = DEFAULT_STATE.bank;
    state.mSearch = '';
    state.mSort = { key: 'hw', dir: 'asc' };
    state.pTier = 'all';
    state.pAge = 'all';
    state.pRegion = 'all';
    state.trafficZones = null;
    syncControls();
    syncHash();
    render();
  });

  $$('#tabnav .tabbtn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      if (!TABS.includes(tab)) return;
      state.tab = tab;
      syncHash();
      applyStateToView();
      render();
      window.scrollTo({ top: 0, behavior: 'auto' });
    });
  });

  setupTheme();

  window.addEventListener('hashchange', () => {
    const before = JSON.stringify([state.tab, state.from, state.to, state.zone, state.bank]);
    parseHash();
    const after = JSON.stringify([state.tab, state.from, state.to, state.zone, state.bank]);
    if (before !== after) {
      syncControls();
      applyStateToView();
      render();
    }
  });
}

function setupTheme() {
  let stored = null;
  try { stored = localStorage.getItem('gilded-ace-theme'); } catch (err) { stored = null; }
  if (stored === 'light' || stored === 'dark') {
    document.documentElement.dataset.theme = stored;
  }
  updateThemeButton();
  $('#themeBtn').addEventListener('click', () => {
    const next = effectiveTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('gilded-ace-theme', next); } catch (err) { /* ignore */ }
    updateThemeButton();
    if (DATA) render();
  });
  const mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  if (mq && mq.addEventListener) {
    mq.addEventListener('change', () => {
      if (!document.documentElement.dataset.theme) {
        updateThemeButton();
        if (DATA) render();
      }
    });
  }
}

function effectiveTheme() {
  const attr = document.documentElement.dataset.theme;
  if (attr === 'light' || attr === 'dark') return attr;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function updateThemeButton() {
  const btn = $('#themeBtn');
  if (!btn) return;
  const dark = effectiveTheme() === 'dark';
  btn.textContent = dark ? 'Light mode' : 'Dark mode';
  btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
}

function renderScopeLine(res) {
  const line = $('#scopeLine');
  if (!line) return;
  const scoped = scopedMachines(res);
  line.textContent = 'Showing ' + res.ndays + ' gaming days · ' + scoped.length + ' machines · period '
    + state.from + '–' + state.to + ' · ' + scopeDescription();
}

function render() {
  if (!DATA) return;
  const { lo, hi } = periodBounds();
  const res = computeAll(lo, hi);
  applyStateToView();
  renderScopeLine(res);
  const app = $('#app');
  clear(app);
  const renderer = RENDERERS[state.tab] || RENDERERS.verdict;
  try {
    renderer(app, res);
  } catch (err) {
    console.error(err);
    const card = el('section', 'card error-card');
    append(card,
      el('h2', null, 'Something went wrong while drawing this tab'),
      el('p', 'muted', String(err && err.message ? err.message : err))
    );
    app.appendChild(card);
  }
}

/* ---- Story and content-pending helpers ---- */

function storyCard(key, options) {
  const s = DATA.story && DATA.story[key];
  const card = el('section', 'card story');
  if (!s || typeof s !== 'object') {
    append(card,
      el('h2', null, (options && options.title) || TAB_LABELS[key] || 'Content pending'),
      el('div', 'pending', 'Content pending — the analyst has not written this section yet.')
    );
    return card;
  }
  if (DATA.story._dummy) card.appendChild(el('span', 'dummy-note', 'Dummy placeholder — analyst content pending'));
  if (s.title) card.appendChild(el('h2', null, s.title));
  if (s.question) card.appendChild(el('p', 'question', s.question));
  if (s.answer) {
    const answer = el('div', 'answer');
    // The task explicitly allows simple <b>, <i>, <br> in our own analyst text.
    answer.innerHTML = String(s.answer);
    card.appendChild(answer);
  }
  if (Array.isArray(s.notes) && s.notes.length) {
    const ul = el('ul');
    for (const note of s.notes) ul.appendChild(el('li', null, note));
    card.appendChild(ul);
  }
  return card;
}

function notesCallout(key) {
  const s = DATA.story && DATA.story[key];
  if (!s || !Array.isArray(s.notes) || !s.notes.length) return null;
  const box = el('div', 'callout');
  box.appendChild(el('strong', null, 'Notes'));
  const ul = el('ul', 'footnote-list');
  for (const n of s.notes) ul.appendChild(el('li', null, n));
  box.appendChild(ul);
  return box;
}

/* =========================================================================
   6. Tab renderers
   ========================================================================= */

const RENDERERS = Object.create(null);

/* ---- 6.1 Verdict ---- */

RENDERERS.verdict = function renderVerdict(root, res) {
  root.appendChild(storyCard('verdict'));

  const scoped = scopedMachines(res);
  const totals = scopedTotals(scoped);
  const observedHold = totals.ci > 0 ? totals.hw / totals.ci : null;
  const theoHold = totals.ci > 0 ? totals.th / totals.ci : null;
  const holdRatio = totals.th > 0 ? totals.hw / totals.th : null;
  const availability = totals.sh > 0 ? totals.ah / totals.sh : null;
  const occupancy = totals.ah > 0 ? totals.oh / totals.ah : null;

  const kpis = el('div', 'kpis');
  append(kpis,
    makeKpi('Floor coin-in', fmtCompactUSD(totals.ci), fmtMoney(totals.ci)),
    makeKpi('House win', fmtCompactUSD(totals.hw), 'Actual, in period'),
    makeKpi('Theoretical win', fmtCompactUSD(totals.th), 'Expected from game math'),
    makeKpi('Observed hold vs theo hold',
      (observedHold !== null ? fmtPct(observedHold, 2) : '—') + ' vs ' + (theoHold !== null ? fmtPct(theoHold, 2) : '—'),
      holdRatio !== null ? 'House win ÷ theo = ' + nf(3).format(holdRatio) + '×' : 'No theo in scope'),
    makeKpi('Availability', availability !== null ? fmtPct(availability) : '—',
      occupancy !== null ? 'Occupancy ' + fmtPct(occupancy) : '')
  );
  root.appendChild(kpis);

  const gm = scoped.slice().sort((a, b) => a.hw - b.hw).slice(0, 10);
  const counts = new Map();
  for (const r of gm) counts.set(r.verdict, (counts.get(r.verdict) || 0) + 1);
  const labelFor = {
    'Location': 'location', 'Game math': 'game math', 'Bad luck': 'bad luck',
    'Downtime/exposure': 'downtime/exposure', 'Short exposure': 'short exposure',
    'Truly weak': 'truly weak', 'Leak? Inspect': 'leaks to inspect', 'Fine': 'fine'
  };
  const countParts = [];
  for (const [label, n] of counts) countParts.push(n + ' ' + (labelFor[label] || label));
  let topDrag = null;
  let topDragN = 0;
  for (const [label, n] of counts) {
    if (['Location', 'Game math', 'Bad luck', 'Downtime/exposure'].includes(label) && n > topDragN) {
      topDrag = label;
      topDragN = n;
    }
  }
  const countLine = gm.length
    ? 'Of the GM\'s ' + gm.length + ': ' + countParts.join(', ') + '.'
    : 'This scope has no machines with activity.';

  const tableCard = el('section', 'card');
  append(tableCard,
    el('h2', null, 'The GM\'s bottom ' + gm.length + ' machines, with the diagnosis attached'),
    el('p', 'how', 'Lowest total house win in the selected period and zone/bank scope. Read the verdict first, then the factors: a factor below 1.00 is a drag; U below 1 means the machine earns less than its location and game predict.'),
    el('p', 'muted', countLine)
  );

  const columns = [
    { label: '#', num: true, get: r => gm.indexOf(r) + 1, fmt: v => String(v) },
    { label: 'Machine', get: r => r.id },
    { label: 'Zone / bank', get: r => r.zoneName + ' · ' + r.bank, wrap: true },
    { label: 'Game (theme · RTP)', get: r => r.theme + ' · ' + fmtPct(r.rtp, 0), wrap: true },
    { label: 'Days', num: true, get: r => r.days, fmt: v => fmtNum(v, 0) },
    { label: 'House win', num: true, get: r => r.hw, fmt: v => fmtMoney(v) },
    { label: 'Theo', num: true, get: r => r.th, fmt: v => fmtMoney(v) },
    { label: 'Luck $', num: true, get: r => r.luck, fmt: v => fmtSignedMoney(v) },
    { label: 'Luck z', num: true, get: r => r.zLuck, fmt: v => fmtNum(v, 2) },
    { label: 'Avail %', num: true, get: r => r.avail, fmt: v => fmtPct(v) },
    { label: 'Location factor', num: true, get: r => r.location, fmt: v => fmtNum(v, 3) },
    { label: 'Game factor', num: true, get: r => r.game, fmt: v => fmtNum(v, 3) },
    {
      label: 'Machine U [80%]', num: true,
      get: r => r.U,
      fmt: (v, r) => fmtNum(r.U, 3) + ' [' + fmtNum(r.lo80, 3) + '–' + fmtNum(r.hi80, 3) + ']'
    },
    { label: 'Hit z', num: true, get: r => r.hitZ, fmt: v => fmtNum(v, 2) },
    { label: 'Verdict', get: r => chip(r.verdict, r.status) }
  ];
  renderTable(tableCard, { columns, rows: gm, caption: 'The GM bottom-ten machines and their verdicts' });
  root.appendChild(tableCard);

  if (gm.length) {
    const ordered = gm.slice().sort((a, b) => {
      const sa = (a.logExposure || 0) + (a.logLocation || 0) + (a.logGame || 0) + (a.logMachine || 0) + (a.logLuck || 0);
      const sb = (b.logExposure || 0) + (b.logLocation || 0) + (b.logGame || 0) + (b.logMachine || 0) + (b.logLuck || 0);
      return sa - sb;
    });
    const labels = ordered.map(r => r.id);
    const factors = [
      { key: 'logExposure', name: 'Exposure', values: ordered.map(r => r.logExposure) },
      { key: 'logLocation', name: 'Location', values: ordered.map(r => r.logLocation) },
      { key: 'logGame', name: 'Game', values: ordered.map(r => r.logGame) },
      { key: 'logMachine', name: 'Machine', values: ordered.map(r => r.logMachine) },
      { key: 'logLuck', name: 'Luck', values: ordered.map(r => r.logLuck) }
    ];
    const t = tokens();
    const data = factors.map((f, i) => ({
      type: 'bar', orientation: 'h', x: f.values, y: labels, name: f.name,
      marker: { color: t.cat[i] },
      hovertemplate: f.name + ': %{x:+.3f}<extra></extra>'
    }));
    const attrTitle = topDrag
      ? (labelFor[topDrag] || topDrag).replace(/^./, c => c.toUpperCase()) + ' is the largest drag for ' + topDragN + ' of the GM\'s ' + gm.length + ' machines'
      : 'The bottom machines\' log factors, relative to a typical machine';
    const table = {
      columns: [
        { label: 'Machine', get: r => r.id },
        { label: 'Exposure', num: true, get: r => r.logExposure, fmt: v => fmtNum(v, 3) },
        { label: 'Location', num: true, get: r => r.logLocation, fmt: v => fmtNum(v, 3) },
        { label: 'Game', num: true, get: r => r.logGame, fmt: v => fmtNum(v, 3) },
        { label: 'Machine', num: true, get: r => r.logMachine, fmt: v => fmtNum(v, 3) },
        { label: 'Luck', num: true, get: r => r.logLuck, fmt: v => fmtNum(v, 3) }
      ],
      rows: ordered
    };
    chartCard(root, {
      title: attrTitle,
      how: 'Each bar is a log factor against a typical machine; bars left of zero are drags and bars right of zero are tailwinds. The five factors multiply to the machine\'s house win relative to the floor reference.',
      source: 'core.json md (machine-day sales), model.json A.k (shrinkage)',
      height: 360,
      build: () => ({
        data,
        layout: baseLayout({
          barmode: 'relative',
          showlegend: true,
          margin: { l: 76, r: 24, t: 12, b: 48 },
          xaxis: { title: { text: 'Log factor (negative = drag)' }, zeroline: true, zerolinecolor: t.axis, zerolinewidth: 1 },
          yaxis: { title: { text: '' }, automargin: true },
          legend: { orientation: 'h', y: -0.25 }
        })
      }),
      table: () => table
    });
  }
};

/* ---- 6.2 Machines ---- */

RENDERERS.machines = function renderMachines(root, res) {
  root.appendChild(storyCard('machines'));

  const t = tokens();
  const scoped = scopedMachines(res);
  const gmIds = new Set(scoped.slice().sort((a, b) => a.hw - b.hw).slice(0, 10).map(r => r.id));
  const leaks = res.perMachine.filter(r => r.hitZ !== null && Math.abs(r.hitZ) >= 5);
  const leakIds = new Set(leaks.map(r => r.id));

  const inScopeBase = [];
  const outScopeBase = [];
  for (const r of res.perMachine) {
    if (gmIds.has(r.id) || leakIds.has(r.id)) continue;
    if (inScope(r)) inScopeBase.push(r);
    else outScopeBase.push(r);
  }
  const gmOther = scoped
    .filter(r => gmIds.has(r.id) && !leakIds.has(r.id))
    .sort((a, b) => a.hw - b.hw);

  const grid1 = el('div', 'grid2');

  const scatterX = r => r.ah > 0 ? r.e / r.ah : null;
  const scatterY = r => r.ah > 0 ? r.th / r.ah : null;
  const maxRate = Math.max(
    1,
    ...res.perMachine.map(r => Math.max(scatterX(r) || 0, scatterY(r) || 0))
  ) * 1.06;

  chartCard(grid1, {
    title: 'Expected vs actual theo per open hour: most machines sit on the diagonal',
    how: 'Each dot is a machine over the selected period. Points above the line beat their location-and-game expectation; points below it lag. The GM\'s bottom ten are orange, statistically suspicious hit rates are red.',
    source: 'core.json md (machine-day sales), core.json configs (game math)',
    height: 390,
    build: () => {
      const data = [];
      if (outScopeBase.length) {
        data.push({
          type: 'scatter', mode: 'markers', x: outScopeBase.map(scatterX), y: outScopeBase.map(scatterY),
          name: 'Outside scope', marker: { color: t.muted, size: 5, opacity: 0.28 },
          text: outScopeBase.map(r => r.id),
          hovertemplate: '%{text}<br>Expected $%{x:.2f}/h<br>Actual $%{y:.2f}/h<extra></extra>'
        });
      }
      data.push({
        type: 'scatter', mode: 'markers', x: inScopeBase.map(scatterX), y: inScopeBase.map(scatterY),
        name: 'Machines', marker: { color: t.cat[0], size: 6, opacity: 0.6 },
        text: inScopeBase.map(r => r.id),
        hovertemplate: '%{text}<br>Expected $%{x:.2f}/h<br>Actual $%{y:.2f}/h<extra></extra>'
      });
      if (gmOther.length) {
        data.push({
          type: 'scatter', mode: 'markers', x: gmOther.map(scatterX), y: gmOther.map(scatterY),
          name: 'GM bottom 10', marker: { color: t.cat[1], size: 9, symbol: 'diamond' },
          text: gmOther.map(r => r.id),
          hovertemplate: '%{text}<br>Expected $%{x:.2f}/h<br>Actual $%{y:.2f}/h<extra></extra>'
        });
      }
      if (leaks.length) {
        data.push({
          type: 'scatter', mode: 'markers+text', x: leaks.map(scatterX), y: leaks.map(scatterY),
          name: 'Leak (|z| ≥ 5)', marker: { color: t.critical, size: 11, symbol: 'x' },
          text: leaks.map(r => r.id), textposition: 'top center',
          textfont: { color: t.critical, size: 10 },
          hovertemplate: '%{text}<br>Expected $%{x:.2f}/h<br>Actual $%{y:.2f}/h<extra></extra>'
        });
      }
      data.push({
        type: 'scatter', mode: 'lines', x: [0, maxRate], y: [0, maxRate],
        name: 'y = x', line: { color: t.axis, width: 2, dash: 'dash' },
        hoverinfo: 'skip'
      });
      return {
        data,
        layout: baseLayout({
          showlegend: true,
          margin: { l: 62, r: 16, t: 12, b: 62 },
          xaxis: { title: { text: 'Expected theo per available hour ($/h)' }, range: [0, maxRate] },
          yaxis: { title: { text: 'Actual theo per available hour ($/h)' }, range: [0, maxRate] },
          legend: { orientation: 'h', y: -0.28 }
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Machine', get: r => r.id },
        { label: 'Expected $/h', num: true, get: r => scatterX(r), fmt: v => fmtNum(v, 2) },
        { label: 'Actual $/h', num: true, get: r => scatterY(r), fmt: v => fmtNum(v, 2) }
      ],
      rows: res.perMachine.slice().sort((a, b) => (scatterY(a) || 0) - (scatterY(b) || 0))
    })
  });

  const funnelRows = res.perMachine.filter(r => r.zLuck !== null);
  chartCard(grid1, {
    title: 'The luck funnel: a handful of machines sit outside ±1.96 standard deviations',
    how: 'Theo is on the x-axis and the luck z-score is on the y-axis. The dashed lines are the 95% band; points outside them had house-win swings that are hard to explain as ordinary slot variance.',
    source: 'core.json md (theo, house win, v), core.json configs (variance multiplier)',
    height: 390,
    build: () => {
      const inside = funnelRows.filter(r => inScope(r));
      const outside = funnelRows.filter(r => !inScope(r));
      const data = [];
      if (outside.length) {
        data.push({
          type: 'scatter', mode: 'markers', x: outside.map(r => r.th), y: outside.map(r => r.zLuck),
          name: 'Outside scope', marker: { color: t.muted, size: 5, opacity: 0.28 },
          text: outside.map(r => r.id),
          hovertemplate: '%{text}<br>Theo $%{x:,.0f}<br>Luck z %{y:.2f}<extra></extra>'
        });
      }
      data.push({
        type: 'scatter', mode: 'markers', x: inside.map(r => r.th), y: inside.map(r => r.zLuck),
        name: 'Machines', marker: { color: t.cat[0], size: 6, opacity: 0.65 },
        text: inside.map(r => r.id),
        hovertemplate: '%{text}<br>Theo $%{x:,.0f}<br>Luck z %{y:.2f}<extra></extra>'
      });
      data.push({
        type: 'scatter', mode: 'lines', x: [0, Math.max(1, ...funnelRows.map(r => r.th))],
        y: [1.96, 1.96], name: '+1.96 sd', line: { color: t.axis, width: 2, dash: 'dot' },
        hoverinfo: 'skip'
      });
      data.push({
        type: 'scatter', mode: 'lines', x: [0, Math.max(1, ...funnelRows.map(r => r.th))],
        y: [-1.96, -1.96], name: '−1.96 sd', line: { color: t.axis, width: 2, dash: 'dot' },
        hoverinfo: 'skip'
      });
      return {
        data,
        layout: baseLayout({
          showlegend: true,
          margin: { l: 62, r: 16, t: 12, b: 58 },
          xaxis: { title: { text: 'Theoretical win in period ($)' } },
          yaxis: { title: { text: 'Luck z = (house win − theo) / sd' }, zerolinecolor: t.axis },
          legend: { orientation: 'h', y: -0.25 }
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Machine', get: r => r.id },
        { label: 'Theo $', num: true, get: r => r.th, fmt: v => fmtMoney(v) },
        { label: 'Luck $', num: true, get: r => r.luck, fmt: v => fmtSignedMoney(v) },
        { label: 'Luck z', num: true, get: r => r.zLuck, fmt: v => fmtNum(v, 2) }
      ],
      rows: funnelRows.slice().sort((a, b) => Math.abs(b.zLuck) - Math.abs(a.zLuck))
    })
  });
  root.appendChild(grid1);

  const hitRows = res.perMachine
    .filter(r => r.hitZ !== null)
    .slice()
    .sort((a, b) => Math.abs(b.hitZ) - Math.abs(a.hitZ))
    .slice(0, 15);
  const hitFlagged = hitRows.filter(r => Math.abs(r.hitZ) >= 5).length;
  chartCard(root, {
    title: 'Hit-rate screen: ' + (hitFlagged ? hitFlagged + ' machine(s) cross the |z| ≥ 5 leak threshold' : 'no machine crosses the |z| ≥ 5 leak threshold'),
    how: 'Bars are the hit-rate z-score (observed minus expected payout-positive spins, divided by its standard deviation). Big positive or negative values mean the payout process does not match the configured hit probability.',
    source: 'core.json md (paid spins, payout-positive spins), core.json configs (hit_p)',
    height: 330,
    build: () => {
      const flagged = hitRows.filter(r => Math.abs(r.hitZ) >= 5);
      const normal = hitRows.filter(r => Math.abs(r.hitZ) < 5);
      const x = hitRows.map(r => r.id);
      const data = [
        {
          type: 'bar', x: normal.map(r => r.id), y: normal.map(r => r.hitZ),
          name: 'Within threshold', marker: { color: t.cat[0] },
          hovertemplate: '%{x}<br>Hit z %{y:.2f}<extra></extra>'
        },
        {
          type: 'bar', x: flagged.map(r => r.id), y: flagged.map(r => r.hitZ),
          name: '|z| ≥ 5 (inspect)', marker: { color: t.critical },
          hovertemplate: '%{x}<br>Hit z %{y:.2f}<extra></extra>'
        }
      ];
      return {
        data,
        layout: baseLayout({
          showlegend: true,
          margin: { l: 58, r: 16, t: 12, b: 84 },
          xaxis: { title: { text: 'Machine' }, tickangle: -45, type: 'category', categoryorder: 'array', categoryarray: hitRows.map(r => r.id) },
          yaxis: { title: { text: 'Hit-rate z' }, zerolinecolor: t.axis },
          shapes: [
            { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 5, y1: 5, line: { color: t.critical, width: 1, dash: 'dot' } },
            { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: -5, y1: -5, line: { color: t.critical, width: 1, dash: 'dot' } }
          ],
          legend: { orientation: 'h', y: -0.32 }
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Machine', get: r => r.id },
        { label: 'Hit z', num: true, get: r => r.hitZ, fmt: v => fmtNum(v, 2) },
        { label: 'Paid spins', num: true, get: r => r.sp, fmt: v => fmtNum(v, 0) },
        { label: 'Payout-positive', num: true, get: r => r.hs, fmt: v => fmtNum(v, 0) },
        { label: 'Expected hits', num: true, get: r => r.sp * r.hitP, fmt: v => fmtNum(v, 0) }
      ],
      rows: hitRows
    })
  });

  /* Full sortable machine table */
  const card = el('section', 'card');
  append(card,
    el('h2', null, 'Every machine, every supplied cost, and what is left after costs'),
    el('p', 'how', 'Sort any column or search by machine, manufacturer, theme, zone, bank or verdict. Contribution is house win minus the supplied cost (lease, service, power and repair) in the period.'),
    el('p', 'source', 'Source: core.json md, core.json machines/configs, ops.json faults (downtime hours)')
  );
  const tools = el('div', 'table-tools');
  const searchLabel = el('label', null, 'Search');
  const search = el('input', null);
  search.type = 'search';
  search.placeholder = 'M-1234, theme, zone, verdict…';
  search.value = state.mSearch;
  search.setAttribute('aria-label', 'Search the machine table');
  const rowCount = el('span', 'row-count');
  append(tools, searchLabel, search, rowCount);
  card.appendChild(tools);
  const tableHost = el('div');
  card.appendChild(tableHost);
  root.appendChild(card);

  const machineColumns = [
    { key: 'id', label: 'Machine', get: r => r.id },
    { key: 'mfr', label: 'Manufacturer', get: r => r.mfr },
    { key: 'zoneName', label: 'Zone / bank', get: r => r.zoneName + ' · ' + r.bank, wrap: true },
    { key: 'theme', label: 'Game (theme · RTP)', get: r => r.theme + ' · ' + fmtPct(r.rtp, 0), wrap: true },
    { key: 'days', label: 'Days', num: true, get: r => r.days },
    { key: 'hw', label: 'House win', num: true, get: r => r.hw, fmt: v => fmtMoney(v) },
    { key: 'th', label: 'Theo', num: true, get: r => r.th, fmt: v => fmtMoney(v) },
    { key: 'luck', label: 'Luck $', num: true, get: r => r.luck, fmt: v => fmtSignedMoney(v) },
    { key: 'zLuck', label: 'Luck z', num: true, get: r => r.zLuck, fmt: v => fmtNum(v, 2) },
    { key: 'avail', label: 'Avail %', num: true, get: r => r.avail, fmt: v => fmtPct(v) },
    { key: 'location', label: 'Location factor', num: true, get: r => r.location, fmt: v => fmtNum(v, 3) },
    { key: 'game', label: 'Game factor', num: true, get: r => r.game, fmt: v => fmtNum(v, 3) },
    { key: 'U', label: 'Machine U [80%]', num: true, get: r => r.U, fmt: (v, r) => fmtNum(r.U, 3) + ' [' + fmtNum(r.lo80, 3) + '–' + fmtNum(r.hi80, 3) + ']' },
    { key: 'hitZ', label: 'Hit z', num: true, get: r => r.hitZ, fmt: v => fmtNum(v, 2) },
    { key: 'verdict', label: 'Verdict', get: r => r.verdict, sort: r => r.verdict, render: r => chip(r.verdict, r.status) },
    { key: 'faults', label: 'Faults', num: true, get: r => r.faults, fmt: v => fmtNum(v, 0) },
    { key: 'downH', label: 'Downtime h', num: true, get: r => r.downH, fmt: v => fmtNum(v, 1) },
    { key: 'cost', label: 'Supplied cost', num: true, get: r => r.cost, fmt: v => fmtMoney(v) },
    { key: 'contribution', label: 'Contribution', num: true, get: r => r.contribution, fmt: v => fmtMoney(v) }
  ];

  function refreshMachineTable() {
    const q = state.mSearch.trim().toLowerCase();
    let rows = scoped.slice();
    if (q) {
      rows = rows.filter(r => {
        const hay = [r.id, r.mfr, r.zoneName, r.bank, r.theme, r.verdict, r.zone].join(' ').toLowerCase();
        return hay.includes(q);
      });
    }
    const s = state.mSort;
    const sortCol = machineColumns.find(c => c.key === s.key) || machineColumns[5];
    rows.sort((a, b) => {
      const av = sortCol.sort ? sortCol.sort(a) : (sortCol.get ? sortCol.get(a) : a[sortCol.key]);
      const bv = sortCol.sort ? sortCol.sort(b) : (sortCol.get ? sortCol.get(b) : b[sortCol.key]);
      return comparisonValue(av, bv) * (s.dir === 'asc' ? 1 : -1);
    });
    rowCount.textContent = rows.length + ' of ' + scoped.length + ' machines';
    clear(tableHost);
    const wrap = el('div', 'table-wrap');
    const table = el('table');
    const cap = el('caption', 'sr-only', 'Full machine table for the selected period and scope');
    table.appendChild(cap);
    const thead = el('thead');
    const tr = el('tr');
    for (const col of machineColumns) {
      const th = el('th', col.num ? 'num' : (col.wrap ? 'wrap' : null));
      th.scope = 'col';
      const btn = el('button', 'sort-btn', col.label);
      btn.type = 'button';
      const active = state.mSort.key === col.key;
      btn.setAttribute('aria-label', 'Sort by ' + col.label);
      if (active) btn.appendChild(el('span', 'sort-ind', state.mSort.dir === 'asc' ? '▲' : '▼'));
      btn.addEventListener('click', () => {
        if (state.mSort.key === col.key) state.mSort.dir = state.mSort.dir === 'asc' ? 'desc' : 'asc';
        else state.mSort = { key: col.key, dir: 'asc' };
        refreshMachineTable();
      });
      th.appendChild(btn);
      tr.appendChild(th);
    }
    thead.appendChild(tr);
    table.appendChild(thead);
    const tbody = el('tbody');
    for (const row of rows) {
      const trr = el('tr');
      for (const col of machineColumns) {
        const td = el('td', col.num ? 'num' : (col.wrap ? 'wrap' : null));
        const v = col.get ? col.get(row) : row[col.key];
        if (col.render) td.appendChild(col.render(row));
        else td.textContent = col.fmt ? col.fmt(v, row) : formatGeneric(v);
        trr.appendChild(td);
      }
      tbody.appendChild(trr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    tableHost.appendChild(wrap);
  }

  search.addEventListener('input', () => {
    state.mSearch = search.value;
    refreshMachineTable();
  });
  refreshMachineTable();
};

/* ---- 6.3 Demand ---- */

RENDERERS.demand = function renderDemand(root, res) {
  root.appendChild(storyCard('demand'));
  const t = tokens();
  const { lo, hi } = periodBounds();
  const daily = dailyScoped(lo, hi);
  let running = 0;
  const mean7 = daily.ci.map((v, j) => {
    running += v;
    if (j >= 7) running -= daily.ci[j - 7];
    return running / Math.min(j + 1, 7);
  });

  const events = eventsInPeriod(state.from, state.to);
  const closureFrom = '2025-03-03';
  const closureTo = '2025-04-06';
  const visibleClosure = closureFrom <= state.to && closureTo >= state.from;

  chartCard(root, {
    title: 'Daily coin-in in the period, with events and the walkway closure marked',
    how: 'Solid line: daily floor coin-in for the current zone/bank scope. Dashed orange line: trailing 7-day mean. Shaded bands mark events from the calendar and the W-ENT-B40 walkway closure.',
    source: 'core.json pd.ci (property day), core.json events and walkways',
    height: 380,
    build: () => {
      const shapes = [];
      const annotations = [];
      events.forEach((e, i) => {
        const a = e.start < state.from ? state.from : e.start;
        const b = e.end > state.to ? state.to : e.end;
        if (a > b) return;
        shapes.push({
          type: 'rect', xref: 'x', yref: 'paper', x0: a, x1: b, y0: 0, y1: 1,
          fillcolor: t.cat[0], opacity: 0.07, line: { width: 0 }, layer: 'below'
        });
        const mid = addDays(a, Math.floor(Math.max(0, daysBetween(a, b)) / 2));
        annotations.push({
          x: mid, y: 1.015 + (i % 2) * 0.07, yref: 'paper', text: e.name.length > 26 ? e.name.slice(0, 25) + '…' : e.name,
          showarrow: false, font: { size: 9, color: t.ink2 }, xanchor: 'center'
        });
      });
      if (visibleClosure) {
        const a = closureFrom < state.from ? state.from : closureFrom;
        const b = closureTo > state.to ? state.to : closureTo;
        shapes.push({
          type: 'rect', xref: 'x', yref: 'paper', x0: a, x1: b, y0: 0, y1: 1,
          fillcolor: t.cat[1], opacity: 0.12, line: { width: 0 }, layer: 'below'
        });
        annotations.push({
          x: addDays(a, Math.max(0, Math.floor(daysBetween(a, b) / 2))), y: 1.16, yref: 'paper',
          text: 'Walkway W-ENT-B40 closed', showarrow: false, font: { size: 9, color: t.cat[1] }
        });
      }
      const data = [
        traceLine(daily.dates, daily.ci, 'Daily coin-in', t.cat[0],
          '%{x|%b %d}<br>Coin-in $%{y:,.0f}<extra></extra>'),
        traceLine(daily.dates, mean7, '7-day mean', t.cat[1],
          '%{x|%b %d}<br>7-day mean $%{y:,.0f}<extra></extra>', { line: { width: 2, color: t.cat[1], dash: 'dash' } })
      ];
      return {
        data,
        layout: baseLayout({
          showlegend: true,
          hovermode: 'x unified',
          margin: { l: 70, r: 18, t: 68, b: 48 },
          xaxis: { type: 'date', title: { text: 'Gaming date' } },
          yaxis: { title: { text: 'Coin-in ($)' }, tickformat: '~s' },
          shapes, annotations,
          legend: { orientation: 'h', y: -0.16 }
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Date', get: r => r.date },
        { label: 'Coin-in', num: true, get: r => r.ci, fmt: v => fmtMoney(v) },
        { label: '7-day mean', num: true, get: r => r.m7, fmt: v => fmtMoney(v) }
      ],
      rows: daily.dates.map((date, i) => ({ date, ci: daily.ci[i], m7: mean7[i] }))
    })
  });

  const weekly = weeksInPeriod(DATA.analysis.closure.weekly, state.from, state.to);
  const periods = DATA.analysis.closure.periods;
  const periodPills = el('div', 'pillrow');
  append(periodPills,
    el('span', 'pill', 'Pre: ' + nf(3).format(periods.pre_ratio)),
    el('span', 'pill', 'Closure: ' + nf(3).format(periods.closure_ratio)),
    el('span', 'pill', 'Post: ' + nf(3).format(periods.post_ratio))
  );
  chartCard(root, {
    title: 'The B40-to-rest theo ratio fell during the walkway closure and recovered after it reopened',
    how: 'Each point is one ISO week: Back Forty theo per available hour divided by the rest of the floor. The orange band is the closure; the dashed steps are the period ratios of sums.',
    source: 'analysis.json closure.weekly and closure.periods (prepared_daily_view)',
    footer: periodPills,
    height: 330,
    build: () => {
      const shapes = [];
      if (visibleClosure) {
        shapes.push({
          type: 'rect', xref: 'x', yref: 'paper', x0: closureFrom, x1: closureTo, y0: 0, y1: 1,
          fillcolor: t.cat[1], opacity: 0.12, line: { width: 0 }, layer: 'below'
        });
      }
      const addPeriodLine = (a, b, value) => {
        const x0 = a < state.from ? state.from : a;
        const x1 = b > state.to ? state.to : b;
        if (x0 > x1) return;
        shapes.push({
          type: 'line', xref: 'x', yref: 'y', x0, x1, y0: value, y1: value,
          line: { color: t.ink2, width: 1, dash: 'dot' }
        });
      };
      addPeriodLine('2025-01-01', '2025-03-02', periods.pre_ratio);
      addPeriodLine('2025-03-03', '2025-04-06', periods.closure_ratio);
      addPeriodLine('2025-04-07', '2025-06-30', periods.post_ratio);
      return {
        data: [
          traceLine(weekly.map(w => w.week_start), weekly.map(w => w.ratio), 'B40 ÷ rest theo/h', t.cat[0],
            '%{x|%b %d}<br>Ratio %{y:.3f}<extra></extra>', { mode: 'lines+markers', marker: { size: 5, color: t.cat[0] } })
        ],
        layout: baseLayout({
          hovermode: 'x unified',
          margin: { l: 62, r: 18, t: 14, b: 48 },
          xaxis: { type: 'date', title: { text: 'Week starting (Monday)' } },
          yaxis: { title: { text: 'B40 ÷ rest theo per available hour' } },
          shapes
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Week start', get: r => r.week_start },
        { label: 'B40 $/h', num: true, get: r => r.b40_rate, fmt: v => fmtNum(v, 2) },
        { label: 'Rest $/h', num: true, get: r => r.rest_rate, fmt: v => fmtNum(v, 2) },
        { label: 'Ratio', num: true, get: r => r.ratio, fmt: v => fmtNum(v, 3) }
      ],
      rows: weekly
    })
  });

  /* Zone traffic, with a local multi-select (default B40 + Main Entrance). */
  const defaultZones = state.zone !== 'all' ? [state.zone] : ['Z-B40', 'Z-ENT'];
  if (!Array.isArray(state.trafficZones) || !state.trafficZones.length) {
    state.trafficZones = defaultZones.filter(z => DATA.derived.zoneById[z]);
  }
  const trafficSelect = el('select');
  trafficSelect.multiple = true;
  trafficSelect.setAttribute('aria-label', 'Zones to show in the traffic chart');
  for (const z of DATA.core.zones) {
    const opt = new Option(z.name, z.id);
    opt.selected = state.trafficZones.includes(z.id);
    trafficSelect.appendChild(opt);
  }
  const trafficControls = el('div', 'inline-filters');
  const tf = el('div', 'fgroup');
  append(tf, el('label', null, 'Traffic zones (multi-select)'), trafficSelect);
  trafficControls.appendChild(tf);
  trafficSelect.addEventListener('change', () => {
    state.trafficZones = Array.from(trafficSelect.selectedOptions).map(o => o.value);
    if (!state.trafficZones.length) state.trafficZones = ['Z-B40', 'Z-ENT'];
    render();
  });

  const traffic = weeksInPeriod(DATA.analysis.closure.traffic_weekly, state.from, state.to)
    .filter(x => state.trafficZones.includes(x.zone_id));
  chartCard(root, {
    title: 'Sensor traffic: Back Forty footfall is the series to watch around the closure',
    how: 'Mean daily entries per working sensor, by ISO week, for the zones selected above. Gaps are weeks where a zone had no usable counter-hours.',
    source: 'analysis.json closure.traffic_weekly (zone_traffic_hourly)',
    controls: trafficControls,
    height: 340,
    build: () => {
      const data = state.trafficZones.map((zid, i) => {
        const rows = traffic.filter(x => x.zone_id === zid).sort((a, b) => a.week_start < b.week_start ? -1 : 1);
        const zone = DATA.derived.zoneById[zid];
        return traceLine(rows.map(r => r.week_start), rows.map(r => r.entries_per_sensor_day),
          zone ? zone.name : zid, t.cat[i % 8],
          '%{x|%b %d}<br>' + (zone ? zone.name : zid) + ': %{y:,.0f} entries/sensor-day<extra></extra>',
          { mode: 'lines+markers', marker: { size: 5, color: t.cat[i % 8] } });
      });
      const shapes = visibleClosure ? [{
        type: 'rect', xref: 'x', yref: 'paper', x0: closureFrom, x1: closureTo, y0: 0, y1: 1,
        fillcolor: t.cat[1], opacity: 0.12, line: { width: 0 }, layer: 'below'
      }] : [];
      return {
        data,
        layout: baseLayout({
          showlegend: true, hovermode: 'x unified',
          margin: { l: 66, r: 18, t: 14, b: 48 },
          xaxis: { type: 'date', title: { text: 'Week starting (Monday)' } },
          yaxis: { title: { text: 'Entries per sensor-day' } },
          shapes
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Zone', get: r => (DATA.derived.zoneById[r.zone_id] || { name: r.zone_id }).name },
        { label: 'Week start', get: r => r.week_start },
        { label: 'Entries / sensor-day', num: true, get: r => r.entries_per_sensor_day, fmt: v => fmtNum(v, 1) }
      ],
      rows: traffic
    })
  });

  const grid = el('div', 'grid2');

  const weekdayOrder = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const wdAgg = new Map();
  daily.dates.forEach((date, j) => {
    const wd = DATA.core.weekday[lo + j];
    if (!wdAgg.has(wd)) wdAgg.set(wd, { n: 0, ci: 0 });
    const o = wdAgg.get(wd);
    o.n += 1;
    o.ci += daily.ci[j];
  });
  const wdRows = weekdayOrder.filter(w => wdAgg.has(w)).map(w => {
    const o = wdAgg.get(w);
    return { weekday: w, days: o.n, meanCi: o.n ? o.ci / o.n : 0 };
  });
  chartCard(grid, {
    title: 'Weekday demand: the property earns more per gaming day on weekends',
    how: 'Mean daily coin-in for each weekday in the selected period and scope. Bars are means, not totals, so months with different day counts stay comparable.',
    source: 'core.json pd.ci, core.json weekday',
    height: 310,
    build: () => ({
      data: [traceBar(wdRows.map(r => r.weekday), wdRows.map(r => r.meanCi), 'Mean coin-in', t.cat[0],
        '%{x}<br>Mean coin-in $%{y:,.0f}<extra></extra>')],
      layout: baseLayout({
        margin: { l: 70, r: 16, t: 12, b: 44 },
        xaxis: { title: { text: 'Weekday' } },
        yaxis: { title: { text: 'Mean coin-in ($)' }, tickformat: '~s' }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Weekday', get: r => r.weekday },
        { label: 'Days', num: true, get: r => r.days, fmt: v => fmtNum(v, 0) },
        { label: 'Mean coin-in', num: true, get: r => r.meanCi, fmt: v => fmtMoney(v) }
      ],
      rows: wdRows
    })
  });

  const evRows = events.map(e => {
    const lift = (DATA.analysis.events || []).find(x => x.id === e.id);
    return lift ? Object.assign({}, e, lift) : null;
  }).filter(Boolean);
  chartCard(grid, {
    title: events.length
      ? 'Event weeks: ' + events.length + ' calendar event(s) overlap the selected period'
      : 'No calendar event overlaps the selected period',
    how: 'Mean daily property coin-in during the event versus the same weekdays in the four weeks before it. A positive lift is correlation, not proof that the event caused the spend.',
    source: 'analysis.json events (property_day and events)',
    height: 310,
    build: () => ({
      data: [traceBar(evRows.map(x => x.name), evRows.map(x => x.lift_pct * 100), 'Lift %', t.cat[1],
        '%{x}<br>Lift %{y:+.1f}%<extra></extra>')],
      layout: baseLayout({
        margin: { l: 58, r: 16, t: 12, b: 92 },
        xaxis: { title: { text: 'Event' }, tickangle: -35, type: 'category' },
        yaxis: { title: { text: 'Coin-in lift (%)' } }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Event', get: r => r.name, wrap: true },
        { label: 'Type', get: r => r.type },
        { label: 'Dates', get: r => r.start + ' – ' + r.end },
        { label: 'Lift %', num: true, get: r => r.lift_pct, fmt: v => fmtPct(v, 1) },
        { label: 'Lift $/day', num: true, get: r => r.lift_usd_per_day, fmt: v => fmtMoney(v, 2) },
        { label: 'Days', num: true, get: r => r.n_days, fmt: v => fmtNum(v, 0) }
      ],
      rows: evRows
    })
  });
  root.appendChild(grid);

  /* Zone table in P */
  const zoneAgg = new Map();
  const md = DATA.core.md;
  const d = DATA.derived;
  for (let i = 0; i < md.d.length; i++) {
    const di = md.d[i];
    if (di < lo || di > hi) continue;
    if (state.bank !== 'all' && d.rowBankId[i] !== state.bank) continue;
    const zid = d.rowZoneId[i];
    if (state.zone !== 'all' && zid !== state.zone) continue;
    if (!zoneAgg.has(zid)) zoneAgg.set(zid, { zid, ah: 0, sh: 0, oh: 0, th: 0, ci: 0, machines: new Set() });
    const o = zoneAgg.get(zid);
    o.ah += md.ah[i];
    o.sh += md.sh[i];
    o.oh += md.oh[i];
    o.th += md.th[i];
    o.ci += md.ci[i];
    o.machines.add(md.m[i]);
  }
  const zoneRows = Array.from(zoneAgg.values()).map(o => ({
    zone: (DATA.derived.zoneById[o.zid] || { name: o.zid }).name,
    machines: o.machines.size,
    theoRate: o.ah > 0 ? o.th / o.ah : 0,
    occ: o.ah > 0 ? o.oh / o.ah : 0,
    avail: o.sh > 0 ? o.ah / o.sh : 0,
    ci: o.ci
  })).sort((a, b) => b.theoRate - a.theoRate);
  const zoneCard = el('section', 'card');
  append(zoneCard,
    el('h2', null, 'Zone table: where an available hour earns the most'),
    el('p', 'how', 'Theo per available hour, occupancy and availability by zone for the selected period. The bank filter narrows the rows to one bank.'),
    el('p', 'source', 'core.json md, core.json zones and banks')
  );
  renderTable(zoneCard, {
    columns: [
      { label: 'Zone', get: r => r.zone },
      { label: 'Machines', num: true, get: r => r.machines, fmt: v => fmtNum(v, 0) },
      { label: 'Theo / avail. hour', num: true, get: r => r.theoRate, fmt: v => fmtRate(v) },
      { label: 'Occupancy', num: true, get: r => r.occ, fmt: v => fmtPct(v) },
      { label: 'Availability', num: true, get: r => r.avail, fmt: v => fmtPct(v) },
      { label: 'Coin-in', num: true, get: r => r.ci, fmt: v => fmtMoney(v) }
    ],
    rows: zoneRows,
    caption: 'Zone performance in the selected period'
  });
  root.appendChild(zoneCard);
};

/* ---- 6.4 Downtime ---- */

RENDERERS.downtime = function renderDowntime(root, res) {
  root.appendChild(storyCard('downtime'));
  const t = tokens();
  const { lo, hi } = periodBounds();
  const dow = DATA.analysis.downtime;
  const byDate = dow.by_date;
  let downH = 0;
  let lost = 0;
  for (let j = lo; j <= hi; j++) { downH += byDate.down_h[j]; lost += byDate.lost_theo[j]; }
  const theoPeriod = sum(DATA.core.pd.th.slice(lo, hi + 1));
  const share = theoPeriod > 0 ? lost / theoPeriod : null;

  const kpis = el('div', 'kpis');
  append(kpis,
    makeKpi('Downtime hours', fmtNum(downH, 0) + ' h', 'Property-wide, machine-hours lost'),
    makeKpi('Lost theo (upper bound)', fmtCompactUSD(lost), fmtMoney(lost)),
    makeKpi('Share of theo', share !== null ? fmtPct(share, 2) : '—', 'Assumes no substitution'),
    makeKpi('Fault tickets in period', fmtNum(DATA.ops.faults.d.filter(x => x >= lo && x <= hi).length, 0), 'ops.json fault_repair')
  );
  root.appendChild(kpis);
  root.appendChild(el('p', 'muted', 'Downtime KPIs and the daily/hourly charts are property-wide and follow the period filter; the zone/bank scope applies to machine-level lists and the top-15 table.'));

  const dates = DATA.core.dates.slice(lo, hi + 1);
  chartCard(root, {
    title: 'Lost theo from downtime is lumpy, not a steady leak',
    how: 'Daily lost theoretical win for the selected period: downtime hours multiplied by each machine\'s theo rate at that local hour. This is an upper bound because players may move to another machine.',
    source: 'analysis.json downtime.by_date (machine_hour)',
    height: 320,
    build: () => ({
      data: [traceBar(dates, byDate.lost_theo.slice(lo, hi + 1), 'Lost theo', t.cat[0],
        '%{x|%b %d}<br>Lost theo $%{y:,.0f}<extra></extra>')],
      layout: baseLayout({
        hovermode: 'x unified',
        margin: { l: 64, r: 16, t: 12, b: 48 },
        xaxis: { type: 'date', title: { text: 'Gaming date' } },
        yaxis: { title: { text: 'Lost theo ($)' }, tickformat: '~s' }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Date', get: r => r.date },
        { label: 'Downtime h', num: true, get: r => r.downH, fmt: v => fmtNum(v, 2) },
        { label: 'Lost theo', num: true, get: r => r.lost, fmt: v => fmtMoney(v) }
      ],
      rows: dates.map((date, j) => ({ date, downH: byDate.down_h[lo + j], lost: byDate.lost_theo[lo + j] }))
    })
  });

  const hourRows = dow.by_hour.down_h.map((h, i) => ({
    hour: i, downH: h, lost: dow.by_hour.lost_theo[i]
  }));
  const waitAgg = new Array(24).fill(0).map(() => ({ n: 0, wait: 0 }));
  DATA.ops.faults.hour.forEach((h, j) => {
    const di = DATA.ops.faults.d[j];
    if (di < lo || di > hi) return;
    const rec = res.byIdx[DATA.ops.faults.m[j]];
    if (!rec || !inScope(rec)) return;
    waitAgg[h].n += 1;
    waitAgg[h].wait += DATA.ops.faults.wait_h[j] || 0;
  });
  const waitRows = waitAgg.map((o, h) => ({ hour: h, n: o.n, mean: o.n ? o.wait / o.n : null }));

  const grid = el('div', 'grid2');
  chartCard(grid, {
    title: 'Downtime clusters in the late-night and afternoon hours',
    how: 'Lost theo by local hour of the fault across the selected period. Bars sum to the period lost-theo upper bound.',
    source: 'analysis.json downtime.by_hour (machine_hour)',
    height: 310,
    build: () => ({
      data: [traceBar(hourRows.map(r => r.hour + ':00'), hourRows.map(r => r.lost), 'Lost theo', t.cat[0],
        '%{x}<br>Lost theo $%{y:,.0f}<extra></extra>')],
      layout: baseLayout({
        margin: { l: 64, r: 16, t: 12, b: 54 },
        xaxis: { title: { text: 'Local hour fault opened' }, tickangle: -45 },
        yaxis: { title: { text: 'Lost theo ($)' }, tickformat: '~s' }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Hour', num: true, get: r => r.hour, fmt: v => String(v).padStart(2, '0') + ':00' },
        { label: 'Downtime h', num: true, get: r => r.downH, fmt: v => fmtNum(v, 2) },
        { label: 'Lost theo', num: true, get: r => r.lost, fmt: v => fmtMoney(v) }
      ],
      rows: hourRows
    })
  });

  chartCard(grid, {
    title: 'Repair waits are longest at night and shortest in the early morning',
    how: 'Mean hours from fault opened to work started, by local hour, for fault tickets in the selected period. Hover shows the ticket count behind each bar.',
    source: 'ops.json faults (wait_h, hour)',
    height: 310,
    build: () => ({
      data: [traceBar(waitRows.map(r => r.hour + ':00'), waitRows.map(r => r.mean), 'Mean wait', t.cat[2],
        '%{x}<br>Mean wait %{y:.2f} h<br>n=%{customdata}<extra></extra>', { customdata: waitRows.map(r => r.n) })],
      layout: baseLayout({
        margin: { l: 62, r: 16, t: 12, b: 54 },
        xaxis: { title: { text: 'Local hour fault opened' }, tickangle: -45 },
        yaxis: { title: { text: 'Mean repair wait (hours)' } }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Hour', num: true, get: r => r.hour, fmt: v => String(v).padStart(2, '0') + ':00' },
        { label: 'Faults', num: true, get: r => r.n, fmt: v => fmtNum(v, 0) },
        { label: 'Mean wait h', num: true, get: r => r.mean, fmt: v => fmtNum(v, 2) }
      ],
      rows: waitRows
    })
  });
  root.appendChild(grid);

  /* Faults per machine-month by manufacturer, months intersecting P. */
  const months = monthsInPeriod(state.from, state.to);
  const monthIdx = new Map();
  DATA.players.months.forEach((m, i) => monthIdx.set(m, i));
  const machineMonths = new Map();
  {
    const mmd = DATA.core.md;
    const mdDates = DATA.core.dates;
    for (let i = 0; i < mmd.d.length; i++) {
      const month = mdDates[mmd.d[i]].slice(0, 7);
      if (!months.includes(month)) continue;
      const mfr = DATA.core.machines[mmd.m[i]].mfr;
      const key = mfr + '|' + month;
      if (!machineMonths.has(key)) machineMonths.set(key, new Set());
      machineMonths.get(key).add(mmd.m[i]);
    }
  }
  const mfrRows = dow.by_mfr_month
    .filter(r => months.includes(r.month))
    .map(r => {
      const machineN = (machineMonths.get(r.mfr + '|' + r.month) || new Set()).size;
      return {
        mfr: r.mfr, month: r.month, faults: r.faults, machines: machineN,
        perMachineMonth: machineN > 0 ? r.faults / machineN : 0,
        downH: r.down_h, lost: r.lost_theo, repair: r.repair_cost
      };
    });
  const mfrs = Array.from(new Set(mfrRows.map(r => r.mfr)));
  chartCard(root, {
    title: 'Faults per machine-month by manufacturer: the mix matters more than the total',
    how: 'Fault tickets per active machine in each manufacturer-month, for months overlapping the selected period. A bar is one manufacturer-month; compare within manufacturer across time.',
    source: 'analysis.json downtime.by_mfr_month, core.json machines and md (active machine count)',
    height: 330,
    build: () => ({
      data: mfrs.map((mfr, i) => {
        const rows = mfrRows.filter(r => r.mfr === mfr);
        return traceBar(rows.map(r => r.month), rows.map(r => r.perMachineMonth), mfr, t.cat[i % 8],
          '%{x}<br>' + mfr + ': %{y:.2f} faults per machine-month<extra></extra>');
      }),
      layout: baseLayout({
        barmode: 'group', showlegend: true, hovermode: 'x unified',
        margin: { l: 64, r: 16, t: 12, b: 54 },
        xaxis: { title: { text: 'Month' }, type: 'category' },
        yaxis: { title: { text: 'Faults per machine-month' } },
        legend: { orientation: 'h', y: -0.22 }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Manufacturer', get: r => r.mfr },
        { label: 'Month', get: r => r.month },
        { label: 'Faults', num: true, get: r => r.faults, fmt: v => fmtNum(v, 0) },
        { label: 'Machines', num: true, get: r => r.machines, fmt: v => fmtNum(v, 0) },
        { label: 'Faults / machine-month', num: true, get: r => r.perMachineMonth, fmt: v => fmtNum(v, 2) },
        { label: 'Lost theo', num: true, get: r => r.lost, fmt: v => fmtMoney(v) }
      ],
      rows: mfrRows
    })
  });

  const grid2 = el('div', 'grid2');

  /* Staffing table card (plain table, no chart). */
  const staffCard = el('section', 'card');
  append(staffCard,
    el('h2', null, 'Staffing shortfalls coincide with longer repair waits'),
    el('p', 'how', 'Fault tickets grouped by shift and whether the slot-tech roster was understaffed. Mean wait is hours from fault opened to work started.'),
    el('p', 'source', 'analysis.json staffing.by_shift (shift_roster + operations)')
  );
  renderTable(staffCard, {
    columns: [
      { label: 'Shift', get: r => r.shift },
      { label: 'Understaffed', get: r => r.understaffed ? chip('Yes', 'warning') : chip('No', 'good') },
      { label: 'Faults', num: true, get: r => r.n, fmt: v => fmtNum(v, 0) },
      { label: 'Mean wait h', num: true, get: r => r.mean_wait_h, fmt: v => fmtNum(v, 2) },
      { label: 'Median wait h', num: true, get: r => r.median_wait_h, fmt: v => fmtNum(v, 2) },
      { label: 'Mean actual HC', num: true, get: r => r.mean_actual_headcount, fmt: v => fmtNum(v, 2) }
    ],
    rows: DATA.analysis.staffing.by_shift
  });
  const reg = DATA.analysis.staffing.regression;
  const regParams = (reg.params || []).map(p => p.term + ' ' + nf(3).format(p.coef) + ' (SE ' + nf(3).format(p.se) + ', p ' + nf(3).format(p.p) + ')').join('; ');
  staffCard.appendChild(el('p', 'source', 'Regression: wait_h ~ C(shift) + actual_headcount; ' + reg.hc + ' SE, n=' + reg.n + ', R²=' + nf(3).format(reg.r2) + '. ' + regParams));
  grid2.appendChild(staffCard);

  const roster = DATA.analysis.staffing.roster_month.filter(r => months.includes(r.month));
  const shifts = Array.from(new Set(roster.map(r => r.shift)));
  chartCard(grid2, {
    title: 'The day-shift technician roster was short in April and May',
    how: 'Monthly mean planned (dashed) and actual (solid) slot-tech headcount by shift. The gap is the natural experiment behind the staffing evidence.',
    source: 'analysis.json staffing.roster_month (shift_roster)',
    height: 330,
    build: () => {
      const data = [];
      shifts.forEach((shift, i) => {
        const rows = roster.filter(r => r.shift === shift);
        data.push(traceLine(rows.map(r => r.month), rows.map(r => r.actual_mean), shift, t.cat[i % 8],
          '%{x}<br>' + shift + ' actual: %{y:.2f}<extra></extra>', { mode: 'lines+markers', marker: { size: 5, color: t.cat[i % 8] } }));
        data.push(traceLine(rows.map(r => r.month), rows.map(r => r.planned_mean), shift + ' planned', t.cat[i % 8],
          '%{x}<br>' + shift + ' planned: %{y:.2f}<extra></extra>',
          { line: { width: 2, color: t.cat[i % 8], dash: 'dash' }, showlegend: false }));
      });
      return {
        data,
        layout: baseLayout({
          showlegend: true, hovermode: 'x unified',
          margin: { l: 54, r: 16, t: 12, b: 54 },
          xaxis: { title: { text: 'Month' }, type: 'category' },
          yaxis: { title: { text: 'Mean technicians on roster' } },
          legend: { orientation: 'h', y: -0.22 }
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Month', get: r => r.month },
        { label: 'Shift', get: r => r.shift },
        { label: 'Planned mean', num: true, get: r => r.planned_mean, fmt: v => fmtNum(v, 2) },
        { label: 'Actual mean', num: true, get: r => r.actual_mean, fmt: v => fmtNum(v, 2) }
      ],
      rows: roster
    })
  });

  const sub = DATA.analysis.substitution;
  const subCard = el('section', 'card');
  append(subCard,
    el('h2', null, 'Substitution test: neighbours do not absorb the lost play'),
    el('p', 'how', 'If players simply moved to another machine in the same bank, occupancy of the other machines would rise when one is down. The matched difference is near zero.')
  );
  const stats = el('div', 'statgrid');
  append(stats,
    makeStat('Treated bank-hours', fmtNum(sub.treated_bank_hours, 0), 'Bank-hours with a machine down ≥ 30 min'),
    makeStat('Mean occupancy difference', fmtPct(sub.weighted_mean_diff_occ, 2), 'Other machines, down vs not down'),
    makeStat('Baseline occupancy', fmtPct(sub.baseline_occ, 2), 'Matched bank × hour × weekday cells'),
    makeStat('Ratio to baseline', fmtPct(sub.ratio, 2), '95% CI ' + fmtPct(sub.ci_low, 2) + ' to ' + fmtPct(sub.ci_high, 2))
  );
  subCard.appendChild(stats);
  subCard.appendChild(el('p', 'source', 'Source: analysis.json substitution (machine_hour, 1000 bootstrap resamples, seed 42)'));
  root.appendChild(grid2);
  root.appendChild(subCard);

  /* Top 15 machines by lost theo in P */
  const lostByMachine = new Map();
  const faults = DATA.ops.faults;
  for (let j = 0; j < faults.m.length; j++) {
    const di = faults.d[j];
    if (di < lo || di > hi) continue;
    const rec = res.byIdx[faults.m[j]];
    if (!rec || !inScope(rec)) continue;
    const value = (faults.down_h[j] || 0) * rec.theoRate;
    if (!lostByMachine.has(rec.id)) lostByMachine.set(rec.id, { rec, downH: 0, lost: 0, faults: 0 });
    const o = lostByMachine.get(rec.id);
    o.downH += faults.down_h[j] || 0;
    o.lost += value;
    o.faults += 1;
  }
  const lostRows = Array.from(lostByMachine.values())
    .sort((a, b) => b.lost - a.lost)
    .slice(0, 15)
    .map(o => ({ id: o.rec.id, zone: o.rec.zoneName, bank: o.rec.bank, downH: o.downH, faults: o.faults, theoRate: o.rec.theoRate, lost: o.lost }));

  if (lostRows.length) {
    chartCard(root, {
      title: 'The 15 machines that lost the most theo to downtime in this period',
      how: 'Lost theo = fault downtime hours × the machine\'s theo per available hour in the selected period. This is an upper bound and does not include any play that moved elsewhere.',
      source: 'ops.json faults, core.json md (machine theo rate), model.json A.k',
      height: 430,
      build: () => ({
        data: [traceBar(lostRows.map(r => r.lost), lostRows.map(r => r.id), 'Lost theo', t.cat[1],
          '%{y}<br>Lost theo $%{x:,.0f}<extra></extra>', { orientation: 'h' })],
        layout: baseLayout({
          margin: { l: 74, r: 22, t: 12, b: 48 },
          xaxis: { title: { text: 'Lost theo in period ($)' } },
          yaxis: { title: { text: 'Machine' }, autorange: 'reversed' }
        })
      }),
      table: () => ({
        columns: [
          { label: 'Machine', get: r => r.id },
          { label: 'Zone / bank', get: r => r.zone + ' · ' + r.bank },
          { label: 'Faults', num: true, get: r => r.faults, fmt: v => fmtNum(v, 0) },
          { label: 'Downtime h', num: true, get: r => r.downH, fmt: v => fmtNum(v, 1) },
          { label: 'Theo rate $/h', num: true, get: r => r.theoRate, fmt: v => fmtRate(v) },
          { label: 'Lost theo', num: true, get: r => r.lost, fmt: v => fmtMoney(v) }
        ],
        rows: lostRows
      })
    });
  } else {
    root.appendChild(emptyCard('No fault tickets in this period and scope', 'Try the full H1 period or a wider zone scope.'));
  }

  function makeStat(label, value, sub2) {
    const box = el('div', 'stat');
    append(box,
      el('div', 'stat-label', label),
      el('div', 'stat-value', value),
      el('div', 'stat-sub', sub2)
    );
    return box;
  }
};

/* ---- 6.5 Players ---- */

RENDERERS.players = function renderPlayers(root, res) {
  root.appendChild(storyCard('players'));
  void res;
  const t = tokens();

  const players = DATA.players;
  const months = monthsInPeriod(state.from, state.to);
  const monthSet = new Set(months.map(m => players.months.indexOf(m)));

  const controls = el('div', 'card');
  append(controls,
    el('h2', null, 'Player group filters'),
    el('p', 'how', 'These selectors apply to every player chart and table on this tab. Months are included when the calendar month overlaps the global period.')
  );
  const filterRow = el('div', 'inline-filters');
  const tierSel = selectFrom('Tier', ['All', ...players.tiers], state.pTier);
  const ageSel = selectFrom('Age band', ['All', ...players.ages], state.pAge);
  const regionSel = selectFrom('Region', ['All', ...players.regions], state.pRegion);
  append(filterRow, tierSel.wrap, ageSel.wrap, regionSel.wrap);
  controls.appendChild(filterRow);
  controls.appendChild(el('p', 'source', 'Source: players.json player_period. Months in scope: ' + (months.join(', ') || 'none')));
  root.appendChild(controls);
  tierSel.select.addEventListener('change', () => { state.pTier = tierSel.select.value; render(); });
  ageSel.select.addEventListener('change', () => { state.pAge = ageSel.select.value; render(); });
  regionSel.select.addEventListener('change', () => { state.pRegion = regionSel.select.value; render(); });

  const baseMap = aggregatePlayers(monthSet, {
    tier: state.pTier, age: state.pAge, region: state.pRegion
  });
  const basePlayers = Array.from(baseMap.values());
  const tracked = basePlayers.length;
  const totalCi = basePlayers.reduce((s, p) => s + p.ci, 0);
  const totalNet = basePlayers.reduce((s, p) => s + p.net, 0);
  const totalTheo = basePlayers.reduce((s, p) => s + p.th, 0);
  const ahead = basePlayers.filter(p => p.net > 0).length;
  const luckResidual = totalNet + totalTheo;

  const kpis = el('div', 'kpis');
  append(kpis,
    makeKpi('Tracked players', fmtNum(tracked, 0), 'Distinct player ids in scope'),
    makeKpi('Tracked coin-in', fmtCompactUSD(totalCi), fmtMoney(totalCi)),
    makeKpi('Players\' net', fmtCompactUSD(totalNet), 'Payout minus coin-in; negative = players lost'),
    makeKpi('Theo', fmtCompactUSD(totalTheo), 'Expected gross win'),
    makeKpi('Luck residual', fmtCompactUSD(luckResidual), 'Net + theo; positive = players ran hot'),
    makeKpi('% of players ahead', tracked ? fmtPct(ahead / tracked, 1) : '—', ahead + ' of ' + tracked + ' net > 0')
  );
  root.appendChild(kpis);

  const theoValues = basePlayers.map(p => Math.max(0, p.th));
  const losers = basePlayers.filter(p => p.net < 0).map(p => -p.net);
  const topTheo1 = topShare(theoValues, 0.01);
  const topTheo10 = topShare(theoValues, 0.10);
  const topLoss1 = topShare(losers, 0.01);
  const topLoss10 = topShare(losers, 0.10);

  const grid = el('div', 'grid2');
  if (tracked) {
    const theoCurve = lorenz(theoValues);
    const lossCurve = lorenz(losers);
    chartCard(grid, {
      title: 'A small share of players carries most of the theo — and most of the net loss',
      how: 'Lorenz curves: x is the cumulative share of players (sorted from smallest to largest), y the cumulative share of theo or of net losses among losing players. The diagonal is perfect equality.',
      source: 'players.json player_period (theo_usd, tracked_net_usd)',
      height: 350,
      build: () => {
        const data = [
          traceLine(theoCurve.x, theoCurve.y, 'Share of theo', t.cat[0],
            'Players %{x:.1f}%<br>Theo %{y:.1f}%<extra></extra>'),
          traceLine(lossCurve.x, lossCurve.y, 'Share of net loss (losers)', t.cat[1],
            'Losers %{x:.1f}%<br>Net loss %{y:.1f}%<extra></extra>'),
          traceLine([0, 100], [0, 100], 'Perfect equality', t.axis,
            'x %{x:.0f}%<br>y %{y:.0f}%<extra></extra>', { line: { width: 2, color: t.axis, dash: 'dash' } })
        ];
        return {
          data,
          layout: baseLayout({
            showlegend: true,
            margin: { l: 62, r: 18, t: 44, b: 54 },
            xaxis: { title: { text: 'Cumulative share of players (%)' }, range: [0, 100] },
            yaxis: { title: { text: 'Cumulative share (%)' }, range: [0, 100] },
            annotations: [{
              x: 0, y: 1.02, xref: 'paper', yref: 'paper', xanchor: 'left', showarrow: false,
              text: 'Top 1% of players: ' + fmtPct(topTheo1, 1) + ' of theo · top 10%: ' + fmtPct(topTheo10, 1)
                + '<br>Top 1% of losers: ' + fmtPct(topLoss1, 1) + ' of net loss · top 10%: ' + fmtPct(topLoss10, 1),
              font: { size: 10, color: t.ink2 }
            }],
            legend: { orientation: 'h', y: -0.2 }
          })
        };
      },
      table: () => ({
        columns: [
          { label: 'Curve', get: r => r.curve },
          { label: 'Players share %', num: true, get: r => r.x, fmt: v => fmtNum(v, 1) },
          { label: 'Value share %', num: true, get: r => r.y, fmt: v => fmtNum(v, 1) }
        ],
        rows: [
          ...theoCurve.x.map((x, i) => ({ curve: 'Theo', x, y: theoCurve.y[i] })),
          ...lossCurve.x.map((x, i) => ({ curve: 'Net loss (losers)', x, y: lossCurve.y[i] }))
        ]
      })
    });
  } else {
    grid.appendChild(emptyCard('No player rows in scope', 'Loosen the month, tier, age or region filters.'));
  }

  const hist = histogramNet(basePlayers);
  chartCard(grid, {
    title: 'Player net outcomes are spread widely, with both large winners and large losers',
    how: 'Distribution of net per player (payout minus coin-in) in the selected months and groups. The two edge bars collect outcomes beyond ±$2,000 so the tails stay visible.',
    source: 'players.json player_period (tracked_net_usd)',
    height: 350,
    build: () => ({
      data: [traceBar(hist.labels, hist.counts, 'Players', t.cat[0],
        '%{x}<br>%{y} players<extra></extra>')],
      layout: baseLayout({
        margin: { l: 58, r: 16, t: 12, b: 84 },
        xaxis: { title: { text: 'Net per player ($, clipped at ±$2,000)' }, tickangle: -40, type: 'category' },
        yaxis: { title: { text: 'Players' } }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Net bin', get: r => r.label },
        { label: 'Players', num: true, get: r => r.count, fmt: v => fmtNum(v, 0) },
        { label: 'Share', num: true, get: r => r.share, fmt: v => fmtPct(v, 2) }
      ],
      rows: hist.rows
    })
  });
  root.appendChild(grid);

  /* Tables by tier and by age band */
  const tierGroups = groupPlayers(monthSet, 'tier', { age: state.pAge, region: state.pRegion });
  const ageGroups = groupPlayers(monthSet, 'age', { tier: state.pTier, region: state.pRegion });
  const tableGrid = el('div', 'grid2');
  const tierCard = groupCard('By tier: who brings the coin-in and who gets the comps', tierGroups, 'Tier');
  const ageCard = groupCard('By age band: the same view across age groups', ageGroups, 'Age band');
  tableGrid.append(tierCard, ageCard);
  root.appendChild(tableGrid);

  const rg = notesCallout('players');
  if (rg) {
    const card = el('section', 'card');
    append(card, el('h2', null, 'Responsible gaming'), rg);
    root.appendChild(card);
  }

  /* ---- helpers ---- */

  function selectFrom(label, options, value) {
    const wrap = el('div', 'fgroup');
    const id = 'pf-' + Math.random().toString(36).slice(2, 8);
    const lab = el('label', null, label);
    lab.htmlFor = id;
    const sel = el('select');
    sel.id = id;
    for (const opt of options) {
      const o = new Option(opt, opt);
      o.selected = opt === value;
      sel.appendChild(o);
    }
    append(wrap, lab, sel);
    return { wrap, select: sel };
  }

  function aggregatePlayers(monthIdxSet, opts) {
    const rows = players.rows;
    const map = new Map();
    for (let i = 0; i < rows.p.length; i++) {
      if (!monthIdxSet.has(rows.mo[i])) continue;
      if (opts.tier && opts.tier !== 'all' && players.tiers[rows.t[i]] !== opts.tier) continue;
      if (opts.age && opts.age !== 'all' && players.ages[rows.a[i]] !== opts.age) continue;
      if (opts.region && opts.region !== 'all' && players.regions[rows.r[i]] !== opts.region) continue;
      const p = rows.p[i];
      let o = map.get(p);
      if (!o) {
        o = { p, ci: 0, net: 0, th: 0, cc: 0, cf: 0, vis: 0 };
        map.set(p, o);
      }
      o.ci += rows.ci[i];
      o.net += rows.net[i];
      o.th += rows.th[i];
      o.cc += rows.cc[i];
      o.cf += rows.cf[i];
      o.vis += rows.vis[i];
    }
    return map;
  }

  function groupPlayers(monthIdxSet, group, opts) {
    const rows = players.rows;
    const map = new Map();
    for (let i = 0; i < rows.p.length; i++) {
      if (!monthIdxSet.has(rows.mo[i])) continue;
      if (opts.tier && opts.tier !== 'all' && players.tiers[rows.t[i]] !== opts.tier) continue;
      if (opts.age && opts.age !== 'all' && players.ages[rows.a[i]] !== opts.age) continue;
      if (opts.region && opts.region !== 'all' && players.regions[rows.r[i]] !== opts.region) continue;
      const label = group === 'tier' ? players.tiers[rows.t[i]] : players.ages[rows.a[i]];
      let o = map.get(label);
      if (!o) {
        o = { label, players: new Set(), ci: 0, net: 0, th: 0, cc: 0 };
        map.set(label, o);
      }
      o.players.add(rows.p[i]);
      o.ci += rows.ci[i];
      o.net += rows.net[i];
      o.th += rows.th[i];
      o.cc += rows.cc[i];
    }
    const order = group === 'tier' ? players.tiers : players.ages;
    return order.filter(l => map.has(l)).map(l => {
      const o = map.get(l);
      return {
        label: l,
        players: o.players.size,
        ci: o.ci,
        net: o.net,
        th: o.th,
        cc: o.cc,
        compTheo: o.th > 0 ? o.cc / o.th : null
      };
    });
  }

  function groupCard(title, groups, groupName) {
    const card = el('section', 'card');
    append(card, el('h2', null, title), el('p', 'source', 'Source: players.json player_period'));
    renderTable(card, {
      columns: [
        { label: groupName, get: r => r.label },
        { label: 'Players', num: true, get: r => r.players, fmt: v => fmtNum(v, 0) },
        { label: 'Coin-in', num: true, get: r => r.ci, fmt: v => fmtMoney(v) },
        { label: 'Net', num: true, get: r => r.net, fmt: v => fmtSignedMoney(v) },
        { label: 'Theo', num: true, get: r => r.th, fmt: v => fmtMoney(v) },
        { label: 'Comp cost', num: true, get: r => r.cc, fmt: v => fmtMoney(v) },
        { label: 'Comp / theo', num: true, get: r => r.compTheo, fmt: v => fmtPct(v, 2) }
      ],
      rows: groups
    });
    return card;
  }

  function topShare(values, frac) {
    if (!values.length) return 0;
    const sorted = values.slice().sort((a, b) => b - a);
    const total = sum(sorted);
    if (total <= 0) return 0;
    const k = Math.max(1, Math.ceil(sorted.length * frac));
    return sum(sorted.slice(0, k)) / total;
  }

  function lorenz(values) {
    if (!values.length) return { x: [0, 100], y: [0, 100] };
    const sorted = values.slice().sort((a, b) => a - b);
    const total = sum(sorted);
    const n = sorted.length;
    const step = Math.max(1, Math.floor(n / 400));
    const xs = [0];
    const ys = [0];
    let cum = 0;
    for (let i = 0; i < n; i++) {
      cum += sorted[i];
      if ((i + 1) % step === 0 || i === n - 1) {
        xs.push((i + 1) / n * 100);
        ys.push(total > 0 ? cum / total * 100 : 0);
      }
    }
    return { x: xs, y: ys };
  }

  function histogramNet(list) {
    const edges = [];
    for (let v = -2000; v <= 2000; v += 250) edges.push(v);
    const labels = ['≤ -$2,000'];
    const counts = [0];
    for (let i = 0; i < edges.length - 1; i++) {
      labels.push('$' + nf(0).format(edges[i]) + ' to $' + nf(0).format(edges[i + 1]));
      counts.push(0);
    }
    labels.push('> $2,000');
    counts.push(0);
    let n = 0;
    for (const p of list) {
      n += 1;
      const v = p.net;
      if (v <= -2000) counts[0] += 1;
      else if (v > 2000) counts[counts.length - 1] += 1;
      else {
        let bin = Math.floor((v + 2000) / 250);
        if (bin < 0) bin = 0;
        if (bin >= counts.length - 1) bin = counts.length - 2;
        counts[bin + 1] += 1;
      }
    }
    const rows = labels.map((label, i) => ({ label, count: counts[i], share: n ? counts[i] / n : 0 }));
    return { labels, counts, rows };
  }
};

/* ---- 6.6 Comps ---- */

RENDERERS.comps = function renderComps(root, res) {
  root.appendChild(storyCard('comps'));
  void res;
  const t = tokens();
  const { lo, hi } = periodBounds();
  const comp = DATA.analysis.comp;
  const dates = DATA.core.dates.slice(lo, hi + 1);
  const changeInPeriod = comp.change_date >= state.from && comp.change_date <= state.to;

  chartCard(root, {
    title: 'The redemption price changed on ' + comp.change_date + ': points per comp dollar fell sharply',
    how: 'Daily points redeemed per $1 of comp face value. The vertical marker is the algorithm-detected change date; a lower ratio means the same face value costs fewer points.',
    source: 'analysis.json comp.daily (loyalty_ledger redemptions)',
    height: 340,
    build: () => {
      const data = [traceLine(dates, comp.daily.pts_per_face_usd.slice(lo, hi + 1), 'Points per $1 face', t.cat[0],
        '%{x|%b %d}<br>%{y:.2f} points per $1<extra></extra>')];
      const shapes = changeInPeriod ? [{
        type: 'line', xref: 'x', yref: 'paper', x0: comp.change_date, x1: comp.change_date, y0: 0, y1: 1,
        line: { color: t.cat[1], width: 2, dash: 'dash' }
      }] : [];
      const annotations = changeInPeriod ? [{
        x: comp.change_date, y: 1.02, yref: 'paper', text: 'Change date ' + comp.change_date,
        showarrow: false, font: { size: 10, color: t.cat[1] }, xanchor: 'left'
      }] : [];
      return {
        data,
        layout: baseLayout({
          hovermode: 'x unified',
          margin: { l: 60, r: 18, t: 30, b: 48 },
          xaxis: { type: 'date', title: { text: 'Gaming date' } },
          yaxis: { title: { text: 'Points per $1 of comp face value' } },
          shapes, annotations
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Date', get: r => r.date },
        { label: 'Points redeemed', num: true, get: r => r.points, fmt: v => fmtNum(v, 0) },
        { label: 'Face value', num: true, get: r => r.face, fmt: v => fmtMoney(v) },
        { label: 'Points per $1', num: true, get: r => r.ratio, fmt: v => fmtNum(v, 2) }
      ],
      rows: dates.map((date, j) => ({
        date,
        points: comp.daily.points_redeemed[lo + j],
        face: comp.daily.face_usd[lo + j],
        ratio: comp.daily.pts_per_face_usd[lo + j]
      }))
    })
  });

  const months = monthsInPeriod(state.from, state.to);
  const monthly = comp.monthly.filter(m => months.includes(m.month));
  const grid = el('div', 'grid2');

  chartCard(grid, {
    title: 'Reinvestment fell after the comp-price change',
    how: 'Comp cost divided by theoretical win, by month. Higher bars mean a larger share of expected win is returned to players as comps.',
    source: 'analysis.json comp.monthly (player_period)',
    height: 300,
    build: () => ({
      data: [traceBar(monthly.map(m => m.month), monthly.map(m => m.reinvestment * 100), 'Reinvestment', t.cat[0],
        '%{x}<br>Reinvestment %{y:.2f}%<extra></extra>')],
      layout: baseLayout({
        hovermode: 'x unified',
        margin: { l: 62, r: 16, t: 12, b: 48 },
        xaxis: { title: { text: 'Month' }, type: 'category' },
        yaxis: { title: { text: 'Comp cost ÷ theo (%)' } }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Month', get: r => r.month },
        { label: 'Comp cost', num: true, get: r => r.comp_cost, fmt: v => fmtMoney(v) },
        { label: 'Theo', num: true, get: r => r.theo, fmt: v => fmtMoney(v) },
        { label: 'Reinvestment', num: true, get: r => r.reinvestment, fmt: v => fmtPct(v, 2) }
      ],
      rows: monthly
    })
  });

  chartCard(grid, {
    title: 'Monthly comp cost stepped down after May',
    how: 'Total economic comp cost by month in the selected period. This is the numerator of the reinvestment chart; the theo denominator is on the table.',
    source: 'analysis.json comp.monthly (player_period)',
    height: 300,
    build: () => ({
      data: [traceBar(monthly.map(m => m.month), monthly.map(m => m.comp_cost), 'Comp cost', t.cat[1],
        '%{x}<br>Comp cost $%{y:,.0f}<extra></extra>')],
      layout: baseLayout({
        hovermode: 'x unified',
        margin: { l: 66, r: 16, t: 12, b: 48 },
        xaxis: { title: { text: 'Month' }, type: 'category' },
        yaxis: { title: { text: 'Comp cost ($)' }, tickformat: '~s' }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Month', get: r => r.month },
        { label: 'Players', num: true, get: r => r.players, fmt: v => fmtNum(v, 0) },
        { label: 'Comp cost', num: true, get: r => r.comp_cost, fmt: v => fmtMoney(v) },
        { label: 'Comp face', num: true, get: r => r.comp_face, fmt: v => fmtMoney(v) },
        { label: 'Theo', num: true, get: r => r.theo, fmt: v => fmtMoney(v) }
      ],
      rows: monthly
    })
  });
  root.appendChild(grid);

  const did = comp.did;
  const placebo = comp.placebo;
  const didCard = el('section', 'card');
  append(didCard,
    el('h2', null, 'Difference-in-differences: carded play rose relative to uncarded play after the change'),
    el('p', 'how', 'The estimate is the change in log carded coin-in minus the change in log uncarded coin-in, pre (Mar–Apr) vs post (May–Jun). The placebo repeats the same test on a period with no comp-price change; a near-zero placebo supports the design.')
  );
  const didStats = el('div', 'statgrid');
  append(didStats,    makeStat('DiD estimate', (did.did * 100 >= 0 ? '+' : '') + nf(2).format(did.did * 100) + '%', '95% CI ' + fmtPct(did.ci_low, 2) + ' to ' + fmtPct(did.ci_high, 2)),
    makeStat('Carded pre → post', fmtCompactUSD(did.carded_pre_daily_mean) + ' → ' + fmtCompactUSD(did.carded_post_daily_mean), 'Daily means'),
    makeStat('Uncarded pre → post', fmtCompactUSD(did.uncarded_pre_daily_mean) + ' → ' + fmtCompactUSD(did.uncarded_post_daily_mean), 'Daily means'),
    makeStat('Placebo estimate', (placebo.did * 100 >= 0 ? '+' : '') + nf(2).format(placebo.did * 100) + '%', '95% CI ' + fmtPct(placebo.ci_low, 2) + ' to ' + fmtPct(placebo.ci_high, 2))
  );
  didCard.appendChild(didStats);
  didCard.appendChild(el('p', 'source', 'Source: analysis.json comp.did and comp.placebo (prepared_daily_view; 1000 bootstrap resamples, seed 42). Carded vs uncarded coin-in.'));

  const tierCard = el('section', 'card');
  append(tierCard,
    el('h2', null, 'By opening tier: theo per player-month barely moved, while comp cost per player-month edged up'),
    el('p', 'how', 'Pre = March–April, post = May–June. Values are per active player-month for each opening tier.'),
    el('p', 'source', 'analysis.json comp.by_opening_tier (player_period)')
  );
  renderTable(tierCard, {
    columns: [
      { label: 'Opening tier', get: r => r.tier },
      { label: 'Theo / player-month pre', num: true, get: r => r.theo_pre_per_player_month, fmt: v => fmtMoney(v, 2) },
      { label: 'Theo / player-month post', num: true, get: r => r.theo_post_per_player_month, fmt: v => fmtMoney(v, 2) },
      { label: 'Comp cost pre', num: true, get: r => r.comp_cost_pre, fmt: v => fmtMoney(v, 2) },
      { label: 'Comp cost post', num: true, get: r => r.comp_cost_post, fmt: v => fmtMoney(v, 2) }
    ],
    rows: comp.by_opening_tier
  });
  const didGrid = el('div', 'grid2');
  didGrid.append(didCard, tierCard);
  root.appendChild(didGrid);

  function makeStat(label, value, sub2) {
    const box = el('div', 'stat');
    append(box, el('div', 'stat-label', label), el('div', 'stat-value', value), el('div', 'stat-sub', sub2));
    return box;
  }
};

/* ---- 6.7 Plan ---- */

RENDERERS.plan = function renderPlan(root, res) {
  void res;
  root.appendChild(storyCard('plan'));
  const plan = DATA.plan;
  if (!plan || typeof plan !== 'object') {
    root.appendChild(pendingCard('Budget plan pending', 'The analyst has not written plan.json yet. This tab will show the $100,000 allocation, action cards, rejected options and sensitivity.'));
    return;
  }
  const t = tokens();
  const actions = Array.isArray(plan.actions) ? plan.actions : [];
  const budget = Number(plan.budget) || 100000;
  const spent = actions.reduce((s, a) => s + (Number(a.cost) || 0), 0);
  const kept = plan.kept !== undefined && plan.kept !== null ? Number(plan.kept) : Math.max(0, budget - spent);

  const budgetData = actions.map((a, i) => ({
    type: 'bar', orientation: 'h', x: [Number(a.cost) || 0], y: ['Budget'],
    name: (a.id || ('Action ' + (i + 1))).replace(/^A-/, ''),
    marker: { color: t.cat[i % 8], line: { width: 0 } },
    hovertemplate: a.name + ': $%{x:,.0f}<extra></extra>'
  }));
  budgetData.push({
    type: 'bar', orientation: 'h', x: [kept], y: ['Budget'], name: 'Kept (unallocated)',
    marker: { color: t.muted }, hovertemplate: 'Kept: $%{x:,.0f}<extra></extra>'
  });

  chartCard(root, {
    title: 'The plan allocates ' + fmtMoney(spent) + ' of the ' + fmtMoney(budget) + ' budget and keeps ' + fmtMoney(kept),
    how: 'One stacked bar: each segment is an action\'s cost, and the gray segment is unallocated budget. Hover or open the table for exact amounts.',
    source: 'plan.json (actions, kept, budget)',
    height: 210,
    build: () => ({
      data: budgetData,
      layout: baseLayout({
        barmode: 'stack', showlegend: true,
        margin: { l: 20, r: 22, t: 18, b: 42 },
        xaxis: { title: { text: 'Budget ($)' }, range: [0, budget], tickformat: '~s' },
        yaxis: { showticklabels: false },
        legend: { orientation: 'h', y: -0.3, font: { size: 10 } }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Item', get: r => r.name },
        { label: 'Cost', num: true, get: r => r.cost, fmt: v => fmtMoney(v) },
        { label: 'Share of budget', num: true, get: r => r.cost / budget, fmt: v => fmtPct(v, 1) }
      ],
      rows: [
        ...actions.map(a => ({ name: a.name, cost: Number(a.cost) || 0, budget })),
        { name: 'Kept (unallocated)', cost: kept, budget }
      ]
    })
  });

  const cards = el('div', 'plan-actions');
  for (const a of actions) {
    const card = el('section', 'action-card');
    const targets = Array.isArray(a.targets) ? a.targets.join(', ') : (a.targets || 'all targets');
    append(card,
      el('h3', null, a.name || a.id || 'Action'),
      el('p', 'action-meta', 'ID ' + (a.id || '—') + ' · ' + (a.qty ?? '—') + ' units · ' + (targets || 'all targets'))
    );
    const grid = el('div', 'action-grid');
    append(grid,
      actionStat('Quantity', String(a.qty ?? '—')),
      actionStat('Cost', fmtMoney(Number(a.cost) || 0)),
      actionStat('Lead days', String(a.lead_days ?? '—')),
      actionStat('Expected effect (low / mid / high)',
        fmtMoney(Number(a.effect_low) || 0) + ' / ' + fmtMoney(Number(a.effect_mid) || 0) + ' / ' + fmtMoney(Number(a.effect_high) || 0)
        + (a.effect_unit ? ' ' + a.effect_unit : ''))
    );
    card.appendChild(grid);

    const assumptions = Array.isArray(a.assumptions) ? a.assumptions : [];
    if (assumptions.length) {
      card.appendChild(el('div', 'label', 'Assumptions'));
      const ul = el('ul');
      assumptions.forEach(x => ul.appendChild(el('li', null, x)));
      card.appendChild(ul);
    }
    if (a.uncertainty) {
      card.appendChild(el('div', 'label', 'Uncertainty'));
      card.appendChild(el('p', 'muted', a.uncertainty));
    }
    if (a.measurement) {
      card.appendChild(el('div', 'label', 'How we will measure it'));
      card.appendChild(el('p', 'muted', a.measurement));
    }
    const evidence = Array.isArray(a.evidence) ? a.evidence : [];
    if (evidence.length) {
      const links = el('div', 'evidence-links');
      for (const ev of evidence) {
        const btn = el('button', 'btn btn-sm', 'Evidence: ' + (ev.label || ev.tab || 'open'));
        btn.type = 'button';
        btn.addEventListener('click', () => applyEvidenceLink(ev));
        links.appendChild(btn);
      }
      card.appendChild(links);
    }
    cards.appendChild(card);
  }
  root.appendChild(cards);

  const rejected = Array.isArray(plan.rejected) ? plan.rejected : [];
  if (rejected.length) {
    const card = el('section', 'card');
    append(card,
      el('h2', null, 'Rejected options: what did not make the cut'),
      el('p', 'how', 'Options considered but not funded, with the expected benefit and the reason for rejection.'),
      el('p', 'source', 'plan.json rejected')
    );
    renderTable(card, {
      columns: [
        { label: 'Option', get: r => r.name, wrap: true },
        { label: 'Cost', num: true, get: r => r.cost, fmt: v => typeof v === 'number' ? fmtMoney(v) : formatGeneric(v) },
        { label: 'Expected benefit', num: true, get: r => r.expected_benefit, fmt: v => typeof v === 'number' ? fmtMoney(v) : formatGeneric(v) },
        { label: 'Reason', get: r => r.reason, wrap: true }
      ],
      rows: rejected
    });
    root.appendChild(card);
  }

  const sensitivity = Array.isArray(plan.sensitivity) ? plan.sensitivity : [];
  const sensCard = el('section', 'card');
  append(sensCard,
    el('h2', null, 'Sensitivity: how the plan holds up when assumptions move'),
    el('p', 'how', 'Each row is one sensitivity case from the analyst. Read the case column first, then the effect on the plan.'),
    el('p', 'source', 'plan.json sensitivity')
  );
  if (sensitivity.length) {
    const keys = Array.from(new Set(sensitivity.flatMap(o => Object.keys(o))));
    renderTable(sensCard, {
      columns: keys.map(k => ({
        label: k.replace(/_/g, ' '), get: r => r[k],
        fmt: v => typeof v === 'number' ? nf(Number.isInteger(v) ? 0 : 2).format(v) : formatGeneric(v),
        wrap: typeof sensitivity[0][k] === 'string'
      })),
      rows: sensitivity
    });
  } else {
    sensCard.appendChild(el('p', 'pending', 'No sensitivity table supplied yet.'));
  }
  root.appendChild(sensCard);

  function actionStat(label, value) {
    const box = el('div', 'stat');
    append(box, el('div', 'label', label), el('div', 'stat-value', value));
    return box;
  }
};

function applyEvidenceLink(ev) {
  if (!ev || typeof ev !== 'object') return;
  if (ev.tab && TABS.includes(ev.tab)) state.tab = ev.tab;
  if (validDate(ev.from)) state.from = ev.from;
  if (validDate(ev.to)) state.to = ev.to;
  if (ev.zone && DATA.derived.zoneById[ev.zone]) {
    state.zone = ev.zone;
    state.trafficZones = [ev.zone];
  }
  if (ev.bank && DATA.derived.bankById[ev.bank]) {
    state.bank = ev.bank;
    state.zone = DATA.core.zones[DATA.derived.bankById[ev.bank].zone].id;
    state.trafficZones = [state.zone];
  } else if (state.zone === 'all') {
    state.bank = 'all';
    state.trafficZones = null;
  }
  if (state.from > state.to) {
    const tmp = state.from;
    state.from = state.to;
    state.to = tmp;
  }
  syncControls();
  syncHash();
  applyStateToView();
  render();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

/* ---- 6.8 Model ---- */

RENDERERS.model = function renderModel(root, res) {
  root.appendChild(storyCard('model'));
  void res;
  const t = tokens();
  const A = DATA.model.A;
  const B = DATA.model.B;
  const modelNote = callout(['Model metrics use the fixed TRAIN (Jan–Apr) / HOLD (May–Jun) split baked into model.json. The global period filter does not refit the model.']);
  modelNote.style.marginBottom = '16px';
  root.appendChild(modelNote);

  const kgrid = A.k_grid.slice();
  const kx = kgrid.map(d => d.k === 0 ? 1 : d.k);
  chartCard(root, {
    title: 'Shrinkage k=' + nf(0).format(A.k) + ' minimises inner-validation MAE',
    how: 'Inner validation fits on Jan–Feb and scores March–April. The x-axis is logarithmic; k=0 is drawn at 1 and labelled 0 so it stays visible. Lower MAE is better.',
    source: 'model.json A.k_grid (inner train Jan–Feb, validation Mar–Apr)',
    height: 320,
    build: () => ({
      data: [traceLine(kx, kgrid.map(d => d.inner_mae), 'Inner MAE', t.cat[0],
        'k=%{customdata}<br>MAE %{y:.3f}<extra></extra>', {
          mode: 'lines+markers', marker: { size: 6, color: t.cat[0] }, customdata: kgrid.map(d => d.k)
        })],
      layout: baseLayout({
        margin: { l: 62, r: 18, t: 30, b: 54 },
        xaxis: {
          type: 'log', title: { text: 'Shrinkage k (log scale; k=0 shown at 1)' },
          tickvals: kx, ticktext: kgrid.map(d => d.k === 0 ? '0' : (d.k >= 1000 ? (d.k / 1000) + 'k' : String(d.k)))
        },
        yaxis: { title: { text: 'Inner-validation MAE ($/h)' } },
        shapes: [{
          type: 'line', xref: 'x', yref: 'paper', x0: A.k === 0 ? 1 : A.k, x1: A.k === 0 ? 1 : A.k,
          y0: 0, y1: 1, line: { color: t.cat[1], width: 2, dash: 'dash' }
        }],
        annotations: [{
          x: A.k === 0 ? 1 : A.k, y: 1.02, yref: 'paper', text: 'chosen k=' + nf(0).format(A.k),
          showarrow: false, font: { size: 10, color: t.cat[1] }, xanchor: 'left'
        }]
      })
    }),
    table: () => ({
      columns: [
        { label: 'k', num: true, get: r => r.k, fmt: v => fmtNum(v, 0) },
        { label: 'Inner MAE', num: true, get: r => r.inner_mae, fmt: v => fmtNum(v, 3) }
      ],
      rows: kgrid
    })
  });

  const METHOD_LABEL = {
    model: 'Model: zone × game × weekday × machine (shrunk)',
    model_noshrink: 'Model without shrinkage (k = 0)',
    B_theo_rate: 'Baseline: own Jan–Apr theo per hour (luck removed)',
    B_hw_rate: "Baseline: own Jan–Apr house win per hour (GM's logic)"
  };
  if (Array.isArray(A.metrics_relative)) {
    const relCard = el('section', 'card');
    append(relCard,
      el('h2', null, 'Relative error: adjusting for zone and game sizes machines against each other best'),
      el('p', 'how', 'Each method\'s May–June prediction for a machine, divided by its average prediction, vs the machine\'s actual rate divided by the actual average (mean absolute gap, %). This removes the floor-wide May–June slowdown that no Jan–Apr method could know, and keeps what the replace/keep decision needs: which machines earn more or less than others.'),
      el('p', 'source', 'model.json A.metrics_relative and A.bootstrap_relative (307 machines, 2,000 paired resamples)')
    );
    renderTable(relCard, {
      columns: [
        { label: 'Method', get: r => METHOD_LABEL[r.method] || r.method },
        { label: 'Target', get: r => r.target === 'y_theo' ? 'theo per open hour' : 'house win per open hour' },
        { label: 'Relative error', num: true, get: r => r.rel_error, fmt: v => fmtNum(v, 2) + '%' }
      ],
      rows: A.metrics_relative
    });
    if (Array.isArray(A.bootstrap_relative)) {
      renderTable(relCard, {
        columns: [
          { label: 'Comparison (target: theo per hour)', get: r => r.comparison.replace('relative_error', 'error').replace(', target=y_theo', '') },
          { label: 'Mean difference', num: true, get: r => r.mean_rel_diff, fmt: v => fmtNum(v, 2) + ' pp' },
          { label: '95% CI', get: r => fmtNum(r.ci95_low, 2) + ' to ' + fmtNum(r.ci95_high, 2) + ' pp' }
        ],
        rows: A.bootstrap_relative
      });
    }
    root.appendChild(relCard);
  }

  const metricsCard = el('section', 'card');
  append(metricsCard,
    el('h2', null, 'Dollar accuracy: luck removal does most of the work; every method over-forecasts the May–June slowdown'),
    el('p', 'how', 'MAE and RMSE are dollars per available hour on the May–June holdout; bias = mean(prediction − actual); Spearman is the rank correlation. Honest result: in absolute dollars the machine\'s own luck-free history (theo rate) is slightly better than the model, because the whole floor slowed in May–June and the Back Forty history happened to include the March closure.'),
    el('p', 'source', 'model.json A.metrics (holdout, 307 eligible machines)')
  );
  renderTable(metricsCard, {
    columns: [
      { label: 'Method', get: r => METHOD_LABEL[r.method] || r.method },
      { label: 'Target', get: r => r.target },
      { label: 'MAE', num: true, get: r => r.mae, fmt: v => fmtNum(v, 3) },
      { label: 'RMSE', num: true, get: r => r.rmse, fmt: v => fmtNum(v, 3) },
      { label: 'Bias', num: true, get: r => r.bias, fmt: v => (v == null ? '—' : fmtNum(v, 3)) },
      { label: 'Spearman', num: true, get: r => r.spearman, fmt: v => fmtNum(v, 3) }
    ],
    rows: A.metrics
  });
  root.appendChild(metricsCard);

  const bootCard = el('section', 'card');
  append(bootCard,
    el('h2', null, 'Paired bootstrap of dollar MAE: far better than raw house win, slightly worse than the theo history'),
    el('p', 'how', 'Mean paired MAE difference over 2,000 resamples of machines, with a 95% interval. A negative difference means the model has lower MAE than the baseline.'),
    el('p', 'source', 'model.json A.bootstrap (2,000 resamples, seed 7)')
  );
  const bootGrid = el('div', 'statgrid');
  for (const b of A.bootstrap) {
    const box = el('div', 'stat');
    append(box,
      el('div', 'stat-label', b.comparison),
      el('div', 'stat-value', nf(3).format(b.mean_mae_diff)),
      el('div', 'stat-sub', '95% CI ' + nf(3).format(b.ci95_low) + ' to ' + nf(3).format(b.ci95_high))
    );
    bootGrid.appendChild(box);
  }
  bootCard.appendChild(bootGrid);
  root.appendChild(bootCard);

  const holdout = A.holdout;
  const maxH = Math.max(1, ...holdout.map(r => Math.max(r.y_theo, r.pred_model, r.b_hw_rate))) * 1.05;
  chartCard(root, {
    title: 'Holdout scatter: model predictions track actual theo more tightly than raw house-win rate',
    how: 'x is actual May–June theo per available hour, y is the prediction. Points near the dashed y=x line are accurate; the gray baseline uses only historical house-win rate.',
    source: 'model.json A.holdout (eligible machines, May–Jun 2025)',
    height: 380,
    build: () => ({
      data: [
        {
          type: 'scatter', mode: 'markers', x: holdout.map(r => r.y_theo), y: holdout.map(r => r.pred_model),
          name: 'Model', marker: { color: t.cat[0], size: 7, opacity: 0.75 },
          text: holdout.map(r => r.machine_id),
          hovertemplate: '%{text}<br>Actual $%{x:.2f}/h<br>Model $%{y:.2f}/h<extra></extra>'
        },
        {
          type: 'scatter', mode: 'markers', x: holdout.map(r => r.y_theo), y: holdout.map(r => r.b_hw_rate),
          name: 'B_hw_rate', marker: { color: t.muted, size: 6, opacity: 0.45 },
          text: holdout.map(r => r.machine_id),
          hovertemplate: '%{text}<br>Actual $%{x:.2f}/h<br>Baseline $%{y:.2f}/h<extra></extra>'
        },
        {
          type: 'scatter', mode: 'lines', x: [0, maxH], y: [0, maxH], name: 'y = x',
          line: { color: t.axis, width: 2, dash: 'dash' }, hoverinfo: 'skip'
        }
      ],
      layout: baseLayout({
        showlegend: true,
        margin: { l: 62, r: 18, t: 12, b: 58 },
        xaxis: { title: { text: 'Actual theo per available hour ($/h)' }, range: [0, maxH] },
        yaxis: { title: { text: 'Predicted theo per available hour ($/h)' }, range: [0, maxH] },
        legend: { orientation: 'h', y: -0.24 }
      })
    }),
    table: () => ({
      columns: [
        { label: 'Machine', get: r => r.machine_id },
        { label: 'Zone', get: r => r.zone },
        { label: 'Actual theo/h', num: true, get: r => r.y_theo, fmt: v => fmtNum(v, 3) },
        { label: 'Model', num: true, get: r => r.pred_model, fmt: v => fmtNum(v, 3) },
        { label: 'B_hw_rate', num: true, get: r => r.b_hw_rate, fmt: v => fmtNum(v, 3) }
      ],
      rows: holdout
    })
  });

  const decCard = el('section', 'card');
  append(decCard,
    el('h2', null, 'Decision test: the model\'s bottom ten are weak on the holdout, not just unlucky'),
    el('p', 'how', 'Each method ranks ten machines in TRAIN. We then check how many land in the HOLD bottom ten by the HOLD machine index (hits_index) and by raw HOLD house win (hits_total). Higher is better for finding truly weak machines.'),
    el('p', 'source', 'model.json A.decision (TRAIN and HOLD split)')
  );
  renderTable(decCard, {
    columns: [
      { label: 'Method', get: r => r.method },
      { label: 'Bottom-ten ids', get: r => r.ids.join(', '), wrap: true },
      { label: 'Mean HOLD theo/h', num: true, get: r => r.mean_hold_theo_rate, fmt: v => fmtNum(v, 3) },
      { label: 'Mean HOLD index', num: true, get: r => r.mean_hold_index, fmt: v => fmtNum(v, 3) },
      { label: 'Hits (index)', num: true, get: r => r.hits_index, fmt: v => fmtNum(v, 0) },
      { label: 'Hits (total hw)', num: true, get: r => r.hits_total, fmt: v => fmtNum(v, 0) }
    ],
    rows: A.decision
  });
  root.appendChild(decCard);

  const bd = B.daily;
  const trainEnd = '2025-04-30';
  const bRows = bd.date.map((date, i) => ({
    date, actual: bd.actual[i], bconst: bd.B_const[i], weekday: bd.M_weekday[i], event: bd.M_weekday_event[i]
  }));
  chartCard(root, {
    title: 'Model B: weekday plus event forecasts track the May–June level, but miss the spikes',
    how: 'Daily property coin-in, actual versus three forecasts. Train months are faded and holdout months are solid; the vertical line is 1 May. Forecasts use only information available by 30 April.',
    source: 'model.json B.daily (property_day)',
    height: 400,
    build: () => {
      const series = [
        { key: 'actual', name: 'Actual', color: t.ink, dash: 'solid' },
        { key: 'bconst', name: 'B_const (train mean)', color: t.muted, dash: 'dot' },
        { key: 'weekday', name: 'M_weekday', color: t.cat[0], dash: 'solid' },
        { key: 'event', name: 'M_weekday_event', color: t.cat[1], dash: 'solid' }
      ];
      const data = [];
      for (const s of series) {
        const train = bRows.filter(r => r.date <= trainEnd);
        const test = bRows.filter(r => r.date > trainEnd);
        data.push({
          type: 'scatter', mode: 'lines', x: train.map(r => r.date), y: train.map(r => r[s.key]),
          name: s.name, line: { width: 2, color: s.color, dash: s.dash }, opacity: 0.28,
          showlegend: false, hoverinfo: 'skip'
        });
        data.push({
          type: 'scatter', mode: 'lines', x: test.map(r => r.date), y: test.map(r => r[s.key]),
          name: s.name, line: { width: 2, color: s.color, dash: s.dash },
          hovertemplate: '%{x|%b %d}<br>' + s.name + ' $%{y:,.0f}<extra></extra>'
        });
      }
      return {
        data,
        layout: baseLayout({
          showlegend: true, hovermode: 'x unified',
          margin: { l: 72, r: 18, t: 18, b: 48 },
          xaxis: { type: 'date', title: { text: 'Gaming date' } },
          yaxis: { title: { text: 'Property coin-in ($)' }, tickformat: '~s' },
          shapes: [{
            type: 'line', xref: 'x', yref: 'paper', x0: '2025-05-01', x1: '2025-05-01', y0: 0, y1: 1,
            line: { color: t.cat[1], width: 2, dash: 'dash' }
          }],
          annotations: [
            { x: '2025-01-05', y: 1.03, yref: 'paper', text: 'Train (faded)', showarrow: false, font: { size: 10, color: t.muted }, xanchor: 'left' },
            { x: '2025-05-01', y: 1.03, yref: 'paper', text: 'Holdout', showarrow: false, font: { size: 10, color: t.cat[1] }, xanchor: 'left' }
          ],
          legend: { orientation: 'h', y: -0.18 }
        })
      };
    },
    table: () => ({
      columns: [
        { label: 'Date', get: r => r.date },
        { label: 'Actual', num: true, get: r => r.actual, fmt: v => fmtMoney(v) },
        { label: 'B_const', num: true, get: r => r.bconst, fmt: v => fmtMoney(v) },
        { label: 'M_weekday', num: true, get: r => r.weekday, fmt: v => fmtMoney(v) },
        { label: 'M_weekday_event', num: true, get: r => r.event, fmt: v => fmtMoney(v) }
      ],
      rows: bRows
    })
  });

  const bMetricsCard = el('section', 'card');
  append(bMetricsCard,
    el('h2', null, 'Model B holdout metrics: weekday seasonality does most of the work'),
    el('p', 'how', 'MAE is in dollars per day; MAPE and bias are percentages of actual. Bias is the mean signed residual (actual minus forecast).'),
    el('p', 'source', 'model.json B.metrics (May–Jun 2025 holdout)')
  );
  renderTable(bMetricsCard, {
    columns: [
      { label: 'Method', get: r => r.method },
      { label: 'MAE', num: true, get: r => r.mae, fmt: v => fmtMoney(v) },
      { label: 'MAPE', num: true, get: r => r.mape, fmt: v => fmtPctPoints(v, 2) },
      { label: 'Bias', num: true, get: r => r.bias, fmt: v => fmtMoney(v) }
    ],
    rows: B.metrics
  });
  root.appendChild(bMetricsCard);

  const evCard = el('section', 'card');
  append(evCard,
    el('h2', null, 'Event forecast rule: only events announced by 30 April were usable in the holdout'),
    el('p', 'how', 'The frozen-forecast rule prevents leakage. An event announced after 30 April could not have informed the May–June forecast, so it is shown as unusable even though its measured lift is reported for evidence.'),
    el('p', 'source', 'model.json B.events (events, announced dates, measured lifts)')
  );
  renderTable(evCard, {
    columns: [
      { label: 'Event', get: r => r.name, wrap: true },
      { label: 'Type', get: r => r.event_type },
      { label: 'Dates', get: r => r.start_date + ' – ' + r.end_date },
      { label: 'Announced', get: r => r.announced_date },
      { label: 'Usable', get: r => r.usable ? chip('Usable', 'good') : chip('Not usable', 'warning') },
      { label: 'Multiplier', num: true, get: r => r.multiplier, fmt: v => fmtNum(v, 3) },
      { label: 'Measured lift', num: true, get: r => r.measured_lift, fmt: v => fmtMoney(v) },
      { label: 'Forecast lift', num: true, get: r => r.forecast_lift, fmt: v => fmtMoney(v) },
      { label: 'Reason', get: r => r.reason, wrap: true }
    ],
    rows: B.events
  });
  root.appendChild(evCard);
};

/* ---- 6.9 Evidence ---- */

RENDERERS.evidence = function renderEvidence(root, res) {
  void res;
  root.appendChild(storyCard('evidence'));

  const claims = Array.isArray(DATA.claims)
    ? DATA.claims
    : (DATA.claims && Array.isArray(DATA.claims.claims) ? DATA.claims.claims : null);

  const card = el('section', 'card');
  append(card,
    el('h2', null, 'Claims and evidence: what we assert, what tested it, and what could still be wrong'),
    el('p', 'how', 'One row per claim. The alternative column records the competing explanation we tested; the limitation column says what the data cannot rule out. Use the link to jump to the relevant tab.'),
    el('p', 'source', 'claims.json (analyst-authored), linked to analysis.json and model.json')
  );
  if (claims && claims.length) {
    if (DATA.claims && DATA.claims._dummy) card.appendChild(el('span', 'dummy-note', 'Dummy placeholder — analyst claims pending'));
    renderTable(card, {
      columns: [
        { label: 'ID', get: r => r.id },
        { label: 'Claim', get: r => r.claim, wrap: true },
        { label: 'Source', get: r => r.source, wrap: true },
        { label: 'Result', get: r => r.result, wrap: true },
        { label: 'Alternative tested', get: r => r.alternative, wrap: true },
        { label: 'Limitation', get: r => r.limitation, wrap: true },
        {
          label: 'Tab',
          get: r => {
            if (!r.tab || !TABS.includes(r.tab)) return el('span', 'muted', '—');
            const btn = el('button', 'btn btn-sm', TAB_LABELS[r.tab] || r.tab);
            btn.type = 'button';
            btn.addEventListener('click', () => applyEvidenceLink({ tab: r.tab }));
            return btn;
          }
        }
      ],
      rows: claims
    });
  } else {
    card.appendChild(el('div', 'pending', 'Claims pending — claims.json is missing or has no rows.'));
  }
  root.appendChild(card);

  const ai = DATA.story && DATA.story.ai;
  if (ai) {
    root.appendChild(storyCard('ai', { title: 'AI-use disclosure' }));
  } else {
    root.appendChild(pendingCard('AI-use disclosure', 'story.json should include an "ai" entry describing how AI was used.'));
  }
};

/* =========================================================================
   7. Boot and window.__selftest()
   ========================================================================= */

async function init() {
  try {
    await ensureData();
    parseHash();
    setupShell();
    syncHash();
    applyStateToView();
    render();
  } catch (err) {
    console.error(err);
    const app = $('#app');
    if (!app) return;
    clear(app);
    const card = el('section', 'card error-card');
    append(card,
      el('h2', null, 'The dashboard data could not be loaded'),
      el('p', null, String(err && err.message ? err.message : err)),
      el('p', 'muted', 'Serve the site from the site/ folder (for example: python -m http.server 8000) so that data/*.json is reachable.')
    );
    app.appendChild(card);
  }
}

function runSelftest() {
  const res = computeAll(0, DATA.core.dates.length - 1);
  return {
    nMachines: res.perMachine.length,
    gmList: res.gm.map(r => r.id),
    sumHW: round2(res.totals.hw),
    sumTheo: round2(res.totals.th),
    leakIds: res.leakIds.slice()
  };
}

/**
 * Exposed for a browser console check. After the dashboard has loaded this
 * returns the result object synchronously; if called while data is still
 * loading it returns a Promise of the same object.
 */
window.__selftest = function __selftest() {
  if (DATA) return runSelftest();
  return ensureData().then(runSelftest);
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
