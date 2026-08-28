async function loadCharacters() {
    try {
        const data = await apiRequest(`/api/books/scripts/characters?script_id=${state.scriptId}`, {
            silent: true,
            errorPrefix: '加载角色失败'
        });
        if (data.success) {
            state.characters = data.characters;
            state.characterVoiceMap = {};
            for (const ch of state.characters) {
                state.characterVoiceMap[ch.role] = {
                    agent_id: ch.agent_id || '',
                    speed: ch.speed || 1.0,
                    seed: ch.seed || 0,
                    tts_capability_id: ch.tts_capability_id || '',
                    cloud_extra_params: ch.cloud_extra_params || '{}',
                };
            }
            renderCharacters();
            refreshRoleSelects();
            if (!state.selectedRole && state.characters.length > 0) {
                selectCharacter(state.characters[0].role);
            } else if (state.selectedRole) {
                renderCharacterSettings();
            }
        }
    } catch (e) {
        console.error('加载角色失败:', e);
    }
}

function refreshRoleSelects(newRoles) {
    const listEl = document.getElementById('linesList');
    if (!listEl) return;
    const selects = listEl.querySelectorAll('.role-select');
    if (newRoles && newRoles.length > 0) {
        const rolesToAdd = newRoles.filter(role =>
            !state.characters.some(c => c.role === role)
        );
        if (rolesToAdd.length === 0) return;
        selects.forEach(select => {
            const currentValue = select.value;
            const sortedRoles = [...rolesToAdd].sort((a, b) =>
                (a !== '旁白') - (b !== '旁白') || a.localeCompare(b)
            );
            sortedRoles.forEach(role => {
                const option = document.createElement('option');
                option.value = role;
                option.textContent = role;
                let inserted = false;
                const isNarration = role === '旁白';
                const options = select.querySelectorAll('option');
                for (const opt of options) {
                    if (!opt.value) continue;
                    const optIsNarration = opt.value === '旁白';
                    if (isNarration && !optIsNarration) {
                        select.insertBefore(option, opt);
                        inserted = true;
                        break;
                    }
                    if (!isNarration && !optIsNarration && role.localeCompare(opt.value) < 0) {
                        select.insertBefore(option, opt);
                        inserted = true;
                        break;
                    }
                }
                if (!inserted) {
                    select.appendChild(option);
                }
            });
            select.value = currentValue;
        });
        return;
    }
    selects.forEach(select => {
        const currentValue = select.value;
        let optionsHtml = state.characters.map(c =>
            `<option value="${escapeHtml(c.role)}">${escapeHtml(c.role)}</option>`
        ).join('');
        if (currentValue && !state.characters.some(c => c.role === currentValue)) {
            optionsHtml += `<option value="${escapeHtml(currentValue)}">${escapeHtml(currentValue)}</option>`;
        }
        select.innerHTML = `<option value="">-- 选择角色 --</option>${optionsHtml}`;
        select.value = currentValue;
    });
}

function renderCharacters() {
    const grid = document.getElementById('characterGrid');
    document.getElementById('characterCountBadge').textContent = state.characters.length;
    grid.innerHTML = '';
    if (state.characters.length === 0) {
        grid.innerHTML = '<div class="settings-empty" style="padding: 16px;"><p>暂无配音角色</p></div>';
        return;
    }
    const sorted = [...state.characters].sort((a, b) =>
        (a.role !== '旁白') - (b.role !== '旁白') || a.role.localeCompare(b.role)
    );
    sorted.forEach((ch) => {
        const div = createCharacterAvatarElement(ch);
        grid.appendChild(div);
    });
}

function createCharacterAvatarElement(ch) {
    const div = document.createElement('div');
    div.className = 'character-avatar';
    div.dataset.role = ch.role;
    if (ch.role === state.selectedRole) div.classList.add('selected');
    const colorIdx = ch.role === '旁白' ? -1 : Math.abs(hashString(ch.role)) % AVATAR_COLORS.length;
    const bg = ch.role === '旁白'
        ? 'linear-gradient(135deg, #94a3b8, #475569)'
        : AVATAR_COLORS[colorIdx >= 0 ? colorIdx : 0];
    div.innerHTML = `
        <div class="avatar-circle" style="background: ${bg};">${escapeHtml(ch.role.charAt(0))}</div>
        <div class="avatar-name">${escapeHtml(ch.role)}</div>
        <div class="avatar-count">${ch.line_count}句</div>
    `;
    div.onclick = () => selectCharacter(ch.role);
    return div;
}

function selectCharacter(role) {
    state.selectedRole = role;
    renderCharacters();
    renderCharacterSettings();
}

async function addNewCharacter() {
    const role = prompt('请输入新角色名称：');
    if (!role || !role.trim()) return;
    const trimmedRole = role.trim();
    if (state.characters.some(c => c.role === trimmedRole)) {
        showToast('角色已存在', 'warning');
        selectCharacter(trimmedRole);
        return;
    }
    try {
        const data = await apiRequest(`/api/books/scripts/characters?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: trimmedRole }),
            errorPrefix: '添加角色失败'
        });
        if (data.success) {
            showToast(`角色"${trimmedRole}"已添加`, 'success');
            await loadCharacters();
            selectCharacter(trimmedRole);
        } else {
            showToast(data.message || '添加失败', 'error');
        }
    } catch (e) {
        console.error('添加角色失败:', e);
        showToast('添加角色失败: ' + e.message, 'error');
    }
}

async function deleteCurrentCharacter() {
    if (!state.selectedRole) return;
    const ch = state.characters.find(c => c.role === state.selectedRole);
    if (!ch) return;
    if (ch.line_count > 0) {
        showToast(`角色"${state.selectedRole}"仍有 ${ch.line_count} 句台词，无法删除`, 'warning');
        return;
    }
    if (!confirm(`确定删除角色"${state.selectedRole}"吗？`)) return;
    try {
        const data = await apiRequest(`/api/books/scripts/characters/delete?script_id=${state.scriptId}&role_name=${encodeURIComponent(state.selectedRole)}`, {
            method: 'DELETE',
            errorPrefix: '删除角色失败'
        });
        if (data.success) {
            showToast(`角色"${state.selectedRole}"已删除`, 'success');
            state.selectedRole = null;
            await loadCharacters();
            renderCharacterSettings();
        } else {
            showToast(data.message || '删除失败', 'error');
        }
    } catch (e) {
        console.error('删除角色失败:', e);
        showToast('删除角色失败: ' + e.message, 'error');
    }
}

function renderCharacterSettings() {
    const el = document.getElementById('characterSettings');
    if (!state.selectedRole) {
        el.innerHTML = '<div class="settings-empty"><i class="fas fa-hand-pointer"></i><p>点击上方角色头像进行设置</p></div>';
        return;
    }
    const config = state.characterVoiceMap[state.selectedRole] || {
        agent_id: '', speed: 1.0, seed: 0, tts_capability_id: '', cloud_extra_params: '{}'
    };

    // 构建模型能力下拉选项（包含所有能力，不再过滤本地）
    const allCaps = state.ttsCapabilities || [];
    const hasMatch = allCaps.some(c => c.id === config.tts_capability_id);
    const capOptions = allCaps.map((cap, idx) => {
        const platformLabel = cap.platform_code === 'local' ? '本地' : (cap.platform_code || '');
        const label = `${platformLabel} / ${cap.model_code}`;
        const selected = (hasMatch ? cap.id === config.tts_capability_id : idx === 0) ? 'selected' : '';
        return `<option value="${cap.id}" ${selected}>${escapeHtml(label)}</option>`;
    }).join('');

    // 若当前无匹配，默认选中第一个
    if (!hasMatch && allCaps.length > 0) {
        config.tts_capability_id = allCaps[0].id;
    }

    const isCloud = config.tts_capability_id && state.ttsCapabilities.some(
        c => c.id === config.tts_capability_id && c.platform_code !== 'local'
    );

    // 解析云端额外参数
    let cloudParams = {};
    try {
        cloudParams = JSON.parse(config.cloud_extra_params || '{}');
    } catch (e) { cloudParams = {}; }
    const cloudExtraJson = JSON.stringify(cloudParams, null, 2);

    // 本地模式：智能体 + 语气
    let localSectionHtml = '';
    if (!isCloud) {
        const selectedAgent = state.agents.find(a => a.id === config.agent_id);
        const voiceTones = (selectedAgent && selectedAgent.voice_tones) || [];
        const tonesListHtml = voiceTones.length > 0
            ? voiceTones.map((vt, idx) => `
                <div class="tone-preview-item">
                    <div class="tone-info">
                        <div class="tone-name">${escapeHtml(vt.tone)}</div>
                        ${vt.prompt_text ? `<div class="tone-prompt">${escapeHtml(vt.prompt_text)}</div>` : ''}
                    </div>
                    <button class="tone-play-btn" data-tone-idx="${idx}" onclick="previewStoredTone(${idx}, this)" title="试听语气">
                        <i class="fas fa-play"></i>
                    </button>
                </div>
            `).join('')
            : '<div class="tone-empty">该智能体暂无可用语气</div>';

        localSectionHtml = `
            <div class="setting-group">
                <label><i class="fas fa-microphone"></i> 配音智能体</label>
                <button type="button" class="picker-select-btn ${!config.agent_id ? 'empty' : ''}" style="width: 100%; justify-content: flex-start;"
                        onclick="openAgentPickerForCharacter()">
                    <i class="fas fa-user-circle"></i>
                    <span>${selectedAgent ? escapeHtml(selectedAgent.name) : '-- 点击选择配音智能体 --'}</span>
                    <i class="fas fa-chevron-down" style="margin-left: auto; font-size: 11px; opacity: 0.5;"></i>
                </button>
                ${selectedAgent ? `<small style="display: block; margin-top: 6px; color: var(--neu-text-muted); font-size: 12px;">${escapeHtml(selectedAgent.description || '暂无描述')}</small>` : ''}
            </div>
            <div class="setting-group">
                <label><i class="fas fa-music"></i> 语气样例（点击试听）</label>
                <div class="tone-list" id="toneListContainer">${tonesListHtml}</div>
            </div>
        `;
    }

    // 云端模式：额外参数
    let cloudSectionHtml = '';
    if (isCloud) {
        cloudSectionHtml = `
            <div class="setting-group">
                <label><i class="fas fa-cogs"></i> 额外参数 <span style="font-size:12px;color:#999;">(JSON 格式)</span></label>
                <textarea id="cloudExtraParamsInput" rows="5"
                          placeholder='{"voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0}'
                          onchange="updateCloudExtraParams()">${escapeHtml(cloudExtraJson === '{}' ? '' : cloudExtraJson)}</textarea>
                <small style="display: block; margin-top: 4px; color: var(--neu-text-muted); font-size: 11px;">
                    不同平台参数规范不同，请根据所选模型的文档填写，如 voice、speed 等
                </small>
            </div>
        `;
    }

    // 模型能力下拉区域
    let capabilitySectionHtml = '';
    if (allCaps.length === 0) {
        capabilitySectionHtml = `
            <div class="setting-group">
                <label><i class="fas fa-sliders-h"></i> 模型能力</label>
                <div style="color: var(--neu-danger, #e53e3e); font-size: 13px; padding: 8px 0;">
                    <i class="fas fa-exclamation-triangle"></i> 未配置任何模型能力，请先在设置中启用
                </div>
            </div>
        `;
    } else {
        capabilitySectionHtml = `
            <div class="setting-group">
                <label><i class="fas fa-sliders-h"></i> 模型能力</label>
                <select id="ttsCapabilitySelect" onchange="updateCharacterVoice('tts_capability_id', this.value)">
                    ${capOptions}
                </select>
            </div>
        `;
    }

    el.innerHTML = `
        ${capabilitySectionHtml}
        ${localSectionHtml}
        ${cloudSectionHtml}
        <div class="setting-group" style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--neu-border);">
            <button type="button" class="btn btn-sm btn-outline-danger" style="width: 100%;"
                    onclick="deleteCurrentCharacter()" title="删除角色">
                <i class="fas fa-trash-alt"></i> 删除角色
            </button>
        </div>
    `;
}

function updateCharacterVoice(key, value) {
    if (!state.selectedRole) return;
    if (!state.characterVoiceMap[state.selectedRole]) {
        state.characterVoiceMap[state.selectedRole] = {
            agent_id: '', speed: 1.0, seed: 0, tts_capability_id: '', cloud_extra_params: '{}'
        };
    }
    state.characterVoiceMap[state.selectedRole][key] = value;
    // 切换模式时清除另一模式的参数，确保音频匹配使用正确的配置
    if (key === 'tts_capability_id') {
        // 切换到云端能力时清除本地智能体；切换到本地能力时保留 agent_id
        const isCloudCap = state.ttsCapabilities.some(c => c.id === value && c.platform_code !== 'local');
        if (isCloudCap) {
            state.characterVoiceMap[state.selectedRole].agent_id = '';
        }
    } else if (key === 'agent_id') {
        // 切换智能体不影响已选的模型能力
    }
    if (key === 'agent_id' || key === 'tts_capability_id') {
        stopTonePreview();
        renderCharacterSettings();
        // 切换智能体/能力时，重置所有台词的音频调整参数（旧参数是为旧音频调的，对新音频不适用）
        // 如果匹配到历史音频，matchAudioHistoryForLines 会从历史记录中恢复正确的参数
        for (const line of state.currentLines) {
            line.audio_path = '';  // 先清除，由 match 决定是否恢复
            line.audio_volume = 1;
            line.audio_pitch = 0;
            line.fade_in = 0;
            line.fade_out = 0;
            line.audio_adjust_enabled = 0;
            line.range_start = 0;
            line.range_end = 0;
        }
    }
    scheduleSaveCharacterConfig();
    
    matchAudioHistoryForLines(state.currentLines).then(() => {
        state.currentLines.forEach(line => {
            updateLineAudioEditorDisplay(line.id);
        });
    });
}

function updateCloudExtraParams() {
    if (!state.selectedRole) return;
    const config = state.characterVoiceMap[state.selectedRole];
    if (!config) return;

    const textareaInput = document.getElementById('cloudExtraParamsInput');
    if (!textareaInput) return;

    if (textareaInput.value.trim()) {
        try {
            JSON.parse(textareaInput.value);
        } catch (e) {
            // JSON 格式错误，不保存
            return;
        }
    }
    config.cloud_extra_params = textareaInput.value.trim() || '{}';
    scheduleSaveCharacterConfig();
}

function scheduleSaveCharacterConfig() {
    if (state.saveConfigTimer) clearTimeout(state.saveConfigTimer);
    state.saveConfigTimer = setTimeout(() => {
        saveCharacterConfig();
    }, 300);
}

async function saveCharacterConfig() {
    if (!state.selectedRole || !state.scriptId) return;
    const config = state.characterVoiceMap[state.selectedRole];
    if (!config) return;
    try {
        await apiRequest(`/api/books/scripts/characters/config?script_id=${state.scriptId}&role=${encodeURIComponent(state.selectedRole)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_id: config.agent_id || '',
                speed: config.speed,
                seed: config.seed,
                tts_capability_id: config.tts_capability_id || '',
                cloud_extra_params: config.cloud_extra_params || '{}',
            }),
            silent: true
        });
    } catch (e) {
        console.error('保存角色配置失败:', e);
    }
}

function stopTonePreview() {
    if (state._tonePreviewAudio) {
        try { state._tonePreviewAudio.pause(); } catch (e) { /* ignore */ }
        state._tonePreviewAudio.currentTime = 0;
        state._tonePreviewAudio = null;
    }
    if (state._tonePreviewBtn) {
        state._tonePreviewBtn.classList.remove('playing');
        const icon = state._tonePreviewBtn.querySelector('i');
        if (icon) icon.className = 'fas fa-play';
        state._tonePreviewBtn = null;
    }
}

function previewStoredTone(toneIdx, btn) {
    if (!state.selectedRole) return;
    const config = state.characterVoiceMap[state.selectedRole] || {};
    const agent = state.agents.find(a => a.id === config.agent_id);
    const tones = (agent && agent.voice_tones) || [];
    const vt = tones[toneIdx];
    if (!vt) return;

    const url = vt.voice_path || vt.original_path;
    if (!url) {
        showToast('该语气没有可播放的语音文件', 'warning');
        return;
    }

    if (state._tonePreviewAudio && state._tonePreviewBtn === btn) {
        stopTonePreview();
        return;
    }

    stopTonePreview();

    const audio = new Audio(url);
    audio.crossOrigin = 'anonymous';
    state._tonePreviewAudio = audio;
    state._tonePreviewBtn = btn;
    btn.classList.add('playing');
    const icon = btn.querySelector('i');
    if (icon) icon.className = 'fas fa-pause';

    audio.addEventListener('ended', () => {
        if (state._tonePreviewBtn === btn) stopTonePreview();
    });
    audio.addEventListener('error', () => {
        showToast('语音文件播放失败', 'error');
        if (state._tonePreviewBtn === btn) stopTonePreview();
    });

    audio.play().catch(err => {
        showToast('语音文件播放失败: ' + err.message, 'error');
        stopTonePreview();
    });
}

function openAgentPickerModal(selectedId, callback) {
    state.agentPickerCallback = callback;
    state.agentPickerCurrentId = selectedId || null;
    state.agentPickerSearch = '';
    state.agentPickerGender = '';
    state.agentPickerAge = '';
    state.agentPickerPage = 1;
    document.getElementById('agentPickerSearch').value = '';
    _updateAgentFilterChips();
    document.getElementById('agentPickerModal').style.display = 'flex';
    loadAgentPicker();
}

function closeAgentPickerModal() {
    _stopAgentVoicePreview();
    document.getElementById('agentPickerModal').style.display = 'none';
    state.agentPickerCallback = null;
}

function setAgentPickerFilter(filterType, value) {
    if (filterType === 'gender') {
        state.agentPickerGender = value;
    } else if (filterType === 'age') {
        state.agentPickerAge = value;
    }
    state.agentPickerPage = 1;
    _updateAgentFilterChips();
    loadAgentPicker();
}

function _updateAgentFilterChips() {
    document.querySelectorAll('.picker-filter-chip[data-filter="gender"]').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.value === state.agentPickerGender);
    });
    document.querySelectorAll('.picker-filter-chip[data-filter="age"]').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.value === state.agentPickerAge);
    });
}

function searchAgentPicker(keyword) {
    state.agentPickerSearch = keyword.trim();
    state.agentPickerPage = 1;
    loadAgentPicker();
}

function goAgentPickerPage(page) {
    if (page < 1 || page > state.agentPickerTotalPages) return;
    state.agentPickerPage = page;
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
            page: state.agentPickerPage,
            page_size: state.agentPickerPageSize,
        });
        if (state.agentPickerSearch) params.set('search', state.agentPickerSearch);
        if (state.agentPickerGender) params.set('gender', state.agentPickerGender);
        if (state.agentPickerAge) params.set('age', state.agentPickerAge);

        const data = await apiRequest(`/api/agents?${params.toString()}`, { silent: true });
        const pageItems = data.items || [];
        state.agentPickerPageItems = pageItems;
        state.agentPickerTotal = data.total || 0;
        state.agentPickerTotalPages = data.total_pages || 1;

        let countText = `共 ${state.agentPickerTotal} 个智能体`;
        const filters = [];
        if (state.agentPickerSearch) filters.push(`搜索: ${state.agentPickerSearch}`);
        if (state.agentPickerGender) filters.push(`性别: ${state.agentPickerGender}`);
        if (state.agentPickerAge) filters.push(`年龄: ${state.agentPickerAge}`);
        if (filters.length) countText += `（${filters.join('，')}）`;
        countEl.textContent = countText;

        if (pageItems.length === 0) {
            listEl.innerHTML = `
                <div class="picker-empty">
                    <i class="fas fa-search"></i>
                    <p>${state.agentPickerSearch || state.agentPickerGender || state.agentPickerAge ? '没有找到匹配的智能体' : '暂无智能体'}</p>
                </div>
            `;
        } else {
            listEl.innerHTML = pageItems.map(agent => {
                const isSelected = agent.id === state.agentPickerCurrentId;
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

        if (state.agentPickerTotalPages <= 1) {
            paginationEl.style.display = 'none';
        } else {
            paginationEl.style.display = 'flex';
            let html = '';
            html += `<button ${state.agentPickerPage === 1 ? 'disabled' : ''} onclick="goAgentPickerPage(${state.agentPickerPage - 1})"><i class="fas fa-chevron-left"></i></button>`;
            const maxVisible = 5;
            let startP = Math.max(1, state.agentPickerPage - Math.floor(maxVisible / 2));
            let endP = Math.min(state.agentPickerTotalPages, startP + maxVisible - 1);
            if (endP - startP + 1 < maxVisible) {
                startP = Math.max(1, endP - maxVisible + 1);
            }
            for (let i = startP; i <= endP; i++) {
                html += `<button class="${i === state.agentPickerPage ? 'active' : ''}" onclick="goAgentPickerPage(${i})">${i}</button>`;
            }
            html += `<button ${state.agentPickerPage === state.agentPickerTotalPages ? 'disabled' : ''} onclick="goAgentPickerPage(${state.agentPickerPage + 1})"><i class="fas fa-chevron-right"></i></button>`;
            paginationEl.innerHTML = html;
        }
    } catch (e) {
        console.error('加载智能体列表失败:', e);
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
    state.agentPickerCurrentId = agentId;
    const agent = state.agents.find(a => a.id === agentId) ||
                  state.agentPickerPageItems.find(a => a.id === agentId) || null;
    if (state.agentPickerCallback) {
        state.agentPickerCallback(agentId, agent);
    }
    closeAgentPickerModal();
}

function toggleAgentVoicePreview(agentId, btnEl) {
    if (state._agentPreviewCurrentAgentId === agentId && state._agentPreviewAudio && !state._agentPreviewAudio.paused) {
        _stopAgentVoicePreview();
        return;
    }

    _stopAgentVoicePreview();

    const agent = state.agentPickerPageItems.find(a => a.id === agentId);
    const voiceTones = (agent && agent.voice_tones) || [];
    if (!voiceTones.length || !voiceTones[0].voice_path) {
        showToast('该智能体暂无音色参考音频', 'warning');
        return;
    }

    const audioUrl = voiceTones[0].voice_path;
    const audio = new Audio(audioUrl);
    state._agentPreviewAudio = audio;
    state._agentPreviewCurrentAgentId = agentId;

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
        state._agentPreviewCurrentAgentId = null;
        state._agentPreviewAudio = null;
    });

    audio.addEventListener('error', () => {
        showToast('音频加载失败', 'error');
        btnEl.classList.remove('playing');
        btnEl.innerHTML = '<i class="fas fa-volume-up"></i>';
        state._agentPreviewCurrentAgentId = null;
        state._agentPreviewAudio = null;
    });

    audio.load();
}

function _stopAgentVoicePreview() {
    if (state._agentPreviewAudio) {
        try { state._agentPreviewAudio.pause(); } catch (e) {}
        state._agentPreviewAudio = null;
    }
    state._agentPreviewCurrentAgentId = null;
    document.querySelectorAll('.picker-item-voice-preview-btn').forEach(b => {
        b.classList.remove('playing');
        b.innerHTML = '<i class="fas fa-volume-up"></i>';
    });
}

function clearAgentPickerSelection() {
    state.agentPickerCurrentId = null;
    if (state.agentPickerCallback) {
        state.agentPickerCallback(null, null);
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

function openRolePickerForLine(lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (!line) return;
    openRolePickerModal(line.role, lineId, function(selectedRole) {
        if (!selectedRole) return;
        line.role = selectedRole;
        updateLine(lineId, { role: selectedRole });
        matchAudioHistoryForLines([line]).then(() => {
            updateLineAudioEditorDisplay(lineId);
        });
        const lineEl = document.querySelector(`.script-line[data-line-id="${lineId}"]`);
        if (lineEl) {
            const btn = lineEl.querySelector('.role-picker-btn');
            if (btn) {
                const colorIdx = selectedRole === '旁白' ? -1 : Math.abs(hashString(selectedRole)) % AVATAR_COLORS.length;
                const bg = selectedRole === '旁白'
                    ? 'linear-gradient(135deg, #94a3b8, #475569)'
                    : AVATAR_COLORS[colorIdx >= 0 ? colorIdx : 0];
                btn.style.background = bg;
                btn.style.color = '#fff';
                btn.classList.remove('empty');
                const textEl = btn.querySelector('.role-picker-text');
                if (textEl) textEl.textContent = selectedRole;
            }
        }
        loadCharacters();
    });
}

function openRolePickerModal(currentRole, lineId, callback) {
    state.rolePickerCallback = callback;
    state.rolePickerCurrentRole = currentRole || null;
    state.rolePickerSearch = '';
    state._pendingLineId = lineId || null;
    document.getElementById('rolePickerSearch').value = '';
    document.getElementById('rolePickerNewRoleInput').value = '';
    document.getElementById('rolePickerModal').style.display = 'flex';
    renderRolePicker();
}

function closeRolePickerModal() {
    document.getElementById('rolePickerModal').style.display = 'none';
    state.rolePickerCallback = null;
    state._pendingLineId = null;
}

function searchRolePicker(keyword) {
    state.rolePickerSearch = keyword.trim();
    renderRolePicker();
}

function renderRolePicker() {
    const listEl = document.getElementById('rolePickerList');
    const countEl = document.getElementById('rolePickerCount');

    let filtered = state.characters.slice();
    if (state.rolePickerSearch) {
        const kw = state.rolePickerSearch.toLowerCase();
        filtered = filtered.filter(c =>
            c.role.toLowerCase().includes(kw)
        );
    }

    countEl.textContent = `共 ${filtered.length} 个角色` +
        (state.rolePickerSearch ? `（搜索: ${state.rolePickerSearch}）` : '');

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
        const isSelected = c.role === state.rolePickerCurrentRole;
        const colorIdx = c.role === '旁白' ? -1 : Math.abs(hashString(c.role)) % AVATAR_COLORS.length;
        const bg = c.role === '旁白'
            ? 'linear-gradient(135deg, #94a3b8, #475569)'
            : AVATAR_COLORS[colorIdx >= 0 ? colorIdx : 0];
        return `
            <div class="picker-item ${isSelected ? 'selected' : ''}" onclick="selectRolePicker('${c.role}')">
                <div class="picker-item-avatar" style="background: ${bg}">${escapeHtml(c.role.charAt(0))}</div>
                <div class="picker-item-info">
                    <div class="picker-item-name">${escapeHtml(c.role)}</div>
                    <div class="picker-item-desc">${c.line_count} 句台词</div>
                </div>
                ${isSelected ? '<i class="fas fa-check-circle" style="color: var(--neu-accent); font-size: 18px; margin-left: 8px;"></i>' : ''}
            </div>
        `;
    }).join('');
}

function selectRolePicker(role) {
    if (state.rolePickerCallback) {
        state.rolePickerCallback(role);
    }
    closeRolePickerModal();
}

async function addRoleFromPicker() {
    const input = document.getElementById('rolePickerNewRoleInput');
    const role = input.value.trim();
    if (!role) {
        showToast('请输入角色名称', 'warning');
        return;
    }
    if (state.characters.some(c => c.role === role)) {
        showToast('角色已存在', 'warning');
        selectRolePicker(role);
        return;
    }
    try {
        const data = await apiRequest(`/api/books/scripts/characters?script_id=${state.scriptId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: role }),
            errorPrefix: '添加角色失败'
        });
        if (data.success) {
            showToast(`角色"${role}"已添加`, 'success');
            await loadCharacters();
            selectRolePicker(role);
        } else {
            showToast(data.message || '添加失败', 'error');
        }
    } catch (e) {
        showToast('添加失败: ' + e.message, 'error');
    }
}