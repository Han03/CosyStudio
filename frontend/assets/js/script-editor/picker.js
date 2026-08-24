let agentPickerCallback = null;
let agentPickerCurrentId = null;
let agentPickerSearch = '';
let agentPickerGender = '';
let agentPickerAge = '';
let agentPickerPage = 1;
let agentPickerPageSize = 5;
let agentPickerTotal = 0;
let agentPickerTotalPages = 1;
let agentPickerPageItems = [];

function openAgentPickerModal(selectedId, callback) {
    agentPickerCallback = callback;
    agentPickerCurrentId = selectedId || null;
    agentPickerSearch = '';
    agentPickerGender = '';
    agentPickerAge = '';
    agentPickerPage = 1;
    document.getElementById('agentPickerSearch').value = '';
    _updateAgentFilterChips();
    document.getElementById('agentPickerModal').style.display = 'flex';
    loadAgentPicker();
}

function closeAgentPickerModal() {
    _stopAgentVoicePreview();
    document.getElementById('agentPickerModal').style.display = 'none';
    agentPickerCallback = null;
}

function setAgentPickerFilter(filterType, value) {
    if (filterType === 'gender') {
        agentPickerGender = value;
    } else if (filterType === 'age') {
        agentPickerAge = value;
    }
    agentPickerPage = 1;
    _updateAgentFilterChips();
    loadAgentPicker();
}

function _updateAgentFilterChips() {
    document.querySelectorAll('.picker-filter-chip[data-filter="gender"]').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.value === agentPickerGender);
    });
    document.querySelectorAll('.picker-filter-chip[data-filter="age"]').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.value === agentPickerAge);
    });
}

function searchAgentPicker(keyword) {
    agentPickerSearch = keyword.trim();
    agentPickerPage = 1;
    loadAgentPicker();
}

function goAgentPickerPage(page) {
    if (page < 1 || page > agentPickerTotalPages) return;
    agentPickerPage = page;
    loadAgentPicker();
}

async function loadAgentPicker() {
    const listEl = document.getElementById('agentPickerList');
    const countEl = document.getElementById('agentPickerCount');
    const paginationEl = document.getElementById('agentPickerPagination');

    listEl.innerHTML = `
        <div class="loading-state" style="padding: 40px 20px;">
            <div class="loading-spinner"></div>
            <p class="mt-2" style="font-size: 13px; color: var(--neu-text-muted);">加载中...</p>
        </div>
    `;
    countEl.textContent = '加载中...';
    paginationEl.style.display = 'none';

    try {
        const params = new URLSearchParams({
            page: agentPickerPage,
            page_size: agentPickerPageSize,
        });
        if (agentPickerSearch) params.set('search', agentPickerSearch);
        if (agentPickerGender) params.set('gender', agentPickerGender);
        if (agentPickerAge) params.set('age', agentPickerAge);

        const data = await apiRequest(`/api/agents?${params.toString()}`, { silent: true });
        const pageItems = data.items || [];
        agentPickerPageItems = pageItems;
        agentPickerTotal = data.total || 0;
        agentPickerTotalPages = data.total_pages || 1;

        let countText = `共 ${agentPickerTotal} 个智能体`;
        const filters = [];
        if (agentPickerSearch) filters.push(`搜索: ${agentPickerSearch}`);
        if (agentPickerGender) filters.push(`性别: ${agentPickerGender}`);
        if (agentPickerAge) filters.push(`年龄: ${agentPickerAge}`);
        if (filters.length) countText += `（${filters.join('，')}）`;
        countEl.textContent = countText;

        if (pageItems.length === 0) {
            listEl.innerHTML = `
                <div class="picker-empty">
                    <i class="fas fa-search"></i>
                    <p>${agentPickerSearch || agentPickerGender || agentPickerAge ? '没有找到匹配的智能体' : '暂无智能体'}</p>
                </div>
            `;
        } else {
            listEl.innerHTML = pageItems.map(agent => {
                const isSelected = agent.id === agentPickerCurrentId;
                const firstChar = agent.name ? agent.name.charAt(0) : '?';
                const colorIdx = Math.abs(hashString(agent.id || agent.name)) % AVATAR_COLORS.length;
                const gender = agent.gender || '';
                const age = agent.age || '';
                const hasVoice = agent.voice_tones && agent.voice_tones.length > 0;
                const firstToneName = hasVoice ? agent.voice_tones[0].tone : '';

                const genderHtml = gender ? `
                    <span class="picker-item-gender-tag ${gender === '男' ? 'male' : gender === '女' ? 'female' : ''}">
                        <i class="fas ${gender === '男' ? 'fa-mars' : gender === '女' ? 'fa-venus' : 'fa-user'}"></i> ${escapeHtml(gender)}
                    </span>
                ` : '';
                const ageHtml = age ? `<span class="picker-item-age-tag">${escapeHtml(age)}</span>` : '';
                const toneHtml = firstToneName ? `<span class="picker-item-age-tag">音色: ${escapeHtml(firstToneName)}</span>` : '';

                const metaTags = [];
                if (genderHtml) metaTags.push(genderHtml);
                if (ageHtml) metaTags.push(ageHtml);
                if (toneHtml) metaTags.push(toneHtml);
                if (agent.tags && agent.tags.length > 0) {
                    agent.tags.slice(0, 2).forEach(t => {
                        metaTags.push(`<span class="picker-item-tag">${escapeHtml(t)}</span>`);
                    });
                    if (agent.tags.length > 2) {
                        metaTags.push(`<span class="picker-item-tag">+${agent.tags.length - 2}</span>`);
                    }
                }

                const metaHtml = metaTags.length > 0 ? `
                    <div class="picker-item-meta">${metaTags.join('')}</div>
                ` : '';

                const previewBtnHtml = hasVoice ? `
                    <button class="picker-item-voice-preview-btn"
                            onclick="event.stopPropagation(); toggleAgentVoicePreview('${agent.id}', this)"
                            title="试听音色">
                        <i class="fas fa-volume-up"></i>
                    </button>
                ` : '';

                return `
                    <div class="picker-item ${isSelected ? 'selected' : ''}" onclick="selectAgentPicker('${agent.id}')">
                        <div class="picker-item-avatar" style="background: ${AVATAR_COLORS[colorIdx]}">${escapeHtml(firstChar)}</div>
                        <div class="picker-item-info">
                            <div class="picker-item-name">${escapeHtml(agent.name)}</div>
                            <div class="picker-item-desc">${escapeHtml(agent.description || '暂无描述')}</div>
                            ${metaHtml}
                        </div>
                        ${previewBtnHtml}
                        ${isSelected ? '<i class="fas fa-check-circle" style="color: var(--neu-accent); font-size: 18px; margin-left: 8px;"></i>' : ''}
                    </div>
                `;
            }).join('');
        }

        if (agentPickerTotalPages <= 1) {
            paginationEl.style.display = 'none';
        } else {
            paginationEl.style.display = 'flex';
            let html = '';
            html += `<button ${agentPickerPage === 1 ? 'disabled' : ''} onclick="goAgentPickerPage(${agentPickerPage - 1})"><i class="fas fa-chevron-left"></i></button>`;
            const maxVisible = 5;
            let startP = Math.max(1, agentPickerPage - Math.floor(maxVisible / 2));
            let endP = Math.min(agentPickerTotalPages, startP + maxVisible - 1);
            if (endP - startP + 1 < maxVisible) {
                startP = Math.max(1, endP - maxVisible + 1);
            }
            for (let i = startP; i <= endP; i++) {
                html += `<button class="${i === agentPickerPage ? 'active' : ''}" onclick="goAgentPickerPage(${i})">${i}</button>`;
            }
            html += `<button ${agentPickerPage === agentPickerTotalPages ? 'disabled' : ''} onclick="goAgentPickerPage(${agentPickerPage + 1})"><i class="fas fa-chevron-right"></i></button>`;
            paginationEl.innerHTML = html;
        }
    } catch (e) {
        listEl.innerHTML = `
            <div class="picker-empty">
                <i class="fas fa-exclamation-circle"></i>
                <p>加载失败，请重试</p>
            </div>
        `;
        countEl.textContent = '加载失败';
    }
}

function selectAgentPicker(agentId) {
    _stopAgentVoicePreview();
    agentPickerCurrentId = agentId;
    const agent = state.agents.find(a => a.id === agentId) ||
                  agentPickerPageItems.find(a => a.id === agentId) || null;
    if (agentPickerCallback) {
        agentPickerCallback(agentId, agent);
    }
    closeAgentPickerModal();
}

let _agentPreviewAudio = null;
let _agentPreviewCurrentAgentId = null;

function toggleAgentVoicePreview(agentId, btnEl) {
    if (_agentPreviewCurrentAgentId === agentId && _agentPreviewAudio && !_agentPreviewAudio.paused) {
        _stopAgentVoicePreview();
        return;
    }

    _stopAgentVoicePreview();

    const agent = agentPickerPageItems.find(a => a.id === agentId);
    const voiceTones = (agent && agent.voice_tones) || [];
    if (!voiceTones.length || !voiceTones[0].voice_path) {
        showToast('该智能体暂无音色参考音频', 'warning');
        return;
    }

    const audioUrl = voiceTones[0].voice_path;
    const audio = new Audio(audioUrl);
    _agentPreviewAudio = audio;
    _agentPreviewCurrentAgentId = agentId;

    btnEl.classList.add('playing');
    btnEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    audio.addEventListener('canplay', () => {
        btnEl.innerHTML = '<i class="fas fa-stop"></i>';
        audio.play().catch(err => {
            console.error('播放失败:', err);
            showToast('播放失败: ' + err.message, 'error');
            _stopAgentVoicePreview();
        });
    });

    audio.addEventListener('ended', () => {
        btnEl.classList.remove('playing');
        btnEl.innerHTML = '<i class="fas fa-volume-up"></i>';
        _agentPreviewCurrentAgentId = null;
        _agentPreviewAudio = null;
    });

    audio.addEventListener('error', () => {
        showToast('音频加载失败', 'error');
        btnEl.classList.remove('playing');
        btnEl.innerHTML = '<i class="fas fa-volume-up"></i>';
        _agentPreviewCurrentAgentId = null;
        _agentPreviewAudio = null;
    });

    audio.load();
}

function _stopAgentVoicePreview() {
    if (_agentPreviewAudio) {
        try { _agentPreviewAudio.pause(); } catch (e) {}
        _agentPreviewAudio = null;
    }
    _agentPreviewCurrentAgentId = null;
    document.querySelectorAll('.picker-item-voice-preview-btn').forEach(b => {
        b.classList.remove('playing');
        b.innerHTML = '<i class="fas fa-volume-up"></i>';
    });
}

function clearAgentPickerSelection() {
    agentPickerCurrentId = null;
    if (agentPickerCallback) {
        agentPickerCallback(null, null);
    }
    closeAgentPickerModal();
}

function openAgentPickerForCharacter() {
    if (!state.selectedRole) return;
    const config = state.characterVoiceMap[state.selectedRole] || {};
    openAgentPickerModal(config.agent_id, function(agentId, agent) {
        updateCharacterVoice('agent_id', agentId || '');
    });
}

let rolePickerCallback = null;
let rolePickerCurrentRole = null;
let rolePickerSearch = '';
let _pendingLineId = null;

function openRolePickerModal(currentRole, lineId, callback) {
    rolePickerCallback = callback;
    rolePickerCurrentRole = currentRole || null;
    rolePickerSearch = '';
    _pendingLineId = lineId || null;
    document.getElementById('rolePickerSearch').value = '';
    document.getElementById('rolePickerNewRoleInput').value = '';
    document.getElementById('rolePickerModal').style.display = 'flex';
    renderRolePicker();
}

function closeRolePickerModal() {
    document.getElementById('rolePickerModal').style.display = 'none';
    rolePickerCallback = null;
    _pendingLineId = null;
}

function searchRolePicker(keyword) {
    rolePickerSearch = keyword.trim();
    renderRolePicker();
}

function renderRolePicker() {
    const listEl = document.getElementById('rolePickerList');
    const countEl = document.getElementById('rolePickerCount');

    let filtered = state.characters.slice();
    if (rolePickerSearch) {
        const kw = rolePickerSearch.toLowerCase();
        filtered = filtered.filter(c =>
            c.role.toLowerCase().includes(kw)
        );
    }

    countEl.textContent = `共 ${filtered.length} 个角色` +
        (rolePickerSearch ? `（搜索: ${rolePickerSearch}）` : '');

    if (filtered.length === 0) {
        listEl.innerHTML = `
            <div class="picker-empty">
                <i class="fas fa-users"></i>
                <p>${state.characters.length === 0 ? '暂无角色' : '没有找到匹配的角色'}</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = filtered.map((c, idx) => {
        const isSelected = c.role === rolePickerCurrentRole;
        const firstChar = c.role ? c.role.charAt(0) : '?';
        const colorIdx = Math.abs(hashString(c.role)) % AVATAR_COLORS.length;
        const agent = (state.characterVoiceMap && state.characterVoiceMap[c.role] && state.characterVoiceMap[c.role].agent_id)
            ? state.agents.find(a => a.id === state.characterVoiceMap[c.role].agent_id)
            : null;
        const agentInfo = agent ? `<div class="picker-item-desc">配音：${escapeHtml(agent.name)}</div>` : '';
        return `
            <div class="picker-item ${isSelected ? 'selected' : ''}" onclick="selectRolePicker('${escapeHtml(c.role).replace(/'/g, "\\'")}')">
                <div class="picker-item-avatar" style="background: ${AVATAR_COLORS[colorIdx]}">${escapeHtml(firstChar)}</div>
                <div class="picker-item-info">
                    <div class="picker-item-name">${escapeHtml(c.role)}</div>
                    ${agentInfo}
                </div>
                ${isSelected ? '<i class="fas fa-check-circle" style="color: var(--neu-accent); font-size: 18px;"></i>' : ''}
            </div>
        `;
    }).join('');
}

function selectRolePicker(role) {
    rolePickerCurrentRole = role;
    if (rolePickerCallback) {
        rolePickerCallback(role, _pendingLineId);
    }
    closeRolePickerModal();
}

function getRoleButtonStyle(role) {
    if (!role) return '';
    const colorIdx = role === '旁白' ? -1 : Math.abs(hashString(role)) % AVATAR_COLORS.length;
    const bg = role === '旁白'
        ? 'linear-gradient(135deg, #94a3b8, #475569)'
        : AVATAR_COLORS[colorIdx];
    return `background: ${bg}; color: #fff;`;
}

function updateLineRoleDisplay(lineId, role) {
    const lineEl = document.querySelector(`.script-line[data-line-id="${lineId}"]`);
    if (!lineEl) return;
    const pickerBtn = lineEl.querySelector('.role-picker-btn');
    if (!pickerBtn) return;
    if (role) {
        pickerBtn.classList.remove('empty');
        pickerBtn.style.cssText = getRoleButtonStyle(role);
        const textEl = pickerBtn.querySelector('.role-picker-text');
        if (textEl) textEl.textContent = role;
    } else {
        pickerBtn.classList.add('empty');
        pickerBtn.style.cssText = '';
        const textEl = pickerBtn.querySelector('.role-picker-text');
        if (textEl) textEl.textContent = '选择角色';
    }
}

function openRolePickerForLine(lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    const currentRole = line ? line.role || '' : '';
    openRolePickerModal(currentRole, lineId, async function(role, lineId) {
        if (!role || !lineId) return;
        const line = state.currentLines.find(l => l.id === lineId);
        if (line && line.role !== role) {
            line.role = role;
            updateLineRoleDisplay(lineId, role);
            await updateLine(lineId, { role: role });
            await loadCharacters();
            await matchAudioHistoryForLines([line]);
            updateLineAudioEditorDisplay(lineId);
        }
    });
}

function createNewRoleFromPicker() {
    const input = document.getElementById('rolePickerNewRoleInput');
    const newRole = input.value.trim();
    if (!newRole) {
        input.focus();
        return;
    }
    if (rolePickerCallback) {
        rolePickerCallback(newRole, _pendingLineId);
    }
    closeRolePickerModal();
}

function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash;
}