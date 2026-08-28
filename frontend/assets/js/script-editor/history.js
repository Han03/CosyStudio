let _currentHistoryLineId = null;
let _historyPreviewAudio = null;   // 当前试听中的 Audio 对象
let _historyPreviewBtn = null;     // 当前试听按钮（用于切换图标）

function showAudioHistory(lineId) {
    _currentHistoryLineId = lineId;
    const modal = document.getElementById('audioHistoryModal');
    const body = document.getElementById('audioHistoryBody');
    modal.style.display = 'flex';
    body.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p class="mt-2">加载历史...</p></div>';

    (async () => {
        try {
            const data = await apiRequest(`/api/audio/history?line_id=${lineId}`, { silent: true });
            if (data.success && data.history && data.history.length > 0) {
                const agentNames = {};
                for (const a of state.agents) {
                    agentNames[a.id] = a.name;
                }

                body.innerHTML = `
                    <div class="history-list">
                        ${data.history.map((h, idx) => `
                            <div class="history-item">
                                <div class="history-time">生成时间: ${new Date(h.created_at * 1000).toLocaleString()}</div>
                                <div class="history-config">
                                    <span><i class="fas fa-user"></i> ${agentNames[h.agent_id] || h.agent_id}</span>
                                    ${h.tone ? `<span><i class="fas fa-music"></i> ${h.tone}</span>` : ''}
                                    ${h.seed !== 0 ? `<span><i class="fas fa-seedling"></i> seed:${h.seed}</span>` : ''}
                                </div>
                                <div class="history-content">${escapeHtml(h.content)}</div>
                                <div class="history-actions">
                                    <button class="btn btn-sm btn-primary" data-action="preview" data-path="${h.audio_path}" data-history-id="${h.id}">
                                        <i class="fas fa-play"></i> 试听
                                    </button>
                                    <button class="btn btn-sm btn-outline-primary" data-action="reload" data-history-id="${h.id}">
                                        <i class="fas fa-undo"></i> 重新加载
                                    </button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;

                body.addEventListener('click', _handleHistoryAction);
            } else {
                body.innerHTML = '<div class="history-empty"><i class="fas fa-history"></i><p class="mt-2">暂无生成历史</p></div>';
            }
        } catch (e) {
            body.innerHTML = '<div class="history-empty">加载失败</div>';
        }
    })();
}

function _stopHistoryPreview() {
    if (_historyPreviewAudio) {
        try { _historyPreviewAudio.pause(); _historyPreviewAudio.currentTime = 0; } catch (e) {}
        _historyPreviewAudio = null;
    }
    if (_historyPreviewBtn) {
        _historyPreviewBtn.innerHTML = '<i class="fas fa-play"></i> 试听';
        _historyPreviewBtn = null;
    }
}

function _handleHistoryAction(e) {
    const btn = e.target.closest('button');
    if (!btn) return;
    
    const action = btn.dataset.action;
    if (action === 'preview') {
        const audioPath = btn.dataset.path;
        if (!audioPath) {
            showToast('音频文件路径无效', 'error');
            return;
        }

        // 如果当前正在播放同一个音频，停止它
        if (_historyPreviewBtn === btn) {
            _stopHistoryPreview();
            return;
        }

        // 停止之前的试听
        _stopHistoryPreview();

        const audioUrl = AudioEditor.getAudioUrl(audioPath);
        const audio = new Audio(audioUrl);
        _historyPreviewAudio = audio;
        _historyPreviewBtn = btn;
        btn.innerHTML = '<i class="fas fa-stop"></i> 停止';

        audio.addEventListener('ended', () => {
            _stopHistoryPreview();
        });
        audio.addEventListener('error', () => {
            showToast('音频加载失败', 'error');
            _stopHistoryPreview();
        });
        audio.play().catch(err => {
            showToast('播放失败: ' + err.message, 'error');
            _stopHistoryPreview();
        });
    } else if (action === 'reload') {
        const historyId = parseInt(btn.dataset.historyId);
        if (historyId && _currentHistoryLineId) {
            (async () => {
                try {
                    const data = await apiRequest(`/api/audio/reload-history?history_id=${historyId}`, {
                        method: 'POST',
                        errorPrefix: '重新加载失败'
                    });
                    if (data.success && data.audio_path) {
                        const line = state.currentLines.find(l => l.id === _currentHistoryLineId);
                        if (line) {
                            line.audio_path = data.audio_path;
                            renderLines();
                        }
                        hideAudioHistoryModal();
                        showToast('已重新加载历史配置', 'success');
                    }
                } catch (e) {
                    // apiRequest 已弹出错误提示
                }
            })();
        }
    }
}

function hideAudioHistoryModal() {
    const body = document.getElementById('audioHistoryBody');
    body.removeEventListener('click', _handleHistoryAction);
    _stopHistoryPreview();
    document.getElementById('audioHistoryModal').style.display = 'none';
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '00:00';
    const s = Math.floor(seconds);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function formatFileSize(bytes) {
    if (!bytes || bytes < 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

let _chapterHistoryCache = null;

function showChapterAudioHistory() {
    if (state.scriptId === null || state.currentChapterIndex < 0) {
        showToast('请先选择章节', 'warning');
        return;
    }
    const modal = document.getElementById('chapterAudioHistoryModal');
    const body = document.getElementById('chapterAudioHistoryBody');
    modal.style.display = 'flex';
    body.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p class="mt-2">加载历史...</p></div>';

    (async () => {
        try {
            const data = await apiRequest(`/api/audio/chapter-history?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`, { silent: true });
            if (!data.success) {
                body.innerHTML = '<div class="history-empty">加载失败</div>';
                return;
            }

            const list = data.history || [];
            _chapterHistoryCache = list;

            if (list.length === 0) {
                body.innerHTML = `
                    <div class="history-empty">
                        <i class="fas fa-history" style="font-size:32px;"></i>
                        <p class="mt-2">暂无配音历史</p>
                        <p style="font-size:11px;margin-top:4px;">点击「整章配音」按钮生成本章音频</p>
                    </div>
                `;
                return;
            }

            body.innerHTML = `
                <div class="chapter-history-list">
                    ${list.map(h => _renderChapterHistoryCard(h)).join('')}
                </div>
            `;

            body.addEventListener('click', _handleChapterHistoryAction);
        } catch (e) {
            body.innerHTML = '<div class="history-empty">加载失败</div>';
        }
    })();
}

function _renderChapterHistoryCard(h) {
    const time = new Date((h.created_at || 0) * 1000).toLocaleString();
    const title = escapeHtml(h.chapter_title || `第 ${(h.chapter_index || 0) + 1} 章`);
    const audioUrl = h.audio_path ? `/api/media/file/content?path=${encodeURIComponent(h.audio_path)}` : '';
    const srtUrl = h.srt_path ? `/api/media/file/content?path=${encodeURIComponent(h.srt_path)}` : '';
    const audioDownloadUrl = h.audio_path ? `/api/media/download?path=${encodeURIComponent(h.audio_path)}` : '';
    const srtDownloadUrl = h.srt_path ? `/api/media/download?path=${encodeURIComponent(h.srt_path)}` : '';
    const zipDownloadUrl = `/api/audio/chapter-history/download?history_id=${h.id}`;

    return `
        <div class="chapter-history-card" data-history-id="${h.id}">
            <div class="ch-card-header">
                <div>
                    <div style="font-size:14px;font-weight:600;color:var(--neu-text);">${title}</div>
                    <div class="ch-card-time">${time}</div>
                </div>
            </div>
            <div class="ch-card-meta">
                <span><i class="fas fa-clock"></i> 时长 ${formatDuration(h.duration)}</span>
                <span><i class="fas fa-list"></i> ${h.line_count || 0} 条台词</span>
                <span><i class="fas fa-microphone"></i> 新生成 ${h.generated_count || 0} 条</span>
                <span><i class="fas fa-file-audio"></i> ${formatFileSize(h.file_size)}</span>
            </div>
            <div class="ch-card-actions">
                <button class="btn btn-outline-primary" data-action="toggle-player" data-audio-url="${audioUrl}">
                    <i class="fas fa-play"></i> 试听音频
                </button>
                <button class="btn btn-outline-primary" data-action="toggle-srt" data-srt-url="${srtUrl}">
                    <i class="fas fa-file-alt"></i> 预览文稿
                </button>
                <button class="btn btn-outline-secondary" data-action="download-audio" data-download-url="${audioDownloadUrl}" ${audioDownloadUrl ? '' : 'disabled'}>
                    <i class="fas fa-download"></i> 音频
                </button>
                <button class="btn btn-outline-secondary" data-action="download-srt" data-download-url="${srtDownloadUrl}" ${srtDownloadUrl ? '' : 'disabled'}>
                    <i class="fas fa-download"></i> 文稿
                </button>
                <button class="btn btn-primary" data-action="download-zip" data-download-url="${zipDownloadUrl}">
                    <i class="fas fa-file-archive"></i> 打包下载
                </button>
            </div>
            <div class="chapter-history-player" style="display:none;" data-player-container></div>
            <div class="chapter-history-srt-preview" style="display:none;" data-srt-container>加载中...</div>
        </div>
    `;
}

function _handleChapterHistoryAction(e) {
    const btn = e.target.closest('button');
    if (!btn) return;

    const action = btn.dataset.action;
    const card = btn.closest('.chapter-history-card');
    if (!card) return;

    if (action === 'toggle-player') {
        const audioUrl = btn.dataset.audioUrl;
        if (!audioUrl) {
            showToast('音频文件路径无效', 'error');
            return;
        }
        const container = card.querySelector('[data-player-container]');
        const isShown = container.style.display !== 'none';
        if (isShown) {
            container.style.display = 'none';
            container.innerHTML = '';
            btn.innerHTML = '<i class="fas fa-play"></i> 试听音频';
        } else {
            container.innerHTML = `<audio controls autoplay src="${audioUrl}">`;
            container.style.display = 'block';
            btn.innerHTML = '<i class="fas fa-stop"></i> 停止试听';
            const audio = container.querySelector('audio');
            audio.addEventListener('ended', () => {
                btn.innerHTML = '<i class="fas fa-play"></i> 试听音频';
            });
            audio.addEventListener('error', () => {
                showToast('音频加载失败', 'error');
            });
        }
    } else if (action === 'toggle-srt') {
        const srtUrl = btn.dataset.srtUrl;
        if (!srtUrl) {
            showToast('文稿文件路径无效', 'error');
            return;
        }
        const container = card.querySelector('[data-srt-container]');
        const isShown = container.style.display !== 'none';
        if (isShown) {
            container.style.display = 'none';
            container.innerHTML = '';
            btn.innerHTML = '<i class="fas fa-file-alt"></i> 预览文稿';
        } else {
            container.style.display = 'block';
            container.innerHTML = '<div style="color:var(--neu-text-muted);">加载文稿中...</div>';
            btn.innerHTML = '<i class="fas fa-eye-slash"></i> 隐藏文稿';
            fetch(srtUrl)
                .then(resp => {
                    if (!resp.ok) throw new Error('文稿加载失败');
                    return resp.text();
                })
                .then(text => {
                    container.innerHTML = _renderSrtPreview(text);
                })
                .catch(err => {
                    container.innerHTML = `<div style="color:#ef4444;">文稿加载失败: ${escapeHtml(err.message)}</div>`;
                });
        }
    } else if (action === 'download-audio' || action === 'download-srt' || action === 'download-zip') {
        const url = btn.dataset.downloadUrl;
        if (!url) {
            showToast('下载链接无效', 'error');
            return;
        }
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

function _renderSrtPreview(srtText) {
    if (!srtText) return '<div style="color:var(--neu-text-muted);">空文稿</div>';
    const blocks = srtText.trim().split(/\r?\n\r?\n/);
    const lines = blocks.map(block => {
        const parts = block.split(/\r?\n/);
        if (parts.length < 2) return '';
        const idx = parts[0].trim();
        const time = parts[1] || '';
        const content = parts.slice(2).join(' ');
        if (!idx || !/^\d+$/.test(idx)) return '';
        return `<div class="srt-line"><span class="srt-idx">#${escapeHtml(idx)}</span><span class="srt-time">${escapeHtml(time)}</span>${escapeHtml(content)}</div>`;
    }).filter(Boolean);
    return lines.length ? lines.join('') : `<div style="white-space:pre-wrap;">${escapeHtml(srtText)}</div>`;
}

function hideChapterAudioHistory() {
    const body = document.getElementById('chapterAudioHistoryBody');
    body.removeEventListener('click', _handleChapterHistoryAction);
    body.querySelectorAll('audio').forEach(a => {
        try { a.pause(); } catch (e) {}
    });
    document.getElementById('chapterAudioHistoryModal').style.display = 'none';
}