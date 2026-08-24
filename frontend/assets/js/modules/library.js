let currentLibraryPage = 1;
const libraryPageSize = 12;
let currentLibraryKeyword = null;

function handleLibrarySearch(event) {
    if (event.key === 'Enter') {
        searchLibraryBooks();
    }
}

function searchLibraryBooks() {
    const keyword = document.getElementById('librarySearchInput').value.trim();
    currentLibraryKeyword = keyword || null;
    currentLibraryPage = 1;
    loadLibraryBooks();
}

async function loadLibraryBooks() {
    let params = new URLSearchParams({
        page: currentLibraryPage,
        page_size: libraryPageSize
    });
    if (currentLibraryKeyword) {
        params.append('keyword', currentLibraryKeyword);
    }

    try {
        const data = await apiRequest(`/api/books/library?${params.toString()}`, { silent: true });
        if (data.success) {
            renderLibraryBooks(data.books);
            renderLibraryPagination(data.total, data.total_pages, data.page);

            const emptyState = document.getElementById('libraryEmptyState');
            const grid = document.getElementById('libraryBookGrid');
            const pagination = document.getElementById('libraryPagination');

            if (data.books.length === 0) {
                emptyState.style.display = 'block';
                grid.style.display = 'none';
                pagination.style.display = 'none';
            } else {
                emptyState.style.display = 'none';
                grid.style.display = 'flex';
                pagination.style.display = data.total_pages > 1 ? 'block' : 'none';
            }
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    }
}

function renderLibraryBooks(books) {
    const grid = document.getElementById('libraryBookGrid');
    grid.innerHTML = '';

    books.forEach(book => {
        const col = document.createElement('div');
        col.className = 'col-lg-2 col-md-3 col-sm-4 col-6';

        const fileSizeStr = formatFileSize(book.file_size);
        const wordCountStr = book.word_count > 10000
                ? `${(book.word_count / 10000).toFixed(1)}万字`
                : `${book.word_count}字`;
        const chapterStr = `${book.chapter_count || 0}章`;
        const authorStr = book.author ? book.author : '佚名';
        const createdStr = book.created_at_str || '';

        col.innerHTML = `
            <div class="book-card">
                <div class="book-cover">
                    <i class="fas fa-book"></i>
                    <span class="book-format-badge">${book.format}</span>
                </div>
                <div class="book-body">
                    <div class="book-title" title="${escapeHtml(book.title)}">${escapeHtml(book.title)}</div>
                    <div class="book-author">${escapeHtml(authorStr)}</div>
                    <div class="book-meta">
                        <span><i class="fas fa-file-alt"></i> ${wordCountStr}</span>
                        <span><i class="fas fa-list"></i> ${chapterStr}</span>
                        <span><i class="fas fa-weight"></i> ${fileSizeStr}</span>
                    </div>
                </div>
                <div class="book-actions">
                    <button class="btn btn-primary btn-sm" onclick="openEbookReader(${book.id})" title="阅读">
                        <i class="fas fa-book-reader"></i>
                    </button>
                    <button class="btn btn-outline-info btn-sm" onclick="openScriptEditor(${book.id})" title="剧本">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteLibraryBook(${book.id}, '${escapeHtml(book.title).replace(/'/g, "\\'")}')" title="删除">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        grid.appendChild(col);
    });
}

function renderLibraryPagination(total, totalPages, currentPage) {
    const list = document.getElementById('libraryPaginationList');
    list.innerHTML = '';

    const addPageItem = (page, label, disabled = false, active = false) => {
        const li = document.createElement('li');
        li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="goToLibraryPage(${page}); return false;">${label}</a>`;
        list.appendChild(li);
    };

    addPageItem(Math.max(1, currentPage - 1), '<i class="fas fa-chevron-left"></i>', currentPage === 1);

    const showPages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(showPages / 2));
    let endPage = Math.min(totalPages, startPage + showPages - 1);
    startPage = Math.max(1, endPage - showPages + 1);

    if (startPage > 1) {
        addPageItem(1, '1');
        if (startPage > 2) addPageItem(0, '...', true);
    }
    for (let i = startPage; i <= endPage; i++) {
        addPageItem(i, i, false, i === currentPage);
    }
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) addPageItem(0, '...', true);
        addPageItem(totalPages, totalPages);
    }
    addPageItem(Math.min(totalPages, currentPage + 1), '<i class="fas fa-chevron-right"></i>', currentPage === totalPages);
}

function goToLibraryPage(page) {
    currentLibraryPage = page;
    loadLibraryBooks();
}

function openEbookReader(bookId) {
    window.open(`ebook_reader.html?book_id=${bookId}`, '_blank');
}

async function openScriptEditor(bookId) {
    window.open(`script_editor.html?book_id=${bookId}`, '_blank');
}

function showCreateEmptyBookModal() {
    document.getElementById('emptyBookTitle').value = '';
    document.getElementById('emptyBookAuthor').value = '';
    document.getElementById('emptyBookDescription').value = '';
    const modal = new bootstrap.Modal(document.getElementById('createEmptyBookModal'));
    modal.show();
}

async function createEmptyBook() {
    const title = document.getElementById('emptyBookTitle').value.trim();
    const author = document.getElementById('emptyBookAuthor').value.trim();
    const description = document.getElementById('emptyBookDescription').value.trim();

    if (!title) {
        showToast('请输入书名', 'warning');
        return;
    }

    showToast('正在创建空书...', 'info');

    const formData = new FormData();
    formData.append('title', title);
    formData.append('author', author);
    formData.append('description', description);

    try {
        const data = await apiRequest(`${API_BASE_URL}/api/books/library/create-empty`, {
            method: 'POST',
            body: formData,
            errorPrefix: '创建空书失败'
        });
        if (data.success) {
            showToast(`创建成功: ${data.message}`, 'success');
            loadLibraryBooks();
            const modal = bootstrap.Modal.getInstance(document.getElementById('createEmptyBookModal'));
            modal.hide();
            setTimeout(() => {
                openScriptEditor(data.book_id);
            }, 500);
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    }
}

async function uploadEbookFile(input) {
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name.replace(/\.[^.]+$/, ''));

    showToast('正在上传电子书...', 'info');
    try {
        const data = await apiRequest(`${API_BASE_URL}/api/books/library/upload`, {
            method: 'POST',
            body: formData,
            errorPrefix: '上传电子书失败'
        });
        if (data.success) {
            if (data.duplicated) {
                showToast(`电子书已存在: ${data.message}`, 'warning');
            } else {
                showToast(`上传成功: ${data.title} (${data.chapter_count}章, ${data.word_count}字)`, 'success');
            }
            loadLibraryBooks();
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    }
    input.value = '';
}

async function deleteLibraryBook(bookId, bookTitle) {
    if (!confirm(`确定删除《${bookTitle}》吗？\n将同时删除文件和章节记录，不可恢复。`)) return;

    try {
        const data = await apiRequest(`/api/books/library?book_id=${bookId}`, {
            method: 'DELETE',
            errorPrefix: '删除失败'
        });
        if (data.success) {
            showToast(data.message, 'success');
            loadLibraryBooks();
        }
    } catch (e) {
        // apiRequest 已弹出错误提示
    }
}