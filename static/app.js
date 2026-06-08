/* ═══════════════════════════════════════════════
   BboxPulse – Frontend Logic v2.0
   ═══════════════════════════════════════════════ */

let REFRESH_MS = 4000;
const MAX_SPEED_KBPS = 1000000; // 1 Gb/s max for gauge scaling
let CHART_MAX_POINTS = 60;

const historyData = {
    labels: [], speedDown: [], speedUp: [],
    sessionDown: [], sessionUp: [],
    netActive: [], netKnown: [], hwRx: [], hwTx: []
};

// ─── DOM Refs ────────────────────────────────────

const $ = (id) => document.getElementById(id);

const els = {
    clock: $('clock'),
    statusText: $('status-text'),
    statusBar: $('status-bar'),
    speedDown: $('speed-down'),
    speedUp: $('speed-up'),
    gaugeDown: $('gauge-down'),
    gaugeUp: $('gauge-up'),
    sessionDown: $('session-down'),
    sessionUp: $('session-up'),
    progressPercent: $('progress-percent'),
    progressFill: $('progress-fill'),
    target: $('target'),
    etaAvg: $('eta-avg'),
    totalDown: $('total-down'),
    totalUp: $('total-up'),
    errorBanner: $('error-banner'),
    errorText: $('error-text'),
    cardGrid: $('card-grid'),
    specMax: $('spec-max'),
    specContract: $('spec-contract'),
    sysModelFirmware: $('sys-model-firmware'),
    sysConnIp: $('sys-conn-ip'),
    hwPackets: $('hw-packets'),
    hwErrors: $('hw-errors'),
    netActive: $('net-active'),
    netKnown: $('net-known'),
    wifi24_5: $('wifi-24-5'),
    wifi6_mlo: $('wifi-6-mlo'),
    // Config page elements
    btnSaveConfig: $('btn-save-config'),
    btnSaveTotal: $('btn-save-total'),
    configMessage: $('config-message'),
    cfgPassword: $('cfg-password'),
    cfgBaseUrl: $('cfg-base-url'),
    cfgRefresh: $('cfg-refresh'),
    cfgMonitorInterval: $('cfg-monitor-interval'),
    cfgMaxPoints: $('cfg-max-points'),
    cfgTargetTb: $('cfg-target-tb'),
    cfgUptimeDate: $('cfg-uptime-date'),
    cfgTotalDownTb: $('cfg-total-down-tb'),
    cfgTotalUpGb: $('cfg-total-up-gb'),
    redisStatus: $('redis-status'),
    uptimeDays: $('uptime-days'),
    monitorIntervalDisplay: $('monitor-interval-display'),
};

// ─── Clock ───────────────────────────────────────

function updateClock() {
    if (!els.clock) return;
    const now = new Date();
    els.clock.textContent = now.toLocaleTimeString('fr-FR', {
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}
setInterval(updateClock, 1000);
updateClock();

// ─── Flash animation on value change ────────────

function setValue(el, value) {
    if (!el) return;
    const strVal = String(value);
    if (el.textContent !== strVal) {
        el.textContent = strVal;
        el.classList.remove('flash');
        void el.offsetWidth;
        el.classList.add('flash');
    }
}

// ─── Gauge fill ─────────────────────────────────

function setGauge(el, rawKbps) {
    if (!el) return;
    const pct = Math.min((rawKbps / MAX_SPEED_KBPS) * 100, 100);
    el.style.width = pct + '%';
}

// ─── Number Formatting ──────────────────────────

function fmtNumber(n) {
    return (n || 0).toLocaleString('fr-FR');
}

// ─── Charts ─────────────────────────────────────

Chart.defaults.color = "rgba(255, 255, 255, 0.4)";
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;

function createSparkline(ctxId, datasets) {
    const el = document.getElementById(ctxId);
    if (!el) return null;
    const ctx = el.getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: { labels: historyData.labels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: { display: false },
                y: { display: false, beginAtZero: false }
            },
            elements: {
                point: { radius: 0, hitRadius: 0, hoverRadius: 0 },
                line: { tension: 0.4, borderWidth: 1.5 }
            },
            layout: { padding: 0 }
        }
    });
}

const charts = {};

function initCharts() {
    const speed = createSparkline('chart-speed', [
        { data: historyData.speedDown, borderColor: '#0070f3', backgroundColor: 'rgba(0, 112, 243, 0.08)', fill: true },
        { data: historyData.speedUp, borderColor: '#7928ca', backgroundColor: 'rgba(121, 40, 202, 0.08)', fill: true }
    ]);
    if (speed) charts.speed = speed;

    const session = createSparkline('chart-session', [
        { data: historyData.sessionDown, borderColor: '#0070f3', backgroundColor: 'rgba(0, 112, 243, 0.08)', fill: true },
        { data: historyData.sessionUp, borderColor: '#7928ca', backgroundColor: 'rgba(121, 40, 202, 0.08)', fill: true }
    ]);
    if (session) charts.session = session;

    const network = createSparkline('chart-network', [
        { data: historyData.netActive, borderColor: '#00c853', backgroundColor: 'rgba(0, 200, 83, 0.08)', fill: true }
    ]);
    if (network) charts.network = network;

    const hardware = createSparkline('chart-hardware', [
        { data: historyData.hwRx, borderColor: '#00c853' },
        { data: historyData.hwTx, borderColor: '#ee0000' }
    ]);
    if (hardware) charts.hardware = hardware;
}
initCharts();

function updateCharts() {
    Object.values(charts).forEach(c => {
        if (c) c.update();
    });
}

// ─── Fetch Stats ─────────────────────────────────

let refreshInterval = null;

async function fetchStats() {
    try {
        const res = await fetch('/api/stats');

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showError(err.error || `Erreur HTTP ${res.status}`);
            return;
        }

        const d = await res.json();
        hideError();
        removeSkeleton();

        // Speed
        setValue(els.speedDown, d.speed.down);
        setValue(els.speedUp, d.speed.up);
        setGauge(els.gaugeDown, d.speed.down_raw);
        setGauge(els.gaugeUp, d.speed.up_raw);

        // Session
        setValue(els.sessionDown, d.session.down);
        setValue(els.sessionUp, d.session.up);

        // Network
        if (d.network) {
            setValue(els.netActive, d.network.active_devices);
            setValue(els.netKnown, d.network.total_known);
        }

        // Wi-Fi
        if (d.wifi) {
            const w24 = d.wifi.band_2_4GHz.status === 'ON' ? d.wifi.band_2_4GHz.standard : 'OFF';
            const w5 = d.wifi.band_5GHz.status === 'ON' ? d.wifi.band_5GHz.standard : 'OFF';
            setValue(els.wifi24_5, `${w24} / ${w5}`);

            const w6 = d.wifi.band_6GHz.status === 'ON' ? d.wifi.band_6GHz.standard : 'OFF';
            const mlo = d.wifi.mlo_wifi7.status === 'ON' ? 'Actif' : 'OFF';
            setValue(els.wifi6_mlo, `${w6} / ${mlo}`);
        }

        // Line Specs
        if (d.line_specs) {
            setValue(els.specMax, d.line_specs.max_down);
            setValue(els.specContract, d.line_specs.contract_down);
        }

        // System Info
        if (d.system) {
            setValue(els.sysModelFirmware, `${d.system.model} / ${d.system.firmware}`);
            setValue(els.sysConnIp, `${d.system.connection_type} / ${d.system.public_ip}`);
        }


        // Hardware
        if (d.hardware) {
            setValue(els.hwPackets, fmtNumber(d.hardware.rx_packets) + ' / ' + fmtNumber(d.hardware.tx_packets));
            setValue(els.hwErrors, fmtNumber(d.hardware.rx_errors) + ' / ' + fmtNumber(d.hardware.tx_errors));
        }

        // Objective
        setValue(els.progressPercent, d.objective.progress + '%');
        if (els.progressFill) els.progressFill.style.width = d.objective.progress + '%';
        if (els.target) els.target.textContent = 'Objectif : ' + d.objective.target;
        setValue(els.etaAvg, d.objective.eta_avg);

        // Total
        setValue(els.totalDown, d.total.down);
        setValue(els.totalUp, d.total.up);

        // Status
        if (els.statusText) els.statusText.textContent = 'Live · ' + d.timestamp;
        if (els.statusBar) els.statusBar.classList.remove('error');

        // Push to sparkline data
        const nowStr = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        pushShift(historyData.labels, nowStr);

        const mbpsDown = (d.speed.down_raw || 0) / 1000;
        const mbpsUp = (d.speed.up_raw || 0) / 1000;
        const mbDown = (d.session.down_raw || 0) / (1024 * 1024);
        const mbUp = (d.session.up_raw || 0) / (1024 * 1024);

        pushShift(historyData.speedDown, mbpsDown);
        pushShift(historyData.speedUp, mbpsUp);
        pushShift(historyData.sessionDown, mbDown);
        pushShift(historyData.sessionUp, mbUp);
        pushShift(historyData.netActive, d.network ? (d.network.active_devices || 0) : 0);
        pushShift(historyData.netKnown, d.network ? (d.network.total_known || 0) : 0);
        pushShift(historyData.hwRx, d.hardware ? (d.hardware.rx_packets || 0) : 0);
        pushShift(historyData.hwTx, d.hardware ? (d.hardware.tx_packets || 0) : 0);

        updateCharts();

        // Refresh live history charts if visible
        if (typeof currentHistoryTimeframe !== 'undefined' && currentHistoryTimeframe === 'live' && document.getElementById('chart-hist-speed')) {
            fetchHistory();
        }

    } catch (e) {
        showError('Impossible de contacter le serveur');
    }
}

function pushShift(arr, val) {
    arr.push(val);
    if (arr.length > CHART_MAX_POINTS) arr.shift();
}

// ─── Error handling ──────────────────────────────

function showError(msg) {
    if (els.errorBanner) els.errorBanner.classList.add('visible');
    if (els.errorText) els.errorText.textContent = msg;
    if (els.statusBar) els.statusBar.classList.add('error');
    if (els.statusText) els.statusText.textContent = 'Déconnecté';
}

function hideError() {
    if (els.errorBanner) els.errorBanner.classList.remove('visible');
}

function removeSkeleton() {
    document.querySelectorAll('.skeleton').forEach(el => el.classList.remove('skeleton'));
}

// ─── Config Page Logic ──────────────────────────

async function loadConfigPage() {
    if (!els.btnSaveConfig) return; // Not on config page

    try {
        const res = await fetch('/api/config');
        if (!res.ok) return;
        const cfg = await res.json();

        // Populate fields
        if (els.cfgBaseUrl) els.cfgBaseUrl.value = cfg.bbox_base_url || '';
        if (els.cfgRefresh) els.cfgRefresh.value = cfg.refresh_interval_ms || 4000;
        if (els.cfgMonitorInterval) els.cfgMonitorInterval.value = cfg.monitor_interval || 60;
        if (els.cfgMaxPoints) els.cfgMaxPoints.value = cfg.max_chart_points || 60;
        if (els.cfgTargetTb) els.cfgTargetTb.value = cfg.target_tb || 5;
        if (els.cfgUptimeDate) els.cfgUptimeDate.value = cfg.uptime_start_date || '';

        // System status
        if (els.redisStatus) {
            const connected = cfg.redis_status === 'connected';
            els.redisStatus.className = `status-badge ${connected ? 'connected' : 'disconnected'}`;
            els.redisStatus.innerHTML = `<span class="dot-sm"></span><span>${connected ? 'Connecté' : 'Déconnecté'}</span>`;
        }
        if (els.uptimeDays) els.uptimeDays.textContent = `${cfg.uptime_days} jours`;
        if (els.monitorIntervalDisplay) els.monitorIntervalDisplay.textContent = `${cfg.monitor_interval || 60}s`;

        // Apply dynamic refresh
        REFRESH_MS = cfg.refresh_interval_ms || 4000;
        CHART_MAX_POINTS = cfg.max_chart_points || 60;

    } catch (e) {
        console.error('Failed to load config:', e);
    }
}

// Save config
if (els.btnSaveConfig) {
    els.btnSaveConfig.addEventListener('click', async () => {
        const body = {};

        if (els.cfgPassword && els.cfgPassword.value.trim()) {
            body.bbox_password = els.cfgPassword.value.trim();
        }
        if (els.cfgBaseUrl && els.cfgBaseUrl.value.trim()) {
            body.bbox_base_url = els.cfgBaseUrl.value.trim();
        }
        if (els.cfgRefresh && els.cfgRefresh.value) {
            body.refresh_interval_ms = parseInt(els.cfgRefresh.value);
        }
        if (els.cfgMonitorInterval && els.cfgMonitorInterval.value) {
            body.monitor_interval = parseInt(els.cfgMonitorInterval.value);
        }
        if (els.cfgMaxPoints && els.cfgMaxPoints.value) {
            body.max_chart_points = parseInt(els.cfgMaxPoints.value);
        }
        if (els.cfgTargetTb && els.cfgTargetTb.value) {
            body.target_tb = parseFloat(els.cfgTargetTb.value);
        }
        if (els.cfgUptimeDate && els.cfgUptimeDate.value) {
            body.uptime_start_date = els.cfgUptimeDate.value;
        }

        if (Object.keys(body).length === 0) {
            showConfigMsg('Aucune modification détectée.', 'error');
            return;
        }

        els.btnSaveConfig.disabled = true;
        els.btnSaveConfig.textContent = '⏳ Sauvegarde...';

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await res.json();

            if (res.ok) {
                showConfigMsg('✅ Configuration sauvegardée avec succès !', 'success');
                // Apply new refresh if changed
                if (body.refresh_interval_ms) {
                    REFRESH_MS = body.refresh_interval_ms;
                    restartRefresh();
                }
                if (body.max_chart_points) {
                    CHART_MAX_POINTS = body.max_chart_points;
                }
                loadConfigPage(); // Reload to reflect changes
            } else {
                showConfigMsg(data.message || 'Erreur lors de la sauvegarde.', 'error');
            }
        } catch (e) {
            showConfigMsg('Impossible de contacter le serveur.', 'error');
        } finally {
            els.btnSaveConfig.disabled = false;
            els.btnSaveConfig.textContent = '💾 Sauvegarder la Configuration';
        }
    });
}

// Save total
if (els.btnSaveTotal) {
    els.btnSaveTotal.addEventListener('click', async () => {
        const downTb = els.cfgTotalDownTb ? els.cfgTotalDownTb.value.trim() : '';
        const upGb = els.cfgTotalUpGb ? els.cfgTotalUpGb.value.trim() : '';

        if (!downTb && !upGb) {
            showConfigMsg('Remplissez au moins un champ de total.', 'error');
            return;
        }

        let url = '/api/set_total?';
        const params = [];
        if (downTb) params.push(`down_tb=${encodeURIComponent(downTb)}`);
        if (upGb) params.push(`up_gb=${encodeURIComponent(upGb)}`);

        els.btnSaveTotal.disabled = true;
        els.btnSaveTotal.textContent = '⏳ Application...';

        try {
            const res = await fetch(url + params.join('&'));
            const data = await res.json();

            if (res.ok) {
                showConfigMsg('✅ Total historique mis à jour !', 'success');
                if (els.cfgTotalDownTb) els.cfgTotalDownTb.value = '';
                if (els.cfgTotalUpGb) els.cfgTotalUpGb.value = '';
            } else {
                showConfigMsg(data.message || 'Erreur lors de la mise à jour.', 'error');
            }
        } catch (e) {
            showConfigMsg('Impossible de contacter le serveur.', 'error');
        } finally {
            els.btnSaveTotal.disabled = false;
            els.btnSaveTotal.textContent = '📊 Appliquer le Total';
        }
    });
}

function showConfigMsg(msg, type) {
    const el = els.configMessage;
    if (!el) return;
    el.textContent = msg;
    el.className = `settings-message ${type} show`;
    setTimeout(() => el.classList.remove('show'), 5000);
}

function restartRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(fetchStats, REFRESH_MS);
}

// ─── Historical Charts ───────────────────────────

let currentHistoryTimeframe = 'live';
let histSpeedChart = null;
let histNetworkChart = null;

function initHistCharts() {
    const ctxSpeed = document.getElementById('chart-hist-speed');
    if (ctxSpeed) {
        histSpeedChart = new Chart(ctxSpeed.getContext('2d'), {
            type: 'line',
            data: { labels: [], datasets: [
                {
                    label: 'Download (Mb/s)',
                    data: [],
                    borderColor: '#0070f3',
                    backgroundColor: 'rgba(0, 112, 243, 0.08)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderWidth: 2
                },
                {
                    label: 'Upload (Mb/s)',
                    data: [],
                    borderColor: '#7928ca',
                    backgroundColor: 'rgba(121, 40, 202, 0.08)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderWidth: 2
                }
            ]},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: true, position: 'top', labels: { usePointStyle: true, pointStyle: 'circle', padding: 16, font: { size: 11 } } },
                    tooltip: { enabled: true, backgroundColor: 'rgba(0,0,0,0.8)', titleFont: { size: 12 }, bodyFont: { size: 11 }, cornerRadius: 8, padding: 10 }
                },
                scales: {
                    x: { display: true, grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { maxRotation: 0, maxTicksLimit: 8 } },
                    y: { display: true, beginAtZero: true, grid: { color: 'rgba(255,255,255,0.03)' } }
                }
            }
        });
    }

    const ctxNet = document.getElementById('chart-hist-network');
    if (ctxNet) {
        histNetworkChart = new Chart(ctxNet.getContext('2d'), {
            type: 'line',
            data: { labels: [], datasets: [
                {
                    label: 'Actifs',
                    data: [],
                    borderColor: '#00c853',
                    backgroundColor: 'rgba(0, 200, 83, 0.08)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderWidth: 2
                },
                {
                    label: 'Connus',
                    data: [],
                    borderColor: '#f5a623',
                    backgroundColor: 'rgba(245, 166, 35, 0.08)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderWidth: 2
                }
            ]},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: true, position: 'top', labels: { usePointStyle: true, pointStyle: 'circle', padding: 16, font: { size: 11 } } },
                    tooltip: { enabled: true, backgroundColor: 'rgba(0,0,0,0.8)', cornerRadius: 8, padding: 10 }
                },
                scales: {
                    x: { display: true, grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { maxRotation: 0, maxTicksLimit: 8 } },
                    y: { display: true, beginAtZero: true, grid: { color: 'rgba(255,255,255,0.03)' } }
                }
            }
        });
    }
}

initHistCharts();

document.querySelectorAll('.timeframe-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.timeframe-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentHistoryTimeframe = btn.getAttribute('data-timeframe');
        fetchHistory();
    });
});

async function fetchHistory() {
    if (currentHistoryTimeframe === 'live') {
        if (histSpeedChart) {
            histSpeedChart.data.labels = [...historyData.labels];
            histSpeedChart.data.datasets[0].data = [...historyData.speedDown];
            histSpeedChart.data.datasets[1].data = [...historyData.speedUp];
            histSpeedChart.update();
        }
        if (histNetworkChart) {
            histNetworkChart.data.labels = [...historyData.labels];
            histNetworkChart.data.datasets[0].data = [...historyData.netActive];
            histNetworkChart.data.datasets[1].data = [...historyData.netKnown];
            histNetworkChart.update();
        }
        return;
    }

    try {
        const res = await fetch(`/api/history?timeframe=${currentHistoryTimeframe}`);
        if (!res.ok) return;
        const data = await res.json();

        if (histSpeedChart) {
            histSpeedChart.data.labels = data.labels;
            histSpeedChart.data.datasets[0].data = data.speed_down;
            histSpeedChart.data.datasets[1].data = data.speed_up;
            histSpeedChart.update();
        }

        if (histNetworkChart) {
            histNetworkChart.data.labels = data.labels;
            histNetworkChart.data.datasets[0].data = data.active_devices;
            histNetworkChart.data.datasets[1].data = data.known_devices;
            histNetworkChart.update();
        }
    } catch (e) {
        console.error('Error fetching history:', e);
    }
}

// ─── Init ────────────────────────────────────────

// Load config page if we're on it
loadConfigPage();

// Start polling
fetchStats();
refreshInterval = setInterval(fetchStats, REFRESH_MS);

// Auto-refresh historical charts (60s)
if (document.getElementById('chart-hist-speed')) {
    setInterval(() => {
        if (currentHistoryTimeframe !== 'live') {
            fetchHistory();
        }
    }, 60000);
}
