let API_BASE = window.location.origin + '/api';

async function initApiBaseUrl() {
    try {
        const resp = await fetch(`${window.location.origin}/api/server-info`);
        const data = await resp.json();
        if (data && data.base_url) {
            API_BASE = data.base_url + '/api';
            console.log('[API] 动态获取服务器地址:', API_BASE);
        }
    } catch (e) {
        console.log('[API] 使用默认地址:', API_BASE);
    }
}

let currentAgentId = null;
let callTimerInterval = null;
let callSeconds = 0;
let isMuted = false;
let isSpeakerOn = false;
let ws = null;

async function fetchSettings() {
    const response = await fetch(`${API_BASE}/settings`);
    const data = await response.json();
    document.getElementById('cosyvoicePath').value = data.cosyvoice_model_path || '';
    document.getElementById('qwenPath').value = data.qwen_model_path || '';
    renderModelList(data.available_models || []);
}

async function saveSettings() {
    const settings = {
        cosyvoice_model_path: document.getElementById('cosyvoicePath').value,
        qwen_model_path: document.getElementById('qwenPath').value
    };
    
    const response = await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    });
    
    const data = await response.json();
    alert(data.message);
}

function renderModelList(models) {
    const list = document.getElementById('modelList');
    list.innerHTML = '';
    
    models.forEach(model => {
        const item = document.createElement('div');
        item.className = 'list-group-item d-flex justify-content-between align-items-center';
        item.innerHTML = `
            <div>
                <strong>${model.name}</strong>
                <span class="badge bg-secondary ms-2">${model.type}</span>
            </div>
            <button class="btn btn-sm btn-outline-primary" onclick="selectModel('${model.path}', '${model.type}')">选择</button>
        `;
        list.appendChild(item);
    });
}

function selectModel(path, type) {
    if (type === 'cosyvoice') {
        document.getElementById('cosyvoicePath').value = path;
    } else if (type === 'qwen') {
        document.getElementById('qwenPath').value = path;
    }
}

function showDownloadModal() {
    document.getElementById('downloadModal').querySelector('.modal-body').style.display = 'block';
    document.getElementById('downloadProgress').classList.add('d-none');
    new bootstrap.Modal(document.getElementById('downloadModal')).show();
}

async function downloadModel() {
    const modelName = document.getElementById('modelName').value;
    if (!modelName) {
        alert('请输入模型名称');
        return;
    }
    
    document.getElementById('downloadModal').querySelector('.modal-body').style.display = 'none';
    document.getElementById('downloadProgress').classList.remove('d-none');
    
    try {
        const response = await fetch(`${API_BASE}/models/download?model_name=${encodeURIComponent(modelName)}`);
        const data = await response.json();
        
        if (response.ok) {
            alert(data.message);
            fetchSettings();
        } else {
            alert(data.detail || '下载失败');
        }
    } catch (error) {
        alert('下载失败: ' + error.message);
    } finally {
        document.getElementById('downloadModal').querySelector('.modal-body').style.display = 'block';
        document.getElementById('downloadProgress').classList.add('d-none');
        bootstrap.Modal.getInstance(document.getElementById('downloadModal')).hide();
    }
}

async function fetchAgents() {
    const response = await fetch(`${API_BASE}/agents`);
    const agents = await response.json();
    renderAgentList(agents);
}

function renderAgentList(agents) {
    const list = document.getElementById('agentList');
    list.innerHTML = '';
    
    if (agents.length === 0) {
        list.innerHTML = '<div class="col-12 text-center text-gray-500 py-8">暂无智能体，请点击上方按钮新增</div>';
        return;
    }
    
    agents.forEach(agent => {
        const card = document.createElement('div');
        card.className = 'col-md-4 mb-4';
        card.innerHTML = `
            <div class="card agent-card">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-3">
                        <div>
                            <h5 class="card-title">${agent.name}</h5>
                            <p class="card-text text-gray-500 text-sm">${agent.description || '暂无描述'}</p>
                        </div>
                        <span class="badge ${agent.trained ? 'bg-success' : 'bg-warning'}">${agent.trained ? '已训练' : '未训练'}</span>
                    </div>
                    <div class="d-flex gap-2">
                        <button class="btn btn-sm btn-outline-primary flex-1" onclick="showTrainModal('${agent.id}')">
                            <i class="fas fa-train"></i> 训练
                        </button>
                        <button class="call-btn" onclick="startCall('${agent.id}', '${agent.name}')">
                            <i class="fas fa-phone"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteAgent('${agent.id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        list.appendChild(card);
    });
}

function showAddAgentModal() {
    document.getElementById('agentName').value = '';
    document.getElementById('agentDescription').value = '';
    new bootstrap.Modal(document.getElementById('addAgentModal')).show();
}

async function createAgent() {
    const name = document.getElementById('agentName').value;
    const description = document.getElementById('agentDescription').value;
    
    if (!name) {
        alert('请输入智能体名称');
        return;
    }
    
    const response = await fetch(`${API_BASE}/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description })
    });
    
    const data = await response.json();
    
    if (response.ok) {
        bootstrap.Modal.getInstance(document.getElementById('addAgentModal')).hide();
        fetchAgents();
        alert('智能体创建成功');
    } else {
        alert(data.error || '创建失败');
    }
}

let trainingAgentId = null;

function showTrainModal(agentId) {
    trainingAgentId = agentId;
    document.getElementById('voiceFile').value = '';
    document.getElementById('promptFile').value = '';
    document.getElementById('trainingProgress').classList.add('d-none');
    new bootstrap.Modal(document.getElementById('trainAgentModal')).show();
}

async function startTraining() {
    const voiceFile = document.getElementById('voiceFile').files[0];
    const promptFile = document.getElementById('promptFile').files[0];
    
    if (!voiceFile || !promptFile) {
        alert('请选择语音文件和提示文件');
        return;
    }
    
    document.getElementById('trainingProgress').classList.remove('d-none');
    
    const formData = new FormData();
    formData.append('voice_file', voiceFile);
    formData.append('prompt_file', promptFile);
    
    try {
        const response = await fetch(`${API_BASE}/agents/train?agent_id=${trainingAgentId}`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert(data.message);
            fetchAgents();
        } else {
            alert(data.error || '训练失败');
        }
    } catch (error) {
        alert('训练失败: ' + error.message);
    } finally {
        document.getElementById('trainingProgress').classList.add('d-none');
        bootstrap.Modal.getInstance(document.getElementById('trainAgentModal')).hide();
    }
}

async function deleteAgent(agentId) {
    if (!confirm('确定要删除这个智能体吗？')) {
        return;
    }
    
    const response = await fetch(`${API_BASE}/agents?agent_id=${agentId}`, {
        method: 'DELETE'
    });
    
    const data = await response.json();
    
    if (response.ok) {
        alert(data.message);
        fetchAgents();
    } else {
        alert(data.error || '删除失败');
    }
}

function startCall(agentId, agentName) {
    currentAgentId = agentId;
    document.getElementById('callAgentName').textContent = agentName;
    document.getElementById('callTimer').textContent = '00:00';
    document.getElementById('callChat').innerHTML = '';
    document.getElementById('messageInput').value = '';
    
    document.getElementById('callInterface').classList.add('d-none');
    document.getElementById('callActive').classList.remove('d-none');
    
    callSeconds = 0;
    callTimerInterval = setInterval(updateCallTimer, 1000);
    
    isMuted = false;
    isSpeakerOn = false;
    document.getElementById('muteBtn').classList.remove('active');
    document.getElementById('muteBtn').innerHTML = '<i class="fas fa-microphone"></i>';
    document.getElementById('speakerBtn').classList.remove('active');
    document.getElementById('speakerBtn').innerHTML = '<i class="fas fa-volume-up"></i>';
    
    connectWebSocket(agentId);
    
    document.querySelector('[data-bs-target="#call"]').click();
}

function updateCallTimer() {
    callSeconds++;
    const minutes = Math.floor(callSeconds / 60).toString().padStart(2, '0');
    const seconds = (callSeconds % 60).toString().padStart(2, '0');
    document.getElementById('callTimer').textContent = `${minutes}:${seconds}`;
}

function toggleMute() {
    isMuted = !isMuted;
    const btn = document.getElementById('muteBtn');
    
    if (isMuted) {
        btn.classList.add('active');
        btn.innerHTML = '<i class="fas fa-microphone-slash"></i>';
    } else {
        btn.classList.remove('active');
        btn.innerHTML = '<i class="fas fa-microphone"></i>';
    }
}

function toggleSpeaker() {
    isSpeakerOn = !isSpeakerOn;
    const btn = document.getElementById('speakerBtn');
    
    if (isSpeakerOn) {
        btn.classList.add('active');
        btn.innerHTML = '<i class="fas fa-volume-up"></i>';
    } else {
        btn.classList.remove('active');
        btn.innerHTML = '<i class="fas fa-volume-up"></i>';
    }
}

function endCall() {
    if (callTimerInterval) {
        clearInterval(callTimerInterval);
        callTimerInterval = null;
    }
    
    if (ws) {
        ws.close();
        ws = null;
    }
    
    document.getElementById('callActive').classList.add('d-none');
    document.getElementById('callInterface').classList.remove('d-none');
    
    currentAgentId = null;
}

function connectWebSocket(agentId) {
    const wsProtocol = API_BASE.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = API_BASE.replace(/^https?:\/\//, '').replace(/:\d+\/api$/, '');
    ws = new WebSocket(`${wsProtocol}//${wsHost}/api/agents/call?agent_id=${agentId}`);
    
    ws.onopen = () => {
        console.log('WebSocket连接成功');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'stream_start') {
            showTypingIndicator();
        } else if (data.type === 'stream_chunk') {
            updateAgentResponse(data.content);
        } else if (data.type === 'stream_finish') {
            hideTypingIndicator();
        } else if (data.type === 'audio_start') {
            showAudioIndicator();
        } else if (data.type === 'audio_chunk') {
            playAudio(data.content);
        } else if (data.type === 'response') {
            hideTypingIndicator();
            hideAudioIndicator();
            addChatBubble(data.text, 'agent');
            
            if (data.audio_path) {
                playAudio(data.audio_path);
            }
        } else if (data.type === 'error') {
            hideTypingIndicator();
            hideAudioIndicator();
            addChatBubble('错误: ' + data.message, 'system');
        }
    };
    
    ws.onclose = () => {
        console.log('WebSocket连接关闭');
        hideTypingIndicator();
        hideAudioIndicator();
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket错误:', error);
        hideTypingIndicator();
        hideAudioIndicator();
    };
}

let currentAgentBubble = null;

function showTypingIndicator() {
    const chat = document.getElementById('callChat');
    const indicator = document.createElement('div');
    indicator.id = 'typingIndicator';
    indicator.className = 'chat-bubble agent typing';
    indicator.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chat.appendChild(indicator);
    chat.scrollTop = chat.scrollHeight;
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

function showAudioIndicator() {
    const chat = document.getElementById('callChat');
    const indicator = document.createElement('div');
    indicator.id = 'audioIndicator';
    indicator.className = 'chat-bubble agent audio-processing';
    indicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在生成语音...';
    chat.appendChild(indicator);
    chat.scrollTop = chat.scrollHeight;
}

function hideAudioIndicator() {
    const indicator = document.getElementById('audioIndicator');
    if (indicator) {
        indicator.remove();
    }
}

function updateAgentResponse(text) {
    hideTypingIndicator();
    
    if (!currentAgentBubble) {
        currentAgentBubble = document.createElement('div');
        currentAgentBubble.className = 'chat-bubble agent';
        currentAgentBubble.textContent = text;
        const chat = document.getElementById('callChat');
        chat.appendChild(currentAgentBubble);
    } else {
        currentAgentBubble.textContent += text;
    }
    
    const chat = document.getElementById('callChat');
    chat.scrollTop = chat.scrollHeight;
}

function sendMessage(text) {
    if (!ws || !text.trim()) return;
    
    addChatBubble(text, 'user');
    
    ws.send(JSON.stringify({
        type: 'message',
        text: text.trim()
    }));
}

function handleSendMessage() {
    const input = document.getElementById('messageInput');
    sendMessage(input.value);
    input.value = '';
}

function addChatBubble(text, type) {
    const chat = document.getElementById('callChat');
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${type}`;
    bubble.textContent = text;
    chat.appendChild(bubble);
    chat.scrollTop = chat.scrollHeight;
}

function playAudio(audioPath) {
    try {
        const baseUrl = API_BASE.replace('/api', '');
        const audioUrl = `${baseUrl}/${audioPath.replace(/\\/g, '/')}`;
        const audio = new Audio(audioUrl);
        audio.play().catch(e => console.error('播放音频失败:', e));
    } catch (e) {
        console.error('播放音频失败:', e);
    }
}

window.addEventListener('load', async () => {
    await initApiBaseUrl();
    fetchSettings();
    fetchAgents();
    
    document.getElementById('messageInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleSendMessage();
        }
    });
    
    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = false;
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        if (!isMuted && currentAgentId) {
            sendMessage(transcript);
        }
    };
});