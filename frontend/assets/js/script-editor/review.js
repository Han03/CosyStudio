function showReviewModal() {
    document.getElementById('reviewModal').style.display = 'flex';
    loadChapterReview();
}

function closeReviewModal() {
    document.getElementById('reviewModal').style.display = 'none';
}

async function loadChapterReview() {
    if (!state.scriptId || state.currentChapterIndex < 0) return;

    try {
        const data = await apiRequest(`/api/books/scripts/chapters/review?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`, { silent: true });
        renderReviewResults(data.review);
    } catch (e) {
        console.error('获取审查结果失败:', e);
    }
}

async function manualReviewChapter() {
    const content = document.querySelector('.chapter-textarea')?.value || '';
    if (!content || !state.scriptId || state.currentChapterIndex < 0) {
        alert('请先选择章节并输入内容');
        return;
    }

    try {
        const data = await apiRequest(`/api/books/scripts/chapters/review?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
            errorPrefix: '审查失败'
        });
        renderReviewResults(data.review);
    } catch (e) {
        console.error('审查失败:', e);
    }
}

function renderReviewResults(review) {
    const grid = document.getElementById('reviewScoresGrid');
    const summary = document.getElementById('reviewSummary');
    const issues = document.getElementById('reviewIssues');

    if (!review || !Array.isArray(review)) {
        grid.innerHTML = '';
        summary.innerHTML = '暂无审查数据';
        issues.innerHTML = '';
        return;
    }

    grid.innerHTML = review.map(d => `
        <div class="review-score-card">
            <div class="review-score-label">${d.name}</div>
            <div class="review-score-value">${d.score}</div>
            <div class="review-score-bar">
                <div class="review-score-fill" style="width: ${d.score * 10}%"></div>
            </div>
        </div>
    `).join('');

    const allIssues = review.flatMap(d => d.issues || []);
    const allStrengths = review.flatMap(d => d.strengths || []);
    
    let summaryHtml = '';
    if (allStrengths.length > 0) {
        summaryHtml += `<div style="margin-bottom: 12px;"><strong style="color: #10b981;">优点:</strong><br>${allStrengths.map(s => `• ${s}`).join('<br>')}</div>`;
    }
    const suggestions = review.filter(d => d.suggestions).map(d => `${d.name}: ${d.suggestions}`).join('<br>');
    if (suggestions) {
        summaryHtml += `<div><strong style="color: var(--neu-accent);">建议:</strong><br>${suggestions}</div>`;
    }
    summary.innerHTML = summaryHtml || '暂无审查总结';

    if (allIssues.length === 0) {
        issues.innerHTML = '<div style="text-align: center; color: var(--neu-text-muted);">未发现明显问题</div>';
    } else {
        const severityColors = {
            'critical': 'background: rgba(239, 68, 68, 0.1); color: #ef4444; border-left: 3px solid #ef4444;',
            'high': 'background: rgba(249, 115, 22, 0.1); color: #f97316; border-left: 3px solid #f97316;',
            'medium': 'background: rgba(234, 179, 8, 0.1); color: #eab308; border-left: 3px solid #eab308;',
            'low': 'background: rgba(59, 130, 246, 0.1); color: #3b82f6; border-left: 3px solid #3b82f6;'
        };
        const severityLabels = {
            'critical': '严重',
            'high': '重要',
            'medium': '一般',
            'low': '轻微'
        };
        
        issues.innerHTML = allIssues.map(issue => `
            <div class="review-issue-item" style="${severityColors[issue.severity] || severityColors['low']}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-weight: 600;">${issue.location || '未知位置'}</span>
                    <span style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(0,0,0,0.1);">${severityLabels[issue.severity] || '未知'}</span>
                </div>
                <div style="font-size: 13px; margin-bottom: 4px;">${issue.description || ''}</div>
                ${issue.evidence ? `<div style="font-size: 11px; color: var(--neu-text-muted); italic: true;">证据: ${issue.evidence}</div>` : ''}
                ${issue.fix_hint ? `<div style="font-size: 12px; color: #10b981; margin-top: 4px;">建议: ${issue.fix_hint}</div>` : ''}
            </div>
        `).join('');
    }
}
