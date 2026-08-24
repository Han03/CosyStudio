let API_BASE_URL = window.location.origin;

async function initApiBaseUrl() {
    try {
        const resp = await fetch(`${window.location.origin}/api/server-info`);
        const data = await resp.json();
        if (data && data.base_url) {
            API_BASE_URL = data.base_url;
            console.log('[API] 动态获取服务器地址:', API_BASE_URL);
        }
    } catch (e) {
        console.log('[API] 使用默认地址:', API_BASE_URL);
    }
}

// 模型分类静态映射，与后端 MODEL_CATEGORIES 保持一致
const MODEL_CATEGORIES = {
    'cosyvoice': 'CosyVoice',
    'qwen': 'Qwen',
    'dreamlite': 'DreamLite',
    'qwen_embedding': 'Qwen3-Embedding',
};
window.MODEL_CATEGORIES = MODEL_CATEGORIES;

function setupUploadArea(areaId, inputId, displayId) {
    const area = document.getElementById(areaId);
    const input = document.getElementById(inputId);
    const display = document.getElementById(displayId);
    if (!area || !input) return;

    area.onclick = () => input.click();
    area.ondragover = (e) => { e.preventDefault(); area.classList.add('dragover'); };
    area.ondragleave = () => area.classList.remove('dragover');
    area.ondrop = (e) => {
        e.preventDefault();
        area.classList.remove('dragover');
        input.files = e.dataTransfer.files;
        showFileName(displayId, e.dataTransfer.files[0].name);
    };
    input.onchange = () => showFileName(displayId, input.files[0]?.name);
}

function showFileName(displayId, name) {
    const el = document.getElementById(displayId);
    if (!el) return;
    el.innerHTML = name ? `<span class="badge bg-success"><i class="fas fa-check"></i> ${name}</span>` : '';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// showToast 已由 api.js 统一提供，此处不再重复定义

function formatFileSize(bytes) {
    if (!bytes || bytes < 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}