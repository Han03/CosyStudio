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
    document.getElementById('initAiBtn').style.display = 'none';
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
            if (cs.hard_constraints) document.getElementById('initConstraints').value = cs.hard_constraints;
            if (cs.core_selling_points) document.getElementById('initCoreSellingPoints').value = cs.core_selling_points;
            if (cs.opening_hook) document.getElementById('initOpeningHook').value = cs.opening_hook;
        }

        // 跳转到后端保存的当前步骤
        if (result.current_step && result.current_step >= 2 && result.current_step <= 7) {
            currentInitStep = result.current_step;
        }

        console.log('[init] 已恢复初始化数据，当前步骤:', currentInitStep);
    } catch (e) {
        console.warn('[init] 恢复初始化数据失败:', e);
    }
}

function resetAllFields() {
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

    // 切到 Step 1 时，回填已有书名（从 Step 2 回退或已有剧本直接回第一步时）
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
    }

    document.getElementById('initPrevBtn').style.display = currentInitStep > 1 ? 'block' : 'none';
    document.getElementById('initAiBtn').style.display = currentInitStep >= 2 && currentInitStep <= 6 ? 'block' : 'none';

    if (currentInitStep === 7) {
        document.getElementById('initNextBtn').textContent = '确认并初始化';
        document.getElementById('initAiBtn').style.display = 'none';
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

        // Step 1 已有 script_id 时：检查是否修改了书名，保存后进入 Step 2
        if (currentInitStep === 1 && state.scriptId) {
            const newName = document.getElementById('initCreateBookName')?.value.trim();
            const oldName = state.scriptData?.name || '';
            if (newName && newName !== oldName) {
                try {
                    const data = await apiRequest('/api/books/scripts/rename', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ script_id: state.scriptId, name: newName }),
                        errorPrefix: '保存失败'
                    });
                    if (data.success) {
                        if (window.setScriptTitle) setScriptTitle(newName);
                        showToast('书名已更新', 'success');
                    } else {
                        showToast(data.message || '保存书名失败', 'error');
                    }
                } catch (e) {
                    console.error('保存书名失败:', e);
                    showToast('保存书名失败: ' + e.message, 'error');
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
            if (constraintPackages.length > 0) {
                if (selectedPackageIndex < 0) {
                    alert('请选择一个创意约束包方案');
                    return false;
                }
            } else {
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
        case 6:
            if (constraintPackages.length > 0 && selectedPackageIndex >= 0) {
                const pkg = constraintPackages[selectedPackageIndex];
                initData.constraints = {
                    anti_trope: pkg.anti_trope_rule || '',
                    hard_constraints: pkg.hard_constraints || [],
                    core_selling_points: pkg.one_liner_selling_point || '',
                    opening_hook: pkg.opening_hook || '',
                    protagonist_flaw: pkg.protagonist_flaw_driven || '',
                    villain_mirror: pkg.antagonist_mirror || '',
                    selected_package_name: pkg.package_name || ''
                };
            } else {
                initData.constraints = {
                    anti_trope: document.getElementById('initAntiTrope').value.trim(),
                    hard_constraints: document.getElementById('initConstraints').value.trim(),
                    core_selling_points: document.getElementById('initCoreSellingPoints').value.trim(),
                    opening_hook: document.getElementById('initOpeningHook').value.trim()
                };
            }
            break;
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

async function generateAiData() {
    const btn = document.getElementById('initAiBtn');
    btn.disabled = true;
    btn.textContent = '生成中...';
    
    try {
        saveStepData(currentInitStep);
        
        const currentStepData = {};
        if (initData.project) currentStepData.project = initData.project;
        if (initData.protagonist) currentStepData.protagonist = initData.protagonist;
        if (initData.relationship) currentStepData.relationship = initData.relationship;
        if (initData.golden_finger) currentStepData.golden_finger = initData.golden_finger;
        if (initData.world) currentStepData.world = initData.world;
        if (initData.constraints) currentStepData.constraints = initData.constraints;
        
        const data = await apiRequest(`/api/books/scripts/webnovel/init/ai/generate/${currentInitStep}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script_id: state.scriptId,
                step: currentInitStep,
                current_data: currentStepData
            }),
            errorPrefix: 'AI生成失败'
        });
        if (data.success && data.data) {
            fillStepData(currentInitStep, data.data, data.is_packages || false);
        } else {
            showToast('AI生成失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('AI生成失败:', e);
        showToast('AI生成失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'AI生成';
    }
}

let constraintPackages = [];
let selectedPackageIndex = -1;

function fillStepData(step, data, isPackages = false) {
    switch(step) {
        case 2:
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
    manualInput.style.display = 'none';
    
    list.innerHTML = constraintPackages.map((pkg, index) => {
        const scoring = pkg.scoring || {};
        const totalScore = Object.values(scoring).reduce((sum, s) => sum + (s.score || 0), 0);
        const hardConstraints = Array.isArray(pkg.hard_constraints) ? pkg.hard_constraints : [];
        
        return `
            <div class="constraint-package-card ${selectedPackageIndex === index ? 'selected' : ''}" onclick="selectConstraintPackage(${index})">
                <div class="constraint-package-header">
                    <h4>${pkg.package_name || `方案${String.fromCharCode(65 + index)}`}</h4>
                    <div class="constraint-package-score">
                        <span class="score-value">${totalScore}</span>
                        <span class="score-label">总分</span>
                    </div>
                </div>
                <div class="constraint-package-body">
                    <div class="constraint-package-item">
                        <strong>一句话卖点：</strong>${pkg.one_liner_selling_point || ''}
                    </div>
                    <div class="constraint-package-item">
                        <strong>反套路规则：</strong>${pkg.anti_trope_rule || ''}
                    </div>
                    <div class="constraint-package-item">
                        <strong>硬约束：</strong>
                        <ul>${hardConstraints.map(c => `<li>${c}</li>`).join('')}</ul>
                    </div>
                    <div class="constraint-package-item">
                        <strong>主角缺陷驱动：</strong>${pkg.protagonist_flaw_driven || ''}
                    </div>
                    <div class="constraint-package-item">
                        <strong>反派镜像：</strong>${pkg.antagonist_mirror || ''}
                    </div>
                    <div class="constraint-package-item">
                        <strong>开篇钩子：</strong>${pkg.opening_hook || ''}
                    </div>
                    <div class="constraint-package-item">
                        <strong>差异化说明：</strong>${pkg.differentiation || ''}
                    </div>
                </div>
                <div class="constraint-package-scoring">
                    <div class="scoring-row">
                        <span class="scoring-label">创意独特性</span>
                        <div class="scoring-bar">
                            <div class="scoring-fill" style="width: ${(scoring.creativity?.score || 0) * 10}%"></div>
                        </div>
                        <span class="scoring-value">${scoring.creativity?.score || 0}/10</span>
                        <span class="scoring-reason">${scoring.creativity?.reason || ''}</span>
                    </div>
                    <div class="scoring-row">
                        <span class="scoring-label">落地可行性</span>
                        <div class="scoring-bar">
                            <div class="scoring-fill" style="width: ${(scoring.feasibility?.score || 0) * 10}%"></div>
                        </div>
                        <span class="scoring-value">${scoring.feasibility?.score || 0}/10</span>
                        <span class="scoring-reason">${scoring.feasibility?.reason || ''}</span>
                    </div>
                    <div class="scoring-row">
                        <span class="scoring-label">市场吸引力</span>
                        <div class="scoring-bar">
                            <div class="scoring-fill" style="width: ${(scoring.market_appeal?.score || 0) * 10}%"></div>
                        </div>
                        <span class="scoring-value">${scoring.market_appeal?.score || 0}/10</span>
                        <span class="scoring-reason">${scoring.market_appeal?.reason || ''}</span>
                    </div>
                    <div class="scoring-row">
                        <span class="scoring-label">长线可持续性</span>
                        <div class="scoring-bar">
                            <div class="scoring-fill" style="width: ${(scoring.sustainability?.score || 0) * 10}%"></div>
                        </div>
                        <span class="scoring-value">${scoring.sustainability?.score || 0}/10</span>
                        <span class="scoring-reason">${scoring.sustainability?.reason || ''}</span>
                    </div>
                    <div class="scoring-row">
                        <span class="scoring-label">情感冲击力</span>
                        <div class="scoring-bar">
                            <div class="scoring-fill" style="width: ${(scoring.emotional_impact?.score || 0) * 10}%"></div>
                        </div>
                        <span class="scoring-value">${scoring.emotional_impact?.score || 0}/10</span>
                        <span class="scoring-reason">${scoring.emotional_impact?.reason || ''}</span>
                    </div>
                </div>
                <div class="constraint-package-three-questions">
                    <strong>三问筛选：</strong>
                    <div class="question-item"><strong>Q1：</strong>${pkg.three_questions?.q1 || ''}</div>
                    <div class="question-item"><strong>Q2：</strong>${pkg.three_questions?.q2 || ''}</div>
                    <div class="question-item"><strong>Q3：</strong>${pkg.three_questions?.q3 || ''}</div>
                </div>
                <div class="constraint-package-select">
                    ${selectedPackageIndex === index ? '<i class="fas fa-check-circle"></i> 已选择' : '<i class="fas fa-circle"></i> 点击选择'}
                </div>
            </div>
        `;
    }).join('');
}

function selectConstraintPackage(index) {
    selectedPackageIndex = index;
    renderConstraintPackages();
    
    const pkg = constraintPackages[index];
    initData.constraints = {
        anti_trope: pkg.anti_trope_rule || '',
        hard_constraints: pkg.hard_constraints || [],
        core_selling_points: pkg.one_liner_selling_point || '',
        opening_hook: pkg.opening_hook || '',
        protagonist_flaw: pkg.protagonist_flaw_driven || '',
        villain_mirror: pkg.antagonist_mirror || '',
        selected_package_name: pkg.package_name || ''
    };
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
    const log = document.getElementById('initTaskLog');
    if (mask) mask.style.display = 'flex';
    if (current) current.textContent = message || '准备中...';
    if (log) log.innerHTML = '<div style="color:var(--neu-text-muted, #888); text-align:center; font-size:13px;">等待任务启动...</div>';
}

function hideInitTaskMask() {
    const mask = document.getElementById('initTaskMask');
    if (mask) mask.style.display = 'none';
}

function appendInitTaskLog(message, status) {
    const log = document.getElementById('initTaskLog');
    if (!log) return;
    const empty = log.querySelector('div[style*="text-align:center"]');
    if (empty) log.innerHTML = '';
    const item = document.createElement('div');
    item.style.cssText = 'padding:4px 0; border-bottom:1px solid rgba(0,0,0,0.05); font-size:13px; line-height:1.6;';
    const color = status === 'failed' ? '#dc3545' : status === 'completed' ? '#28a745' : 'var(--neu-text, #333)';
    item.innerHTML = `<span style="color:${color};">●</span> <span>${message}</span>`;
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
}

function handleInitProgressMessage(msg) {
    const status = msg.status;
    const step = msg.step;
    const message = msg.message;
    const progress = msg.progress || 0;

    showInitTaskMask(message);
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
            await apiRequest('/api/books/scripts/webnovel/init/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ script_id: state.scriptId }),
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

function cancelInit() {
    resetInitModal();
}

