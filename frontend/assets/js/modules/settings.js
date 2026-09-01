const PLATFORM_CONFIG_DETAILS = {
    aliyun: {
        name: '阿里云百炼',
        icon: 'fa-cloud',
        color: '#6c5ce7',
        needsSecretKey: false,
        enabled: false,
        description: '阿里云推出的大模型服务平台，提供通义千问系列模型（Qwen-Plus、Qwen-Turbo、Qwen-Max等），支持中文对话、多模态生成等能力。',
        features: ['通义千问系列模型', '中文理解能力强', '支持多模态', '高性价比'],
        website: 'https://bailian.console.aliyun.com/',
        models: ['Qwen-Plus', 'Qwen-Turbo', 'Qwen-Max', 'Qwen-Long']
    },
    volcengine: {
        name: '火山引擎',
        icon: 'fa-fire',
        color: '#ff6b35',
        needsSecretKey: true,
        authTypes: [
            { value: 'api_key', label: 'API Key (Bearer Token)', description: '适用于AI生成相关接口，请求方式简单' },
            { value: 'access_key', label: 'Access Key (AK/SK签名)', description: '标准云API凭证，安全性较高' }
        ],
        enabled: false,
        description: '字节跳动旗下的云服务平台，提供豆包系列大模型，支持多轮对话、创意生成等能力。',
        features: ['豆包系列模型', '多轮对话', '创意生成', '实时信息'],
        website: 'https://www.volcengine.com/',
        models: ['doubao-seed-2-1-pro-260628', 'doubao-seed-2-1-turbo-260628', 'doubao-seed-evolving-latest-version']
    },
    deepseek: {
        name: 'DeepSeek',
        icon: 'fa-compass',
        color: '#00d4ff',
        needsSecretKey: false,
        enabled: false,
        description: '深度求索（DeepSeek）是一家AI公司，推出的DeepSeek系列模型在代码生成和数学推理方面表现出色。',
        features: ['代码生成强', '数学推理', 'R1模型', '开源友好'],
        website: 'https://www.deepseek.com/',
        models: ['DeepSeek-Chat', 'DeepSeek-R1-Chat', 'DeepSeek-R1-Vision']
    },
    zhipu: {
        name: '智谱AI',
        icon: 'fa-brain',
        color: '#00b4d8',
        needsSecretKey: false,
        enabled: false,
        description: '智谱AI是专注于认知大模型的人工智能公司，提供GLM系列大模型，在中文语义理解、逻辑推理等方面表现优异。',
        features: ['GLM-4系列模型', '中文语义理解', '逻辑推理', '代码生成'],
        website: 'https://www.zhipuai.cn/',
        models: ['GLM-4-Plus', 'GLM-4-Flash', 'GLM-3-Turbo']
    },
    baidu: {
        name: '百度千帆',
        icon: 'fa-search',
        color: '#262626',
        needsSecretKey: true,
        enabled: false,
        description: '百度智能云推出的大模型服务平台，提供文心一言（ERNIE）系列模型，支持多模态对话、知识问答等能力。',
        features: ['ERNIE系列模型', '知识增强', '多模态能力', '企业级服务'],
        website: 'https://cloud.baidu.com/product/wenxinworkshop',
        models: ['ERNIE-4.0-Turbo', 'ERNIE-3.5-Turbo', 'ERNIE-4.0']
    },
    moonshot: {
        name: '月之暗面',
        icon: 'fa-moon',
        color: '#1e3a5f',
        needsSecretKey: false,
        enabled: false,
        description: '月之暗面是一家专注于大语言模型研发的AI公司，推出的Moonshot系列模型以长上下文窗口著称。',
        features: ['超长上下文（128k）', '数学推理强', '代码生成', '多语言支持'],
        website: 'https://moonshot.cn/',
        models: ['Moonshot-v1-8k', 'Moonshot-v1-32k', 'Moonshot-v1-128k']
    },
    google: {
        name: 'Google AI Studio',
        icon: 'fa-google-g',
        color: '#4285f4',
        needsSecretKey: false,
        enabled: false,
        description: '谷歌推出的AI开发平台，提供Gemini系列大模型，支持多模态理解和生成。',
        features: ['Gemini系列模型', '多模态理解', '强大推理', '全球服务'],
        website: 'https://ai.google.dev/',
        models: ['Gemini-Pro', 'Gemini-1.5-Flash', 'Gemini-1.5-Pro']
    },
    groq: {
        name: 'Groq',
        icon: 'fa-zap',
        color: '#10b981',
        needsSecretKey: false,
        enabled: false,
        description: 'Groq提供超快推理速度的大模型服务，支持Mixtral、Llama等热门开源模型。',
        features: ['超高推理速度', 'Mixtral模型', 'Llama模型', '低延迟'],
        website: 'https://groq.com/',
        models: ['Mixtral-8x7B', 'Llama-3-8B', 'Llama-3-70B']
    },
    openrouter: {
        name: 'OpenRouter',
        icon: 'fa-globe',
        color: '#8b5cf6',
        needsSecretKey: false,
        enabled: false,
        description: 'OpenRouter是一个聚合平台，提供一站式访问多家AI服务商的模型，包括OpenAI、Anthropic等。',
        features: ['聚合多家供应商', 'GPT系列模型', 'Claude系列', '一站式管理'],
        website: 'https://openrouter.ai/',
        models: ['Llama-3-8B', 'GPT-4', 'Claude-3-Sonnet']
    },
};

const CAPABILITY_TYPE_DETAILS = {
    text_predict: {
        name: '文本预测',
        icon: 'fa-comment',
        color: '#6c5ce7',
        description: '大语言模型文本生成能力，用于对话、问答、创作等场景',
        output_type: '流式'
    },
    text_to_speech: {
        name: '语音合成',
        icon: 'fa-volume-up',
        color: '#10b981',
        description: '将文本转换为语音，支持多种音色和语速',
        output_type: '流式'
    },
    text_to_image: {
        name: '文生图',
        icon: 'fa-image',
        color: '#8b5cf6',
        description: '根据文本描述生成图像',
        output_type: '同步'
    },
    text_to_vector: {
        name: '文本转向量',
        icon: 'fa-puzzle-piece',
        color: '#f59e0b',
        description: '将文本转换为向量表示，用于语义检索和相似度计算',
        output_type: '同步'
    },
    text_rerank: {
        name: '片段重排序',
        icon: 'fa-sort-amount-down',
        color: '#ef4444',
        description: '对检索候选片段按与查询的相关性重新排序，用于 RAG 结果精排',
        output_type: '同步'
    }
};

let currentPlatformKey = 'aliyun';
let currentSettingsTab = 'platform';
let currentCapabilityType = 'text_predict';
let currentCallPointCategory = '';
let _callPointCategoriesData = null;
let _callPointCapOptions = '';
let draggedElement = null;

async function loadSettingsNav() {
    const nav = document.getElementById('settingsNav');
    const content = document.getElementById('settingsContent');
    if (!nav || !content) return;

    nav.innerHTML = `
        <button class="nav-link ${currentSettingsTab === 'platform' ? 'active' : ''}" onclick="switchSettingsTab('platform')" style="display: flex; align-items: center; gap: 8px; padding: 10px 20px; font-weight: 600;">
            <i class="fas fa-server" style="color: #6c5ce7;"></i>
            <span>平台配置</span>
        </button>
        <button class="nav-link ${currentSettingsTab === 'capability' ? 'active' : ''}" onclick="switchSettingsTab('capability')" style="display: flex; align-items: center; gap: 8px; padding: 10px 20px; font-weight: 600;">
            <i class="fas fa-rocket" style="color: #10b981;"></i>
            <span>模型能力</span>
        </button>
        <button class="nav-link ${currentSettingsTab === 'callpoint' ? 'active' : ''}" onclick="switchSettingsTab('callpoint')" style="display: flex; align-items: center; gap: 8px; padding: 10px 20px; font-weight: 600;">
            <i class="fas fa-sliders" style="color: #f59e0b;"></i>
            <span>调用点配置</span>
        </button>
    `;

    if (currentSettingsTab === 'platform') {
        await loadPlatformConfig();
    } else if (currentSettingsTab === 'callpoint') {
        await loadCallPointConfig();
    } else {
        await loadCapabilityConfig();
    }
}

function switchSettingsTab(tab) {
    currentSettingsTab = tab;
    document.querySelectorAll('#settingsNav .nav-link').forEach(el => {
        el.classList.remove('active');
    });
    const activeLink = document.querySelector(`#settingsNav .nav-link[onclick="switchSettingsTab('${tab}')"]`);
    if (activeLink) activeLink.classList.add('active');

    if (tab === 'platform') {
        loadPlatformConfig();
    } else if (tab === 'callpoint') {
        loadCallPointConfig();
    } else {
        loadCapabilityConfig();
    }
}

async function loadPlatformConfig() {
    const content = document.getElementById('settingsContent');
    if (!content) return;

    try {
        const data = await apiRequest('/api/settings', { silent: true });
        const platformKeys = data.config?.platform_keys || {};

        const platformList = Object.entries(PLATFORM_CONFIG_DETAILS);
        const firstPlatformKey = platformList[0]?.[0] || 'aliyun';
        const activePlatformKey = currentPlatformKey || firstPlatformKey;

        let html = '<div class="row">';
        html += '<div class="col-md-3">';
        html += '<div class="platform-list" id="platformNav">';
        
        html += platformList.map(([key, detail]) => {
            const config = platformKeys[key] || {};
            const enabled = config.enabled || false;
            const isActive = key === activePlatformKey;
            const enabledBadge = enabled ? '<span class="badge bg-success" style="font-size: 9px;">启用</span>' : '<span class="badge bg-secondary" style="font-size: 9px;">停用</span>';
            return `
                <div class="platform-item-card" id="platform-card-${key}" onclick="showPlatformConfigCard('${key}')" style="cursor: pointer; display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border-radius: 10px; transition: all 0.2s ease; text-align: left; ${isActive ? 'background: var(--neu-bg); color: var(--neu-accent); box-shadow: var(--neu-shadow-inset);' : 'background: var(--neu-bg); color: var(--neu-text-muted); box-shadow: var(--neu-shadow-small);'}">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <i class="fas ${detail.icon}" style="font-size: 16px;"></i>
                        <span style="font-weight: 600; font-size: 13px;">${detail.name}</span>
                        ${enabledBadge}
                    </div>
                    <div class="flex flex-wrap gap-1">
                        ${detail.models.slice(0, 3).map(m => `<span class="badge" style="font-size: 8px; background: rgba(108, 92, 231, 0.1); color: ${isActive ? 'var(--neu-accent)' : 'var(--neu-text-muted)'}; padding: 1px 5px;">${m}</span>`).join('')}
                        ${detail.models.length > 3 ? `<span class="badge" style="font-size: 8px; background: rgba(0,0,0,0.05); color: var(--neu-text-muted); padding: 1px 5px;">+${detail.models.length - 3}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        html += '</div></div>';
        html += '<div class="col-md-9" id="platformConfigCardContent"></div>';
        html += '</div>';

        content.innerHTML = html;
        
        showPlatformConfigCard(activePlatformKey);
    } catch (e) {
        content.innerHTML = '<div class="text-center text-danger">加载平台配置失败</div>';
    }
}

function showPlatformConfig(platformKey) {
    showPlatformConfigCard(platformKey);
}

function showPlatformConfigCard(platformKey) {
    currentPlatformKey = platformKey;
    const detail = PLATFORM_CONFIG_DETAILS[platformKey];
    const content = document.getElementById('platformConfigCardContent');

    document.querySelectorAll('.platform-item-card').forEach(card => {
        card.style.background = 'var(--neu-bg)';
        card.style.color = 'var(--neu-text-muted)';
        card.style.boxShadow = 'var(--neu-shadow-small)';
        const badges = card.querySelectorAll('.badge:not(.bg-success):not(.bg-secondary)');
        badges.forEach(b => b.style.color = 'var(--neu-text-muted)');
    });
    
    const activeCard = document.getElementById(`platform-card-${platformKey}`);
    if (activeCard) {
        activeCard.style.background = 'var(--neu-bg)';
        activeCard.style.color = 'var(--neu-accent)';
        activeCard.style.boxShadow = 'var(--neu-shadow-inset)';
        const badges = activeCard.querySelectorAll('.badge:not(.bg-success):not(.bg-secondary)');
        badges.forEach(b => b.style.color = 'var(--neu-accent)');
    }

    apiRequest('/api/settings', { silent: true })
        .then(data => {
            const platformKeys = data.config?.platform_keys || {};
            const config = platformKeys[platformKey] || {};
            const enabled = config.enabled || false;

            content.innerHTML = `
                <div class="card" style="border-radius: 12px;">
                    <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <i class="fas ${detail.icon}" style="color: ${detail.color}; font-size: 24px;"></i>
                            <div>
                                <h5 style="margin: 0; font-weight: 700;">${detail.name}</h5>
                                <p style="margin: 2px 0 0; font-size: 12px; color: var(--neu-text-muted);">平台配置</p>
                            </div>
                        </div>
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="platform-enabled-${platformKey}" ${enabled ? 'checked' : ''} onchange="togglePlatformEnabled('${platformKey}')">
                            <label class="form-check-label" for="platform-enabled-${platformKey}" style="font-size: 13px;">${enabled ? '已启用' : '已停用'}</label>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-8">
                                <div class="mb-4">
                                    <h6 style="font-weight: 600; margin-bottom: 8px;">平台简介</h6>
                                    <p style="font-size: 13px; color: var(--neu-text-muted); line-height: 1.6;">${detail.description}</p>
                                </div>
                                <div class="mb-4">
                                    <h6 style="font-weight: 600; margin-bottom: 8px;">主要特性</h6>
                                    <div class="flex flex-wrap gap-2">
                                        ${detail.features.map(f => `<span class="badge bg-light text-dark" style="font-size: 12px;">${f}</span>`).join('')}
                                    </div>
                                </div>
                                <div class="mb-4">
                                    <h6 style="font-weight: 600; margin-bottom: 8px;">支持模型</h6>
                                    <div class="flex flex-wrap gap-2">
                                        ${detail.models.map(m => `<span class="badge" style="font-size: 12px; background: ${detail.color}20; color: ${detail.color};">${m}</span>`).join('')}
                                    </div>
                                </div>
                                <div>
                                    <a href="${detail.website}" target="_blank" class="btn btn-sm btn-outline-secondary" style="display: inline-flex; align-items: center; gap: 6px;">
                                        <i class="fas fa-external-link-alt"></i> 访问官网
                                    </a>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <h6 style="font-weight: 600; margin-bottom: 12px;">API配置</h6>
                                ${detail.authTypes ? `
                                <div class="mb-3">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">鉴权方式</label>
                                    <select class="form-select form-select-sm" id="platform-auth-type-${platformKey}" onchange="toggleVolcengineAuthFields('${platformKey}')">
                                        ${detail.authTypes.map(at => `<option value="${at.value}" ${config.auth_type === at.value ? 'selected' : ''}>${at.label}</option>`).join('')}
                                    </select>
                                    <div id="platform-auth-desc-${platformKey}" class="form-text" style="font-size: 11px; color: #666;">${detail.authTypes.find(at => at.value === (config.auth_type || detail.authTypes[0].value))?.description}</div>
                                </div>
                                ` : ''}
                                <div class="mb-3">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">${detail.authTypes ? (config.auth_type === 'access_key' ? 'Access Key ID (AK)' : 'API Key') : 'API Key'}</label>
                                    <input type="password" class="form-control form-control-sm" id="platform-api-key-${platformKey}" value="${config.api_key || ''}" placeholder="${detail.authTypes ? (config.auth_type === 'access_key' ? 'AK...' : 'sk-...') : 'sk-...'}" autocomplete="off">
                                </div>
                                ${detail.authTypes ? (config.auth_type === 'access_key' ? `
                                <div class="mb-3" id="platform-secret-key-div-${platformKey}">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">Secret Access Key (SK)</label>
                                    <input type="password" class="form-control form-control-sm" id="platform-secret-key-${platformKey}" value="${config.secret_key || ''}" placeholder="SK..." autocomplete="off">
                                </div>
                                ` : (detail.needsSecretKey ? `
                                <div class="mb-3" id="platform-secret-key-div-${platformKey}">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">Secret Key</label>
                                    <input type="password" class="form-control form-control-sm" id="platform-secret-key-${platformKey}" value="${config.secret_key || ''}" placeholder="Secret Key" autocomplete="off">
                                </div>
                                ` : '')) : (detail.needsSecretKey ? `
                                <div class="mb-3" id="platform-secret-key-div-${platformKey}">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">Secret Key</label>
                                    <input type="password" class="form-control form-control-sm" id="platform-secret-key-${platformKey}" value="${config.secret_key || ''}" placeholder="Secret Key" autocomplete="off">
                                </div>
                                ` : '')}
                                <div class="mb-3">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">默认模型</label>
                                    <input type="text" class="form-control form-control-sm" id="platform-default-model-${platformKey}" value="${config.default_model || ''}" placeholder="默认模型ID">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label" style="font-size: 12px; font-weight: 600;">API Base URL</label>
                                    <input type="text" class="form-control form-control-sm" id="platform-base-url-${platformKey}" value="${config.base_url || ''}" placeholder="API地址">
                                </div>
                                <button class="btn btn-sm btn-primary w-100" onclick="saveSinglePlatformConfig('${platformKey}')">
                                    <i class="fas fa-save"></i> 保存配置
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        })
        .catch(e => {
            content.innerHTML = '<div class="text-center text-danger">加载配置失败</div>';
        });
}

function closePlatformConfigCard() {
    const content = document.getElementById('platformConfigCardContent');
    if (content) {
        content.style.display = 'none';
        content.innerHTML = '';
    }
}

function togglePlatformEnabled(platformKey) {
    const checkbox = document.getElementById(`platform-enabled-${platformKey}`);
    const label = checkbox.nextElementSibling;
    const enabled = checkbox.checked;
    label.textContent = enabled ? '已启用' : '已停用';

    saveSinglePlatformConfig(platformKey);
}

function toggleVolcengineAuthFields(platformKey) {
    const detail = PLATFORM_CONFIG_DETAILS[platformKey];
    const authType = document.getElementById(`platform-auth-type-${platformKey}`)?.value || 'api_key';
    const secretKeyDiv = document.getElementById(`platform-secret-key-div-${platformKey}`);
    const authDesc = document.getElementById(`platform-auth-desc-${platformKey}`);
    const apiKeyLabel = document.querySelector(`#platform-api-key-${platformKey}`)?.previousElementSibling;
    const secretKeyLabel = document.querySelector(`#platform-secret-key-${platformKey}`)?.previousElementSibling;
    const apiKeyInput = document.getElementById(`platform-api-key-${platformKey}`);
    const secretKeyInput = document.getElementById(`platform-secret-key-${platformKey}`);

    if (authDesc && detail.authTypes) {
        authDesc.textContent = detail.authTypes.find(at => at.value === authType)?.description || '';
    }

    if (apiKeyLabel) {
        apiKeyLabel.textContent = authType === 'access_key' ? 'Access Key ID (AK)' : 'API Key';
    }
    if (apiKeyInput) {
        apiKeyInput.placeholder = authType === 'access_key' ? 'AK...' : 'sk-...';
    }

    if (secretKeyDiv) {
        if (authType === 'access_key') {
            secretKeyDiv.style.display = 'block';
            if (secretKeyLabel) {
                secretKeyLabel.textContent = 'Secret Access Key (SK)';
            }
            if (secretKeyInput) {
                secretKeyInput.placeholder = 'SK...';
            }
        } else {
            secretKeyDiv.style.display = 'none';
        }
    }
}

async function saveSinglePlatformConfig(platformKey) {
    const detail = PLATFORM_CONFIG_DETAILS[platformKey];
    const enabled = document.getElementById(`platform-enabled-${platformKey}`)?.checked || false;
    const apiKey = document.getElementById(`platform-api-key-${platformKey}`)?.value || '';
    const secretKey = document.getElementById(`platform-secret-key-${platformKey}`)?.value || '';
    const defaultModel = document.getElementById(`platform-default-model-${platformKey}`)?.value || '';
    const baseUrl = document.getElementById(`platform-base-url-${platformKey}`)?.value || '';
    const authType = document.getElementById(`platform-auth-type-${platformKey}`)?.value || 'api_key';

    const config = {
        enabled: enabled,
        api_key: apiKey,
        secret_key: secretKey,
        default_model: defaultModel,
        base_url: baseUrl || detail.base_url || '',
        auth_type: authType
    };

    try {
        const data = await apiRequest('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform_keys: { [platformKey]: config } }),
            errorPrefix: '保存失败'
        });
        if (data.success) {
            showToast(`${detail.name}配置保存成功`, 'success');
            loadPlatformConfig();
        } else {
            showToast('保存失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

async function loadCapabilityConfig() {
    const content = document.getElementById('settingsContent');
    if (!content) return;

    try {
        const [capData, platData] = await Promise.all([
            apiRequest('/api/capabilities', { silent: true }),
            apiRequest('/api/capabilities/platforms', { silent: true })
        ]);
        const capabilities = capData.capabilities || {};
        const platforms = platData.platforms || {};

        let tabsHtml = '<nav class="nav nav-tabs mb-4" id="capabilityNav">';
        tabsHtml += Object.entries(CAPABILITY_TYPE_DETAILS).map(([key, detail]) => {
            const activeClass = key === currentCapabilityType ? 'active' : '';
            const count = (capabilities[key] || []).length;
            return `
                <button class="nav-link ${activeClass}" onclick="showCapabilityType('${key}')" style="display: flex; align-items: center; gap: 8px; padding: 10px 20px; font-weight: 600;">
                    <i class="fas ${detail.icon}" style="color: ${detail.color};"></i>
                    <span>${detail.name}</span>
                    <span class="badge bg-secondary" style="font-size: 10px;">${count}</span>
                </button>
            `;
        }).join('');
        tabsHtml += '</nav>';

        let infoHtml = '<div class="card mb-4" style="border-radius: 12px;">';
        infoHtml += '<div class="card-header" style="font-weight: 600;">';
        infoHtml += '<i class="fas fa-info-circle"></i> 使用说明';
        infoHtml += '</div>';
        infoHtml += '<div class="card-body">';
        infoHtml += '<p style="font-size: 13px; color: var(--neu-text-muted);">';
        infoHtml += '模型能力按优先级从高到低依次调用。当高优先级模型不可用时，自动降级到低优先级模型。';
        infoHtml += '</p>';
        infoHtml += '<p style="font-size: 13px; color: var(--neu-text-muted); margin-top: 8px;">';
        infoHtml += '<strong>优先级数值越大优先级越高</strong>，建议本地模型设置较高优先级，云端模型设置较低优先级。';
        infoHtml += '</p>';
        infoHtml += '</div></div>';

        content.innerHTML = `${tabsHtml}${infoHtml}<div id="capabilityConfigContent"></div>`;

        showCapabilityType(currentCapabilityType, capabilities, platforms);
    } catch (e) {
        content.innerHTML = '<div class="text-center text-danger">加载模型能力配置失败</div>';
    }
}

async function showCapabilityType(capabilityType, capabilities = null, platforms = null) {
    currentCapabilityType = capabilityType;
    const detail = CAPABILITY_TYPE_DETAILS[capabilityType];

    document.querySelectorAll('#capabilityNav .nav-link').forEach(el => {
        el.classList.remove('active');
    });
    const activeLink = document.querySelector(`#capabilityNav .nav-link[onclick="showCapabilityType('${capabilityType}')"]`);
    if (activeLink) activeLink.classList.add('active');

    if (!capabilities || !platforms) {
        const [capData, platData] = await Promise.all([
            apiRequest('/api/capabilities', { silent: true }),
            apiRequest('/api/capabilities/platforms', { silent: true })
        ]);
        capabilities = capData.capabilities || {};
        platforms = platData.platforms || {};
    }

    const capList = capabilities[capabilityType] || [];
    const content = document.getElementById('capabilityConfigContent');

    let html = `
        <div class="card" style="border-radius: 12px;">
            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <i class="fas ${detail.icon}" style="color: ${detail.color}; font-size: 24px;"></i>
                    <div>
                        <h5 style="margin: 0; font-weight: 700;">${detail.name}</h5>
                        <p style="margin: 2px 0 0; font-size: 12px; color: var(--neu-text-muted);">${detail.description} · 输出方式: ${detail.output_type}</p>
                    </div>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="btn btn-sm btn-outline-info" onclick="openCapabilityTest('${capabilityType}')">
                        <i class="fas fa-play-circle"></i> 测试
                    </button>
                    <button class="btn btn-sm btn-primary" onclick="showAddCapabilityModal('${capabilityType}')">
                        <i class="fas fa-plus"></i> 添加能力
                    </button>
                </div>
            </div>
            <div class="card-body">
                ${capList.length === 0 ? `
                    <div class="model-list-empty">
                        <i class="fas ${detail.icon}"></i>
                        <p>暂无${detail.name}能力配置</p>
                        <p style="font-size: 12px;">点击上方"添加能力"按钮添加</p>
                    </div>
                ` : `
                    <div class="model-list" id="capability-list-${capabilityType}">
                        ${capList.map((cap, index) => {
                            const platInfo = platforms[cap.platform_code] || { name: cap.platform_code };
                            return `
                                <div class="model-item" draggable="true" data-id="${cap.id}" data-type="${capabilityType}" 
                                         ondragstart="handleDragStart(event)" ondragover="handleDragOver(event)" 
                                         ondrop="handleDrop(event)" ondragend="handleDragEnd(event)">
                                    <div class="model-item-info" style="flex: 1;">
                                        <div class="model-item-name">
                                            <span style="display: flex; align-items: center; gap: 8px;">
                                                <span style="cursor: move; color: var(--neu-text-muted);"><i class="fas fa-grip-vertical"></i></span>
                                                ${cap.description || cap.model_code}
                                                <span class="badge" style="font-size: 10px;">#${index + 1}</span>
                                            </span>
                                        </div>
                                        <div class="model-item-meta">
                                            <span class="model-meta-item"><i class="fas fa-server"></i> ${platInfo.name}</span>
                                            <span class="model-meta-item"><i class="fas fa-box"></i> ${cap.model_code}</span>
                                        </div>
                                    </div>
                                    <div class="model-item-actions">
                                        <label class="form-check form-switch" style="margin-right: 8px; padding-top: 4px;">
                                            <input class="form-check-input" type="checkbox" ${cap.enabled ? 'checked' : ''} onchange="toggleCapabilityEnabled('${capabilityType}', '${cap.id}', this.checked)">
                                        </label>
                                        <button class="btn btn-sm btn-outline-secondary" onclick="showEditCapabilityModal('${capabilityType}', '${cap.id}')">
                                            <i class="fas fa-edit"></i>
                                        </button>
                                        <button class="btn btn-sm btn-outline-danger" onclick="deleteCapability('${capabilityType}', '${cap.id}')">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                    <div style="margin-top: 12px; font-size: 12px; color: var(--neu-text-muted);">
                        <i class="fas fa-info-circle"></i> 拖拽调整顺序，顶部优先级最高
                    </div>
                `}
            </div>
        </div>
    `;

    content.innerHTML = html;
}

async function showAddCapabilityModal(capabilityType) {
    const existingModal = document.getElementById('addCapabilityModal');
    if (existingModal) {
        existingModal.remove();
    }

    const detail = CAPABILITY_TYPE_DETAILS[capabilityType];
    const platData = await apiRequest('/api/capabilities/platforms', { silent: true });
    const platforms = platData.platforms || {};

    const modalHtml = `
        <div class="modal fade" id="addCapabilityModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">添加${detail.name}能力</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">平台</label>
                            <select class="form-select" id="add-cap-platform">
                                ${Object.entries(platforms).map(([code, info]) => 
                                    `<option value="${code}">${info.name}</option>`
                                ).join('')}
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">模型编码</label>
                            <input type="text" class="form-control" id="add-cap-model-code" placeholder="如: qwen, cosyvoice, qwen-plus">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">描述</label>
                            <input type="text" class="form-control" id="add-cap-description" placeholder="描述该能力的用途">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">是否启用</label>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="add-cap-enabled" checked>
                                <label class="form-check-label" for="add-cap-enabled">启用该能力</label>
                            </div>
                            <div class="form-text">优先级通过列表拖拽排序设置，顶部优先级最高</div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="addCapability('${capabilityType}')">添加</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    new bootstrap.Modal(document.getElementById('addCapabilityModal')).show();
}

async function addCapability(capabilityType) {
    const platformCode = document.getElementById('add-cap-platform')?.value || '';
    const modelCode = document.getElementById('add-cap-model-code')?.value || '';
    const description = document.getElementById('add-cap-description')?.value || '';
    const enabled = document.getElementById('add-cap-enabled')?.checked || true;

    if (!platformCode || !modelCode) {
        showToast('请填写平台和模型编码', 'error');
        return;
    }

    const capability = {
        id: `${capabilityType}_${platformCode}_${modelCode}`,
        platform_code: platformCode,
        model_code: modelCode,
        priority: 1,
        enabled: enabled,
        description: description || `${platformCode} ${modelCode}`
    };

    try {
        const data = await apiRequest('/api/capabilities', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ capability_type: capabilityType, capability }),
            errorPrefix: '添加失败'
        });
        if (data.success) {
            showToast('能力添加成功', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('addCapabilityModal'));
            if (modal) {
                modal.hide();
            }
            loadCapabilityConfig();
        } else {
            showToast('添加失败: ' + (data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('添加失败: ' + e.message, 'error');
    }
}

async function toggleCapabilityEnabled(capabilityType, capabilityId, enabled) {
    try {
        const data = await apiRequest(`/api/capabilities?capability_type=${capabilityType}&capability_id=${capabilityId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ updates: { enabled } }),
            errorPrefix: '更新失败'
        });
        if (!data.success) {
            showToast('更新失败', 'error');
        }
    } catch (e) {
        showToast('更新失败: ' + e.message, 'error');
    }
}

async function showEditCapabilityModal(capabilityType, capabilityId) {
    const existingModal = document.getElementById('editCapabilityModal');
    if (existingModal) {
        existingModal.remove();
    }

    const data = await apiRequest(`/api/capabilities/detail?capability_type=${capabilityType}&capability_id=${capabilityId}`, {
        silent: true,
        errorPrefix: '加载能力详情失败'
    });
    const cap = data.capability;
    if (!cap) return;

    const platData = await apiRequest('/api/capabilities/platforms', { silent: true });
    const platforms = platData.platforms || {};

    const modalHtml = `
        <div class="modal fade" id="editCapabilityModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">编辑能力配置</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">平台</label>
                            <select class="form-select" id="edit-cap-platform">
                                ${Object.entries(platforms).map(([code, info]) => 
                                    `<option value="${code}" ${cap.platform_code === code ? 'selected' : ''}>${info.name}</option>`
                                ).join('')}
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">模型编码</label>
                            <input type="text" class="form-control" id="edit-cap-model-code" value="${cap.model_code}">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">优先级</label>
                            <input type="number" class="form-control" id="edit-cap-priority" value="${cap.priority}" min="1" max="100">
                            <div class="form-text">数值越大优先级越高</div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">描述</label>
                            <input type="text" class="form-control" id="edit-cap-description" value="${cap.description || ''}">
                        </div>
                        <div class="mb-3">
                            <label class="form-check">
                                <input type="checkbox" class="form-check-input" id="edit-cap-enabled" ${cap.enabled ? 'checked' : ''}>
                                启用该能力
                            </label>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="editCapability('${capabilityType}', '${capabilityId}')">保存</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    new bootstrap.Modal(document.getElementById('editCapabilityModal')).show();
}

async function editCapability(capabilityType, capabilityId) {
    const platformCode = document.getElementById('edit-cap-platform')?.value || '';
    const modelCode = document.getElementById('edit-cap-model-code')?.value || '';
    const priority = parseInt(document.getElementById('edit-cap-priority')?.value || '5');
    const description = document.getElementById('edit-cap-description')?.value || '';
    const enabled = document.getElementById('edit-cap-enabled')?.checked || true;

    const updates = {
        platform_code: platformCode,
        model_code: modelCode,
        priority: priority,
        enabled: enabled,
        description: description || `${platformCode} ${modelCode}`
    };

    try {
        const data = await apiRequest(`/api/capabilities?capability_type=${capabilityType}&capability_id=${capabilityId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ updates }),
            errorPrefix: '更新失败'
        });
        if (data.success) {
            showToast('能力更新成功', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('editCapabilityModal'));
            if (modal) {
                modal.hide();
            }
            loadCapabilityConfig();
        } else {
            showToast('更新失败: ' + (data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('更新失败: ' + e.message, 'error');
    }
}

async function deleteCapability(capabilityType, capabilityId) {
    if (!confirm('确定要删除该能力配置吗？')) return;

    try {
        const data = await apiRequest(`/api/capabilities?capability_type=${capabilityType}&capability_id=${capabilityId}`, {
            method: 'DELETE',
            errorPrefix: '删除失败'
        });
        if (data.success) {
            showToast('能力删除成功', 'success');
            loadCapabilityConfig();
        } else {
            showToast('删除失败: ' + (data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

function handleDragStart(event) {
    draggedElement = event.target.closest('.model-item');
    if (!draggedElement) return;
    
    draggedElement.style.opacity = '0.5';
    draggedElement.style.transform = 'scale(1.02)';
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', draggedElement.dataset.id);
}

function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    
    const target = event.target.closest('.model-item');
    if (target && target !== draggedElement) {
        target.style.borderTop = '3px dashed var(--primary-color)';
    }
}

async function handleDrop(event) {
    event.preventDefault();
    
    const target = event.target.closest('.model-item');
    if (!target || !draggedElement) {
        handleDragEnd();
        return;
    }
    
    target.style.borderTop = '';
    
    if (target === draggedElement) {
        handleDragEnd();
        return;
    }

    const capabilityType = draggedElement.dataset.type;
    const list = document.getElementById(`capability-list-${capabilityType}`);
    if (!list) {
        handleDragEnd();
        return;
    }

    const items = Array.from(list.querySelectorAll('.model-item'));
    const draggedId = draggedElement.dataset.id;
    const targetId = target.dataset.id;

    const draggedIndex = items.findIndex(item => item.dataset.id === draggedId);
    const targetIndex = items.findIndex(item => item.dataset.id === targetId);

    if (draggedIndex === -1 || targetIndex === -1) {
        handleDragEnd();
        return;
    }

    if (draggedIndex < targetIndex) {
        list.insertBefore(draggedElement, target.nextSibling);
    } else {
        list.insertBefore(draggedElement, target);
    }

    const capabilityIds = Array.from(list.querySelectorAll('.model-item')).map(item => item.dataset.id);

    try {
        await apiRequest('/api/capabilities/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ capability_type: capabilityType, capability_ids: capabilityIds }),
            errorPrefix: '保存排序失败'
        });
    } catch (e) {
        console.error('保存排序失败:', e);
        showToast('保存排序失败', 'error');
    }

    handleDragEnd();
}

function handleDragEnd() {
    if (draggedElement) {
        draggedElement.style.opacity = '';
        draggedElement.style.transform = '';
        draggedElement.style.transition = '';
    }
    
    document.querySelectorAll('.model-item').forEach(item => {
        item.style.borderTop = '';
        item.style.transition = '';
    });
    
    draggedElement = null;
}

async function loadSettings() {
    await loadSettingsNav();
}

// ===================== 调用点模型配置 =====================

async function loadCallPointConfig() {
    const content = document.getElementById('settingsContent');
    if (!content) return;

    try {
        const cpData = await apiRequest('/api/capabilities/call-points', { silent: true });
        const categories = cpData.categories || [];
        const availableCaps = cpData.available_capabilities || [];

        // 缓存分类数据和能力选项
        _callPointCategoriesData = categories;
        _callPointCapOptions = availableCaps.map(cap => {
            const label = `${cap.platform_code} / ${cap.model_code}` + (cap.description && cap.description !== cap.model_code ? ` (${cap.description})` : '');
            return `<option value="${cap.id}">${label}</option>`;
        }).join('');

        // 默认选中第一个分类
        if (categories.length > 0 && !currentCallPointCategory) {
            currentCallPointCategory = categories[0].category;
        }

        // 分类 Tab 按钮
        let tabsHtml = '<nav class="nav nav-tabs mb-4" id="callPointCatNav">';
        categories.forEach(cat => {
            const activeClass = cat.category === currentCallPointCategory ? 'active' : '';
            const configuredCount = cat.call_points.filter(cp => cp.capability_id).length;
            tabsHtml += `
                <button class="nav-link ${activeClass}" onclick="switchCallPointCategory('${cat.category}')"
                        style="display: flex; align-items: center; gap: 8px; padding: 10px 20px; font-weight: 600;">
                    <i class="${cat.icon}" style="color: ${cat.color};"></i>
                    <span>${cat.category}</span>
                    ${configuredCount > 0 ? `<span class="badge" style="font-size: 9px; background: rgba(245, 158, 11, 0.15); color: #d97706;">${configuredCount}</span>` : ''}
                </button>
            `;
        });
        tabsHtml += '</nav>';

        // 说明卡片 + 保存按钮 + 分类内容容器
        let html = `
            <div class="card mb-4" style="border-radius: 12px;">
                <div class="card-body">
                    <p style="font-size: 13px; color: var(--neu-text-muted); margin: 0;">
                        <i class="fas fa-info-circle"></i>
                        为不同的调用点分配已配置的模型能力。未配置的调用点将使用“模型能力”中优先级最高的默认模型。
                        配置后，指定调用点的 LLM 调用将优先使用所选能力，失败时自动回退到默认模型。
                    </p>
                </div>
            </div>
            ${tabsHtml}
            <div class="card" style="border-radius: 12px;">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 600;" id="callPointCatTitle"></span>
                    <button class="btn btn-sm btn-primary" onclick="saveCallPointConfig()">
                        <i class="fas fa-save"></i> 保存配置
                    </button>
                </div>
                <div class="card-body">
                    <div class="model-list" id="callPointList"></div>
        `;

        if (availableCaps.length === 0) {
            html += `
                    <div class="alert alert-warning" style="margin: 16px; font-size: 13px;">
                        <i class="fas fa-exclamation-triangle"></i>
                        暂无已启用的文本预测能力配置。请先在“模型能力”页面添加并启用至少一个能力。
                    </div>
            `;
        }

        html += `
                </div>
            </div>
        `;

        content.innerHTML = html;

        // 渲染当前分类的调用点
        renderCallPointCategory(currentCallPointCategory);
    } catch (e) {
        content.innerHTML = '<div class="text-center text-danger">加载调用点配置失败</div>';
        console.error('loadCallPointConfig error:', e);
    }
}

function switchCallPointCategory(category) {
    currentCallPointCategory = category;
    // 更新 Tab 激活状态
    const tabs = document.querySelectorAll('#callPointCatNav .nav-link');
    tabs.forEach(tab => {
        tab.classList.toggle('active', tab.textContent.trim().startsWith(category));
    });
    renderCallPointCategory(category);
}

function renderCallPointCategory(category) {
    const listEl = document.getElementById('callPointList');
    const titleEl = document.getElementById('callPointCatTitle');
    if (!listEl || !_callPointCategoriesData) return;

    const catData = _callPointCategoriesData.find(c => c.category === category);
    if (!catData) return;

    if (titleEl) {
        titleEl.innerHTML = `<i class="${catData.icon}" style="color: ${catData.color};"></i> ${catData.category} · 调用点模型分配`;
    }

    const capOptions = _callPointCapOptions;
    let html = '';

    catData.call_points.forEach(cp => {
        const hasOverride = !!cp.capability_id;
        const itemShadow = hasOverride ? 'var(--neu-shadow-inset)' : 'var(--neu-shadow-small)';
        const overrideBadge = hasOverride
            ? `<span class="badge" style="font-size: 9px; background: rgba(245, 158, 11, 0.15); color: #d97706; margin-left: 4px;">已配置</span>`
            : `<span class="badge" style="font-size: 9px; background: rgba(0,0,0,0.05); color: var(--neu-text-muted);">默认</span>`;
        html += `
            <div class="model-item" id="cp-row-${cp.name}" style="box-shadow: ${itemShadow}; gap: 12px;">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 600; font-size: 14px; color: var(--neu-text); display: flex; align-items: center; margin-bottom: 4px;">
                        ${cp.display_name} ${overrideBadge}
                    </div>
                    <div style="font-size: 12px; color: var(--neu-text-muted);">${cp.description}</div>
                </div>
                <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
                    <select class="form-select form-select-sm cp-capability-select" id="cp-cap-${cp.name}" 
                            onchange="updateCallPointItemStyle('${cp.name}')"
                            style="font-size: 13px; border-radius: 10px; border: none; background: var(--neu-bg); box-shadow: var(--neu-shadow-inset); min-width: 260px;">
                        <option value="">使用默认模型</option>
                        ${capOptions}
                    </select>
                    <button class="btn btn-sm btn-outline-secondary" onclick="resetCallPoint('${cp.name}')" 
                            title="重置为默认模型"
                            style="font-size: 12px; padding: 4px 10px; border-radius: 8px;">
                        <i class="fas fa-undo"></i>
                    </button>
                </div>
            </div>
        `;
    });

    listEl.innerHTML = html;

    // 回填已配置的能力
    catData.call_points.forEach(cp => {
        if (cp.capability_id) {
            const capSelect = document.getElementById(`cp-cap-${cp.name}`);
            if (capSelect) capSelect.value = cp.capability_id;
        }
    });
}

function updateCallPointItemStyle(callPointName) {
    const capId = document.getElementById(`cp-cap-${callPointName}`)?.value || '';
    const item = document.getElementById(`cp-row-${callPointName}`);
    if (!item) return;

    const hasOverride = !!capId;
    item.style.boxShadow = hasOverride ? 'var(--neu-shadow-inset)' : 'var(--neu-shadow-small)';

    // 更新 badge
    const badge = item.querySelector('.badge');
    if (badge) {
        if (hasOverride) {
            badge.textContent = '已配置';
            badge.style.background = 'rgba(245, 158, 11, 0.15)';
            badge.style.color = '#d97706';
        } else {
            badge.textContent = '默认';
            badge.style.background = 'rgba(0,0,0,0.05)';
            badge.style.color = 'var(--neu-text-muted)';
        }
    }
}

function resetCallPoint(callPointName) {
    const capSelect = document.getElementById(`cp-cap-${callPointName}`);
    if (capSelect) capSelect.value = '';
    updateCallPointItemStyle(callPointName);
}

async function saveCallPointConfig() {
    // 收集当前显示的分类下所有调用点的配置
    // 后端 update_call_point_models 是 merge 操作，不会影响其他分类的已有配置
    const configs = {};
    const rows = document.querySelectorAll('#callPointList [id^="cp-row-"]');

    rows.forEach(row => {
        const cpName = row.id.replace('cp-row-', '');
        const capId = document.getElementById(`cp-cap-${cpName}`)?.value || '';
        if (capId) {
            configs[cpName] = { capability_id: capId };
        } else {
            configs[cpName] = { capability_id: '' };
        }
    });

    try {
        const data = await apiRequest('/api/capabilities/call-points', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ configs }),
            errorPrefix: '保存失败'
        });
        if (data.success) {
            showToast('调用点配置保存成功', 'success');
        } else {
            showToast('保存失败: ' + (data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}