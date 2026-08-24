let mediaCategories = [];
let currentMediaCategory = null;
let currentMediaPage = 1;
let currentMediaPageSize = 24;
let currentMediaKeyword = null;

async function loadMediaCategories() {
    try {
        const data = await apiRequest(`/api/media/categories`, { silent: true });
        if (data.success) {
            mediaCategories = data.categories;
            renderMediaCategories();
            if (currentMediaCategory === null) {
                selectMediaCategory(null);
            } else {
                loadMediaFiles();
            }
        }
    } catch (e) {
        // 静默加载
    }
}

function renderMediaCategories() {
    const row = document.getElementById('mediaCategoriesRow');
    row.innerHTML = '';

    const allCount = mediaCategories.reduce((sum, c) => sum + c.count, 0);
    const allCard = document.createElement('div');
    allCard.className = 'col-md-2 col-4 mb-3';
    allCard.innerHTML = `
        <div class="media-category-card ${currentMediaCategory === null ? 'active' : ''}" onclick="selectMediaCategory(null)">
            <div class="media-category-icon">
                <i class="fas fa-th-large"></i>
            </div>
            <div class="media-category-info">
                <div class="media-category-name">全部</div>
                <div class="media-category-count">${allCount} 个文件</div>
            </div>
        </div>
    `;
    row.appendChild(allCard);

    mediaCategories.forEach(cat => {
        const col = document.createElement('div');
        col.className = 'col-md-2 col-4 mb-3';
        col.innerHTML = `
            <div class="media-category-card ${cat.key} ${currentMediaCategory === cat.key ? 'active' : ''}" onclick="selectMediaCategory('${cat.key}')">
                <div class="media-category-icon">
                    <i class="fas ${cat.icon}"></i>
                </div>
                <div class="media-category-info">
                    <div class="media-category-name">${cat.name}</div>
                    <div class="media-category-count">${cat.count} 个文件</div>
                </div>
            </div>
        `;
        row.appendChild(col);
    });
}

function selectMediaCategory(category) {
    currentMediaCategory = category;
    currentMediaPage = 1;
    currentMediaKeyword = null;
    document.getElementById('mediaSearchInput').value = '';
    renderMediaCategories();
    loadMediaFiles();
}

function handleMediaSearch(event) {
    if (event.key === 'Enter') {
        searchMediaFiles();
    }
}

function searchMediaFiles() {
    const keyword = document.getElementById('mediaSearchInput').value.trim();
    currentMediaKeyword = keyword || null;
    currentMediaPage = 1;
    loadMediaFiles();
}

function refreshMediaFiles() {
    loadMediaFiles();
}

async function loadMediaFiles() {
    const sortBy = document.getElementById('mediaSortBy').value;
    const sortOrder = document.getElementById('mediaSortOrder').value;

    let params = new URLSearchParams({
        page: currentMediaPage,
        page_size: currentMediaPageSize,
        sort_by: sortBy,
        sort_order: sortOrder
    });

    if (currentMediaCategory) {
        params.append('category', currentMediaCategory);
    }
    if (currentMediaKeyword) {
        params.append('keyword', currentMediaKeyword);
    }

    try {
        const data = await apiRequest(`/api/media/files?${params.toString()}`, { silent: true });
        if (data.success) {
            renderMediaFiles(data.files);
            renderMediaPagination(data.total, data.total_pages, data.page);
            document.getElementById('mediaFileCount').textContent = `共 ${data.total} 个文件`;

            const emptyState = document.getElementById('mediaEmptyState');
            const fileGrid = document.getElementById('mediaFileGrid');
            const pagination = document.getElementById('mediaPagination');

            if (data.files.length === 0) {
                emptyState.style.display = 'block';
                fileGrid.style.display = 'none';
                pagination.style.display = 'none';
            } else {
                emptyState.style.display = 'none';
                fileGrid.style.display = 'flex';
                pagination.style.display = data.total_pages > 1 ? 'block' : 'none';
            }
        }
    } catch (e) {
        // 静默加载
    }
}

function renderMediaFiles(files) {
    const grid = document.getElementById('mediaFileGrid');
    grid.innerHTML = '';

    files.forEach(file => {
        const col = document.createElement('div');
        col.className = 'col-lg-2 col-md-3 col-sm-4 col-6';

        let previewHtml = '';
        const iconClass = file.icon;
        
        if (file.category === 'image') {
            previewHtml = `<img src="/api/media/file/content?path=${encodeURIComponent(file.relative_path)}" alt="${file.name}" onerror="this.parentElement.innerHTML='<i class=\\'fas ${iconClass}\\'></i>'">`;
        } else {
            previewHtml = `<i class="fas ${iconClass}"></i>`;
        }

        col.innerHTML = `
            <div class="media-file-card" onclick="previewMediaFile('${file.relative_path.replace(/'/g, "\\'")}', '${file.name.replace(/'/g, "\\'")}', '${file.category}')">
                <div class="media-file-preview">
                    ${previewHtml}
                    <span class="media-file-badge">${file.extension.replace('.', '')}</span>
                </div>
                <div class="media-file-body">
                    <div class="media-file-name" title="${file.name}">${file.name}</div>
                    <div class="media-file-meta">
                        <span>${file.size_str}</span>
                    </div>
                </div>
                <div class="media-file-actions">
                    <button class="btn btn-outline-primary btn-sm" onclick="event.stopPropagation(); previewMediaFile('${file.relative_path.replace(/'/g, "\\'")}', '${file.name.replace(/'/g, "\\'")}', '${file.category}')">
                        <i class="fas fa-eye"></i> 预览
                    </button>
                    <button class="btn btn-outline-success btn-sm" onclick="event.stopPropagation(); downloadMediaFile('${file.relative_path.replace(/'/g, "\\'")}')">
                        <i class="fas fa-download"></i> 下载
                    </button>
                </div>
            </div>
        `;
        grid.appendChild(col);
    });
}

function renderMediaPagination(total, totalPages, currentPage) {
    const list = document.getElementById('mediaPaginationList');
    list.innerHTML = '';

    const addPageItem = (page, label, disabled = false, active = false) => {
        const li = document.createElement('li');
        li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="goToMediaPage(${page}); return false;">${label}</a>`;
        list.appendChild(li);
    };

    addPageItem(Math.max(1, currentPage - 1), '<i class="fas fa-chevron-left"></i>', currentPage === 1);

    const showPages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(showPages / 2));
    let endPage = Math.min(totalPages, startPage + showPages - 1);
    startPage = Math.max(1, endPage - showPages + 1);

    if (startPage > 1) {
        addPageItem(1, '1');
        if (startPage > 2) {
            const li = document.createElement('li');
            li.className = 'page-item disabled';
            li.innerHTML = '<span class="page-link">...</span>';
            list.appendChild(li);
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        addPageItem(i, i, false, i === currentPage);
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            const li = document.createElement('li');
            li.className = 'page-item disabled';
            li.innerHTML = '<span class="page-link">...</span>';
            list.appendChild(li);
        }
        addPageItem(totalPages, totalPages);
    }

    addPageItem(Math.min(totalPages, currentPage + 1), '<i class="fas fa-chevron-right"></i>', currentPage === totalPages);
}

function goToMediaPage(page) {
    currentMediaPage = page;
    loadMediaFiles();
}

function previewMediaFile(relativePath, fileName, category) {
    const url = `/api/media/file/content?path=${encodeURIComponent(relativePath)}`;
    
    if (category === 'image') {
        window.open(url, '_blank');
    } else if (category === 'note' || category === 'document') {
        if (fileName.endsWith('.txt') || fileName.endsWith('.md')) {
            fetch(url)
                .then(r => r.text())
                .then(text => {
                    const win = window.open('', '_blank');
                    win.document.write(`
                        <html>
                        <head><title>${fileName}</title>
                        <style>
                            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 30px; max-width: 800px; margin: 0 auto; line-height: 1.8; background: #f5f5f5; }
                            pre { white-space: pre-wrap; word-wrap: break-word; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
                        </style>
                        </head>
                        <body><h2>${fileName}</h2><pre>${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></body>
                        </html>
                    `);
                });
        } else {
            downloadMediaFile(relativePath);
        }
    } else if (category === 'audio') {
        const win = window.open('', '_blank');
        win.document.write(`
            <html>
            <head><title>${fileName}</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 40px; text-align: center; background: #f5f5f5; }
                audio { width: 100%; max-width: 500px; margin-top: 20px; }
            </style>
            </head>
            <body>
                <h2>${fileName}</h2>
                <audio controls autoplay>
                    <source src="${url}" type="audio/wav">
                    您的浏览器不支持音频播放。
                </audio>
            </body>
            </html>
        `);
    } else if (category === 'video') {
        const win = window.open('', '_blank');
        win.document.write(`
            <html>
            <head><title>${fileName}</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 40px; text-align: center; background: #000; margin: 0; }
                video { width: 100%; max-width: 800px; }
            </style>
            </head>
            <body>
                <video controls autoplay>
                    <source src="${url}" type="video/mp4">
                    您的浏览器不支持视频播放。
                </video>
            </body>
            </html>
        `);
    } else {
        downloadMediaFile(relativePath);
    }
}

function downloadMediaFile(relativePath) {
    const url = `/api/media/download?path=${encodeURIComponent(relativePath)}`;
    window.location.href = url;
}