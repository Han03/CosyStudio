// 追踪当前是否有运行中的创作任务，用于控制"重新创作"按钮显隐
let _continueHasRunningTask = false;

async function showContinueModal() {
    document.getElementById('continueModal').style.display = 'flex';
    await populateContinueChapterSelector();
    document.getElementById('continuePrompt').value = '';
    const polishCheckbox = document.getElementById('continueEnablePolish');
    if (polishCheckbox) polishCheckbox.checked = true;
    const autoApplyCheckbox = document.getElementById('continueAutoApply');
    if (autoApplyCheckbox) autoApplyCheckbox.checked = true;
    state.continueTaskId = null;
    state.continueTargetChapter = null;
    state.continueResultText = null;
    _continueHasRunningTask = false;
    const resultPreview = document.getElementById('continueResultPreview');
    if (resultPreview) resultPreview.innerHTML = '';
    const applyBtn = document.getElementById('continueApplyBtn');
    if (applyBtn) applyBtn.style.display = 'none';
    const recreateBtn = document.getElementById('continueRecreateBtn');
    if (recreateBtn) recreateBtn.style.display = 'none';
    const statusEl = document.getElementById('continueTaskStatus');
    if (statusEl) statusEl.innerHTML = '';
    document.getElementById('continueInstructions').style.display = 'block';
    document.getElementById('continueProgressContainer').style.display = 'none';

    // 查询最新任务：已完成则展示结果，运行中则提示进度在外部查看
    const hasTask = await restoreLatestContinueTask();
    // 仅在无活跃任务时按当前选中章节查询（有任务时 restoreLatestContinueTask 已处理）
    if (!hasTask) {
        await onContinueChapterSelectionChanged();
    }
}

async function restoreLatestContinueTask() {
    if (!state.scriptId) return false;
    try {
        const data = await apiRequest(`/api/books/scripts/chapters/continue/latest?script_id=${state.scriptId}`, { silent: true });
        if (!data.success || !data.task) return false;

        const task = data.task;
        state.continueTaskId = task.id;
        state.continueTargetChapter = task.chapter_index;

        if (task.status === 'running') {
            _continueHasRunningTask = true;
            // 任务正在运行：进度由编辑器顶部的工作流进度条展示
            document.getElementById('continueStartBtn').style.display = 'none';
            document.getElementById('continueCancelBtn').style.display = 'block';
            document.getElementById('continueInstructions').style.display = 'none';
            document.getElementById('continueProgressContainer').style.display = 'block';
            const statusEl = document.getElementById('continueTaskStatus');
            if (statusEl) {
                statusEl.className = 'continue-task-status running';
                statusEl.innerHTML = '<strong>创作进行中</strong><br>请关闭此窗口，通过编辑器顶部的创作流程进度条查看实时进度。';
            }
            return true;
        } else if (task.status === 'completed') {
            // 任务已完成，选中该章节并展示结果预览
            await selectContinueChapter(task.chapter_index);
            return true;
        } else if (task.status === 'failed') {
            // 失败任务：清除 taskId 以便用户可直接重新开始
            state.continueTaskId = null;
            document.getElementById('continueProgressContainer').style.display = 'block';
            const statusEl = document.getElementById('continueTaskStatus');
            if (statusEl) {
                statusEl.className = 'continue-task-status failed';
                statusEl.innerHTML = `<strong>上次创作失败</strong><br>${task.error_message || '未知错误'}`;
            }
            return true;
        } else if (task.status === 'cancelled') {
            // 已取消任务：清除 taskId 以便用户可直接重新开始
            state.continueTaskId = null;
            document.getElementById('continueProgressContainer').style.display = 'block';
            const statusEl = document.getElementById('continueTaskStatus');
            if (statusEl) {
                statusEl.className = 'continue-task-status cancelled';
                statusEl.innerHTML = '<strong>上次创作已取消</strong>';
            }
            return true;
        }
    } catch (e) {
        console.error('恢复创作任务失败:', e);
    }
    return false;
}

/**
 * 页面加载时恢复运行中创作任务的流程进度条。
 * 仅设置 state.continueTaskId 并渲染编辑器顶部进度条，不涉及模态框 UI。
 */
async function restoreWorkflowProgressBar() {
    if (!state.scriptId) return;
    try {
        const data = await apiRequest(`/api/books/scripts/chapters/continue/latest?script_id=${state.scriptId}`, { silent: true });
        if (!data.success || !data.task) return;

        const task = data.task;
        if (task.status !== 'running') return;

        // 设置 taskId，使后续 WebSocket 的 handleContinueTaskUpdate 能正常匹配
        state.continueTaskId = task.id;
        state.continueTargetChapter = task.chapter_index;

        // 显示并渲染创作流程进度条
        // step_result 存储的是干净的步骤名称（如"初始化"），current_step 存储的是带后缀的消息
        const stepName = task.step_result || task.current_step || '';
        updateWorkflowProgress(stepName, 'running');
    } catch (e) {
        console.error('恢复创作进度条失败:', e);
    }
}

function closeContinueModal() {
    document.getElementById('continueModal').style.display = 'none';
    // 不隐藏工作流进度条：任务运行中时进度条需在编辑器顶部持续展示
}

async function populateContinueChapterSelector() {
    const listEl = document.getElementById('chapterSelectorList');
    listEl.innerHTML = '<div class="chapter-selector-loading"><i class="fas fa-spinner fa-spin"></i> 加载章节规划...</div>';
    // 重置选中状态为“自动追加”
    state.selectedContinueChapter = null;
    updateContinueAutoHighlight();

    if (!state.scriptId) {
        listEl.innerHTML = '<div class="chapter-selector-empty">未加载剧本</div>';
        return;
    }

    try {
        const data = await apiRequest(`/api/books/scripts/chapter-plans/all?script_id=${state.scriptId}`, { silent: true });
        if (!data.success || !data.volumes || data.volumes.length === 0) {
            listEl.innerHTML = '<div class="chapter-selector-empty"><i class="fas fa-info-circle"></i> 暂无章节规划<br><span style="font-size:11px;margin-top:4px;display:inline-block;">请先通过大纲规划生成章节</span></div>';
            return;
        }

        // 缓存全部章节规划数据供搜索过滤使用
        state.chapterPlanSelectorData = data.volumes;
        renderChapterSelectorList(data.volumes);
    } catch (e) {
        console.error('加载章节规划失败:', e);
        listEl.innerHTML = '<div class="chapter-selector-empty">加载失败</div>';
    }
}

function renderChapterSelectorList(volumes) {
    const listEl = document.getElementById('chapterSelectorList');
    let html = '';
    for (const vol of volumes) {
        const plans = vol.chapter_plans || [];
        if (plans.length === 0) continue;
        html += `<div class="chapter-selector-volume" data-volume="${vol.volume_id}">第${vol.volume_number}卷 ${vol.volume_name || ''}（第${vol.chapter_start}-${vol.chapter_end}章）</div>`;
        for (const plan of plans) {
            const selected = state.selectedContinueChapter === plan.chapter_index;
            const summary = (plan.summary || '').substring(0, 60);
            const statusHtml = plan.has_result
                ? '<span class="chapter-selector-item-status completed">已创作</span>'
                : '';
            html += `
                <div class="chapter-selector-item ${selected ? 'selected' : ''}" data-chapter="${plan.chapter_index}" onclick="selectContinueChapter(${plan.chapter_index})">
                    <div class="chapter-selector-item-info">
                        <div class="chapter-selector-item-title">第${plan.chapter_index}章 ${escapeHtml(plan.chapter_title || '未命名')}</div>
                        ${summary ? `<div class="chapter-selector-item-summary">${escapeHtml(summary)}</div>` : ''}
                    </div>
                    ${statusHtml}
                </div>
            `;
        }
    }
    if (!html) {
        listEl.innerHTML = '<div class="chapter-selector-empty">暂无章节规划</div>';
        return;
    }
    listEl.innerHTML = html;
}

async function selectContinueChapter(chapterIndex) {
    state.selectedContinueChapter = chapterIndex; // null = 自动追加, number = 具体章节
    // 更新自动追加高亮
    updateContinueAutoHighlight();
    // 更新章节列表项高亮
    document.querySelectorAll('.chapter-selector-item').forEach(el => {
        el.classList.toggle('selected', parseInt(el.dataset.chapter) === chapterIndex);
    });
    // 触发变更（await 避免竞态）
    await onContinueChapterSelectionChanged();
}

function updateContinueAutoHighlight() {
    const autoEl = document.querySelector('.chapter-selector-auto');
    if (autoEl) {
        autoEl.classList.toggle('selected', state.selectedContinueChapter === null || state.selectedContinueChapter === undefined);
    }
}

function filterChapterSelector() {
    const query = document.getElementById('chapterSelectorSearch').value.trim().toLowerCase();
    if (!state.chapterPlanSelectorData) return;

    if (!query) {
        renderChapterSelectorList(state.chapterPlanSelectorData);
        return;
    }

    // 过滤：匹配章节号、标题、概要
    const filtered = state.chapterPlanSelectorData.map(vol => ({
        ...vol,
        chapter_plans: (vol.chapter_plans || []).filter(plan => {
            const idxStr = String(plan.chapter_index);
            const title = (plan.chapter_title || '').toLowerCase();
            const summary = (plan.summary || '').toLowerCase();
            return idxStr.includes(query) || title.includes(query) || summary.includes(query);
        })
    })).filter(vol => vol.chapter_plans.length > 0);

    renderChapterSelectorList(filtered);
}

async function onContinueChapterSelectionChanged() {
    const chapterIndex = state.selectedContinueChapter;
    const startBtn = document.getElementById('continueStartBtn');
    const applyBtn = document.getElementById('continueApplyBtn');
    const resultPreview = document.getElementById('continueResultPreview');
    const statusEl = document.getElementById('continueTaskStatus');

    // 如果当前有运行中的任务，不干扰
    //if (state.continueTaskId && !state.continueResultText) return;

    if (chapterIndex === null || chapterIndex === undefined) {
        // "自动追加章节" —— 显示开始创作按钮，隐藏结果
        startBtn.style.display = 'block';
        applyBtn.style.display = 'none';
        resultPreview.innerHTML = '';
        statusEl.innerHTML = '';
        state.continueResultText = null;
        state.continueTargetChapter = null;
        document.getElementById('continueProgressContainer').style.display = 'none';
        resetContinueModal();
    } else {
        // 按需查询该章节的创作结果
        try {
            const data = await apiRequest(`/api/books/scripts/chapters/continue/results?script_id=${state.scriptId}&chapter_index=${chapterIndex}`, { silent: true });
            const result = data.success ? data.result : null;

            if (result && (result.polished || result.draft)) {
                const content = result.polished || result.draft;
                state.continueResultText = content;
                state.continueTargetChapter = chapterIndex;
                startBtn.style.display = 'none';
                applyBtn.style.display = 'block';
                document.getElementById('continueInstructions').style.display = 'none';
                document.getElementById('continueProgressContainer').style.display = 'block';

                // 有 completed 任务且无 running 任务时显示"重新创作"按钮
                const showRecreate = !_continueHasRunningTask;
                const recreateBtn = document.getElementById('continueRecreateBtn');
                if (recreateBtn) recreateBtn.style.display = showRecreate ? 'inline-block' : 'none';
                applyBtn.textContent = '应用结果';
                applyBtn.className = 'btn btn-primary';

                resultPreview.innerHTML = `
                    <div class="continue-result-header">
                        <strong>第${chapterIndex}章 创作结果预览</strong>
                        <span style="font-size:12px; color:var(--neu-text-muted); margin-left:8px;">${content.length} 字</span>
                    </div>
                    <div class="continue-result-content">${escapeHtml(content).replace(/\n/g, '<br>')}</div>
                `;
                statusEl.className = 'continue-task-status completed';
                statusEl.innerHTML = result.chapter_has_content
                    ? `<strong>该章节已应用创作结果</strong><br>点击"重新创作"将重新生成并覆盖，或点击"应用结果"再次应用当前结果。`
                    : `<strong>已有创作结果</strong><br>点击"应用结果"将覆盖当前章节内容。`;
            } else {
                // 该章节未创作 —— 显示开始创作按钮
                startBtn.style.display = 'block';
                applyBtn.style.display = 'none';
                resultPreview.innerHTML = '';
                statusEl.innerHTML = '';
                state.continueResultText = null;
                state.continueTargetChapter = null;
                document.getElementById('continueProgressContainer').style.display = 'none';
                resetContinueModal();
            }
        } catch (e) {
            console.error('查询章节创作结果失败:', e);
            startBtn.style.display = 'block';
            applyBtn.style.display = 'none';
            const recreateBtn = document.getElementById('continueRecreateBtn');
            if (recreateBtn) recreateBtn.style.display = 'none';
            resultPreview.innerHTML = '';
            statusEl.innerHTML = '';
            state.continueResultText = null;
            state.continueTargetChapter = null;
            document.getElementById('continueProgressContainer').style.display = 'none';
        }
    }
}

async function startContinue() {
    const prompt = document.getElementById('continuePrompt').value.trim();
    const selectedChapter = state.selectedContinueChapter;

    try {
        const enablePolish = document.getElementById('continueEnablePolish') ? document.getElementById('continueEnablePolish').checked : true;
        const autoApply = document.getElementById('continueAutoApply') ? document.getElementById('continueAutoApply').checked : false;
        const body = { prompt: prompt, enable_polish: enablePolish, auto_apply: autoApply };
        let url = `/api/books/scripts/chapters/continue?script_id=${state.scriptId}`;
        if (selectedChapter !== null && selectedChapter !== undefined) {
            url += `&chapter_index=${selectedChapter}`;
        }

        const data = await apiRequest(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            errorPrefix: '创建任务失败'
        });
        if (data.success && data.task_id) {
            state.continueTaskId = data.task_id;
            state.continueTargetChapter = data.chapter_index;
            _continueHasRunningTask = true;
            // 显示工作流进度条，关闭模态框，进度交由编辑器顶部展示
            // 重置所有步骤节点和连线状态，避免上次创作的残留状态，并立即激活第一步
            document.getElementById('workflowProgressBar').style.display = 'block';
            document.getElementById('workflowProgressStatus').textContent = '准备';
            document.querySelectorAll('.workflow-step').forEach((el, idx) => {
                el.className = idx === 0 ? 'workflow-step running' : 'workflow-step';
            });
            document.querySelectorAll('.workflow-step-line').forEach(el => {
                el.className = 'workflow-step-line';
            });
            // 刷新竞态缓冲：DOM 就绪后处理 HTTP 响应到达前积累的 WS 消息
            _flushPendingTaskUpdates();
            showToast(`创作任务已启动，目标: 第${data.chapter_index}章`, 'success');
            document.getElementById('continueModal').style.display = 'none';
        } else {
            showToast(data.error || '创作任务创建失败', 'error');
            resetContinueModal();
        }
    } catch (e) {
        console.error('开始创作失败:', e);
        showToast('创建任务失败', 'error');
        resetContinueModal();
    }
}

// 缓冲队列：解决 startContinue() 发起 HTTP 请求后、HTTP 响应到达前，
// WS 通知先于到达导致消息被静默丢弃的竞态问题
let _pendingTaskUpdates = [];

function handleContinueTaskUpdate(status) {
    // 竞态缓冲：taskId 尚未确认时（HTTP 响应未返回），缓存 running 状态消息而非丢弃
    // 仅缓冲 running 消息，防止任务结束后残留的终态消息被误缓存
    if (!state.continueTaskId) {
        if (status.status === 'running') {
            _pendingTaskUpdates.push(status);
        }
        return;
    }
    if (status.id !== state.continueTaskId) {
        return;
    }

    _processTaskUpdate(status);
}

/** 处理单条任务状态更新（实际渲染逻辑） */
function _processTaskUpdate(status) {
    // 所有进度通过编辑器顶部的创作流程进度条展示
    updateWorkflowProgress(status.step_name || '', status.status || '');

    if (status.status === 'completed') {
        state.continueResultText = status.polished || status.draft || '';
        showContinueComplete(status);
    } else if (status.status === 'failed') {
        showContinueFailed(status);
    } else if (status.status === 'cancelled') {
        showContinueCancelled(status);
    }
}

/** 刷新缓冲的 WS 消息队列，在 continueTaskId 确认后调用 */
function _flushPendingTaskUpdates() {
    if (_pendingTaskUpdates.length > 0) {
        const pending = _pendingTaskUpdates;
        _pendingTaskUpdates = [];
        console.log(`[WS] 刷新 ${pending.length} 条缓冲的创作任务更新`);
        for (const s of pending) {
            _processTaskUpdate(s);
        }
    }
}

function updateWorkflowProgress(stepName, taskStatus) {
    const progressBar = document.getElementById('workflowProgressBar');
    if (!progressBar) return;

    // 后端 step_name → { 步骤编号, 显示文案 }
    // 多个后端步骤可映射到同一个前端显示节点
    const stepConfig = {
        // 节点1: 准备（初始化 + 上下文及以前的全部节点）
        '初始化':           { num: 1,  label: '准备' },
        '大纲准备':         { num: 1,  label: '准备' },
        '章节规划':         { num: 1,  label: '准备' },
        '拆章规划':         { num: 1,  label: '准备' },
        '时间线修补':       { num: 1,  label: '准备' },
        '设定记录':         { num: 1,  label: '准备' },
        '上下文构建':       { num: 1,  label: '准备' },
        // 节点2: 剧情（剧情生成和审查）
        '剧情生成':         { num: 2,  label: '剧情' },
        '剧情审查':         { num: 2,  label: '剧情' },
        // 节点3: 草稿
        '草稿生成':         { num: 3,  label: '草稿' },
        // 节点4: 审查
        '草稿审查':         { num: 4,  label: '审查' },
        // 节点5: 润色
        '草稿润色':         { num: 5,  label: '润色' },
        // 节点6: 事实
        '事实记录':         { num: 6,  label: '事实' },
        // 节点7: 伏笔
        '伏笔和爽点提取':   { num: 7,  label: '伏笔' },
        // 节点8: 归档
        '任务归档':         { num: 8,  label: '归档' }
    };

    const cfg = stepConfig[stepName];
    const stepNum = cfg ? cfg.num : undefined;
    const statusEl = document.getElementById('workflowProgressStatus');

    if (taskStatus === 'completed') {
        progressBar.style.display = 'none';
        return;
    }

    if (taskStatus === 'failed') {
        statusEl.textContent = '任务失败';
        return;
    }

    if (stepNum) {
        progressBar.style.display = 'block';
        statusEl.textContent = cfg.label;

        document.querySelectorAll('.workflow-step').forEach((el, idx) => {
            const stepIndex = idx + 1;
            if (stepIndex < stepNum) {
                el.className = 'workflow-step completed';
            } else if (stepIndex === stepNum) {
                el.className = 'workflow-step running';
            } else {
                el.className = 'workflow-step';
            }
        });

        document.querySelectorAll('.workflow-step-line').forEach((el, idx) => {
            if (idx < stepNum - 1) {
                el.className = 'workflow-step-line completed';
            } else {
                el.className = 'workflow-step-line';
            }
        });
    } else if (taskStatus === 'running') {
        progressBar.style.display = 'block';
        statusEl.textContent = '初始化任务...';
    }
}

async function showContinueComplete(status) {
    state.continueResultText = status.polished || status.draft || '';
    state.continueTaskId = null;
    _continueHasRunningTask = false;
    _pendingTaskUpdates = []; // 清除缓冲队列，防止残留消息干扰下次创作
    showToast(`创作完成！已生成 ${status.polished ? status.polished.length : 0} 字`, 'success');

    // 重置模态框按钮状态：隐藏取消按钮，恢复开始创作按钮
    document.getElementById('continueCancelBtn').style.display = 'none';
    document.getElementById('continueStartBtn').style.display = 'block';
    document.getElementById('continueApplyBtn').style.display = 'none';
    const recreateBtn = document.getElementById('continueRecreateBtn');
    if (recreateBtn) recreateBtn.style.display = 'none';
    document.getElementById('continueProgressContainer').style.display = 'none';
    document.getElementById('continueInstructions').style.display = 'block';

    // 刷新章节列表，反映新创作的章节
    if (typeof loadScriptInfo === 'function') {
        await loadScriptInfo();
        renderChapterList();
    }
}

function showContinueFailed(status) {
    _continueHasRunningTask = false;
    showToast('创作失败: ' + (status.error_message || '未知错误'), 'error');
}

function showContinueCancelled(status) {
    _continueHasRunningTask = false;
    showToast('创作已取消', 'warning');
}

async function applyContinueResult() {
    const chapterIndex = state.continueTargetChapter;
    const taskId = state.continueTaskId;

    if (chapterIndex === null || chapterIndex === undefined) {
        showToast('未确定目标章节', 'warning');
        return;
    }
    if (!taskId) {
        showToast('未找到创作任务ID', 'warning');
        return;
    }

    try {
        const data = await apiRequest(`/api/books/scripts/chapters/continue/apply?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId, chapter_index: chapterIndex }),
            errorPrefix: '应用失败'
        });
        if (!data.success) {
            showToast(data.detail || data.error || '应用失败', 'error');
            return;
        }
        // 后续 UI 更新由 WebSocket chapter_applied 消息驱动，
        // 此处仅显示“应用中”提示，避免前端重复执行章节创建/内容写入
        showToast('正在应用创作结果...', 'info');
    } catch (e) {
        console.error('应用创作结果失败:', e);
        showToast('应用失败: ' + e.message, 'error');
    }
}

function resetContinueModal() {
    document.getElementById('continueStartBtn').style.display = 'block';
    document.getElementById('continueInstructions').style.display = 'block';
    document.getElementById('continueCancelBtn').style.display = 'none';
    const recreateBtn = document.getElementById('continueRecreateBtn');
    if (recreateBtn) recreateBtn.style.display = 'none';
    document.getElementById('continueTaskStatus').innerHTML = '';
    state.continueTaskId = null;
}

async function insertContinueResult(content) {
    const textarea = document.getElementById('originalTextBody');
    if (textarea) {
        textarea.value += '\n\n' + content;
        textarea.dispatchEvent(new Event('input'));
        await saveChapterContent();
    } else {
        console.error('未找到章节内容输入框');
    }
}

async function cancelContinue() {
    if (!state.continueTaskId) return;

    try {
        await apiRequest(`/api/books/scripts/chapters/continue/cancel?script_id=${state.scriptId}&task_id=${state.continueTaskId}`, {
            method: 'POST',
            silent: true
        });
        showToast('创作任务已取消', 'warning');
        document.getElementById('continueModal').style.display = 'none';
        document.getElementById('workflowProgressBar').style.display = 'none';
        state.continueTaskId = null;
    } catch (e) {
        console.error('取消任务失败:', e);
    }
}

function showRagModal() {
    document.getElementById('ragModal').style.display = 'flex';
}

function closeRagModal() {
    document.getElementById('ragModal').style.display = 'none';
}

async function searchRag() {
    const query = document.getElementById('ragSearchInput').value.trim();
    if (!query || !state.scriptId) return;

    try {
        const data = await apiRequest(`/api/books/scripts/rag/search?script_id=${state.scriptId}&query=${encodeURIComponent(query)}&limit=10`, { silent: true });
        renderRagResults(data.chunks || []);
    } catch (e) {
        console.error('RAG检索失败:', e);
    }
}

function renderRagResults(chunks) {
    const container = document.getElementById('ragResultsList');
    if (chunks.length === 0) {
        container.innerHTML = `
            <div class="rag-empty">
                <i class="fas fa-search"></i>
                <p>未找到相关内容</p>
            </div>
        `;
        return;
    }

    const typeLabels = {
        'character': '角色', 'worldview': '世界观', 'power_system': '力量体系',
        'golden_finger': '金手指', 'volume_outline': '卷纲', 'foreshadow': '伏笔',
        'villain': '反派', 'chapter': '章节', 'chapter_paragraph': '章节原文'
    };

    container.innerHTML = chunks.map(chunk => {
        const typeLabel = typeLabels[chunk.chunk_type] || chunk.chunk_type || '未知';
        const chapterInfo = chunk.chapter_number ? ` · 第${chunk.chapter_number}章` : '';
        return `
        <div class="rag-result-card">
            <div class="rag-result-header">
                <span class="rag-result-source">${typeLabel}${chapterInfo}</span>
                <span class="rag-result-score">相似度: ${((chunk.score || 0) * 100).toFixed(1)}%</span>
            </div>
            <div class="rag-result-content">${escapeHtml(chunk.content || '')}</div>
        </div>
        `;
    }).join('');
}
