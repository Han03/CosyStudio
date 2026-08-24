function showTasksModal() {
    document.getElementById('tasksModal').style.display = 'flex';
    refreshTasks();
}

function closeTasksModal() {
    document.getElementById('tasksModal').style.display = 'none';
}

function filterTasks(filter) {
    state.currentTaskFilter = filter;
    document.querySelectorAll('.tasks-filter-chip').forEach(chip => chip.classList.remove('active'));
    event.target.classList.add('active');
    renderTasks();
}

async function refreshTasks() {
    if (!state.scriptId) return;
    try {
        const data = await apiRequest(`/api/books/scripts/writing-tasks?script_id=${state.scriptId}`, { silent: true });
        state.writingTasks = data.tasks || [];
        renderTasks();
    } catch (e) {
        console.error('获取任务列表失败:', e);
    }
}

function renderTasks() {
    const container = document.getElementById('tasksList');
    let filtered = state.writingTasks;
    if (state.currentTaskFilter !== 'all') {
        filtered = state.writingTasks.filter(t => t.status === state.currentTaskFilter);
    }

    if (filtered.length === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--neu-text-muted);">暂无任务</div>';
        return;
    }

    container.innerHTML = filtered.map(task => `
        <div class="task-card ${task.status}">
            <div class="task-card-header">
                <div class="task-card-title">第${task.chapter_index}章 - ${getTaskTypeText(task.task_type)}</div>
                <span class="task-card-status ${task.status}">${getTaskStatusText(task.status)}</span>
            </div>
            <div class="task-card-meta">
                <span><i class="fas fa-clock"></i> ${formatDateTime(task.created_at)}</span>
                <span><i class="fas fa-file-alt"></i> 任务ID: ${task.id}</span>
            </div>
            ${task.status === 'running' || task.status === 'pending' ? `
                <div class="task-card-progress">
                    <div class="task-card-progress-fill" style="width: ${task.progress || 0}%"></div>
                </div>
                <div class="task-card-message">${task.progress_message || '处理中...'}</div>
            ` : ''}
            ${task.status === 'completed' && task.polished ? `
                <div class="task-card-message">已生成 ${task.polished.length} 字</div>
            ` : ''}
            ${task.status === 'failed' && task.error_message ? `
                <div class="task-card-message" style="color: #ef4444;">${task.error_message}</div>
            ` : ''}
            ${task.status === 'cancelled' ? `
                <div class="task-card-message" style="color: #f59e0b;">创作已取消</div>
            ` : ''}
            <div class="task-card-actions">
                ${task.status === 'completed' && task.polished && task.polished.trim() ? `
                    <button class="btn btn-outline-primary" onclick="applyTaskResult(${task.id})">应用结果</button>
                ` : ''}
                ${task.status === 'running' ? `
                    <button class="btn btn-outline-danger" onclick="cancelTask(${task.id})">取消</button>
                ` : ''}
                <button class="btn btn-outline-secondary" onclick="deleteTask(${task.id})">删除</button>
            </div>
        </div>
    `).join('');
}

function getTaskTypeText(type) {
    const map = { 'continue': '创作', 'draft': '起草', 'polish': '润色', 'review': '审查' };
    return map[type] || type;
}

function getTaskStatusText(status) {
    const map = { 'pending': '等待中', 'running': '运行中', 'completed': '已完成', 'failed': '失败', 'cancelled': '已取消' };
    return map[status] || status;
}

async function applyTaskResult(taskId) {
    const task = state.writingTasks.find(t => t.id === taskId);
    if (!task) {
        showToast('任务不存在', 'error');
        return;
    }
    if (!task.polished || !task.polished.trim()) {
        showToast('任务结果为空，无法应用', 'error');
        return;
    }

    const chapterIndex = task.chapter_index;

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
        // 后续 UI 更新由 WebSocket chapter_applied 消息驱动
        showToast('正在应用创作结果...', 'info');
        closeTasksModal();
    } catch (e) {
        console.error('应用创作结果失败:', e);
        showToast('应用失败: ' + e.message, 'error');
    }
}

async function cancelTask(taskId) {
    if (!confirm('确定取消这个任务吗？')) return;
    try {
        await apiRequest(`/api/books/scripts/writing-tasks?script_id=${state.scriptId}&task_id=${taskId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'cancelled' }),
            errorPrefix: '取消任务失败'
        });
        refreshTasks();
    } catch (e) {
        console.error('取消任务失败:', e);
    }
}

async function deleteTask(taskId) {
    if (!confirm('确定删除这个任务吗？')) return;
    try {
        await apiRequest(`/api/books/scripts/writing-tasks?script_id=${state.scriptId}&task_id=${taskId}`, {
            method: 'DELETE',
            errorPrefix: '删除任务失败'
        });
        refreshTasks();
    } catch (e) {
        console.error('删除任务失败:', e);
    }
}
