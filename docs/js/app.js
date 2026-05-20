// ══════════════════════════════════════════════════════════
// STATE & UTILS
// ══════════════════════════════════════════════════════════
const state = { evalData: null, trendData: null, overlapData: null, activeTab: null };
const charts = {};
let tbl = { filtered: [], page: 0, pageSize: 30, sortKey: '_priorityOrder', sortDir: 1 };
let spm = { sortKey: null, sortDir: 1 };

const num = v => parseFloat(v) || 0;
const pct = (n, t) => t ? ((n / t) * 100).toFixed(1) + '%' : '0%';
const avg = arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
const countVal = (arr, k, v) => arr.filter(r => String(r[k] ?? '').trim() === String(v).trim()).length;
const isTrue = v => v === true || v === 'TRUE' || v === 'true' || v === 'True' || v === 1 || v === '1';
const trunc = (s, n) => s && s.length > n ? s.slice(0, n) + '…' : (s || '');

function scoreColor(s) {
  if (s >= 90) return '#16a34a'; if (s >= 70) return '#65a30d';
  if (s >= 50) return '#d97706'; return '#dc2626';
}
function priColor(p) {
  return { red: '#dc2626', yellow: '#d97706', green: '#16a34a', gray: '#94a3b8' }[p] || '#94a3b8';
}
function priBadge(p) {
  const cls = { red: 'b-red', yellow: 'b-yellow', green: 'b-green', gray: 'b-gray' }[p] || 'b-gray';
  const lbl = { red: '🔴 Red', yellow: '🟡 Yellow', green: '🟢 Green', gray: '⚪ Gray' }[p] || (p || '–');
  return `<span class="badge ${cls}">${lbl}</span>`;
}
function hasAiError(row) {
  return !String(row?.ai_response || '').trim() &&
         !String(row?.primary_article_url || '').trim() &&
         !String(row?.citation_1_url || '').trim();
}
function spmPriority(row) {
  return hasAiError(row) ? 'gray' : (row.synthesis_priority || 'gray');
}
function spmPriorityOrder(row) {
  const p = spmPriority(row);
  return p === 'red' ? 1 : p === 'yellow' ? 2 : p === 'green' ? 3 : 4;
}
function verdictBadge(v) {
  const cls = { adequate: 'b-green', needs_supplementation: 'b-yellow', inadequate: 'b-red', no_citation_provided: 'b-purple' }[v] || 'b-gray';
  return `<span class="badge ${cls}">${(v || '–').replace(/_/g, ' ')}</span>`;
}
function citationVerdictBadge(v) {
  const map = { good: ['b-green', '✓ Good Article'], partial: ['b-yellow', '~ Partial'], bad: ['b-red', '✗ Poor Article'] };
  const [cls, lbl] = map[v] || ['b-gray', (v || '–').replace(/_/g, ' ')];
  return `<span class="badge ${cls}">${lbl}</span>`;
}
function actionBadge(v) {
  const cls = { none: 'b-green', add_context: 'b-yellow', find_better_article: 'b-yellow', create_content: 'b-red' }[v] || 'b-gray';
  const lbl = { none: 'None', add_context: 'Action Required', find_better_article: 'Find Better Article', create_content: 'Create Content' }[v] || (v || '–').replace(/_/g, ' ');
  return `<span class="badge ${cls}">${lbl}</span>`;
}
function scoreChip(s) {
  const sc = num(s); return `<span class="score-chip" style="background:${scoreColor(sc)}">${sc.toFixed(0)}</span>`;
}
function descQualityBadge(score) {
  const s = num(score);
  if (s >= 70) return `<span class="badge b-green">High</span>`;
  if (s >= 40) return `<span class="badge b-yellow">OK</span>`;
  return `<span class="badge b-red">Low</span>`;
}
// Strip "Exchange Online/" prefix (and anything before it) to get the leaf segment
function exoLeaf(ap) {
  const marker = 'exchange online/';
  const idx = ap.toLowerCase().indexOf(marker);
  return idx >= 0 ? ap.slice(idx + marker.length) : ap;
}
// Area path chip — Exchange cases show leaf after "Exchange Online/", others truncated
function evalAreaChip(row, maxLen) {
  const ap = row._areaPath;
  if (!ap) return '<span style="color:#94a3b8;font-size:10px">–</span>';
  const isExo = (row._product || '').toLowerCase().includes('exchange');
  if (isExo) return `<span class="area-chip">${exoLeaf(ap)}</span>`;
  return `<span class="area-chip">${trunc(ap, maxLen)}</span>`;
}
function trendAreaChip(row, maxLen) {
  const ap = row._areaPath;
  if (!ap) return '';
  const isExo = (row.products_affected || '').toLowerCase().includes('exchange');
  if (isExo) return `<span class="area-chip">${exoLeaf(ap)}</span>`;
  return `<span class="area-chip">${trunc(ap, maxLen)}</span>`;
}
function kpiCard(label, value, sub, barPct, barColor) {
  const bar = barPct != null ? `<div class="kpi-bar"><div class="kpi-bar-fill" style="width:${Math.min(barPct,100)}%;background:${barColor}"></div></div>` : '';
  return `<div class="kpi-card">
    <div class="kpi-label">${label}</div>
    <div class="kpi-value"${barColor && barPct != null ? ` style="color:${barColor}"` : ''}>${value}</div>
    ${sub ? `<div class="kpi-sub">${sub}</div>` : ''}${bar}</div>`;
}
function scoreBandBar(label, val, maxVal) {
  const v = parseFloat(val) || 0; const m = maxVal || 100; const color = scoreColor(v);
  return `<div class="score-bar-row">
    <div class="score-bar-label">${label}</div>
    <div class="score-bar-track"><div class="score-bar-fill" style="width:${(v/m)*100}%;background:${color}"></div></div>
    <div class="score-bar-val" style="color:${color}">${v.toFixed(1)}</div></div>`;
}

// Bullet list from semicolon-separated text
function bulletList(text) {
  if (!text || !text.trim()) return '<em>Not provided</em>';
  const items = text.split(';').map(s => s.trim()).filter(Boolean);
  if (items.length === 1) return `<span>${items[0]}</span>`;
  return `<ul class="detail-bullets">${items.map(i => `<li>${i}</li>`).join('')}</ul>`;
}
function textOrEmpty(text) {
  return (text && text.trim()) ? text.trim() : '<em>Not provided</em>';
}
function renderMweaResponse(text) {
  if (!text || !text.trim()) return '<em>Not provided</em>';
  const body = text.trim()
    .replace(/\[(\d+)\]/g, '<sup><a href="#cit-$1" style="color:#3b82f6;text-decoration:none;font-weight:700">[$1]</a></sup>')
    .split(/\n\n+/)
    .map(p => `<p style="margin-bottom:10px">${p.replace(/\n/g, '<br>')}</p>`)
    .join('');
  return `<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px;font-size:13px;line-height:1.6;color:#1e293b">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:#64748b;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f1f5f9">📧 MWEA Response</div>
    ${body}
  </div>`;
}

// ══════════════════════════════════════════════════════════
// CROSS-FILTER STATE
// ══════════════════════════════════════════════════════════
const filterState = {};
const MATCHERS = {
  priority:     (r, v) => spmPriority(r) === v,
  verdict:      (r, v) => r.primary_article_verdict === v,
  scoreBand:    (r, v) => r._scoreBand === v,
  relVerdict:   (r, v) => r.article_relevance_verdict === v,
  compVerdict:  (r, v) => r.article_completeness_verdict === v,
  valVerdict:   (r, v) => r.article_validity_verdict === v,
  dqVerdict:    (r, v) => r.dq_description_quality_verdict === v,
  groundVerdict:(r, v) => r.citation_grounding_verdict === v,
  rqVerdict:    (r, v) => r.rq_ai_response_quality_verdict === v,
  rootCause:    (r, v) => (r.synthesis_root_cause_category || 'Unknown') === v,
  product:      (r, v) => r._product === v,
  areaPath:     (r, v) => (r._areaPath || '') === v,
};
const DIM_LABELS = {
  priority:'Priority', verdict:'Verdict',
  scoreBand:'Score Band', relVerdict:'Relevance', compVerdict:'Completeness',
  valVerdict:'Validity', dqVerdict:'Description Quality Verdict', groundVerdict:'Grounding',
  rqVerdict:'Response Quality', rootCause:'Root Cause', product:'Product',
  areaPath:'Area Path',
};

// Returns data filtered by all active filters EXCEPT excludeDim (so each chart sees others' filters but not its own)
function getFiltered(excludeDim) {
  if (!state.evalData) return [];
  return state.evalData.filter(row =>
    Object.entries(filterState).every(([d, v]) => d === excludeDim || MATCHERS[d](row, v))
  );
}
// Returns data filtered by ALL active filters (for KPIs and table)
function getFilteredAll() { return getFiltered('__none__'); }

function hexAlpha(hex, a) {
  const rr = parseInt(hex.slice(1,3),16), gg = parseInt(hex.slice(3,5),16), bb = parseInt(hex.slice(5,7),16);
  return `rgba(${rr},${gg},${bb},${a})`;
}
function dimColors(colors, activeVal, values) {
  if (activeVal == null) return colors;
  return colors.map((c, i) => values[i] === activeVal ? c : hexAlpha(c, 0.2));
}

function toggleFilter(dim, val) {
  if (filterState[dim] === val) delete filterState[dim]; else filterState[dim] = val;
  updateEvalView();
}
function clearFilter(dim) { delete filterState[dim]; updateEvalView(); }
function clearAllFilters() { Object.keys(filterState).forEach(k => delete filterState[k]); updateEvalView(); }

function renderFilterChips() {
  const el = document.getElementById('filter-chips'); if (!el) return;
  const entries = Object.entries(filterState);
  if (!entries.length) { el.style.display = 'none'; return; }
  el.style.display = 'flex';
  el.innerHTML = entries.map(([dim, val]) =>
    `<span style="background:#eff6ff;border:1px solid #bfdbfe;color:#1d4ed8;padding:3px 6px 3px 10px;border-radius:12px;font-size:11px;font-weight:600;display:inline-flex;align-items:center;gap:4px">
      ${DIM_LABELS[dim]}: <strong>${val.replace(/_/g,' ')}</strong>
      <button onclick="clearFilter('${dim}')" style="background:none;border:none;cursor:pointer;color:#3b82f6;font-size:15px;line-height:1;padding:0 1px">×</button>
    </span>`
  ).join('') + `<button onclick="clearAllFilters()" style="background:#e2e8f0;border:none;cursor:pointer;padding:3px 10px;border-radius:12px;font-size:11px;color:#374151;font-weight:600">Clear all</button>`;
}

// ══════════════════════════════════════════════════════════
// CHART HELPERS (cross-filter aware)
// ══════════════════════════════════════════════════════════
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  const el = document.getElementById(id);
  if (el) { const existing = Chart.getChart(el); if (existing) existing.destroy(); }
}

// Donut — predefined values list
function makeDonut(id, labels, values, keyFn, colors, dim) {
  destroyChart(id);
  const ctx = document.getElementById(id); if (!ctx) return;
  const data = getFiltered(dim);
  const activeVal = filterState[dim] ?? null;
  const counts = values.map(v => data.filter(r => keyFn(r) === v).length);
  const bgColors = dimColors(colors, activeVal, values);
  const total = counts.reduce((a,b) => a+b, 0);
  charts[id] = new Chart(ctx.getContext('2d'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data: counts, backgroundColor: bgColors, borderWidth: 2, borderColor: '#fff', hoverOffset: 3 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '60%',
      plugins: {
        legend: { position: 'right', labels: { font: { size: 10 }, boxWidth: 10, padding: 5,
          generateLabels: chart => labels.map((lbl, i) => ({
            text: lbl, fillStyle: bgColors[i], strokeStyle: '#fff', lineWidth: 1,
            fontColor: activeVal !== null && values[i] !== activeVal ? '#b0b8c4' : '#374151',
            datasetIndex: 0, index: i, hidden: false
          }))
        }},
        tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw} (${total ? ((c.raw/total)*100).toFixed(1) : 0}%)` } }
      },
      onClick: (evt, els) => { if (els.length) toggleFilter(dim, values[els[0].index]); else if (activeVal !== null) clearFilter(dim); }
    }
  });
}

// Horizontal bar — predefined values list
function makeHBar(id, labels, values, keyFn, colors, dim) {
  destroyChart(id);
  const ctx = document.getElementById(id); if (!ctx) return;
  const data = getFiltered(dim);
  const activeVal = filterState[dim] ?? null;
  const counts = values.map(v => data.filter(r => keyFn(r) === v).length);
  const bgColors = dimColors(Array.isArray(colors) ? colors : values.map(() => colors), activeVal, values);
  charts[id] = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: counts, backgroundColor: bgColors, borderRadius: 3, barThickness: 18 }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.raw} cases` } } },
      scales: { x: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } },
      onClick: (evt, els) => { if (els.length) toggleFilter(dim, values[els[0].index]); else if (activeVal !== null) clearFilter(dim); }
    }
  });
}

// Horizontal bar — dynamic values from data (root cause, etc.)
function makeDynHBar(id, keyFn, colorFn, dim) {
  destroyChart(id);
  const ctx = document.getElementById(id); if (!ctx) return;
  const data = getFiltered(dim);
  const activeVal = filterState[dim] ?? null;
  const map = {}; data.forEach(r => { const v = keyFn(r)||'Unknown'; map[v]=(map[v]||0)+1; });
  const sorted = Object.entries(map).sort((a,b)=>b[1]-a[1]);
  const labels = sorted.map(([k])=>k), values = labels, counts = sorted.map(([,v])=>v);
  const bgColors = sorted.map(([k]) => { const c=colorFn(k); return activeVal!==null&&k!==activeVal?hexAlpha(c,0.2):c; });
  charts[id] = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: counts, backgroundColor: bgColors, borderRadius: 3, barThickness: 18 }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.raw} cases` } } },
      scales: { x: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } },
      onClick: (evt, els) => { if (els.length) toggleFilter(dim, values[els[0].index]); else if (activeVal !== null) clearFilter(dim); }
    }
  });
}

// Vertical bar — score bands (predefined)
function makeVBar(id, labels, values, keyFn, colors, dim) {
  destroyChart(id);
  const ctx = document.getElementById(id); if (!ctx) return;
  const data = getFiltered(dim);
  const activeVal = filterState[dim] ?? null;
  const counts = values.map(v => data.filter(r => keyFn(r) === v).length);
  const bgColors = dimColors(colors, activeVal, values);
  charts[id] = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: counts, backgroundColor: bgColors, borderRadius: 3, barThickness: 28 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.raw} cases` } } },
      scales: { x: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 }, maxRotation: 20 } }, y: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } } },
      onClick: (evt, els) => { if (els.length) toggleFilter(dim, values[els[0].index]); else if (activeVal !== null) clearFilter(dim); }
    }
  });
}

// Vertical bar — avg score by product (dynamic, filterable by product)
function makeProdBar(id, dim) {
  destroyChart(id);
  const ctx = document.getElementById(id); if (!ctx) return;
  const data = getFiltered(dim);
  const activeVal = filterState[dim] ?? null;
  const map = {}; data.forEach(r => { const k=r._product||'Unknown'; if(!map[k]) map[k]=[]; map[k].push(num(r.primary_article_score)); });
  const sorted = Object.entries(map).map(([k,v])=>[k,avg(v),v.length]).sort((a,b)=>b[2]-a[2]).slice(0,12);
  const labels = sorted.map(([k])=>k), values = labels;
  const scores = sorted.map(([,s])=>parseFloat(s.toFixed(1)));
  const bgColors = sorted.map(([k,s])=>{ const c=scoreColor(s); return activeVal!==null&&k!==activeVal?hexAlpha(c,0.2):c; });
  charts[id] = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: scores, backgroundColor: bgColors, borderRadius: 3 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` Avg score: ${c.raw}` } } },
      scales: { x: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 }, maxRotation: 30 } }, y: { beginAtZero: true, max: 100, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } } },
      onClick: (evt, els) => { if (els.length) toggleFilter(dim, values[els[0].index]); else if (activeVal !== null) clearFilter(dim); }
    }
  });
}

// ══════════════════════════════════════════════════════════
// CSV PARSING
// ══════════════════════════════════════════════════════════
function parseEval(text) {
  const r = Papa.parse(text, { header: true, skipEmptyLines: true, dynamicTyping: true });
  return r.data.map(row => {
    const s = num(row.primary_article_score);
    row._scoreBand = s >= 90 ? '90-100' : s >= 70 ? '70-89' : s >= 50 ? '50-69' : '0-49';
    row._priorityOrder = spmPriorityOrder(row);
    row._hasError = !!(row.error && String(row.error).trim());
    row._product = row.issue_product || (row.sap_path ? String(row.sap_path).split('/')[0].trim() : 'Unknown');
    const _isExchange = row._product.toLowerCase().includes('exchange');
    row._areaPath = (row.area_path || '').trim() || (_isExchange ? (row.sap_path || '').trim() : '');
    return row;
  });
}
function parseTrend(text) {
  const r = Papa.parse(text, { header: true, skipEmptyLines: true, dynamicTyping: true });
  return r.data.map(row => {
    row._priorityOrder = row.priority === 'red' ? 1 : row.priority === 'yellow' ? 2 : row.priority === 'green' ? 3 : 4;
    const m = String(row.estimated_impact || '').match(/~(\d+)/);
    row._impact = m ? parseInt(m[1]) : num(row.case_count);
    const _isExchange = (row.products_affected || '').toLowerCase().includes('exchange');
    row._areaPath = (row.area_path || '').trim() || (_isExchange ? (row.products_affected || '').trim() : '');
    return row;
  }).sort((a, b) => a._priorityOrder - b._priorityOrder || b.case_count - a.case_count);
}
function parseOverlaps(text) {
  const r = Papa.parse(text, { header: true, skipEmptyLines: true, dynamicTyping: true });
  return r.data.map(row => {
    row._snippets = (row.issue_snippets || '').split('|').map(s => s.trim()).filter(Boolean);
    row._cases = (row.case_numbers || '').split(';').map(s => s.trim()).filter(Boolean);
    return row;
  }).sort((a, b) => {
    const typeOrder = t => t === 'cross_coverage' ? 0 : 1;
    return typeOrder(a.overlap_type) - typeOrder(b.overlap_type) || num(b.case_count) - num(a.case_count);
  });
}
function isMwea(data) {
  return data.some(r => r.citation_grounding_score !== null && r.citation_grounding_score !== undefined && String(r.citation_grounding_score).trim() !== '');
}

// ══════════════════════════════════════════════════════════
// UPLOAD
// ══════════════════════════════════════════════════════════
function onDragOver(e, id) { e.preventDefault(); document.getElementById(id).classList.add('drag-over'); }
function onDragLeave(id) { document.getElementById(id).classList.remove('drag-over'); }
function onDrop(e, type) {
  e.preventDefault();
  const cardId = type === 'eval' ? 'eval-card' : type === 'trend' ? 'trend-card' : 'overlap-card';
  document.getElementById(cardId).classList.remove('drag-over');
  const f = e.dataTransfer.files[0]; if (f) readFile(f, type);
}
function handleFile(e, type) { if (e.target.files[0]) readFile(e.target.files[0], type); }
function readFile(file, type) {
  const reader = new FileReader();
  reader.onload = e => {
    try {
      if (type === 'eval') {
        state.evalData = parseEval(e.target.result);
        setLoaded('eval', file.name, state.evalData.length + ' cases');
        renderSPM(); renderEval();
      } else if (type === 'trend') {
        state.trendData = parseTrend(e.target.result);
        setLoaded('trend', file.name, state.trendData.length + ' clusters');
        renderTrends();
      } else {
        state.overlapData = parseOverlaps(e.target.result);
        setLoaded('overlap', file.name, state.overlapData.length + ' overlaps');
        renderOverlaps();
      }
      updateTabs();
    } catch (err) { alert('Error parsing CSV: ' + err.message); console.error(err); }
  };
  reader.readAsText(file, 'UTF-8');
}
function setLoaded(type, fname, sub) {
  const ids = { eval: ['eval-card','eval-icon','eval-fname','eval-hint'], trend: ['trend-card','trend-icon','trend-fname','trend-hint'], overlap: ['overlap-card','overlap-icon','overlap-fname','overlap-hint'] };
  const [cardId, iconId, fnameId, hintId] = ids[type];
  document.getElementById(cardId).classList.add('loaded');
  document.getElementById(iconId).textContent = '✅';
  document.getElementById(fnameId).textContent = fname;
  document.getElementById(hintId).textContent = sub;
}
function clearFile(e, type) {
  e.preventDefault(); e.stopPropagation();
  const defaults = { eval: ['📋','evaluation_results_*.csv'], trend: ['📈','trend_report_*.csv'], overlap: ['🔗','citation_overlaps_*.csv'] };
  const ids = { eval: ['eval-card','eval-icon','eval-fname','eval-hint','eval-input'], trend: ['trend-card','trend-icon','trend-fname','trend-hint','trend-input'], overlap: ['overlap-card','overlap-icon','overlap-fname','overlap-hint','overlap-input'] };
  const [cardId, iconId, fnameId, hintId, inputId] = ids[type];
  const [icon, hint] = defaults[type];
  document.getElementById(cardId).classList.remove('loaded');
  document.getElementById(iconId).textContent = icon;
  document.getElementById(fnameId).textContent = '';
  document.getElementById(hintId).textContent = hint;
  document.getElementById(inputId).value = '';
  if (type === 'eval') state.evalData = null;
  else if (type === 'trend') state.trendData = null;
  else state.overlapData = null;
  updateTabs();
}
function updateTabs() {
  const hasEval = !!state.evalData, hasTrend = !!state.trendData, hasOverlap = !!state.overlapData;
  const hasSome = hasEval || hasTrend || hasOverlap;
  document.getElementById('empty-state').style.display = hasSome ? 'none' : 'block';
  document.getElementById('tabs').classList.toggle('visible', hasSome);
  ['spm', 'eval'].forEach(t => {
    const btn = document.getElementById('tab-' + t);
    btn.classList.toggle('disabled', !hasEval);
    btn.classList.toggle('has-data', hasEval);
  });
  const tBtn = document.getElementById('tab-trends');
  tBtn.classList.toggle('disabled', !hasTrend);
  tBtn.classList.toggle('has-data', hasTrend);
  const oBtn = document.getElementById('tab-overlaps');
  oBtn.classList.toggle('disabled', !hasOverlap);
  oBtn.classList.toggle('has-data', hasOverlap);

  if (state.activeTab === 'spm' && !hasEval) state.activeTab = null;
  if (state.activeTab === 'eval' && !hasEval) state.activeTab = null;
  if (state.activeTab === 'trends' && !hasTrend) state.activeTab = null;
  if (state.activeTab === 'overlaps' && !hasOverlap) state.activeTab = null;
  if (!state.activeTab && hasSome) {
    state.activeTab = hasEval ? 'spm' : hasTrend ? 'trends' : 'overlaps';
  }
  if (state.activeTab) showTab(state.activeTab);
}
function showTab(tab) {
  if ((tab === 'spm' || tab === 'eval') && !state.evalData) return;
  if (tab === 'trends' && !state.trendData) return;
  if (tab === 'overlaps' && !state.overlapData) return;
  state.activeTab = tab;
  ['spm', 'eval', 'trends', 'overlaps'].forEach(t => {
    document.getElementById('content-' + t).classList.toggle('active', t === tab);
    document.getElementById('tab-' + t).classList.toggle('active', t === tab);
  });
}

// ══════════════════════════════════════════════════════════
// CASE DETAIL PANEL
// ══════════════════════════════════════════════════════════
function buildDetailPanel(row, mweaMode, isSpmTab) {
  const pmActions = row.synthesis_pm_actions || '';
  const priReason = row.synthesis_priority_reason || '';
  const finalRec = row.final_recommendation || '';
  const rqAnalysis = row.rq_response_quality_analysis || '';
  const gndAnalysis = row.rq_groundedness_analysis || '';
  const resAnalysis = row.rq_issue_resolution_analysis || '';
  const weaknesses = row.rq_quality_weaknesses || '';
  const improvements = row.rq_improvement_suggestions || '';
  const dqMissing = row.dq_missing_elements || '';
  const dqSuggestions = row.dq_improvement_suggestions || '';
  const artMissing = row.article_completeness_missing_elements || '';
  const artIssues = row.article_validity_potential_issues || '';
  const url = row.primary_article_url || '';
  const warn = isTrue(row.dq_evaluation_reliability_warning);
  const isExo = (row._product || '').toLowerCase().includes('exchange');

  let html = `<div class="detail-panel">`;

  if (isSpmTab) {
    // ── SPM tab: show case context at top ──────────────────────
    // Customer description quality warning (replaces KT warning)
    if (warn) html += `<div class="detail-block detail-full-row"><div class="detail-warning">⚠️ Customer description scored low — evaluation reliability may be reduced.</div></div>`;

    // PM Actions — full width, most important
    html += `<div class="detail-block detail-full-row">
      <div class="detail-label">💡 PM Actions</div>
      <div class="detail-text">${bulletList(pmActions)}</div>
    </div>`;

    // Case title
    if (row.case_number) {
      html += `<div class="detail-block">
        <div class="detail-label">🏷️ Case Title</div>
        <div class="detail-text" style="font-family:monospace">${row.case_number}</div>
      </div>`;
    }

    // Customer description quality badge
    html += `<div class="detail-block">
      <div class="detail-label">📊 Customer Description</div>
      <div class="detail-text">${descQualityBadge(row.dq_description_quality_score)} <span style="color:#64748b;font-size:11px">(score: ${num(row.dq_description_quality_score).toFixed(0)})</span></div>
    </div>`;

    // Problem description
    if ((row.issue_description || '').trim()) {
      html += `<div class="detail-block detail-full-row">
        <div class="detail-label">📝 Problem Description</div>
        <div class="detail-text" style="white-space:pre-wrap">${(row.issue_description || '').trim()}</div>
      </div>`;
    }

    // MWEA Response
    if ((row.ai_response || '').trim()) {
      html += `<div class="detail-block detail-full-row">
        <div class="detail-label">🤖 MWEA Response</div>
        <div class="detail-text">${renderMweaResponse(row.ai_response)}</div>
      </div>`;
    }

    // Area Path
    if (row._areaPath) {
      const apDisplay = isExo ? exoLeaf(row._areaPath) : row._areaPath;
      html += `<div class="detail-block">
        <div class="detail-label">📍 Area Path</div>
        <div class="detail-text"><span class="area-chip">${apDisplay}</span></div>
      </div>`;
    }

    // Priority Reason
    html += `<div class="detail-block">
      <div class="detail-label">🎯 Priority Reason</div>
      <div class="detail-text">${textOrEmpty(priReason)}</div>
    </div>`;

    // Final Recommendation
    html += `<div class="detail-block">
      <div class="detail-label">📋 Final Recommendation</div>
      <div class="detail-text">${textOrEmpty(finalRec)}</div>
    </div>`;

    if (mweaMode) {
      if (rqAnalysis.trim()) html += `<div class="detail-block"><div class="detail-label">📝 Response Quality Analysis</div><div class="detail-text">${rqAnalysis}</div></div>`;
      if (gndAnalysis.trim()) html += `<div class="detail-block"><div class="detail-label">🔗 Groundedness Analysis</div><div class="detail-text">${gndAnalysis}</div></div>`;
      if (resAnalysis.trim()) html += `<div class="detail-block"><div class="detail-label">✅ Issue Resolution Analysis</div><div class="detail-text">${resAnalysis}</div></div>`;
      if (weaknesses.trim()) html += `<div class="detail-block"><div class="detail-label">⚠️ Quality Weaknesses</div><div class="detail-text">${bulletList(weaknesses)}</div></div>`;
      if (improvements.trim()) html += `<div class="detail-block"><div class="detail-label">🔧 Response Improvement Suggestions</div><div class="detail-text">${bulletList(improvements)}</div></div>`;
    }

    // Citations with weights — sorted by score, numbered with [N] reference
    const citations = [];
    for (let i = 1; i <= 10; i++) {
      const cUrl = (row[`citation_${i}_url`] || '').trim();
      if (!cUrl) break;
      citations.push({ refNum: i, url: cUrl, score: num(row[`citation_${i}_score`]), verdict: (row[`citation_${i}_verdict`] || '').trim(), coverage: num(row[`citation_${i}_coverage`]), isPrimary: !!(url && cUrl === url) });
    }
    const sortedCitations = [...citations].sort((a, b) => b.score - a.score);
    if (sortedCitations.length) {
      html += `<div class="detail-block detail-full-row">
        <div class="detail-label">🔗 Citations (${sortedCitations.length})</div>
        <div style="font-size:10px;color:#94a3b8;margin:2px 0 6px">Sorted by relevance score. Reference numbers [N] correspond to citations in the MWEA response above.${sortedCitations.length > 1 ? ' Coverage % shows how much of the AI response each article supports — citations can overlap.' : ''}</div>
        ${sortedCitations.map(c => `<div id="cit-${c.refNum}" style="background:#f8fafc;border-radius:6px;padding:7px 10px;margin-top:5px;border-left:3px solid ${scoreColor(c.score)}">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span style="background:#e0f2fe;color:#0369a1;border-radius:4px;padding:1px 6px;font-size:10px;font-weight:800;font-family:monospace;flex-shrink:0">[${c.refNum}]</span>
            ${c.isPrimary ? `<span class="badge b-yellow" style="flex-shrink:0">⭐ Primary</span>` : ''}
            <a href="${c.url}" target="_blank" class="detail-link" style="flex:1;min-width:0">${trunc(c.url, 80)}</a>
            <span class="score-chip" style="background:${scoreColor(c.score)}">${c.score.toFixed(0)}</span>
            ${c.verdict ? citationVerdictBadge(c.verdict) : ''}
          </div>
          ${c.coverage ? `<div style="font-size:11px;color:#64748b;margin-top:3px" title="How much of the AI response this article covers. Each citation is scored independently — totals across citations can exceed 100%.">Coverage: ${c.coverage.toFixed(0)}%</div>` : ''}
        </div>`).join('')}
      </div>`;
    }

    // Article gaps
    if (artMissing.trim()) html += `<div class="detail-block"><div class="detail-label">📄 Primary Article — Missing Elements</div><div class="detail-text"><div style="font-size:10px;color:#94a3b8;margin-bottom:4px">(applies to the ⭐ primary article above)</div>${bulletList(artMissing)}</div></div>`;
    if (artIssues.trim()) html += `<div class="detail-block"><div class="detail-label">🚨 Article Potential Issues</div><div class="detail-text">${bulletList(artIssues)}</div></div>`;

  } else {
    // ── Eval tab: original full display with KT items ──────────
    if (warn) html += `<div class="detail-block detail-full-row"><div class="detail-warning">⚠️ Low KT confidence — description quality below 40. Evaluation reliability may be reduced.</div></div>`;

    // PM Actions — full width, most important
    html += `<div class="detail-block detail-full-row">
      <div class="detail-label">💡 PM Actions</div>
      <div class="detail-text">${bulletList(pmActions)}</div>
    </div>`;

    // Area Path
    if (row._areaPath) {
      const apDisplay = isExo ? exoLeaf(row._areaPath) : row._areaPath;
      html += `<div class="detail-block">
        <div class="detail-label">📍 Area Path</div>
        <div class="detail-text"><span class="area-chip">${apDisplay}</span></div>
      </div>`;
    }

    // Priority Reason
    html += `<div class="detail-block">
      <div class="detail-label">🎯 Priority Reason</div>
      <div class="detail-text">${textOrEmpty(priReason)}</div>
    </div>`;

    // Final Recommendation
    html += `<div class="detail-block">
      <div class="detail-label">📋 Final Recommendation</div>
      <div class="detail-text">${textOrEmpty(finalRec)}</div>
    </div>`;

    if (mweaMode) {
      // Response Quality Analysis
      if (rqAnalysis.trim()) {
        html += `<div class="detail-block">
          <div class="detail-label">📝 Response Quality Analysis</div>
          <div class="detail-text">${rqAnalysis}</div>
        </div>`;
      }
      // Groundedness Analysis
      if (gndAnalysis.trim()) {
        html += `<div class="detail-block">
          <div class="detail-label">🔗 Groundedness Analysis</div>
          <div class="detail-text">${gndAnalysis}</div>
        </div>`;
      }
      // Issue Resolution Analysis
      if (resAnalysis.trim()) {
        html += `<div class="detail-block">
          <div class="detail-label">✅ Issue Resolution Analysis</div>
          <div class="detail-text">${resAnalysis}</div>
        </div>`;
      }
      // Weaknesses
      if (weaknesses.trim()) {
        html += `<div class="detail-block">
          <div class="detail-label">⚠️ Quality Weaknesses</div>
          <div class="detail-text">${bulletList(weaknesses)}</div>
        </div>`;
      }
      // Improvement Suggestions
      if (improvements.trim()) {
        html += `<div class="detail-block">
          <div class="detail-label">🔧 Response Improvement Suggestions</div>
          <div class="detail-text">${bulletList(improvements)}</div>
        </div>`;
      }
    }

    // DQ Missing Elements
    if (dqMissing.trim()) {
      html += `<div class="detail-block">
        <div class="detail-label">❓ Description Missing Elements</div>
        <div class="detail-text">${bulletList(dqMissing)}</div>
      </div>`;
    }
    if (dqSuggestions.trim()) {
      html += `<div class="detail-block">
        <div class="detail-label">📌 Description Improvement Suggestions</div>
        <div class="detail-text">${bulletList(dqSuggestions)}</div>
      </div>`;
    }

    // Article gaps
    if (artMissing.trim()) {
      html += `<div class="detail-block">
        <div class="detail-label">📄 Primary Article — Missing Elements</div>
        <div class="detail-text">${bulletList(artMissing)}</div>
      </div>`;
    }
    if (artIssues.trim()) {
      html += `<div class="detail-block">
        <div class="detail-label">🚨 Article Potential Issues</div>
        <div class="detail-text">${bulletList(artIssues)}</div>
      </div>`;
    }

    // Article URL
    if (url.trim()) {
      html += `<div class="detail-block detail-full-row">
        <div class="detail-label">🔗 Cited Article</div>
        <a href="${url}" target="_blank" class="detail-link">${url}</a>
      </div>`;
    }
  } // end else (eval tab)

  html += `</div>`;
  return html;
}

function toggleDetail(btn, caseIdx, tableBodyId, mweaMode) {
  const tbody = document.getElementById(tableBodyId);
  const dataRow = tbody.querySelector(`tr[data-idx="${caseIdx}"]`);
  const existing = tbody.querySelector(`tr.detail-row[data-idx="${caseIdx}"]`);
  if (existing) {
    existing.remove();
    dataRow.classList.remove('expanded');
    btn.classList.remove('open');
    btn.textContent = '▶';
  } else {
    // Close any other open detail
    tbody.querySelectorAll('tr.detail-row').forEach(r => r.remove());
    tbody.querySelectorAll('tr.data-row.expanded').forEach(r => r.classList.remove('expanded'));
    tbody.querySelectorAll('.expand-btn.open').forEach(b => { b.classList.remove('open'); b.textContent = '▶'; });

    const row = state.evalData[caseIdx];
    const detailTr = document.createElement('tr');
    detailTr.className = 'detail-row';
    detailTr.dataset.idx = caseIdx;
    const isSpmTab = tableBodyId === 'spm-table-body';
    const cols = isSpmTab ? 9 : 9;
    detailTr.innerHTML = `<td colspan="${cols}">${buildDetailPanel(row, mweaMode, isSpmTab)}</td>`;
    dataRow.after(detailTr);
    dataRow.classList.add('expanded');
    btn.classList.add('open');
    btn.textContent = '▶';
  }
}

// ══════════════════════════════════════════════════════════
// RENDER SPM ACTIONS
// ══════════════════════════════════════════════════════════
function renderSPM() {
  const data = state.evalData; if (!data) return;
  const n = data.length; // always full count for alert/KPIs
  const mwea = isMwea(data);

  function matchesSpmScoreRange(row, range) {
    if (!range) return true;
    const score = num(row.primary_article_score);
    if (range === '0-20') return score >= 0 && score <= 20;
    if (range === '21-40') return score >= 21 && score <= 40;
    if (range === '41-60') return score >= 41 && score <= 60;
    if (range === '60-100') return score >= 60 && score <= 100;
    return true;
  }

  // Populate area filter (once, on first render)
  const areaSelectEl = document.getElementById('spm-f-area');
  if (areaSelectEl && areaSelectEl.options.length <= 1) {
    const areas = [...new Set(data.map(r => r._areaPath).filter(Boolean))].sort();
    areas.forEach(a => { const o = document.createElement('option'); o.value = a; o.textContent = a; areaSelectEl.appendChild(o); });
  }

  // Apply local filters
  const searchVal = (document.getElementById('spm-search') || {}).value || '';
  const fpVal = (document.getElementById('spm-f-priority') || {}).value || '';
  const fsVal = (document.getElementById('spm-f-score') || {}).value || '';
  const faVal = (areaSelectEl || {}).value || '';
  const fdqVal = (document.getElementById('spm-f-dq') || {}).value || '';
  const filtered = data.filter(r =>
    (!fpVal || spmPriority(r) === fpVal) &&
    matchesSpmScoreRange(r, fsVal) &&
    (!faVal || r._areaPath === faVal) &&
    (!fdqVal || r.dq_description_quality_verdict === fdqVal) &&
    (!searchVal || String(r.case_number || '').includes(searchVal) || (r._areaPath || '').toLowerCase().includes(searchVal.toLowerCase()))
  );

  const redN = data.filter(r => spmPriority(r) === 'red').length;
  const yelN = data.filter(r => spmPriority(r) === 'yellow').length;
  const grnN = data.filter(r => spmPriority(r) === 'green').length;
  const errN = data.filter(r => hasAiError(r)).length;
  // Alert
  const alertEl = document.getElementById('spm-alert');
  if (redN > 0) {
    alertEl.innerHTML = `<div class="alert-banner alert-red">🚨 <strong>${redN} red-priority case${redN > 1 ? 's' : ''}</strong> require immediate PM action${errN > 0 ? ` (${errN} AI-error case${errN > 1 ? 's' : ''} excluded — no MWEA response received)` : ''} — articles need replacement or new content must be created.</div>`;
  } else if (yelN > 0) {
    alertEl.innerHTML = `<div class="alert-banner alert-yellow">⚠️ <strong>${yelN} yellow-priority case${yelN > 1 ? 's' : ''}</strong> need PM review${errN > 0 ? ` (${errN} AI-error case${errN > 1 ? 's' : ''} excluded)` : ''}.</div>`;
  } else {
    alertEl.innerHTML = `<div class="alert-banner alert-green">✅ No red-priority cases. All ${n - errN} evaluated cases are green or yellow${errN > 0 ? ` (${errN} AI-error case${errN > 1 ? 's' : ''} excluded from priority counts)` : ''}.</div>`;
  }

  // KPIs
  document.getElementById('spm-kpis').innerHTML = [
    `<div class="kpi-card"><div class="kpi-label">🔴 Immediate Action</div><div class="kpi-value c-red">${redN}</div><div class="kpi-sub">${pct(redN,n)} — critical article gaps</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">🟡 Needs Review</div><div class="kpi-value c-yellow">${yelN}</div><div class="kpi-sub">${pct(yelN,n)} — supplementation needed</div></div>`,
    `<div class="kpi-card" title="Cases with no MWEA response, article URL or citations — excluded from priority counts"><div class="kpi-label">⚠️ AI Errors</div><div class="kpi-value c-gray">${errN}</div><div class="kpi-sub">excluded from priority counts</div></div>`,
  ].join('');
  // Sort filtered: by spm.sortKey if set, otherwise by priority then score asc
  const sorted = [...filtered].sort((a, b) => {
    if (spm.sortKey) {
      const sk = spm.sortKey;
      if (sk === '_priorityOrder') return (spmPriorityOrder(a) - spmPriorityOrder(b)) * spm.sortDir;
      const av = a[sk], bv = b[sk];
      if (typeof av === 'number') return (av - bv) * spm.sortDir;
      return String(av||'').localeCompare(String(bv||'')) * spm.sortDir;
    }
    const aOrder = spmPriorityOrder(a);
    const bOrder = spmPriorityOrder(b);
    if (aOrder !== bOrder) return aOrder - bOrder;
    return num(a.primary_article_score) - num(b.primary_article_score);
  });

  const fn = filtered.length;
  document.getElementById('spm-table-badge').textContent = fn + (fn < n ? ' of ' + n : '') + ' cases';
  const rows = sorted.map(row => {
    const idx = data.indexOf(row);
    const pm = row.synthesis_pm_actions || '';
    const preview = pm.trim() ? trunc(pm.replace(/;/g, ' ·'), 80) : null;
    const pmTitle = (pm.trim() || 'No PM actions recorded').replace(/"/g, '&quot;');
    const areaHtml = evalAreaChip(row, 24);
    const citedUrl = (row.primary_article_url || '').trim();
    return `<tr class="data-row" data-idx="${idx}">
      <td><button class="expand-btn" onclick="toggleDetail(this,${idx},'spm-table-body',${mwea})" title="Show detail">▶</button></td>
      <td>${priBadge(spmPriority(row))}</td>
      <td style="font-family:monospace;font-size:11px">${row.case_number || '–'}</td>
      <td>${trunc(row._product || '–', 22)}</td>
      <td>${areaHtml}</td>
      <td>${scoreChip(row.primary_article_score)}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${citedUrl ? `<a href="${citedUrl}" target="_blank" class="detail-link" style="font-size:11px">${trunc(citedUrl, 40)}</a>` : '<span style="color:#94a3b8">—</span>'}</td>
      <td class="${preview ? 'pm-preview' : 'pm-empty'}" title="${pmTitle}">${preview || 'No PM actions recorded'}</td>
    </tr>`;
  }).join('');
  document.getElementById('spm-table-body').innerHTML = rows || '<tr><td colspan="8" style="text-align:center;color:#94a3b8;padding:20px">No cases</td></tr>';
}

// ══════════════════════════════════════════════════════════
// RENDER EVAL REPORT
// ══════════════════════════════════════════════════════════
function renderEval() {
  if (!state.evalData) return;
  // Reset text/select filters on first load only
  document.getElementById('table-search').value = '';
  document.getElementById('f-priority').value = '';
  document.getElementById('f-verdict').value = '';
  // Setup citation section visibility once
  document.getElementById('sec-citation').style.display = isMwea(state.evalData) ? '' : 'none';
  updateEvalView();
}

// Called on every filter change — re-renders everything using current filterState
function updateEvalView() {
  const allData = state.evalData; if (!allData) return;
  const data = getFilteredAll(); // KPIs & static elements use all-filtered data
  const n = data.length;
  const mwea = isMwea(allData);

  document.getElementById('eval-badge').textContent = n + ' of ' + allData.length + ' cases';
  renderFilterChips();

  // KPI cards (respond to filters)
  const adequate = countVal(data, 'primary_article_verdict', 'adequate');
  const avgScore = n ? avg(data.map(r => num(r.primary_article_score))) : 0;
  const redN = data.filter(r => spmPriority(r) === 'red').length;
  const grayN = data.filter(r => spmPriority(r) === 'gray').length;
  document.getElementById('exec-kpis').innerHTML = [
    kpiCard('Cases (filtered)', n, 'of ' + allData.length + ' total', null, null),
    kpiCard('Avg Overall Score', avgScore.toFixed(1), 'out of 100', avgScore, scoreColor(avgScore)),
    kpiCard('Adequacy Rate', pct(adequate, n), adequate + ' adequate', (adequate/n)*100, '#16a34a'),
  ].join('');
  document.getElementById('exec-kpis2').innerHTML = [
    `<div class="kpi-card"><div class="kpi-label">🔴 Red Priority</div><div class="kpi-value c-red">${redN}</div><div class="kpi-sub">${pct(redN,n)} — immediate action</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">⚪ Gray Priority</div><div class="kpi-value c-gray">${grayN}</div><div class="kpi-sub">${pct(grayN,n)} — no AI response provided</div></div>`,
    kpiCard('Low Desc. Quality Confidence', data.filter(r => isTrue(r.dq_evaluation_reliability_warning)).length, 'reliability warnings', null, null),
    kpiCard('Avg Processing', n ? (avg(data.map(r => num(r.processing_time_ms)))/1000).toFixed(1) + 's' : '–', 'per case', null, null),
  ].join('');

  // Charts — each uses getFiltered(dim) internally
  makeDonut('chart-verdict',
    ['Adequate','Needs Supplement','Inadequate','No Citation'],
    ['adequate','needs_supplementation','inadequate','no_citation_provided'],
    r => r.primary_article_verdict,
    ['#16a34a','#d97706','#dc2626','#7c3aed'], 'verdict');

  makeDonut('chart-priority',
    ['🔴 Red','🟡 Yellow','🟢 Green','⚪ Gray'],
    ['red','yellow','green','gray'],
    r => spmPriority(r),
    ['#dc2626','#d97706','#16a34a','#94a3b8'], 'priority');

  makeVBar('chart-scorebands',
    ['90-100 Excellent','70-89 Good','50-69 Needs Work','0-49 Critical'],
    ['90-100','70-89','50-69','0-49'],
    r => r._scoreBand,
    ['#16a34a','#65a30d','#d97706','#dc2626'], 'scoreBand');

  // Article quality KPIs
  const avgR = n ? avg(data.map(r => num(r.article_relevance_score))) : 0;
  const avgC = n ? avg(data.map(r => num(r.article_completeness_score))) : 0;
  const avgV = n ? avg(data.map(r => num(r.article_validity_score))) : 0;
  document.getElementById('article-kpis').innerHTML = [
    kpiCard('Avg Relevance', avgR.toFixed(1), '40% weight', avgR, '#3b82f6'),
    kpiCard('Avg Completeness', avgC.toFixed(1), '30% weight', avgC, '#3b82f6'),
    kpiCard('Avg Validity', avgV.toFixed(1), '30% weight', avgV, '#3b82f6'),
  ].join('');

  makeDonut('chart-rel',
    ['Excellent','Good','Partial','Poor','Irrelevant'],
    ['excellent','good','partial','poor','irrelevant'],
    r => r.article_relevance_verdict,
    ['#16a34a','#65a30d','#d97706','#f97316','#dc2626'], 'relVerdict');

  makeDonut('chart-comp',
    ['Complete','Mostly Complete','Incomplete','Severely Lacking'],
    ['complete','mostly_complete','incomplete','severely_lacking'],
    r => r.article_completeness_verdict,
    ['#16a34a','#65a30d','#d97706','#dc2626'], 'compVerdict');

  makeDonut('chart-val',
    ['Valid','Likely Valid','Uncertain','Likely Invalid','Invalid'],
    ['valid','likely_valid','uncertain','likely_invalid','invalid'],
    r => r.article_validity_verdict,
    ['#16a34a','#65a30d','#d97706','#f97316','#dc2626'], 'valVerdict');

  // Content checklist (uses all-filtered data)
  const checks = [
    { key: 'article_completeness_has_prerequisites', label: 'Has Prerequisites' },
    { key: 'article_completeness_has_step_by_step', label: 'Has Step-by-Step' },
    { key: 'article_completeness_has_examples', label: 'Has Examples' },
    { key: 'article_completeness_has_troubleshooting', label: 'Has Troubleshooting' },
    { key: 'article_completeness_has_success_criteria', label: 'Has Success Criteria' },
    { key: 'article_validity_addresses_root_cause', label: 'Addresses Root Cause' },
    { key: 'article_validity_is_current_solution', label: 'Is Current Solution' },
    { key: 'article_validity_environment_compatible', label: 'Env. Compatible' },
  ];
  document.getElementById('checklist').innerHTML = '<div class="checklist">' + checks.map(c => {
    const cnt = data.filter(r => isTrue(r[c.key])).length;
    const p = n ? Math.round(cnt/n*100) : 0;
    const color = p >= 70 ? '#16a34a' : p >= 40 ? '#d97706' : '#dc2626';
    return `<div class="checklist-item"><span>${p>=70?'✅':p>=40?'⚠️':'❌'}</span><span class="checklist-label">${c.label}</span><span class="checklist-pct" style="color:${color}">${p}%</span></div>`;
  }).join('') + '</div>';

  // Description Quality KPIs
  const avgDQ = n ? avg(data.map(r => num(r.dq_description_quality_score))) : 0;
  document.getElementById('kt-kpis').innerHTML = [
    kpiCard('Avg Description Quality Score', avgDQ.toFixed(1), 'Product Clarity 40% + Symptom Specificity 40% + Context 20%', avgDQ, scoreColor(avgDQ)),
    kpiCard('Agent Ready', pct(countVal(data,'dq_description_quality_verdict','agent_ready'), n), 'clear descriptions', null, '#16a34a'),
    kpiCard('Insufficient', pct(countVal(data,'dq_description_quality_verdict','insufficient'), n), 'under-described cases', null, '#dc2626'),
    kpiCard('Description Quality Warnings', data.filter(r => isTrue(r.dq_evaluation_reliability_warning)).length, 'DQ score < 40', null, null),
  ].join('');
  document.getElementById('kt-bars').innerHTML = [
    { label: 'Product Clarity', val: n ? avg(data.map(r=>num(r.product_clarity_score))) : 0 },
    { label: 'Symptom Specificity', val: n ? avg(data.map(r=>num(r.symptom_specificity_score))) : 0 },
    { label: 'Operational Context', val: n ? avg(data.map(r=>num(r.operational_context_score))) : 0 },
  ].map(d => scoreBandBar(d.label, d.val)).join('');

  makeDonut('chart-kt',
    ['Agent Ready','Workable','Insufficient'],
    ['agent_ready','workable','insufficient'],
    r => r.dq_description_quality_verdict,
    ['#16a34a','#d97706','#dc2626'], 'dqVerdict');

  // Citation & Response (mweaeval only)
  if (mwea) {
    const mweaData = data.filter(r => String(r.citation_grounding_score ?? '').trim() !== '');
    const avgGround = mweaData.length ? avg(mweaData.map(r => num(r.citation_grounding_score))) : 0;
    const avgRQ = mweaData.length ? avg(mweaData.map(r => num(r.rq_ai_response_quality_score))) : 0;
    const totalCit = data.reduce((a,r) => a+num(r.citations_total), 0);
    const goodCit = data.reduce((a,r) => a+num(r.citations_good), 0);
    document.getElementById('citation-kpis').innerHTML = [
      kpiCard('Avg Grounding Score', avgGround.toFixed(1), 'how well responses are backed by the article', avgGround, scoreColor(avgGround)),
      kpiCard('Avg Response Quality', avgRQ.toFixed(1), 'composite AI response score', avgRQ, scoreColor(avgRQ)),
      kpiCard('Good Citation Rate', pct(goodCit, totalCit), goodCit + ' cited · ' + (totalCit - goodCit) + ' uncited of ' + totalCit, null, null),
      kpiCard('Zero Citation Cases', data.filter(r => num(r.citations_total) === 0).length, 'no citations evaluated', null, null),
    ].join('');
    makeDonut('chart-ground',
      ['Well Grounded','Partially','Poorly','Ungrounded'],
      ['well_grounded','partially_grounded','poorly_grounded','ungrounded'],
      r => r.citation_grounding_verdict,
      ['#16a34a','#65a30d','#d97706','#dc2626'], 'groundVerdict');
    makeDonut('chart-rq',
      ['Excellent','Good','Fair','Poor'],
      ['excellent','good','fair','poor'],
      r => r.rq_ai_response_quality_verdict,
      ['#16a34a','#65a30d','#d97706','#dc2626'], 'rqVerdict');
    document.getElementById('rq-bars').innerHTML = [
      { label: 'Response Quality', val: mweaData.length ? avg(mweaData.map(r=>num(r.rq_response_quality_score))) : 0 },
      { label: 'Groundedness', val: mweaData.length ? avg(mweaData.map(r=>num(r.rq_groundedness_score))) : 0 },
      { label: 'Issue Resolution', val: mweaData.length ? avg(mweaData.map(r=>num(r.rq_issue_resolution_score))) : 0 },
    ].map(c => scoreBandBar(c.label, c.val)).join('');
  }

  // Synthesis KPIs
  const sRed = data.filter(r => spmPriority(r) === 'red').length;
  const sYel = data.filter(r => spmPriority(r) === 'yellow').length;
  const sGrn = data.filter(r => spmPriority(r) === 'green').length;
  const sGray = data.filter(r => spmPriority(r) === 'gray').length;
  document.getElementById('synth-kpis').innerHTML = [
    `<div class="kpi-card"><div class="kpi-label">🔴 Red</div><div class="kpi-value c-red">${sRed}</div><div class="kpi-sub">${pct(sRed,n)}</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">🟡 Yellow</div><div class="kpi-value c-yellow">${sYel}</div><div class="kpi-sub">${pct(sYel,n)}</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">🟢 Green</div><div class="kpi-value c-green">${sGrn}</div><div class="kpi-sub">${pct(sGrn,n)}</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">⚪ Gray</div><div class="kpi-value c-gray">${sGray}</div><div class="kpi-sub">${pct(sGray,n)} — no AI response provided</div></div>`,
  ].join('');

  // Dynamic charts
  makeDynHBar('chart-rc', r => r.synthesis_root_cause_category || 'Unknown',
    k => { const ex = getFiltered('rootCause').find(r => (r.synthesis_root_cause_category||'Unknown')===k); return priColor(spmPriority(ex)); },
    'rootCause');
  makeProdBar('chart-product', 'product');
  makeDynHBar('chart-area', r => r._areaPath || 'Unclassified', () => '#0369a1', 'areaPath');

  // Populate f-area dropdown (once)
  const fareaEl = document.getElementById('f-area');
  if (fareaEl && fareaEl.options.length <= 1) {
    const areas = [...new Set(allData.map(r => r._areaPath).filter(Boolean))].sort();
    areas.forEach(a => { const o = document.createElement('option'); o.value = a; o.textContent = a; fareaEl.appendChild(o); });
  }

  // Case table
  filterTable();
}

// ══════════════════════════════════════════════════════════
// CASE TABLE
// ══════════════════════════════════════════════════════════
function filterTable() {
  const q = (document.getElementById('table-search').value||'').toLowerCase();
  const fp = document.getElementById('f-priority').value;
  const fv = document.getElementById('f-verdict').value;
  const fdq = document.getElementById('f-dq').value;
  const farea = (document.getElementById('f-area') || {}).value || '';
  // Start from chart-filtered data, then apply text/dropdown filters on top
  tbl.filtered = getFilteredAll().filter(r => {
    if (fp && spmPriority(r) !== fp) return false;
    if (fv && r.primary_article_verdict !== fv) return false;
    if (fdq && r.dq_description_quality_verdict !== fdq) return false;
    if (farea && r._areaPath !== farea) return false;
    if (q) {
      const hay = [r.case_number, r._product, r.primary_article_verdict, spmPriority(r), r.synthesis_root_cause_category, r._areaPath].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  tbl.page = 0;
  document.getElementById('table-badge').textContent = tbl.filtered.length + ' / ' + state.evalData.length;
  renderTablePage();
}
function sortTable(key) {
  if (tbl.sortKey === key) tbl.sortDir = -tbl.sortDir;
  else { tbl.sortKey = key; tbl.sortDir = 1; }
  tbl.page = 0; renderTablePage();
}
function sortSpm(key) {
  if (spm.sortKey === key) spm.sortDir = -spm.sortDir;
  else { spm.sortKey = key; spm.sortDir = 1; }
  renderSPM();
}
function renderTablePage() {
  const { filtered, page, pageSize, sortKey, sortDir } = tbl;
  const mwea = isMwea(state.evalData);
  const sorted = [...filtered].sort((a, b) => {
    if (sortKey === 'synthesis_priority') return (spmPriorityOrder(a) - spmPriorityOrder(b)) * sortDir;
    const av = a[sortKey], bv = b[sortKey];
    if (typeof av === 'number') return (av - bv) * sortDir;
    return String(av||'').localeCompare(String(bv||'')) * sortDir;
  });
  const start = page * pageSize;
  const rows = sorted.slice(start, start + pageSize);
  document.getElementById('case-tbody').innerHTML = rows.map(row => {
    const idx = state.evalData.indexOf(row);
    const areaHtml = evalAreaChip(row, 20);
    return `<tr class="data-row" data-idx="${idx}">
      <td><button class="expand-btn" onclick="toggleDetail(this,${idx},'case-tbody',${mwea})" title="Show detail">▶</button></td>
      <td style="font-family:monospace;font-size:11px">${row.case_number||'–'}</td>
      <td>${trunc(row._product||'–', 22)}</td>
      <td>${areaHtml}</td>
      <td>${scoreChip(row.primary_article_score)}</td>
      <td>${verdictBadge(row.primary_article_verdict)}</td>
      <td>${priBadge(spmPriority(row))}</td>
      <td><span class="score-chip" style="background:#64748b">${num(row.dq_description_quality_score).toFixed(0)}</span></td>
    </tr>`;
  }).join('') || '<tr><td colspan="8" style="text-align:center;color:#94a3b8;padding:20px">No cases match</td></tr>';

  const totalPages = Math.ceil(filtered.length / pageSize);
  const btns = Array.from({ length: Math.min(totalPages, 10) }, (_, i) =>
    `<button class="${i === page ? 'active' : ''}" onclick="goPage(${i})">${i + 1}</button>`).join('');
  document.getElementById('table-pagination').innerHTML =
    `<span>Showing ${start+1}–${Math.min(start+pageSize, filtered.length)} of ${filtered.length}</span><div class="pagination-btns">${btns}</div>`;
}
function goPage(p) { tbl.page = p; renderTablePage(); }

// ══════════════════════════════════════════════════════════
// CLUSTER EXPAND / CASE DRILL
// ══════════════════════════════════════════════════════════
function toggleCluster(card) {
  const detail = card.querySelector('.cluster-detail');
  const chevron = card.querySelector('.cluster-chevron');
  const isOpen = detail.classList.contains('open');
  detail.classList.toggle('open', !isOpen);
  chevron.classList.toggle('open', !isOpen);
  card.classList.toggle('open', !isOpen);
}

function drillCase(caseNum, evt) {
  if (evt) evt.stopPropagation();
  if (!state.evalData) return;
  showTab('eval');
  const searchEl = document.getElementById('table-search');
  if (searchEl) { searchEl.value = caseNum; filterTable(); }
  document.getElementById('content-eval').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// RENDER TRENDS
// ══════════════════════════════════════════════════════════
function renderTrends() {
  const data = state.trendData; if (!data) return;

  // Populate area filter (once)
  const tAreaEl = document.getElementById('trend-f-area');
  if (tAreaEl && tAreaEl.options.length <= 1) {
    const areas = [...new Set(data.map(r => r._areaPath).filter(Boolean))].sort();
    areas.forEach(a => { const o = document.createElement('option'); o.value = a; o.textContent = a; tAreaEl.appendChild(o); });
  }
  const tAreaVal = (tAreaEl || {}).value || '';
  const filtered = tAreaVal ? data.filter(r => r._areaPath === tAreaVal) : data;

  const n = data.length;
  const fn = filtered.length;
  const totalCases = data.reduce((a, r) => a + num(r.case_count), 0);
  const filteredCases = filtered.reduce((a, r) => a + num(r.case_count), 0);
  const redN = countVal(data,'priority','red'), yelN = countVal(data,'priority','yellow'), grnN = countVal(data,'priority','green');
  const redCases = data.filter(r => r.priority==='red').reduce((a,r) => a+num(r.case_count), 0);

  document.getElementById('trend-badge').textContent = fn + (fn < n ? ' of ' + n : '') + ' clusters · ' + filteredCases + ' cases';
  document.getElementById('trend-kpis').innerHTML = [
    kpiCard('Total Clusters', n, 'trend pattern groups', null, null),
    kpiCard('Cases Covered', totalCases, 'across all clusters', null, null),
    `<div class="kpi-card"><div class="kpi-label">🔴 Red Clusters</div><div class="kpi-value c-red">${redN}</div><div class="kpi-sub">${redCases} cases — urgent</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">🟡 Yellow Clusters</div><div class="kpi-value c-yellow">${yelN}</div><div class="kpi-sub">${pct(yelN,n)}</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">🟢 Green Clusters</div><div class="kpi-value c-green">${grnN}</div><div class="kpi-sub">${pct(grnN,n)}</div></div>`,
  ].join('');

  const rcMap = {};
  data.forEach(r => { const k = r.root_cause_pattern||'Unknown'; rcMap[k] = (rcMap[k]||0)+num(r.case_count); });
  const rcSorted = Object.entries(rcMap).sort((a,b) => b[1]-a[1]);
  destroyChart('chart-trc');
  const trcCtx = document.getElementById('chart-trc');
  if (trcCtx) charts['chart-trc'] = new Chart(trcCtx.getContext('2d'), {
    type: 'bar',
    data: { labels: rcSorted.map(([k])=>k), datasets: [{ data: rcSorted.map(([,v])=>v), backgroundColor: '#3b82f6', borderRadius: 3, barThickness: 18 }] },
    options: { indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false}, tooltip:{callbacks:{label:c=>` ${c.raw} cases`}} }, scales:{ x:{beginAtZero:true,grid:{color:'#f1f5f9'},ticks:{font:{size:10}}}, y:{grid:{display:false},ticks:{font:{size:10},callback:v=>v.length>28?v.slice(0,27)+'…':v}} } }
  });
  destroyChart('chart-tpri');
  const tpriCtx = document.getElementById('chart-tpri');
  if (tpriCtx) {
    const priLabels = ['🔴 Red','🟡 Yellow','🟢 Green'], priColors = ['#dc2626','#d97706','#16a34a'];
    const priCounts = ['red','yellow','green'].map(p => countVal(data,'priority',p));
    const priTotal = priCounts.reduce((a,b)=>a+b,0);
    charts['chart-tpri'] = new Chart(tpriCtx.getContext('2d'), {
      type: 'doughnut',
      data: { labels: priLabels, datasets: [{ data: priCounts, backgroundColor: priColors, borderWidth:2, borderColor:'#fff', hoverOffset:3 }] },
      options: { responsive:true, maintainAspectRatio:false, cutout:'60%', plugins:{ legend:{ position:'right', labels:{ font:{size:10}, boxWidth:10, padding:5, generateLabels: () => priLabels.map((lbl,i) => ({ text:lbl, fillStyle:priColors[i], strokeStyle:'#fff', lineWidth:1, fontColor:'#374151', datasetIndex:0, index:i, hidden:false })) }}, tooltip:{ callbacks:{ label: c => ` ${c.label}: ${c.raw} (${priTotal ? ((c.raw/priTotal)*100).toFixed(1):0}%)` }} } }
    });
  }

  document.getElementById('cluster-grid').innerHTML = filtered.map((r, idx) => {
    const products = (r.products_affected||'').split(';').map(s => s.trim()).filter(Boolean);
    const evidenceParts = (r.supporting_evidence||'').split(';').map(s => s.trim()).filter(Boolean);
    const caseNums = String(r.case_numbers||'').split(';').map(s => s.trim()).filter(Boolean);
    const areaPath = r._areaPath || '';
    const hasEval = !!state.evalData;

    // Case chips — clickable if eval data loaded
    const caseChipsHtml = caseNums.length
      ? caseNums.map(c => `<span class="case-chip${hasEval?' clickable':''}" ${hasEval?`onclick="drillCase('${c}',event)" title="View in Eval tab"`:''}>${c}</span>`).join('')
      : `<em style="font-size:11px;color:#94a3b8">${r.case_count} cases (load eval CSV for case numbers)</em>`;

    // Full evidence list with URL detection
    const fullEvidenceHtml = evidenceParts.map(e => {
      const isUrl = /^https?:\/\//.test(e.trim());
      return isUrl
        ? `<div class="cluster-article-item has-url">🔗 <a href="${e}" target="_blank" class="detail-link">${trunc(e,90)}</a></div>`
        : `<div class="cluster-article-item">📌 ${e}</div>`;
    }).join('');

    // Extra products (beyond first 5) shown in detail panel
    const extraProductsHtml = products.length > 5
      ? `<div style="margin-top:10px"><div class="cluster-fl">All Products Affected</div><div class="cluster-fv" style="margin-top:4px">${products.join(' · ')}</div></div>`
      : '';

    const toggleLabel = `${caseNums.length || r.case_count} case${(caseNums.length||r.case_count)!==1?'s':''} · article details`;

    return `<div class="cluster-card ${r.priority||'gray'}" data-tidx="${idx}">
      <div class="cluster-meta">${priBadge(r.priority)}<span class="badge b-blue">${r.case_count} cases</span>${r.root_cause_pattern ? `<span class="badge b-gray">${r.root_cause_pattern}</span>` : ''}${trendAreaChip(r, 24)}</div>
      <div class="cluster-name">${r.cluster_name||'Unnamed Cluster'}</div>
      ${products.length ? `<div style="margin-bottom:6px"><div class="cluster-fl">Products</div><div class="cluster-fv">${products.slice(0,5).join(', ')}${products.length>5?` <span style="color:#94a3b8">+${products.length-5} more</span>`:''}</div></div>` : ''}
      ${r.estimated_impact ? `<div style="margin-bottom:6px"><div class="cluster-fl">Estimated Impact</div><div class="cluster-fv">${r.estimated_impact}</div></div>` : ''}
      ${r.unified_pm_action ? `<div class="cluster-action">💡 ${r.unified_pm_action}</div>` : ''}
      ${evidenceParts.slice(0,2).map(e => `<div class="cluster-evidence">📌 ${trunc(e,200)}</div>`).join('')}
      <div class="cluster-toggle" onclick="toggleCluster(this.closest('.cluster-card'))">
        <span class="cluster-toggle-label">▾ ${toggleLabel}</span>
        <span class="cluster-chevron">▼</span>
      </div>
      <div class="cluster-detail">
        <div class="cluster-fl" style="margin-bottom:5px">Cases in this cluster</div>
        <div class="cluster-case-chips">${caseChipsHtml}</div>
        ${extraProductsHtml}
        ${evidenceParts.length ? `<div style="margin-top:10px"><div class="cluster-fl" style="margin-bottom:3px">Update articles — supporting evidence</div>${fullEvidenceHtml}</div>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════
// RENDER OVERLAPS
// ══════════════════════════════════════════════════════════
function renderOverlaps() {
  const data = state.overlapData; if (!data) return;
  const typeFilter = (document.getElementById('overlap-f-type') || {}).value || '';
  const filtered = typeFilter ? data.filter(r => r.overlap_type === typeFilter) : data;

  const n = data.length;
  const crossN = data.filter(r => r.overlap_type === 'cross_coverage').length;
  const dupeN = data.filter(r => r.overlap_type === 'duplicate_issues').length;
  const maxCases = data.length ? Math.max(...data.map(r => num(r.case_count))) : 0;

  document.getElementById('overlap-badge').textContent = filtered.length + (filtered.length < n ? ' of ' + n : '') + ' overlaps';
  document.getElementById('overlap-kpis').innerHTML = [
    `<div class="kpi-card"><div class="kpi-label">🔗 Total Overlapping URLs</div><div class="kpi-value c-blue">${n}</div><div class="kpi-sub">articles cited by multiple cases</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">⚡ Cross-Coverage</div><div class="kpi-value" style="color:#ea580c">${crossN}</div><div class="kpi-sub">different problems, shared article — hidden impact risk</div></div>`,
    `<div class="kpi-card"><div class="kpi-label">🔁 Potential Duplicates</div><div class="kpi-value c-yellow">${dupeN}</div><div class="kpi-sub">same problem cited repeatedly — consolidation candidates</div></div>`,
  ].join('');

  document.getElementById('overlap-grid').innerHTML = filtered.map(r => {
    const isCross = r.overlap_type === 'cross_coverage';
    const borderColor = isCross ? '#ea580c' : '#d97706';
    const typeBadge = isCross
      ? `<span class="badge" style="background:#fff7ed;color:#c2410c">⚡ Cross-Coverage</span>`
      : `<span class="badge b-yellow">🔁 Potential Duplicate</span>`;
    const simPct = Math.round(num(r.similarity_score) * 100);
    const simColor = simPct >= 35 ? '#d97706' : '#3b82f6';
    const urlShort = trunc(r.url || '', 60);
    const snippets = (r._snippets || []).slice(0, 4);
    const cases = (r._cases || []);
    return `<div class="cluster-card" style="border-left-color:${borderColor}">
      <div class="cluster-meta">${typeBadge}<span class="badge b-blue">${r.case_count} cases</span></div>
      ${r.url ? `<div style="margin:6px 0 8px"><a href="${r.url}" target="_blank" class="detail-link" title="${r.url}">${urlShort}</a></div>` : ''}
      ${cases.length ? `<div style="margin-bottom:8px"><div class="cluster-fl">Cases</div><div class="cluster-fv" style="font-family:monospace;font-size:11px">${cases.join(' · ')}</div></div>` : ''}
      <div style="margin-bottom:8px">
        <div class="cluster-fl">Description Similarity</div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:3px">
          <div class="score-bar-track" style="flex:1"><div class="score-bar-fill" style="width:${simPct}%;background:${simColor}"></div></div>
          <span style="font-size:11px;font-weight:700;color:${simColor}">${num(r.similarity_score).toFixed(2)}</span>
        </div>
      </div>
      ${r.flag_reason ? `<div class="cluster-evidence">⚠️ ${trunc(r.flag_reason, 200)}</div>` : ''}
      ${r.recommendation ? `<div class="cluster-action">💡 ${r.recommendation}</div>` : ''}
      ${snippets.length ? `<div style="margin-top:8px"><div class="cluster-fl">Issue Snippets</div>${snippets.map((s,i) => `<div style="font-size:11px;color:#374151;background:#f8fafc;border-radius:4px;padding:5px 8px;margin-top:4px"><span style="font-weight:700;color:#64748b">Case ${cases[i]||i+1}:</span> ${trunc(s,150)}</div>`).join('')}</div>` : ''}
    </div>`;
  }).join('') || '<div style="text-align:center;color:#94a3b8;padding:40px">No overlaps match the current filter.</div>';
}

// Init
document.getElementById('empty-state').style.display = 'block';
