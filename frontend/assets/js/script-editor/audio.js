/** 检查角色是否已配置 TTS（本地智能体或云端能力） */
function _hasTtsConfig(cfg) {
    if (!cfg) return false;
    if (cfg.agent_id) return true;
    if (cfg.tts_capability_id) {
        return state.ttsCapabilities.some(c => c.id === cfg.tts_capability_id);
    }
    return false;
}

async function synthesizeChapterAudio() {
    if (state.isSynthesizing || state.currentLines.length === 0 || state.scriptId === null || state.currentChapterIndex < 0) return;

    for (const line of state.currentLines) {
        const cfg = state.characterVoiceMap[line.role];
        if (!_hasTtsConfig(cfg)) {
            showToast(`角色「${line.role}」尚未配置配音，无法配音`, 'warning');
            return;
        }
    }

    state.isSynthesizing = true;
    updatePlayerButtons();
    const btn = document.getElementById('synthesizeBtn');
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 配音中...';

    try {
        const data = await apiRequest(`/api/audio/synthesize-chapter?script_id=${state.scriptId}&chapter_index=${state.currentChapterIndex}`, {
            method: 'POST',
            errorPrefix: '配音失败'
        });

        if (data.audio_paths) {
            for (const item of data.audio_paths) {
                const line = state.currentLines.find(l => l.id === item.line_id);
                if (line && item.audio_path) line.audio_path = item.audio_path;
            }
        }

        showToast(`配音成功：${data.line_count} 条台词，新生成 ${data.generated_count} 条，时长 ${formatDuration(data.duration)}`, 'success');

        showChapterAudioHistory();
    } catch (e) {
        console.error('配音失败:', e);
        showToast('配音失败: ' + e.message, 'error');
    } finally {
        state.isSynthesizing = false;
        updatePlayerButtons();
        btn.innerHTML = originalHtml;
    }
}

function updatePlayerButtons() {
    const hasLines = state.currentLines.length > 0;
    document.getElementById('playBtn').disabled = !hasLines;
    document.getElementById('prevLineBtn').disabled = !hasLines;
    document.getElementById('nextLineBtn').disabled = !hasLines;
    document.getElementById('synthesizeBtn').disabled = !hasLines || state.isSynthesizing;
    document.getElementById('chapterHistoryBtn').disabled = !hasLines;
    if (!hasLines) {
        document.getElementById('currentLineDisplay').textContent = '未播放';
        document.getElementById('playProgress').textContent = '-- / --';
    }
}

function togglePlay() {
    if (state.isPlaying) {
        stopPlay();
    } else {
        startPlay();
    }
}

async function startPlay() {
    if (state.currentLines.length === 0) return;
    if (state.currentPlayingIndex < 0) {
        state.currentPlayingIndex = 0;
    }
    state.isPlaying = true;
    updatePlayButton();
    await playFromIndex(state.currentPlayingIndex);
}

function stopPlay() {
    state.isPlaying = false;
    updatePlayButton();
    stopStreamPlayer();
    for (const src of state.activeSources) {
        try { src.onended = null; src.stop(); } catch(e) {}
    }
    state.activeSources = [];
    if (state.audioContext) {
        state.audioContext.close();
        state.audioContext = null;
    }
    state.audioQueue = [];
}

function updatePlayButton() {
    const btn = document.getElementById('playBtn');
    btn.innerHTML = state.isPlaying ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
}

function updatePlayingHighlight(index) {
    document.querySelectorAll('.script-line.playing').forEach(el => el.classList.remove('playing'));
    if (index >= 0 && index < state.currentLines.length) {
        const line = state.currentLines[index];
        const el = document.querySelector(`.script-line[data-line-id="${line.id}"]`);
        if (el) el.classList.add('playing');
    }
    updatePlayerInfo();
    updatePlayerButtons();
}

async function playFromIndex(index) {
    if (!state.isPlaying || index >= state.currentLines.length) {
        state.isPlaying = false;
        updatePlayButton();
        state.currentPlayingIndex = -1;
        updatePlayingHighlight(-1);
        return;
    }
    state.currentPlayingIndex = index;
    updatePlayingHighlight(index);

    const line = state.currentLines[index];
    const config = state.characterVoiceMap[line.role] || { agent_id: '', speed: 1.0, seed: 0, tts_capability_id: '', cloud_extra_params: '{}' };
    if (!_hasTtsConfig(config)) {
        showToast(`角色「${line.role}」尚未配置配音`, 'warning');
        state.isPlaying = false;
        updatePlayButton();
        state.currentPlayingIndex = -1;
        updatePlayingHighlight(-1);
        return;
    }

    await playLineById(line.id);

    if (state.isPlaying) {
        await playFromIndex(index + 1);
    }
}

async function playLineById(lineId) {
    try {
        const resp = await fetch(`/api/audio/play-line?line_id=${lineId}`, { method: 'POST' });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || '语音合成失败', 'error');
            return;
        }

        state.nextPlayTime = 0;
        state.isPlayingAudio = false;

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lineSampleRate = 24000;
        let finishReceived = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const lineStr of lines) {
                if (!lineStr.trim()) continue;
                try {
                    const msg = JSON.parse(lineStr);
                    if (msg.type === 'start') {
                        lineSampleRate = msg.sample_rate || 24000;
                    } else if (msg.type === 'pcm_chunk') {
                        if (!state.isPlaying) return;
                        const pcmData = new Int16Array(base64ToArrayBuffer(msg.data));
                        playPCMChunk(pcmData, msg.sample_rate || lineSampleRate);
                    } else if (msg.type === 'finish') {
                        if (msg.audio_path) {
                            const lineObj = state.currentLines.find(l => l.id === lineId);
                            if (lineObj) lineObj.audio_path = msg.audio_path;
                            updateLineAudioEditorDisplay(lineId);
                        }
                        finishReceived = true;
                    } else if (msg.type === 'error') {
                        showToast(`合成错误: ${msg.message}`, 'error');
                        return;
                    }
                } catch (e) { /* ignore parse errors */ }
            }
        }

        if (finishReceived) {
            while (state.activeSources.length > 0 && state.isPlaying) {
                await new Promise(resolve => setTimeout(resolve, 50));
            }
        }
    } catch (e) {
        console.error('语音合成失败:', e);
        showToast('语音合成失败', 'error');
    }
}

function playPrevLine() {
    if (state.currentPlayingIndex > 0) {
        stopPlay();
        state.currentPlayingIndex--;
        startPlay();
    }
}

function playNextLine() {
    if (state.currentPlayingIndex < state.currentLines.length - 1) {
        stopPlay();
        state.currentPlayingIndex++;
        startPlay();
    }
}

async function playSingleLine(index) {
    stopPlay();
    state.currentPlayingIndex = index;
    state.isPlaying = true;
    updatePlayButton();
    updatePlayingHighlight(index);
    const line = state.currentLines[index];
    const config = state.characterVoiceMap[line.role] || { agent_id: '', speed: 1.0, seed: 0, tts_capability_id: '', cloud_extra_params: '{}' };
    if (!_hasTtsConfig(config)) {
        showToast(`角色「${line.role}」尚未配置配音`, 'warning');
        state.isPlaying = false;
        updatePlayButton();
        state.currentPlayingIndex = -1;
        updatePlayingHighlight(-1);
        return;
    }
    await playLineById(line.id);
    state.isPlaying = false;
    state.currentPlayingIndex = -1;
    updatePlayButton();
    updatePlayingHighlight(-1);
}

function updatePlayerInfo() {
    if (state.currentPlayingIndex >= 0 && state.currentLines[state.currentPlayingIndex]) {
        const line = state.currentLines[state.currentPlayingIndex];
        document.getElementById('currentLineDisplay').textContent =
            `[${line.role}] ${line.content.substring(0, 50)}${line.content.length > 50 ? '...' : ''}`;
        document.getElementById('playProgress').textContent =
            `${state.currentPlayingIndex + 1} / ${state.currentLines.length}`;
    }
}

function expandLineAudioEditor(lineId) {
    document.querySelectorAll('.line-audio-editor').forEach(el => {
        el.classList.remove('expanded');
    });

    const editorEl = document.getElementById(`audioEditor-${lineId}`);
    if (editorEl) {
        editorEl.classList.add('expanded');
        setTimeout(() => {
            const editor = state.lineAudioStates[lineId];
            if (editor) {
                editor.resize();
                if (editor.hasAudio) {
                    if (!editor.loaded) {
                        loadLineWaveform(lineId);
                    }
                }
            }
        }, 100);
    }
}

function setupLineWaveform(line, parentEl) {
    const editor = new AudioEditor({
        wrapperId: `waveformWrapper-${line.id}`,
        canvasId: `waveformCanvas-${line.id}`,
        rangeId: `waveformRange-${line.id}`,
        startHandleId: `rangeStartHandle-${line.id}`,
        endHandleId: `rangeEndHandle-${line.id}`,
        progressId: `waveformProgress-${line.id}`,
        playheadId: `waveformPlayhead-${line.id}`,
        currentTimeId: `waveformCurrentTime-${line.id}`,
        totalTimeId: `waveformTotalTime-${line.id}`,
        rangeStartTimeId: `rangeStartTime-${line.id}`,
        rangeEndTimeId: `rangeEndTime-${line.id}`,
        scopeEl: parentEl
    });

    const estDuration = AudioEditor.estimateDuration(line.content.length);
    editor.data = AudioEditor.generateMockWaveform(line.content.length);
    editor.duration = estDuration;
    editor.hasAudio = !!line.audio_path;
    editor.adjustEnabled = !!(line.audio_adjust_enabled);
    if (line.audio_path) {
        editor.audioPath = AudioEditor.getAudioUrl(line.audio_path);
    }

    const savedRangeStart = parseFloat(line.range_start) || 0;
    const savedRangeEnd = parseFloat(line.range_end) || 0;
    if (savedRangeEnd > 0 && savedRangeStart < savedRangeEnd) {
        editor.rangeStart = savedRangeStart;
        editor.rangeEnd = savedRangeEnd;
    } else {
        editor.rangeEnd = estDuration;
    }

    editor.resize();

    // 从已保存数据初始化音频调整参数
    editor.volume = Math.round((line.audio_volume || 1) * 100);
    editor.pitch = line.audio_pitch || 0;
    editor.fadeIn = line.fade_in || 0;
    editor.fadeOut = line.fade_out || 0;

    // 区间变化时保存设置
    editor.onRangeChange = () => saveAudioSettings(line.id);

    state.lineAudioStates[line.id] = editor;
}

function loadLineWaveform(lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    const editor = state.lineAudioStates[lineId];
    if (!line || !editor || !line.audio_path) return;

    editor.loadWaveform(AudioEditor.getAudioUrl(line.audio_path)).then(() => {
        // 回显已保存的音频范围；无有效范围时归一化为全程
        const savedStart = parseFloat(line.range_start) || 0;
        const savedEnd = parseFloat(line.range_end) || 0;
        if (savedEnd > 0 && savedStart < savedEnd) {
            editor.setRange(savedStart, savedEnd);
        } else {
            editor.setRange(0, editor.duration);
        }
    }).catch(() => {});
}

function onAudioAdjustToggle(lineId, enabled) {
    const editor = state.lineAudioStates[lineId];
    if (editor) {
        editor.setAdjustEnabled(enabled);
    }

    document.querySelectorAll(`#audioEditor-${lineId} .line-param-slider`).forEach(slider => {
        slider.disabled = !enabled;
    });

    const resetBtn = document.getElementById(`resetBtn-${lineId}`);
    if (resetBtn) resetBtn.disabled = !enabled;

    saveAudioSettings(lineId);
}

function updateLineAudioEditorDisplay(lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (!line) return;

    const editor = state.lineAudioStates[lineId];
    if (!editor) return;

    const wrapper = document.getElementById(`waveformWrapper-${lineId}`);
    const overlay = document.getElementById(`waveformOverlay-${lineId}`);
    const timebar = document.querySelector(`#audioEditor-${lineId} .line-waveform-timebar`);
    const params = document.querySelector(`#audioEditor-${lineId} .line-audio-params`);

    // 音频调整控件的可用性须与初始渲染逻辑一致：
    // 开关依赖 audio_path，滑杆/重置按钮依赖 audio_path && audio_adjust_enabled
    const lineEl = document.querySelector(`.script-line[data-line-id="${lineId}"]`);
    const toggle = document.getElementById(`audioAdjustToggle-${lineId}`);
    const resetBtn = document.getElementById(`resetBtn-${lineId}`);
    const sliders = document.querySelectorAll(`#audioEditor-${lineId} .line-param-slider`);
    const adjustOn = !!line.audio_adjust_enabled;

    if (line.audio_path) {
        if (wrapper) wrapper.classList.remove('no-audio');
        if (timebar) timebar.classList.remove('no-audio');
        if (params) params.classList.remove('no-audio');
        if (overlay) overlay.style.display = 'none';
        if (lineEl) lineEl.classList.add('has-audio');

        if (toggle) {
            toggle.disabled = false;
            toggle.checked = adjustOn;
        }
        sliders.forEach(slider => { slider.disabled = !adjustOn; });
        if (resetBtn) resetBtn.disabled = !adjustOn;
        editor.adjustEnabled = adjustOn;
        editor.hasAudio = true;

        // 同步播放按钮：有音频时启用播放/停止
        const playBtnContainer = document.querySelector(`#audioEditor-${lineId} .line-param-play-btn`);
        if (playBtnContainer) {
            playBtnContainer.innerHTML = `
                <button class="audio-icon-btn play-inline-btn" onclick="playLineAudio(${lineId})" id="playBtn-${lineId}" title="播放">
                    <i class="fas fa-play"></i>
                </button>
                <button class="audio-icon-btn play-inline-btn" onclick="stopLineAudio(${lineId})" id="stopBtn-${lineId}" title="停止" style="display:none;">
                    <i class="fas fa-stop"></i>
                </button>
            `;
        }

        const audioUrl = AudioEditor.getAudioUrl(line.audio_path);
        if (editor.audioPath !== audioUrl) {
            // 音频源已变更：停止当前播放并清除旧路径，防止 editor.play() 使用过期音频
            if (editor._lineStopFn) { editor._lineStopFn(); editor._lineStopFn = null; }
            editor.stop();
            editor.audioPath = '';
            editor.loaded = false;
        }
        // 始终从 DB（line 对象）恢复调整参数
        // 此函数只在匹配/生成后调用，line 中的参数始终是最新的
        const savedAdjust = !!line.audio_adjust_enabled;
        const savedVolume = Math.round((line.audio_volume || 1) * 100);
        const savedPitch = line.audio_pitch || 0;
        const savedFadeIn = line.fade_in || 0;
        const savedFadeOut = line.fade_out || 0;

        editor.adjustEnabled = savedAdjust;
        editor.volume = savedVolume;
        editor.pitch = savedPitch;
        editor.fadeIn = savedFadeIn;
        editor.fadeOut = savedFadeOut;

        const uiValues = [
            { id: 'volume', val: savedVolume, suffix: '%' },
            { id: 'pitch', val: savedPitch, suffix: '' },
            { id: 'fadeIn', val: savedFadeIn, suffix: 's' },
            { id: 'fadeOut', val: savedFadeOut, suffix: 's' },
        ];
        for (const { id, val, suffix } of uiValues) {
            const el = document.getElementById(`${id}Value-${lineId}`);
            if (el) el.textContent = suffix ? val + suffix : val;
            const slider = document.getElementById(`${id}Slider-${lineId}`);
            if (slider) slider.value = val;
        }

        if (toggle) { toggle.checked = savedAdjust; toggle.disabled = false; }
        sliders.forEach(s => { s.disabled = !savedAdjust; });
        if (resetBtn) resetBtn.disabled = !savedAdjust;
        if (!editor.loaded) {
            loadLineWaveform(lineId);
        }
    } else {
        // 无音频：重置编辑器所有视觉状态（使用 AudioEditor 缓存的 DOM 引用）
        if (editor._lineStopFn) {
            editor._lineStopFn();
            editor._lineStopFn = null;
        }
        editor.resetVisual();

        // 重置外层容器样式
        if (wrapper) wrapper.classList.add('no-audio');
        if (timebar) timebar.classList.add('no-audio');
        if (params) params.classList.add('no-audio');
        if (overlay) overlay.style.display = 'flex';
        if (lineEl) lineEl.classList.remove('has-audio');

        // 重置滑杆 UI 值（ID 使用驼峰命名：fadeIn/fadeOut）
        const sliderDefaults = [
            { id: 'volume', val: 100, suffix: '%' },
            { id: 'pitch', val: 0, suffix: '' },
            { id: 'fadeIn', val: 0, suffix: 's' },
            { id: 'fadeOut', val: 0, suffix: 's' },
        ];
        for (const { id, val, suffix } of sliderDefaults) {
            const valueEl = document.getElementById(`${id}Value-${lineId}`);
            if (valueEl) valueEl.textContent = suffix ? val + suffix : val;
            const sliderEl = document.getElementById(`${id}Slider-${lineId}`);
            if (sliderEl) sliderEl.value = val;
        }
        // 重置调整开关和控件
        if (toggle) { toggle.checked = false; toggle.disabled = true; }
        sliders.forEach(slider => { slider.disabled = true; });
        if (resetBtn) resetBtn.disabled = true;

        // 同步播放按钮：无音频时禁用
        const playBtnContainer = document.querySelector(`#audioEditor-${lineId} .line-param-play-btn`);
        if (playBtnContainer) {
            playBtnContainer.innerHTML = `
                <button class="audio-icon-btn play-inline-btn" disabled title="请先生成配音">
                    <i class="fas fa-play"></i>
                </button>
            `;
        }
    }
}

function updateLineAudioDisplay(lineId, type, value) {
    const el = document.getElementById(`${type}Value-${lineId}`);
    if (!el) return;
    if (type === 'volume') {
        el.textContent = value + '%';
    } else if (type === 'pitch') {
        el.textContent = value;
    } else if (type === 'fadeIn') {
        el.textContent = parseFloat(value).toFixed(1) + 's';
    } else if (type === 'fadeOut') {
        el.textContent = parseFloat(value).toFixed(1) + 's';
    }

    const editor = state.lineAudioStates[lineId];
    if (editor) {
        editor[type] = parseFloat(value);
    }
}

function onLineSeedChange(lineId, value) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (!line) return;
    const seed = parseInt(value) || 0;
    line.seed = seed;
    updateLine(lineId, { seed: seed });
    matchAudioHistoryForLines([line]).then(() => {
        updateLineAudioEditorDisplay(lineId);
    });
}

function onLineAudioParamChange(lineId, type, value) {
    const key = `${lineId}_${type}`;
    const newVal = parseFloat(value);
    if (state.lineAudioParamLastValues[key] === newVal) return;
    state.lineAudioParamLastValues[key] = newVal;
    saveAudioSettings(lineId);
}

function resetLineAudioParams(lineId) {
    const lineState = state.lineAudioStates[lineId];
    if (!lineState) return;

    const defaults = {
        volume: 100,
        pitch: 0,
        fadeIn: 0,
        fadeOut: 0
    };

    for (const [key, val] of Object.entries(defaults)) {
        const sliderId = key === 'fadeIn' ? 'fadeInSlider' : key === 'fadeOut' ? 'fadeOutSlider' : `${key.charAt(0).toUpperCase() + key.slice(1)}Slider`;
        const slider = document.getElementById(`${sliderId}-${lineId}`);
        if (slider) {
            slider.value = val;
        }
        updateLineAudioDisplay(lineId, key, val);
        const lastKey = `${lineId}_${key}`;
        state.lineAudioParamLastValues[lastKey] = val;
    }

    const editor = state.lineAudioStates[lineId];
    if (editor) {
        editor.resetRange();
    }

    saveAudioSettings(lineId);
    showToast('参数已重置', 'success');
}

async function saveAudioSettings(lineId) {
    const editor = state.lineAudioStates[lineId];
    if (!editor) return;

    // 同步到台词对象，保证后续重新加载波形时能回显最新范围
    const line = state.currentLines.find(l => l.id === lineId);
    if (line) {
        line.range_start = editor.rangeStart || 0;
        line.range_end = editor.rangeEnd || 0;
        line.audio_adjust_enabled = editor.adjustEnabled ? 1 : 0;
    }

    try {
        await apiRequest(`/api/audio/save-audio-settings?line_id=${lineId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                volume: editor.volume || 100,
                pitch: editor.pitch || 0,
                fade_in: editor.fadeIn || 0,
                fade_out: editor.fadeOut || 0,
                audio_adjust_enabled: editor.adjustEnabled ? 1 : 0,
                range_start: editor.rangeStart || 0,
                range_end: editor.rangeEnd || 0
            }),
            silent: true
        });
    } catch (e) {
        console.error('保存音频设置失败:', e);
    }
}

async function generateLineAudio(lineId) {
    const line = state.currentLines.find(l => l.id === lineId);
    if (!line) return;
    
    const btn = document.getElementById(`generateBtn-${lineId}`);
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    
    try {
        const response = await fetch(`/api/audio/generate-and-save?line_id=${lineId}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || '生成失败');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            
            for (const lineStr of lines) {
                if (!lineStr.trim()) continue;
                try {
                    const msg = JSON.parse(lineStr);
                    if (msg.type === 'finish') {
                        if (msg.audio_path) {
                            line.audio_path = msg.audio_path;
                            const lineEl = document.querySelector(`.script-line[data-line-id="${lineId}"]`);
                            if (lineEl) lineEl.classList.add('has-audio');

                            const overlay = document.getElementById(`waveformOverlay-${lineId}`);
                            if (overlay) overlay.remove();

                            const wrapper = document.getElementById(`waveformWrapper-${lineId}`);
                            if (wrapper) wrapper.classList.remove('no-audio');

                            const timebar = document.querySelector(`#audioEditor-${lineId} .line-waveform-timebar`);
                            if (timebar) timebar.classList.remove('no-audio');

                            const paramsEl = document.querySelector(`#audioEditor-${lineId} .line-audio-params`);
                            if (paramsEl) paramsEl.classList.remove('no-audio');

                            const playBtnContainer = document.querySelector(`#audioEditor-${lineId} .line-param-play-btn`);
                            if (playBtnContainer) {
                                playBtnContainer.innerHTML = `
                                    <button class="audio-icon-btn play-inline-btn" onclick="playLineAudio(${lineId})" id="playBtn-${lineId}" title="播放">
                                        <i class="fas fa-play"></i>
                                    </button>
                                    <button class="audio-icon-btn play-inline-btn" onclick="stopLineAudio(${lineId})" id="stopBtn-${lineId}" title="停止" style="display:none;">
                                        <i class="fas fa-stop"></i>
                                    </button>
                                `;
                            }

                            updateLineAudioEditorDisplay(lineId);
                        }
                        showToast('配音生成成功', 'success');
                    } else if (msg.type === 'error') {
                        showToast(msg.message || '生成失败', 'error');
                    }
                } catch (e) { /* ignore parse errors */ }
            }
        }
    } catch (e) {
        console.error('生成音频失败:', e);
        showToast('生成失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-microphone"></i>';
    }
}

async function playLineAudio(lineId) {
    const editor = state.lineAudioStates[lineId];
    if (!editor || !editor.hasAudio) return;

    const btn = document.getElementById(`playBtn-${lineId}`);
    const stopBtn = document.getElementById(`stopBtn-${lineId}`);
    if (btn) btn.style.display = 'none';
    if (stopBtn) stopBtn.style.display = 'flex';

    const onEnd = () => {
        if (btn) btn.style.display = 'flex';
        if (stopBtn) stopBtn.style.display = 'none';
    };

    if (editor.adjustEnabled) {
        // 启用音频编辑时，通过后端接口获取处理后的音频（音量/变调/淡入淡出/区间）
        try {
            const resp = await fetch(`/api/audio/play-with-settings?line_id=${lineId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    range_start: editor.rangeStart || 0,
                    range_end: editor.rangeEnd || 0,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                showToast(err.detail || '播放失败', 'error');
                onEnd();
                return;
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let sampleRate = 24000;
            let startTime = 0;
            let duration = 0;
            let animFrameId = null;
            let localCtx = null;
            let localSources = [];
            let stopped = false;

            // 创建独立的 AudioContext 用于单行播放
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            localCtx = audioContext;
            let nextPlayTime = audioContext.currentTime;

            // 进度更新动画
            const updateProgressLoop = () => {
                if (stopped || !localCtx) return;
                const elapsed = localCtx.currentTime - startTime;
                editor.currentTime = editor.rangeStart + elapsed;
                if (editor.currentTime >= editor.rangeEnd) {
                    editor.currentTime = editor.rangeEnd;
                    editor.updateProgress();
                    if (!stopped) {
                        stopped = true;
                        onEnd();
                    }
                    return;
                }
                editor.updateProgress();
                animFrameId = requestAnimationFrame(updateProgressLoop);
            };

            // 覆盖 editor.stop 以支持中断此流式播放
            editor._lineStopFn = () => {
                stopped = true;
                if (animFrameId) cancelAnimationFrame(animFrameId);
                for (const src of localSources) {
                    try { src.stop(); } catch(e) {}
                }
                if (localCtx) localCtx.close();
                localCtx = null;
                try { reader.cancel(); } catch(e) {}
            };

            while (true) {
                const { done, value } = await reader.read();
                if (done || stopped) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const lineStr of lines) {
                    if (!lineStr.trim()) continue;
                    try {
                        const msg = JSON.parse(lineStr);
                        if (msg.type === 'start') {
                            sampleRate = msg.sample_rate || 24000;
                            startTime = audioContext.currentTime;
                            updateProgressLoop();
                        } else if (msg.type === 'pcm_chunk') {
                            if (stopped) return;
                            const pcmData = new Int16Array(base64ToArrayBuffer(msg.data));
                            const sr = msg.sample_rate || sampleRate;

                            const buf = audioContext.createBuffer(1, pcmData.length, sr);
                            const ch = buf.getChannelData(0);
                            for (let i = 0; i < pcmData.length; i++) {
                                ch[i] = pcmData[i] / 32768;
                            }
                            const source = audioContext.createBufferSource();
                            source.buffer = buf;
                            source.connect(audioContext.destination);
                            if (nextPlayTime > audioContext.currentTime) {
                                source.start(nextPlayTime);
                            } else {
                                source.start();
                            }
                            nextPlayTime += buf.duration;
                            localSources.push(source);
                            source.onended = () => {
                                const idx = localSources.indexOf(source);
                                if (idx >= 0) localSources.splice(idx, 1);
                            };
                        } else if (msg.type === 'finish') {
                            duration = nextPlayTime - startTime;
                        } else if (msg.type === 'error') {
                            showToast(`播放错误: ${msg.message}`, 'error');
                            stopped = true;
                        }
                    } catch (e) { /* ignore parse errors */ }
                }
            }

            // 等待所有已调度的音频播放完毕
            if (!stopped) {
                while (localSources.length > 0 && !stopped) {
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
                if (!stopped) {
                    stopped = true;
                    if (animFrameId) cancelAnimationFrame(animFrameId);
                    onEnd();
                }
            }

            editor._lineStopFn = null;
        } catch (e) {
            console.error('播放失败:', e);
            showToast('播放失败', 'error');
            editor._lineStopFn = null;
            onEnd();
        }
    } else {
        // 未启用音频编辑时，直接播放原始音频
        editor.onPlayEnd = onEnd;
        editor.play();
    }
}

function stopLineAudio(lineId) {
    const editor = state.lineAudioStates[lineId];
    if (!editor) return;

    // 优先使用流式播放的中断函数
    if (editor._lineStopFn) {
        editor._lineStopFn();
        editor._lineStopFn = null;
    } else {
        editor.stop();
    }

    const btn = document.getElementById(`playBtn-${lineId}`);
    const stopBtn = document.getElementById(`stopBtn-${lineId}`);
    if (btn) btn.style.display = 'flex';
    if (stopBtn) stopBtn.style.display = 'none';
}

function base64ToArrayBuffer(base64) {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
}

function playPCMChunk(pcmData, sampleRate) {
    if (!state.audioContext) {
        state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    const audioContext = state.audioContext;
    const buffer = audioContext.createBuffer(1, pcmData.length, sampleRate);
    const data = buffer.getChannelData(0);

    for (let i = 0; i < pcmData.length; i++) {
        data[i] = pcmData[i] / 32768;
    }

    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);

    if (state.nextPlayTime === 0) {
        state.nextPlayTime = audioContext.currentTime;
    }

    if (state.nextPlayTime > audioContext.currentTime) {
        source.start(state.nextPlayTime);
        state.nextPlayTime += buffer.duration;
    } else {
        source.start();
        state.nextPlayTime = audioContext.currentTime + buffer.duration;
    }

    state.activeSources.push(source);
    source.onended = () => {
        const idx = state.activeSources.indexOf(source);
        if (idx >= 0) state.activeSources.splice(idx, 1);
    };
}

function stopStreamPlayer() {
    for (const src of state.streamPlayQueue) {
        try { src.stop(); } catch(e) {}
    }
    state.streamPlayQueue = [];
    state.streamIsPlaying = false;
    state.streamFinished = false;
    state.streamCurrentSource = null;
    if (state.streamResolve) {
        state.streamResolve();
        state.streamResolve = null;
    }
}

function formatDuration(seconds) {
    if (!seconds || isNaN(seconds)) return '--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

async function matchAudioHistoryForLines(lines) {
    if (!lines || lines.length === 0) return;

    const batchData = [];
    for (const line of lines) {
        const config = state.characterVoiceMap[line.role] || { agent_id: '', speed: 1.0, seed: 0, tts_capability_id: '', cloud_extra_params: '{}' };
        
        if (!_hasTtsConfig(config)) {
            line.audio_path = '';
            continue;
        }

        // 使用当前角色配置进行匹配（切换智能体/能力后 config 已是新值）
        const effectiveSeed = (line.seed || 0) !== 0 ? line.seed : (config.seed || 0);
        batchData.push({
            line_id: line.id,
            content: line.content || '',
            role: line.role || '',
            tone: line.tone || '',
            instruction: line.instruction || '',
            agent_id: config.agent_id || '',
            tts_capability_id: config.tts_capability_id || '',
            seed: effectiveSeed,
        });
    }

    if (batchData.length === 0) return;

    try {
        const data = await apiRequest('/api/audio/history/batch-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lines: batchData }),
            silent: true
        });
        if (data.success && data.matches) {
            for (const line of lines) {
                const match = data.matches[line.id];
                if (match && match.audio_path) {
                    line.audio_path = match.audio_path;
                    // 从音频历史恢复该音频的调整参数（参数绑定在音频上）
                    line.audio_volume = match.audio_volume != null ? match.audio_volume : 1;
                    line.audio_pitch = match.audio_pitch || 0;
                    line.fade_in = match.fade_in || 0;
                    line.fade_out = match.fade_out || 0;
                    line.audio_adjust_enabled = match.audio_adjust_enabled || 0;
                    line.range_start = match.range_start || 0;
                    line.range_end = match.range_end || 0;
                    updateAudioStatusDot(line.id, 'generated');
                } else {
                    line.audio_path = '';
                    updateAudioStatusDot(line.id, 'none');
                }
            }
        } else {
            for (const line of lines) {
                line.audio_path = '';
            }
        }
    } catch (e) {
        console.error('批量匹配音频历史失败:', e);
        for (const line of lines) {
            line.audio_path = '';
        }
    }
}