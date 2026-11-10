// TCFD Compliance Calculator

const API_BASE = 'http://localhost:8250';

const PILLARS = ['Governance', 'Strategy', 'Risk Management', 'Metrics & Targets'];

// The 11 TCFD recommended disclosures (TCFD Final Report, 2017).
const disclosures = [
    { id: 'G.1', ref: 'Governance (a)', pillar: 'Governance', title: 'Board oversight',
      description: "Describe the board's oversight of climate-related risks and opportunities.",
      asks: ['How often and through which committees the board is informed about climate-related issues',
             'Whether the board considers climate issues when reviewing strategy, budgets and major plans',
             'How the board monitors progress against climate-related goals and targets'] },
    { id: 'G.2', ref: 'Governance (b)', pillar: 'Governance', title: "Management's role",
      description: "Describe management's role in assessing and managing climate-related risks and opportunities.",
      asks: ['Whether climate responsibilities are assigned to management positions or committees',
             'The associated organisational structure and reporting lines',
             'How management is informed about and monitors climate-related issues'] },
    { id: 'S.1', ref: 'Strategy (a)', pillar: 'Strategy', title: 'Climate risks and opportunities',
      description: 'Describe the climate-related risks and opportunities identified over the short, medium and long term.',
      asks: ['Relevant short-, medium- and long-term time horizons',
             'Specific climate-related issues for each horizon that could have a material financial impact',
             'How material risks and opportunities are determined'] },
    { id: 'S.2', ref: 'Strategy (b)', pillar: 'Strategy', title: 'Business and financial impact',
      description: "Describe the impact of climate-related risks and opportunities on the organisation's businesses, strategy and financial planning.",
      asks: ['Impact on products, services, supply chain, operations and R&D',
             'How climate issues feed into financial planning',
             'Impact on financial performance and financial position'] },
    { id: 'S.3', ref: 'Strategy (c)', pillar: 'Strategy', title: 'Strategy resilience',
      description: 'Describe the resilience of the strategy under different climate-related scenarios, including a 2°C or lower scenario.',
      asks: ['Climate scenarios and time horizons considered',
             'Inclusion of a 2°C or lower scenario',
             'Where strategy may be affected and how it might change'] },
    { id: 'R.1', ref: 'Risk Management (a)', pillar: 'Risk Management', title: 'Risk identification and assessment',
      description: "Describe the organisation's processes for identifying and assessing climate-related risks.",
      asks: ['Processes for identifying and assessing climate-related risks',
             'How the relative significance of climate risks is determined',
             'Whether existing and emerging regulation is considered'] },
    { id: 'R.2', ref: 'Risk Management (b)', pillar: 'Risk Management', title: 'Risk management processes',
      description: "Describe the organisation's processes for managing climate-related risks.",
      asks: ['Decisions to mitigate, transfer, accept or control climate risks',
             'How climate risks are prioritised',
             'How materiality determinations are made'] },
    { id: 'R.3', ref: 'Risk Management (c)', pillar: 'Risk Management', title: 'Integration into overall risk management',
      description: 'Describe how climate risk processes are integrated into overall risk management.',
      asks: ['How climate risk processes are integrated into enterprise risk management'] },
    { id: 'M.1', ref: 'Metrics and Targets (a)', pillar: 'Metrics & Targets', title: 'Climate-related metrics',
      description: 'Disclose the metrics used to assess climate-related risks and opportunities in line with strategy and risk management.',
      asks: ['Key metrics used to measure and manage climate risks and opportunities',
             'Whether performance metrics feed into remuneration',
             'Internal carbon prices and opportunity metrics, where relevant'] },
    { id: 'M.2', ref: 'Metrics and Targets (b)', pillar: 'Metrics & Targets', title: 'Scope 1, 2 and 3 emissions',
      description: 'Disclose Scope 1, Scope 2 and, if appropriate, Scope 3 greenhouse gas emissions and the related risks.',
      asks: ['Scope 1 and Scope 2 GHG emissions',
             'Scope 3 GHG emissions, if appropriate',
             'Methodology (e.g. GHG Protocol) and historical trend'] },
    { id: 'M.3', ref: 'Metrics and Targets (c)', pillar: 'Metrics & Targets', title: 'Climate targets and performance',
      description: 'Describe the targets used to manage climate-related risks and opportunities and performance against them.',
      asks: ['Key climate-related targets (e.g. GHG emissions, energy use)',
             'Time frames and base years',
             'KPIs used to assess progress against targets'] },
].map(d => ({ ...d, status: null, notes: '', open: false, analysis: null }));

const STATUS = {
    compliant: { label: 'Compliant', points: 1 },
    partial: { label: 'Partial', points: 0.5 },
    noncompliant: { label: 'Non-compliant', points: 0 },
};
const STATUS_FROM_API = {
    'Disclosed': 'compliant',
    'Partially disclosed': 'partial',
    'Not disclosed': 'noncompliant',
};

let source = null; // { file, pages, method, analysedAt }

// --------------------------------------------------------------------------- helpers

function esc(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Escape a passage and highlight the requirement keywords that matched.
function highlight(text, keywords) {
    let html = esc(text);
    const terms = [...(keywords || [])].sort((a, b) => b.length - a.length).map(k => escRegex(esc(k)));
    if (terms.length) {
        html = html.replace(new RegExp(`(${terms.join('|')})`, 'gi'), '<mark>$1</mark>');
    }
    return html;
}

// Same blend the backend uses to rank passages: TF-IDF similarity (scaled) and model probability.
function passageMatch(p) {
    const sim = Math.min((p.similarity || 0) / 0.25, 1);
    return p.model_score == null ? sim : 0.5 * sim + 0.5 * p.model_score;
}

function pct(x) {
    return `${Math.round((x || 0) * 100)}%`;
}

function pagesOf(d) {
    return d.analysis ? [...new Set(d.analysis.evidence.map(e => e.page))].sort((a, b) => a - b) : [];
}

function companyName() {
    return document.getElementById('companyName').value.trim();
}

function reportingYear() {
    return document.getElementById('reportingYear').value.trim();
}

// --------------------------------------------------------------------------- rendering

function render() {
    const container = document.getElementById('disclosuresList');
    container.innerHTML = PILLARS.map(pillar => {
        const items = disclosures.filter(d => d.pillar === pillar);
        const points = items.reduce((s, d) => s + (d.status ? STATUS[d.status].points : 0), 0);
        return `
            <section>
                <div class="pillar-head">
                    <h3>${esc(pillar)}</h3>
                    <span>${points} / ${items.length} points</span>
                </div>
                ${items.map(renderCard).join('')}
            </section>`;
    }).join('');
    updateScore();
}

function renderCard(d) {
    const i = disclosures.indexOf(d);
    const seg = Object.entries(STATUS).map(([key, s]) =>
        `<button class="${d.status === key ? 'on-' + key : ''}" onclick="setStatus(${i}, '${key}')"
                 aria-pressed="${d.status === key}">${s.label}</button>`).join('');

    let suggest = '';
    if (d.analysis) {
        const a = d.analysis;
        const suggested = STATUS_FROM_API[a.status];
        const overridden = d.status && d.status !== suggested;
        const pages = pagesOf(d);
        suggest = `
            <div class="suggest">
                <span>Suggested <span class="badge ${suggested}">${STATUS[suggested].label}</span></span>
                ${overridden ? '<span class="badge override">Overridden</span>' : ''}
                <span class="meter">Evidence strength
                    <span class="meter-bar"><div style="width:${pct(a.confidence)}"></div></span>${pct(a.confidence)}</span>
                ${pages.length ? `<span>Pages ${pages.join(', ')}</span>` : '<span>No evidence found</span>'}
                <button class="btn-link toggle" onclick="toggle(${i})">${d.open ? 'Hide evidence ▲' : 'Show evidence ▼'}</button>
            </div>`;
    } else {
        suggest = `
            <div class="suggest">
                <span>No automated analysis</span>
                <button class="btn-link toggle" onclick="toggle(${i})">${d.open ? 'Hide details ▲' : 'Details ▼'}</button>
            </div>`;
    }

    return `
        <article class="card ${d.open ? 'open' : ''}" id="card-${d.id}">
            <div class="card-top">
                <div>
                    <div class="card-id">${d.id} · ${esc(d.ref)}</div>
                    <div class="card-title">${esc(d.title)}</div>
                    <div class="card-desc">${esc(d.description)}</div>
                </div>
                <div class="seg" role="group" aria-label="Status for ${d.id}">${seg}</div>
            </div>
            ${suggest}
            <div class="evidence">${d.open ? renderEvidence(d, i) : ''}</div>
        </article>`;
}

function renderEvidence(d, i) {
    const a = d.analysis;
    const asks = `
        <div class="ev-section">
            <div class="ev-label">What TCFD asks</div>
            <ul class="asks">${d.asks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        </div>`;

    let analysis = '';
    if (a) {
        const keywords = a.matched_keywords || [];
        analysis = `
            <div class="ev-section">
                <div class="ev-label">Matched terms (${keywords.length})</div>
                <div class="chips">${keywords.length
                    ? keywords.map(k => `<span class="chip">${esc(k)}</span>`).join('')
                    : '<span class="chip muted">none</span>'}</div>
            </div>
            <div class="ev-section">
                <div class="ev-label">Supporting passages</div>
                ${a.evidence.length ? `<div class="passages">${a.evidence.map((p, n) => `
                    <div class="passage">
                        <div class="passage-head">
                            <span class="page-pill">Page ${p.page}</span>
                            <span class="meter">Match <span class="meter-bar"><div style="width:${pct(passageMatch(p))}"></div></span>${pct(passageMatch(p))}</span>
                            <span>#${n + 1}</span>
                        </div>
                        <div class="passage-body">${highlight(p.text, keywords)}</div>
                    </div>`).join('')}</div>` : '<p class="empty">No relevant passages were found in the report.</p>'}
            </div>`;
    }

    const notes = `
        <div class="ev-section">
            <div class="ev-label">Reviewer notes</div>
            <textarea class="input notes" placeholder="Why this status? Included in the exported report."
                      oninput="setNotes(${i}, this.value)">${esc(d.notes)}</textarea>
        </div>`;

    return asks + analysis + notes;
}

function updateScore() {
    const counts = { compliant: 0, partial: 0, noncompliant: 0 };
    let points = 0;
    disclosures.forEach(d => {
        if (d.status) {
            counts[d.status]++;
            points += STATUS[d.status].points;
        }
    });
    const score = points / disclosures.length * 100;
    const unassessed = disclosures.length - counts.compliant - counts.partial - counts.noncompliant;

    document.getElementById('overallScore').textContent = `${Math.round(score)}%`;
    document.getElementById('scoreRing').style.strokeDashoffset = 263.9 * (1 - score / 100);
    document.getElementById('compliantCount').textContent = counts.compliant;
    document.getElementById('partialCount').textContent = counts.partial;
    document.getElementById('nonCompliantCount').textContent = counts.noncompliant;
    document.getElementById('unassessedCount').textContent = unassessed;

    document.getElementById('pillarBars').innerHTML = PILLARS.map(p => {
        const items = disclosures.filter(d => d.pillar === p);
        const pts = items.reduce((s, d) => s + (d.status ? STATUS[d.status].points : 0), 0);
        return `<div><div class="pbar-label"><span>${esc(p)}</span><span>${pts}/${items.length}</span></div>
                <div class="pbar"><div style="width:${pts / items.length * 100}%"></div></div></div>`;
    }).join('');
}

// --------------------------------------------------------------------------- interactions

function setStatus(i, status) {
    disclosures[i].status = disclosures[i].status === status ? null : status;
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

function setupFileInput() {
    const input = document.getElementById('reportFile');
    const zone = document.getElementById('dropZone');
    const showName = () => {
        document.getElementById('fileName').textContent = input.files[0] ? input.files[0].name : 'Choose a PDF';
    };
    input.addEventListener('change', showName);
    ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => {
        e.preventDefault();
        zone.classList.add('drag');
    }));
    ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => {
        e.preventDefault();
        zone.classList.remove('drag');
    }));
    zone.addEventListener('drop', e => {
        if (e.dataTransfer.files.length) {
            input.files = e.dataTransfer.files;
            showName();
        }
    });
}

async function analyzeReport() {
    const file = document.getElementById('reportFile').files[0];
    if (!file) {
        setUploadStatus('Choose a PDF first.', true);
        return;
    }
    const button = document.getElementById('analyzeBtn');
    const label = document.getElementById('analyzeLabel');
    button.disabled = true;
    button.classList.add('busy');
    const started = Date.now();
    const tick = setInterval(() => {
        label.textContent = `Analysing… ${Math.round((Date.now() - started) / 1000)}s`;
    }, 500);
    label.textContent = 'Analysing…';
    setUploadStatus(`Reading ${file.name}. Large reports can take up to a minute.`);

    try {
        const form = new FormData();
        form.append('file', file);
        const response = await fetch(`${API_BASE}/tcfd/assess`, { method: 'POST', body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || `Server returned ${response.status}`);
        }

        disclosures.forEach(d => {
            const r = data.compliance_checklist[d.id];
            if (!r) return;
            d.analysis = {
                status: r.status,
                confidence: r.confidence,
                matched_keywords: r.matched_keywords || [],
                evidence: r.evidence || [],
            };
            d.status = STATUS_FROM_API[r.status] || null;
        });
        source = {
            file: file.name,
            pages: data.summary.pages_with_text,
            method: data.method,
            analysedAt: new Date(),
        };
        const tag = document.getElementById('sourceTag');
        tag.textContent = `Analysed: ${file.name} · ${source.pages} pages`;
        tag.hidden = false;

        const s = data.summary;
        setUploadStatus(`Done in ${Math.round((Date.now() - started) / 1000)}s: ${s.disclosed} compliant, ` +
            `${s.partially_disclosed} partial, ${s.not_disclosed} non-compliant suggested. Review each card's evidence.`);
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

function resetAssessment() {
    if (!confirm('Clear all statuses, notes and analysis results?')) return;
    disclosures.forEach(d => Object.assign(d, { status: null, notes: '', open: false, analysis: null }));
    source = null;
    document.getElementById('sourceTag').hidden = true;
    document.getElementById('reportFile').value = '';
    document.getElementById('fileName').textContent = 'Choose a PDF';
    document.getElementById('companyName').value = '';
    document.getElementById('reportingYear').value = new Date().getFullYear() - 1;
    setUploadStatus('Optional. Suggests a status for each disclosure with page-cited evidence. Needs the backend on localhost:8250.');
    render();
}

// --------------------------------------------------------------------------- export

function fileStem() {
    const name = (companyName() || 'Company').replace(/[^\w-]+/g, '_');
    return `TCFD_Assessment_${name}_${reportingYear() || 'year'}`;
}

function download(content, filename, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function summaryData() {
    const counts = { compliant: 0, partial: 0, noncompliant: 0 };
    let points = 0;
    disclosures.forEach(d => {
        if (d.status) {
            counts[d.status]++;
            points += STATUS[d.status].points;
        }
    });
    return { counts, points, score: points / disclosures.length * 100,
             unassessed: disclosures.length - counts.compliant - counts.partial - counts.noncompliant };
}

function exportJson() {
    const s = summaryData();
    const data = {
        framework: 'TCFD',
        company: companyName() || null,
        reporting_year: reportingYear() || null,
        generated_at: new Date().toISOString(),
        source_report: source ? { file: source.file, pages: source.pages, method: source.method } : null,
        score: Math.round(s.score * 100) / 100,
        counts: s.counts,
        disclosures: disclosures.map(d => ({
            id: d.id, tcfd_ref: d.ref, pillar: d.pillar, title: d.title,
            status: d.status ? STATUS[d.status].label : null,
            suggested_status: d.analysis ? STATUS[STATUS_FROM_API[d.analysis.status]].label : null,
            evidence_strength: d.analysis ? d.analysis.confidence : null,
            matched_keywords: d.analysis ? d.analysis.matched_keywords : [],
            evidence: d.analysis ? d.analysis.evidence.map(p => ({ page: p.page, match: Math.round(passageMatch(p) * 100) / 100, text: p.text })) : [],
            notes: d.notes || '',
        })),
    };
    download(JSON.stringify(data, null, 2), `${fileStem()}.json`, 'application/json');
}

function exportReport() {
    const s = summaryData();
    const company = companyName() || 'Not specified';
    const year = reportingYear() || 'Not specified';
    const generated = new Date().toLocaleString();
    const badge = key => key
        ? `<span class="badge ${key}">${STATUS[key].label}</span>`
        : '<span class="badge none">Not assessed</span>';

    const pillarRows = PILLARS.map(p => {
        const items = disclosures.filter(d => d.pillar === p);
        const pts = items.reduce((t, d) => t + (d.status ? STATUS[d.status].points : 0), 0);
        return `<tr><td>${esc(p)}</td><td>${items.length}</td><td>${pts}</td><td>${Math.round(pts / items.length * 100)}%</td></tr>`;
    }).join('');

    const overviewRows = disclosures.map(d => {
        const suggested = d.analysis ? STATUS_FROM_API[d.analysis.status] : null;
        return `<tr>
            <td><a href="#${d.id}">${d.id}</a></td>
            <td>${esc(d.title)}</td>
            <td>${badge(d.status)}</td>
            <td>${suggested ? badge(suggested) + (d.status && d.status !== suggested ? ' <span class="small">(overridden)</span>' : '') : '<span class="small">-</span>'}</td>
            <td>${d.analysis ? pagesOf(d).join(', ') || '-' : '-'}</td>
        </tr>`;
    }).join('');

    const details = disclosures.map(d => {
        const a = d.analysis;
        const suggested = a ? STATUS_FROM_API[a.status] : null;
        const evidence = a
            ? (a.evidence.length
                ? a.evidence.map(p => `
                    <div class="passage">
                        <div class="passage-head"><b>Page ${p.page}</b><span>Match ${pct(passageMatch(p))}</span></div>
                        <div class="passage-body">${highlight(p.text, a.matched_keywords)}</div>
                    </div>`).join('')
                : '<p class="small">No relevant passages were found in the report.</p>')
            : '<p class="small">No automated analysis was run for this disclosure.</p>';
        return `
            <section class="disclosure" id="${d.id}">
                <div class="d-head">
                    <div>
                        <div class="d-id">${d.id} · ${esc(d.ref)}</div>
                        <h3>${esc(d.title)}</h3>
                    </div>
                    ${badge(d.status)}
                </div>
                <p class="desc">${esc(d.description)}</p>
                <table class="facts">
                    <tr><th>Final status</th><td>${d.status ? STATUS[d.status].label : 'Not assessed'}</td></tr>
                    <tr><th>Automated suggestion</th><td>${suggested ? STATUS[suggested].label + (d.status && d.status !== suggested ? ' (overridden by reviewer)' : '') : '-'}</td></tr>
                    <tr><th>Evidence strength</th><td>${a ? pct(a.confidence) : '-'}</td></tr>
                    <tr><th>Evidence pages</th><td>${a ? pagesOf(d).join(', ') || '-' : '-'}</td></tr>
                    <tr><th>Matched terms</th><td>${a && a.matched_keywords.length ? a.matched_keywords.map(esc).join(', ') : '-'}</td></tr>
                    <tr><th>Reviewer notes</th><td>${d.notes ? esc(d.notes).replace(/\n/g, '<br>') : '-'}</td></tr>
                </table>
                <h4>What TCFD asks</h4>
                <ul>${d.asks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
                <h4>Supporting evidence</h4>
                ${evidence}
            </section>`;
    }).join('');

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
    .page { max-width: 860px; margin: 0 auto; padding: 40px 32px; }
    h1 { font-size: 24px; margin: 0 0 4px; }
    h2 { font-size: 16px; margin: 32px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #1d2330; }
    h3 { font-size: 15px; margin: 2px 0 0; }
    h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #5b6474; margin: 16px 0 6px; }
    .sub { color: #5b6474; margin: 0; }
    .meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 20px 0 0; }
    .meta div { border: 1px solid #e3e6eb; border-radius: 8px; padding: 10px 12px; }
    .meta span { display: block; font-size: 11px; color: #8a93a3; text-transform: uppercase; letter-spacing: 0.04em; }
    .meta b { font-size: 15px; overflow-wrap: anywhere; }
    .score b { font-size: 26px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #e3e6eb; vertical-align: top; }
    thead th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: #5b6474; border-bottom: 1px solid #c9ced6; }
    .facts th { width: 180px; color: #5b6474; font-weight: 500; }
    a { color: #3b5bdb; text-decoration: none; }
    .badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; white-space: nowrap; }
    .badge.compliant { background: #ebf8ee; color: #2f9e44; }
    .badge.partial { background: #fff4e6; color: #c25e00; }
    .badge.noncompliant { background: #fff0f0; color: #c92a2a; }
    .badge.none { background: #f1f3f5; color: #868e96; }
    .small { color: #8a93a3; font-size: 12px; }
    .disclosure { border: 1px solid #e3e6eb; border-radius: 10px; padding: 16px 18px; margin: 0 0 14px; break-inside: avoid-page; }
    .d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .d-id { font-size: 11px; font-weight: 600; color: #3b5bdb; }
    .desc { color: #5b6474; margin: 6px 0 10px; }
    ul { margin: 0; padding-left: 18px; color: #5b6474; }
    .passage { border: 1px solid #e3e6eb; border-radius: 8px; margin-bottom: 8px; break-inside: avoid; }
    .passage-head { display: flex; justify-content: space-between; padding: 5px 10px; background: #f8f9fb; border-bottom: 1px solid #e3e6eb; font-size: 12px; color: #5b6474; }
    .passage-head b { color: #1d2330; }
    .passage-body { padding: 8px 10px; }
    mark { background: #fff3bf; color: inherit; }
    .note { margin-top: 32px; padding: 12px 14px; background: #f8f9fb; border-radius: 8px; color: #5b6474; font-size: 12px; }
    .print-hint { text-align: right; margin-bottom: 12px; }
    .print-hint button { font: inherit; padding: 6px 12px; border: 1px solid #c9ced6; border-radius: 6px; background: #fff; cursor: pointer; }
    @media print {
        .print-hint { display: none; }
        .page { padding: 0; }
        @page { margin: 16mm; }
        a { color: inherit; }
    }
</style>
</head>
<body>
<div class="page">
    <div class="print-hint"><button onclick="window.print()">Print / Save as PDF</button></div>
    <h1>TCFD Compliance Assessment</h1>
    <p class="sub">${esc(company)} · Reporting year ${esc(year)}</p>

    <div class="meta">
        <div class="score"><span>Overall score</span><b>${Math.round(s.score)}%</b></div>
        <div><span>Compliant / Partial / Non-compliant</span><b>${s.counts.compliant} / ${s.counts.partial} / ${s.counts.noncompliant}</b></div>
        <div><span>Not assessed</span><b>${s.unassessed}</b></div>
        <div><span>Source report</span><b>${source ? esc(source.file) : 'Manual assessment'}</b></div>
    </div>

    <h2>Summary by pillar</h2>
    <table>
        <thead><tr><th>Pillar</th><th>Disclosures</th><th>Points</th><th>Score</th></tr></thead>
        <tbody>${pillarRows}</tbody>
    </table>

    <h2>Disclosure overview</h2>
    <table>
        <thead><tr><th>ID</th><th>Disclosure</th><th>Status</th><th>Suggested</th><th>Evidence pages</th></tr></thead>
        <tbody>${overviewRows}</tbody>
    </table>

    <h2>Detailed findings and evidence</h2>
    ${details}

    <div class="note">
        <b>Method.</b> Score = (Compliant × 1 + Partial × 0.5) ÷ 11 × 100.
        ${source ? `Automated suggestions were generated from <i>${esc(source.file)}</i> (${source.pages} pages) using ${esc(source.method || 'evidence retrieval')}; page numbers refer to the PDF.
        Suggestions are a starting point and were reviewed by the assessor; overridden items are marked.` : 'All statuses were set manually.'}
        <br>Generated ${esc(generated)} with the TCFD Compliance Calculator.
    </div>
</div>
</body>
</html>`;

    download(html, `${fileStem()}.html`, 'text/html');
}

// --------------------------------------------------------------------------- init

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('reportingYear').value = new Date().getFullYear() - 1;
    setupFileInput();
    render();
});
