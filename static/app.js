const storageKey = 'agentic-settings';

function getSettings() {
  const saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
  return {
    apiKey: saved.apiKey || '',
    baseUrl: saved.baseUrl || ''
  };
}

function saveSettings() {
  const apiKey = document.getElementById('apiKey').value.trim();
  const baseUrl = document.getElementById('baseUrl').value.trim();
  localStorage.setItem(storageKey, JSON.stringify({ apiKey, baseUrl }));
  setHealth();
}

function authHeader() {
  const { apiKey } = getSettings();
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

function baseUrl() {
  return getSettings().baseUrl || '';
}

async function request(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...authHeader(),
    ...(options.headers || {})
  };
  const response = await fetch(`${baseUrl()}${path}`, { ...options, headers });
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

async function setHealth() {
  const healthEl = document.getElementById('health');
  if (!healthEl) return;
  try {
    const data = await request('/health', { headers: {} });
    healthEl.textContent = `Health: ${JSON.stringify(data)}`;
  } catch (err) {
    healthEl.textContent = `Health check failed: ${err.message}`;
  }
}

function bindSettings() {
  const settings = getSettings();
  const apiInput = document.getElementById('apiKey');
  const baseInput = document.getElementById('baseUrl');
  if (apiInput) apiInput.value = settings.apiKey;
  if (baseInput) baseInput.value = settings.baseUrl;
}

async function runAgent() {
  const prompt = document.getElementById('agentPrompt').value;
  const output = document.getElementById('agentOutput');
  try {
    const data = await request('/agent', {
      method: 'POST',
      body: JSON.stringify({ prompt })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function runQualityCheck() {
  const prompt = document.getElementById('qualityPrompt').value;
  const constraints = document.getElementById('qualityConstraints').value;
  const audience = document.getElementById('qualityAudience').value;
  const output = document.getElementById('qualityOutput');
  try {
    const data = await request('/quality-check', {
      method: 'POST',
      body: JSON.stringify({ prompt, constraints, audience })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function submitProjectBrief() {
  const name = document.getElementById('projectName').value;
  const purpose = document.getElementById('projectPurpose').value;
  const audience = document.getElementById('projectAudience').value;
  const constraints = document.getElementById('projectConstraints').value;
  const output = document.getElementById('projectOutput');
  try {
    const data = await request('/project-brief', {
      method: 'POST',
      body: JSON.stringify({ name, purpose, audience, constraints })
    });
    output.textContent = JSON.stringify(data, null, 2);
    await listProjectBriefs();
  } catch (err) {
    output.textContent = err.message;
  }
}

async function listProjectBriefs() {
  const container = document.getElementById('projectBriefs');
  if (!container) return;
  try {
    const data = await request('/project-briefs', { method: 'GET' });
    if (!data.data.length) {
      container.innerHTML = '<div class="card-item">No briefs yet.</div>';
      return;
    }
    container.innerHTML = data.data
      .map(
        (brief) => `
          <div class="card-item">
            <div class="flex" style="justify-content: space-between;">
              <strong>${brief.name}</strong>
              <span class="badge">${brief.created_at}</span>
            </div>
            <p class="status">${brief.purpose}</p>
            <p class="footer-note">Audience: ${brief.audience || 'N/A'}</p>
          </div>
        `
      )
      .join('');
  } catch (err) {
    container.innerHTML = `<div class="card-item">${err.message}</div>`;
  }
}

async function runAlignmentCheck() {
  const purpose = document.getElementById('alignPurpose').value;
  const featuresRaw = document.getElementById('alignFeatures').value;
  const output = document.getElementById('alignOutput');
  const features = featuresRaw
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    const data = await request('/alignment-check', {
      method: 'POST',
      body: JSON.stringify({ purpose, features })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function listTasks() {
  const output = document.getElementById('taskOutput');
  try {
    const data = await request('/tasks', { method: 'GET' });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function createTask() {
  const task = document.getElementById('taskText').value;
  const output = document.getElementById('taskOutput');
  try {
    const data = await request('/tasks', {
      method: 'POST',
      body: JSON.stringify({ task })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function updateTask() {
  const task = document.getElementById('taskText').value;
  const id = document.getElementById('taskId').value;
  const output = document.getElementById('taskOutput');
  try {
    const data = await request('/tasks', {
      method: 'PUT',
      body: JSON.stringify({ id, task })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function deleteTask() {
  const id = document.getElementById('taskId').value;
  const output = document.getElementById('taskOutput');
  try {
    const data = await request('/tasks', {
      method: 'DELETE',
      body: JSON.stringify({ id })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsList() {
  const path = document.getElementById('fsPath').value;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/list', {
      method: 'POST',
      body: JSON.stringify({ path })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsRead() {
  const path = document.getElementById('fsPath').value;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/read', {
      method: 'POST',
      body: JSON.stringify({ path })
    });
    output.textContent = JSON.stringify(data, null, 2);
    document.getElementById('fsContent').value = data.content || '';
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsWrite() {
  const path = document.getElementById('fsPath').value;
  const content = document.getElementById('fsContent').value;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/write', {
      method: 'POST',
      body: JSON.stringify({ path, content })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsDelete() {
  const path = document.getElementById('fsPath').value;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/delete', {
      method: 'POST',
      body: JSON.stringify({ path })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsMkdir() {
  const path = document.getElementById('fsPath').value;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/mkdir', {
      method: 'POST',
      body: JSON.stringify({ path })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsRmdir() {
  const path = document.getElementById('fsPath').value;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/rmdir', {
      method: 'POST',
      body: JSON.stringify({ path })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function fsReplace() {
  const path = document.getElementById('fsPath').value;
  const find = document.getElementById('fsFind').value;
  const replace = document.getElementById('fsReplace').value;
  const countRaw = document.getElementById('fsReplaceCount').value;
  const count = countRaw ? Number(countRaw) : undefined;
  const output = document.getElementById('fsOutput');
  try {
    const data = await request('/fs/replace', {
      method: 'POST',
      body: JSON.stringify({ path, find, replace, count })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

function parseJsonInput(value) {
  if (!value.trim()) {
    throw new Error('JSON input required');
  }
  return JSON.parse(value);
}

async function fsBulk() {
  const raw = document.getElementById('bulkFiles').value;
  const output = document.getElementById('bulkOutput');
  try {
    const files = parseJsonInput(raw);
    const data = await request('/fs/bulk', {
      method: 'POST',
      body: JSON.stringify({ files })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function executePlan() {
  const raw = document.getElementById('execPlan').value;
  const output = document.getElementById('execOutput');
  try {
    const operations = parseJsonInput(raw);
    const data = await request('/execute', {
      method: 'POST',
      body: JSON.stringify({ operations })
    });
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = err.message;
  }
}

async function exportSystem() {
  const name = document.getElementById('exportName').value || 'system';
  const output = document.getElementById('exportOutput');
  try {
    const response = await fetch(`${baseUrl()}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ name })
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || 'Export failed');
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${name}.zip`;
    link.click();
    window.URL.revokeObjectURL(url);
    if (output) output.textContent = 'Export created and downloaded.';
  } catch (err) {
    if (output) output.textContent = err.message;
  }
}

function initNav() {
  const current = document.body.dataset.page;
  document.querySelectorAll('nav a').forEach((link) => {
    if (link.dataset.page === current) {
      link.classList.add('active');
    }
  });
}

function init() {
  bindSettings();
  setHealth();
  initNav();
  if (document.getElementById('projectBriefs')) {
    listProjectBriefs();
  }
}

window.addEventListener('load', init);

window.saveSettings = saveSettings;
window.runAgent = runAgent;
window.runQualityCheck = runQualityCheck;
window.submitProjectBrief = submitProjectBrief;
window.runAlignmentCheck = runAlignmentCheck;
window.listTasks = listTasks;
window.createTask = createTask;
window.updateTask = updateTask;
window.deleteTask = deleteTask;
window.fsList = fsList;
window.fsRead = fsRead;
window.fsWrite = fsWrite;
window.fsDelete = fsDelete;
window.fsMkdir = fsMkdir;
window.fsRmdir = fsRmdir;
window.fsReplace = fsReplace;
window.fsBulk = fsBulk;
window.executePlan = executePlan;
window.exportSystem = exportSystem;
