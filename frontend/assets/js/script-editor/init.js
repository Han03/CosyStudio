// ========== 深度初始化（分步式） ==========

let currentInitStep = 2;
let initData = {};
let isSubmitting = false;
let initModalLocked = false; // 模态框锁定（未初始化时不允许关闭）

async function showInitModal(opts = {}) {
    const { locked = false, startStep = null } = opts;
    initModalLocked = locked;
    updateInitModalLock();

    document.getElementById('initModal').style.display = 'flex';
    document.getElementById('initProgressContainer').style.display = 'none';
    document.getElementById('initPrevBtn').style.display = 'none';
    document.getElementById('initCancelBtn').style.display = 'none';
    document.getElementById('initNextBtn').style.display = 'block';

    resetAllFields();

    // 决定起始步骤：无 script_id 时从 Step 1 开始，否则从 Step 2 开始
    if (startStep) {
        currentInitStep = startStep;
    } else if (!state.scriptId) {
        currentInitStep = 1;
    } else {
        currentInitStep = 2;
    }
    initData = {};

    // 深度初始化打开时，用剧本编辑器的书名自动填充模态框书名（只读，不可编辑）
    const initTitleEl = document.getElementById('initTitle');
    const initCreateNameEl = document.getElementById('initCreateBookName');
    const scriptName = state.scriptData?.name || '';
    if (initTitleEl) {
        initTitleEl.value = scriptName;
        initTitleEl.readOnly = true;
    }
    // Step 1 的书名输入框也自动填充已有书名（可编辑）
    if (initCreateNameEl) {
        // 用户手动修改时清除 autoFilled 标记（只绑定一次）
        if (!initCreateNameEl.dataset.inputBound) {
            initCreateNameEl.addEventListener('input', function() {
                this.dataset.autoFilled = 'false';
            });
            initCreateNameEl.dataset.inputBound = 'true';
        }
        if (!initCreateNameEl.value.trim()) {
            initCreateNameEl.value = scriptName;
            initCreateNameEl.dataset.autoFilled = 'true';
        }
    }
    if (window.setScriptTitle && scriptName) {
        setScriptTitle(scriptName, { silent: true });
    }

    document.getElementById('initGenre').innerHTML = '<option value="">请选择题材...</option>';
    try {
        const data = await apiRequest('/api/books/scripts/genres', { silent: true });
        if (data.success && data.genres) {
            const select = document.getElementById('initGenre');
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

    // Step 1 不需要创建 init session；有 script_id 时才创建
    if (state.scriptId && currentInitStep >= 2) {
        await createInitSession();
        // 创建/获取 session 后，尝试从后端恢复已保存的步骤数据
        await restoreInitData();
    }
    updateStepUI();
}

function updateInitModalLock() {
    // 锁定模式下隐藏所有关闭入口
    const closeBtn = document.getElementById('initModalCloseBtn');
    const footerCloseBtn = document.getElementById('initModalFooterCloseBtn');
    if (closeBtn) closeBtn.style.display = initModalLocked ? 'none' : '';
    if (footerCloseBtn) footerCloseBtn.style.display = initModalLocked ? 'none' : '';
}

async function createInitSession() {
    try {
        const data = await apiRequest('/api/books/scripts/webnovel/init/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_id: state.scriptId }),
            silent: true
        });
        if (data.success) {
            state.initSessionId = data.session_id;
            currentInitStep = data.current_step || currentInitStep;
        } else {
            // 若项目已初始化或创建会话失败，保持模态框可打开，仅记录日志
            console.warn('创建初始化会话未成功:', data.detail || data.message || '未知原因');
            showToast(data.message || '项目已初始化，可查看已有配置', 'info');
            currentInitStep = currentInitStep || 2;
        }
    } catch (e) {
        console.error('创建初始化会话失败:', e);
        showToast('初始化会话异常，继续查看配置', 'warning');
    }
}

/**
 * 从后端恢复已保存的初始化步骤数据，回填表单并跳转到正确步骤。
 */
async function restoreInitData() {
    if (!state.scriptId) return;
    try {
        const result = await apiRequest(`/api/books/scripts/webnovel/init/session?script_id=${state.scriptId}`, { silent: true });
        if (!result.success || !result.data) return;

        const d = result.data;

        // 恢复 initData 内存对象
        if (d.project_data && Object.keys(d.project_data).length > 0) {
            initData.project = d.project_data;
        }
        if (d.protagonist_data && Object.keys(d.protagonist_data).length > 0) {
            initData.protagonist = d.protagonist_data;
        }
        if (d.relationship_data && Object.keys(d.relationship_data).length > 0) {
            initData.relationship = d.relationship_data;
        }
        if (d.golden_finger_data && Object.keys(d.golden_finger_data).length > 0) {
            initData.golden_finger = d.golden_finger_data;
        }
        if (d.world_data && Object.keys(d.world_data).length > 0) {
            initData.world = d.world_data;
        }
        if (d.constraints_data && Object.keys(d.constraints_data).length > 0) {
            initData.constraints = d.constraints_data;
        }

        // 回填 Step 2 - 故事核与商业定位
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

        // 回填 Step 3 - 角色骨架与关系冲突
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

        // 回填 Step 4 - 金手指
        if (initData.golden_finger) {
            const g = initData.golden_finger;
            if (g.type) document.getElementById('initGoldenFingerType').value = g.type;
            if (g.name) document.getElementById('initGoldenFingerName').value = g.name;
            if (g.style) document.getElementById('initGoldenFingerStyle').value = g.style;
            if (g.visibility) document.getElementById('initGoldenFingerVisibility').value = g.visibility;
            if (g.irreversible_cost) document.getElementById('initGoldenFingerCost').value = g.irreversible_cost;
        }

        // 回填 Step 5 - 世界观
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

        // 回填 Step 6 - 创意约束包
        if (initData.constraints) {
            const cs = initData.constraints;
            if (cs.anti_trope) document.getElementById('initAntiTrope').value = cs.anti_trope;
            if (cs.hard_constraints) document.getElementById('initConstraints').value = Array.isArray(cs.hard_constraints) ? cs.hard_constraints.join('\n') : cs.hard_constraints;
            if (cs.core_selling_points) document.getElementById('initCoreSellingPoints').value = cs.core_selling_points;
            if (cs.opening_hook) document.getElementById('initOpeningHook').value = cs.opening_hook;
        }

        // 跳转到后端保存的当前步骤
        if (result.current_step && result.current_step >= 2 && result.current_step <= 7) {
            currentInitStep = result.current_step;
        }

        // 恢复 AI 占位区域状态：有已保存数据的步骤显示结果态，否则显示占位卡片
        for (let s = 2; s <= 6; s++) {
            const dataKey = getDataKeyForStep(s);
            const hasData = dataKey && initData[dataKey] && Object.keys(initData[dataKey]).length > 0;
            if (hasData) {
                showAiResult(s);
            } else {
                showAiPlaceholder(s);
            }
        }

        console.log('[init] 已恢复初始化数据，当前步骤:', currentInitStep);
    } catch (e) {
        console.warn('[init] 恢复初始化数据失败:', e);
    }
}

function resetAllFields() {
    // 重置所有 AI 占位区域
    for (let s = 2; s <= 6; s++) {
        showAiPlaceholder(s);
    }

    // 清除步骤 2-5 选项状态
    stepOptions = { 2: [], 3: [], 4: [], 5: [] };
    stepSelectedIndex = { 2: -1, 3: -1, 4: -1, 5: -1 };
    for (let s = 2; s <= 5; s++) {
        const container = document.getElementById(`step${s}OptionsContainer`);
        const list = document.getElementById(`step${s}OptionsList`);
        if (container) container.style.display = 'none';
        if (list) list.innerHTML = '';
    }

    // Step 1 字段
    const createBookName = document.getElementById('initCreateBookName');
    if (createBookName) createBookName.value = '';
    const createBookAuthor = document.getElementById('initCreateBookAuthor');
    if (createBookAuthor) createBookAuthor.value = '';
    const createBookDesc = document.getElementById('initCreateBookDesc');
    if (createBookDesc) createBookDesc.value = '';

    document.getElementById('initTitle').value = '';
    document.getElementById('initTargetWords').value = '';
    document.getElementById('initTargetChapters').value = '';
    document.getElementById('initOneLiner').value = '';
    document.getElementById('initCoreConflict').value = '';
    document.getElementById('initTargetReader').value = '';
    document.getElementById('initPlatform').value = '';
    
    document.getElementById('initProtagonistName').value = '';
    document.getElementById('initProtagonistArchetype').value = '';
    document.getElementById('initProtagonistDesire').value = '';
    document.getElementById('initProtagonistFlaw').value = '';
    document.getElementById('initProtagonistStructure').value = '单主角';
    document.getElementById('initHeroineConfig').value = '无女主';
    document.getElementById('initAntagonistLevel').value = 'BOSS级';
    document.getElementById('initVillainMirror').value = '';
    
    document.getElementById('initGoldenFingerType').value = '无金手指';
    document.getElementById('initGoldenFingerName').value = '';
    document.getElementById('initGoldenFingerStyle').value = '辅助型';
    document.getElementById('initGoldenFingerVisibility').value = '隐藏';
    document.getElementById('initGoldenFingerCost').value = '';
    
    document.getElementById('initWorldScale').value = '大陆';
    document.getElementById('initPowerSystemType').value = '无';
    document.getElementById('initFactions').value = '';
    document.getElementById('initSocialClass').value = '';
    document.getElementById('initCurrencySystem').value = '';
    document.getElementById('initCultivationChain').value = '';
    document.getElementById('initSectHierarchy').value = '';
    
    document.getElementById('initAntiTrope').value = '';
    document.getElementById('initConstraints').value = '';
    document.getElementById('initCoreSellingPoints').value = '';
    document.getElementById('initOpeningHook').value = '';
    
}


function closeInitModal() {
    if (initModalLocked) return; // 锁定模式下不允许关闭
    document.getElementById('initModal').style.display = 'none';
}

function updateStepUI() {
    const stepTitles = {
        1: 'Step 1 - 创建剧本',
        2: 'Step 2 - 故事核与商业定位',
        3: 'Step 3 - 角色骨架与关系冲突',
        4: 'Step 4 - 金手指与兑现机制',
        5: 'Step 5 - 世界观与力量规则',
        6: 'Step 6 - 创意约束包',
        7: 'Step 7 - 确认信息'
    };

    document.getElementById('initStepTitle').textContent = stepTitles[currentInitStep];

    for (let i = 1; i <= 7; i++) {
        const stepEl = document.getElementById(`step-${i}`);
        const contentEl = document.getElementById(`step${i}Content`);

        if (i === currentInitStep) {
            stepEl.classList.add('active');
            contentEl.style.display = 'block';
        } else {
            stepEl.classList.remove('active');
            contentEl.style.display = 'none';
        }

        if (i < currentInitStep) {
            stepEl.classList.add('completed');
        } else {
            stepEl.classList.remove('completed');
        }
    }

    // 切到 Step 1 时，回填已有书名/作者/备注（从 Step 2 回退或已有剧本直接回第一步时）
    if (currentInitStep === 1) {
        const existingName = state.scriptData?.name || document.getElementById('initTitle')?.value || '';
        const createNameEl = document.getElementById('initCreateBookName');
        if (createNameEl && existingName) {
            const shouldFill = !createNameEl.value.trim() || createNameEl.dataset.autoFilled === 'true';
            if (shouldFill) {
                createNameEl.value = existingName;
                createNameEl.dataset.autoFilled = 'true';
            }
        }
        // 回填作者和备注
        const authorEl = document.getElementById('initCreateBookAuthor');
        if (authorEl && state.scriptData?.author && !authorEl.value.trim()) {
            authorEl.value = state.scriptData.author;
        }
        const descEl = document.getElementById('initCreateBookDesc');
        if (descEl && state.scriptData?.description && !descEl.value.trim()) {
            descEl.value = state.scriptData.description;
        }
    }

    document.getElementById('initPrevBtn').style.display = currentInitStep > 1 ? 'block' : 'none';

    if (currentInitStep === 7) {
        document.getElementById('initNextBtn').textContent = '确认并初始化';
        generateSummary();
    } else if (currentInitStep === 1) {
        document.getElementById('initNextBtn').textContent = state.scriptId ? '下一步' : '创建并下一步';
    } else {
        document.getElementById('initNextBtn').textContent = '下一步';
    }
}

function goToStep(step) {
    if (step < 1 || step > 7) return;
    if (step > currentInitStep) return;
    currentInitStep = step;
    updateStepUI();
}

function prevStep() {
    if (currentInitStep > 1) {
        currentInitStep--;
        updateStepUI();
    }
}

async function nextStep() {
    if (isSubmitting) return;
    if (!validateStep(currentInitStep)) {
        return;
    }

    isSubmitting = true;
    const btn = document.getElementById('initNextBtn');
    const originalText = btn.textContent;
    btn.textContent = '处理中...';
    btn.disabled = true;
    // 是否在 finally 中恢复按钮文字（步骤成功推进时不恢复，以保留 updateStepUI 设置的新文字）
    let restoreBtnText = true;

    try {
        // Step 1: 创建剧本（无 script_id 时）
        if (currentInitStep === 1 && !state.scriptId) {
            const created = await createScriptFromStep1();
            if (!created) return;
            // 创建成功后加载剧本信息、连接WS，并创建 init session
            await loadScriptInfo();
            connectWebSocket();
            await createInitSession();
            currentInitStep = 2;
            // 创建后用新书名填充 Step 2 的只读书名字段，并同步编辑器顶部标题
            const newBookName = state.scriptData?.name || '';
            const titleEl2 = document.getElementById('initTitle');
            if (titleEl2) titleEl2.value = newBookName;
            if (window.setScriptTitle && newBookName) {
                setScriptTitle(newBookName, { silent: false });
            }
            restoreBtnText = false;
            updateStepUI();
            return;
        }

        // Step 1 已有 script_id 时：检查是否修改了书名/作者/备注，保存后进入 Step 2
        if (currentInitStep === 1 && state.scriptId) {
            const newName = document.getElementById('initCreateBookName')?.value.trim();
            const newAuthor = document.getElementById('initCreateBookAuthor')?.value.trim() || '';
            const newDesc = document.getElementById('initCreateBookDesc')?.value.trim() || '';
            const oldName = state.scriptData?.name || '';
            const oldAuthor = state.scriptData?.author || '';
            const oldDesc = state.scriptData?.description || '';
            const hasChanges = (newName && newName !== oldName) || newAuthor !== oldAuthor || newDesc !== oldDesc;
            if (hasChanges) {
                try {
                    const body = { script_id: state.scriptId, name: newName || oldName };
                    if (newAuthor !== oldAuthor) body.author = newAuthor;
                    if (newDesc !== oldDesc) body.description = newDesc;
                    const data = await apiRequest('/api/books/scripts/rename', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                        errorPrefix: '保存失败'
                    });
                    if (data.success) {
                        if (newName && newName !== oldName && window.setScriptTitle) setScriptTitle(newName);
                        // 同步本地状态
                        if (state.scriptData) {
                            if (newName) state.scriptData.name = newName;
                            state.scriptData.author = newAuthor;
                            state.scriptData.description = newDesc;
                        }
                        showToast('信息已更新', 'success');
                    } else {
                        showToast(data.message || '保存失败', 'error');
                    }
                } catch (e) {
                    console.error('保存信息失败:', e);
                    showToast('保存失败: ' + e.message, 'error');
                }
            }
            // 同步 Step 2 的只读书名字段
            const latestName = state.scriptData?.name || newName || oldName;
            const initTitleEl = document.getElementById('initTitle');
            if (initTitleEl) initTitleEl.value = latestName;
            currentInitStep = 2;
            restoreBtnText = false;
            updateStepUI();
            return;
        }

        saveStepData(currentInitStep);

        if (currentInitStep === 7) {
            await confirmInit();
        } else {
            const result = await saveStepToServer(currentInitStep);
            if (result && result.current_step) {
                currentInitStep = result.current_step;
            } else {
                currentInitStep++;
            }
            restoreBtnText = false;
            updateStepUI();
        }
    } finally {
        isSubmitting = false;
        if (restoreBtnText) {
            btn.textContent = originalText;
        }
        btn.disabled = false;
    }
}

async function createScriptFromStep1() {
    const bookName = document.getElementById('initCreateBookName').value.trim();
    const author = document.getElementById('initCreateBookAuthor').value.trim();
    const desc = document.getElementById('initCreateBookDesc').value.trim();
    if (!bookName) {
        alert('请输入书名');
        return false;
    }
    try {
        // 先创建空书（使用 create-empty 接口，Form 数据）
        const bookForm = new URLSearchParams();
        bookForm.append('title', bookName);
        bookForm.append('author', author || '佚名');
        bookForm.append('description', desc);
        const bookData = await apiRequest('/api/books/library/create-empty', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: bookForm.toString(),
            errorPrefix: '创建书籍失败'
        });
        let bookId;
        if (bookData.success !== false && (bookData.id || bookData.book_id)) {
            bookId = bookData.id || bookData.book_id;
        } else {
            showToast('创建书籍失败: ' + (bookData.detail || bookData.message || '未知错误'), 'error');
            return false;
        }

        // 用 book_id 创建剧本
        const scriptData = await apiRequest('/api/books/scripts/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `book_id=${encodeURIComponent(bookId)}`,
            errorPrefix: '创建剧本失败'
        });
        if (scriptData.success) {
            state.scriptId = scriptData.script_id;
            // 更新URL
            const params = new URLSearchParams(window.location.search);
            params.set('script_id', state.scriptId);
            window.history.replaceState({}, '', window.location.pathname + '?' + params.toString());
            showToast('剧本创建成功', 'success');
            return true;
        } else {
            showToast('创建剧本失败: ' + (scriptData.message || '未知错误'), 'error');
            return false;
        }
    } catch (e) {
        console.error('创建剧本失败:', e);
        showToast('创建剧本失败: ' + e.message, 'error');
        return false;
    }
}

function validateStep(step) {
    switch(step) {
        case 1:
            if (!state.scriptId) {
                if (!document.getElementById('initCreateBookName').value.trim()) {
                    alert('请输入书名');
                    return false;
                }
            }
            break;
        case 2:
            if (!document.getElementById('initTitle').value.trim()) {
                alert('请输入书名');
                return false;
            }
            if (!document.getElementById('initGenre').value.trim()) {
                alert('请选择题材');
                return false;
            }
            if (!document.getElementById('initOneLiner').value.trim()) {
                alert('请输入一句话故事');
                return false;
            }
            if (!document.getElementById('initCoreConflict').value.trim()) {
                alert('请输入核心冲突');
                return false;
            }
            break;
        case 3:
            if (!document.getElementById('initProtagonistName').value.trim()) {
                alert('请输入主角姓名');
                return false;
            }
            if (!document.getElementById('initProtagonistDesire').value.trim()) {
                alert('请输入主角欲望');
                return false;
            }
            if (!document.getElementById('initProtagonistFlaw').value.trim()) {
                alert('请输入主角缺陷');
                return false;
            }
            break;
        case 4:
            if (!document.getElementById('initGoldenFingerCost').value.trim()) {
                alert('请输入金手指不可逆代价（若无金手指，请说明理由）');
                return false;
            }
            break;
        case 5:
            if (!document.getElementById('initWorldScale').value) {
                alert('请选择世界规模');
                return false;
            }
            if (!document.getElementById('initPowerSystemType').value) {
                alert('请选择力量体系类型');
                return false;
            }
            break;
        case 6:
            // 允许不选择方案，直接填写表单也能通过
            if (constraintPackages.length > 0 && selectedPackageIndex < 0) {
                // 有方案但未选择，检查表单是否已填写
                if (!document.getElementById('initAntiTrope').value.trim() &&
                    !document.getElementById('initConstraints').value.trim() &&
                    !document.getElementById('initCoreSellingPoints').value.trim()) {
                    alert('请选择一个创意约束包方案，或手动填写反套路规则、硬性约束和核心卖点');
                    return false;
                }
            } else if (constraintPackages.length === 0) {
                if (!document.getElementById('initAntiTrope').value.trim()) {
                    alert('请输入反套路规则');
                    return false;
                }
                if (!document.getElementById('initConstraints').value.trim()) {
                    alert('请输入硬性约束');
                    return false;
                }
                if (!document.getElementById('initCoreSellingPoints').value.trim()) {
                    alert('请输入核心卖点');
                    return false;
                }
                if (!document.getElementById('initOpeningHook').value.trim()) {
                    alert('请输入开篇钩子');
                    return false;
                }
            }
            break;
    }
    return true;
}

function saveStepData(step) {
    switch(step) {
        case 2:
            initData.project = {
                title: document.getElementById('initTitle').value.trim(),
                genre: document.getElementById('initGenre').value.trim(),
                target_words: parseInt(document.getElementById('initTargetWords').value) || 0,
                target_chapters: parseInt(document.getElementById('initTargetChapters').value) || 0,
                one_liner: document.getElementById('initOneLiner').value.trim(),
                core_conflict: document.getElementById('initCoreConflict').value.trim(),
                target_reader: document.getElementById('initTargetReader').value.trim(),
                platform: document.getElementById('initPlatform').value.trim()
            };
            break;
        case 3:
            initData.protagonist = {
                name: document.getElementById('initProtagonistName').value.trim(),
                archetype: document.getElementById('initProtagonistArchetype').value.trim(),
                desire: document.getElementById('initProtagonistDesire').value.trim(),
                flaw: document.getElementById('initProtagonistFlaw').value.trim(),
                structure: document.getElementById('initProtagonistStructure').value
            };
            initData.relationship = {
                heroine_config: document.getElementById('initHeroineConfig').value,
                antagonist_level: document.getElementById('initAntagonistLevel').value,
                antagonist_mirror: document.getElementById('initVillainMirror').value.trim()
            };
            break;
        case 4:
            initData.golden_finger = {
                type: document.getElementById('initGoldenFingerType').value,
                name: document.getElementById('initGoldenFingerName').value.trim(),
                style: document.getElementById('initGoldenFingerStyle').value,
                visibility: document.getElementById('initGoldenFingerVisibility').value,
                irreversible_cost: document.getElementById('initGoldenFingerCost').value.trim()
            };
            break;
        case 5:
            initData.world = {
                scale: document.getElementById('initWorldScale').value,
                power_system_type: document.getElementById('initPowerSystemType').value,
                factions: document.getElementById('initFactions').value.trim(),
                social_class: document.getElementById('initSocialClass').value.trim(),
                currency_system: document.getElementById('initCurrencySystem').value.trim(),
                cultivation_chain: document.getElementById('initCultivationChain').value.trim(),
                sect_hierarchy: document.getElementById('initSectHierarchy').value.trim()
            };
            break;
        case 6: {
            // 表单为最终数据源（选择方案后已回填到表单，用户可继续微调）
            const hardText = document.getElementById('initConstraints').value.trim();
            let hardConstraints = hardText;
            if (constraintPackages.length > 0 && selectedPackageIndex >= 0) {
                // 未修改时保持方案的数组格式，避免提交时丢失结构化数据
                const pkgHard = constraintPackages[selectedPackageIndex].hard_constraints;
                if (Array.isArray(pkgHard) && hardText === pkgHard.join('\n')) {
                    hardConstraints = pkgHard;
                } else if (hardText) {
                    hardConstraints = hardText.split('\n').map(s => s.trim()).filter(Boolean);
                }
            }
            initData.constraints = {
                anti_trope: document.getElementById('initAntiTrope').value.trim(),
                hard_constraints: hardConstraints,
                core_selling_points: document.getElementById('initCoreSellingPoints').value.trim(),
                opening_hook: document.getElementById('initOpeningHook').value.trim()
            };
            break;
        }
    }
}

async function saveStepToServer(step) {
    try {
        const data = {
            script_id: state.scriptId,
            step: step,
            data: initData[getStepKey(step)] || {}
        };
        if (step === 3 && initData.relationship) {
            data.data = { ...data.data, relationship: initData.relationship };
        }
        const result = await apiRequest(`/api/books/scripts/webnovel/init/step/${step}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            errorPrefix: '保存失败'
        });
        if (!result.success) {
            showToast('保存失败: ' + (result.detail || result.message || '未知错误'), 'error');
            throw new Error(result.detail || result.message);
        }
        return result;
    } catch (e) {
        console.error('保存步骤数据失败:', e);
        throw e;
    }
}

function getStepKey(step) {
    const keys = {
        2: 'project',
        3: 'protagonist',
        4: 'golden_finger',
        5: 'world',
        6: 'constraints'
    };
    return keys[step];
}

// ── AI 占位区域状态管理 ──

/** 显示 AI 占位卡片（未生成状态） */
function showAiPlaceholder(step) {
    const zone = document.getElementById(`step${step}AiZone`);
    if (!zone) return;
    const placeholder = document.getElementById(`step${step}AiPlaceholder`);
    const loading = document.getElementById(`step${step}AiLoading`);
    const result = document.getElementById(`step${step}AiResult`);
    if (placeholder) placeholder.style.display = 'flex';
    if (loading) loading.style.display = 'none';
    if (result) result.style.display = 'none';
    // 隐藏选项容器
    if (step <= 5) {
        const optC = document.getElementById(`step${step}OptionsContainer`);
        if (optC) optC.style.display = 'none';
    }
    if (step === 6) {
        const pkgC = document.getElementById('constraintPackagesContainer');
        if (pkgC) pkgC.style.display = 'none';
    }
}

/** 显示 AI 加载状态 */
function showAiLoading(step) {
    const zone = document.getElementById(`step${step}AiZone`);
    if (!zone) return;
    const placeholder = document.getElementById(`step${step}AiPlaceholder`);
    const loading = document.getElementById(`step${step}AiLoading`);
    const result = document.getElementById(`step${step}AiResult`);
    if (placeholder) placeholder.style.display = 'none';
    if (loading) loading.style.display = 'flex';
    if (result) result.style.display = 'none';
}

/** 显示 AI 生成结果区域 */
function showAiResult(step) {
    const zone = document.getElementById(`step${step}AiZone`);
    if (!zone) return;
    const placeholder = document.getElementById(`step${step}AiPlaceholder`);
    const loading = document.getElementById(`step${step}AiLoading`);
    const result = document.getElementById(`step${step}AiResult`);
    if (placeholder) placeholder.style.display = 'none';
    if (loading) loading.style.display = 'none';
    if (result) result.style.display = 'block';
}

/** 重新生成：重置当前步骤选项并重新调用 AI */
function regenerateAiData() {
    const step = currentInitStep;
    // 清除当前步骤的选项数据
    if (step >= 2 && step <= 5) {
        stepOptions[step] = [];
        stepSelectedIndex[step] = -1;
    }
    if (step === 6) {
        constraintPackages = [];
        selectedPackageIndex = -1;
    }
    generateAiData();
}

async function generateAiData() {
    const step = currentInitStep;
    showAiLoading(step);
    
    try {
        saveStepData(step);
        
        const currentStepData = {};
        if (initData.project) currentStepData.project = initData.project;
        if (initData.protagonist) currentStepData.protagonist = initData.protagonist;
        if (initData.relationship) currentStepData.relationship = initData.relationship;
        if (initData.golden_finger) currentStepData.golden_finger = initData.golden_finger;
        if (initData.world) currentStepData.world = initData.world;
        if (initData.constraints) currentStepData.constraints = initData.constraints;
        
        const data = await apiRequest(`/api/books/scripts/webnovel/init/ai/generate/${step}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script_id: state.scriptId,
                step: step,
                current_data: currentStepData
            }),
            errorPrefix: 'AI生成失败'
        });
        if (data.success && data.data) {
            showAiResult(step);
            if (data.is_multi_options && data.data.options) {
                // 多选项模式：渲染选项卡片
                stepOptions[step] = data.data.options;
                stepSelectedIndex[step] = -1;
                renderStepOptions(step, data.data.options);
            } else if (data.is_packages) {
                // 约束包模式
                constraintPackages = data.data.constraint_packages || [];
                selectedPackageIndex = -1;
                renderConstraintPackages();
            } else {
                fillStepData(step, data.data, false);
            }
        } else {
            showAiPlaceholder(step);
            showToast('AI生成失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('AI生成失败:', e);
        showAiPlaceholder(step);
        showToast('AI生成失败: ' + e.message, 'error');
    }
}

let constraintPackages = [];
let selectedPackageIndex = -1;

// ── 步骤 2-5 多选项状态 ──
let stepOptions = { 2: [], 3: [], 4: [], 5: [] };
let stepSelectedIndex = { 2: -1, 3: -1, 4: -1, 5: -1 };

/** 各步骤选项卡片展示的字段定义（详情浮层用） */
const STEP_OPTION_FIELDS = {
    2: [
        { key: 'genre', label: '题材' },
        { key: 'one_liner', label: '一句话故事' },
        { key: 'core_conflict', label: '核心冲突' },
        { key: 'target_reader', label: '目标读者' },
        { key: 'platform', label: '目标平台' },
        { key: 'target_words', label: '目标字数', numeric: true },
        { key: 'target_chapters', label: '目标章节', numeric: true }
    ],
    3: [
        { key: 'name', label: '主角姓名' },
        { key: 'archetype', label: '主角原型' },
        { key: 'desire', label: '主角欲望' },
        { key: 'flaw', label: '主角缺陷' },
        { key: 'villain_mirror', label: '反派镜像' },
        { key: 'heroine_config', label: '感情线' },
        { key: 'antagonist_level', label: '反派分层' }
    ],
    4: [
        { key: 'type', label: '类型' },
        { key: 'name', label: '名称' },
        { key: 'style', label: '风格' },
        { key: 'visibility', label: '可见度' },
        { key: 'irreversible_cost', label: '不可逆代价' },
        { key: 'growth_rhythm', label: '成长节奏' }
    ],
    5: [
        { key: 'scale', label: '世界规模' },
        { key: 'power_system_type', label: '力量体系' },
        { key: 'factions', label: '势力格局' },
        { key: 'social_class', label: '社会阶层' },
        { key: 'currency_system', label: '货币体系' },
        { key: 'cultivation_chain', label: '境界链' },
        { key: 'sect_hierarchy', label: '宗门层级' }
    ]
};

/** 各步骤摘要行显示的主字段 */
const STEP_OPTION_SUMMARY_FIELD = {
    2: opt => [opt.genre, opt.one_liner].filter(Boolean).join(' · '),
    3: opt => [opt.name, opt.archetype].filter(Boolean).join(' · '),
    4: opt => [opt.type, opt.name].filter(Boolean).join(' · '),
    5: opt => [opt.scale, opt.power_system_type].filter(Boolean).join(' · ')
};

/** 浮层当前待确认的选项 { step, index } */
let _pendingOptionSelect = null;

/** 计算选项总分 */
function _calcTotalScore(scoring) {
    return Object.values(scoring || {}).reduce((sum, s) => sum + (typeof s === 'object' ? (s.score || 0) : 0), 0);
}

/** 渲染步骤 2-5 的紧凑摘要行 */
function renderStepOptions(step, options) {
    const container = document.getElementById(`step${step}OptionsContainer`);
    const list = document.getElementById(`step${step}OptionsList`);
    if (!container || !list) return;

    if (!options || options.length === 0) {
        container.style.display = 'none';
        return;
    }

    stepOptions[step] = options;
    container.style.display = 'block';
    const summaryFn = STEP_OPTION_SUMMARY_FIELD[step] || (() => '');

    let html = `<div class="option-summary-list">`;
    html += options.map((opt, index) => {
        const totalScore = _calcTotalScore(opt.scoring);
        const isSelected = stepSelectedIndex[step] === index;
        const summaryText = escapeHtml(summaryFn(opt));
        const optName = escapeHtml(opt.option_name || `方案${String.fromCharCode(65 + index)}`);

        return `<div class="option-summary-row ${isSelected ? 'selected' : ''}" onclick="quickSelectOption(${step}, ${index})">
            <span class="summary-check"><i class="fas ${isSelected ? 'fa-check-circle' : 'fa-circle'}"></i></span>
            <span class="summary-name">${optName}</span>
            <span class="summary-text">${summaryText}</span>
            <span class="summary-score"><span class="score-num">${totalScore}</span>分</span>
            <button class="summary-detail-btn" onclick="event.stopPropagation(); showOptionDetail(${step}, ${index})" title="查看详情"><i class="fas fa-eye"></i></button>
        </div>`;
    }).join('');
    html += `</div>`;
    html += `<div class="option-hint"><span><i class="fas fa-wand-magic-sparkles"></i> 已为你智能生成 ${options.length} 套备选方案，点击即可选用，也可继续手动编辑</span><button class="btn-regenerate" onclick="regenerateAiData()"><i class="fas fa-rotate"></i> 重新生成</button></div>`;
    list.innerHTML = html;
}

/** 打开选项详情浮层 */
function showOptionDetail(step, index) {
    const opt = stepOptions[step]?.[index];
    if (!opt) return;

    _pendingOptionSelect = { step, index };

    const overlay = document.getElementById('optionDetailOverlay');
    const titleEl = document.getElementById('optionDetailTitle');
    const scoreEl = document.getElementById('optionDetailScore');
    const contentEl = document.getElementById('optionDetailContent');
    const selectBtn = document.getElementById('optionDetailSelectBtn');

    const totalScore = _calcTotalScore(opt.scoring);
    const fields = STEP_OPTION_FIELDS[step] || [];
    const isSelected = stepSelectedIndex[step] === index;

    titleEl.textContent = opt.option_name || `方案${String.fromCharCode(65 + index)}`;
    scoreEl.innerHTML = `<span>${totalScore}</span><span style="font-size:10px;opacity:0.8">分</span>`;

    // 构建详情内容
    let fieldsHtml = fields.map(f => {
        const val = opt[f.key];
        if (val === undefined || val === null || val === '') return '';
        return `<div class="constraint-package-item"><strong>${f.label}：</strong>${f.numeric ? val : escapeHtml(String(val))}</div>`;
    }).filter(Boolean).join('');

    let scoringHtml = '';
    const scoring = opt.scoring || {};
    if (Object.keys(scoring).length > 0) {
        const labels = { creativity: '创意独特性', feasibility: '落地可行性', market_appeal: '市场吸引力', sustainability: '长线可持续性', emotional_impact: '情感冲击力' };
        scoringHtml = `<div class="constraint-package-scoring">` + Object.entries(scoring).map(([key, s]) => {
            if (typeof s !== 'object') return '';
            return `<div class="scoring-row">
                <span class="scoring-label">${labels[key] || key}</span>
                <div class="scoring-bar"><div class="scoring-fill" style="width: ${(s.score || 0) * 10}%"></div></div>
                <span class="scoring-value">${s.score || 0}/10</span>
                <span class="scoring-reason">${escapeHtml(s.reason || '')}</span>
            </div>`;
        }).filter(Boolean).join('') + `</div>`;
    }

    contentEl.innerHTML = fieldsHtml + scoringHtml;
    selectBtn.textContent = isSelected ? '已选择（点击更新）' : '选择此方案';

    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

/** 关闭选项详情浮层 */
function closeOptionDetail() {
    const overlay = document.getElementById('optionDetailOverlay');
    if (overlay) overlay.style.display = 'none';
    document.body.style.overflow = '';
    _pendingOptionSelect = null;
}

/** 浮层内“选择此方案”按钮确认 */
function confirmOptionSelect() {
    if (!_pendingOptionSelect) return;
    const { step, index } = _pendingOptionSelect;
    closeOptionDetail();
    if (step === 6) {
        selectConstraintPackage(index);
    } else {
        selectStepOption(step, index);
    }
}

/** ESC 关闭浮层 */
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const overlay = document.getElementById('optionDetailOverlay');
        if (overlay && overlay.style.display === 'flex') {
            closeOptionDetail();
        }
    }
});

/** 摘要行点击 → 自动选择方案（不打开浮层） */
function quickSelectOption(step, index) {
    if (step === 6) {
        selectConstraintPackage(index);
    } else {
        selectStepOption(step, index);
    }
}

/** 选择步骤 2-5 的某个选项，填充表单 */
function selectStepOption(step, index) {
    stepSelectedIndex[step] = index;
    renderStepOptions(step, stepOptions[step]);

    const opt = stepOptions[step][index];
    if (!opt) return;

    // 各步骤字段 → 表单元素 ID 映射
    const fieldMap = {
        2: { genre: 'initGenre', one_liner: 'initOneLiner', core_conflict: 'initCoreConflict', target_words: 'initTargetWords', target_chapters: 'initTargetChapters', target_reader: 'initTargetReader', platform: 'initPlatform' },
        3: { name: 'initProtagonistName', archetype: 'initProtagonistArchetype', desire: 'initProtagonistDesire', flaw: 'initProtagonistFlaw', structure: 'initProtagonistStructure', villain_mirror: 'initVillainMirror', heroine_config: 'initHeroineConfig', antagonist_level: 'initAntagonistLevel' },
        4: { type: 'initGoldenFingerType', name: 'initGoldenFingerName', style: 'initGoldenFingerStyle', visibility: 'initGoldenFingerVisibility', irreversible_cost: 'initGoldenFingerCost' },
        5: { scale: 'initWorldScale', power_system_type: 'initPowerSystemType', factions: 'initFactions', social_class: 'initSocialClass', currency_system: 'initCurrencySystem', cultivation_chain: 'initCultivationChain', sect_hierarchy: 'initSectHierarchy' }
    };

    const map = fieldMap[step] || {};
    for (const [key, elId] of Object.entries(map)) {
        const el = document.getElementById(elId);
        if (!el || opt[key] === undefined || opt[key] === null) continue;
        const val = String(opt[key]);
        if (el.tagName === 'SELECT') {
            setSelectValue(el, val);
        } else {
            el.value = val;
        }
    }

    // 同步到 initData
    saveStepData(step);

    // 保存到后端
    try {
        apiRequest('/api/books/scripts/webnovel/init/select-option', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_id: state.scriptId, step: step, option_index: index }),
            silent: true
        });
    } catch (e) {
        console.warn('保存选项选择失败:', e);
    }
}

/** 安全设置 select 元素值 */
function setSelectValue(el, val) {
    const opts = Array.from(el.options).map(o => o.value);
    if (opts.includes(val)) {
        el.value = val;
    } else {
        // 模糊匹配
        for (const opt of opts) {
            if (val.includes(opt) || opt.includes(val)) {
                el.value = opt;
                return;
            }
        }
    }
}

/** HTML 转义 */
function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fillStepData(step, data, isPackages = false) {
    switch(step) {
        case 2:
            if (data.genre) {
                const genreSelect = document.getElementById('initGenre');
                const genreOptions = Array.from(genreSelect.options).map(o => o.value);
                if (genreOptions.includes(data.genre)) {
                    genreSelect.value = data.genre;
                } else {
                    for (const opt of genreOptions) {
                        if (data.genre.includes(opt) || opt.includes(data.genre)) {
                            genreSelect.value = opt;
                            break;
                        }
                    }
                }
            }
            if (data.one_liner) document.getElementById('initOneLiner').value = data.one_liner;
            if (data.core_conflict) document.getElementById('initCoreConflict').value = data.core_conflict;
            if (data.target_words) document.getElementById('initTargetWords').value = data.target_words;
            if (data.target_chapters) document.getElementById('initTargetChapters').value = data.target_chapters;
            if (data.target_reader) document.getElementById('initTargetReader').value = data.target_reader;
            if (data.platform) document.getElementById('initPlatform').value = data.platform;
            break;
        case 3:
            if (data.name) document.getElementById('initProtagonistName').value = data.name;
            if (data.desire) document.getElementById('initProtagonistDesire').value = data.desire;
            if (data.flaw) document.getElementById('initProtagonistFlaw').value = data.flaw;
            if (data.archetype) document.getElementById('initProtagonistArchetype').value = data.archetype;
            if (data.structure) document.getElementById('initProtagonistStructure').value = data.structure;
            if (data.villain_mirror) document.getElementById('initVillainMirror').value = data.villain_mirror;
            break;
        case 4:
            if (data.type) document.getElementById('initGoldenFingerType').value = data.type;
            if (data.name) document.getElementById('initGoldenFingerName').value = data.name;
            if (data.style) document.getElementById('initGoldenFingerStyle').value = data.style;
            if (data.visibility) document.getElementById('initGoldenFingerVisibility').value = data.visibility;
            if (data.irreversible_cost) document.getElementById('initGoldenFingerCost').value = data.irreversible_cost;
            break;
        case 5:
            if (data.scale) {
                const scaleSelect = document.getElementById('initWorldScale');
                const scaleOptions = Array.from(scaleSelect.options).map(o => o.value);
                scaleSelect.value = scaleOptions.includes(data.scale) ? data.scale : (data.scale.includes('城') ? '单城' : (data.scale.includes('陆') ? '大陆' : (data.scale.includes('界') ? '多界' : '大陆')));
            }
            if (data.power_system_type) {
                const powerSelect = document.getElementById('initPowerSystemType');
                const powerOptions = Array.from(powerSelect.options).map(o => o.value);
                let powerValue = data.power_system_type;
                if (!powerOptions.includes(powerValue)) {
                    for (const opt of powerOptions) {
                        if (data.power_system_type.includes(opt)) {
                            powerValue = opt;
                            break;
                        }
                    }
                }
                powerSelect.value = powerOptions.includes(powerValue) ? powerValue : '修仙';
            }
            if (data.factions) document.getElementById('initFactions').value = data.factions;
            if (data.social_class) document.getElementById('initSocialClass').value = data.social_class;
            if (data.currency_system) document.getElementById('initCurrencySystem').value = data.currency_system;
            if (data.cultivation_chain) document.getElementById('initCultivationChain').value = data.cultivation_chain;
            if (data.sect_hierarchy) document.getElementById('initSectHierarchy').value = data.sect_hierarchy;
            break;
        case 6:
            if (isPackages) {
                constraintPackages = data.constraint_packages || [];
                renderConstraintPackages();
            } else {
                if (data.anti_trope) document.getElementById('initAntiTrope').value = data.anti_trope;
                if (data.hard_constraints) document.getElementById('initConstraints').value = Array.isArray(data.hard_constraints) ? data.hard_constraints.join('\n') : data.hard_constraints;
                if (data.core_selling_points) document.getElementById('initCoreSellingPoints').value = data.core_selling_points;
                if (data.opening_hook) document.getElementById('initOpeningHook').value = data.opening_hook;
            }
            break;
    }
}

function renderConstraintPackages() {
    const container = document.getElementById('constraintPackagesContainer');
    const manualInput = document.getElementById('constraintManualInput');
    const list = document.getElementById('constraintPackagesList');
    
    if (constraintPackages.length === 0) {
        container.style.display = 'none';
        manualInput.style.display = 'block';
        return;
    }
    
    container.style.display = 'block';
    manualInput.style.display = 'block';
    
    let html = `<div class="option-summary-list">` + constraintPackages.map((pkg, index) => {
        const isSelected = selectedPackageIndex === index;
        const summaryText = (pkg.core_selling_points || pkg.anti_trope_rule || '').slice(0, 40);
        const optName = escapeHtml(`方案${String.fromCharCode(65 + index)}`);
        const totalScore = _calcTotalScore(pkg.scoring);

        return `<div class="option-summary-row ${isSelected ? 'selected' : ''}" onclick="quickSelectOption(6, ${index})">
            <span class="summary-check"><i class="fas ${isSelected ? 'fa-check-circle' : 'fa-circle'}"></i></span>
            <span class="summary-name">${optName}</span>
            <span class="summary-text">${escapeHtml(summaryText)}${summaryText.length >= 40 ? '...' : ''}</span>
            <span class="summary-score"><span class="score-num">${totalScore}</span>分</span>
            <button class="summary-detail-btn" onclick="event.stopPropagation(); showPackageDetail(${index})" title="查看详情"><i class="fas fa-eye"></i></button>
        </div>`;
    }).join('') + `</div>`;
    html += `<div class="option-hint"><span><i class="fas fa-wand-magic-sparkles"></i> 已为你智能生成 ${constraintPackages.length} 套约束包方案，点击即可选用，也可在下方手动编辑</span><button class="btn-regenerate" onclick="regenerateAiData()"><i class="fas fa-rotate"></i> 重新生成</button></div>`;
    list.innerHTML = html;
}

/** 打开步骤6约束包详情浮层 */
function showPackageDetail(index) {
    const pkg = constraintPackages[index];
    if (!pkg) return;

    _pendingOptionSelect = { step: 6, index };

    const overlay = document.getElementById('optionDetailOverlay');
    const titleEl = document.getElementById('optionDetailTitle');
    const scoreEl = document.getElementById('optionDetailScore');
    const contentEl = document.getElementById('optionDetailContent');
    const selectBtn = document.getElementById('optionDetailSelectBtn');

    const isSelected = selectedPackageIndex === index;
    const hardConstraints = Array.isArray(pkg.hard_constraints) ? pkg.hard_constraints : [];

    titleEl.textContent = `方案${String.fromCharCode(65 + index)}`;
    const totalScore = _calcTotalScore(pkg.scoring);
    scoreEl.innerHTML = `<span>${totalScore}</span><span style="font-size:10px;opacity:0.8">分</span>`;

    let html = '';
    html += `<div class="constraint-package-item"><strong>反套路规则：</strong>${escapeHtml(pkg.anti_trope_rule || '')}</div>`;
    if (hardConstraints.length) {
        html += `<div class="constraint-package-item"><strong>硬性约束：</strong><ul>${hardConstraints.map(c => `<li>${escapeHtml(c)}</li>`).join('')}</ul></div>`;
    }
    html += `<div class="constraint-package-item"><strong>核心卖点：</strong>${escapeHtml(pkg.core_selling_points || '')}</div>`;
    html += `<div class="constraint-package-item"><strong>开篇钩子：</strong>${escapeHtml(pkg.opening_hook || '')}</div>`;

    // 五维评分展示
    let scoringHtml = '';
    const scoring = pkg.scoring || {};
    if (Object.keys(scoring).length > 0) {
        const labels = { creativity: '创意独特性', feasibility: '落地可行性', market_appeal: '市场吸引力', sustainability: '长线可持续性', emotional_impact: '情感冲击力' };
        scoringHtml = `<div class="constraint-package-scoring">` + Object.entries(scoring).map(([key, s]) => {
            if (typeof s !== 'object') return '';
            return `<div class="scoring-row">
                <span class="scoring-label">${labels[key] || key}</span>
                <div class="scoring-bar"><div class="scoring-fill" style="width: ${(s.score || 0) * 10}%"></div></div>
                <span class="scoring-value">${s.score || 0}/10</span>
                <span class="scoring-reason">${escapeHtml(s.reason || '')}</span>
            </div>`;
        }).filter(Boolean).join('') + `</div>`;
    }

    contentEl.innerHTML = html + scoringHtml;
    selectBtn.textContent = isSelected ? '已选择（点击更新）' : '选择此方案';

    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function selectConstraintPackage(index) {
    selectedPackageIndex = index;
    renderConstraintPackages();
    
    const pkg = constraintPackages[index];
    initData.constraints = {
        anti_trope: pkg.anti_trope_rule || '',
        hard_constraints: pkg.hard_constraints || [],
        core_selling_points: pkg.core_selling_points || '',
        opening_hook: pkg.opening_hook || ''
    };

    // 将所选方案回填到表单输入框，与步骤 2-5 的选择行为保持一致
    document.getElementById('initAntiTrope').value = pkg.anti_trope_rule || '';
    document.getElementById('initConstraints').value = Array.isArray(pkg.hard_constraints)
        ? pkg.hard_constraints.join('\n')
        : (pkg.hard_constraints || '');
    document.getElementById('initCoreSellingPoints').value = pkg.core_selling_points || '';
    document.getElementById('initOpeningHook').value = pkg.opening_hook || '';
}

async function selectConstraintPackageAndSave(index) {
    selectConstraintPackage(index);
    
    try {
        const data = await apiRequest('/api/books/scripts/webnovel/init/select-package', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script_id: state.scriptId,
                package_index: index
            }),
            errorPrefix: '保存方案失败'
        });
        if (!data.success) {
            showToast('保存方案失败: ' + (data.detail || data.message || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('保存方案失败:', e);
    }
}

function generateSummary() {
    let html = '';
    
    if (initData.project) {
        html += '<h4>📖 故事核与商业定位</h4>';
        html += `<p><strong>书名：</strong>${initData.project.title || '未填写'}</p>`;
        html += `<p><strong>题材：</strong>${initData.project.genre || '未填写'}</p>`;
        html += `<p><strong>一句话故事：</strong>${initData.project.one_liner || '未填写'}</p>`;
        html += `<p><strong>核心冲突：</strong>${initData.project.core_conflict || '未填写'}</p>`;
        html += `<p><strong>目标字数/章节：</strong>${initData.project.target_words || 0}字 / ${initData.project.target_chapters || 0}章</p>`;
        html += `<p><strong>目标读者：</strong>${initData.project.target_reader || '未填写'}</p>`;
        html += `<p><strong>目标平台：</strong>${initData.project.platform || '未填写'}</p>`;
    }
    
    if (initData.protagonist) {
        html += '<h4>👤 主角设定</h4>';
        html += `<p><strong>姓名：</strong>${initData.protagonist.name || '未填写'}</p>`;
        html += `<p><strong>原型：</strong>${initData.protagonist.archetype || '未填写'}</p>`;
        html += `<p><strong>欲望：</strong>${initData.protagonist.desire || '未填写'}</p>`;
        html += `<p><strong>缺陷：</strong>${initData.protagonist.flaw || '未填写'}</p>`;
        html += `<p><strong>结构：</strong>${initData.protagonist.structure || '未填写'}</p>`;
    }
    
    if (initData.relationship) {
        html += '<h4>❤️ 关系与反派</h4>';
        html += `<p><strong>感情线：</strong>${initData.relationship.heroine_config || '未填写'}</p>`;
        html += `<p><strong>反派分层：</strong>${initData.relationship.antagonist_level || '未填写'}</p>`;
        html += `<p><strong>反派镜像：</strong>${initData.relationship.antagonist_mirror || '未填写'}</p>`;
    }
    
    if (initData.golden_finger) {
        html += '<h4>⭐ 金手指</h4>';
        html += `<p><strong>类型：</strong>${initData.golden_finger.type || '未填写'}</p>`;
        html += `<p><strong>名称：</strong>${initData.golden_finger.name || '未填写'}</p>`;
        html += `<p><strong>不可逆代价：</strong>${initData.golden_finger.irreversible_cost || '未填写'}</p>`;
    }
    
    if (initData.world) {
        html += '<h4>🌍 世界观</h4>';
        html += `<p><strong>世界规模：</strong>${initData.world.scale || '未填写'}</p>`;
        html += `<p><strong>力量体系：</strong>${initData.world.power_system_type || '未填写'}</p>`;
        html += `<p><strong>势力格局：</strong>${initData.world.factions || '未填写'}</p>`;
    }
    
    if (initData.constraints) {
        html += '<h4>🔒 创意约束</h4>';
        html += `<p><strong>反套路规则：</strong>${initData.constraints.anti_trope || '未填写'}</p>`;
        html += `<p><strong>硬性约束：</strong>${initData.constraints.hard_constraints || '未填写'}</p>`;
        html += `<p><strong>核心卖点：</strong>${initData.constraints.core_selling_points || '未填写'}</p>`;
        html += `<p><strong>开篇钩子：</strong>${initData.constraints.opening_hook || '未填写'}</p>`;
    }
    
    document.getElementById('initSummaryContent').innerHTML = html;
}

async function confirmInit() {
    // 二次确认：防止误操作，基于 dashboard 接口的 initialized 标志判断是否为重新初始化
    const isReinit = !!state.webnovelInitialized;
    const confirmMsg = isReinit
        ? '该项目已完成初始化，重新初始化将覆盖所有现有设定数据（角色、世界观、章节等），确定要继续吗？'
        : '确认提交所有设定并启动深度初始化？';
    if (!confirm(confirmMsg)) return;

    document.getElementById('initNextBtn').style.display = 'none';
    document.getElementById('initPrevBtn').style.display = 'none';
    document.getElementById('initCancelBtn').style.display = 'block';

    try {
        const data = await apiRequest('/api/books/scripts/webnovel/init/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_id: state.scriptId }),
            errorPrefix: '初始化失败'
        });
        if (data.success) {
            // 初始化已启动，解锁模态框并关闭（后续由任务遮罩接管）
            initModalLocked = false;
            updateInitModalLock();
            closeInitModal();
            showInitTaskMask('准备中...');
            if (state.scriptData) state.scriptData.status = 'initializing';
            updateStatusBadge('initializing');
            // 重新启动初始化时恢复WS重连标志，并确保WS已连接以接收进度
            state.wsShouldReconnect = true;
            if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
                if (typeof connectWebSocket === 'function') connectWebSocket();
            }
        } else {
            showToast('初始化启动失败: ' + (data.message || data.detail || '未知错误'), 'error');
            resetInitButtons();
        }
    } catch (e) {
        console.error('确认初始化失败:', e);
        showToast('确认初始化失败: ' + e.message, 'error');
        resetInitButtons();
    }
}

function showInitTaskMask(message) {
    const mask = document.getElementById('initTaskMask');
    const current = document.getElementById('initTaskCurrent');
    if (mask) mask.style.display = 'flex';
    if (current) current.textContent = message || '准备中...';
}

function hideInitTaskMask() {
    const mask = document.getElementById('initTaskMask');
    if (mask) mask.style.display = 'none';
}

function appendInitTaskLog(message, status) {
    const log = document.getElementById('initTaskLog');
    if (!log) return;
    // 只显示最新的一条：每次清空后写入，保证刷新前后显示一致
    log.innerHTML = '';
    const item = document.createElement('div');
    item.style.cssText = 'padding:4px 0; font-size:13px; line-height:1.6;';
    const color = status === 'failed' ? '#dc3545' : status === 'completed' ? '#28a745' : 'var(--neu-text, #333)';
    item.innerHTML = `<span style="color:${color};">●</span> <span>${message}</span>`;
    log.appendChild(item);
}

function handleInitProgressMessage(msg) {
    const status = msg.status;
    const step = msg.step;
    const message = msg.message;
    const progress = msg.progress || 0;

    showInitTaskMask(message);

    // 更新进度条
    const barEl = document.getElementById('initTaskProgressBar');
    const fillEl = document.getElementById('initTaskProgressFill');
    const textEl = document.getElementById('initTaskProgressText');
    if (barEl) barEl.style.display = 'block';
    if (fillEl) fillEl.style.width = `${progress}%`;
    if (textEl) {
        textEl.style.display = 'block';
        textEl.textContent = `${progress}%`;
    }

    appendInitTaskLog(message, status);

    if (status === 'completed') {
        state.webnovelInitialized = true;
        appendInitTaskLog('深度初始化完成，正在刷新数据...', 'completed');
        setTimeout(async () => {
            hideInitTaskMask();
            await loadScriptInfo();
            await loadCharacters();
            renderChapterList();
            showToast('深度初始化完成！', 'success');
            // 初始化完成后自动打开项目信息模态框
            if (typeof showWorldModal === 'function') showWorldModal();
        }, 1500);
    } else if (status === 'failed') {
        const btn = document.getElementById('initInterruptBtn');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-times"></i> 关闭';
            btn.onclick = () => {
                hideInitTaskMask();
                if (state.scriptData) state.scriptData.status = 'failed';
                updateStatusBadge('failed');
                btn.innerHTML = '<i class="fas fa-stop"></i> 中断初始化';
                btn.onclick = interruptInitTask;
            };
        }
        showToast('深度初始化失败: ' + message, 'error');
    } else if (status === 'interrupted') {
        const btn = document.getElementById('initInterruptBtn');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-times"></i> 关闭';
            btn.onclick = () => {
                hideInitTaskMask();
                if (state.scriptData) state.scriptData.status = 'failed';
                updateStatusBadge('failed');
                btn.innerHTML = '<i class="fas fa-stop"></i> 中断初始化';
                btn.onclick = interruptInitTask;
            };
        }
        showToast('初始化已中断', 'warning');
    }
    // 初始化失败/中断后，任务已永久结束：停止WS重连，避免重连后后端推送failed状态造成循环
    if (status === 'failed' || status === 'interrupted') {
        if (typeof state !== 'undefined' && 'wsShouldReconnect' in state) {
            state.wsShouldReconnect = false;
            if (state.wsReconnectTimer) {
                clearTimeout(state.wsReconnectTimer);
                state.wsReconnectTimer = null;
            }
        }
        // 终态停止轮询
        if (typeof stopInitStatusPolling === 'function') stopInitStatusPolling();
    }
    if (status === 'completed') {
        // 完成态也停止轮询
        if (typeof stopInitStatusPolling === 'function') stopInitStatusPolling();
    }
}

async function interruptInitTask() {
    if (!confirm('确定要中断初始化任务吗？中断后剧本状态将标记为失败。')) return;
    try {
        const data = await apiRequest('/api/books/scripts/webnovel/init/interrupt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_id: state.scriptId }),
            errorPrefix: '中断失败'
        });
        if (data.success) {
            showToast('中断请求已发送', 'info');
        } else {
            showToast('中断失败: ' + (data.detail || data.message || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('中断初始化失败:', e);
        showToast('中断初始化失败: ' + e.message, 'error');
    }
}

function resetInitButtons() {
    document.getElementById('initProgressContainer').style.display = 'none';
    document.getElementById('initNextBtn').style.display = 'block';
    document.getElementById('initPrevBtn').style.display = currentInitStep > 1 ? 'block' : 'none';
    document.getElementById('initCancelBtn').style.display = 'none';
}

async function cancelInit() {
    if (confirm('确定要取消初始化吗？')) {
        try {
            await apiRequest(`/api/books/scripts/webnovel/init/cancel?script_id=${state.scriptId}`, {
                method: 'POST',
                silent: true
            });
        } catch (e) {
            console.error('取消初始化失败:', e);
        }
        closeInitModal();
    }
}

async function pollInitStatus(taskId) {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/init/status?script_id=${state.scriptId}&task_id=${taskId}`, { silent: true });
        if (data.success && data.task) {
            const task = data.task;
            updateInitProgress(task.progress || 0, task.progress_message || '处理中...');
            
            if (task.status === 'completed') {
                const statusEl = document.getElementById('initTaskStatus');
                statusEl.className = 'continue-task-status completed';
                statusEl.innerHTML = '<strong>初始化完成！</strong><br>项目基础数据已创建成功。';
            } else if (task.status === 'failed') {
                const statusEl = document.getElementById('initTaskStatus');
                statusEl.className = 'continue-task-status failed';
                statusEl.innerHTML = `<strong>任务失败</strong><br>${task.error_message || '未知错误'}`;
                setTimeout(() => resetInitModal(), 2000);
                return;
            } else if (task.status === 'running') {
                setTimeout(() => pollInitStatus(taskId), 2000);
            }
        }
    } catch (e) {
        console.error('轮询初始化状态失败:', e);
        setTimeout(() => pollInitStatus(taskId), 3000);
    }
}

function updateInitProgress(progress, message) {
    document.getElementById('initProgressFill').style.width = `${progress}%`;
    document.getElementById('initProgressText').textContent = `${progress}%`;
    document.getElementById('initProgressMessage').textContent = message;
}

function resetInitModal() {
    document.getElementById('initStartBtn').style.display = 'block';
    document.getElementById('initCancelBtn').style.display = 'none';
    document.getElementById('initProgressContainer').style.display = 'none';
    document.getElementById('initTaskStatus').innerHTML = '';
}

// ============= 初始化状态检测（页面刷新后一次性确认） =============
// 页面刷新后调用一次 /init/status 确认当前状态，然后依赖 WebSocket 推送
// 不再持续轮询，避免不必要的请求
let _initStatusCheckTimer = null;

function startInitStatusPolling() {
    // 兼容旧调用：改为一次性状态检测
    if (_initStatusCheckTimer) return;
    _initStatusCheckTimer = setTimeout(() => {
        _initStatusCheckTimer = null;
        checkInitStatusOnce();
    }, 500); // 延迟 500ms 让页面先渲染
}

function stopInitStatusPolling() {
    if (_initStatusCheckTimer) {
        clearTimeout(_initStatusCheckTimer);
        _initStatusCheckTimer = null;
    }
}

async function checkInitStatusOnce() {
    if (!state.scriptId) return;
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/init/status?script_id=${state.scriptId}`, { silent: true });
        if (!data.success) return;

        const isRunning = data.is_running;
        const scriptStatus = data.status;
        const progressMsg = data.progress_message || '';
        const progress = data.progress || 0;

        // 更新遮罩上的当前步骤文本
        if (progressMsg) {
            const currentEl = document.getElementById('initTaskCurrent');
            if (currentEl) currentEl.textContent = progressMsg;
        }

        // 恢复进度条
        if (progress > 0) {
            const barEl = document.getElementById('initTaskProgressBar');
            const fillEl = document.getElementById('initTaskProgressFill');
            const textEl = document.getElementById('initTaskProgressText');
            if (barEl) barEl.style.display = 'block';
            if (fillEl) fillEl.style.width = `${progress}%`;
            if (textEl) {
                textEl.style.display = 'block';
                textEl.textContent = `${progress}%`;
            }
        }

        // 清除日志占位符“等待任务启动...”，并将当前步骤作为第一条日志显示
        // 这样刷新页面后用户能立即看到有意义的信息，而不是空白或占位文本
        if (isRunning && progressMsg) {
            const logEl = document.getElementById('initTaskLog');
            if (logEl) {
                const placeholder = logEl.querySelector('div[style*="text-align:center"]');
                if (placeholder) logEl.innerHTML = '';
                // 如果日志为空，添加当前步骤作为第一条记录
                if (logEl.children.length === 0) {
                    appendInitTaskLog(progressMsg, 'running');
                }
            }
        }

        if (isRunning) {
            // 任务正在运行：依赖 WebSocket 推送进度，不再轮询
            console.log('[init] 任务正在运行，依赖 WebSocket 推送');
            return;
        }

        // 任务未运行，根据状态处理
        if (scriptStatus === 'initializing') {
            // 僵尸状态：服务器重启后内存任务丢失
            if (state.scriptData) state.scriptData.status = 'failed';
            updateStatusBadge('failed');
            const btn = document.getElementById('initInterruptBtn');
            if (btn) {
                btn.innerHTML = '<i class="fas fa-times"></i> 关闭';
                btn.onclick = () => {
                    hideInitTaskMask();
                    if (typeof showInitModal === 'function') {
                        showInitModal({ locked: true, startStep: 2 });
                    }
                };
            }
            showToast('初始化任务已丢失（服务器可能重启），请重新开始', 'warning');
            return;
        }

        // 任务已结束
        if (scriptStatus === 'ready') {
            state.webnovelInitialized = true;
            hideInitTaskMask();
            await loadScriptInfo();
            await loadCharacters();
            renderChapterList();
            showToast('深度初始化完成！', 'success');
            if (typeof showWorldModal === 'function') showWorldModal();
        } else if (scriptStatus === 'failed') {
            if (state.scriptData) state.scriptData.status = 'failed';
            updateStatusBadge('failed');
            hideInitTaskMask();
            showToast('深度初始化失败: ' + progressMsg, 'error');
        }
    } catch (e) {
        console.warn('[init] 检测初始化状态失败:', e);
    }
}

