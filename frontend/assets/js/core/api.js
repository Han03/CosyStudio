/**
 * 统一 API 请求封装 & Toast 提示
 * 提供 apiRequest() 自动检查 HTTP 状态码并弹出错误提示
 * 提供 showToast() 全局统一的 Toast 通知
 */

// ─── Toast 通知 ───────────────────────────────────────────────

/**
 * 获取或创建全局 toast 容器，多个 toast 自动纵向堆叠、不会重叠。
 */
function _getToastContainer() {
    var container = document.getElementById('toastContainer');
    if (container) return container;
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.style.cssText = [
        'position:fixed', 'top:20px', 'right:20px', 'z-index:99999',
        'display:flex', 'flex-direction:column', 'gap:10px',
        'pointer-events:none', 'max-width:420px'
    ].join(';');
    document.body.appendChild(container);
    return container;
}

function showToast(message, type) {
    if (typeof message !== 'string') {
        try { message = String(message); } catch (_) { message = '未知错误'; }
    }
    type = type || 'info';

    var bgColors = { success: '#10b981', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
    var icons    = { success: 'fa-check-circle', error: 'fa-exclamation-circle', warning: 'fa-exclamation-triangle', info: 'fa-info-circle' };

    var container = _getToastContainer();

    var toast = document.createElement('div');
    toast.style.cssText = [
        'padding:12px 20px', 'border-radius:10px', 'color:#fff',
        'font-size:14px', 'min-width:220px', 'max-width:420px',
        'box-shadow:0 4px 16px rgba(0,0,0,0.18)',
        'display:flex', 'align-items:center', 'gap:8px',
        'opacity:0', 'transform:translateX(20px)',
        'transition:opacity 0.3s,transform 0.3s',
        'background:' + (bgColors[type] || bgColors.info),
        'word-break:break-word', 'pointer-events:auto'
    ].join(';');
    toast.innerHTML = '<i class="fas ' + (icons[type] || icons.info) + '"></i><span>' + message + '</span>';

    container.appendChild(toast);
    // 触发动画
    requestAnimationFrame(function () {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(0)';
    });
    setTimeout(function () {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(function () { toast.remove(); }, 300);
    }, 5000);
}

// 便捷别名
function showError(msg)   { showToast(msg, 'error'); }
function showSuccess(msg) { showToast(msg, 'success'); }

// ─── API 请求封装 ─────────────────────────────────────────────

/**
 * 统一 API 请求，自动处理 HTTP 错误并弹出 Toast 提示。
 *
 * @param {string} url     - 请求地址
 * @param {object} [options]
 * @param {string} [options.method]    - HTTP 方法，默认 GET
 * @param {object} [options.headers]   - 请求头
 * @param {*}      [options.body]      - 请求体
 * @param {boolean} [options.silent]   - true 时不自动弹错误 Toast（由调用方自行处理）
 * @param {string}  [options.errorPrefix] - 错误提示前缀，如 "保存失败"
 * @returns {Promise<object>} 解析后的 JSON 数据
 */
async function apiRequest(url, options) {
    options = options || {};
    var silent     = options.silent || false;
    var errorPrefix = options.errorPrefix || '';
    var fetchOpts  = {
        method:  options.method || 'GET',
        headers: options.headers || {},
    };
    if (options.body !== undefined) {
        fetchOpts.body = options.body;
    }

    var response;
    try {
        response = await fetch(url, fetchOpts);
    } catch (networkErr) {
        var netMsg = (errorPrefix ? errorPrefix + ': ' : '') + '网络请求失败，请检查服务是否启动';
        if (!silent) showToast(netMsg, 'error');
        throw new Error(netMsg);
    }

    if (!response.ok) {
        var errorMsg = await _parseHttpError(response);
        var fullMsg  = errorPrefix
            ? errorPrefix + ': ' + errorMsg
            : errorMsg;
        if (!silent) showToast(fullMsg, 'error');
        var err = new Error(fullMsg);
        err.status = response.status;
        throw err;
    }

    // 204 No Content 或空响应
    var text = await response.text();
    if (!text) return {};
    try {
        return JSON.parse(text);
    } catch (_) {
        return {};
    }
}

/**
 * 从 HTTP 错误响应中提取可读的错误信息。
 * 兼容后端 FastAPI 的 {"detail": ...} 格式以及 {"success":false,"message":"..."} 格式。
 */
async function _parseHttpError(response) {
    try {
        var text = await response.text();
        if (!text) return 'HTTP ' + response.status;
        var data;
        try { data = JSON.parse(text); } catch (_) { return text.substring(0, 200); }

        // FastAPI HTTPException → {"detail": "..."}
        if (data.detail !== undefined) {
            if (typeof data.detail === 'string') return data.detail;
            if (Array.isArray(data.detail)) return data.detail.map(function (e) { return e.msg || JSON.stringify(e); }).join('; ');
            return JSON.stringify(data.detail);
        }
        // 业务错误 → {"success": false, "message": "..."}
        if (data.message) return data.message;
        if (data.error)   return data.error;
        return JSON.stringify(data).substring(0, 200);
    } catch (_) {
        return 'HTTP ' + response.status;
    }
}
