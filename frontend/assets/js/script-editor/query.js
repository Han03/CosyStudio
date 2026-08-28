// ========== 状态查询（基于RAG语义检索） ==========

function showQueryModal() {
    document.getElementById('queryModal').style.display = 'flex';
    document.getElementById('queryQuestion').value = '';
    document.getElementById('queryResult').style.display = 'none';
    document.getElementById('queryLoading').style.display = 'none';
    document.getElementById('queryEmpty').style.display = 'none';
    document.getElementById('querySubmitBtn').disabled = false;
    document.getElementById('queryQuestion').focus();
}

function closeQueryModal() {
    document.getElementById('queryModal').style.display = 'none';
}

async function submitQuery() {
    const question = document.getElementById('queryQuestion').value.trim();
    if (!question) {
        showToast('请输入查询问题', 'warning');
        return;
    }

    document.getElementById('querySubmitBtn').disabled = true;
    document.getElementById('queryResult').style.display = 'none';
    document.getElementById('queryEmpty').style.display = 'none';
    document.getElementById('queryLoading').style.display = 'block';

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/query?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_question: question }),
            errorPrefix: '查询失败'
        });

        document.getElementById('queryLoading').style.display = 'none';

        if (data.success) {
            const chunks = data.chunks || [];
            if (chunks.length > 0) {
                renderQueryResults(chunks);
                document.getElementById('queryResult').style.display = 'block';
            } else {
                document.getElementById('queryEmpty').style.display = 'block';
            }
        } else {
            showToast(data.error || '查询失败', 'error');
        }
    } catch (e) {
        document.getElementById('queryLoading').style.display = 'none';
        showToast('查询请求失败', 'error');
    } finally {
        document.getElementById('querySubmitBtn').disabled = false;
    }
}

function renderQueryResults(chunks) {
    const typeLabels = {
        'character': '角色', 'worldview': '世界观', 'power_system': '力量体系',
        'golden_finger': '金手指', 'volume_outline': '卷纲', 'foreshadow': '伏笔',
        'villain': '反派', 'chapter': '章节', 'chapter_paragraph': '章节原文'
    };

    // 按 chunk_type 分组，保持后端返回的顺序（分类已按首条相似度降序排列）
    const grouped = {};
    const categoryOrder = [];
    for (const chunk of chunks) {
        const cat = chunk.chunk_type || 'unknown';
        if (!grouped[cat]) {
            grouped[cat] = [];
            categoryOrder.push(cat);
        }
        grouped[cat].push(chunk);
    }

    const container = document.getElementById('queryResultContent');
    let html = '';
    for (const cat of categoryOrder) {
        const items = grouped[cat];
        const typeLabel = typeLabels[cat] || cat || '未知';
        html += `<div class="query-category-group">`;
        html += `<div class="query-category-title"><i class="fas fa-tag"></i> ${typeLabel}（${items.length}）</div>`;
        html += items.map(chunk => {
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
        html += `</div>`;
    }
    container.innerHTML = html;
}
