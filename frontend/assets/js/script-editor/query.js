// ========== 状态查询 ==========

let currentQueryType = 'character';

function showQueryModal() {
    document.getElementById('queryModal').style.display = 'flex';
    document.getElementById('queryProgressContainer').style.display = 'none';
    document.getElementById('queryResult').style.display = 'none';
    document.getElementById('queryQuestion').value = '';
    currentQueryType = 'character';
}

function closeQueryModal() {
    document.getElementById('queryModal').style.display = 'none';
}

function setQueryType(btn, type) {
    document.querySelectorAll('.continue-option-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentQueryType = type;
    
    const prompts = {
        'character': '查询角色相关信息，例如：主角的核心性格是什么？',
        'power': '查询能力体系相关信息，例如：当前最高境界是什么？',
        'timeline': '查询时间线相关信息，例如：故事已过去多久？',
        'plot': '查询剧情进展相关信息，例如：当前剧情处于什么阶段？',
        'custom': '输入自定义查询问题...'
    };
    document.getElementById('queryQuestion').placeholder = prompts[type];
}

async function submitQuery() {
    const question = document.getElementById('queryQuestion').value.trim();
    if (!question) {
        showToast('请输入查询问题', 'warning');
        return;
    }

    document.getElementById('querySubmitBtn').disabled = true;
    document.getElementById('queryProgressContainer').style.display = 'block';
    document.getElementById('queryResult').style.display = 'none';
    updateQueryProgress(30, '查询中...');

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/query?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_type: currentQueryType, query_question: question }),
            errorPrefix: '提交查询失败'
        });
        if (data.success && data.task_id) {
            pollQueryStatus(data.task_id);
        } else {
            showToast(data.error || '查询任务创建失败', 'error');
            resetQueryModal();
        }
    } catch (e) {
        resetQueryModal();
    }
}

async function pollQueryStatus(taskId) {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/init/status?script_id=${state.scriptId}&task_id=${taskId}`, { silent: true });
        if (data.success && data.task) {
            const task = data.task;
            
            if (task.status === 'completed') {
                updateQueryProgress(100, '查询完成');
                let resultContent = '';
                if (task.context) {
                    try {
                        const context = JSON.parse(task.context);
                        if (typeof context === 'object') {
                            resultContent = formatQueryResult(context);
                        } else {
                            resultContent = escapeHtml(context);
                        }
                    } catch {
                        resultContent = escapeHtml(task.context);
                    }
                } else {
                    resultContent = '<div style="color: var(--neu-text-muted);">暂无查询结果</div>';
                }
                document.getElementById('queryResultContent').innerHTML = resultContent;
                document.getElementById('queryResult').style.display = 'block';
                document.getElementById('querySubmitBtn').disabled = false;
            } else if (task.status === 'failed') {
                updateQueryProgress(0, '查询失败');
                document.getElementById('queryResultContent').innerHTML = `<span style="color: #ef4444;">${task.error_message || '查询失败'}</span>`;
                document.getElementById('queryResult').style.display = 'block';
                document.getElementById('querySubmitBtn').disabled = false;
            } else if (task.status === 'running') {
                setTimeout(() => pollQueryStatus(taskId), 2000);
            }
        }
    } catch (e) {
        console.error('轮询查询状态失败:', e);
        setTimeout(() => pollQueryStatus(taskId), 3000);
    }
}

function formatQueryResult(result) {
    if (Array.isArray(result)) {
        return result.map((item, idx) => `<div style="margin-bottom: 8px;"><strong>${idx + 1}.</strong> ${escapeHtml(typeof item === 'object' ? JSON.stringify(item, null, 2) : item)}</div>`).join('');
    }
    return '<pre style="white-space: pre-wrap; font-family: inherit;">' + escapeHtml(JSON.stringify(result, null, 2)) + '</pre>';
}

function updateQueryProgress(progress, message) {
    document.getElementById('queryProgressFill').style.width = `${progress}%`;
    document.getElementById('queryProgressText').textContent = `${progress}%`;
    document.getElementById('queryProgressMessage').textContent = message;
}

function resetQueryModal() {
    document.getElementById('querySubmitBtn').disabled = false;
    document.getElementById('queryProgressContainer').style.display = 'none';
}

