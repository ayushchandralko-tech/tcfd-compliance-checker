// TCFD Compliance Calculator - criterion-level review

const API_BASE = 'http://localhost:8250';
const PILLARS = ['Governance', 'Strategy', 'Risk Management', 'Metrics & Targets'];

// The 11 TCFD recommended disclosures (TCFD Final Report, 2017). Criteria come from the
// backend after analysis; `asks` is shown for manual assessments.
const disclosures = [
    { id: 'G.1', ref: 'Governance (a)', pillar: 'Governance', title: 'Board oversight',
      description: "Describe the board's oversight of climate-related risks and opportunities.",
      asks: ['Board body that oversees climate issues and how often it is informed',
             'Board considers climate issues in strategy, budgets, risk appetite and major plans',
             'Board monitors progress against climate goals and targets'] },
    { id: 'G.2', ref: 'Governance (b)', pillar: 'Governance', title: "Management's role",
      description: "Describe management's role in assessing and managing climate-related risks and opportunities.",
      asks: ['Climate responsibilities assigned to management roles or committees',
             'Organisational structure and reporting lines for climate issues',
             'How management is informed about and monitors climate issues'] },
    { id: 'S.1', ref: 'Strategy (a)', pillar: 'Strategy', title: 'Climate risks and opportunities',
      description: 'Describe the climate-related risks and opportunities identified over the short, medium and long term.',
      asks: ['Short-, medium- and long-term horizons defined', 'Specific climate-related risks identified',
             'Climate-related opportunities identified', 'Process for determining material risks and opportunities'] },
    { id: 'S.2', ref: 'Strategy (b)', pillar: 'Strategy', title: 'Business and financial impact',
      description: "Describe the impact of climate-related risks and opportunities on the organisation's businesses, strategy and financial planning.",
      asks: ['Impact on businesses, products, operations or portfolio', 'Climate issues as an input to financial planning',
             'Impact on financial performance and position'] },
    { id: 'S.3', ref: 'Strategy (c)', pillar: 'Strategy', title: 'Strategy resilience',
      description: 'Describe the resilience of the strategy under different climate-related scenarios, including a 2°C or lower scenario.',
      asks: ['Climate scenarios used, named', 'A 2°C-or-lower scenario with temperature assumptions',
             'Results: how the strategy holds up under the scenarios'] },
    { id: 'R.1', ref: 'Risk Management (a)', pillar: 'Risk Management', title: 'Risk identification and assessment',
      description: "Describe the organisation's processes for identifying and assessing climate-related risks.",
      asks: ['Process for identifying and assessing climate risks', 'How the significance of climate risks is determined',
             'Existing and emerging regulation considered'] },
    { id: 'R.2', ref: 'Risk Management (b)', pillar: 'Risk Management', title: 'Risk management processes',
      description: "Describe the organisation's processes for managing climate-related risks.",
      asks: ['Decisions to mitigate, transfer, accept or control climate risks',
             'How climate risks are prioritised (appetite, limits, thresholds)', 'How climate risks are monitored and controlled'] },
    { id: 'R.3', ref: 'Risk Management (c)', pillar: 'Risk Management', title: 'Integration into overall risk management',
      description: 'Describe how climate risk processes are integrated into overall risk management.',
      asks: ['Climate risk processes integrated into overall risk management'] },
    { id: 'M.1', ref: 'Metrics and Targets (a)', pillar: 'Metrics & Targets', title: 'Climate-related metrics',
      description: 'Disclose the metrics used to assess climate-related risks and opportunities in line with strategy and risk management.',
      asks: ['Climate metrics reported with actual values', 'Climate metrics linked to remuneration',
             'Internal carbon price or climate-opportunity metrics'] },
    { id: 'M.2', ref: 'Metrics and Targets (b)', pillar: 'Metrics & Targets', title: 'Scope 1, 2 and 3 emissions',
      description: 'Disclose Scope 1, Scope 2 and, if appropriate, Scope 3 greenhouse gas emissions and the related risks.',
      asks: ['Scope 1 and Scope 2 emissions with values', 'Scope 3 emissions (incl. financed emissions)',
             'Emissions methodology', 'Historical emissions for trend analysis'] },
    { id: 'M.3', ref: 'Metrics and Targets (c)', pillar: 'Metrics & Targets', title: 'Climate targets and performance',
      description: 'Describe the targets used to manage climate-related risks and opportunities and performance against them.',
      asks: ['Quantified climate targets', 'Target time frame (deadline)', 'Base year for targets',
             'Performance and progress against targets'] },
].map(d => ({ ...d, status: null, notes: '', open: false, analysis: null,
              review: { decision: null, reason: '', at: null } }));

const STATUS = {
    compliant: { label: 'Compliant', short: 'Compliant', points: 1 },
    partial: { label: 'Partially compliant', short: 'Partial', points: 0.5 },
    noncompliant: { label: 'Non-compliant', short: 'Non-compliant', points: 0 },
    na: { label: 'Not assessable', short: 'N/A', points: null },
};
const STATUS_FROM_API = {
    'Disclosed': 'compliant',
    'Partially disclosed': 'partial',
    'Not disclosed': 'noncompliant',
    'Not assessable': 'na',
};
const RESULT = {
    'Supported': { icon: '✓', cls: 'ok' },
    'Partly supported': { icon: '◐', cls: 'warn' },
    'Not found': { icon: '✕', cls: 'bad' },
    'Not assessable': { icon: '–', cls: 'none' },
};

let source = null;      // { file, pages, pagesTotal, method, details, analysedAt, summary, url }
let detected = null;    // { company, reporting_year, ... }
const audit = [];       // review audit trail

// --------------------------------------------------------------------------- dialog
// In-page replacement for confirm()/alert(): native dialogs are blocked in some embedded
// browsers (they silently return false), which made Export and Reset do nothing.

function showDialog({ title, message = '', items = [], confirmText = 'OK', cancelText = 'Cancel', danger = false }) {
    return new Promise(resolve => {
        const overlay = document.getElementById('dialog');
        document.getElementById('dialogTitle').textContent = title;
        document.getElementById('dialogMessage').textContent = message;
        const list = document.getElementById('dialogItems');
        list.innerHTML = items.map(x => `<li>${esc(x)}</li>`).join('');
        list.hidden = !items.length;
        const ok = document.getElementById('dialogOk');
        const cancel = document.getElementById('dialogCancel');
        ok.textContent = confirmText;
        ok.classList.toggle('btn-danger', danger);
        cancel.textContent = cancelText || '';
        cancel.hidden = !cancelText;
        overlay.hidden = false;
        const finish = value => {
            overlay.hidden = true;
            ok.onclick = cancel.onclick = overlay.onclick = document.onkeydown = null;
            resolve(value);
        };
        ok.onclick = () => finish(true);
        cancel.onclick = () => finish(false);
        overlay.onclick = e => { if (e.target === overlay) finish(false); };
        document.onkeydown = e => { if (e.key === 'Escape') finish(false); };
        ok.focus();
    });
}

// --------------------------------------------------------------------------- helpers

function esc(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function pct(x) {
    return x == null ? '–' : `${Math.round(x)}%`;
}

function companyName() { return document.getElementById('companyName').value.trim(); }
function reportingYear() { return document.getElementById('reportingYear').value.trim(); }

function yearRange(label) {
    const m = String(label || '').trim().match(/^(20\d\d)(?:\s*[-–/]\s*(\d{2}|20\d\d))?$/);
    if (!m) return [];
    const start = parseInt(m[1], 10);
    return m[2] ? [start, start + 1] : [start];
}

// Does the year entered by the user match the year detected in the report?
function yearMismatch() {
    if (!detected || !detected.reporting_year || !reportingYear()) return false;
    const entered = yearRange(reportingYear());
    const found = yearRange(detected.reporting_year);
    if (!entered.length || !found.length) return false;
    return !entered.some(y => found.includes(y));
}

function suggestedKey(d) {
    return d.analysis ? STATUS_FROM_API[d.analysis.status] : null;
}

function reviewState(d) {
    if (!d.analysis) return d.status ? 'manual' : 'unassessed';
    return d.review.decision || 'pending';
}

function log(action, d, extra = {}) {
    audit.push({ at: new Date().toISOString(), disclosure: d ? d.id : null, action, ...extra });
}

// --------------------------------------------------------------------------- scores

function scores() {
    const counts = { compliant: 0, partial: 0, noncompliant: 0, na: 0, unassessed: 0 };
    let points = 0, assessable = 0;
    disclosures.forEach(d => {
        if (!d.status) { counts.unassessed++; return; }
        counts[d.status]++;
        if (STATUS[d.status].points != null) {
            points += STATUS[d.status].points;
            assessable++;
        }
    });
    const compliance = assessable ? points / assessable * 100 : null;

    // Evidence coverage: share of criteria with supporting evidence (partly = half), from the analysis.
    let cov = null, crit = { supported: 0, partly: 0, missing: 0, total: 0 };
    const analysed = disclosures.filter(d => d.analysis && d.analysis.status !== 'Not assessable');
    if (analysed.length) {
        analysed.forEach(d => d.analysis.criteria.forEach(c => {
            crit.total++;
            if (c.result === 'Supported') crit.supported++;
            else if (c.result === 'Partly supported') crit.partly++;
            else crit.missing++;
        }));
        cov = crit.total ? (crit.supported + 0.5 * crit.partly) / crit.total * 100 : null;
    }
    const review = { pending: 0, accepted: 0, changed: 0 };
    disclosures.forEach(d => { const r = reviewState(d); if (r in review) review[r]++; });
    return { counts, points, assessable, compliance, coverage: cov, crit, review };
}

function pillarStats(pillar) {
    const items = disclosures.filter(d => d.pillar === pillar);
    const assessed = items.filter(d => d.status && STATUS[d.status].points != null);
    const pts = assessed.reduce((s, d) => s + STATUS[d.status].points, 0);
    const crits = items.filter(d => d.analysis).flatMap(d => d.analysis.criteria);
    const cov = crits.length
        ? (crits.filter(c => c.result === 'Supported').length + 0.5 * crits.filter(c => c.result === 'Partly supported').length) / crits.length * 100
        : null;
    return { items, assessed, pts, compliance: assessed.length ? pts / assessed.length * 100 : null, coverage: cov };
}

// --------------------------------------------------------------------------- rendering

function render() {
    document.getElementById('disclosuresList').innerHTML = PILLARS.map(pillar => {
        const st = pillarStats(pillar);
        return `
            <section>
                <div class="pillar-head">
                    <h3>${esc(pillar)}</h3>
                    <span>${st.pts} / ${st.assessed.length || st.items.length} points</span>
                </div>
                ${st.items.map(renderCard).join('')}
            </section>`;
    }).join('');
    updateSidebar();
}

function renderCard(d) {
    const i = disclosures.indexOf(d);
    const sug = suggestedKey(d);
    const seg = Object.entries(STATUS).map(([key, s]) =>
        `<button class="${d.status === key ? 'on-' + key : ''}" onclick="setStatus(${i}, '${key}')"
                 aria-pressed="${d.status === key}" title="${s.label}">${s.short}</button>`).join('');

    let summary;
    if (d.analysis) {
        const a = d.analysis;
        const cv = a.coverage;
        const rs = reviewState(d);
        const reviewChip = {
            pending: '<span class="chip-review pending">Awaiting review</span>',
            accepted: '<span class="chip-review accepted">Accepted by reviewer</span>',
            changed: `<span class="chip-review changed">Changed by reviewer${d.review.reason ? '' : ' · reason needed'}</span>`,
        }[rs];
        summary = `
            <div class="suggest">
                <span>AI suggestion <span class="badge ${sug}">${STATUS[sug].label}</span></span>
                ${a.status !== 'Not assessable' ? `
                <span class="meter" title="Criteria with supporting evidence (partly supported = half)">Criteria
                    <span class="meter-bar"><div style="width:${(cv.score || 0) * 100}%"></div></span>
                    ${cv.supported}/${cv.total} supported${cv.partly ? `, ${cv.partly} partly` : ''}</span>
                <span class="conf conf-${a.confidence.level.toLowerCase()}" title="${esc(a.confidence.reason)}">${a.confidence.level} confidence</span>` : ''}
                ${reviewChip}
                <button class="btn-link toggle" onclick="toggle(${i})">${d.open ? 'Hide details ▲' : 'Review evidence ▼'}</button>
            </div>
            <div class="why">${esc(a.reason)}</div>`;
    } else {
        summary = `
            <div class="suggest">
                <span>${d.status ? 'Manual assessment' : 'Not assessed'}</span>
                <button class="btn-link toggle" onclick="toggle(${i})">${d.open ? 'Hide details ▲' : 'Details ▼'}</button>
            </div>`;
    }

    return `
        <article class="card ${d.open ? 'open' : ''} ${reviewState(d) === 'pending' ? 'needs-review' : ''}" id="card-${d.id}">
            <div class="card-top">
                <div>
                    <div class="card-id">${d.id} · ${esc(d.ref)}</div>
                    <div class="card-title">${esc(d.title)}</div>
                    <div class="card-desc">${esc(d.description)}</div>
                </div>
                <div class="seg" role="group" aria-label="Final status for ${d.id}">${seg}</div>
            </div>
            ${summary}
            <div class="evidence">${d.open ? renderDetails(d, i) : ''}</div>
        </article>`;
}

function renderCriterion(c) {
    const r = RESULT[c.result] || RESULT['Not found'];
    const e = c.evidence;
    const openLink = e && source && source.url
        ? ` · <a href="${source.url}#page=${e.page}" target="_blank" rel="noopener">Open page ${e.page} ↗</a>` : '';
    return `
        <div class="crit crit-${r.cls}">
            <div class="crit-head">
                <span class="crit-icon ${r.cls}" aria-hidden="true">${r.icon}</span>
                <div class="crit-main">
                    <div class="crit-title">${esc(c.text)} ${c.essential ? '' : '<span class="tag">optional</span>'}</div>
                    <div class="crit-result"><b>${esc(c.result)}</b> · ${esc(c.reason)}</div>
                </div>
            </div>
            ${e ? `
            <div class="quote">
                <div class="quote-head">Page ${e.page} · relevance ${e.relevance.toFixed(2)}${openLink}
                    <span class="signals">${e.signals_found.map(s => `<span class="chip">${esc(s)}</span>`).join('')}</span></div>
                <div class="quote-body">${e.context_before ? `<span class="ctx">${esc(e.context_before)} </span>` : ''}${esc(e.text)}${e.context_after ? `<span class="ctx"> ${esc(e.context_after)}</span>` : ''}</div>
            </div>` : ''}
            ${c.missing_guidance ? `<div class="missing"><b>What is missing:</b> ${esc(c.missing_guidance)}</div>` : ''}
        </div>`;
}

function renderDetails(d, i) {
    let body;
    if (d.analysis) {
        body = `
            <div class="ev-section">
                <div class="ev-label">Criterion-level assessment (${d.analysis.criteria.length})</div>
                ${d.analysis.criteria.map(renderCriterion).join('')}
            </div>`;
    } else {
        body = `
            <div class="ev-section">
                <div class="ev-label">What TCFD asks</div>
                <ul class="asks">${d.asks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
            </div>`;
    }

    let review = '';
    if (d.analysis) {
        const sug = suggestedKey(d);
        const rs = reviewState(d);
        review = `
            <div class="ev-section review-box">
                <div class="ev-label">Reviewer decision</div>
                ${rs === 'pending' ? `
                    <p>Check the evidence above, then accept the AI suggestion or choose a different status at the top of this card.</p>
                    <button class="btn btn-primary" onclick="accept(${i})">Accept suggestion: ${STATUS[sug].label}</button>` : ''}
                ${rs === 'accepted' ? `<p>Accepted the AI suggestion (${STATUS[sug].label}). <button class="btn-link" onclick="undoReview(${i})">Undo</button></p>` : ''}
                ${rs === 'changed' ? `
                    <p>Changed from <b>${STATUS[sug].label}</b> to <b>${STATUS[d.status].label}</b>. A reason is required and appears in the report.</p>
                    <textarea class="input ${d.review.reason ? '' : 'required'}" placeholder="Reason for changing the AI suggestion (required)"
                              onchange="setReason(${i}, this.value)">${esc(d.review.reason)}</textarea>` : ''}
            </div>`;
    }

    const notes = `
        <div class="ev-section">
            <div class="ev-label">Reviewer notes</div>
            <textarea class="input notes" placeholder="Optional notes, included in the exported report."
                      oninput="setNotes(${i}, this.value)">${esc(d.notes)}</textarea>
        </div>`;
    return body + review + notes;
}

function updateSidebar() {
    const s = scores();
    document.getElementById('overallScore').textContent = s.compliance == null ? '–' : `${Math.round(s.compliance)}%`;
    document.getElementById('scoreRing').style.strokeDashoffset = 263.9 * (1 - (s.compliance || 0) / 100);
    document.getElementById('coverageScore').textContent = s.coverage == null ? '–' : `${Math.round(s.coverage)}%`;
    document.getElementById('coverageDetail').textContent = s.crit.total
        ? `${s.crit.supported} supported, ${s.crit.partly} partly, ${s.crit.missing} missing of ${s.crit.total} criteria`
        : 'Run an analysis to measure evidence coverage';
    document.getElementById('compliantCount').textContent = s.counts.compliant;
    document.getElementById('partialCount').textContent = s.counts.partial;
    document.getElementById('nonCompliantCount').textContent = s.counts.noncompliant;
    document.getElementById('naCount').textContent = s.counts.na;
    document.getElementById('unassessedCount').textContent = s.counts.unassessed;

    const rv = document.getElementById('reviewPanel');
    rv.hidden = !source;
    document.getElementById('pendingCount').textContent = s.review.pending;
    document.getElementById('acceptedCount').textContent = s.review.accepted;
    document.getElementById('changedCount').textContent = s.review.changed;

    document.getElementById('pillarBars').innerHTML = PILLARS.map(p => {
        const st = pillarStats(p);
        return `<div>
            <div class="pbar-label"><span>${esc(p)}</span><span>${pct(st.compliance)}${st.coverage != null ? ` · evidence ${pct(st.coverage)}` : ''}</span></div>
            <div class="pbar"><div style="width:${st.compliance || 0}%"></div></div></div>`;
    }).join('');
    updateMetaWarning();
}

function updateMetaWarning() {
    const box = document.getElementById('metaCheck');
    if (!detected) { box.hidden = true; return; }
    box.hidden = false;
    const mismatch = yearMismatch();
    const confirmBox = document.getElementById('yearConfirm');
    if (!mismatch) confirmBox.checked = false;
    box.className = 'meta-check' + (mismatch ? ' warn' : '');
    document.getElementById('metaText').innerHTML =
        `Detected in report: <b>${esc(detected.company || 'company not found')}</b> · ` +
        `reporting year <b>${esc(detected.reporting_year || 'not found')}</b>` +
        (mismatch ? `<br>The year entered (${esc(reportingYear())}) does not match the report.` : '');
    document.getElementById('yearConfirmRow').hidden = !mismatch;
}

// --------------------------------------------------------------------------- interactions

function setStatus(i, key) {
    const d = disclosures[i];
    const before = d.status;
    d.status = d.status === key && !d.analysis ? null : key;
    if (d.analysis) {
        const sug = suggestedKey(d);
        if (d.status === sug) {
            d.review = { decision: 'accepted', reason: '', at: new Date().toISOString() };
            log('accepted', d, { status: STATUS[sug].label });
        } else {
            d.review = { decision: 'changed', reason: d.review.decision === 'changed' ? d.review.reason : '',
                         at: new Date().toISOString() };
            d.open = true;  // show the reason box
            log('changed', d, { from: STATUS[sug].label, to: STATUS[d.status].label });
        }
    } else if (before !== d.status) {
        log('manual status', d, { status: d.status ? STATUS[d.status].label : 'cleared' });
    }
    render();
}

function accept(i) {
    const d = disclosures[i];
    d.status = suggestedKey(d);
    d.review = { decision: 'accepted', reason: '', at: new Date().toISOString() };
    log('accepted', d, { status: STATUS[d.status].label });
    render();
}

function undoReview(i) {
    const d = disclosures[i];
    d.review = { decision: null, reason: '', at: null };
    d.status = suggestedKey(d);
    log('review undone', d);
    render();
}

function setReason(i, value) {
    const d = disclosures[i];
    d.review.reason = value.trim();
    log('change reason', d, { reason: d.review.reason });
    render();
}

function setNotes(i, value) {
    disclosures[i].notes = value;
}

function toggle(i) {
    disclosures[i].open = !disclosures[i].open;
    render();
}

function setUploadStatus(message, isError = false) {
    const el = document.getElementById('uploadStatus');
    el.textContent = message;
    el.className = 'status-msg' + (isError ? ' error' : '');
}

function setupInputs() {
    const input = document.getElementById('reportFile');
    const zone = document.getElementById('dropZone');
    const showName = () => {
        document.getElementById('fileName').textContent = input.files[0] ? input.files[0].name : 'Choose a PDF';
    };
    input.addEventListener('change', showName);
    ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove('drag'); }));
    zone.addEventListener('drop', e => {
        if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; showName(); }
    });
    document.getElementById('reportingYear').addEventListener('input', updateMetaWarning);
    document.getElementById('yearConfirm').addEventListener('change', e => {
        log(e.target.checked ? 'year mismatch confirmed' : 'year mismatch unconfirmed', null,
            { entered: reportingYear(), detected: detected && detected.reporting_year });
    });
}

async function analyzeReport() {
    const file = document.getElementById('reportFile').files[0];
    if (!file) { setUploadStatus('Choose a PDF first.', true); return; }
    const reviewed = disclosures.filter(d => d.review.decision).length;
    if (reviewed && !(await showDialog({ title: 'Re-analyse the report?',
        message: `This replaces the AI suggestions and clears ${reviewed} review decision(s).`,
        confirmText: 'Re-analyse', danger: true }))) return;

    const button = document.getElementById('analyzeBtn');
    const label = document.getElementById('analyzeLabel');
    button.disabled = true;
    button.classList.add('busy');
    const started = Date.now();
    const tick = setInterval(() => { label.textContent = `Analysing… ${Math.round((Date.now() - started) / 1000)}s`; }, 500);
    label.textContent = 'Analysing…';
    setUploadStatus(`Reading ${file.name}. Large reports can take a minute or two.`);

    try {
        const form = new FormData();
        form.append('file', file);
        const response = await fetch(`${API_BASE}/tcfd/assess`, { method: 'POST', body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `Server returned ${response.status}`);

        disclosures.forEach(d => {
            const r = data.compliance_checklist[d.id];
            if (!r) return;
            d.analysis = { status: r.status, reason: r.reason, coverage: r.coverage, confidence: r.confidence, criteria: r.criteria };
            d.status = STATUS_FROM_API[r.status];
            d.review = { decision: null, reason: '', at: null };
        });
        if (source && source.url) URL.revokeObjectURL(source.url);
        source = { file: file.name, pages: data.summary.pages_with_text, pagesTotal: data.summary.pages_total,
                   method: data.method, details: data.method_details, analysedAt: new Date(), summary: data.summary,
                   url: URL.createObjectURL(file) };
        detected = data.metadata || null;

        // Fill empty fields from the report; never overwrite what the user typed.
        if (detected) {
            if (!companyName() && detected.company) document.getElementById('companyName').value = detected.company;
            if (!reportingYear() && detected.reporting_year) document.getElementById('reportingYear').value = detected.reporting_year;
        }
        log('analysed', null, { file: file.name, suggestion_counts: {
            compliant: data.summary.disclosed, partial: data.summary.partially_disclosed,
            noncompliant: data.summary.not_disclosed, na: data.summary.not_assessable } });

        const tag = document.getElementById('sourceTag');
        tag.textContent = `Analysed: ${file.name} · ${source.pages} of ${source.pagesTotal} pages with text`;
        tag.hidden = false;
        const s = data.summary;
        setUploadStatus(s.not_assessable === 11
            ? `Not assessable: ${s.not_assessable_reason}`
            : `Done in ${Math.round((Date.now() - started) / 1000)}s. ${s.criteria_supported} of ${s.criteria_total} criteria have supporting evidence. ` +
              'Review each disclosure: accept the suggestion or change it with a reason.',
            s.not_assessable === 11);
        render();
    } catch (err) {
        setUploadStatus(err instanceof TypeError
            ? 'Could not reach the backend on localhost:8250. Start it with "python tcfd_api_server.py" in backend/.'
            : `Analysis failed: ${err.message}`, true);
    } finally {
        clearInterval(tick);
        label.textContent = 'Analyse report';
        button.classList.remove('busy');
        button.disabled = false;
    }
}

async function resetAssessment() {
    if (!(await showDialog({ title: 'Reset the assessment?',
        message: 'This clears all statuses, review decisions, notes and analysis results.',
        confirmText: 'Reset', danger: true }))) return;
    disclosures.forEach(d => Object.assign(d, { status: null, notes: '', open: false, analysis: null,
                                                review: { decision: null, reason: '', at: null } }));
    if (source && source.url) URL.revokeObjectURL(source.url);
    source = null;
    detected = null;
    audit.length = 0;
    document.getElementById('sourceTag').hidden = true;
    document.getElementById('reportFile').value = '';
    document.getElementById('fileName').textContent = 'Choose a PDF';
    document.getElementById('companyName').value = '';
    document.getElementById('reportingYear').value = '';
    document.getElementById('yearConfirm').checked = false;
    setUploadStatus('Optional. Suggests a status per disclosure from criterion-level evidence. Needs the backend on localhost:8250.');
    render();
}

// --------------------------------------------------------------------------- export

function fileStem() {
    const name = (companyName() || 'Company').replace(/[^\w-]+/g, '_');
    return `TCFD_Assessment_${name}_${(reportingYear() || 'year').replace(/[^\w-]+/g, '_')}`;
}

function download(content, filename, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Keep the URL alive for the "open" link; release it after 10 minutes.
    setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000);
    saveCopyOnServer(filename, content, url);
}

// Also save the export through the backend (InferESG/exports/), so the file reaches disk
// even where the browser blocks downloads (some embedded preview panes discard them silently).
async function saveCopyOnServer(filename, content, url) {
    const box = document.getElementById('exportNotice');
    let saved = null;
    try {
        const res = await fetch(`${API_BASE}/tcfd/exports`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, content }),
        });
        if (res.ok) saved = await res.json();
    } catch (e) { /* backend not running: browser download only */ }
    box.innerHTML = `<b>Exported:</b> ${esc(filename)}<br>` + (saved
        ? `Saved to <code>InferESG/${esc(saved.relative_path)}</code> and sent to your browser's downloads.`
        : `Sent to your browser's downloads. Not there? <a href="${url}" target="_blank" rel="noopener">Open it in a new tab</a>.`);
    box.hidden = false;
}

// Checks before export. Resolves false if export should not go ahead.
async function readyToExport() {
    if (yearMismatch() && !document.getElementById('yearConfirm').checked) {
        await showDialog({ title: 'Reporting year does not match the report',
            message: `You entered ${reportingYear()}, but the report appears to cover ${detected.reporting_year}. ` +
                     'Correct the year, or tick the confirmation box in the sidebar, then export again.',
            confirmText: 'OK', cancelText: null });
        document.getElementById('metaCheck').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return false;
    }
    const s = scores();
    const noReason = disclosures.filter(d => d.review.decision === 'changed' && !d.review.reason);
    const problems = [];
    if (s.review.pending) problems.push(`${s.review.pending} AI suggestion(s) have not been reviewed (they will be marked "Not reviewed")`);
    if (noReason.length) problems.push(`${noReason.length} change(s) have no reason: ${noReason.map(d => d.id).join(', ')}`);
    if (problems.length && !(await showDialog({ title: 'Export with open review items?', items: problems,
        message: 'The report will show these clearly. You can also go back and finish the review first.',
        confirmText: 'Export anyway', cancelText: 'Go back' }))) return false;
    return true;
}

function exportData() {
    const s = scores();
    return {
        framework: 'TCFD',
        company: companyName() || null,
        reporting_year: reportingYear() || null,
        detected_metadata: detected,
        year_mismatch: yearMismatch(),
        year_mismatch_confirmed: yearMismatch() ? document.getElementById('yearConfirm').checked : null,
        generated_at: new Date().toISOString(),
        source_report: source ? { file: source.file, pages_with_text: source.pages, pages_total: source.pagesTotal,
                                  method: source.method, method_details: source.details } : null,
        compliance_score: s.compliance == null ? null : Math.round(s.compliance * 100) / 100,
        evidence_coverage_score: s.coverage == null ? null : Math.round(s.coverage * 100) / 100,
        counts: s.counts,
        review_counts: s.review,
        disclosures: disclosures.map(d => ({
            id: d.id, tcfd_ref: d.ref, pillar: d.pillar, title: d.title,
            final_status: d.status ? STATUS[d.status].label : null,
            ai_suggestion: d.analysis ? STATUS[suggestedKey(d)].label : null,
            ai_reason: d.analysis ? d.analysis.reason : null,
            review: d.analysis ? { decision: d.review.decision || 'not reviewed', reason: d.review.reason || null, at: d.review.at } : null,
            coverage: d.analysis ? d.analysis.coverage : null,
            confidence: d.analysis ? d.analysis.confidence : null,
            criteria: d.analysis ? d.analysis.criteria.map(c => ({
                id: c.id, criterion: c.text, essential: c.essential, result: c.result, reason: c.reason,
                evidence: c.evidence ? { page: c.evidence.page, relevance: c.evidence.relevance,
                                         signals: c.evidence.signals_found, text: c.evidence.text } : null,
                missing: c.missing_guidance })) : null,
            notes: d.notes || '',
        })),
        audit_trail: audit,
    };
}

async function exportJson() {
    if (!(await readyToExport())) return;
    download(JSON.stringify(exportData(), null, 2), `${fileStem()}.json`, 'application/json');
}

async function exportReport() {
    if (!(await readyToExport())) return;
    const s = scores();
    const company = companyName() || 'Not specified';
    const year = reportingYear() || 'Not specified';
    const generated = new Date().toLocaleString();
    const mismatch = yearMismatch();

    const badge = key => key ? `<span class="badge ${key}">${STATUS[key].label}</span>` : '<span class="badge none">Not assessed</span>';
    const reviewText = d => {
        if (!d.analysis) return d.status ? 'Manual assessment' : '–';
        if (d.review.decision === 'accepted') return 'Accepted';
        if (d.review.decision === 'changed') return 'Changed';
        return '<span class="flag">Not reviewed</span>';
    };

    const pillarRows = PILLARS.map(p => {
        const st = pillarStats(p);
        const missing = st.items.filter(d => d.analysis).flatMap(d => d.analysis.criteria).filter(c => c.result === 'Not found').length;
        return `<tr><td>${esc(p)}</td><td>${st.items.length}</td><td>${st.pts} / ${st.assessed.length}</td>
            <td>${bar(st.compliance)}</td><td>${bar(st.coverage)}</td><td>${source ? missing : '–'}</td></tr>`;
    }).join('');

    const overviewRows = disclosures.map(d => {
        const sug = suggestedKey(d);
        return `<tr>
            <td><a href="#${d.id}">${d.id}</a></td>
            <td>${esc(d.title)}</td>
            <td>${sug ? badge(sug) : '–'}</td>
            <td>${badge(d.status)}</td>
            <td>${reviewText(d)}</td>
            <td>${d.analysis && d.analysis.status !== 'Not assessable' ? `${d.analysis.coverage.supported}/${d.analysis.coverage.total}` : '–'}</td>
            <td>${d.analysis ? esc(d.analysis.confidence.level) : '–'}</td>
        </tr>`;
    }).join('');

    const details = disclosures.map(d => {
        const a = d.analysis;
        const sug = suggestedKey(d);
        const crit = a ? a.criteria.map(c => {
            const r = RESULT[c.result] || RESULT['Not found'];
            const e = c.evidence;
            return `<tr>
                <td><span class="ri ${r.cls}">${r.icon}</span></td>
                <td><b>${esc(c.text)}</b>${c.essential ? '' : ' <span class="small">(optional)</span>'}<br>
                    <span class="small">${esc(c.result)} · ${esc(c.reason)}</span>
                    ${e ? `<blockquote><span class="pg">Page ${e.page} · relevance ${e.relevance.toFixed(2)} · ${e.signals_found.map(esc).join(', ')}</span>${esc(e.text)}</blockquote>` : ''}
                    ${c.missing_guidance ? `<div class="miss"><b>What is missing:</b> ${esc(c.missing_guidance)}</div>` : ''}</td>
            </tr>`;
        }).join('') : '';
        let review = '';
        if (a) {
            review = d.review.decision === 'accepted' ? `Reviewer <b>accepted</b> the AI suggestion (${STATUS[sug].label}).`
                : d.review.decision === 'changed' ? `Reviewer <b>changed</b> the status from ${STATUS[sug].label} to ${STATUS[d.status].label}. Reason: ${d.review.reason ? esc(d.review.reason) : '<span class="flag">no reason given</span>'}`
                : '<span class="flag">Not reviewed</span> - the final status is the unreviewed AI suggestion.';
        }
        return `
            <section class="disclosure" id="${d.id}">
                <div class="d-head">
                    <div><div class="d-id">${d.id} · ${esc(d.ref)}</div><h3>${esc(d.title)}</h3></div>
                    ${badge(d.status)}
                </div>
                <p class="desc">${esc(d.description)}</p>
                <table class="facts">
                    <tr><th>Final status</th><td>${d.status ? STATUS[d.status].label : 'Not assessed'}</td></tr>
                    ${a ? `<tr><th>AI suggestion</th><td>${STATUS[sug].label} - ${esc(a.reason)}</td></tr>
                    <tr><th>Review</th><td>${review}</td></tr>
                    ${a.status !== 'Not assessable' ? `<tr><th>Evidence coverage</th><td>${a.coverage.supported} supported, ${a.coverage.partly} partly, ${a.coverage.not_found} not found (of ${a.coverage.total} criteria)</td></tr>` : ''}
                    <tr><th>Classification confidence</th><td>${esc(a.confidence.level)} - ${esc(a.confidence.reason)}</td></tr>` : ''}
                    <tr><th>Reviewer notes</th><td>${d.notes ? esc(d.notes).replace(/\n/g, '<br>') : '–'}</td></tr>
                </table>
                ${a ? `<h4>Criterion-level evidence</h4><table class="crit">${crit}</table>`
                    : `<h4>What TCFD asks</h4><ul>${d.asks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`}
            </section>`;
    }).join('');

    const auditRows = audit.map(e => `<tr><td>${esc(new Date(e.at).toLocaleString())}</td><td>${esc(e.disclosure || '–')}</td>
        <td>${esc(e.action)}</td><td>${esc(Object.entries(e).filter(([k]) => !['at', 'disclosure', 'action'].includes(k))
            .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('; '))}</td></tr>`).join('');

    const yearNote = !detected ? '' : mismatch
        ? `<div class="alert">The reporting year entered (${esc(year)}) differs from the year detected in the report (${esc(detected.reporting_year)}). The assessor confirmed this before export.</div>`
        : `<p class="small">Detected in the report: ${esc(detected.company || 'company not found')}, reporting year ${esc(detected.reporting_year || 'not found')}.</p>`;

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TCFD Assessment - ${esc(company)} ${esc(year)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
           color: #1d2330; background: #fff; margin: 0; font-size: 13px; line-height: 1.55; }
    .page { max-width: 900px; margin: 0 auto; padding: 40px 32px; }
    h1 { font-size: 24px; margin: 0 0 4px; }
    h2 { font-size: 16px; margin: 32px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #1d2330; }
    h3 { font-size: 15px; margin: 2px 0 0; }
    h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #5b6474; margin: 16px 0 6px; }
    .sub { color: #5b6474; margin: 0; }
    .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 20px 0 0; }
    .tile { border: 1px solid #e3e6eb; border-radius: 8px; padding: 12px 14px; }
    .tile span { display: block; font-size: 11px; color: #8a93a3; text-transform: uppercase; letter-spacing: 0.04em; }
    .tile b { font-size: 24px; display: block; }
    .tile small { color: #5b6474; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #e3e6eb; vertical-align: top; }
    thead th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: #5b6474; border-bottom: 1px solid #c9ced6; }
    .facts th { width: 190px; color: #5b6474; font-weight: 500; }
    a { color: #3b5bdb; text-decoration: none; }
    .badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; white-space: nowrap; }
    .badge.compliant { background: #ebf8ee; color: #2f9e44; }
    .badge.partial { background: #fff4e6; color: #c25e00; }
    .badge.noncompliant { background: #fff0f0; color: #c92a2a; }
    .badge.na, .badge.none { background: #f1f3f5; color: #868e96; }
    .small { color: #8a93a3; font-size: 12px; }
    .flag { color: #c92a2a; font-weight: 600; }
    .alert { background: #fff4e6; border: 1px solid #ffd8a8; border-radius: 8px; padding: 10px 12px; margin-top: 12px; }
    .bar { display: inline-flex; align-items: center; gap: 6px; }
    .bar i { display: inline-block; width: 70px; height: 6px; background: #e3e6eb; border-radius: 3px; overflow: hidden; }
    .bar i b { display: block; height: 100%; background: #3b5bdb; }
    .disclosure { border: 1px solid #e3e6eb; border-radius: 10px; padding: 16px 18px; margin: 0 0 14px; }
    .d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .d-id { font-size: 11px; font-weight: 600; color: #3b5bdb; }
    .desc { color: #5b6474; margin: 6px 0 10px; }
    ul { margin: 0; padding-left: 18px; color: #5b6474; }
    .crit td { border-bottom: 1px solid #eef0f3; }
    .crit td:first-child { width: 26px; }
    .ri { display: inline-block; width: 20px; height: 20px; border-radius: 50%; text-align: center; line-height: 20px; font-size: 12px; font-weight: 700; }
    .ri.ok { background: #ebf8ee; color: #2f9e44; } .ri.warn { background: #fff4e6; color: #c25e00; }
    .ri.bad { background: #fff0f0; color: #c92a2a; } .ri.none { background: #f1f3f5; color: #868e96; }
    blockquote { margin: 6px 0 0; padding: 6px 10px; border-left: 3px solid #c9ced6; background: #f8f9fb; break-inside: avoid; }
    .pg { display: block; font-size: 11px; color: #5b6474; margin-bottom: 2px; }
    .miss { margin-top: 6px; padding: 6px 10px; background: #fff8f0; border-radius: 6px; font-size: 12px; }
    .method dt { font-weight: 600; margin-top: 8px; }
    .method dd { margin: 2px 0 0 0; color: #5b6474; }
    .note { margin-top: 24px; padding: 12px 14px; background: #f8f9fb; border-radius: 8px; color: #5b6474; font-size: 12px; }
    .print-hint { text-align: right; margin-bottom: 12px; }
    .print-hint button { font: inherit; padding: 6px 12px; border: 1px solid #c9ced6; border-radius: 6px; background: #fff; cursor: pointer; }
    @media print { .print-hint { display: none; } .page { padding: 0; } @page { margin: 16mm; } a { color: inherit; }
                   .disclosure { break-inside: auto; } }
</style>
</head>
<body>
<div class="page">
    <div class="print-hint"><button onclick="window.print()">Print / Save as PDF</button></div>
    <h1>TCFD Compliance Assessment</h1>
    <p class="sub">${esc(company)} · Reporting year ${esc(year)}${source ? ` · Source: ${esc(source.file)}` : ''}</p>
    ${yearNote}

    <div class="tiles">
        <div class="tile"><span>Compliance score</span><b>${pct(s.compliance)}</b><small>Final statuses: (Compliant + 0.5 × Partial) ÷ assessable disclosures</small></div>
        <div class="tile"><span>Evidence coverage</span><b>${pct(s.coverage)}</b><small>${s.crit.total ? `${s.crit.supported} supported, ${s.crit.partly} partly, ${s.crit.missing} missing of ${s.crit.total} criteria` : 'No automated analysis'}</small></div>
        <div class="tile"><span>Final statuses</span><b>${s.counts.compliant} / ${s.counts.partial} / ${s.counts.noncompliant}</b><small>Compliant / Partial / Non-compliant${s.counts.na ? ` · ${s.counts.na} not assessable` : ''}${s.counts.unassessed ? ` · ${s.counts.unassessed} not assessed` : ''}</small></div>
        <div class="tile"><span>Review</span><b>${s.review.accepted + s.review.changed} / ${source ? 11 : 0}</b><small>${source ? `${s.review.accepted} accepted, ${s.review.changed} changed, ${s.review.pending} not reviewed` : 'Manual assessment'}</small></div>
    </div>

    <h2>Dashboard by pillar</h2>
    <table>
        <thead><tr><th>Pillar</th><th>Disclosures</th><th>Points</th><th>Compliance</th><th>Evidence coverage</th><th>Missing criteria</th></tr></thead>
        <tbody>${pillarRows}</tbody>
    </table>

    <h2>Disclosure overview</h2>
    <table>
        <thead><tr><th>ID</th><th>Disclosure</th><th>AI suggestion</th><th>Final</th><th>Review</th><th>Criteria</th><th>Confidence</th></tr></thead>
        <tbody>${overviewRows}</tbody>
    </table>

    <h2>Findings and evidence by disclosure</h2>
    ${details}

    ${audit.length ? `<h2>Review audit trail</h2>
    <table><thead><tr><th>Time</th><th>Disclosure</th><th>Action</th><th>Details</th></tr></thead><tbody>${auditRows}</tbody></table>` : ''}

    <h2>Method</h2>
    <dl class="method">
        <dt>Compliance score</dt><dd>(Compliant × 1 + Partially compliant × 0.5) ÷ number of assessable disclosures × 100. Not assessable disclosures are excluded, not scored as non-compliant.</dd>
        ${source ? `<dt>Retrieval relevance</dt><dd>${esc(source.details.relevance)}; shown per evidence passage.</dd>
        <dt>Criterion supported</dt><dd>${esc(source.details.criterion_supported)}.</dd>
        <dt>Evidence coverage</dt><dd>${esc(source.details.coverage)}, independent of the final status.</dd>
        <dt>Classification confidence</dt><dd>${esc(source.details.confidence)}.</dd>
        <dt>AI suggestion rules</dt><dd>Compliant: all essential criteria supported. Partially compliant: some criteria supported or partly supported. Non-compliant: no supporting evidence. Not assessable: document unreadable or too short.</dd>` : ''}
    </dl>
    <div class="note">
        This is a model-assisted assessment, not an audit opinion. Scores depend on the correctness of each criterion result; read the evidence before relying on them.
        ${source ? `Page numbers refer to the PDF (${esc(source.file)}, ${source.pages} of ${source.pagesTotal} pages with extractable text).` : ''}
        Generated ${esc(generated)} with the TCFD Compliance Calculator.
    </div>
</div>
</body>
</html>`;

    log('exported report', null, {});
    download(html, `${fileStem()}.html`, 'text/html');
}

function bar(v) {
    return v == null ? '–' : `<span class="bar"><i><b style="width:${v}%"></b></i>${Math.round(v)}%</span>`;
}

// --------------------------------------------------------------------------- init

document.addEventListener('DOMContentLoaded', () => {
    setupInputs();
    render();
});
