let loadingProgressInterval = null;
let modelListCache = [];
let currentModelFilter = 'qwen';
let currentConfig = {};

function setCategoryButtonLoading(category, loading, statusText) {
    const btnId = `loadBtn-${category}`;
    const btn = document.getElementById(btnId);
    if (!btn) return;
    if (loading) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + (statusText || '加载中...');
    } else {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-upload"></i> 加载模型';
    }
}

function loadSingleModel(category) {
    const bodyMap = {
        'qwen': (p) => ({ qwen_model_path: p }),
        'cosyvoice': (p) => ({ cosyvoice_model_path: p }),
        'qwen_omni': (p) => ({ qwen_omni_model_path: p }),
        'dreamlite': (p) => ({ dreamlite_model_path: p }),
        'qwen_embedding': (p) => ({ qwen_embedding_model_path: p })
    };

    const modelPath = currentConfig.models && currentConfig.models[category] 
        ? currentConfig.models[category].model_path 
        : '';

    if (!modelPath) {
        alert('请先在模型管理页面选择模型');
        switchTab('models');
        return;
    }

    setCategoryButtonLoading(category, true, '加载中...');

    apiRequest(`${API_BASE_URL}/api/models/load-async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyMap[category](modelPath)),
        errorPrefix: '启动加载失败'
    })
        .then(result => {
            if (result.success) {
                startLoadingProgressPolling(category);
            } else {
                showToast('启动加载失败: ' + (result.error || ''), 'error');
                setCategoryButtonLoading(category, false);
            }
        })
        .catch(e => {
            setCategoryButtonLoading(category, false);
        });
}

function startLoadingProgressPolling(activeCategory) {
    if (loadingProgressInterval) {
        clearInterval(loadingProgressInterval);
    }

    loadingProgressInterval = setInterval(() => {
        fetch(`${API_BASE_URL}/api/models/loading-status`)
            .then(r => r.json())
            .then(status => {
                const cat = status[activeCategory];
                if (!cat) return;

                if (cat.status === 'loading') {
                    setCategoryButtonLoading(activeCategory, true, cat.message || '加载中...');
                }

                if (cat.status === 'loaded' || cat.status === 'error') {
                    clearInterval(loadingProgressInterval);
                    loadingProgressInterval = null;
                    setCategoryButtonLoading(activeCategory, false);

                    if (cat.status === 'loaded') {
                        alert('模型加载完成！');
                    } else if (cat.status === 'error') {
                        alert('模型加载失败: ' + (cat.error || cat.message || '未知错误'));
                    }
                }
            })
            .catch(e => {
                console.error('获取加载状态失败:', e);
                setCategoryButtonLoading(activeCategory, false);
            });
    }, 1000);
}

function loadModelsSync() {
    const cosyvoiceSelect = document.getElementById('cosyvoiceSelect');
    const qwenSelect = document.getElementById('qwenSelect');

    const cosyvoicePath = cosyvoiceSelect.value;
    const qwenPath = qwenSelect.value;

    if (!cosyvoicePath) {
        showToast('请选择CosyVoice模型', 'warning');
        return;
    }

    apiRequest(`${API_BASE_URL}/api/resources/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        errorPrefix: '资源检查失败'
    })
        .then(checkResult => {
            if (!checkResult.can_proceed) {
                const confirmLoad = confirm(`资源状态异常！\n\n${checkResult.message}\n\n检测到的问题：\n${checkResult.issues.join('\n')}\n\n仍要继续加载模型吗？`);
                if (!confirmLoad) {
                    return;
                }
            }

            apiRequest(`${API_BASE_URL}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cosyvoice_model_path: cosyvoicePath,
                    qwen_model_path: qwenPath
                }),
                errorPrefix: '加载失败'
            })
                .then(data => {
                    showToast(data.message || '操作完成', 'info');
                    refreshResources();
                });
        });
}

function refreshModelList() {
    Promise.all([
        apiRequest(`${API_BASE_URL}/api/models/list`, { silent: true }),
        apiRequest(`${API_BASE_URL}/api/settings`, { silent: true })
    ])
    .then(([modelsData, configData]) => {
        modelListCache = modelsData.models || [];
        currentConfig = configData.config || {};
        const statusOrder = { 'downloading': 0, 'canceled': 1, 'error': 2, 'ready': 3 };
        modelListCache.sort((a, b) => {
            const orderA = statusOrder[a.status] !== undefined ? statusOrder[a.status] : 4;
            const orderB = statusOrder[b.status] !== undefined ? statusOrder[b.status] : 4;
            return orderA - orderB;
        });
        renderFilteredModels();
    })
    .catch(e => {
        console.error('加载模型列表失败:', e);
        showToast('加载模型列表失败', 'error');
        const container = document.getElementById('modelListContainer');
        if (container) {
            container.innerHTML = '<div class="model-list-empty"><i class="fas fa-box"></i><p>加载失败，请检查控制台</p></div>';
        }
    });
}

function filterModels(category) {
    currentModelFilter = category;
    document.querySelectorAll('#modelCategoryFilters .btn').forEach(btn => {
        btn.classList.remove('active', 'btn-outline-primary');
        btn.classList.add('btn-outline-secondary');
    });
    const activeBtn = document.querySelector(`#modelCategoryFilters .btn[data-category="${category}"]`);
    if (activeBtn) {
        activeBtn.classList.remove('btn-outline-secondary');
        activeBtn.classList.add('active', 'btn-outline-primary');
    }
    renderFilteredModels();
}

function isModelSelected(category, modelPath) {
    if (!currentConfig.models || !currentConfig.models[category]) return false;
    const selectedPath = currentConfig.models[category].model_path || '';
    
    const normalizePath = (path) => {
        return path.toLowerCase().replace(/\\/g, '/').replace(/\/+/g, '/');
    };
    
    return normalizePath(selectedPath) === normalizePath(modelPath);
}

function selectModelRadio(category, modelPath, modelName) {
    document.querySelectorAll(`input[name="model-select-${category}"]`).forEach(input => {
        input.checked = false;
    });
    const targetInput = document.querySelector(`input[name="model-select-${category}"][value="${encodeURIComponent(modelPath)}"]`);
    if (targetInput) {
        targetInput.checked = true;
    }
    apiRequest(`${API_BASE_URL}/api/models_select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, model_path: modelPath, model_name: modelName }),
        errorPrefix: '选择模型失败'
    })
    .then(data => {
        if (data.success) {
            console.log('模型选择成功:', data.message);
            if (!currentConfig.models) currentConfig.models = {};
            if (!currentConfig.models[category]) currentConfig.models[category] = {};
            currentConfig.models[category].model_path = modelPath;
            currentConfig.models[category].model_name = modelName;
        } else {
            showToast('选择模型失败: ' + (data.error || ''), 'error');
        }
    })
    .catch(e => console.error('选择模型失败:', e));
}

function saveCategoryParams(btn) {
    const category = btn.closest('.card').dataset.category;
    if (!category) return;

    const params = {};
    const inputs = btn.closest('.card').querySelectorAll('input, select');
    inputs.forEach(input => {
        const paramKey = input.dataset.paramKey;
        if (!paramKey) return;

        if (input.type === 'number') {
            const val = parseFloat(input.value);
            if (!isNaN(val)) params[paramKey] = val;
        } else if (input.type === 'checkbox') {
            params[paramKey] = input.checked;
        } else if (input.tagName === 'SELECT') {
            params[paramKey] = input.value === 'true' ? true : input.value === 'false' ? false : input.value;
        } else {
            params[paramKey] = input.value;
        }
    });

    apiRequest(`${API_BASE_URL}/api/models/params`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, params }),
        errorPrefix: '保存参数失败'
    })
    .then(data => {
        if (data.success) {
            showToast('参数保存成功', 'success');
        } else {
            showToast('保存失败: ' + (data.error || ''), 'error');
        }
    })
    .catch(e => console.error('保存参数失败:', e));
}

function renderFilteredModels() {
    const container = document.getElementById('modelListContainer');
    if (!container) return;

    let filteredModels = modelListCache.filter(m => m.category === currentModelFilter);

    if (filteredModels.length === 0) {
        container.innerHTML = `
            <div class="model-list-empty">
                <i class="fas fa-box"></i>
                <p>暂无模型</p>
            </div>
        `;
        return;
    }

    let html = '';
    html += '<div class="model-list">';
    html += filteredModels.map(model => {
        let statusHtml = '';
        let progressBarHtml = '';
        if (model.status === 'downloading') {
            const progress = model.download_progress || 0;
            statusHtml = `<span class="badge bg-warning"><i class="fas fa-spinner fa-spin"></i> 下载中</span>`;
            progressBarHtml = `
                <div class="model-download-progress">
                    <div class="model-download-progress-bar" style="width: ${progress}%"></div>
                </div>
            `;
        } else if (model.status === 'error') {
            statusHtml = `<span class="badge bg-danger"><i class="fas fa-exclamation-triangle"></i> 错误</span>`;
        } else if (model.status === 'canceled') {
            statusHtml = `<span class="badge bg-secondary"><i class="fas fa-ban"></i> 已取消</span>`;
        } else {
            statusHtml = `<span class="badge bg-success"><i class="fas fa-check"></i> 就绪</span>`;
        }

        let actionBtn = '';
        if (model.status === 'downloading') {
            actionBtn = `
            <button class="btn btn-warning btn-sm" onclick='cancelModelDownload()'>
                <i class="fas fa-times"></i> 取消下载
            </button>`;
        } else if (model.status === 'canceled' || model.status === 'error') {
            actionBtn = `
            <button class="btn btn-primary btn-sm" onclick='resumeModelDownload(${JSON.stringify(model.name)}, ${JSON.stringify(model.category)})'>
                <i class="fas fa-download"></i> 继续下载
            </button>
            <button class="btn btn-danger btn-sm" onclick='deleteModel(${JSON.stringify(model.path)})'>
                <i class="fas fa-trash"></i> 删除
            </button>`;
        } else {
            actionBtn = `
            <button class="btn btn-danger btn-sm" onclick='deleteModel(${JSON.stringify(model.path)})'>
                <i class="fas fa-trash"></i> 删除
            </button>`;
        }

        const isSelected = isModelSelected(model.category, model.path);
        const canSelect = model.status === 'ready';
        const selectHtml = canSelect ? `
            <label class="form-check-label model-select-label" style="margin-right: 12px;">
                <input type="radio" name="model-select-${model.category}" 
                    class="form-check-input"
                    value="${encodeURIComponent(model.path)}"
                    ${isSelected ? 'checked' : ''}
                    onclick="selectModelRadio('${model.category}', '${model.path.replace(/'/g, "\\'").replace(/\\/g, "\\\\")}', '${model.name.replace(/'/g, "\\'")}')">
            </label>
        ` : '';

        return `
            <div class="model-item">
                <div class="model-item-info" style="display: flex; align-items: flex-start; gap: 12px;">
                    ${selectHtml}
                    <div style="flex: 1;">
                        <div class="model-item-name">
                            ${model.name}
                            ${statusHtml}
                        </div>
                        ${model.description ? `<div class="model-item-desc">${model.description}</div>` : ''}
                        ${progressBarHtml}
                        <div class="model-item-meta" style="margin-top: ${progressBarHtml ? '10px' : '8px'};">
                            <span class="model-meta-item">
                                <i class="fas fa-folder"></i>
                                分类: <strong>${model.category_name}</strong>
                            </span>
                            <span class="model-meta-item">
                                <i class="fas fa-weight-hanging"></i>
                                大小: <strong>${model.size}</strong>
                            </span>
                            <span class="model-meta-item">
                                <i class="fas fa-file"></i>
                                文件: <strong>${model.file_count}</strong>
                            </span>
                        </div>
                    </div>
                </div>
                <div class="model-item-actions">
                    ${actionBtn}
                </div>
            </div>
        `;
    }).join('');
    html += '</div>';
    container.innerHTML = html;
}

function closeImportModal() {
    const modal = bootstrap.Modal.getInstance(document.getElementById('importModal'));
    if (modal) {
        modal.hide();
    }
}

function selectImportFolder() {
    document.getElementById('importFolderInput').click();
}

function handleFolderSelect(input) {
    if (input.files && input.files.length > 0) {
        const filePath = input.files[0].webkitRelativePath || input.files[0].path;
        const folderPath = filePath.substring(0, filePath.indexOf('/'));
        document.getElementById('importSourcePath').value = folderPath;
    }
}

async function startModelImport() {
    const btn = document.getElementById('startImportBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导入中...';

    const category = document.getElementById('importCategory').value;
    const name = document.getElementById('importName').value.trim();
    const description = document.getElementById('importDescription').value.trim();
    const usePath = document.getElementById('importByPath').checked;
    const sourcePath = document.getElementById('importSourcePath').value.trim();
    const fileInput = document.getElementById('importFile');

    try {
        if (usePath) {
            if (!sourcePath) {
                alert('请选择源路径');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-upload"></i> 开始导入';
                return;
            }

            const data = await apiRequest(`${API_BASE_URL}/api/models/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({
                    category: category,
                    name: name,
                    description: description,
                    source_path: sourcePath
                }),
                errorPrefix: '导入失败'
            });

            if (data.success) {
                showToast('导入成功！', 'success');
                refreshModelList();
                closeImportModal();
            } else {
                showToast('导入失败: ' + (data.error || ''), 'error');
            }
        } else {
            if (!fileInput.files || fileInput.files.length === 0) {
                alert('请选择文件');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-upload"></i> 开始导入';
                return;
            }

            const formData = new FormData();
            formData.append('category', category);
            formData.append('name', name);
            formData.append('description', description);
            formData.append('file', fileInput.files[0]);

            const data = await apiRequest(`${API_BASE_URL}/api/models/import`, {
                method: 'POST',
                body: formData,
                errorPrefix: '导入失败'
            });

            if (data.success) {
                showToast('导入成功！', 'success');
                refreshModelList();
                closeImportModal();
            } else {
                showToast('导入失败: ' + (data.error || ''), 'error');
            }
        }
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-upload"></i> 开始导入';
    }
}

async function deleteModel(path) {
    if (!confirm('确定要删除这个模型吗？此操作不可撤销！')) {
        return;
    }

    try {
        const data = await apiRequest(`${API_BASE_URL}/api/models/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
            errorPrefix: '删除失败'
        });

        if (data.success) {
            showToast('删除成功！', 'success');
            refreshModelList();
        } else {
            showToast('删除失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        // apiRequest 已自动弹出错误提示
    }
}

function resumeModelDownload(modelName, category) {
    startModelDownload(modelName, category);
}

function cancelModelDownload() {
    if (!confirm('确定要取消当前下载吗？')) {
        return;
    }

    apiRequest(`${API_BASE_URL}/api/models/download/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        errorPrefix: '取消下载失败'
    })
    .then(data => {
        if (data.success) {
            showToast('下载已取消', 'info');
            refreshModelList();
        } else {
            showToast('取消失败: ' + (data.error || ''), 'error');
        }
    })
    .catch(e => console.error('取消下载失败:', e));
}

function startModelDownload(modelName, category) {
    const modal = bootstrap.Modal.getInstance(document.getElementById('downloadModelModal'));
    if (modal) {
        modal.hide();
    }

    apiRequest(`${API_BASE_URL}/api/models/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName, category }),
        errorPrefix: '下载失败'
    })
    .then(data => {
        if (data.success) {
            showToast('下载已开始，请在模型列表中查看进度', 'success');
            refreshModelList();
        } else {
            showToast('下载失败: ' + (data.error || ''), 'error');
        }
    })
    .catch(e => console.error('下载失败:', e));
}

function openDownloadModal(modelName, category) {
    const existingModal = document.getElementById('downloadModelModal');
    if (existingModal) {
        existingModal.remove();
    }

    const modalHtml = `
        <div class="modal fade" id="downloadModelModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-download"></i> 确认下载</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>确定要下载模型 <strong>${modelName}</strong> 吗？</p>
                        <p class="text-muted" style="font-size: 12px;">下载可能需要较长时间，请确保网络连接稳定。</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="startModelDownload('${modelName}', '${category}')">确认下载</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    new bootstrap.Modal(document.getElementById('downloadModelModal')).show();
}

async function showDownloadModal() {
    const existingModal = document.getElementById('downloadModelModal');
    if (existingModal) {
        existingModal.remove();
    }

    const modalHtml = `
        <div class="modal fade" id="downloadModelModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-download"></i> 下载模型</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">模型分类</label>
                            <select class="form-select" id="downloadCategory">
                                <option value="">请选择分类</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">下载源</label>
                            <div class="btn-group w-100" role="group">
                                <input type="radio" class="btn-check" name="downloadSource" id="sourceModelscope" value="modelscope" checked onchange="updateModelIdPlaceholder()">
                                <label class="btn btn-outline-primary" for="sourceModelscope"><i class="fas fa-cloud"></i> ModelScope</label>
                                <input type="radio" class="btn-check" name="downloadSource" id="sourceHuggingface" value="huggingface" onchange="updateModelIdPlaceholder()">
                                <label class="btn btn-outline-primary" for="sourceHuggingface"><i class="fas fa-cubes"></i> HuggingFace</label>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">模型 ID</label>
                            <input type="text" class="form-control" id="downloadModelId" placeholder="例如: iic/CosyVoice2-0.5B">
                            <div class="form-text">输入完整的模型仓库 ID，格式为 <code>组织/模型名</code></div>
                        </div>
                        <div class="alert alert-info mb-0" style="font-size: 12px;">
                            <i class="fas fa-info-circle"></i> 下载可能需要较长时间，请确保网络连接稳定。HuggingFace 源可能需要代理。
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="confirmModelDownload()">开始下载</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    const categorySelect = document.getElementById('downloadCategory');
    Object.entries(MODEL_CATEGORIES).forEach(([key, name]) => {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = name;
        categorySelect.appendChild(option);
    });

    new bootstrap.Modal(document.getElementById('downloadModelModal')).show();
}

function updateModelIdPlaceholder() {
    const source = document.querySelector('input[name="downloadSource"]:checked').value;
    const input = document.getElementById('downloadModelId');
    if (source === 'huggingface') {
        input.placeholder = '例如: Qwen/Qwen3-Embedding-0.6B';
    } else {
        input.placeholder = '例如: iic/CosyVoice2-0.5B';
    }
}

function confirmModelDownload() {
    const category = document.getElementById('downloadCategory').value;
    const modelId = document.getElementById('downloadModelId').value.trim();
    const source = document.querySelector('input[name="downloadSource"]:checked').value;
    
    if (!category) {
        alert('请选择模型分类');
        return;
    }
    if (!modelId) {
        alert('请输入模型 ID');
        return;
    }
    if (!/^[^\/]+\/[^\/]+$/.test(modelId)) {
        alert('模型 ID 格式不正确，应为 组织/模型名');
        return;
    }

    const modal = bootstrap.Modal.getInstance(document.getElementById('downloadModelModal'));
    if (modal) {
        modal.hide();
    }

    apiRequest(`${API_BASE_URL}/api/models/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelId, category, source }),
        errorPrefix: '下载失败'
    })
    .then(data => {
        if (data.success) {
            showToast('下载已开始，请在模型列表中查看进度', 'success');
            refreshModelList();
        } else {
            showToast('下载失败: ' + (data.error || ''), 'error');
        }
    })
    .catch(e => console.error('下载失败:', e));
}

function showImportModal() {
    new bootstrap.Modal(document.getElementById('importModal')).show();
}