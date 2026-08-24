function pollTaskStatus(taskId, agentName, opts) {
    const cfg = Object.assign({
        modalId: 'addAgentModal',
        btnId: 'createAgentBtn',
        progressId: 'createProgress',
        successText: '创建成功！',
        failText: '创建失败'
    }, opts || {});
    const pollInterval = 2000;

    const intervalId = setInterval(async () => {
        try {
            const task = await apiRequest(`/api/agents/tasks?task_id=${taskId}`, { silent: true });
            if (task.status === 'ready') {
                clearInterval(intervalId);
                updateProgress(100, cfg.successText, cfg.progressId);
                setTimeout(() => {
                    bootstrap.Modal.getInstance(document.getElementById(cfg.modalId)).hide();
                    loadAgents();
                    document.getElementById(cfg.btnId).disabled = false;
                    document.getElementById(cfg.progressId).classList.add('d-none');
                }, 1000);
            } else if (task.status === 'failed') {
                clearInterval(intervalId);
                updateProgress(0, cfg.failText + ': ' + (task.error || task.message), cfg.progressId);
                document.getElementById(cfg.btnId).disabled = false;
            } else {
                const progress = task.progress || 10;
                const message = task.message || '训练中...';
                updateProgress(progress, message, cfg.progressId);
            }
        } catch (e) {
            // 静默轮询
        }
    }, pollInterval);
}