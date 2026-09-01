// ========== 深度初始化（一键模式） ==========

let ocAllInOneSets = [];       // AI 生成的 3 套完整方案
let ocSelectedSetIndex = -1;   // 当前选中的方案索引
let ocModalLocked = false;     // 模态框锁定状态

/** 打开一键初始化模态框 */
async function showInitModalOneClick(opts = {}) {
    const { locked = false } = opts;
    ocModalLocked = locked;
    updateOCModalLock();

    document.getElementById('initModalOneClick').style.display = 'flex';
    resetAllInOneFields();
    ocAllInOneSets = [];
    ocSelectedSetIndex = -1;

    // 自动填充书名
    const scriptName = state.scriptData?.name || '';
    const titleEl = document.getElementById('initTitle_oc');
    if (titleEl) {
        titleEl.value = scriptName;
        titleEl.readOnly = true;
    }

    // 加载题材列表
    document.getElementById('initGenre_oc').innerHTML = '<option value="">请选择题材...</option>';
    try {
        const data = await apiRequest('/api/books/scripts/genres', { silent: true });
        if (data.success && data.genres) {
            const select = document.getElementById('initGenre_oc');
            data.genres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre;
                option.textContent = genre;
                select.appendChild(option);
            });
        }
    } catch (e) {
        console.error('加载题材列表失败:', e);
    }

    // 创建 init session（如果还没有）
    if (state.scriptId) {
        await createInitSession();
    }

    // 如果有已保存的 initData，回填到一键表单
    if (Object.keys(initData).length > 0) {
        fillAllInOneFormData(initData);
    }
}

/** 关闭一键模态框 */
function closeInitModalOneClick() {
    if (ocModalLocked) return;
    document.getElementById('initModalOneClick').style.display = 'none';
}

/** 更新模态框锁定状态 */
function updateOCModalLock() {
    const closeBtn = document.getElementById('initOCCloseBtn');
    const footerCloseBtn = document.getElementById('initOCFooterCloseBtn');
    if (closeBtn) closeBtn.style.display = ocModalLocked ? 'none' : '';
    if (footerCloseBtn) footerCloseBtn.style.display = ocModalLocked ? 'none' : '';
}

/** 切换到一键模式（从分步模式） */
async function switchToInitOneClick() {
    // 保存当前分步模式的表单数据到 initData
    if (currentInitStep >= 2 && currentInitStep <= 6) {
        saveStepData(currentInitStep);
    }

    // 关闭分步模态框
    document.getElementById('initModal').style.display = 'none';

    // 打开一键模态框
    await showInitModalOneClick({ locked: initModalLocked });
}

/** 切换到分步模式（从一键模式） */
async function switchToInitStepByStep() {
    // 收集一键模式的表单数据到 initData
    collectAllInOneFormData();
    // 保存一份副本，因为 showInitModal 会重置 initData
    const savedInitData = JSON.parse(JSON.stringify(initData));

    // 关闭一键模态框
    document.getElementById('initModalOneClick').style.display = 'none';

    // 打开分步模态框
    await showInitModal({ locked: ocModalLocked });

    // showInitModal 会 resetAllFields + restoreInitData，可能覆盖我们的数据
    // 用保存的副本重新填充
    initData = savedInitData;

    // 回填已收集的数据到分步表单
    if (initData.project) {
        const p = initData.project;
        if (p.title) document.getElementById('initTitle').value = p.title;
        if (p.genre) document.getElementById('initGenre').value = p.genre;
        if (p.target_words) document.getElementById('initTargetWords').value = p.target_words;
        if (p.target_chapters) document.getElementById('initTargetChapters').value = p.target_chapters;
        if (p.one_liner) document.getElementById('initOneLiner').value = p.one_liner;
        if (p.core_conflict) document.getElementById('initCoreConflict').value = p.core_conflict;
        if (p.target_reader) document.getElementById('initTargetReader').value = p.target_reader;
        if (p.platform) document.getElementById('initPlatform').value = p.platform;
    }
    if (initData.protagonist) {
        const c = initData.protagonist;
        if (c.name) document.getElementById('initProtagonistName').value = c.name;
        if (c.archetype) document.getElementById('initProtagonistArchetype').value = c.archetype;
        if (c.desire) document.getElementById('initProtagonistDesire').value = c.desire;
        if (c.flaw) document.getElementById('initProtagonistFlaw').value = c.flaw;
        if (c.structure) document.getElementById('initProtagonistStructure').value = c.structure;
    }
    if (initData.relationship) {
        const r = initData.relationship;
        if (r.heroine_config) document.getElementById('initHeroineConfig').value = r.heroine_config;
        if (r.antagonist_level) document.getElementById('initAntagonistLevel').value = r.antagonist_level;
        if (r.antagonist_mirror) document.getElementById('initVillainMirror').value = r.antagonist_mirror;
    }
    if (initData.golden_finger) {
        const g = initData.golden_finger;
        if (g.type) document.getElementById('initGoldenFingerType').value = g.type;
        if (g.name) document.getElementById('initGoldenFingerName').value = g.name;
        if (g.style) document.getElementById('initGoldenFingerStyle').value = g.style;
        if (g.visibility) document.getElementById('initGoldenFingerVisibility').value = g.visibility;
        if (g.irreversible_cost) document.getElementById('initGoldenFingerCost').value = g.irreversible_cost;
    }
    if (initData.world) {
        const w = initData.world;
        if (w.scale) document.getElementById('initWorldScale').value = w.scale;
        if (w.power_system_type) document.getElementById('initPowerSystemType').value = w.power_system_type;
        if (w.factions) document.getElementById('initFactions').value = w.factions;
        if (w.social_class) document.getElementById('initSocialClass').value = w.social_class;
        if (w.currency_system) document.getElementById('initCurrencySystem').value = w.currency_system;
        if (w.cultivation_chain) document.getElementById('initCultivationChain').value = w.cultivation_chain;
        if (w.sect_hierarchy) document.getElementById('initSectHierarchy').value = w.sect_hierarchy;
    }
    if (initData.constraints) {
        const cs = initData.constraints;
        if (cs.anti_trope) document.getElementById('initAntiTrope').value = cs.anti_trope;
        if (cs.hard_constraints) document.getElementById('initConstraints').value = Array.isArray(cs.hard_constraints) ? cs.hard_constraints.join('\n') : cs.hard_constraints;
        if (cs.core_selling_points) document.getElementById('initCoreSellingPoints').value = cs.core_selling_points;
        if (cs.opening_hook) document.getElementById('initOpeningHook').value = cs.opening_hook;
    }

    // 恢复 AI 占位区域状态
    for (let s = 2; s <= 6; s++) {
        const dataKey = getDataKeyForStep(s);
        const hasData = dataKey && initData[dataKey] && Object.keys(initData[dataKey]).length > 0;
        if (hasData) {
            showAiResult(s);
        } else {
            showAiPlaceholder(s);
        }
    }
}

/** 一键 AI 生成：调用 generate-all API */
async function generateAllInOne() {
    const placeholder = document.getElementById('ocAiPlaceholder');
    const loading = document.getElementById('ocAiLoading');
    const result = document.getElementById('ocAiResult');
    const setsContainer = document.getElementById('ocSetsContainer');

    placeholder.style.display = 'none';
    loading.style.display = 'flex';
    result.style.display = 'none';
    setsContainer.style.display = 'none';

    try {
        // 先收集当前表单数据作为上下文
        collectAllInOneFormData();

        const currentStepData = {};
        if (initData.project) currentStepData.project = initData.project;
        if (initData.protagonist) currentStepData.protagonist = initData.protagonist;
        if (initData.relationship) currentStepData.relationship = initData.relationship;
        if (initData.golden_finger) currentStepData.golden_finger = initData.golden_finger;
        if (initData.world) currentStepData.world = initData.world;
        if (initData.constraints) currentStepData.constraints = initData.constraints;

        const data = await apiRequest('/api/books/scripts/webnovel/init/ai/generate-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script_id: state.scriptId,
                current_data: currentStepData
            }),
            errorPrefix: 'AI生成失败'
        });

        loading.style.display = 'none';

        if (data.success && data.data && data.data.sets) {
            ocAllInOneSets = data.data.sets;
            ocSelectedSetIndex = -1;
            renderAllInOneSets(ocAllInOneSets);
            result.style.display = 'block';
            result.innerHTML = `<div class="option-hint" style="margin-bottom:8px;"><span><i class="fas fa-wand-magic-sparkles"></i> 已为你智能生成 ${ocAllInOneSets.length} 套完整方案，点击选择后自动填充所有表单</span><button class="btn-regenerate" onclick="generateAllInOne()"><i class="fas fa-rotate"></i> 重新生成</button></div>`;
            setsContainer.style.display = 'flex';
        } else {
            placeholder.style.display = 'flex';
            showToast('AI生成失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('AI生成失败:', e);
        loading.style.display = 'none';
        placeholder.style.display = 'flex';
        showToast('AI生成失败: ' + e.message, 'error');
    }
}

/** 渲染 3 套方案卡片 */
function renderAllInOneSets(sets) {
    const container = document.getElementById('ocSetsContainer');
    if (!container) return;

    let html = '';
    sets.forEach((set, index) => {
        const isSelected = ocSelectedSetIndex === index;
        const setName = escapeHtml(set.set_name || `方案${String.fromCharCode(65 + index)}`);
        const project = set.project || {};
        const protagonist = set.protagonist || {};
        const goldenFinger = set.golden_finger || {};
        const world = set.world || {};
        const totalScore = _calcTotalScore(set.scoring);

        html += `<div class="all-in-one-set-card ${isSelected ? 'selected' : ''}" onclick="selectAllInOneSet(${index})">
            <div class="oc-card-header">
                <span class="oc-card-check"><i class="fas ${isSelected ? 'fa-check-circle' : 'fa-circle'}"></i></span>
                <span class="oc-card-name">${setName}</span>
                <span class="oc-card-score"><span class="score-num">${totalScore}</span>分</span>
            </div>
            <div class="oc-card-body">
                <div class="oc-card-field"><strong>题材:</strong> ${escapeHtml(project.genre || '')}</div>
                <div class="oc-card-field"><strong>一句话:</strong> ${escapeHtml((project.one_liner || '').slice(0, 30))}${(project.one_liner || '').length > 30 ? '...' : ''}</div>
                <div class="oc-card-field"><strong>主角:</strong> ${escapeHtml(protagonist.name || '')} · ${escapeHtml(protagonist.archetype || '')}</div>
                <div class="oc-card-field"><strong>金手指:</strong> ${escapeHtml(goldenFinger.type || '')} · ${escapeHtml(goldenFinger.name || '')}</div>
                <div class="oc-card-field"><strong>世界观:</strong> ${escapeHtml(world.scale || '')} · ${escapeHtml(world.power_system_type || '')}</div>
            </div>
        </div>`;
    });

    container.innerHTML = html;
}

/** 选择一套方案，高亮并回填表单 */
function selectAllInOneSet(index) {
    ocSelectedSetIndex = index;
    renderAllInOneSets(ocAllInOneSets);

    const set = ocAllInOneSets[index];
    if (!set) return;

    fillAllInOneFormData(set);

    // 同步到 initData
    collectAllInOneFormData();
}

/** 将一套方案数据填充到一键模态框表单 */
function fillAllInOneFormData(data) {
    // data 可能是一整套方案（含 project/protagonist/golden_finger/world/constraints）
    // 也可能是 initData 对象（结构相同）
    const project = data.project || {};
    const protagonist = data.protagonist || {};
    const relationship = data.relationship || {};
    const goldenFinger = data.golden_finger || {};
    const world = data.world || {};
    const constraints = data.constraints || {};

    // Section 1: 故事核
    const titleEl = document.getElementById('initTitle_oc');
    if (titleEl && project.title) titleEl.value = project.title;
    _setSelectValue('initGenre_oc', project.genre);
    _setVal('initTargetWords_oc', project.target_words);
    _setVal('initTargetChapters_oc', project.target_chapters);
    _setVal('initOneLiner_oc', project.one_liner);
    _setVal('initCoreConflict_oc', project.core_conflict);
    _setVal('initTargetReader_oc', project.target_reader);
    _setVal('initPlatform_oc', project.platform);

    // Section 2: 角色
    _setVal('initProtagonistName_oc', protagonist.name);
    _setVal('initProtagonistArchetype_oc', protagonist.archetype);
    _setVal('initProtagonistDesire_oc', protagonist.desire);
    _setVal('initProtagonistFlaw_oc', protagonist.flaw);
    _setSelectValue('initProtagonistStructure_oc', protagonist.structure);
    _setSelectValue('initHeroineConfig_oc', relationship.heroine_config);
    _setSelectValue('initAntagonistLevel_oc', relationship.antagonist_level);
    _setVal('initVillainMirror_oc', protagonist.villain_mirror || relationship.antagonist_mirror);

    // Section 3: 金手指
    _setSelectValue('initGoldenFingerType_oc', goldenFinger.type);
    _setVal('initGoldenFingerName_oc', goldenFinger.name);
    _setSelectValue('initGoldenFingerStyle_oc', goldenFinger.style);
    _setSelectValue('initGoldenFingerVisibility_oc', goldenFinger.visibility);
    _setVal('initGoldenFingerCost_oc', goldenFinger.irreversible_cost);

    // Section 4: 世界观
    _setSelectValue('initWorldScale_oc', world.scale);
    _setSelectValue('initPowerSystemType_oc', world.power_system_type);
    _setVal('initFactions_oc', world.factions);
    _setVal('initSocialClass_oc', world.social_class);
    _setVal('initCurrencySystem_oc', world.currency_system);
    _setVal('initCultivationChain_oc', world.cultivation_chain);
    _setVal('initSectHierarchy_oc', world.sect_hierarchy);

    // Section 5: 约束包
    _setVal('initAntiTrope_oc', constraints.anti_trope || constraints.anti_trope_rule);
    const hardConstraints = constraints.hard_constraints;
    if (hardConstraints) {
        _setVal('initConstraints_oc', Array.isArray(hardConstraints) ? hardConstraints.join('\n') : hardConstraints);
    }
    _setVal('initCoreSellingPoints_oc', constraints.core_selling_points);
    _setVal('initOpeningHook_oc', constraints.opening_hook);
}

/** 收集一键模态框表单数据到 initData */
function collectAllInOneFormData() {
    initData.project = {
        title: _getVal('initTitle_oc'),
        genre: _getVal('initGenre_oc'),
        target_words: parseInt(_getVal('initTargetWords_oc')) || 0,
        target_chapters: parseInt(_getVal('initTargetChapters_oc')) || 0,
        one_liner: _getVal('initOneLiner_oc'),
        core_conflict: _getVal('initCoreConflict_oc'),
        target_reader: _getVal('initTargetReader_oc'),
        platform: _getVal('initPlatform_oc')
    };
    initData.protagonist = {
        name: _getVal('initProtagonistName_oc'),
        archetype: _getVal('initProtagonistArchetype_oc'),
        desire: _getVal('initProtagonistDesire_oc'),
        flaw: _getVal('initProtagonistFlaw_oc'),
        structure: _getVal('initProtagonistStructure_oc')
    };
    initData.relationship = {
        heroine_config: _getVal('initHeroineConfig_oc'),
        antagonist_level: _getVal('initAntagonistLevel_oc'),
        antagonist_mirror: _getVal('initVillainMirror_oc')
    };
    initData.golden_finger = {
        type: _getVal('initGoldenFingerType_oc'),
        name: _getVal('initGoldenFingerName_oc'),
        style: _getVal('initGoldenFingerStyle_oc'),
        visibility: _getVal('initGoldenFingerVisibility_oc'),
        irreversible_cost: _getVal('initGoldenFingerCost_oc')
    };
    initData.world = {
        scale: _getVal('initWorldScale_oc'),
        power_system_type: _getVal('initPowerSystemType_oc'),
        factions: _getVal('initFactions_oc'),
        social_class: _getVal('initSocialClass_oc'),
        currency_system: _getVal('initCurrencySystem_oc'),
        cultivation_chain: _getVal('initCultivationChain_oc'),
        sect_hierarchy: _getVal('initSectHierarchy_oc')
    };
    const hardText = _getVal('initConstraints_oc');
    initData.constraints = {
        anti_trope: _getVal('initAntiTrope_oc'),
        hard_constraints: hardText ? hardText.split('\n').map(s => s.trim()).filter(Boolean) : '',
        core_selling_points: _getVal('initCoreSellingPoints_oc'),
        opening_hook: _getVal('initOpeningHook_oc')
    };
}

/** 确认并初始化（一键模式） */
async function confirmInitOneClick() {
    if (isSubmitting) return;

    // 验证必填字段
    if (!_getVal('initGenre_oc')) { alert('请选择题材'); return; }
    if (!_getVal('initOneLiner_oc')) { alert('请输入一句话故事'); return; }
    if (!_getVal('initCoreConflict_oc')) { alert('请输入核心冲突'); return; }
    if (!_getVal('initProtagonistName_oc')) { alert('请输入主角姓名'); return; }
    if (!_getVal('initProtagonistDesire_oc')) { alert('请输入主角欲望'); return; }
    if (!_getVal('initProtagonistFlaw_oc')) { alert('请输入主角缺陷'); return; }
    if (!_getVal('initGoldenFingerCost_oc')) { alert('请输入金手指不可逆代价'); return; }
    if (!_getVal('initWorldScale_oc')) { alert('请选择世界规模'); return; }
    if (!_getVal('initPowerSystemType_oc')) { alert('请选择力量体系类型'); return; }

    // 二次确认
    const isReinit = !!state.webnovelInitialized;
    const confirmMsg = isReinit
        ? '该项目已完成初始化，重新初始化将覆盖所有现有设定数据（角色、世界观、章节等），确定要继续吗？'
        : '确认提交所有设定并启动深度初始化？';
    if (!confirm(confirmMsg)) return;

    isSubmitting = true;
    const btn = document.getElementById('initOCConfirmBtn');
    const originalText = btn.textContent;
    btn.textContent = '处理中...';
    btn.disabled = true;

    try {
        // 收集表单数据
        collectAllInOneFormData();

        // 按步骤保存到后端（复用现有逻辑）
        for (let step = 2; step <= 6; step++) {
            const data = initData[getStepKey(step)] || {};
            const body = {
                script_id: state.scriptId,
                step: step,
                data: data
            };
            if (step === 3 && initData.relationship) {
                body.data = { ...body.data, relationship: initData.relationship };
            }
            await apiRequest(`/api/books/scripts/webnovel/init/step/${step}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                silent: true
            });
        }

        // 调用确认接口
        const data = await apiRequest('/api/books/scripts/webnovel/init/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_id: state.scriptId }),
            errorPrefix: '初始化失败'
        });

        if (data.success) {
            ocModalLocked = false;
            updateOCModalLock();
            closeInitModalOneClick();
            showInitTaskMask('准备中...');
            if (state.scriptData) state.scriptData.status = 'initializing';
            updateStatusBadge('initializing');
            state.wsShouldReconnect = true;
            if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
                if (typeof connectWebSocket === 'function') connectWebSocket();
            }
        } else {
            showToast('初始化启动失败: ' + (data.message || data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('确认初始化失败:', e);
        showToast('确认初始化失败: ' + e.message, 'error');
    } finally {
        isSubmitting = false;
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

/** 重置一键模态框所有字段 */
function resetAllInOneFields() {
    _setVal('initTitle_oc', '');
    _setVal('initTargetWords_oc', '');
    _setVal('initTargetChapters_oc', '');
    _setVal('initOneLiner_oc', '');
    _setVal('initCoreConflict_oc', '');
    _setVal('initTargetReader_oc', '');
    _setVal('initPlatform_oc', '');

    _setVal('initProtagonistName_oc', '');
    _setVal('initProtagonistArchetype_oc', '');
    _setVal('initProtagonistDesire_oc', '');
    _setVal('initProtagonistFlaw_oc', '');
    _setSelectValue('initProtagonistStructure_oc', '单主角');
    _setSelectValue('initHeroineConfig_oc', '无女主');
    _setSelectValue('initAntagonistLevel_oc', 'BOSS级');
    _setVal('initVillainMirror_oc', '');

    _setSelectValue('initGoldenFingerType_oc', '无金手指');
    _setVal('initGoldenFingerName_oc', '');
    _setSelectValue('initGoldenFingerStyle_oc', '辅助型');
    _setSelectValue('initGoldenFingerVisibility_oc', '隐藏');
    _setVal('initGoldenFingerCost_oc', '');

    _setSelectValue('initWorldScale_oc', '大陆');
    _setSelectValue('initPowerSystemType_oc', '无');
    _setVal('initFactions_oc', '');
    _setVal('initSocialClass_oc', '');
    _setVal('initCurrencySystem_oc', '');
    _setVal('initCultivationChain_oc', '');
    _setVal('initSectHierarchy_oc', '');

    _setVal('initAntiTrope_oc', '');
    _setVal('initConstraints_oc', '');
    _setVal('initCoreSellingPoints_oc', '');
    _setVal('initOpeningHook_oc', '');

    // 重置 AI 区域
    document.getElementById('ocAiPlaceholder').style.display = 'flex';
    document.getElementById('ocAiLoading').style.display = 'none';
    document.getElementById('ocAiResult').style.display = 'none';
    document.getElementById('ocSetsContainer').style.display = 'none';
    document.getElementById('ocSetsContainer').innerHTML = '';
}

/** 折叠/展开 section */
function toggleOCSection(bodyId) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    const isHidden = body.style.display === 'none';
    body.style.display = isHidden ? 'block' : 'none';

    // 旋转箭头
    const arrowId = bodyId.replace('Body', 'Arrow');
    const arrow = document.getElementById(arrowId);
    if (arrow) {
        arrow.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(-90deg)';
    }
}

// ── 辅助函数 ──

function _getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function _setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val !== undefined && val !== null ? String(val) : '';
}

function _setSelectValue(id, val) {
    const el = document.getElementById(id);
    if (!el || !val) return;
    if (typeof setSelectValue === 'function') {
        setSelectValue(el, String(val));
    } else {
        const opts = Array.from(el.options).map(o => o.value);
        if (opts.includes(val)) {
            el.value = val;
        }
    }
}
