// TCFD Compliance Calculator

const disclosures = [
    {
        id: 'G.1',
        pillar: 'Governance',
        title: 'Board oversight',
        status: null
    },
    {
        id: 'G.2',
        pillar: 'Governance',
        title: "Management's role",
        status: null
    },
    {
        id: 'S.1',
        pillar: 'Strategy',
        title: 'Climate risks and opportunities',
        status: null
    },
    {
        id: 'S.2',
        pillar: 'Strategy',
        title: 'Business and financial impact',
        status: null
    },
    {
        id: 'S.3',
        pillar: 'Strategy',
        title: 'Organisational resilience',
        status: null
    },
    {
        id: 'R.1',
        pillar: 'Risk Management',
        title: 'Risk identification and assessment',
        status: null
    },
    {
        id: 'R.2',
        pillar: 'Risk Management',
        title: 'Risk management processes',
        status: null
    },
    {
        id: 'R.3',
        pillar: 'Risk Management',
        title: 'Integration into overall risk management',
        status: null
    },
    {
        id: 'M.1',
        pillar: 'Metrics & Targets',
        title: 'Climate-related metrics',
        status: null
    },
    {
        id: 'M.2',
        pillar: 'Metrics & Targets',
        title: 'Scope 1, 2 and 3 emissions',
        status: null
    },
    {
        id: 'M.3',
        pillar: 'Metrics & Targets',
        title: 'Climate targets and performance',
        status: null
    }
];

// Initialize the UI
function init() {
    renderDisclosures();
    updateScore();
}

const API_BASE = 'http://localhost:8250';
const STATUS_FROM_API = {
    'Disclosed': 'compliant',
    'Partially disclosed': 'partial',
    'Not disclosed': 'noncompliant'
};

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Render the disclosures list
function renderDisclosures() {
    const container = document.getElementById('disclosuresList');
    container.innerHTML = '';

    disclosures.forEach((disclosure, index) => {
        const item = document.createElement('div');
        item.className = 'disclosure-item';

        let meta = '';
        let evidence = '';
        if (disclosure.suggested) {
            const pages = [...new Set(disclosure.evidence.map(e => e.page))].sort((a, b) => a - b);
            const overridden = disclosure.status !== STATUS_FROM_API[disclosure.suggested];
            meta = `<div class="disclosure-meta">Suggested: ${escapeHtml(disclosure.suggested)}
                (evidence strength ${Math.round(disclosure.confidence * 100)}%)
                ${pages.length ? '· pages ' + pages.join(', ') : ''}
                ${overridden ? '· <strong>overridden</strong>' : ''}</div>`;
            if (disclosure.evidence.length) {
                evidence = `<details class="evidence"><summary>Show evidence</summary>
                    ${disclosure.evidence.map(e => `<blockquote><span class="page-ref">p.${e.page}</span> ${escapeHtml(e.text)}</blockquote>`).join('')}
                </details>`;
            }
        }

        item.innerHTML = `
            <div class="disclosure-info">
                <div class="disclosure-pillar">${disclosure.id} · ${disclosure.pillar}</div>
                <div class="disclosure-title">${disclosure.title}</div>
                ${meta}
            </div>
            <div class="status-selector">
                <button class="status-btn ${disclosure.status === 'compliant' ? 'active active-compliant' : ''}"
                        onclick="setStatus(${index}, 'compliant')">Compliant</button>
                <button class="status-btn ${disclosure.status === 'partial' ? 'active active-partial' : ''}"
                        onclick="setStatus(${index}, 'partial')">Partial</button>
                <button class="status-btn ${disclosure.status === 'noncompliant' ? 'active active-noncompliant' : ''}"
                        onclick="setStatus(${index}, 'noncompliant')">Non-compliant</button>
            </div>
            ${evidence}
        `;
        container.appendChild(item);
    });
}

function setUploadStatus(message, isError = false) {
    const el = document.getElementById('uploadStatus');
    el.textContent = message;
    el.className = 'upload-status' + (isError ? ' error' : '');
}

// Send the PDF to the backend and pre-fill statuses from the result
async function analyzeReport() {
    const input = document.getElementById('reportFile');
    const button = document.getElementById('analyzeBtn');
    const file = input.files[0];
    if (!file) {
        setUploadStatus('Choose a PDF file first.', true);
        return;
    }

    const form = new FormData();
    form.append('file', file);
    button.disabled = true;
    setUploadStatus(`Analysing ${file.name}...`);

    try {
        const response = await fetch(`${API_BASE}/tcfd/assess`, { method: 'POST', body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || `Server returned ${response.status}`);
        }

        disclosures.forEach(disclosure => {
            const result = data.compliance_checklist[disclosure.id];
            if (!result) return;
            disclosure.suggested = result.status;
            disclosure.confidence = result.confidence;
            disclosure.evidence = result.evidence || [];
            disclosure.status = STATUS_FROM_API[result.status] || null;
        });

        const s = data.summary;
        setUploadStatus(`Analysed ${file.name}: ${s.disclosed} disclosed, ${s.partially_disclosed} partial, ` +
            `${s.not_disclosed} not disclosed (${s.pages_with_text} pages read). Review the evidence and adjust as needed.`);
        renderDisclosures();
        updateScore();
    } catch (err) {
        const msg = err instanceof TypeError
            ? 'Could not reach the backend at localhost:8250. Start it with "python tcfd_api_server.py" in backend/.'
            : `Analysis failed: ${err.message}`;
        setUploadStatus(msg, true);
    } finally {
        button.disabled = false;
    }
}

// Set status for a disclosure
function setStatus(index, status) {
    disclosures[index].status = status;
    renderDisclosures();
    updateScore();
}

// Calculate and update the score
function updateScore() {
    let totalPoints = 0;
    let compliantCount = 0;
    let partialCount = 0;
    let nonCompliantCount = 0;

    disclosures.forEach(disclosure => {
        if (disclosure.status === 'compliant') {
            totalPoints += 1;
            compliantCount++;
        } else if (disclosure.status === 'partial') {
            totalPoints += 0.5;
            partialCount++;
        } else if (disclosure.status === 'noncompliant') {
            totalPoints += 0;
            nonCompliantCount++;
        }
    });

    const overallScore = (totalPoints / disclosures.length) * 100;

    document.getElementById('overallScore').textContent = overallScore.toFixed(2) + '%';
    document.getElementById('compliantCount').textContent = compliantCount;
    document.getElementById('partialCount').textContent = partialCount;
    document.getElementById('nonCompliantCount').textContent = nonCompliantCount;
}

// Reset the assessment
function resetAssessment() {
    disclosures.forEach(disclosure => {
        disclosure.status = null;
        delete disclosure.suggested;
        delete disclosure.confidence;
        delete disclosure.evidence;
    });
    document.getElementById('reportFile').value = '';
    setUploadStatus('Upload a sustainability report to pre-fill statuses with page-cited evidence.');
    document.getElementById('companyName').value = '';
    document.getElementById('reportingYear').value = '2023';
    renderDisclosures();
    updateScore();
}

const STATUS_LABELS = { compliant: 'Compliant', partial: 'Partial', noncompliant: 'Non-compliant' };

// Export the report as a simple text file
function exportReport() {
    const companyName = document.getElementById('companyName').value || 'Not specified';
    const reportingYear = document.getElementById('reportingYear').value || 'Not specified';

    let report = `TCFD Compliance Assessment Report\n`;
    report += `=================================\n\n`;
    report += `Company: ${companyName}\n`;
    report += `Reporting Year: ${reportingYear}\n`;
    report += `Date: ${new Date().toLocaleDateString()}\n\n`;
    report += `Overall Compliance Score: ${document.getElementById('overallScore').textContent}\n`;
    report += `Compliant: ${document.getElementById('compliantCount').textContent}\n`;
    report += `Partial: ${document.getElementById('partialCount').textContent}\n`;
    report += `Non-compliant: ${document.getElementById('nonCompliantCount').textContent}\n\n`;
    report += `Detailed Assessment:\n`;
    report += `===================\n\n`;

    disclosures.forEach(disclosure => {
        const statusText = STATUS_LABELS[disclosure.status] || 'Not assessed';
        report += `${disclosure.id} - ${disclosure.pillar}\n`;
        report += `${disclosure.title}\n`;
        report += `Status: ${statusText}\n`;
        if (disclosure.suggested) {
            const pages = [...new Set(disclosure.evidence.map(e => e.page))].sort((a, b) => a - b);
            report += `Automated suggestion: ${disclosure.suggested}` +
                (pages.length ? ` (evidence on pages ${pages.join(', ')})` : '') + `\n`;
        }
        report += `\n`;
    });

    const blob = new Blob([report], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `TCFD_Assessment_${companyName.replace(/\s+/g, '_')}_${reportingYear}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
