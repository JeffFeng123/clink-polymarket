const state = {
  readiness: null,
  health: null,
  preview: null,
  execution: null,
  timeline: [],
};

const $ = (id) => document.getElementById(id);

function utcClock() {
  const now = new Date();
  $('clock').textContent = now.toISOString().slice(11, 19) + ' UTC';
}
setInterval(utcClock, 1000);
utcClock();

function addBubble(text, kind = 'system') {
  const node = document.createElement('div');
  node.className = `bubble ${kind}`;
  node.textContent = text;
  $('chatFeed').appendChild(node);
  $('chatFeed').scrollTop = $('chatFeed').scrollHeight;
}

function addTimeline(title, body, tone = '') {
  state.timeline.unshift({ title, body, tone, at: new Date().toISOString() });
  state.timeline = state.timeline.slice(0, 8);
  renderTimeline();
}

function renderTimeline() {
  $('timeline').innerHTML = state.timeline.map((item) => `
    <div class="event ${item.tone}">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.body)}</p>
      <p class="mono mini">${item.at.slice(11, 19)} UTC</p>
    </div>
  `).join('');
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function refresh() {
  try {
    const [readiness, health, consoleHealth] = await Promise.all([
      api('/api/readiness'),
      api('/api/adapter-health'),
      api('/api/healthz'),
    ]);
    state.readiness = readiness;
    state.health = health;
    renderReadiness(readiness, health, consoleHealth);
    addTimeline('Systems check', readiness.live_ready ? 'Live readiness is green.' : `Blocked: ${(readiness.missing || []).join(', ')}`, readiness.live_ready ? 'good' : 'bad');
  } catch (error) {
    addBubble(`Refresh failed: ${error.message}`, 'system');
    addTimeline('Systems check failed', error.message, 'bad');
  }
}

function renderReadiness(readiness, health, consoleHealth) {
  const livePill = $('livePill');
  livePill.classList.toggle('ready', Boolean(readiness.live_ready));
  livePill.classList.toggle('blocked', !readiness.live_ready);
  livePill.lastChild.textContent = readiness.live_ready ? 'Live ready' : 'Live blocked';
  $('launchCore').textContent = readiness.live_ready ? 'READY' : 'HOLD';
  $('headline').textContent = readiness.live_ready ? 'Hermes can propose. Clink is cleared for launch.' : 'Live launch is blocked until Clink clears readiness.';

  $('bridgePill').lastChild.textContent = consoleHealth.mode === 'hermes_http_bridge' ? 'Hermes CLI bridge' : 'Local MCP runner';

  const checks = [
    ['Live mode', readiness.live_mode_enabled ? 'Enabled' : 'Disabled', readiness.live_mode_enabled],
    ['Missing', (readiness.missing || []).length ? readiness.missing.join(', ') : 'None', !(readiness.missing || []).length],
    ['Warnings', (readiness.warnings || []).length ? readiness.warnings.join(', ') : 'None', !(readiness.warnings || []).length],
    ['Max order', `${readiness.max_order_usdc || '--'} USDC`, true],
    ['Market service', health.market?.status || 'unknown', health.market?.status === 'ok'],
    ['Execution service', health.execution?.mode || 'unknown', health.execution?.status === 'ok'],
  ];
  $('readinessGrid').innerHTML = checks.map(([label, value, ok]) => `
    <div class="check-card ${ok ? 'ok' : 'bad'}">
      <strong>${ok ? '✓' : '×'} ${escapeHtml(label)}</strong>
      <div class="mono mini">${escapeHtml(value)}</div>
    </div>
  `).join('');
}

function renderPreview(preview) {
  state.preview = preview;
  if (!preview) return;
  const tokenReady = Boolean(preview.token_id);
  $('previewCard').innerHTML = `
    <p class="eyebrow">Current Preview</p>
    <h4>${escapeHtml(preview.question)}</h4>
    <p class="muted">${escapeHtml(preview.side)} ${escapeHtml(preview.outcome)} · ${escapeHtml(preview.amount_usdc)} USDC · state ${escapeHtml(preview.state)}</p>
    <div class="preview-grid">
      <div class="kv"><span>Preview ID</span><b>${escapeHtml(preview.order_preview_id)}</b></div>
      <div class="kv"><span>Market ID</span><b>${escapeHtml(preview.market_id)}</b></div>
      <div class="kv"><span>Limit Price</span><b>${escapeHtml(preview.limit_price)}</b></div>
      <div class="kv"><span>Shares</span><b>${escapeHtml(preview.estimated_shares)}</b></div>
      <div class="kv"><span>Token ID</span><b>${tokenReady ? escapeHtml(preview.token_id) : 'MISSING'}</b></div>
      <div class="kv"><span>Policy</span><b>${escapeHtml(preview.core_policy_decision?.decision || 'unknown')}</b></div>
    </div>
  `;
  $('executeBtn').disabled = !(tokenReady && $('livePhrase').value === 'LIVE');
  addTimeline('Preview created', `${preview.order_preview_id} · token ${tokenReady ? 'ready' : 'missing'}`, tokenReady ? 'good' : 'warn');
}

async function handleTask(event) {
  event.preventDefault();
  const message = $('messageInput').value.trim();
  const amount = $('amountInput').value.trim() || '1';
  if (!message) return;
  addBubble(message, 'user');
  addTimeline('User intent', message, '');
  const button = event.submitter;
  button.disabled = true;
  button.textContent = 'Hermes thinking...';
  try {
    const payload = await api('/api/agent/message', {
      method: 'POST',
      body: JSON.stringify({ message, amount_usdc: amount, user_id: 'console-user', agent_id: 'hermes_console_agent' }),
    });
    (payload.agent_messages || ['Hermes returned a response.']).forEach((line) => addBubble(line, 'agent'));
    if (payload.bridge_mode === 'hermes_cli') {
      addTimeline(
        'Hermes bridge ack',
        `${payload.request_id || 'no-request-id'} · return=${payload.hermes_returncode ?? payload.returncode ?? 'unknown'} · output=${payload.raw_hermes_output_length ?? 0} chars`,
        payload.hermes_received ? 'good' : 'warn',
      );
    }
    if (payload.hermes_bridge_error) addBubble(`Hermes bridge failed, local fallback used: ${payload.hermes_bridge_error}`, 'system');
    if (payload.order_preview) renderPreview(payload.order_preview);
    if (payload.selected_opportunity) addTimeline('Opportunity selected', payload.selected_opportunity.question || payload.selected_opportunity.market_id, 'good');
  } catch (error) {
    addBubble(`Hermes flow failed: ${error.message}`, 'system');
    addTimeline('Hermes flow failed', error.message, 'bad');
  } finally {
    button.disabled = false;
    button.textContent = 'Send to Hermes';
  }
}

async function executeLiveTrade() {
  if (!state.preview) return;
  const phrase = $('livePhrase').value;
  const button = $('executeBtn');
  button.disabled = true;
  button.textContent = 'Submitting...';
  try {
    const execution = await api('/api/executions', {
      method: 'POST',
      body: JSON.stringify({ order_preview_id: state.preview.order_preview_id, live_phrase: phrase, metadata: { console_confirmed_at: new Date().toISOString() } }),
    });
    state.execution = execution;
    $('lastExecution').textContent = `${execution.execution_id} · ${execution.state}`;
    addBubble(`Clink execution result: ${execution.state} / ${execution.execution_mode} / submitted=${execution.submitted_to_polymarket}`, execution.submitted_to_polymarket ? 'agent' : 'system');
    addTimeline('Live execution', `${execution.reason || execution.state} · order ${execution.order_id || 'none'}`, execution.submitted_to_polymarket ? 'good' : 'warn');
  } catch (error) {
    addBubble(`Execution blocked: ${error.message}`, 'system');
    addTimeline('Execution blocked', error.message, 'bad');
  } finally {
    button.disabled = !state.preview?.token_id;
    button.textContent = 'Execute Live Trade';
  }
}

$('taskForm').addEventListener('submit', handleTask);
$('executeBtn').addEventListener('click', executeLiveTrade);
$('refreshBtn').addEventListener('click', refresh);
$('livePhrase').addEventListener('input', () => {
  $('executeBtn').disabled = !(state.preview?.token_id && $('livePhrase').value === 'LIVE');
});

refresh();
