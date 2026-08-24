let agentCurrentPage = 1;
let agentPageSize = 20;
let agentTotal = 0;
let agentTotalPages = 1;
let agentCurrentTag = '';
let agentSearchKeyword = '';
let currentEditAgentId = null;
let currentPlayingAudio = null;
let currentPlayingBtn = null;

function filterByTag(tag) {
    agentCurrentTag = tag;
    agentCurrentPage = 1;
    document.querySelectorAll('#agentTagsFilter .btn').forEach(btn => {
        const btnTag = btn.getAttribute('data-tag') || '';
        btn.classList.toggle('active', btnTag === tag);
    });
    loadAgents();
}

function searchAgents() {
    agentSearchKeyword = document.getElementById('agentSearchInput').value.trim();
    agentCurrentPage = 1;
    loadAgents();
}

function handleAgentSearch(event) {
    if (event.key === 'Enter') {
        searchAgents();
    }
}

function goToAgentPage(page) {
    if (page < 1 || page > agentTotalPages) return;
    agentCurrentPage = page;
    loadAgents();
}

function renderAgentPagination() {
    const paginationUl = document.getElementById('agentPaginationUl');
    const paginationDiv = document.getElementById('agentPagination');
    if (!paginationUl || !paginationDiv) return;

    if (agentTotalPages <= 1) {
        paginationDiv.style.display = 'none';
        return;
    }

    paginationDiv.style.display = 'flex';

    let html = '';

    html += `
        <li class="page-item ${agentCurrentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="javascript:void(0)" onclick="goToAgentPage(${agentCurrentPage - 1})">
                <i class="fas fa-chevron-left"></i>
            </a>
        </li>
    `;

    const maxVisiblePages = 5;
    let startPage = Math.max(1, agentCurrentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(agentTotalPages, startPage + maxVisiblePages - 1);
    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    if (startPage > 1) {
        html += `
            <li class="page-item">
                <a class="page-link" href="javascript:void(0)" onclick="goToAgentPage(1)">1</a>
            </li>
        `;
        if (startPage > 2) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `
            <li class="page-item ${i === agentCurrentPage ? 'active' : ''}">
                <a class="page-link" href="javascript:void(0)" onclick="goToAgentPage(${i})">${i}</a>
            </li>
        `;
    }

    if (endPage < agentTotalPages) {
        if (endPage < agentTotalPages - 1) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        html += `
            <li class="page-item">
                <a class="page-link" href="javascript:void(0)" onclick="goToAgentPage(${agentTotalPages})">${agentTotalPages}</a>
            </li>
        `;
    }

    html += `
        <li class="page-item ${agentCurrentPage === agentTotalPages ? 'disabled' : ''}">
            <a class="page-link" href="javascript:void(0)" onclick="goToAgentPage(${agentCurrentPage + 1})">
                <i class="fas fa-chevron-right"></i>
            </a>
        </li>
    `;

    paginationUl.innerHTML = html;
}

function loadAgents() {
    const params = new URLSearchParams({
        page: agentCurrentPage,
        page_size: agentPageSize,
        tag: agentCurrentTag,
        search: agentSearchKeyword
    });

    apiRequest(`${API_BASE_URL}/api/agents?` + params.toString(), { errorPrefix: '加载智能体失败' })
        .then(data => {
            const agentList = document.getElementById('agentList');
            const countText = document.getElementById('agentCountText');
            const agents = data.items || [];
            agentTotal = data.total || 0;
            agentTotalPages = data.total_pages || 1;

            if (countText) {
                let countDesc = `共 ${agentTotal} 个智能体`;
                if (agentCurrentTag) {
                    countDesc += ` (标签: ${agentCurrentTag})`;
                }
                if (agentSearchKeyword) {
                    countDesc += ` (搜索: ${agentSearchKeyword})`;
                }
                countText.textContent = countDesc;
            }

            if (!agents || agents.length === 0) {
                agentList.innerHTML = `
                    <div class="text-center py-5">
                        <div class="text-muted">
                            <i class="fas fa-users text-4xl mb-3" style="color: #ccc;"></i>
                            <p>暂无智能体</p>
                        </div>
                    </div>
                `;
                renderAgentPagination();
                return;
            }

            agentList.innerHTML = agents.map(agent => {
                const statusBadge = `<span class="status-badge ${agent.trained ? 'trained' : 'not-trained'}">${agent.trained ? '已训练' : '未训练'}</span>`;
                const metaBadges = [
                    agent.gender ? `<span class="badge bg-light text-dark border">${agent.gender}</span>` : '',
                    agent.age ? `<span class="badge bg-light text-dark border">${agent.age}</span>` : ''
                ].filter(Boolean).join(' ');

                const tagBadges = (agent.tags && agent.tags.length > 0) ? `
                    <div class="agent-tags">
                        ${agent.tags.slice(0, 3).map(tag => `
                            <span class="agent-tag" onclick="event.stopPropagation(); filterByTag('${tag.replace(/'/g, "\\'")}')">${tag}</span>
                        `).join('')}
                        ${agent.tags.length > 3 ? `<span class="agent-tag">+${agent.tags.length - 3}</span>` : ''}
                    </div>
                ` : '';

                const hasVoice = agent.voice_path || (agent.voice_tones && agent.voice_tones.length > 0);
                const playBtn = hasVoice ? `
                    <button class="btn btn-outline-primary btn-sm ms-2 play-voice-btn" 
                        onclick="playAgentVoice('${agent.id}')" 
                        title="试听音色"
                        data-agent-id="${agent.id}">
                        <i class="fas fa-volume-up"></i>
                    </button>
                ` : '';

                return `
                    <div class="agent-card-wrapper">
                        <div class="card agent-card">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <div class="d-flex align-items-center">
                                        <h5 class="card-title mb-0">${agent.name}</h5>
                                    </div>
                                    ${statusBadge}
                                </div>
                                ${metaBadges ? `<div class="mb-2">${metaBadges}</div>` : ''}
                                <p class="card-text text-muted text-truncate mb-0" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${agent.description || '暂无描述'}">${agent.description || '暂无描述'}</p>
                                ${tagBadges}
                                <div class="d-flex justify-content-between align-items-center mt-3">
                                    <div>
                                        ${playBtn}
                                    </div>
                                    <div class="btn-group">
                                        <button class="btn btn-outline-secondary btn-sm" onclick="showEditAgentModal('${agent.id}')">
                                            <i class="fas fa-edit"></i>
                                        </button>
                                        <button class="btn btn-outline-danger btn-sm" onclick="deleteAgent('${agent.id}')">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            renderAgentPagination();
        })
        .catch(e => console.error('加载智能体失败:', e));
}

function updateProgress(percent, text, progressId) {
    const containerId = progressId || 'createProgress';
    const barId = containerId === 'editProgress' ? 'editProgressBar' : 'createProgressBar';
    const textId = containerId === 'editProgress' ? 'editProgressText' : 'createProgressText';
    document.getElementById(barId).style.width = percent + '%';
    document.getElementById(textId).textContent = text;
}

function playAgentVoice(agentId) {
    const btn = document.querySelector(`.play-voice-btn[data-agent-id="${agentId}"]`);
    
    if (currentPlayingAudio && currentPlayingBtn) {
        currentPlayingAudio.pause();
        currentPlayingAudio = null;
        currentPlayingBtn.innerHTML = '<i class="fas fa-volume-up"></i>';
        currentPlayingBtn.classList.remove('playing');
    }

    if (!btn) return;

    const audioUrl = `${API_BASE_URL}/api/agents/voice-preview?agent_id=${agentId}`;
    const audio = new Audio(audioUrl);

    audio.onplay = function() {
        currentPlayingAudio = audio;
        currentPlayingBtn = btn;
        btn.innerHTML = '<i class="fas fa-volume-down"></i>';
        btn.classList.add('playing');
    };

    audio.onended = function() {
        btn.innerHTML = '<i class="fas fa-volume-up"></i>';
        btn.classList.remove('playing');
        currentPlayingAudio = null;
        currentPlayingBtn = null;
    };

    audio.onerror = function() {
        btn.innerHTML = '<i class="fas fa-volume-up"></i>';
        btn.classList.remove('playing');
        currentPlayingAudio = null;
        currentPlayingBtn = null;
        console.error('播放音色试听失败');
    };

    audio.play().catch(e => {
        console.error('播放失败:', e);
        btn.innerHTML = '<i class="fas fa-volume-up"></i>';
        btn.classList.remove('playing');
    });
}

function deleteAgent(agentId) {
    if (!confirm('确定删除此智能体？')) return;

    apiRequest(`/api/agents?agent_id=${agentId}`, { method: 'DELETE', errorPrefix: '删除失败' })
        .then(() => loadAgents())
        .catch(e => console.error('删除失败:', e));
}

function parseTagsInput(inputStr) {
    const tags = [];
    const parts = inputStr.split(/[,\s，、]+/);
    parts.forEach(part => {
        const trimmed = part.trim();
        if (trimmed && !tags.includes(trimmed)) {
            tags.push(trimmed);
        }
    });
    return tags;
}

function collectVoiceTones(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return { tones: [], files: {} };

    const items = container.querySelectorAll('.voice-tone-item');
    const tones = [];
    const files = {};
    let toneIndex = 0;

    items.forEach((item) => {
        const toneName = item.querySelector('.tone-name-input').value.trim();
        if (!toneName) return;

        const toneId = item.dataset.toneId;
        const state = toneAudioStates[toneId];
        const promptText = item.querySelector('.tone-text-input').value.trim();
        const rangeStart = item.querySelector('.range-start-input') ? parseFloat(item.querySelector('.range-start-input').value) || 0 : 0;
        const rangeEnd = item.querySelector('.range-end-input') ? parseFloat(item.querySelector('.range-end-input').value) || 0 : 0;

        const toneData = {
            tone: toneName,
            prompt_text: promptText,
            voice_path: state ? (state.voicePath || '') : '',
            original_path: state ? (state.originalPath || '') : '',
            range_start: rangeStart,
            range_end: rangeEnd
        };

        if (state && state.file) {
            files[toneIndex] = state.file;
        }

        tones.push(toneData);
        toneIndex++;
    });

    return { tones, files };
}

function showAddAgentModal() {
    resetAddAgentForm();
    const modal = new bootstrap.Modal(document.getElementById('addAgentModal'));
    modal.show();
}

function closeAddAgentModal() {
    const modal = bootstrap.Modal.getInstance(document.getElementById('addAgentModal'));
    if (modal) {
        modal.hide();
    }
}

function resetAddAgentForm() {
    document.getElementById('agentName').value = '';
    document.getElementById('agentDescription').value = '';
    document.getElementById('agentGender').value = 'female';
    document.getElementById('agentAge').value = '';
    document.getElementById('agentTags').value = '';
    document.getElementById('createProgress').classList.add('d-none');
    document.getElementById('createAgentBtn').disabled = false;
    document.getElementById('createAgentBtn').innerHTML = '<i class="fas fa-plus"></i> 创建智能体';
    document.getElementById('voiceTonesContainer').innerHTML = '';
}

async function createAgentWithTraining() {
    const name = document.getElementById('agentName').value.trim();
    const description = document.getElementById('agentDescription').value.trim();
    const gender = document.getElementById('agentGender').value;
    const age = document.getElementById('agentAge').value;
    const tagsStr = document.getElementById('agentTags').value.trim();
    const tags = parseTagsInput(tagsStr);

    if (!name) {
        alert('请输入智能体名称');
        return;
    }

    document.getElementById('createAgentBtn').disabled = true;
    document.getElementById('createProgress').classList.remove('d-none');
    updateProgress(5, '正在创建...');

    const formData = new FormData();
    formData.append('name', name);
    formData.append('description', description);
    formData.append('gender', gender);
    formData.append('age', age);
    formData.append('tags', JSON.stringify(tags));

    const { tones: voiceTones, files: toneFiles } = collectVoiceTones('voiceTonesContainer');
    formData.append('voice_tones', JSON.stringify(voiceTones));
    Object.keys(toneFiles).forEach(idx => {
        formData.append(`tone_file_${idx}`, toneFiles[idx]);
    });

    apiRequest(`${API_BASE_URL}/api/agents`, {
        method: 'POST',
        body: formData,
        silent: true,
        errorPrefix: '创建失败'
    })
        .then(data => {
            updateProgress(100, '创建成功！');
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('addAgentModal')).hide();
                loadAgents();
            }, 1000);
        })
        .catch(e => {
            console.error('创建失败:', e);
            updateProgress(0, '创建失败: ' + e.message);
            document.getElementById('createAgentBtn').disabled = false;
        });
}

function showEditAgentModal(agentId) {
    currentEditAgentId = agentId;

    document.getElementById('editProgress').classList.add('d-none');
    document.getElementById('editAgentBtn').disabled = false;
    document.getElementById('editAgentBtn').innerHTML = '<i class="fas fa-save"></i> 保存修改';

    apiRequest(`${API_BASE_URL}/api/agents?agent_id=${agentId}`, { silent: true })
        .then(agent => {
            if (!agent || !agent.name) return;

            document.getElementById('editAgentName').value = agent.name || '';
            document.getElementById('editAgentDescription').value = agent.description || '';
            document.getElementById('editAgentGender').value = agent.gender || 'female';
            document.getElementById('editAgentAge').value = agent.age || '';
            document.getElementById('editAgentTags').value = (agent.tags || []).join(', ');

            const tonesContainer = document.getElementById('editVoiceTonesContainer');
            tonesContainer.innerHTML = '';

            if (agent.voice_tones && agent.voice_tones.length > 0) {
                agent.voice_tones.forEach((tone, index) => {
                    addVoiceToneItem(
                        'editVoiceTonesContainer',
                        tone.tone,
                        tone.prompt_text,
                        tone.voice_path || '',
                        tone.original_path || '',
                        tone.range_start || 0,
                        tone.range_end || 0
                    );
                });
            }

            new bootstrap.Modal(document.getElementById('editAgentModal')).show();
        })
        .catch(e => { console.error('加载智能体信息失败:', e); showToast('加载智能体信息失败', 'error'); });
}

async function saveAgentChanges() {
    if (!currentEditAgentId) return;

    const name = document.getElementById('editAgentName').value.trim();
    const description = document.getElementById('editAgentDescription').value.trim();
    const gender = document.getElementById('editAgentGender').value;
    const age = document.getElementById('editAgentAge').value;
    const tagsStr = document.getElementById('editAgentTags').value.trim();
    const tags = parseTagsInput(tagsStr);

    if (!name) {
        alert('请输入智能体名称');
        return;
    }

    document.getElementById('editAgentBtn').disabled = true;
    document.getElementById('editProgress').classList.remove('d-none');
    updateProgress(5, '正在保存...', 'editProgress');

    const formData = new FormData();
    formData.append('name', name);
    formData.append('description', description);
    formData.append('gender', gender);
    formData.append('age', age);
    formData.append('tags', JSON.stringify(tags));

    const { tones: voiceTones, files: toneFiles } = collectVoiceTones('editVoiceTonesContainer');
    formData.append('voice_tones', JSON.stringify(voiceTones));
    Object.keys(toneFiles).forEach(idx => {
        formData.append(`tone_file_${idx}`, toneFiles[idx]);
    });

    apiRequest(`${API_BASE_URL}/api/agents?agent_id=${currentEditAgentId}`, {
        method: 'PUT',
        body: formData,
        silent: true,
        errorPrefix: '保存失败'
    })
        .then(data => {
            updateProgress(100, '保存成功！', 'editProgress');
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('editAgentModal')).hide();
                loadAgents();
            }, 1000);
        })
        .catch(e => {
            console.error('保存失败:', e);
            updateProgress(0, '保存失败: ' + e.message, 'editProgress');
            document.getElementById('editAgentBtn').disabled = false;
        });
}