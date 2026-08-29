let ttsAudioContext = null;
let ttsRecordedAudioBuffer = [];
let ttsNextPlayTime = 0;
let ttsWaveformBuffer = [];
const TTS_WAVEFORM_MAX = 200;

function openCapabilityTest(capabilityType) {
    const existingModal = document.getElementById('capabilityTestModal');
    if (existingModal) {
        existingModal.remove();
    }

    const detail = CAPABILITY_TYPE_DETAILS[capabilityType];
    let inputAreaHtml = '';
    
    if (capabilityType === 'text_predict') {
        inputAreaHtml = `
            <div class="mb-3">
                <label class="form-label">系统提示词 (可选)</label>
                <textarea class="form-control" id="test-system-prompt" rows="3" placeholder="请输入系统提示词"></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">测试文本</label>
                <textarea class="form-control" id="test-input-text" rows="4" placeholder="请输入测试文本..."></textarea>
            </div>
        `;
    } else if (capabilityType === 'text_to_speech') {
        inputAreaHtml = `
            <div class="mb-3">
                <label class="form-label">智能体</label>
                <select class="form-select" id="test-agent-select">
                    <option value="">点击刷新加载...</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">测试文本</label>
                <textarea class="form-control" id="test-input-text" rows="4" placeholder="请输入要合成语音的文本..."></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">语气指令（可选，CosyVoice3）</label>
                <input type="text" class="form-control" id="test-instruction" placeholder="例如：请非常开心地说一句话">
            </div>
            <div id="tts-stats" style="display: none; margin-bottom: 12px; padding: 12px; background: #f8f9fa; border-radius: 8px;">
                <div class="row">
                    <div class="col-3"><small>采样率:</small><div id="tts-sample-rate" style="font-weight: 600;">--</div></div>
                    <div class="col-3"><small>已接收块:</small><div id="tts-chunks" style="font-weight: 600;">0</div></div>
                    <div class="col-3"><small>时长:</small><div id="tts-duration" style="font-weight: 600;">0.00s</div></div>
                    <div class="col-3"><small>耗时:</small><div id="tts-elapsed" style="font-weight: 600;">0.00s</div></div>
                </div>
            </div>
            <div id="tts-waveform-container" style="display: none; margin-bottom: 12px; padding: 8px; background: #0a0f1c; border-radius: 8px; height: 60px;">
                <canvas id="tts-waveform" style="width: 100%; height: 100%;"></canvas>
            </div>
        `;
    } else if (capabilityType === 'text_to_image') {
        inputAreaHtml = `
            <div class="mb-3">
                <label class="form-label">提示词</label>
                <textarea class="form-control" id="test-input-text" rows="4" placeholder="请输入图像描述..."></textarea>
            </div>
        `;
    } else if (capabilityType === 'text_to_vector') {
        inputAreaHtml = `
            <div class="mb-3">
                <label class="form-label">测试文本</label>
                <textarea class="form-control" id="test-input-text" rows="4" placeholder="请输入要转向量的文本..."></textarea>
            </div>
        `;
    } else if (capabilityType === 'text_rerank') {
        inputAreaHtml = `
            <div class="mb-3">
                <label class="form-label">查询文本</label>
                <textarea class="form-control" id="test-rerank-query" rows="2" placeholder="请输入查询文本..."></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">候选片段（每行一个）</label>
                <textarea class="form-control" id="test-rerank-documents" rows="6" placeholder="每行输入一个候选片段..."></textarea>
            </div>
        `;
    }

    const modalHtml = `
        <div class="modal fade" id="capabilityTestModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <i class="fas ${detail.icon}" style="color: ${detail.color}; font-size: 24px;"></i>
                            <div>
                                <h5 class="modal-title" style="margin: 0;">${detail.name}测试</h5>
                                <p style="margin: 2px 0 0; font-size: 12px; color: var(--neu-text-muted);">选择能力配置进行测试</p>
                            </div>
                        </div>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="height: 60vh; overflow-y: auto;">
                        <div class="row mb-4">
                            <div class="col-md-6">
                                <label class="form-label" style="font-size: 12px; font-weight: 600;">选择能力配置</label>
                                <select class="form-select" id="test-capability-select">
                                    <option value="">自动选择最佳能力</option>
                                </select>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label" style="font-size: 12px; font-weight: 600;">历史记录</label>
                                <button class="btn btn-sm btn-outline-secondary w-100" onclick="loadCapabilityTestHistory('${capabilityType}')">
                                    <i class="fas fa-history"></i> 查看历史
                                </button>
                            </div>
                        </div>
                        <div id="test-input-area">${inputAreaHtml}</div>
                        <div id="test-result-area" style="display: none;">
                            <div class="card mt-4" style="border-radius: 8px;">
                                <div class="card-header" style="font-size: 13px; font-weight: 600;">测试结果</div>
                                <div class="card-body">
                                    <div id="test-result-content"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                        <button type="button" class="btn btn-primary" id="run-test-btn" onclick="runCapabilityTest('${capabilityType}')">
                            <i class="fas fa-play"></i> 开始测试
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('capabilityTestModal'));
    modal.show();

    loadCapabilityTestOptions(capabilityType);
    
    if (capabilityType === 'text_to_speech') {
        setTimeout(() => {
            refreshTestAgents();
        }, 100);
    }
}

async function loadCapabilityTestOptions(capabilityType) {
    const select = document.getElementById('test-capability-select');
    if (!select) return;

    try {
        const data = await apiRequest(`/api/capabilities`, { silent: true });
        const capabilities = data.capabilities || {};
        const capList = capabilities[capabilityType] || [];
        
        select.innerHTML = '<option value="">自动选择最佳能力</option>' + 
            capList.map(cap => `<option value="${cap.id}">${cap.description || cap.model_code} (${cap.platform_code})</option>`).join('');
    } catch (e) {
        // 静默加载
    }
}

async function runCapabilityTest(capabilityType) {
    const btn = document.getElementById('run-test-btn');
    const resultArea = document.getElementById('test-result-area');
    const resultContent = document.getElementById('test-result-content');
    
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 测试中...';
    resultArea.style.display = 'none';

    const capabilityId = document.getElementById('test-capability-select')?.value || '';
    let inputData = {};

    if (capabilityType === 'text_predict') {
        inputData = {
            prompt: document.getElementById('test-input-text')?.value || '',
            system_prompt: document.getElementById('test-system-prompt')?.value || ''
        };
    } else if (capabilityType === 'text_to_speech') {
        inputData = {
            text: document.getElementById('test-input-text')?.value || '',
            agent_id: document.getElementById('test-agent-select')?.value || '',
            instruction: document.getElementById('test-instruction')?.value || ''
        };
    } else if (capabilityType === 'text_to_image') {
        inputData = {
            prompt: document.getElementById('test-input-text')?.value || ''
        };
    } else if (capabilityType === 'text_to_vector') {
        inputData = {
            text: document.getElementById('test-input-text')?.value || ''
        };
    } else if (capabilityType === 'text_rerank') {
        const docsText = document.getElementById('test-rerank-documents')?.value || '';
        inputData = {
            query: document.getElementById('test-rerank-query')?.value || '',
            documents: docsText.split('\n').map(s => s.trim()).filter(s => s),
            top_k: 5
        };
    }

    if (capabilityType === 'text_to_speech') {
        await runTtsTest(capabilityId, inputData, btn, resultArea, resultContent);
    } else {
        await runGenericCapabilityTest(capabilityType, capabilityId, inputData, btn, resultArea, resultContent);
    }
}

async function runGenericCapabilityTest(capabilityType, capabilityId, inputData, btn, resultArea, resultContent) {
    const startTime = performance.now();

    try {
        const url = `${API_BASE_URL}/api/capabilities/test`;
        const payload = {
            capability_type: capabilityType,
            capability_id: capabilityId,
            input_data: inputData
        };

        const data = await apiRequest(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            silent: true
        });

        const elapsed = (performance.now() - startTime) / 1000;

        resultArea.style.display = 'block';

        if (data.success) {
            let resultHtml = `<div class="mb-3"><strong>状态:</strong> <span class="badge bg-success">成功</span></div>`;
            resultHtml += `<div class="mb-3"><strong>耗时:</strong> ${elapsed.toFixed(2)}s</div>`;
            
            if (capabilityType === 'text_predict') {
                resultHtml += `<div class="mb-3"><strong>输出:</strong></div><pre style="white-space: pre-wrap; word-wrap: break-word; background: #f8f9fa; padding: 12px; border-radius: 6px; font-size: 13px;">${escapeHtml(data.output || '')}</pre>`;
            } else if (capabilityType === 'text_to_image') {
                resultHtml += `<div class="mb-3"><strong>生成图像:</strong></div><img src="${data.output || ''}" class="img-fluid rounded" style="max-height: 400px;">`;
            } else if (capabilityType === 'text_to_vector') {
                const vec = data.output || [];
                resultHtml += `<div class="mb-3"><strong>向量维度:</strong> ${vec.length}</div>`;
                resultHtml += `<div class="mb-3"><strong>向量前10个值:</strong></div><pre style="white-space: pre-wrap; word-wrap: break-word; background: #f8f9fa; padding: 12px; border-radius: 6px; font-size: 12px;">${vec.slice(0, 10).join(', ')}</pre>`;
            } else if (capabilityType === 'text_rerank') {
                const rerankResults = (data.result && data.result.results) || (data.output && data.output.results) || [];
                resultHtml += `<div class="mb-3"><strong>重排序结果（共 ${rerankResults.length} 条）:</strong></div>`;
                resultHtml += rerankResults.map((item, i) => `
                    <div style="margin-bottom: 8px; padding: 10px; background: #f8f9fa; border-radius: 6px;">
                        <div style="font-size: 12px; color: #6c757d; margin-bottom: 4px;">
                            #${i + 1} &nbsp;分数: <strong>${(item.score || 0).toFixed(4)}</strong> &nbsp;原始索引: ${item.index}
                        </div>
                        <div style="font-size: 13px;">${escapeHtml(item.document || '')}</div>
                    </div>
                `).join('');
            }
            
            resultContent.innerHTML = resultHtml;
        } else {
            resultContent.innerHTML = `
                <div class="mb-3"><strong>状态:</strong> <span class="badge bg-danger">失败</span></div>
                <div class="bg-danger bg-opacity-10 p-3 rounded"><strong>错误:</strong> ${data.error || '未知错误'}</div>
            `;
        }
    } catch (e) {
        resultArea.style.display = 'block';
        resultContent.innerHTML = `
            <div class="mb-3"><strong>状态:</strong> <span class="badge bg-danger">失败</span></div>
            <div class="bg-danger bg-opacity-10 p-3 rounded"><strong>错误:</strong> ${e.message}</div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> 开始测试';
    }
}

async function runTtsTest(capabilityId, inputData, btn, resultArea, resultContent) {
    const startTime = performance.now();
    const abortController = new AbortController();

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 合成中...';
    resultArea.style.display = 'none';

    ttsRecordedAudioBuffer = [];
    ttsNextPlayTime = 0;
    ttsWaveformBuffer = [];

    const url = `${API_BASE_URL}/api/audio/synthesize`;
    const payload = { agent_id: inputData.agent_id, text: inputData.text };
    if (inputData.instruction) {
        payload.instruction = inputData.instruction;
    }

    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: abortController.signal,
        });

        if (!resp.ok) {
            const errText = await resp.text().catch(() => '');
            throw new Error(`HTTP ${resp.status}: ${errText || resp.statusText}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let chunkCount = 0;
        let totalSamples = 0;
        let currentSampleRate = 24000;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const msg = JSON.parse(line);
                    switch (msg.type) {
                        case 'start':
                            break;
                        case 'pcm_chunk':
                            currentSampleRate = msg.sample_rate;
                            document.getElementById('tts-sample-rate').textContent = msg.sample_rate + ' Hz';

                            const b64 = msg.data;
                            const pcmBytes = base64ToUint8Array(b64);
                            const int16 = new Int16Array(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength / 2);

                            ttsEnqueuePCM(int16, msg.sample_rate);

                            chunkCount = msg.chunk_index + 1;
                            totalSamples += int16.length;
                            const duration = totalSamples / msg.sample_rate;

                            document.getElementById('tts-chunks').textContent = chunkCount;
                            document.getElementById('tts-duration').textContent = duration.toFixed(2) + 's';
                            const elapsed = (performance.now() - startTime) / 1000;
                            document.getElementById('tts-elapsed').textContent = elapsed.toFixed(2) + 's';
                            break;
                        case 'finish':
                            break;
                        case 'error':
                            throw new Error(msg.message);
                    }
                } catch (e) {
                    console.error('消息解析失败:', e);
                }
            }
        }

        if (chunkCount > 0) {
            const elapsed = (performance.now() - startTime) / 1000;
            resultArea.style.display = 'block';
            let resultHtml = `<div class="mb-3"><strong>状态:</strong> <span class="badge bg-success">成功</span></div>`;
            resultHtml += `<div class="mb-3"><strong>耗时:</strong> ${elapsed.toFixed(2)}s</div>`;
            resultHtml += `<div class="mb-3"><strong>采样率:</strong> ${currentSampleRate} Hz</div>`;
            resultHtml += `<div class="mb-3"><strong>块数:</strong> ${chunkCount}</div>`;
            resultHtml += `<div class="mb-3"><strong>时长:</strong> ${(totalSamples / currentSampleRate).toFixed(2)}s</div>`;
            if (ttsRecordedAudioBuffer.length > 0) {
                resultHtml += `<button class="btn btn-sm btn-outline-secondary mt-2" onclick="ttsReplayAudio()">重新播放</button>`;
            }
            resultContent.innerHTML = resultHtml;
        } else {
            throw new Error('未收到任何音频数据');
        }

    } catch (e) {
        resultArea.style.display = 'block';
        resultContent.innerHTML = `
            <div class="mb-3"><strong>状态:</strong> <span class="badge bg-danger">失败</span></div>
            <div class="bg-danger bg-opacity-10 p-3 rounded"><strong>错误:</strong> ${e.message}</div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> 开始测试';
    }
}

function resetTtsStats() {
    document.getElementById('tts-sample-rate').textContent = '--';
    document.getElementById('tts-chunks').textContent = '0';
    document.getElementById('tts-duration').textContent = '0.00s';
    document.getElementById('tts-elapsed').textContent = '0.00s';
    ttsWaveformBuffer = [];
    ttsDrawWaveform();
}

function ttsEnsureAudioContext() {
    if (!ttsAudioContext) {
        ttsAudioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (ttsAudioContext.state === 'suspended') {
        ttsAudioContext.resume();
    }
    return ttsAudioContext;
}

function ttsEnqueuePCM(int16Array, sampleRate) {
    const ctx = ttsEnsureAudioContext();
    const float32 = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
        float32[i] = int16Array[i] / 32767.0;
    }

    ttsRecordedAudioBuffer.push({ data: float32, sampleRate: sampleRate });

    let playable = float32;
    if (sampleRate !== ctx.sampleRate) {
        playable = ttsResampleLinear(float32, sampleRate, ctx.sampleRate);
    }

    const audioBuffer = ctx.createBuffer(1, playable.length, ctx.sampleRate);
    audioBuffer.copyToChannel(playable, 0);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    if (ttsNextPlayTime < now) {
        ttsNextPlayTime = now;
    }
    source.start(ttsNextPlayTime);
    ttsNextPlayTime += audioBuffer.duration;

    ttsPushWaveformSamples(playable);
}

function ttsResampleLinear(input, fromSR, toSR) {
    if (fromSR === toSR) return input;
    const ratio = toSR / fromSR;
    const outLen = Math.floor(input.length * ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
        const srcIdx = i / ratio;
        const i0 = Math.floor(srcIdx);
        const i1 = Math.min(i0 + 1, input.length - 1);
        const frac = srcIdx - i0;
        out[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    return out;
}

function ttsPushWaveformSamples(samples) {
    const step = Math.max(1, Math.floor(samples.length / 20));
    for (let i = 0; i < samples.length; i += step) {
        if (ttsWaveformBuffer.length >= TTS_WAVEFORM_MAX) {
            ttsWaveformBuffer.shift();
        }
        ttsWaveformBuffer.push(samples[i]);
    }
    ttsDrawWaveform();
}

function ttsDrawWaveform() {
    const canvas = document.getElementById('tts-waveform');
    if (!canvas) return;
    const ctx2d = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx2d.scale(dpr, dpr);

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    ctx2d.clearRect(0, 0, w, h);

    ctx2d.strokeStyle = 'rgba(148, 163, 184, 0.15)';
    ctx2d.lineWidth = 1;
    ctx2d.beginPath();
    ctx2d.moveTo(0, h / 2);
    ctx2d.lineTo(w, h / 2);
    ctx2d.stroke();

    if (ttsWaveformBuffer.length === 0) return;

    const barWidth = w / TTS_WAVEFORM_MAX;
    for (let i = 0; i < ttsWaveformBuffer.length; i++) {
        const v = Math.abs(ttsWaveformBuffer[i]);
        const barH = Math.max(1, v * h * 0.9);
        const x = i * barWidth;
        const y = (h - barH) / 2;
        const grad = ctx2d.createLinearGradient(0, y, 0, y + barH);
        grad.addColorStop(0, '#38bdf8');
        grad.addColorStop(1, '#6366f1');
        ctx2d.fillStyle = grad;
        ctx2d.fillRect(x, y, Math.max(1, barWidth - 1), barH);
    }
}

function ttsReplayAudio() {
    if (!ttsRecordedAudioBuffer || ttsRecordedAudioBuffer.length === 0) {
        alert('没有可回放的音频数据');
        return;
    }

    const ctx = ttsEnsureAudioContext();
    ttsNextPlayTime = ctx.currentTime;
    ttsWaveformBuffer = [];

    ttsRecordedAudioBuffer.forEach((chunk) => {
        let playable = chunk.data;
        if (chunk.sampleRate !== ctx.sampleRate) {
            playable = ttsResampleLinear(chunk.data, chunk.sampleRate, ctx.sampleRate);
        }

        const audioBuffer = ctx.createBuffer(1, playable.length, ctx.sampleRate);
        audioBuffer.copyToChannel(playable, 0);

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        source.start(ttsNextPlayTime);

        ttsNextPlayTime += audioBuffer.duration;
        ttsPushWaveformSamples(playable);
    });
}

function base64ToUint8Array(b64) {
    const binStr = atob(b64);
    const len = binStr.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binStr.charCodeAt(i);
    }
    return bytes;
}

async function refreshTestAgents() {
    const select = document.getElementById('test-agent-select');
    if (!select) return;
    
    try {
        const data = await apiRequest(`/api/agents?page=1&page_size=200`, { silent: true });
        const agents = data.items || data.agents || data;
        select.innerHTML = '';
        if (!Array.isArray(agents) || agents.length === 0) {
            select.innerHTML = '<option value="">无可用智能体</option>';
            return;
        }
        agents.forEach(a => {
            const opt = document.createElement('option');
            opt.value = a.id;
            opt.textContent = `${a.name} (${a.id})`;
            select.appendChild(opt);
        });
    } catch (e) {
        select.innerHTML = '<option value="">加载失败</option>';
        showToast('加载智能体列表失败', 'error');
    }
}

async function loadCapabilityTestHistory(capabilityType) {
    const modalHtml = `
        <div class="modal fade" id="testHistoryModal" tabindex="-1" style="z-index: 2000;">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">测试历史记录</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="height: 50vh; overflow-y: auto;">
                        <div id="test-history-content"></div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('testHistoryModal'));
    modal.show();

    await fetchTestHistory(capabilityType, 1);
}

async function fetchTestHistory(capabilityType, page) {
    const content = document.getElementById('test-history-content');
    if (!content) return;

    try {
        const data = await apiRequest(`/api/capabilities/test-history?capability_type=${capabilityType}&page=${page}&page_size=10`, { silent: true });
        const records = data.records || [];

        if (records.length === 0) {
            content.innerHTML = '<div class="text-center text-muted py-4">暂无测试记录</div>';
            return;
        }

        let html = '<div class="list-group">';
        records.forEach(record => {
            const statusClass = record.status === 'success' ? 'bg-success' : 'bg-danger';
            html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span class="badge ${statusClass}">${record.status === 'success' ? '成功' : '失败'}</span>
                                <span style="font-size: 12px; color: var(--neu-text-muted);">${new Date(record.created_at * 1000).toLocaleString()}</span>
                                <span style="font-size: 12px;">${record.duration.toFixed(2)}s</span>
                            </div>
                            <div style="margin-top: 8px; font-size: 12px;">
                                <span style="color: var(--neu-text-muted);">平台:</span> ${record.platform_code}
                                <span style="margin-left: 12px; color: var(--neu-text-muted);">模型:</span> ${record.model_code}
                            </div>
                            <div style="margin-top: 4px; font-size: 12px; color: var(--neu-text-muted);">
                                输入: ${record.input_data.length > 50 ? record.input_data.substring(0, 50) + '...' : record.input_data}
                            </div>
                            ${record.error_message ? `<div style="margin-top: 4px; font-size: 12px; color: #dc3545;">错误: ${record.error_message}</div>` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        html += '</div>';

        if (data.total_pages > 1) {
            html += '<div class="mt-3 d-flex justify-content-center gap-2">';
            if (page > 1) {
                html += `<button class="btn btn-sm btn-outline-secondary" onclick="fetchTestHistory('${capabilityType}', ${page - 1})">上一页</button>`;
            }
            html += `<span style="font-size: 12px; align-self: center;">第 ${page} / ${data.total_pages} 页</span>`;
            if (page < data.total_pages) {
                html += `<button class="btn btn-sm btn-outline-secondary" onclick="fetchTestHistory('${capabilityType}', ${page + 1})">下一页</button>`;
            }
            html += '</div>';
        }

        content.innerHTML = html;
    } catch (e) {
        content.innerHTML = `<div class="text-center text-danger">加载失败: ${e.message}</div>`;
    }
}