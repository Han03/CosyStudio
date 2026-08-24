// ========== 可视化面板 ==========

function showDashboardModal() {
    document.getElementById('dashboardModal').style.display = 'flex';
    refreshDashboard();
}

function closeDashboardModal() {
    document.getElementById('dashboardModal').style.display = 'none';
}

async function refreshDashboard() {
    document.getElementById('dashboardLoading').style.display = 'block';
    document.getElementById('dashboardContent').style.display = 'none';

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/dashboard?script_id=${state.scriptId}`, { silent: true });
        
        if (data.success) {
            renderDashboard(data);
            document.getElementById('dashboardLoading').style.display = 'none';
            document.getElementById('dashboardContent').style.display = 'block';
        }
    } catch (e) {
        document.getElementById('dashboardLoading').innerHTML = '<div style="color: #ef4444;">加载失败，请重试</div>';
    }
}

function renderDashboard(data) {
    const stats = data.statistics || {};
    document.getElementById('statTotalChapters').textContent = stats.total_chapters || 0;
    document.getElementById('statTotalWords').textContent = (stats.total_words || 0).toLocaleString();
    document.getElementById('statTotalVolumes').textContent = stats.total_volumes || 0;
    document.getElementById('statTotalCharacters').textContent = stats.total_characters || 0;

    const project = data.project || {};
    const projectInfo = [
        { label: '书名', value: project.title || '未设置' },
        { label: '题材', value: project.genre || '未设置' },
        { label: '目标字数', value: project.target_words ? project.target_words.toLocaleString() + '字' : '未设置' },
        { label: '目标章节', value: project.target_chapters ? project.target_chapters + '章' : '未设置' },
    ];
    document.getElementById('dashboardProjectInfo').innerHTML = projectInfo.map(item => `
        <div class="dashboard-info-item">
            <span class="dashboard-info-label">${item.label}</span>
            <span class="dashboard-info-value">${escapeHtml(item.value)}</span>
        </div>
    `).join('');

    const volumes = data.volume_outlines || [];
    if (volumes.length === 0) {
        document.getElementById('dashboardVolumeList').innerHTML = '<div style="text-align: center; color: var(--neu-text-muted); padding: 12px;">暂无卷纲</div>';
    } else {
        document.getElementById('dashboardVolumeList').innerHTML = volumes.map(v => `
            <div class="dashboard-list-item">
                <div class="dashboard-list-item-title">第${v.volume_number}卷 ${v.volume_name || ''}</div>
                <div class="dashboard-list-item-meta">
                    <span>${v.chapter_start || 0}-${v.chapter_end || 0}章</span>
                </div>
                <div class="dashboard-list-item-content">${escapeHtml(v.core_conflict || '').substring(0, 100)}...</div>
            </div>
        `).join('');
    }

    const characters = data.characters || [];
    if (characters.length === 0) {
        document.getElementById('dashboardCharacterList').innerHTML = '<div style="text-align: center; color: var(--neu-text-muted); padding: 12px;">暂无角色</div>';
    } else {
        document.getElementById('dashboardCharacterList').innerHTML = characters.map(c => `
            <div class="dashboard-list-item">
                <div class="dashboard-list-item-title">
                    ${c.name || '未知角色'}
                    <span style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(59, 130, 246, 0.1); color: #3b82f6; margin-left: 8px;">
                        ${c.character_type === 'protagonist' ? '主角' : c.character_type === 'villain' ? '反派' : '配角'}
                    </span>
                </div>
                <div class="dashboard-list-item-content">${escapeHtml(c.core_personality || c.identity || '').substring(0, 100)}...</div>
            </div>
        `).join('');
    }
}