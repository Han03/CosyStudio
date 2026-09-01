function toggleChapterSidebar() {
    document.getElementById('chapterSidebar').classList.toggle('collapsed');
}

function toggleCharacterSidebar() {
    document.getElementById('audioSidebar').classList.toggle('collapsed');
}

async function regenerateScript() {
    if (!state.scriptData) return;
    if (state.scriptData.status === 'running') {
        showToast('剧本正在生成中，请稍后再试', 'warning');
        return;
    }
    if (!confirm(`确定重新生成《${state.scriptData.name}》的全部台词吗？\n当前所有台词将被删除并重新生成。`)) return;
    
    try {
        const data = await apiRequest(`/api/books/scripts/regenerate?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            errorPrefix: '生成失败'
        });
        if (data.success) {
            showToast('生成全部台词任务已启动', 'success');
            state.scriptData.status = 'running';
            updateStatusBadge('running');
            showGenerationProgress();
            state.currentLines = [];
            renderLines();
            await loadScriptInfo();
            connectWebSocket();
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    }
}

async function stopGeneration() {
    if (!state.scriptId) return;
    if (!confirm('确定停止生成吗？已生成的台词会保留。')) return;
    hideGenerationProgress();
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'stop_generation' }));
        showToast('生成已停止', 'info');
        updateStatusBadge('ready');
        if (state.scriptData) state.scriptData.status = 'ready';
        const listEl = document.getElementById('linesList');
        const loadingDiv = listEl.querySelector('.generation-loading');
        if (loadingDiv) loadingDiv.remove();
        updateGenerateButtons(false);
    } else {
        try {
            const data = await apiRequest(`/api/books/scripts/stop?script_id=${state.scriptId}`, {
                method: 'POST',
                errorPrefix: '停止失败'
            });
            if (data.success) {
                showToast('生成已停止', 'info');
                updateStatusBadge('ready');
                if (state.scriptData) state.scriptData.status = 'ready';
                const listEl = document.getElementById('linesList');
                const loadingDiv = listEl.querySelector('.generation-loading');
                if (loadingDiv) loadingDiv.remove();
                updateGenerateButtons(false);
                loadScriptInfo();
            }
        } catch (e) {
            // apiRequest 已弹出错误提示
        }
    }
}

function updateWsStatus(status) {
    const dot = document.getElementById('wsStatusDot');
    if (dot) {
        dot.className = `ws-status-dot ${status}`;
    }
}

function updateStatusBadge(status) {
    const badge = document.getElementById('statusBadge');
    const badgeText = document.getElementById('statusBadgeText');
    if (badge) {
        badge.className = `status-badge ${status}`;
        const labels = {
            'ready': '已就绪',
            'running': '生成中',
            'failed': '失败',
            'stopped': '已停止',
            'initializing': '初始化中',
            'pending': '待处理'
        };
        if (badgeText) {
            badgeText.textContent = labels[status] || status;
        } else {
            badge.textContent = labels[status] || status;
        }
    }
}

function updateProgress(percent, message) {
    const fill = document.getElementById('playerBarProgressFill');
    if (fill) fill.style.width = `${percent}%`;
}

function showGenerationProgress() {
    const container = document.getElementById('playerBarProgress');
    const fill = document.getElementById('playerBarProgressFill');
    const stopBtn = document.getElementById('stopGenBtn');
    if (container) container.style.display = 'block';
    if (fill) fill.style.width = '0%';
    if (stopBtn) stopBtn.style.display = 'flex';
}

function hideGenerationProgress() {
    const container = document.getElementById('playerBarProgress');
    const fill = document.getElementById('playerBarProgressFill');
    const stopBtn = document.getElementById('stopGenBtn');
    if (container) container.style.display = 'none';
    if (fill) fill.style.width = '0%';
    if (stopBtn) stopBtn.style.display = 'none';
}

function updateGenerateButtons(isGenerating) {
    const btn = document.getElementById('generateBtn');
    if (btn) {
        btn.disabled = isGenerating;
        btn.innerHTML = isGenerating ? '<i class="fas fa-spinner fa-spin"></i> 生成中...' : '<i class="fas fa-magic"></i> 生成台词';
    }
}

function closeInstructionQuickMenus() {
    document.querySelectorAll('.instruction-quick-dropdown').forEach(el => {
        el.style.display = 'none';
    });
}

function handleGlobalEvents() {
    document.addEventListener('keydown', (e) => {
        if (e.target.contentEditable === 'true' || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
        if (e.key === ' ') { e.preventDefault(); togglePlay(); }
        else if (e.key === 'ArrowLeft') playPrevLine();
        else if (e.key === 'ArrowRight') playNextLine();
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.instruction-quick-btn') && !e.target.closest('.instruction-quick-dropdown')) {
            closeInstructionQuickMenus();
        }
    });

    window.addEventListener('beforeunload', () => {
        closeWebSocket();
    });
}