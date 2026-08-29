// ========== 状态查询（基于RAG语义检索） ==========

// --- RAG 浏览状态 ---
const ragBrowseState = {
    page: 1,
    pageSize: 15,
    chunkType: '',
    total: 0,
    totalPages: 0,
};

function showQueryModal() {
    document.getElementById('queryModal').style.display = 'flex';
    document.getElementById('queryQuestion').value = '';
    document.getElementById('queryResult').style.display = 'none';
    document.getElementById('queryLoading').style.display = 'none';
    document.getElementById('queryEmpty').style.display = 'none';
    document.getElementById('queryQuestion').focus();
    // 默认显示浏览面板，隐藏清空按钮
    document.getElementById('queryClearBtn').style.display = 'none';
    showBrowsePanel();
    ragBrowseState.page = 1;
    loadRagBrowse();
}

function closeQueryModal() {
    document.getElementById('queryModal').style.display = 'none';
}

// --- 搜索框清空按钮 ---
function toggleQueryClearBtn() {
    const val = document.getElementById('queryQuestion').value.trim();
    document.getElementById('queryClearBtn').style.display = val ? '' : 'none';
}

function clearQuerySearch() {
    document.getElementById('queryQuestion').value = '';
    document.getElementById('queryClearBtn').style.display = 'none';
    document.getElementById('queryResult').style.display = 'none';
    document.getElementById('queryLoading').style.display = 'none';
    document.getElementById('queryEmpty').style.display = 'none';
    showBrowsePanel();
    ragBrowseState.page = 1;
    loadRagBrowse();
}

function showBrowsePanel() {
    document.getElementById('queryPanelBrowse').style.display = '';
}

function hideBrowsePanel() {
    document.getElementById('queryPanelBrowse').style.display = 'none';
}

// --- RAG 浏览全部 ---
function filterRagBrowse(chunkType) {
    ragBrowseState.chunkType = chunkType;
    ragBrowseState.page = 1;
    // 更新 filter 按钮状态
    document.querySelectorAll('.rag-browse-filter').forEach(el => {
        el.classList.toggle('active', el.dataset.type === chunkType);
    });
    loadRagBrowse();
}

async function loadRagBrowse() {
    const listEl = document.getElementById('ragBrowseList');
    const paginationEl = document.getElementById('ragBrowsePagination');
    const statsEl = document.getElementById('ragBrowseStats');
    listEl.innerHTML = '<div class="rag-empty"><i class="fas fa-spinner fa-spin"></i><p>加载中...</p></div>';
    paginationEl.innerHTML = '';
    statsEl.innerHTML = '';

    try {
        const params = new URLSearchParams({
            script_id: state.scriptId,
            page: ragBrowseState.page,
            page_size: ragBrowseState.pageSize,
        });
        if (ragBrowseState.chunkType) {
            params.set('chunk_type', ragBrowseState.chunkType);
        }
        const data = await apiRequest(`/api/books/scripts/webnovel/rag-chunks?${params}`, { silent: true });

        if (!data.success) {
            listEl.innerHTML = '<div class="rag-empty"><i class="fas fa-exclamation-circle"></i><p>加载失败</p></div>';
            return;
        }

        ragBrowseState.total = data.total || 0;
        ragBrowseState.totalPages = data.total_pages || 0;
        ragBrowseState.page = data.page || 1;

        // 统计信息
        statsEl.innerHTML = `<span>共 <strong>${ragBrowseState.total}</strong> 条记录，第 <strong>${ragBrowseState.page}</strong>/${ragBrowseState.totalPages} 页</span>`;

        const items = data.items || [];
        if (items.length === 0) {
            listEl.innerHTML = '<div class="rag-empty"><i class="fas fa-database"></i><p>暂无 RAG 数据</p></div>';
            return;
        }

        renderRagBrowseItems(items, listEl);
        renderRagBrowsePagination(paginationEl);
    } catch (e) {
        listEl.innerHTML = '<div class="rag-empty"><i class="fas fa-exclamation-circle"></i><p>加载失败</p></div>';
        console.error('加载 RAG 数据失败:', e);
    }
}

function renderRagBrowseItems(items, container) {
    const typeLabels = {
        'character': '角色', 'worldview': '世界观', 'power_system': '力量体系',
        'golden_finger': '金手指', 'volume_outline': '卷纲', 'foreshadow': '伏笔',
        'villain': '反派', 'chapter': '章节', 'chapter_summary': '章节摘要',
        'chapter_paragraph': '章节原文',
    };

    let html = '';
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const typeLabel = typeLabels[item.chunk_type] || item.chunk_type || '未知';
        const chapterInfo = item.chapter_number ? ` · 第${item.chapter_number}章` : '';
        let content = item.content || '';
        const maxLen = 500;
        const truncated = content.length > maxLen;
        const displayContent = truncated ? content.substring(0, maxLen) + '...' : content;
        const uniqueId = `rag-card-${Date.now()}-${i}`;

        html += `
        <div class="rag-browse-card">
            <div class="rag-browse-card-header">
                <span class="rag-browse-type-badge">${typeLabel}</span>
                ${chapterInfo ? `<span class="rag-browse-chapter">${chapterInfo}</span>` : ''}
                <span class="rag-browse-id">#${item.id}</span>
            </div>
            <div class="rag-browse-card-content" id="${uniqueId}">${escapeHtml(displayContent)}</div>
            ${truncated ? `<div class="rag-browse-expand" data-full="${btoa(unescape(encodeURIComponent(content)))}" data-target="${uniqueId}" onclick="expandRagCard(this)"><i class="fas fa-angle-down"></i> 展开完整内容</div>` : ''}
        </div>
        `;
    }
    container.innerHTML = html;
}

function expandRagCard(el) {
    const targetId = el.getAttribute('data-target');
    const fullContent = decodeURIComponent(escape(atob(el.getAttribute('data-full'))));
    document.getElementById(targetId).innerHTML = escapeHtml(fullContent);
    el.remove();
}

function renderRagBrowsePagination(container) {
    if (ragBrowseState.totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    const { page, totalPages } = ragBrowseState;
    let html = '<div class="rag-pagination">';

    // 上一页
    html += `<button class="rag-pagination-btn" ${page <= 1 ? 'disabled' : ''} onclick="goToRagPage(${page - 1})"><i class="fas fa-chevron-left"></i></button>`;

    // 页码按钮（最多显示 7 个）
    const maxVisible = 7;
    let startPage = Math.max(1, page - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage < maxVisible - 1) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
        html += `<button class="rag-pagination-btn" onclick="goToRagPage(1)">1</button>`;
        if (startPage > 2) html += `<span class="rag-pagination-ellipsis">...</span>`;
    }
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="rag-pagination-btn ${i === page ? 'active' : ''}" onclick="goToRagPage(${i})">${i}</button>`;
    }
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += `<span class="rag-pagination-ellipsis">...</span>`;
        html += `<button class="rag-pagination-btn" onclick="goToRagPage(${totalPages})">${totalPages}</button>`;
    }

    // 下一页
    html += `<button class="rag-pagination-btn" ${page >= totalPages ? 'disabled' : ''} onclick="goToRagPage(${page + 1})"><i class="fas fa-chevron-right"></i></button>`;

    html += '</div>';
    container.innerHTML = html;
}

function goToRagPage(page) {
    ragBrowseState.page = page;
    loadRagBrowse();
    // 滚动列表到顶部
    const listEl = document.getElementById('ragBrowseList');
    if (listEl) listEl.scrollTop = 0;
}

async function submitQuery() {
    const question = document.getElementById('queryQuestion').value.trim();
    if (!question) {
        showToast('请输入查询问题', 'warning');
        return;
    }

    document.getElementById('queryResult').style.display = 'none';
    document.getElementById('queryEmpty').style.display = 'none';
    document.getElementById('queryLoading').style.display = 'block';
    hideBrowsePanel();

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
                renderQueryResults(chunks, !!data.reranked);
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
        showBrowsePanel();
    }
}

function renderQueryResults(chunks, reranked = false) {
    const typeLabels = {
        'character': '角色', 'worldview': '世界观', 'power_system': '力量体系',
        'golden_finger': '金手指', 'volume_outline': '卷纲', 'foreshadow': '伏笔',
        'villain': '反派', 'chapter': '章节', 'chapter_summary': '章节摘要',
        'chapter_paragraph': '章节原文',
    };

    // 按 chunk_type 分组，保持后端返回的顺序（分类已按首条分数降序排列）
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
    // 重排序提示：结果已经过片段重排序模型二次精排，按相关性降序排列
    let html = reranked
        ? `<div class="query-rerank-hint"><i class="fas fa-magic"></i> 结果已经片段重排序模型精排，按相关性降序排列</div>`
        : '';
    for (const cat of categoryOrder) {
        const items = grouped[cat];
        const typeLabel = typeLabels[cat] || cat || '未知';
        html += `<div class="query-category-group">`;
        html += `<div class="query-category-title"><i class="fas fa-tag"></i> ${typeLabel}（${items.length}）</div>`;
        html += items.map(chunk => {
            const chapterInfo = chunk.chapter_number ? ` · 第${chunk.chapter_number}章` : '';
            // 章节原文段落：展示前后上下文
            const hasContext = chunk.context_before || chunk.context_after;
            let contentHtml = '';
            if (hasContext) {
                if (chunk.context_before) {
                    contentHtml += `<div class="rag-ctx-block rag-ctx-before">${escapeHtml(chunk.context_before)}</div>`;
                }
                contentHtml += `<div class="rag-ctx-hit">${escapeHtml(chunk.content || '')}</div>`;
                if (chunk.context_after) {
                    contentHtml += `<div class="rag-ctx-block rag-ctx-after">${escapeHtml(chunk.context_after)}</div>`;
                }
            } else {
                contentHtml = `<div class="rag-result-content">${escapeHtml(chunk.content || '')}</div>`;
            }
            // 重排序分数徽章：rerank_score 为 query-doc 相关性概率，与向量相似度量纲不同，分别展示
            const rerankBadge = chunk.rerank_score != null
                ? `<span class="rag-result-score rag-result-rerank" title="片段重排序相关性分数">相关性: ${(chunk.rerank_score * 100).toFixed(1)}%</span>`
                : '';
            return `
            <div class="rag-result-card">
                <div class="rag-result-header">
                    <span class="rag-result-source">${typeLabel}${chapterInfo}</span>
                    <span class="rag-result-scores">${rerankBadge}<span class="rag-result-score">相似度: ${((chunk.score || 0) * 100).toFixed(1)}%</span></span>
                </div>
                ${contentHtml}
            </div>
            `;
        }).join('');
        html += `</div>`;
    }
    container.innerHTML = html;
}

// ========== RAG 重建索引 ==========

let _reindexActive = false;

// 注册 WS 回调，由 websocket.js 的 handleReindexProgressMessage 调用
window.handleReindexProgress = function(msg) {
    if (!_reindexActive) return;
    const progressEl = document.getElementById('reindexProgressText');
    const btn = document.getElementById('reindexRagBtn');
    const status = msg.status;
    const message = msg.message || '';
    const progress = msg.progress || 0;

    if (status === 'running') {
        progressEl.textContent = `${message} (${progress}%)`;
    } else if (status === 'completed') {
        progressEl.textContent = message || '重建完成';
        showToast('RAG 索引重建完成', 'success');
        _reindexActive = false;
        resetReindexBtn();
        // 刷新浏览面板
        ragBrowseState.page = 1;
        loadRagBrowse();
    } else if (status === 'failed') {
        progressEl.textContent = message || '重建失败';
        showToast('RAG 索引重建失败', 'error');
        _reindexActive = false;
        resetReindexBtn();
    }
};

async function startReindexRag() {
    if (!state.scriptId) {
        showToast('请先选择剧本', 'warning');
        return;
    }

    // 二次确认
    const confirmed = confirm(
        '将清空项目所有 RAG 向量数据，然后重新索引项目设定和已有章节内容。\n\n' +
        '注意：重建过程需要计算 embedding，耗时取决于章节数量。\n' +
        '重建完成前请勿关闭页面。'
    );
    if (!confirmed) return;

    const btn = document.getElementById('reindexRagBtn');
    const progressEl = document.getElementById('reindexProgressText');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 重建中...';
    progressEl.style.display = '';
    progressEl.textContent = '正在创建任务...';
    _reindexActive = true;

    try {
        const data = await apiRequest(
            `/api/books/scripts/webnovel/reindex-rag?script_id=${state.scriptId}`,
            { method: 'POST', errorPrefix: '重建索引失败' }
        );
        if (!data.success) {
            showToast(data.error || '重建任务创建失败', 'error');
            _reindexActive = false;
            resetReindexBtn();
        }
        // 任务已创建，后续进度由 WS 推送，无需轮询
    } catch (e) {
        console.error('启动重建索引失败:', e);
        showToast('重建请求失败', 'error');
        _reindexActive = false;
        resetReindexBtn();
    }
}

function resetReindexBtn() {
    const btn = document.getElementById('reindexRagBtn');
    const progressEl = document.getElementById('reindexProgressText');
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-sync-alt"></i> 重建RAG索引';
    // 3秒后隐藏进度文本
    setTimeout(() => { progressEl.style.display = 'none'; }, 3000);
}
