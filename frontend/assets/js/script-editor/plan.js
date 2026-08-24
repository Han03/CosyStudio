// ========== 卷纲规划 ==========

function showPlanModal() {
    showOutlineModal();
}

function closePlanModal() {
    document.getElementById('outlineModal').style.display = 'none';
}

/** 显示内联 AI 规划表单（替代 prompt） */
function showInlinePlanForm() {
    const form = document.getElementById('inlinePlanForm');
    if (form) {
        form.style.display = 'block';
        const input = document.getElementById('inlinePlanVolumeNumber');
        if (input) {
            // 自动计算下一个卷号
            const existing = state.volumeOutlines || [];
            const nextNumber = existing.length > 0 ? Math.max(...existing.map(o => o.volume_number || 1)) + 1 : 1;
            input.value = nextNumber;
            input.focus();
            input.select();
        }
    }
}

/** 隐藏内联 AI 规划表单 */
function hideInlinePlanForm() {
    const form = document.getElementById('inlinePlanForm');
    if (form) form.style.display = 'none';
}

/** 内联表单发起 AI 规划 */
async function startVolumePlanInline() {
    const input = document.getElementById('inlinePlanVolumeNumber');
    const volumeNumber = parseInt(input ? input.value : '');
    if (isNaN(volumeNumber) || volumeNumber < 1) {
        showToast('请输入有效的卷号', 'warning');
        return;
    }
    hideInlinePlanForm();
    await startVolumePlanWithNumber(volumeNumber);
}

/** 兼容旧的 startVolumePlan（保留入口但不再使用 prompt） */
async function startVolumePlan() {
    showInlinePlanForm();
}

/** 使用指定卷号发起 AI 规划 */
async function startVolumePlanWithNumber(volumeNumber) {
    const progressContainer = document.getElementById('planProgressContainer');
    if (progressContainer) progressContainer.style.display = 'block';
    updatePlanProgress(0, '正在规划第' + volumeNumber + '卷...');

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/plan?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ volume_number: volumeNumber }),
            errorPrefix: '创建规划任务失败'
        });
        if (data.success && data.task_id) {
            pollPlanStatus(data.task_id, volumeNumber);
        } else {
            showToast(data.error || '规划任务创建失败', 'error');
            resetPlanProgress();
        }
    } catch (e) {
        console.error('开始规划失败:', e);
        showToast('创建任务失败', 'error');
        resetPlanProgress();
    }
}

async function pollPlanStatus(taskId, volumeNumber) {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/init/status?script_id=${state.scriptId}&task_id=${taskId}`, { silent: true });
        if (data.success && data.task) {
            const task = data.task;
            updatePlanProgress(task.progress || 0, task.progress_message || '处理中...');
            
            if (task.status === 'completed') {
                const statusEl = document.getElementById('planTaskStatus');
                if (statusEl) {
                    statusEl.className = 'continue-task-status completed';
                    statusEl.innerHTML = `<strong>第${volumeNumber}卷规划完成！</strong>`;
                }
                // 刷新卷纲列表和右栏
                await loadWebnovelOutline();
                showToast(`第${volumeNumber}卷规划完成`, 'success');
                setTimeout(() => resetPlanProgress(), 3000);
            } else if (task.status === 'failed') {
                const statusEl = document.getElementById('planTaskStatus');
                if (statusEl) {
                    statusEl.className = 'continue-task-status failed';
                    statusEl.innerHTML = `<strong>任务失败</strong><br>${task.error_message || '未知错误'}`;
                }
                setTimeout(() => resetPlanProgress(), 3000);
                return;
            } else if (task.status === 'running') {
                setTimeout(() => pollPlanStatus(taskId, volumeNumber), 2000);
            }
        }
    } catch (e) {
        console.error('轮询规划状态失败:', e);
        setTimeout(() => pollPlanStatus(taskId, volumeNumber), 3000);
    }
}

function updatePlanProgress(progress, message) {
    const fill = document.getElementById('planProgressFill');
    const text = document.getElementById('planProgressText');
    const msg = document.getElementById('planProgressMessage');
    if (fill) fill.style.width = `${progress}%`;
    if (text) text.textContent = `${progress}%`;
    if (msg) msg.textContent = message;
}

function resetPlanProgress() {
    const container = document.getElementById('planProgressContainer');
    const status = document.getElementById('planTaskStatus');
    if (container) container.style.display = 'none';
    if (status) status.innerHTML = '';
}
