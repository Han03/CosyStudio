const AVATAR_COLORS = [
    'linear-gradient(135deg, #667eea, #764ba2)',
    'linear-gradient(135deg, #f093fb, #f5576c)',
    'linear-gradient(135deg, #4facfe, #00f2fe)',
    'linear-gradient(135deg, #43e97b, #38f9d7)',
    'linear-gradient(135deg, #fa709a, #fee140)',
    'linear-gradient(135deg, #30cfd0, #330867)',
    'linear-gradient(135deg, #a8edea, #fed6e3)',
    'linear-gradient(135deg, #ff9a9e, #fecfef)',
    'linear-gradient(135deg, #ffecd2, #fcb69f)',
    'linear-gradient(135deg, #84fab0, #8fd3f4)',
];

const QUICK_INSTRUCTIONS = [
    { label: '平静地说', text: '用平静的语气说' },
    { label: '开心地说', text: '用非常开心的语气说' },
    { label: '生气地说', text: '用愤怒的语气说' },
    { label: '悲伤地说', text: '用悲伤的语气说' },
    { label: '小声地说', text: '小声地说' },
    { label: '大声地说', text: '大声地说' },
    { label: '温柔地说', text: '温柔地说' },
    { label: '冷淡地说', text: '冷淡地说' },
    { label: '紧张地说', text: '紧张地说' },
    { label: '犹豫地说', text: '犹豫地说' },
    { label: '坚定地说', text: '坚定地说' },
    { label: '颤抖地说', text: '颤抖着说' },
];

const SOUND_TAGS = {
    '[叹气]': '叹气', '[叹气声]': '叹气', '[叹息]': '叹气',
    '[苦笑]': '苦笑', '[冷笑]': '冷笑', '[微笑]': '微笑',
    '[轻声]': '轻声', '[低声]': '低声', '[喃喃]': '喃喃',
    '[哽咽]': '哽咽', '[抽泣]': '抽泣', '[哭]': '哭',
    '[笑]': '笑', '[轻笑]': '轻笑', '[大笑]': '大笑',
    '[喘气]': '喘气', '[喘息]': '喘息', '[呼吸急促]': '呼吸急促',
    '[停顿]': '停顿', '[沉默]': '沉默', '[迟疑]': '迟疑',
    '[摇头]': '摇头', '[点头]': '点头', '[皱眉]': '皱眉',
    '[脸红]': '脸红', '[尴尬]': '尴尬', '[害羞]': '害羞',
    '[怒]': '怒', '[愤怒]': '愤怒', '[生气]': '生气',
    '[惊讶]': '惊讶', '[震惊]': '震惊', '[愕然]': '愕然',
    '[疲惫]': '疲惫', '[虚弱]': '虚弱', '[无力]': '无力',
    '[兴奋]': '兴奋', '[激动]': '激动', '[高兴]': '高兴',
};

const SOUND_TAG_REGEX = new RegExp(
    '(' + Object.keys(SOUND_TAGS).map(k => k.replace(/[\\[\](){}*+?^$.|]/g, '\\$&')).join('|') + ')',
    'g'
);

const state = {
    scriptId: null,
    scriptData: null,
    chapters: [],
    currentLines: [],
    currentChapterIndex: -1,
    generatingChapterIndex: -1,
    showOriginalText: true,
    characters: [],
    selectedRole: null,
    agents: [],
    ttsCapabilities: [],
    characterVoiceMap: {},
    isPlaying: false,
    currentPlayingIndex: -1,
    selectedLineId: null,
    audioContext: null,
    audioQueue: [],
    isGeneratingAudio: false,
    isSynthesizing: false,
    streamPlayQueue: [],
    streamIsPlaying: false,
    streamFinished: false,
    streamSampleRate: 24000,
    streamResolve: null,
    streamCurrentSource: null,
    ws: null,
    wsReconnectTimer: null,
    wsReconnectDelay: 2000,
    wsMaxReconnectDelay: 30000,
    wsShouldReconnect: true,
    dragState: {},
    lastFocusedEditor: null,
    lastSavedRange: null,
    _highlightTimer: null,
    saveConfigTimer: null,
    _tonePreviewAudio: null,
    _tonePreviewBtn: null,
    lineAudioStates: {},
    lineAudioParamLastValues: {},
    isPlayingAudio: false,
    nextPlayTime: 0,
    playbackLineId: null,
    playbackStartAudioTime: null,
    playbackStartOffset: 0,
    playbackEndOffset: 0,
    progressAnimationId: null,
    activeSources: [],
    totalPlaybackDuration: 0,
    _currentHistoryLineId: null,
    _chapterHistoryCache: null,
    agentPickerCallback: null,
    agentPickerCurrentId: null,
    agentPickerSearch: '',
    agentPickerGender: '',
    agentPickerAge: '',
    agentPickerPage: 1,
    agentPickerPageSize: 5,
    agentPickerTotal: 0,
    agentPickerTotalPages: 1,
    agentPickerPageItems: [],
    _agentPreviewAudio: null,
    _agentPreviewCurrentAgentId: null,
    rolePickerCallback: null,
    rolePickerCurrentRole: null,
    rolePickerSearch: '',
    _pendingLineId: null,
    currentWorldTab: 'webnovel',
    worldSettingsCategories: [],
    nounCategories: [],
    selectedWorldCategory: '',
    selectedNounCategory: '',
    nounSearchKeyword: '',
    worldSettings: [],

    selectedOutlineId: null,
    chapterPlans: [],
    volumeOutlines: [],
    selectedVolumeOutlineId: null,
    volumeChapterPlans: {},
    writingTasks: [],
    currentTaskFilter: 'all',
    continueTaskId: null,
    continueTargetChapter: -1,
    continueResultText: '',
    selectedContinueChapter: null,
    chapterPlanSelectorData: null,
    webnovelInitialized: false,
};

function getScriptIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('script_id');
}

function getBookIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('book_id');
}

// showToast / showError 已由 api.js 统一提供，此处不再重复定义

function getAvatarColor(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDateTime(timestamp) {
    if (!timestamp) return '未知';
    return new Date(timestamp * 1000).toLocaleString('zh-CN');
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

async function init() {
    state.scriptId = getScriptIdFromUrl();
    const bookId = getBookIdFromUrl();

    // 无 script_id 且无 book_id：进入"创建剧本"模式（Step 1）
    if (!state.scriptId && !bookId) {
        // 加载智能体等基础数据
        await loadAgents();
        // 展示锁定的初始化模态框，从 Step 1 开始
        if (typeof showInitModal === 'function') {
            await showInitModal({ locked: true, startStep: 1 });
        }
        handleGlobalEvents();
        return;
    }

    if (!state.scriptId) {
        await createScriptFromBook(bookId);
    }

    await loadAgents();
    await loadTtsCapabilities();
    const ok = await loadScriptInfo();
    if (!ok) return;
    await loadCharacters();
    renderChapterList();
    if (state.chapters.length > 0) {
        const firstWithLines = state.chapters.find(c => c.has_lines) || state.chapters[0];
        await selectChapter(firstWithLines.chapter_index);
    }
    connectWebSocket();
    handleGlobalEvents();

    // 恢复运行中创作任务的流程进度条（须在 connectWebSocket 之后、WS 消息到达前设置 continueTaskId）
    if (typeof restoreWorkflowProgressBar === 'function') {
        await restoreWorkflowProgressBar();
    }

    // 检测 webnovel 项目是否已初始化，未初始化则自动展示锁定的初始化模态框
    await checkInitStatus();
}

async function checkInitStatus() {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/dashboard?script_id=${state.scriptId}`, {
            silent: true
        });
        if (data.success) {
            state.webnovelInitialized = !!data.initialized;
            if (!data.initialized) {
                // 未初始化：自动展示锁定模态框（从 Step 2 开始，因为已有 script_id）
                if (typeof showInitModal === 'function') {
                    await showInitModal({ locked: true, startStep: 2 });
                }
            }
        }
    } catch (e) {
        console.error('检查初始化状态失败:', e);
    }
}

async function createScriptFromBook(bookId) {
    try {
        const data = await apiRequest('/api/books/scripts/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `book_id=${encodeURIComponent(bookId)}`,
            errorPrefix: '创建剧本失败'
        });
        if (data.success) {
            state.scriptId = data.script_id;
            const params = new URLSearchParams(window.location.search);
            params.set('script_id', state.scriptId);
            window.history.replaceState({}, '', window.location.pathname + '?' + params.toString());
            showToast('剧本已加载', 'success');
        } else {
            showError('创建剧本失败: ' + data.message);
            throw new Error(data.message);
        }
    } catch (e) {
        console.error('创建剧本失败:', e);
        showError('创建剧本失败: ' + e.message);
        throw e;
    }
}

async function loadAgents() {
    try {
        const data = await apiRequest('/api/agents?page_size=1000', { silent: true });
        if (Array.isArray(data)) {
            state.agents = data;
        } else if (data.items) {
            state.agents = data.items;
        } else if (data.success) {
            state.agents = data.agents || [];
        }
    } catch (e) {
        console.error('加载智能体列表失败:', e);
    }
}

async function loadTtsCapabilities() {
    try {
        const data = await apiRequest('/api/capabilities/type?capability_type=text_to_speech', { silent: true });
        if (data && Array.isArray(data.capabilities)) {
            state.ttsCapabilities = data.capabilities;
        }
    } catch (e) {
        console.error('加载TTS能力列表失败:', e);
    }
}

async function loadScriptInfo() {
    try {
        const data = await apiRequest(`/api/books/scripts?script_id=${state.scriptId}`, {
            silent: true,
            errorPrefix: '加载剧本失败'
        });
        if (data.success) {
            state.scriptData = data.script;
            state.chapters = data.chapters || [];
            setScriptTitle(state.scriptData.name, { silent: true });
            // 与深度初始化弹窗的书名联动（silent:true 时 setScriptTitle 不会同步这些字段，所以手动同步）
            const loadedName = state.scriptData.name || '';
            const initTitleEl = document.getElementById('initTitle');
            if (initTitleEl && document.activeElement?.id !== 'initTitle') {
                initTitleEl.value = loadedName;
            }
            // 同步 Step 1 的书名输入框
            const initCreateNameEl = document.getElementById('initCreateBookName');
            if (initCreateNameEl && document.activeElement?.id !== 'initCreateBookName') {
                if (!initCreateNameEl.value.trim() || initCreateNameEl.dataset.autoFilled === 'true') {
                    initCreateNameEl.value = loadedName;
                    initCreateNameEl.dataset.autoFilled = 'true';
                }
            }
            document.getElementById('scriptMeta').textContent =
                `${state.scriptData.chapter_count} 章 · ${state.scriptData.line_count || 0} 句 · ${state.scriptData.created_at_str || ''}`;
            updateStatusBadge(state.scriptData.status || 'ready');
            // 检测初始化中状态，展示任务遮罩
            if (state.scriptData.status === 'initializing') {
                if (typeof showInitTaskMask === 'function') {
                    showInitTaskMask(state.scriptData.progress_message || '深度初始化中...');
                }
            }
        } else {
            showError('加载剧本失败');
            return false;
        }
    } catch (e) {
        console.error('加载剧本信息失败:', e);
        showError('加载剧本失败: ' + e.message);
        return false;
    }
    return true;
}

function setScriptTitle(name, opts = {}) {
    if (!name) return;
    if (state.scriptData) state.scriptData.name = name;
    const titleEl = document.getElementById('scriptTitle');
    if (titleEl && titleEl.textContent !== name) {
        titleEl.textContent = name;
    }
    document.title = `${name} - 剧本编辑器`;
    // 同步 Step 2 的只读书名（深度初始化模态框内）
    const initTitleEl = document.getElementById('initTitle');
    if (initTitleEl && opts.silent !== true && document.activeElement?.id !== 'initTitle') {
        initTitleEl.value = name;
    }
    // 同步 Step 1 的可编辑书名（深度初始化模态框内），仅当未获得焦点且用户未手动输入时
    const initCreateNameEl = document.getElementById('initCreateBookName');
    if (initCreateNameEl && opts.silent !== true && document.activeElement?.id !== 'initCreateBookName') {
        if (!initCreateNameEl.value.trim() || initCreateNameEl.dataset.autoFilled === 'true') {
            initCreateNameEl.value = name;
            initCreateNameEl.dataset.autoFilled = 'true';
        }
    }
}

function showTitleEditor() {
    const titleEl = document.getElementById('scriptTitle');
    const inputEl = document.getElementById('scriptTitleInput');
    const btnEl = document.getElementById('editTitleBtn');
    inputEl.value = state.scriptData?.name || titleEl.textContent || '';
    titleEl.style.display = 'none';
    if (btnEl) btnEl.style.display = 'none';
    inputEl.style.display = 'inline-block';
    inputEl.focus();
    inputEl.select();
}

async function saveTitle() {
    const titleEl = document.getElementById('scriptTitle');
    const inputEl = document.getElementById('scriptTitleInput');
    const btnEl = document.getElementById('editTitleBtn');
    const newName = (inputEl.value || '').trim();
    if (!newName) {
        showToast('书名不能为空', 'warning');
        inputEl.focus();
        return;
    }
    const oldName = state.scriptData?.name || '';
    if (oldName === newName) {
        titleEl.style.display = '';
        if (btnEl) btnEl.style.display = '';
        inputEl.style.display = 'none';
        return;
    }
    try {
        const data = await apiRequest(`/api/books/scripts/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_id: state.scriptId, name: newName }),
            errorPrefix: '保存失败'
        });
        if (data.success) {
            setScriptTitle(newName);
            showToast('书名已更新', 'success');
        } else {
            showToast(data.message || '保存失败', 'error');
            inputEl.value = oldName;
        }
    } catch (e) {
        console.error('保存书名失败:', e);
        showToast('保存失败: ' + e.message, 'error');
        inputEl.value = oldName;
    } finally {
        titleEl.style.display = '';
        if (btnEl) btnEl.style.display = '';
        inputEl.style.display = 'none';
    }
}