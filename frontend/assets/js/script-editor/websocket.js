function connectWebSocket() {
    if (!state.scriptId) return;
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    state.wsShouldReconnect = true;
    updateWsStatus('connecting');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/books/scripts/ws?script_id=${state.scriptId}`;
    try {
        state.ws = new WebSocket(wsUrl);
    } catch (e) {
        console.error('WebSocket 创建失败:', e);
        scheduleReconnect();
        return;
    }
    state.ws.onopen = () => {
        console.log('[WS] 连接已建立');
        updateWsStatus('connected');
        state.wsReconnectDelay = 2000;
        if (state.scriptData && state.scriptData.status === 'running') {
            loadCharacters();
        }
    };
    state.ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWsMessage(msg);
        } catch (e) {
            console.error('[WS] 消息解析失败:', e);
        }
    };
    state.ws.onerror = (error) => {
        console.error('[WS] 连接错误:', error);
        updateWsStatus('disconnected');
    };
    state.ws.onclose = (event) => {
        console.log('[WS] 连接关闭, code:', event.code, 'reason:', event.reason);
        updateWsStatus('disconnected');
        if (state.wsShouldReconnect) {
            scheduleReconnect();
        }
    };
}

function scheduleReconnect() {
    if (state.wsReconnectTimer) return;
    updateWsStatus('connecting');
    state.wsReconnectTimer = setTimeout(() => {
        state.wsReconnectTimer = null;
        if (state.wsShouldReconnect) {
            console.log('[WS] 尝试重连...');
            connectWebSocket();
            state.wsReconnectDelay = Math.min(state.wsReconnectDelay * 2, state.wsMaxReconnectDelay);
        }
    }, state.wsReconnectDelay);
}

function closeWebSocket() {
    state.wsShouldReconnect = false;
    if (state.wsReconnectTimer) {
        clearTimeout(state.wsReconnectTimer);
        state.wsReconnectTimer = null;
    }
    if (state.ws) {
        try {
            state.ws.close();
        } catch (e) {}
        state.ws = null;
    }
    updateWsStatus('disconnected');
}

function handleWsMessage(msg) {
    const type = msg.type || msg.event;
    switch (type) {
        case 'status':
            handleStatusMessage(msg);
            break;
        case 'lines_added':
            handleLinesAddedMessage(msg);
            break;
        case 'characters_updated':
            handleCharactersUpdatedMessage(msg);
            break;
        case 'finish':
            handleFinishMessage(msg);
            break;
        case 'error':
            handleErrorMessage(msg);
            break;
        case 'audio_generated':
            handleAudioGeneratedMessage(msg);
            break;
        case 'line_generating':
            handleLineGeneratingMessage(msg);
            break;
        case 'line_generated':
            handleLineGeneratedMessage(msg);
            break;
        case 'continue_task_update':
            handleContinueTaskUpdateMessage(msg);
            break;
        case 'chapter_applied':
            handleChapterAppliedMessage(msg);
            break;
        case 'apply_task_update':
            handleApplyTaskUpdate(msg);
            break;
        case 'init_progress':
            handleInitProgressMessage(msg);
            break;
        case 'chapter_plans_generated':
            handleChapterPlansGeneratedMessage(msg);
            break;
        case 'reindex_progress':
            handleReindexProgressMessage(msg);
            break;
        case 'script_progress':
            handleScriptProgressMessage(msg);
            break;
        case 'pong':
            break;
        default:
            console.log('[WS] 未知消息类型:', type, msg);
    }
}

function handleContinueTaskUpdateMessage(msg) {
    if (typeof window.handleContinueTaskUpdate === 'function') {
        window.handleContinueTaskUpdate(msg.status);
    }
}

function handleChapterAppliedMessage(msg) {
    const { chapter_index: chapterIndex, title, content } = msg;
    console.log(`[WS] 收到章节应用通知: 第${chapterIndex}章 ${title}`);

    // 1. 更新 state.chapters（新增或更新章节）
    const existingIdx = state.chapters.findIndex(c => c.chapter_index === chapterIndex);
    if (existingIdx >= 0) {
        state.chapters[existingIdx].chapter_title = title;
    } else {
        state.chapters.push({
            chapter_index: chapterIndex,
            chapter_title: title,
            line_count: 0,
            has_lines: false,
        });
        // 按 chapter_index 升序排列，保持与 renderChapterList 渲染顺序一致
        state.chapters.sort((a, b) => a.chapter_index - b.chapter_index);
    }

    // 2. 更新章节计数
    if (state.scriptData) {
        state.scriptData.chapter_count = state.chapters.length;
    }

    // 3. 重绘章节列表（从 state.chapters 构建 DOM，编辑/删除按钮自动保留）
    if (typeof renderChapterList === 'function') {
        renderChapterList();
    }

    // 4. 切换当前章节高亮
    state.currentChapterIndex = chapterIndex;
    document.querySelectorAll('.chapter-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.index) === chapterIndex);
    });

    // 5. 更新章节标题显示
    const titleEl = document.getElementById('currentChapterTitle');
    if (titleEl && title) {
        titleEl.textContent = title;
    }

    // 6. 更新原文内容（WS 消息已携带过滤后的正文，无需网络请求）
    const textarea = document.getElementById('originalTextBody');
    if (textarea) {
        textarea.value = content || '';
        textarea.dispatchEvent(new Event('input'));
    }

    // 7. 更新顶部元信息
    const metaEl = document.getElementById('scriptMeta');
    if (metaEl && state.scriptData) {
        metaEl.textContent =
            `${state.scriptData.chapter_count} 章 · ${state.scriptData.line_count || 0} 句 · ${state.scriptData.created_at_str || ''}`;
    }
    if (typeof updateClearButton === 'function') {
        updateClearButton();
    }

    // 8. 提示并关闭模态框
    if (typeof showToast === 'function') {
        showToast('创作结果已应用', 'success');
    }
    if (typeof closeContinueModal === 'function') {
        closeContinueModal();
    }
    if (typeof closeTasksModal === 'function') {
        closeTasksModal();
    }
}

function handleApplyTaskUpdate(msg) {
    const update = msg.update || {};
    const phase = update.phase;
    const message = update.message || '';
    const chapterIndex = update.chapter_index;

    console.log(`[WS] 应用任务更新: phase=${phase}, chapter=${chapterIndex}, msg=${message}`);

    switch (phase) {
        case 'started':
            // 设置应用状态（不锁编辑器，用户可能正在查看其他章节）
            state.applyingChapterIndex = chapterIndex;
            state.applyTaskId = update.task_id;
            // 显示横幅
            if (typeof showApplyBanner === 'function') showApplyBanner('正在应用创作结果...');
            // 刷新章节列表以显示处理中状态
            if (typeof renderChapterList === 'function') renderChapterList();
            break;

        case 'content_saved':
            // 章节已创建，刷新列表并切换到目标章节
            if (typeof loadScriptInfo === 'function') {
                loadScriptInfo().then(() => {
                    if (typeof selectChapter === 'function') selectChapter(chapterIndex);
                    // 切换后再锁定编辑器，此时编辑器显示的是目标章节
                    if (typeof setEditorReadonly === 'function') setEditorReadonly(true);
                    if (typeof renderChapterList === 'function') renderChapterList();
                });
            }
            if (typeof updateApplyBanner === 'function') updateApplyBanner('章节已保存，正在执行后处理...');
            break;

        case 'processing':
            // 更新横幅显示当前处理步骤
            if (typeof updateApplyBanner === 'function') updateApplyBanner(message);
            break;

        case 'completed':
            // 清除应用状态
            if (typeof clearApplyState === 'function') clearApplyState();
            // 刷新章节列表以获取最新状态
            if (typeof loadScriptInfo === 'function') {
                loadScriptInfo().then(() => {
                    if (typeof renderChapterList === 'function') renderChapterList();
                });
            }
            if (typeof showToast === 'function') showToast('应用完成', 'success');
            break;

        case 'failed':
            // 清除应用状态
            if (typeof clearApplyState === 'function') clearApplyState();
            // 刷新章节列表
            if (typeof loadScriptInfo === 'function') {
                loadScriptInfo().then(() => {
                    if (typeof renderChapterList === 'function') renderChapterList();
                });
            }
            // 显示错误提示
            const errorMsg = update.error || '应用失败';
            if (typeof showToast === 'function') showToast('应用失败: ' + errorMsg, 'error');
            break;
    }
}

async function handleAudioGeneratedMessage(msg) {
    const lineId = msg.line_id;
    console.log('[WS] 收到音频生成通知:', lineId);
    
    const line = state.currentLines.find(l => l.id === lineId);
    if (!line) {
        console.warn('[WS] 未找到对应的台词:', lineId);
        return;
    }

    // 如果流式响应已经设置了 audio_path，跳过重新匹配（避免竞态覆盖）
    if (!line.audio_path) {
        await matchAudioHistoryForLines([line]);
    }
    updateLineAudioEditorDisplay(lineId);
    updateAudioStatusDot(lineId, 'generated');
}

function handleLineGeneratingMessage(msg) {
    const lineId = msg.line_id;
    console.log('[WS] 收到台词生成中通知:', lineId);
    updateAudioStatusDot(lineId, 'generating');
}

function handleLineGeneratedMessage(msg) {
    const lineId = msg.line_id;
    console.log('[WS] 收到台词生成完成通知:', lineId);
    updateAudioStatusDot(lineId, 'generated');
}

function updateAudioStatusDot(lineId, status) {
    const dot = document.getElementById(`audioStatus-${lineId}`);
    if (dot) {
        dot.setAttribute('data-status', status);
    }
}

function startChapterGeneration(chapterIndex) {
    if (state.scriptData && state.scriptData.status === 'running') {
        showToast('剧本正在生成中，请稍后再试', 'warning');
        return;
    }
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
        showToast('WebSocket 未连接', 'warning');
        return;
    }
    state.generatingChapterIndex = chapterIndex;
    showGenerationProgress();
    const btn = document.getElementById('generateBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
    }
    state.ws.send(JSON.stringify({
        type: 'generate_chapter',
        chapter_index: chapterIndex
    }));
}

function handleScriptProgressMessage(msg) {
    // 守卫：如果生成已结束，忽略迟到的进度消息
    if (state.generatingChapterIndex === -1 && state.scriptData && state.scriptData.status === 'ready') {
        return;
    }
    const progress = msg.progress || 0;
    const message = msg.message || '';
    updateProgress(progress, message);
}

function handleStatusMessage(msg) {
    const status = msg.status;
    const progress = msg.progress;
    const message = msg.message;
    const chapterIndex = msg.chapter_index;
    if (status) {
        updateStatusBadge(status);
        if (state.scriptData) {
            state.scriptData.status = status;
        }
        if (status === 'running' && chapterIndex !== undefined && chapterIndex !== null) {
            state.generatingChapterIndex = chapterIndex;
            showGenerationProgress();
        } else if (status === 'running') {
            showGenerationProgress();
        } else if (status === 'ready') {
            state.generatingChapterIndex = -1;
            hideGenerationProgress();
        }
        // 初始化中状态：展示任务遮罩
        if (status === 'initializing' && typeof showInitTaskMask === 'function') {
            showInitTaskMask(message || '深度初始化中...');
        }
    }
    if (typeof progress === 'number') {
        updateProgress(progress, message);
    }
}

function handleLinesAddedMessage(msg) {
    const lines = msg.lines || [];
    if (lines.length === 0) return;
    let chapterIndex = msg.chapter_index;
    if (chapterIndex === undefined || chapterIndex === null) {
        chapterIndex = lines[0].chapter_index;
    }
    const chapter = state.chapters.find(c => c.chapter_index === chapterIndex);
    if (chapter) {
        chapter.line_count = (chapter.line_count || 0) + lines.length;
        chapter.has_lines = true;
        renderChapterList();
        if (chapterIndex === state.currentChapterIndex) {
            updateClearButton();
        }
    } else {
        loadScriptInfo();
    }
    if (state.scriptData) {
        state.scriptData.line_count = (state.scriptData.line_count || 0) + lines.length;
        document.getElementById('scriptMeta').textContent =
            `${state.scriptData.chapter_count} 章 · ${state.scriptData.line_count} 句 · ${state.scriptData.created_at_str || ''}`;
    }
    if (chapterIndex === state.currentChapterIndex) {
        appendLines(lines);
    }
}

function handleCharactersUpdatedMessage(msg) {
    const updated = msg.characters || [];
    if (updated.length === 0) return;
    const newRoles = [];
    let changed = false;
    updated.forEach(ch => {
        const role = ch.role;
        if (!role) return;
        const existing = state.characters.find(c => c.role === role);
        if (existing) {
            if (existing.line_count !== ch.line_count) {
                existing.line_count = ch.line_count;
                changed = true;
            }
        } else {
            state.characters.push({
                role: role,
                line_count: ch.line_count || 0,
                agent_id: '',
                speed: 1.0,
                seed: 0,
            });
            state.characterVoiceMap[role] = { agent_id: '', speed: 1.0, seed: 0 };
            newRoles.push(role);
            changed = true;
        }
    });
    if (!changed) return;
    renderCharacters();
    refreshRoleSelects(newRoles.length > 0 ? newRoles : null);
    if (state.selectedRole) {
        renderCharacterSettings();
    }
    if (newRoles.length > 0) {
        showToast(`发现 ${newRoles.length} 个新角色: ${newRoles.join('、')}`, 'info');
    }
}

function appendLines(newLines) {
    const listEl = document.getElementById('linesList');
    if (state.currentLines.length === 0 && listEl.querySelector('.loading-state')) {
        listEl.innerHTML = '';
    }
    const existingLoading = listEl.querySelector('.generation-loading');
    if (existingLoading) {
        existingLoading.remove();
    }
    newLines.forEach((line) => {
        state.currentLines.push(line);
        const idx = state.currentLines.length - 1;
        const div = buildLineElement(line, idx);
        div.style.opacity = '0';
        div.style.transform = 'translateY(-10px)';
        div.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        listEl.appendChild(div);
        requestAnimationFrame(() => {
            div.style.opacity = '1';
            div.style.transform = 'translateY(0)';
        });
    });
    if (state.scriptData && state.scriptData.status === 'running' && (state.generatingChapterIndex === -1 || state.generatingChapterIndex === state.currentChapterIndex)) {
        listEl.appendChild(createLinePlaceholder());
    }
    updatePlayerButtons();
    const shouldScroll = listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 100;
    if (shouldScroll) {
        listEl.scrollTop = listEl.scrollHeight;
    }
}

function handleFinishMessage(msg) {
    state.generatingChapterIndex = -1;
    updateStatusBadge('ready');
    hideGenerationProgress();
    if (state.scriptData) {
        state.scriptData.status = 'ready';
    }
    const listEl = document.getElementById('linesList');
    const loadingDiv = listEl.querySelector('.generation-loading');
    if (loadingDiv) {
        loadingDiv.remove();
    }
    loadScriptInfo();
    loadCharacters();
    const scope = msg.scope || '';
    if (scope === 'chapter') {
        showToast('本章台词生成完成', 'success');
    } else {
        showToast('生成全部台词完成', 'success');
    }
}

function handleErrorMessage(msg) {
    const errorMsg = msg.message || msg.error || '生成失败';
    if (errorMsg === '剧本不存在') {
        console.warn('[WS] 剧本不存在，停止重连');
        state.wsShouldReconnect = false;
        showError('剧本不存在');
        return;
    }
    updateStatusBadge('failed');
    hideGenerationProgress();
    if (state.scriptData) {
        state.scriptData.status = 'failed';
    }
    // 永久性失败（剧本状态为failed）：停止重连，避免后端关闭→前端重连→后端再关闭的死循环
    if (msg.permanent_failure) {
        console.warn('[WS] 检测到永久性失败，停止重连');
        state.wsShouldReconnect = false;
        if (state.wsReconnectTimer) {
            clearTimeout(state.wsReconnectTimer);
            state.wsReconnectTimer = null;
        }
    }
    showToast(errorMsg, 'error');
}

function handleChapterPlansGeneratedMessage(msg) {
    const { outline_id: outlineId, success, message, plan_count: planCount } = msg;
    console.log(`[WS] 智能拆章完成: success=${success}, planCount=${planCount}, message=${message}`);

    // 清除拆章进行中标记
    if (typeof _splitChapterInProgress !== 'undefined') {
        _splitChapterInProgress = false;
    }

    if (typeof showToast === 'function') {
        showToast(message, success ? 'success' : 'error');
    }

    if (success) {
        // 清除缓存并刷新右栏
        if (state.volumeChapterPlans) delete state.volumeChapterPlans[outlineId];
        if (typeof renderOutlineDetailPanel === 'function') {
            renderOutlineDetailPanel(outlineId);
        }
        if (typeof loadWebnovelOutline === 'function') {
            loadWebnovelOutline();
        }
    }

    // 同步刷新全局任务列表（若任务管理面板已打开则实时更新状态）
    if (typeof refreshTasks === 'function') {
        refreshTasks();
    }
}

function handleReindexProgressMessage(msg) {
    if (typeof window.handleReindexProgress === 'function') {
        window.handleReindexProgress(msg);
    }
}