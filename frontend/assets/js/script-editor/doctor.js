// ========== 项目体检 ==========

function showDoctorModal() {
    document.getElementById('doctorModal').style.display = 'flex';
    document.getElementById('doctorProgressContainer').style.display = 'none';
    document.getElementById('doctorResult').style.display = 'none';
    document.getElementById('doctorDeep').checked = true;
}

function closeDoctorModal() {
    document.getElementById('doctorModal').style.display = 'none';
}

async function startDoctor() {
    const deep = document.getElementById('doctorDeep').checked;
    
    document.getElementById('doctorStartBtn').disabled = true;
    document.getElementById('doctorProgressContainer').style.display = 'block';
    document.getElementById('doctorResult').style.display = 'none';
    updateDoctorProgress(0, '正在进行项目体检...');

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/doctor?script_id=${state.scriptId}&deep=${deep}`, {
            errorPrefix: '体检失败'
        });
        if (data.success && data.task_id) {
            pollDoctorStatus(data.task_id);
        } else {
            showToast(data.error || '体检任务创建失败', 'error');
            resetDoctorModal();
        }
    } catch (e) {
        console.error('开始体检失败:', e);
        showToast('创建任务失败', 'error');
        resetDoctorModal();
    }
}

async function pollDoctorStatus(taskId) {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/init/status?script_id=${state.scriptId}&task_id=${taskId}`, { silent: true });
        if (data.success && data.task) {
            const task = data.task;
            
            if (task.status === 'completed') {
                updateDoctorProgress(100, '体检完成');
                let report = {};
                if (task.context) {
                    try {
                        report = JSON.parse(task.context);
                    } catch {}
                }
                renderDoctorResult(report);
                document.getElementById('doctorResult').style.display = 'block';
                document.getElementById('doctorStartBtn').disabled = false;
            } else if (task.status === 'failed') {
                updateDoctorProgress(0, '体检失败');
                document.getElementById('doctorStartBtn').disabled = false;
            } else if (task.status === 'running') {
                setTimeout(() => pollDoctorStatus(taskId), 2000);
            }
        }
    } catch (e) {
        console.error('轮询体检状态失败:', e);
        setTimeout(() => pollDoctorStatus(taskId), 3000);
    }
}

function renderDoctorResult(report) {
    const totalIssues = report.total_issues || 0;
    const score = Math.max(0, 100 - totalIssues * 10);
    
    const badgeEl = document.getElementById('doctorScoreBadge');
    badgeEl.textContent = `${score}分`;
    badgeEl.className = `badge ${score >= 80 ? 'bg-success' : score >= 60 ? 'bg-warning' : 'bg-danger'}`;

    const issuesEl = document.getElementById('doctorIssues');
    const issues = report.issues || [];
    
    if (issues.length === 0) {
        issuesEl.innerHTML = '<div style="text-align: center; color: var(--neu-text-muted);">未发现问题</div>';
    } else {
        issuesEl.innerHTML = issues.map(issue => `
            <div style="padding: 8px; margin-bottom: 8px; background: rgba(239, 68, 68, 0.05); border-left: 3px solid #ef4444; border-radius: 0 4px 4px 0;">
                <div style="font-weight: 600; font-size: 13px;">${issue.title || '未知问题'}</div>
                <div style="font-size: 12px; color: var(--neu-text-muted); margin-top: 4px;">${issue.description || ''}</div>
            </div>
        `).join('');
    }

    const suggestionsEl = document.getElementById('doctorSuggestions');
    const suggestions = report.suggestions || [];
    
    if (suggestions.length > 0) {
        suggestionsEl.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 8px;">改进建议</div>
            ${suggestions.map((s, idx) => `<div style="font-size: 13px; margin-bottom: 4px;">${idx + 1}. ${s}</div>`).join('')}
        `;
    } else {
        suggestionsEl.innerHTML = '';
    }
}

function updateDoctorProgress(progress, message) {
    document.getElementById('doctorProgressFill').style.width = `${progress}%`;
    document.getElementById('doctorProgressText').textContent = `${progress}%`;
    document.getElementById('doctorProgressMessage').textContent = message;
}

function resetDoctorModal() {
    document.getElementById('doctorStartBtn').disabled = false;
    document.getElementById('doctorProgressContainer').style.display = 'none';
}

