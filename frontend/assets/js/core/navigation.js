let isSwitchingTab = false;

function switchTab(tabId, fromHash = false) {
    const targetPane = document.getElementById(tabId);
    if (!targetPane) return;

    const tabButton = document.querySelector(`#mainTabs button[data-bs-target="#${tabId}"]`);
    if (tabButton) {
        const tab = new bootstrap.Tab(tabButton);
        tab.show();
    } else {
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('show', 'active');
        });
        targetPane.classList.add('show', 'active');
    }

    document.querySelectorAll('.sidebar-nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const sidebarBtn = document.getElementById(`sidebar-${tabId}-btn`);
    if (sidebarBtn) {
        sidebarBtn.classList.add('active');
    }

    if (!fromHash) {
        history.replaceState(null, '', `#${tabId}`);
    }

    if (tabId === 'models') {
        refreshModelList();
    }

    if (tabId === 'settings') {
        loadSettingsNav();
    }
}

function switchTabByHash() {
    if (isSwitchingTab) return;
    const hash = window.location.hash.replace('#', '');
    if (!hash) return;
    switchTab(hash, true);
    
    const loaders = {
        'media': () => loadMediaCategories(),
        'settings': () => loadSettings(),
        'library': () => loadLibraryBooks(),
    };
    if (loaders[hash]) loaders[hash]();
}

window.addEventListener('hashchange', switchTabByHash);

const triggerTabList = document.querySelectorAll('#mainTabs button[data-bs-toggle="tab"]');
triggerTabList.forEach(triggerEl => {
    triggerEl.addEventListener('shown.bs.tab', function(event) {
        const targetId = event.target.getAttribute('data-bs-target').replace('#', '');
        document.querySelectorAll('.sidebar-nav-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        const sidebarBtn = document.getElementById(`sidebar-${targetId}-btn`);
        if (sidebarBtn) {
            sidebarBtn.classList.add('active');
        }
    });
});

function setupFileUploads() {
}

window.onload = async function () {
    await initApiBaseUrl();
    loadSettings();
    loadAgents();
    startStatusPolling();
    setupFileUploads();
    connectLogWebSocket();
    switchTabByHash();
};