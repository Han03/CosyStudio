function toggleSidebarCollapse() {
    const sidebar = document.getElementById('sidebarLeft');
    const btn = document.getElementById('sidebarCollapseBtn');
    if (!sidebar || !btn) return;

    const isCollapsed = sidebar.classList.toggle('collapsed');
    btn.title = isCollapsed ? '展开侧栏' : '收起侧栏';
}

let logWs = null;
let logWsReconnectTimer = null;
let logWsReconnectCount = 0;
const MAX_RECONNECT_ATTEMPTS = 10;

function connectLogWebSocket() {
    if (logWs && logWs.readyState === WebSocket.OPEN) return;

    const wsProtocol = API_BASE_URL.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = API_BASE_URL.replace(/^https?:\/\//, '').replace(/:\d+$/, '');
    const wsPort = API_BASE_URL.match(/:(\d+)$/)?.[1] || '8000';
    const wsUrl = `${wsProtocol}//${wsHost}:${wsPort}/api/logs/ws`;

    console.log('[日志WS] 尝试连接:', wsUrl);

    try {
        logWs = new WebSocket(wsUrl);
    } catch (e) {
        console.error('[日志WS] 创建连接失败:', e);
        scheduleLogWsReconnect();
        return;
    }

    logWs.onopen = function() {
        logWsReconnectCount = 0;
        console.log('[日志WS] 连接已建立');
    };

    logWs.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'history') {
                renderLogHistory(data.logs);
            } else if (data.type === 'log') {
                appendLogItem(data);
            }
        } catch (e) {
            console.error('[日志WS] 解析消息失败:', e);
        }
    };

    logWs.onclose = function(event) {
        console.log('[日志WS] 连接断开, code:', event.code, 'reason:', event.reason);
        if (event.code !== 1000 && event.code !== 1001) {
            scheduleLogWsReconnect();
        }
    };

    logWs.onerror = function(e) {
        console.error('[日志WS] 连接错误:', e);
    };
}

function scheduleLogWsReconnect() {
    if (logWsReconnectTimer) return;
    if (logWsReconnectCount >= MAX_RECONNECT_ATTEMPTS) {
        console.warn('[日志WS] 达到最大重连次数，停止重连');
        return;
    }
    
    logWsReconnectCount++;
    const delay = Math.min(3000 * logWsReconnectCount, 30000);
    console.log(`[日志WS] ${logWsReconnectCount}秒后重连 (第${logWsReconnectCount}次)`);
    
    logWsReconnectTimer = setTimeout(() => {
        logWsReconnectTimer = null;
        connectLogWebSocket();
    }, delay);
}

function renderLogHistory(logs) {
    const logPanel = document.getElementById('logPanel');
    if (!logPanel) return;

    if (!logs || logs.length === 0) {
        logPanel.innerHTML = '<div class="text-center text-muted"><small>暂无日志</small></div>';
        return;
    }

    logPanel.innerHTML = logs.map(log => {
        const time = new Date(log.timestamp * 1000).toLocaleTimeString();
        return `<div class="log-item ${log.level.toLowerCase()}"><small class="text-muted">[${time}]</small> ${escapeHtml(log.message)}</div>`;
    }).join('');
    logPanel.scrollTop = logPanel.scrollHeight;
}

function appendLogItem(log) {
    const logPanel = document.getElementById('logPanel');
    if (!logPanel) return;

    const emptyMsg = logPanel.querySelector('.text-center.text-muted');
    if (emptyMsg) {
        logPanel.innerHTML = '';
    }

    const time = new Date(log.timestamp * 1000).toLocaleTimeString();
    const logItem = document.createElement('div');
    logItem.className = `log-item ${log.level.toLowerCase()}`;
    logItem.innerHTML = `<small class="text-muted">[${time}]</small> ${escapeHtml(log.message)}`;
    logPanel.appendChild(logItem);

    while (logPanel.children.length > 200) {
        logPanel.removeChild(logPanel.firstChild);
    }

    logPanel.scrollTop = logPanel.scrollHeight;
}

function startStatusPolling() {
    fetchStatus();
    // 首屏立即拉一次资源监控，保证不为空
    try { refreshResources(); } catch (e) {}
    setInterval(fetchStatus, 3000);
    // 资源监控独立每5s强刷一次（与status轮询解耦，解决进度条为空问题）
    setInterval(() => { try { refreshResources(); } catch (e) {} }, 5000);
}

function updateHeaderStatus(dotId, statusId, loaded) {
    const dot = document.getElementById(dotId);
    const status = document.getElementById(statusId);
    if (dot && status) {
        dot.className = 'status-dot ' + (loaded ? 'available' : 'unavailable');
        status.textContent = loaded ? '已加载' : '未加载';
        status.style.color = loaded ? 'var(--neu-success)' : 'var(--neu-text-muted)';
    }
}

const MODEL_STATUS_MAP = [
    { dotId: 'headerQwenDot', name: 'Qwen', key: 'qwen_loaded' },
    { dotId: 'headerCosyvoiceDot', name: 'CosyVoice', key: 'cosyvoice_loaded' },
    { dotId: 'headerDreamliteDot', name: 'DreamLite', key: 'dreamlite_loaded' },
    { dotId: 'headerEmbeddingDot', name: 'Embedding', key: 'qwen_embedding_loaded' }
];

function updateModelsCombinedStatus(data) {
    let loadedCount = 0;
    MODEL_STATUS_MAP.forEach(m => {
        const dot = document.getElementById(m.dotId);
        const loaded = !!data[m.key];
        if (dot) {
            dot.className = 'status-dot ' + (loaded ? 'available' : 'unavailable');
        }
        const item = dot ? dot.closest('.model-dot-item') : null;
        if (item) {
            item.title = m.name + ': ' + (loaded ? '已加载' : '未加载');
        }
        if (loaded) loadedCount++;
    });
    const summary = document.getElementById('headerModelsSummary');
    if (summary) {
        summary.textContent = loadedCount + '/' + MODEL_STATUS_MAP.length;
        summary.style.color = loadedCount === MODEL_STATUS_MAP.length
            ? 'var(--neu-success)'
            : loadedCount > 0 ? 'var(--neu-warning)' : 'var(--neu-text-muted)';
    }
}

async function fetchStatus() {
    try {
        const data = await apiRequest(`${API_BASE_URL}/api/status`, { silent: true });

        const qwenStatusEl = document.getElementById('qwenStatus');
        if (qwenStatusEl) {
            qwenStatusEl.textContent = data.qwen_loaded ? '已加载' : '未加载';
            qwenStatusEl.style.color = data.qwen_loaded ? '#155724' : '#721c24';
        }
        const cosyvoiceStatusEl = document.getElementById('cosyvoiceStatus');
        if (cosyvoiceStatusEl) {
            cosyvoiceStatusEl.textContent = data.cosyvoice_loaded ? '已加载' : '未加载';
            cosyvoiceStatusEl.style.color = data.cosyvoice_loaded ? '#155724' : '#721c24';
        }
        const qwenOmniStatusEl = document.getElementById('qwenOmniStatus');
        if (qwenOmniStatusEl) {
            qwenOmniStatusEl.textContent = data.qwen_omni_loaded ? '已加载' : '未加载';
            qwenOmniStatusEl.style.color = data.qwen_omni_loaded ? '#155724' : '#721c24';
        }
        const dreamliteStatusEl = document.getElementById('dreamliteStatus');
        if (dreamliteStatusEl) {
            dreamliteStatusEl.textContent = data.dreamlite_loaded ? '已加载' : '未加载';
            dreamliteStatusEl.style.color = data.dreamlite_loaded ? '#155724' : '#721c24';
        }
        const qwenEmbeddingStatusEl = document.getElementById('qwenEmbeddingStatus');
        if (qwenEmbeddingStatusEl) {
            qwenEmbeddingStatusEl.textContent = data.qwen_embedding_loaded ? '已加载' : '未加载';
            qwenEmbeddingStatusEl.style.color = data.qwen_embedding_loaded ? '#155724' : '#721c24';
        }

        updateModelsCombinedStatus(data);

        const gpuAvailable = data.resources && data.resources.gpu && data.resources.gpu.available;
        const gpuDot = document.getElementById('headerGpuDot');
        const gpuStatus = document.getElementById('headerGpuStatus');
        if (gpuDot && gpuStatus) {
            gpuDot.className = 'status-dot ' + (gpuAvailable ? 'available' : 'unavailable');
            gpuStatus.textContent = gpuAvailable ? '已检测' : '未检测';
            gpuStatus.style.color = gpuAvailable ? 'var(--neu-success)' : 'var(--neu-text-muted)';
        }

        if (data.version) {
            document.getElementById('versionBadge').textContent = 'v' + data.version;
        }

        if (data.app_name) {
            var appTitleEl = document.getElementById('appTitle');
            if (appTitleEl) {
                appTitleEl.textContent = data.app_name;
            }
        }

        if (data.resources) {
            updateResourceDisplay(data.resources);
        } else {
            refreshResources();
        }
    } catch (e) {
        // 静默轮询，不弹出提示
    }
}

async function unloadModels() {
    if (!confirm('确定要卸载所有已加载的模型吗？')) {
        return;
    }

    const btn = event.target.closest('button');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 卸载中...';

    try {
        const data = await apiRequest(`${API_BASE_URL}/api/unload-models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            errorPrefix: '卸载失败'
        });
        if (data.success) {
            showToast('模型卸载成功！' + (data.message ? '\n' + data.message : ''), 'success');
            refreshResources();
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function shutdownService() {
    if (!confirm('确定要关闭服务吗？这将释放所有资源并停止服务。')) {
        return;
    }

    const btn = document.getElementById('shutdownBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 关闭中...';

    try {
        const data = await apiRequest(`${API_BASE_URL}/api/shutdown`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            errorPrefix: '关闭失败'
        });
        if (data.success) {
            showToast('服务正在关闭...', 'info');
        }
    } catch (e) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-power-off"></i> 关闭服务';
    }
}

async function clearGpuCache() {
    try {
        const data = await apiRequest(`${API_BASE_URL}/api/clear-gpu-cache`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            errorPrefix: '清理失败'
        });
        if (data.success) {
            showToast(`GPU缓存清理成功！释放显存: ${data.freed}`, 'success');
            refreshResources();
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    }
}

async function refreshResources() {
    try {
        const data = await apiRequest(`${API_BASE_URL}/api/resources`, { silent: true });
        updateResourceDisplay(data);
    } catch (e) {
        // 静默轮询
    }
}

function updateResourceDisplay(resources) {
    if (!resources) return;

    const cpuPercentEl = document.getElementById('cpuPercent');
    const cpuBarEl = document.getElementById('cpuBar');
    const memoryPercentEl = document.getElementById('memoryPercent');
    const memoryBarEl = document.getElementById('memoryBar');
    const memoryDetailEl = document.getElementById('memoryDetail');
    const diskPercentEl = document.getElementById('diskPercent');
    const diskBarEl = document.getElementById('diskBar');
    const gpuSectionEl = document.getElementById('gpuSection');
    const gpuPercentEl = document.getElementById('gpuPercent');
    const gpuBarEl = document.getElementById('gpuBar');
    const gpuNameEl = document.getElementById('gpuName');

    function pct(value) {
        if (value === undefined || value === null) return 0;
        const num = Number(value);
        if (!isFinite(num) || isNaN(num)) return 0;
        return Math.max(0, Math.min(100, num));
    }

    function pctText(value) {
        return Math.round(pct(value)) + '%';
    }

    function pctWidth(value) {
        return pct(value) + '%';
    }

    if (resources.cpu) {
        const cpuPct = pct(resources.cpu.percent);
        if (cpuPercentEl) cpuPercentEl.textContent = Math.round(cpuPct) + '%';
        if (cpuBarEl) cpuBarEl.style.width = cpuPct + '%';
    }
    if (resources.memory) {
        // 用同一个计算结果保证进度条宽度和百分比文本完全一致
        const memPctNum = pct(resources.memory.percent);
        const memPctText = Math.round(memPctNum) + '%';
        const memPctWidth = memPctNum + '%';
        if (memoryPercentEl) memoryPercentEl.textContent = memPctText;
        if (memoryBarEl) memoryBarEl.style.width = memPctWidth;
        if (memoryDetailEl) {
            memoryDetailEl.textContent = `${resources.memory.used || '--'} / ${resources.memory.total || '--'}`;
        }
    }

    if (resources.disk) {
        const diskPct = pct(resources.disk.percent);
        if (diskPercentEl) diskPercentEl.textContent = Math.round(diskPct) + '%';
        if (diskBarEl) diskBarEl.style.width = diskPct + '%';
    }

    const gpu = resources.gpu;
    if (gpu && gpu.available) {
        if (gpuSectionEl) gpuSectionEl.style.display = 'flex';
        const gpuPct = pct(gpu.memory_percent);
        if (gpuPercentEl) gpuPercentEl.textContent = Math.round(gpuPct) + '%';
        if (gpuBarEl) gpuBarEl.style.width = gpuPct + '%';
        if (gpuNameEl) gpuNameEl.textContent = gpu.name || '';
    } else {
        if (gpuSectionEl) gpuSectionEl.style.display = 'none';
        if (gpuNameEl) gpuNameEl.textContent = '';
    }
}