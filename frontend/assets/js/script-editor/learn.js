// ========== 项目学习 ==========

function showLearnModal() {
    document.getElementById('learnModal').style.display = 'flex';
    document.getElementById('learnProgressContainer').style.display = 'none';
    document.getElementById('learnResult').style.display = 'none';
    document.getElementById('learnContent').value = '';
    
    populateLearnChapterSelect();
}

function closeLearnModal() {
    document.getElementById('learnModal').style.display = 'none';
}

function populateLearnChapterSelect() {
    const select = document.getElementById('learnChapterSelect');
    select.innerHTML = '<option value="">请选择章节</option>';
    state.chapters.forEach(chapter => {
        select.innerHTML += `<option value="${chapter.chapter_index}" ${chapter.chapter_index === state.currentChapterIndex ? 'selected' : ''}>第${chapter.chapter_index}章 ${chapter.chapter_title || '未命名'}</option>`;
    });
}

async function startLearn() {
    const content = document.getElementById('learnContent').value.trim();
    const chapter = parseInt(document.getElementById('learnChapterSelect').value) || 0;
    
    if (!content) {
        showToast('请输入学习内容', 'warning');
        return;
    }

    document.getElementById('learnStartBtn').disabled = true;
    document.getElementById('learnProgressContainer').style.display = 'block';
    document.getElementById('learnResult').style.display = 'none';
    updateLearnProgress(0, '正在学习...');

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/learn?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ learning_content: content, current_chapter: chapter }),
            errorPrefix: '开始学习失败'
        });
        if (data.success && data.task_id) {
            pollLearnStatus(data.task_id);
        } else {
            showToast(data.error || '学习任务创建失败', 'error');
            resetLearnModal();
        }
    } catch (e) {
        resetLearnModal();
    }
}

async function pollLearnStatus(taskId) {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/init/status?script_id=${state.scriptId}&task_id=${taskId}`, { silent: true });
        if (data.success && data.task) {
            const task = data.task;
            
            if (task.status === 'completed') {
                updateLearnProgress(100, '学习完成');
                let learned = [];
                if (task.context) {
                    try {
                        const ctx = JSON.parse(task.context);
                        learned = ctx.learned_patterns || [];
                    } catch {}
                }
                
                if (learned.length > 0) {
                    document.getElementById('learnResultContent').innerHTML = `
                        <div style="font-size: 13px;">
                            <div style="font-weight: 600; margin-bottom: 8px;">学习到以下写作模式：</div>
                            ${learned.map((pattern, idx) => `<div style="margin-bottom: 6px; padding: 6px; background: var(--neu-bg-secondary); border-radius: 4px;">
                                <strong>${idx + 1}.</strong> ${escapeHtml(pattern)}
                            </div>`).join('')}
                        </div>
                    `;
                } else {
                    document.getElementById('learnResultContent').innerHTML = '<div style="color: var(--neu-text-muted);">学习完成，但没有生成新的模式</div>';
                }
                document.getElementById('learnResult').style.display = 'block';
                document.getElementById('learnStartBtn').disabled = false;
            } else if (task.status === 'failed') {
                updateLearnProgress(0, '学习失败');
                document.getElementById('learnStartBtn').disabled = false;
            } else if (task.status === 'running') {
                setTimeout(() => pollLearnStatus(taskId), 2000);
            }
        }
    } catch (e) {
        console.error('轮询学习状态失败:', e);
        setTimeout(() => pollLearnStatus(taskId), 3000);
    }
}

function updateLearnProgress(progress, message) {
    document.getElementById('learnProgressFill').style.width = `${progress}%`;
    document.getElementById('learnProgressText').textContent = `${progress}%`;
    document.getElementById('learnProgressMessage').textContent = message;
}

function resetLearnModal() {
    document.getElementById('learnStartBtn').disabled = false;
    document.getElementById('learnProgressContainer').style.display = 'none';
}

