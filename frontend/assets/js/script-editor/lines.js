function renderChapterList() {
    const list = document.getElementById('chapterList');
    document.getElementById('chapterCountBadge').textContent = state.chapters.length;
    list.innerHTML = '';
    if (state.chapters.length === 0) {
        list.innerHTML = '<div class="loading-state" style="padding: 20px;"><p>暂无章节</p></div>';
        return;
    }
    state.chapters.forEach(ch => {
        const item = document.createElement('div');
        item.className = 'chapter-item';
        if (ch.chapter_index === state.currentChapterIndex) item.classList.add('active');
        item.dataset.index = ch.chapter_index;
        const countBadge = ch.line_count > 0
                ? `<span class="line-count">${ch.line_count}句</span>` : '';
        const editBtn = `<button class="chapter-item-edit-btn" onclick="event.stopPropagation(); editChapterTitle(${ch.chapter_index})" title="编辑标题"><i class="fas fa-pen"></i></button>`;
        const deleteBtn = `<button class="chapter-item-delete-btn" onclick="event.stopPropagation(); deleteChapter(${ch.chapter_index})" title="删除章节"><i class="fas fa-trash"></i></button>`;
        item.innerHTML = `<span style="overflow:hidden;text-overflow:ellipsis;">${escapeHtml(ch.chapter_title)}</span>${countBadge}${editBtn}${deleteBtn}`;
        item.onclick = () => selectChapter(ch.chapter_index);
        list.appendChild(item);
    });
}

function updateClearButton() {
    const btn = document.getElementById('clearChapterBtn');
    if (!btn) return;
    const ch = state.chapters.find(c => c.chapter_index === state.currentChapterIndex);
    const hasLines = ch && ch.line_count > 0;
    btn.classList.toggle('hidden', !hasLines);
}

async function clearCurrentChapter() {
    if (!state.scriptId || state.currentChapterIndex < 0) return;
    const ch = state.chapters.find(c => c.chapter_index === state.currentChapterIndex);
    const chapterTitle = ch ? ch.chapter_title : '当前章节';
    if (!confirm(`确定清空「${chapterTitle}」的台词吗？此操作不可撤销。`)) return;
    try {
        const data = await apiRequest(
            `/api/books/scripts/chapters/clear?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`,
            { method: 'POST', errorPrefix: '清空失败' }
        );
        if (data.success) {
            showToast(data.message, 'success');
            if (ch) ch.line_count = 0;
            renderChapterList();
            state.currentLines = [];
            renderLines();
            updateClearButton();
        } else {
            showToast(data.detail || data.message || '清空失败', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

async function loadOriginalText(chapterIndex) {
    if (!state.scriptId) return;
    const bodyEl = document.getElementById('originalTextBody');
    bodyEl.value = '';
    bodyEl.placeholder = '加载原文...';
    try {
        const data = await apiRequest(
            `/api/books/scripts/chapters/content?script_id=${state.scriptId}&chapter_index=${chapterIndex}`,
            { silent: true }
        );
        if (data.success && data.content !== undefined) {
            bodyEl.value = data.content;
            bodyEl.placeholder = '（空）';
        } else {
            bodyEl.value = '';
            bodyEl.placeholder = '原文加载失败';
        }
    } catch (e) {
        bodyEl.value = '';
        bodyEl.placeholder = '原文加载失败';
    }
}

async function saveChapterContent() {
    if (!state.scriptId || state.currentChapterIndex < 0) return;
    const bodyEl = document.getElementById('originalTextBody');
    const btn = document.getElementById('saveOriginalBtn');
    const content = bodyEl.value;
    btn.classList.add('saving');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 保存中';
    try {
        const formData = new FormData();
        formData.append('content', content);
        const data = await apiRequest(
            `/api/books/scripts/chapters/content?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`,
            { method: 'PUT', body: formData, errorPrefix: '保存失败' }
        );
        if (data.success) {
            showToast('章节内容已保存', 'success');
        } else {
            showToast(data.detail || '保存失败', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    } finally {
        btn.classList.remove('saving');
        btn.innerHTML = '<i class="fas fa-save"></i> 保存';
    }
}

async function editChapterTitle(chapterIndex) {
    if (!state.scriptId) return;
    const ch = state.chapters.find(c => c.chapter_index === chapterIndex);
    if (!ch) return;
    const newTitle = prompt('请输入新的章节标题：', ch.chapter_title || '');
    if (newTitle === null) return;
    const trimmed = newTitle.trim();
    if (!trimmed) {
        showToast('章节标题不能为空', 'warning');
        return;
    }
    if (trimmed === ch.chapter_title) return;
    try {
        const data = await apiRequest('/api/books/scripts/chapters/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script_id: state.scriptId,
                chapter_index: chapterIndex,
                title: trimmed,
            }),
            errorPrefix: '重命名失败'
        });
        if (data.success) {
            ch.chapter_title = data.title || trimmed;
            renderChapterList();
            if (state.currentChapterIndex === chapterIndex) {
                const titleEl = document.getElementById('currentChapterTitle');
                if (titleEl) titleEl.textContent = ch.chapter_title;
            }
            showToast(data.message || '章节标题已更新', 'success');
        } else {
            showToast(data.detail || '更新失败', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

async function deleteChapter(chapterIndex) {
    if (!state.scriptId) return;
    const ch = state.chapters.find(c => c.chapter_index === chapterIndex);
    const title = ch ? ch.chapter_title : `章节${chapterIndex + 1}`;
    if (!confirm(`确定删除「${title}」吗？\n该章节的文件和台词将被一并删除，此操作不可撤销。`)) return;
    try {
        const data = await apiRequest(
            `/api/books/scripts/chapters?script_id=${state.scriptId}&chapter_index=${chapterIndex}`,
            { method: 'DELETE', errorPrefix: '删除失败' }
        );
        if (data.success) {
            showToast(data.message, 'success');
            await loadScriptInfo();
            renderChapterList();
            if (state.currentChapterIndex === chapterIndex) {
                state.currentChapterIndex = -1;
                state.currentLines = [];
                renderLines();
                const bodyEl = document.getElementById('originalTextBody');
                if (bodyEl) bodyEl.value = '';
            }
        } else {
            showToast(data.detail || '删除失败', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

async function showAddChapterModal() {
    if (!state.scriptId) return;
    
    const newIndex = state.chapters.length > 0 
        ? Math.max(...state.chapters.map(c => c.chapter_index)) + 1 
        : 0;
    const title = `第${newIndex}章`;
    
    try {
        const formData = new FormData();
        formData.append('title', title);
        formData.append('content', '');
        const data = await apiRequest(
            `/api/books/scripts/chapters?script_id=${state.scriptId}`,
            { method: 'POST', body: formData, errorPrefix: '添加章节失败' }
        );
        if (data.success) {
            showToast(data.message, 'success');
            await loadScriptInfo();
            renderChapterList();
            await selectChapter(newIndex);
        } else {
            showToast(data.detail || '添加失败', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

async function addChapter(chapterIndex) {
    if (!state.scriptId) return;
    
    const title = `第${chapterIndex + 1}章`;
    
    try {
        const formData = new FormData();
        formData.append('title', title);
        formData.append('content', '');
        const data = await apiRequest(
            `/api/books/scripts/chapters?script_id=${state.scriptId}`,
            { method: 'POST', body: formData, errorPrefix: '新增章节失败' }
        );
        if (data.success) {
            await loadScriptInfo();
            renderChapterList();
        }
    } catch (e) {
        console.error('添加章节失败:', e);
    }
}

async function selectChapter(chapterIndex) {
    state.currentChapterIndex = chapterIndex;
    state.selectedLineId = null;
    document.querySelectorAll('.chapter-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.index) === chapterIndex);
    });
    const ch = state.chapters.find(c => c.chapter_index === chapterIndex);
    document.getElementById('currentChapterTitle').textContent = ch ? ch.chapter_title : '';
    updateClearButton();
    if (state.showOriginalText && state.scriptData) {
        loadOriginalText(chapterIndex);
    }
    const listEl = document.getElementById('linesList');
    listEl.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p class="mt-2">加载语句...</p></div>';
    try {
        const data = await apiRequest(`/api/books/scripts/lines?script_id=${state.scriptId}&chapter_index=${chapterIndex}`, {
            silent: true
        });
        if (data.success) {
            state.currentLines = data.lines;
            await matchAudioHistoryForLines(state.currentLines);
            renderLines();
            updatePlayerButtons();
        }
    } catch (e) {
        console.error('加载台词失败:', e);
        listEl.innerHTML = '<div class="loading-state"><p>加载失败</p></div>';
    }
}

function createLinePlaceholder() {
    const div = document.createElement('div');
    div.className = 'line-placeholder generation-loading';
    div.innerHTML = `
        <div class="skeleton ph-drag"></div>
        <div class="skeleton ph-number" style="height: 16px;"></div>
        <div class="ph-body">
            <div class="ph-header">
                <div class="skeleton ph-role"></div>
                <div class="skeleton ph-instruction"></div>
            </div>
            <div class="skeleton ph-content"></div>
            <div class="skeleton ph-content-short"></div>
        </div>
        <div class="ph-actions">
            <div class="skeleton ph-action"></div>
            <div class="skeleton ph-action"></div>
        </div>
    `;
    return div;
}

function buildLineElement(line, idx) {
    const div = document.createElement('div');
    div.className = 'script-line';
    if (line.audio_path) div.classList.add('has-audio');
    div.dataset.index = idx;
    div.dataset.lineId = line.id;
    if (idx === state.currentPlayingIndex) div.classList.add('playing');
    if (line.id === state.selectedLineId) {
        div.classList.add('selected');
    }
    
    div.addEventListener('click', (e) => {
        if (e.target.closest('.line-action-btn') || e.target.closest('.line-drag-handle')) {
            return;
        }
        if (div.classList.contains('selected')) {
            if (e.target.closest('.role-picker-btn') || e.target.closest('.instruction-input') ||
                e.target.closest('.instruction-quick-btn') || e.target.closest('.instruction-quick-dropdown') ||
                e.target.closest('.tone-input') || e.target.closest('.line-content') ||
                e.target.closest('.tag-toolbar') || e.target.closest('.line-audio-editor')) {
                return;
            }
            return;
        }
        document.querySelectorAll('.script-line').forEach(el => {
            el.classList.remove('selected');
            const c = el.querySelector('.line-content');
            if (c) c.setAttribute('contenteditable', 'false');
        });
        div.classList.add('selected');
        state.selectedLineId = line.id;
        const contentEl = div.querySelector('.line-content');
        if (contentEl) contentEl.setAttribute('contenteditable', 'true');
        expandLineAudioEditor(line.id);
        // 根据台词行角色同步选中角色列表
        if (line.role && state.selectedRole !== line.role) {
            selectCharacter(line.role);
        }
    });

    const roleColorIdx = !line.role ? -1 : (line.role === '旁白' ? -1 : Math.abs(hashString(line.role)) % AVATAR_COLORS.length);
    const roleBg = !line.role
        ? 'transparent'
        : line.role === '旁白'
            ? 'linear-gradient(135deg, #94a3b8, #475569)'
            : AVATAR_COLORS[roleColorIdx];

    div.innerHTML = `
        <div class="line-drag-handle" title="拖拽排序">
            <i class="fas fa-grip-vertical"></i>
        </div>
        <div class="line-number">${idx + 1}</div>
        <div class="line-body">
            <div class="line-header">
                <div class="line-header-field role-field">
                    <span class="audio-status-dot" id="audioStatus-${line.id}" data-status="${line.audio_path ? 'generated' : 'none'}"></span>
                    <button type="button" class="role-picker-btn ${!line.role ? 'empty' : ''}" 
                            style="${line.role ? `background: ${roleBg}; color: #fff;` : ''}"
                            onclick="openRolePickerForLine(${line.id})" 
                            title="${line.role ? '点击切换配音角色' : '点击选择配音角色'}">
                        <span class="role-picker-text">${escapeHtml(line.role || '选择配音角色')}</span>
                        <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
                <div class="line-header-field tone-field">
                    <input type="text" class="tone-input" value="${escapeHtml(line.tone || '')}"
                           onchange="onToneChange(this, ${line.id})"
                           onkeydown="if(event.key==='Enter')this.blur()"
                           placeholder="语气样例"
                           title="指定合适的语气样例可提升配音效果">
                    <span class="field-display tone-display">${escapeHtml(line.tone || '')}</span>
                </div>
                <div class="line-header-field instruction-field">
                    <input type="text" class="instruction-input" value="${escapeHtml(line.instruction || '')}"
                           onchange="onInstructionChange(this, ${line.id})"
                           onkeydown="if(event.key==='Enter')this.blur()"
                           placeholder="指令"
                           title="语气指令，如：请非常开心地说一句话">
                    <i class="fas fa-bolt instruction-quick-btn"
                       onclick="toggleInstructionQuickMenu(event, ${line.id})"
                       title="快捷指令"></i>
                    <span class="field-display instruction-display">${escapeHtml(line.instruction || '')}</span>
                </div>
                <div class="line-actions">
                    <button class="line-action-btn insert-above-btn" data-action="add-above" onclick="addLineAbove(${idx})" title="在上方增加">
                        <span class="insert-icon"><span class="insert-line"></span><i class="fas fa-plus"></i></span>
                    </button>
                    <button class="line-action-btn insert-below-btn" data-action="add-below" onclick="addLineBelow(${idx})" title="在下方增加">
                        <span class="insert-icon"><i class="fas fa-plus"></i><span class="insert-line"></span></span>
                    </button>
                    <button class="line-action-btn danger" onclick="deleteLine(${line.id})" title="删除">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="line-content-wrapper">
                <div class="tag-toolbar">
                    <button type="button" class="tag-insert-btn" onclick="toggleTagMenu(this, ${line.id})">
                        <i class="fas fa-tags" style="font-size:10px;"></i> 人物音效
                    </button>
                    <button type="button" class="tag-insert-btn" onclick="locateInOriginalText(${line.id})" title="在章节原文中定位并高亮该台词">
                        <i class="fas fa-search-location" style="font-size:10px;"></i> 定位原文
                    </button>
                </div>
                <div class="line-content" contenteditable="${line.id === state.selectedLineId ? 'true' : 'false'}" data-line-id="${line.id}"
                     onfocus="onLineContentFocus(this)"
                     onblur="onLineContentBlur(this, ${line.id})"
                     onkeydown="onLineContentKeydown(event)">${renderContentWithTags(line.content)}</div>
            </div>
        </div>
        <div class="line-audio-editor" id="audioEditor-${line.id}">
            <div class="audio-editor-toolbar">
                <div class="audio-editor-toolbar-title">
                    <i class="fas fa-wave-square"></i> 音频编辑
                </div>
                <div class="audio-editor-toolbar-actions">
                    <div class="seed-input-wrapper">
                        <span class="seed-label">种子</span>
                        <input type="number" class="seed-input" id="seedInput-${line.id}" min="0" max="100000000"
                               value="${line.seed || ''}"
                               onchange="onLineSeedChange(${line.id}, this.value)"
                               placeholder="0">
                    </div>
                    <button class="audio-icon-btn primary" onclick="generateLineAudio(${line.id})" id="generateBtn-${line.id}" title="生成配音">
                        <i class="fas fa-microphone"></i>
                    </button>
                    <button class="audio-icon-btn" onclick="showAudioHistory(${line.id})" id="historyBtn-${line.id}" title="查看生成历史">
                        <i class="fas fa-history"></i>
                    </button>
                </div>
            </div>
            <div class="line-waveform-wrapper ${line.audio_path ? '' : 'no-audio'}" id="waveformWrapper-${line.id}">
                <div class="line-waveform-container" id="waveformContainer-${line.id}">
                    <canvas id="waveformCanvas-${line.id}"></canvas>
                </div>
                <div class="line-waveform-progress" id="waveformProgress-${line.id}" style="width:0;"></div>
                <div class="line-waveform-range" id="waveformRange-${line.id}" style="left:0;right:0;display:none;"></div>
                <div class="line-waveform-handle" id="rangeStartHandle-${line.id}" style="left:0;display:none;" data-handle="start"></div>
                <div class="line-waveform-handle" id="rangeEndHandle-${line.id}" style="left:100%;display:none;" data-handle="end"></div>
                <div class="line-waveform-playhead" id="waveformPlayhead-${line.id}" style="left:0;display:none;"></div>
                <div class="line-waveform-overlay" id="waveformOverlay-${line.id}" style="${line.audio_path ? 'display:none;' : ''}">
                    <div class="overlay-content">
                        <i class="fas fa-volume-mute"></i>
                        <span>请先生成配音</span>
                    </div>
                </div>
            </div>
            <div class="line-waveform-timebar ${line.audio_path ? '' : 'no-audio'}">
                <span id="waveformCurrentTime-${line.id}">00:00</span>
                <div class="time-range">
                    <span id="rangeStartTime-${line.id}">00:00</span>
                    <span>~</span>
                    <span id="rangeEndTime-${line.id}">00:00</span>
                </div>
                <span id="waveformTotalTime-${line.id}">00:00</span>
            </div>
            <div class="line-audio-params ${line.audio_path ? '' : 'no-audio'}">
                <div class="line-audio-toggle">
                    <label class="audio-toggle-switch">
                        <input type="checkbox" id="audioAdjustToggle-${line.id}"
                               ${line.audio_adjust_enabled ? 'checked' : ''}
                               ${line.audio_path ? '' : 'disabled'}
                               onchange="onAudioAdjustToggle(${line.id}, this.checked)">
                        <span class="audio-toggle-slider"></span>
                    </label>
                    <span class="audio-toggle-label">调整</span>
                </div>
                <div class="line-param">
                    <span class="line-param-label">音量</span>
                    <input type="range" class="line-param-slider" id="volumeSlider-${line.id}" min="0" max="100" step="1" value="${Math.round((line.audio_volume || 1) * 100)}"
                           oninput="updateLineAudioDisplay(${line.id}, 'volume', this.value)"
                           onchange="onLineAudioParamChange(${line.id}, 'volume', this.value)"
                           ${(line.audio_path && line.audio_adjust_enabled) ? '' : 'disabled'}>
                    <span class="line-param-value" id="volumeValue-${line.id}">${Math.round((line.audio_volume || 1) * 100)}%</span>
                </div>
                <div class="line-param">
                    <span class="line-param-label">音调</span>
                    <input type="range" class="line-param-slider" id="pitchSlider-${line.id}" min="-12" max="12" step="1" value="${line.audio_pitch || 0}"
                           oninput="updateLineAudioDisplay(${line.id}, 'pitch', this.value)"
                           onchange="onLineAudioParamChange(${line.id}, 'pitch', this.value)"
                           ${(line.audio_path && line.audio_adjust_enabled) ? '' : 'disabled'}>
                    <span class="line-param-value" id="pitchValue-${line.id}">${line.audio_pitch || 0}</span>
                </div>
                <div class="line-param">
                    <span class="line-param-label">淡入</span>
                    <input type="range" class="line-param-slider" id="fadeInSlider-${line.id}" min="0" max="3" step="0.1" value="${line.fade_in || 0}"
                           oninput="updateLineAudioDisplay(${line.id}, 'fadeIn', this.value)"
                           onchange="onLineAudioParamChange(${line.id}, 'fadeIn', this.value)"
                           ${(line.audio_path && line.audio_adjust_enabled) ? '' : 'disabled'}>
                    <span class="line-param-value" id="fadeInValue-${line.id}">${(line.fade_in || 0).toFixed(1)}s</span>
                </div>
                <div class="line-param">
                    <span class="line-param-label">淡出</span>
                    <input type="range" class="line-param-slider" id="fadeOutSlider-${line.id}" min="0" max="3" step="0.1" value="${line.fade_out || 0}"
                           oninput="updateLineAudioDisplay(${line.id}, 'fadeOut', this.value)"
                           onchange="onLineAudioParamChange(${line.id}, 'fadeOut', this.value)"
                           ${(line.audio_path && line.audio_adjust_enabled) ? '' : 'disabled'}>
                    <span class="line-param-value" id="fadeOutValue-${line.id}">${(line.fade_out || 0).toFixed(1)}s</span>
                </div>
                <div class="line-param-reset">
                    <button class="audio-icon-btn reset-params-btn" onclick="resetLineAudioParams(${line.id})"
                            id="resetBtn-${line.id}" title="重置参数和播放范围"
                            ${(line.audio_path && line.audio_adjust_enabled) ? '' : 'disabled'}>
                        <i class="fas fa-undo"></i>
                    </button>
                </div>
                <div class="line-param-play-btn">
                    ${line.audio_path ? `
                    <button class="audio-icon-btn play-inline-btn" onclick="playLineAudio(${line.id})" id="playBtn-${line.id}" title="播放">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="audio-icon-btn play-inline-btn" onclick="stopLineAudio(${line.id})" id="stopBtn-${line.id}" title="停止" style="display:none;">
                        <i class="fas fa-stop"></i>
                    </button>
                    ` : `
                    <button class="audio-icon-btn play-inline-btn" disabled title="请先生成配音">
                        <i class="fas fa-play"></i>
                    </button>
                    `}
                </div>
            </div>
        </div>
    `;
    setupDragAndDrop(div, idx);
    setupLineWaveform(line, div);
    return div;
}

function renderLines() {
    const listEl = document.getElementById('linesList');
    const prevSelectedLineId = state.selectedLineId;
    const prevExpandedEditorId = document.querySelector('.line-audio-editor.expanded');
    const prevExpandedLineId = prevExpandedEditorId ? parseInt(prevExpandedEditorId.id.replace('audioEditor-', '')) : null;

    if (state.currentLines.length === 0) {
        const ch = state.chapters.find(c => c.chapter_index === state.currentChapterIndex);
        const isDisabled = state.scriptData && state.scriptData.status === 'running';
        listEl.innerHTML = `
            <div class="loading-state" style="padding: 40px 20px;">
                <i class="fas fa-file-alt" style="font-size: 48px;color:var(--neu-dark);"></i>
                <p class="mt-3" style="font-size: 16px;color:var(--neu-text);">本章暂无台词</p>
                <p class="text-muted" style="font-size: 13px;">点击下方按钮生成 ${ch ? ch.chapter_title : ''} 的台词</p>
                <button class="btn btn-primary mt-4" onclick="startChapterGeneration(${state.currentChapterIndex})" id="generateBtn" ${isDisabled ? 'disabled' : ''}>
                    <i class="fas fa-magic"></i> 生成台词
                </button>
            </div>
        `;
        return;
    }
    listEl.innerHTML = '';
    state.currentLines.forEach((line, idx) => {
        listEl.appendChild(buildLineElement(line, idx));
    });
    if (state.scriptData && state.scriptData.status === 'running' && (state.generatingChapterIndex === -1 || state.generatingChapterIndex === state.currentChapterIndex)) {
        listEl.appendChild(createLinePlaceholder());
    }

    if (prevSelectedLineId && state.currentLines.some(l => l.id === prevSelectedLineId)) {
        const div = listEl.querySelector(`.script-line[data-line-id="${prevSelectedLineId}"]`);
        if (div) {
            div.classList.add('selected');
            const contentEl = div.querySelector('.line-content');
            if (contentEl) contentEl.setAttribute('contenteditable', 'true');
        }
    }

    if (prevExpandedLineId && state.currentLines.some(l => l.id === prevExpandedLineId)) {
        expandLineAudioEditor(prevExpandedLineId);
    }
}

function reorderLinesDOM(fromIndex, toIndex) {
    const listEl = document.getElementById('linesList');
    const items = Array.from(listEl.children);
    const fromEl = items[fromIndex];
    if (!fromEl) return;
    listEl.removeChild(fromEl);
    if (toIndex >= items.length - 1) {
        listEl.appendChild(fromEl);
    } else {
        listEl.insertBefore(fromEl, listEl.children[toIndex]);
    }
}

function updateLineNumbers() {
    const listEl = document.getElementById('linesList');
    const items = listEl.querySelectorAll('.script-line');
    items.forEach((item, idx) => {
        const numEl = item.querySelector('.line-number');
        if (numEl) numEl.textContent = idx + 1;
        item.dataset.index = idx;
    });
}

function setupDragAndDrop(el, idx) {
    const handle = el.querySelector('.line-drag-handle');
    if (!handle) return;

    handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        startDrag(el, idx, e);
    });
}

function startDrag(el, idx, e) {
    state.dragState.isDragging = true;
    state.dragState.dragIndex = idx;
    state.dragState.dragLineId = state.currentLines[idx].id;
    state.dragState.startY = e.clientY;
    state.dragState.dragEl = el;
    const style = getComputedStyle(el);
    state.dragState.dragHeight = el.offsetHeight + parseInt(style.marginBottom);
    const listEl = document.getElementById('linesList');
    const items = Array.from(listEl.querySelectorAll('.script-line'));
    state.dragState.itemPositions = items.map(item => {
        const rect = item.getBoundingClientRect();
        return rect.top + rect.height / 2;
    });
    el.classList.add('dragging');

    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('mouseup', onDragEnd);
}

function onDragMove(e) {
    if (!state.dragState.isDragging) return;

    const deltaY = e.clientY - state.dragState.startY;
    if (state.dragState.dragEl) {
        state.dragState.dragEl.style.transform = `translateY(${deltaY}px)`;
    }

    const positions = state.dragState.itemPositions;
    let targetIndex = -1;
    for (let i = 0; i < positions.length; i++) {
        if (i === state.dragState.dragIndex) continue;
        if (e.clientY < positions[i]) {
            targetIndex = i;
            break;
        }
    }
    if (targetIndex === -1) {
        targetIndex = positions.length;
    }

    const listEl = document.getElementById('linesList');
    const items = Array.from(listEl.querySelectorAll('.script-line'));
    const dragIdx = state.dragState.dragIndex;
    const dragHeight = state.dragState.dragHeight;

    items.forEach((item, idx) => {
        if (item === state.dragState.dragEl) return;
        if (targetIndex > dragIdx + 1 && idx > dragIdx && idx < targetIndex) {
            item.style.transform = `translateY(${-dragHeight}px)`;
        } else if (targetIndex <= dragIdx && idx >= targetIndex && idx < dragIdx) {
            item.style.transform = `translateY(${dragHeight}px)`;
        } else {
            item.style.transform = '';
        }
    });

    items.forEach(i => i.classList.remove('drag-over'));
    if (targetIndex !== dragIdx + 1 && targetIndex < items.length && items[targetIndex] !== state.dragState.dragEl) {
        items[targetIndex].classList.add('drag-over');
    }

    if (targetIndex !== dragIdx + 1) {
        state.dragState.targetIndex = targetIndex;
    } else {
        state.dragState.targetIndex = undefined;
    }
}

function onDragEnd(e) {
    if (!state.dragState.isDragging) return;

    state.dragState.isDragging = false;

    const listEl = document.getElementById('linesList');
    const items = listEl.querySelectorAll('.script-line');
    items.forEach(i => {
        i.style.transform = '';
        i.classList.remove('dragging');
        i.classList.remove('drag-over');
    });

    document.removeEventListener('mousemove', onDragMove);
    document.removeEventListener('mouseup', onDragEnd);

    if (state.dragState.dragLineId !== null && state.dragState.targetIndex !== undefined) {
        const line = state.currentLines[state.dragState.dragIndex];
        state.currentLines.splice(state.dragState.dragIndex, 1);
        let insertAt = state.dragState.targetIndex;
        if (state.dragState.targetIndex > state.dragState.dragIndex) {
            insertAt = state.dragState.targetIndex - 1;
        }
        state.currentLines.splice(insertAt, 0, line);

        reorderLinesDOM(state.dragState.dragIndex, insertAt);
        updateLineNumbers();
        saveReorder();
    }

    state.dragState = {
        isDragging: false,
        dragIndex: -1,
        dragLineId: null,
        startY: 0,
        dragEl: null,
        dragHeight: 0,
        targetIndex: undefined,
        itemPositions: []
    };
}

async function saveReorder() {
    if (!state.scriptId || !state.currentLines.length) return;

    const lineMap = new Map(state.currentLines.map((line, idx) => [line.id, idx]));
    const dragLineId = state.dragState.dragLineId;
    const dragIndex = lineMap.get(dragLineId);

    if (dragIndex === undefined) return;

    const targetPrevId = dragIndex > 0 ? state.currentLines[dragIndex - 1].id : null;
    const targetNextId = dragIndex < state.currentLines.length - 1 ? state.currentLines[dragIndex + 1].id : null;

    try {
        const data = await apiRequest(`/api/books/scripts/lines/reorder?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                line_id: dragLineId,
                chapter_index: state.currentChapterIndex,
                target_prev_id: targetPrevId,
                target_next_id: targetNextId
            }),
            errorPrefix: '排序失败'
        });
        if (!data.success) {
            showToast('排序保存失败', 'error');
        }
    } catch (e) {
        console.error('保存排序失败:', e);
        showToast('排序保存失败', 'error');
    }
}

async function updateLine(lineId, updates) {
    try {
        const data = await apiRequest(`/api/books/scripts/lines?script_id=${state.scriptId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lines: [{ id: lineId, ...updates }] }),
            silent: true
        });
        if (!data.success) {
            console.error('保存失败:', data);
        }
    } catch (e) {
        console.error('保存失败:', e);
    }
}

function showInstructionQuickMenu(event, lineId) {
    event.stopPropagation();
    const btn = event.currentTarget;
    const field = btn.closest('.instruction-field');
    if (!field) return;

    document.querySelectorAll('.instruction-quick-dropdown').forEach(d => d.remove());

    const dropdown = document.createElement('div');
    dropdown.className = 'instruction-quick-dropdown';
    dropdown.innerHTML = QUICK_INSTRUCTIONS.map(item =>
        `<div class="quick-item" onclick="applyQuickInstruction(${lineId}, '${item.text.replace(/'/g, "\\'")}')">
            <div class="quick-label">${item.label}</div>
            <div class="quick-text">${item.text}</div>
        </div>`
    ).join('');
    field.appendChild(dropdown);
}

function toggleInstructionQuickMenu(event, lineId) {
    event.stopPropagation();
    const btn = event.currentTarget;
    const field = btn.closest('.instruction-field');
    if (!field) return;

    const dropdown = field.querySelector('.instruction-quick-dropdown');
    if (dropdown) {
        dropdown.remove();
        return;
    }
    showInstructionQuickMenu(event, lineId);
}

function closeInstructionQuickMenus() {
    document.querySelectorAll('.instruction-quick-dropdown').forEach(d => d.remove());
}

function applyQuickInstruction(lineId, text) {
    closeInstructionQuickMenus();

    const line = state.currentLines.find(l => l.id === lineId);
    if (!line) return;

    line.instruction = text;
    updateLine(lineId, { instruction: text });

    const lineEl = document.querySelector(`.script-line[data-line-id="${lineId}"]`);
    if (lineEl) {
        const input = lineEl.querySelector('.instruction-input');
        if (input) input.value = text;
        const display = lineEl.querySelector('.instruction-display');
        if (display) display.textContent = text;
    }
}

function renderContentWithTags(text) {
    if (!text) return '';
    const escaped = escapeHtml(text);
    return escaped.replace(
        SOUND_TAG_REGEX,
        (_, tag) => `<span class="sound-tag" contenteditable="false" data-tag="${tag}">${SOUND_TAGS[tag]}</span>`
    );
}

function extractContentFromEditor(el) {
    let result = '';
    for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
            result += node.textContent.replace(/\u200B/g, '');
        } else if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('sound-tag')) {
            result += '[' + node.dataset.tag + ']';
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            result += node.textContent.replace(/\u200B/g, '');
        }
    }
    return result;
}

function onLineContentFocus(el) {
    state.lastFocusedEditor = el;
}

function onLineContentBlur(el, lineId) {
    const selection = window.getSelection();
    if (selection.rangeCount > 0 && el.contains(selection.anchorNode)) {
        state.lastSavedRange = selection.getRangeAt(0).cloneRange();
    }
    const newText = extractContentFromEditor(el).trim();
    const line = state.currentLines.find(l => l.id === lineId);
    if (line && line.content !== newText) {
        line.content = newText;
        updateLine(lineId, { content: newText });
        matchAudioHistoryForLines([line]).then(() => {
            updateLineAudioEditorDisplay(lineId);
        });
    }
}

function onLineContentKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        event.target.blur();
        return;
    }
    if (event.key === 'Backspace' || event.key === 'Delete') {
        handleTagDeletion(event);
    }
}

function handleTagDeletion(event) {
    const selection = window.getSelection();
    if (!selection.isCollapsed) return;
    const range = selection.getRangeAt(0);
    const container = range.startContainer;
    const offset = range.startOffset;

    if (event.key === 'Backspace') {
        const tag = getTagBeforeCursor(container, offset);
        if (tag) {
            event.preventDefault();
            tag.remove();
            saveAndDispatch(event.target);
        }
    } else if (event.key === 'Delete') {
        const tag = getTagAfterCursor(container, offset);
        if (tag) {
            event.preventDefault();
            tag.remove();
            saveAndDispatch(event.target);
        }
    }
}

function getTagBeforeCursor(node, offset) {
    if (node.nodeType === Node.TEXT_NODE) {
        if (offset > 0) return null;
        const prev = node.previousSibling;
        if (prev && prev.nodeType === Node.ELEMENT_NODE && prev.classList.contains('sound-tag')) {
            return prev;
        }
    } else if (node.classList && node.classList.contains('line-content')) {
        const child = node.childNodes[offset - 1];
        if (child && child.nodeType === Node.ELEMENT_NODE && child.classList.contains('sound-tag')) {
            return child;
        }
    }
    return null;
}

function getTagAfterCursor(node, offset) {
    if (node.nodeType === Node.TEXT_NODE) {
        if (offset < node.textContent.length) return null;
        const next = node.nextSibling;
        if (next && next.nodeType === Node.ELEMENT_NODE && next.classList.contains('sound-tag')) {
            return next;
        }
    } else if (node.classList && node.classList.contains('line-content')) {
        const child = node.childNodes[offset];
        if (child && child.nodeType === Node.ELEMENT_NODE && child.classList.contains('sound-tag')) {
            return child;
        }
    }
    return null;
}

function saveAndDispatch(editorEl) {
    const lineContent = editorEl.closest('.line-content');
    if (!lineContent) return;
    const lineId = parseInt(lineContent.dataset.lineId);
    const newText = extractContentFromEditor(lineContent).trim();
    const line = state.currentLines.find(l => l.id === lineId);
    if (line && line.content !== newText) {
        line.content = newText;
        updateLine(lineId, { content: newText });
    }
}

function toggleTagMenu(btn, lineId) {
    const wrapper = btn.closest('.line-content-wrapper');
    let dropdown = wrapper.querySelector('.tag-dropdown');
    if (dropdown) {
        dropdown.remove();
        return;
    }
    document.querySelectorAll('.tag-dropdown').forEach(d => d.remove());

    dropdown = document.createElement('div');
    dropdown.className = 'tag-dropdown';
    dropdown.innerHTML = Object.entries(SOUND_TAGS).map(([tag, label]) =>
                        `<div class="tag-dropdown-item" onclick="insertSoundTag('${tag}', ${lineId})">
            <span>${label}</span>
            <span class="tag-code">[${tag}]</span>
        </div>`
    ).join('');
    wrapper.appendChild(dropdown);

    const onOutsideClick = (e) => {
        if (!dropdown.contains(e.target) && e.target !== btn) {
            dropdown.remove();
            document.removeEventListener('mousedown', onOutsideClick, true);
        }
    };
    setTimeout(() => document.addEventListener('mousedown', onOutsideClick, true), 0);
}

function insertSoundTag(tagName, lineId) {
    document.querySelectorAll('.tag-dropdown').forEach(d => d.remove());

    const editor = document.querySelector(`.line-content[data-line-id="${lineId}"]`);
    if (!editor) return;

    editor.focus();

    const selection = window.getSelection();
    let range;
    if (state.lastSavedRange && editor.contains(state.lastSavedRange.startContainer)) {
        range = state.lastSavedRange;
    } else {
        range = document.createRange();
        range.selectNodeContents(editor);
        range.collapse(false);
    }
    selection.removeAllRanges();
    selection.addRange(range);

    const tagSpan = document.createElement('span');
    tagSpan.className = 'sound-tag';
    tagSpan.contentEditable = 'false';
    tagSpan.dataset.tag = tagName;
    tagSpan.textContent = SOUND_TAGS[tagName];

    range.deleteContents();
    range.insertNode(tagSpan);

    const spacer = document.createTextNode('\u200B');
    range.setStartAfter(tagSpan);
    range.insertNode(spacer);
    range.setStartAfter(spacer);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
    state.lastSavedRange = range.cloneRange();

    saveAndDispatch(editor);
}

function locateInOriginalText(lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (!line || !line.content) {
        showToast('该台词没有内容', 'warning');
        return;
    }

    if (state.currentChapterIndex < 0) {
        showToast('请先选择章节', 'warning');
        return;
    }

    const panel = document.getElementById('originalTextPanel');
    if (panel.classList.contains('collapsed')) {
        state.showOriginalText = true;
        panel.classList.remove('collapsed');
    }

    const bodyEl = document.getElementById('originalTextBody');
    const searchText = line.content.trim();

    if (!bodyEl.value && !state.showOriginalText) {
        loadOriginalText(state.currentChapterIndex).then(() => {
            doLocateInOriginal(searchText, bodyEl);
        });
        return;
    }

    if (!bodyEl.value) {
        loadOriginalText(state.currentChapterIndex).then(() => {
            doLocateInOriginal(searchText, bodyEl);
        });
        return;
    }

    doLocateInOriginal(searchText, bodyEl);
}

function doLocateInOriginal(searchText, textareaEl) {
    const fullText = textareaEl.value;
    if (!fullText || !searchText) return;

    const cleanSearch = searchText
        .replace(/[\[\]（）()【】""''「」『』《》]/g, '')
        .replace(/\s+/g, '')
        .trim();

    if (!cleanSearch) {
        showToast('无法定位：内容为空', 'warning');
        return;
    }

    let bestIndex = -1;
    let bestLength = 0;

    for (let len = Math.min(cleanSearch.length, 30); len >= 5; len -= 2) {
        const snippet = cleanSearch.substring(0, len);
        const idx = fullText.indexOf(snippet);
        if (idx !== -1) {
            bestIndex = idx;
            bestLength = len;
            break;
        }
    }

    if (bestIndex === -1) {
        const words = cleanSearch.split(/[，。！？、；：,.!?;:]/).filter(w => w.length >= 3);
        for (const word of words) {
            const idx = fullText.indexOf(word);
            if (idx !== -1) {
                bestIndex = idx;
                bestLength = word.length;
                break;
            }
        }
    }

    if (bestIndex === -1) {
        showToast('未在原文中找到匹配内容', 'warning');
        return;
    }

    const endIndex = bestIndex + bestLength;

    textareaEl.focus();
    textareaEl.setSelectionRange(bestIndex, endIndex);

    const totalLength = fullText.length;
    const scrollRatio = bestIndex / totalLength;
    const maxScroll = textareaEl.scrollHeight - textareaEl.clientHeight;
    textareaEl.scrollTop = Math.max(0, Math.min(maxScroll,
        scrollRatio * textareaEl.scrollHeight - textareaEl.clientHeight / 2
    ));

    textareaEl.classList.add('highlight-flash');
    if (state._highlightTimer) clearTimeout(state._highlightTimer);
    state._highlightTimer = setTimeout(() => {
        textareaEl.classList.remove('highlight-flash');
    }, 1500);
}

function addLineAbove(index) {
    const line = {
        id: Date.now(),
        content: '',
        role: '',
        tone: '',
        instruction: '',
        audio_path: null
    };
    state.currentLines.splice(index, 0, line);
    renderLines();
}

function addLineBelow(index) {
    const line = {
        id: Date.now(),
        content: '',
        role: '',
        tone: '',
        instruction: '',
        audio_path: null
    };
    state.currentLines.splice(index + 1, 0, line);
    renderLines();
}

async function deleteLine(lineId) {
    if (!confirm('确定删除这条台词吗？')) return;
    const idx = state.currentLines.findIndex(l => l.id === lineId);
    if (idx === -1) return;

    try {
        const data = await apiRequest(`/api/books/scripts/lines?script_id=${state.scriptId}&line_id=${lineId}`, {
            method: 'DELETE',
            errorPrefix: '删除失败'
        });
        if (data.success) {
            state.currentLines.splice(idx, 1);
            renderLines();
            updatePlayerButtons();
        } else {
            showToast(data.detail || '删除失败', 'error');
        }
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

function onToneChange(input, lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (line) {
        line.tone = input.value;
        updateLine(lineId, { tone: input.value });
        const display = input.parentElement.querySelector('.tone-display');
        if (display) display.textContent = input.value;
    }
}

function onInstructionChange(input, lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (line) {
        line.instruction = input.value;
        updateLine(lineId, { instruction: input.value });
        const display = input.parentElement.querySelector('.instruction-display');
        if (display) display.textContent = input.value;
    }
}

function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return hash;
}

let versionCompareState = {
    selectedVersions: [],
    versions: []
};

async function showChapterVersionHistory() {
    if (!state.scriptId || state.currentChapterIndex < 0) {
        showToast('请先选择章节', 'warning');
        return;
    }
    versionCompareState.selectedVersion = null;
    versionCompareState.versions = [];
    const modal = document.getElementById('chapterVersionModal');
    modal.style.display = 'flex';
    document.getElementById('versionList').innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p class="mt-2">加载历史...</p></div>';
    document.getElementById('versionCompare').innerHTML = '<div class="compare-empty"><i class="fas fa-search"></i><p>点击左侧历史版本查看与当前内容的差异</p></div>';
    await loadChapterVersions();
}

function closeChapterVersionModal() {
    const modal = document.getElementById('chapterVersionModal');
    modal.style.display = 'none';
    versionCompareState.selectedVersion = null;
    versionCompareState.versions = [];
}

async function loadChapterVersions() {
    if (!state.scriptId || state.currentChapterIndex < 0) return;
    try {
        const data = await apiRequest(
            `/api/books/scripts/chapters/versions?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`,
            { silent: true }
        );
        if (data.success) {
            versionCompareState.versions = data.versions;
            renderVersionList();
        }
    } catch (e) {
        console.error('加载版本历史失败:', e);
        document.getElementById('versionList').innerHTML = '<div class="loading-state"><p>加载失败</p></div>';
    }
}

function renderVersionList() {
    const listEl = document.getElementById('versionList');
    if (versionCompareState.versions.length === 0) {
        listEl.innerHTML = '<div class="loading-state"><p>暂无版本历史</p></div>';
        return;
    }
    listEl.innerHTML = '';
    versionCompareState.versions.forEach((version, idx) => {
        const item = document.createElement('div');
        item.className = 'version-item';
        if (versionCompareState.selectedVersion === version.id) {
            item.classList.add('selected');
        }
        item.dataset.versionId = version.id;
        const date = new Date(version.created_at * 1000);
        const timeStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
        const preview = version.content ? version.content.substring(0, 100) + (version.content.length > 100 ? '...' : '') : '';
        item.innerHTML = `
            <div class="version-time">${timeStr}</div>
            <div class="version-wordcount">${version.word_count || 0} 字</div>
            <div class="version-preview">${escapeHtml(preview)}</div>
        `;
        item.onclick = () => selectVersionForCompare(version.id);
        listEl.appendChild(item);
    });
}

function selectVersionForCompare(versionId) {
    versionCompareState.selectedVersion = versionCompareState.selectedVersion === versionId ? null : versionId;
    renderVersionList();
    if (versionCompareState.selectedVersion) {
        renderVersionCompare();
    } else {
        document.getElementById('versionCompare').innerHTML = '<div class="compare-empty"><i class="fas fa-search"></i><p>点击左侧历史版本查看与当前内容的差异</p></div>';
    }
}

async function renderVersionCompare() {
    const versionId = versionCompareState.selectedVersion;
    try {
        const data = await apiRequest(`/api/books/scripts/chapters/versions/detail?script_id=${state.scriptId}&version_id=${versionId}`, {
            silent: true
        });
        if (data.success && data.version) {
            const version = data.version;
            const currentContent = document.getElementById('originalTextBody').value || '';
            
            const date = new Date(version.created_at * 1000);
            const timeStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
            
            const diff = generateGitDiff(version.content || '', currentContent);
            
            document.getElementById('versionCompare').innerHTML = `
                <div class="compare-panels">
                    <div class="compare-panel compare-panel-old">
                        <div class="compare-panel-header">
                            <span><i class="fas fa-history"></i> 历史版本 <span class="version-label">${timeStr}</span></span>
                            <button class="btn btn-outline-primary" style="padding:2px 8px;font-size:11px;" onclick="restoreVersion(${versionId})">恢复此版本</button>
                        </div>
                        <div class="compare-panel-body">${diff.oldHtml}</div>
                    </div>
                    <div class="compare-panel compare-panel-new">
                        <div class="compare-panel-header">
                            <span><i class="fas fa-check-circle"></i> 当前版本</span>
                        </div>
                        <div class="compare-panel-body">${diff.newHtml}</div>
                    </div>
                </div>
                <div class="compare-actions">
                    <div class="diff-stats">
                        <span class="diff-stat added">+${diff.addedLines} 行</span>
                        <span class="diff-stat removed">-${diff.removedLines} 行</span>
                        <span class="diff-stat changed">~${diff.changedLines} 行</span>
                    </div>
                    <button class="btn btn-outline-primary" onclick="closeChapterVersionModal()">关闭</button>
                </div>
            `;
        }
    } catch (e) {
        console.error('对比版本失败:', e);
    }
}

function generateGitDiff(oldText, newText) {
    const oldLines = oldText.split('\n');
    const newLines = newText.split('\n');
    
    const lcs = computeLCS(oldLines, newLines);
    
    let oldIdx = 0, newIdx = 0;
    let oldHtml = '';
    let newHtml = '';
    let addedLines = 0;
    let removedLines = 0;
    let changedLines = 0;
    
    for (const lcsLine of lcs) {
        while (oldIdx < oldLines.length && oldLines[oldIdx] !== lcsLine) {
            oldHtml += `<div class="diff-line diff-line-removed"><span class="diff-line-num">-${oldIdx + 1}</span><span class="diff-line-content">${escapeHtml(oldLines[oldIdx])}</span></div>`;
            newHtml += `<div class="diff-line diff-line-empty"><span class="diff-line-num"></span><span class="diff-line-content"></span></div>`;
            removedLines++;
            oldIdx++;
        }
        
        while (newIdx < newLines.length && newLines[newIdx] !== lcsLine) {
            oldHtml += `<div class="diff-line diff-line-empty"><span class="diff-line-num"></span><span class="diff-line-content"></span></div>`;
            newHtml += `<div class="diff-line diff-line-added"><span class="diff-line-num">+${newIdx + 1}</span><span class="diff-line-content">${escapeHtml(newLines[newIdx])}</span></div>`;
            addedLines++;
            newIdx++;
        }
        
        oldHtml += `<div class="diff-line diff-line-same"><span class="diff-line-num">${oldIdx + 1}</span><span class="diff-line-content">${escapeHtml(lcsLine)}</span></div>`;
        newHtml += `<div class="diff-line diff-line-same"><span class="diff-line-num">${newIdx + 1}</span><span class="diff-line-content">${escapeHtml(lcsLine)}</span></div>`;
        oldIdx++;
        newIdx++;
    }
    
    while (oldIdx < oldLines.length) {
        oldHtml += `<div class="diff-line diff-line-removed"><span class="diff-line-num">-${oldIdx + 1}</span><span class="diff-line-content">${escapeHtml(oldLines[oldIdx])}</span></div>`;
        newHtml += `<div class="diff-line diff-line-empty"><span class="diff-line-num"></span><span class="diff-line-content"></span></div>`;
        removedLines++;
        oldIdx++;
    }
    
    while (newIdx < newLines.length) {
        oldHtml += `<div class="diff-line diff-line-empty"><span class="diff-line-num"></span><span class="diff-line-content"></span></div>`;
        newHtml += `<div class="diff-line diff-line-added"><span class="diff-line-num">+${newIdx + 1}</span><span class="diff-line-content">${escapeHtml(newLines[newIdx])}</span></div>`;
        addedLines++;
        newIdx++;
    }
    
    return {
        oldHtml: oldHtml || '<div class="diff-empty">（空）</div>',
        newHtml: newHtml || '<div class="diff-empty">（空）</div>',
        addedLines,
        removedLines,
        changedLines: Math.min(addedLines, removedLines)
    };
}

function computeLCS(a, b) {
    const m = a.length;
    const n = b.length;
    const dp = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));
    
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            if (a[i - 1] === b[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
            } else {
                dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
    }
    
    const lcs = [];
    let i = m, j = n;
    while (i > 0 && j > 0) {
        if (a[i - 1] === b[j - 1]) {
            lcs.unshift(a[i - 1]);
            i--;
            j--;
        } else if (dp[i - 1][j] > dp[i][j - 1]) {
            i--;
        } else {
            j--;
        }
    }
    
    return lcs;
}

async function restoreVersion(versionId) {
    if (!confirm('确定恢复此版本吗？当前内容将被覆盖。')) return;
    try {
        const data = await apiRequest(
            `/api/books/scripts/chapters/versions/detail?script_id=${state.scriptId}&version_id=${versionId}`,
            { silent: true }
        );
        if (data.success && data.version) {
            const bodyEl = document.getElementById('originalTextBody');
            bodyEl.value = data.version.content || '';
            closeChapterVersionModal();
            await saveChapterContent();
            showToast('版本已恢复', 'success');
        }
    } catch (e) {
        showToast('恢复失败', 'error');
    }
}