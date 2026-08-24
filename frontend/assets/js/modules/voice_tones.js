const toneAudioStates = {};
let _toneIdCounter = 0;

function _genToneId() {
    return 'tone_' + (++_toneIdCounter);
}

function addVoiceToneItem(containerId, toneName = '', promptText = '', voicePath = '', originalPath = '', savedRangeStart = 0, savedRangeEnd = 0) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const item = document.createElement('div');
    item.className = 'voice-tone-item';
    const toneId = _genToneId();
    item.dataset.toneId = toneId;

    // 波形展示优先用原始完整音频（范围选择基于原始文件）
    const waveformPath = originalPath || voicePath;

    toneAudioStates[toneId] = {
        audio: null,
        audioUrl: null,
        file: null,
        voicePath: voicePath || '',
        originalPath: originalPath || '',
        duration: 0,
        rangeStart: 0,
        rangeEnd: 0,
        savedRangeStart: parseFloat(savedRangeStart) || 0,
        savedRangeEnd: parseFloat(savedRangeEnd) || 0,
        currentTime: 0,
        isPlaying: false,
        waveformData: [],
        canvas: null,
        ctx: null,
        path: '',
        size: '',
        sample_rate: 0,
        channels: 0
    };

    item.innerHTML = `
        <div class="tone-header">
            <input type="text" class="tone-name-input" value="${toneName.replace(/"/g, '&quot;')}"
                   placeholder="语气名称（如：平静、愤怒）">
            <button type="button" class="tone-remove-btn" onclick="removeVoiceToneItem(this)">
                <i class="fas fa-times"></i> 删除
            </button>
        </div>
        <div class="tone-audio-section">
            <div class="tone-audio-toolbar">
                <label class="tone-file-btn">
                    <i class="fas fa-upload"></i> 选择语音
                    <input type="file" accept="audio/*" style="display:none;" class="tone-file-input">
                </label>
                <button type="button" class="tone-play-btn" disabled title="试听">
                    <i class="fas fa-play"></i>
                </button>
                <span class="tone-file-name">${waveformPath ? '已有: ' + waveformPath.split(/[/\\]/).pop() : '未选择文件'}</span>
            </div>
            <div class="tone-waveform-wrapper" id="toneWrapper-${toneId}">
                <div class="tone-waveform-container">
                    <canvas class="tone-waveform-canvas" id="toneCanvas-${toneId}"></canvas>
                    <div class="tone-waveform-range" id="toneRange-${toneId}"></div>
                    <div class="tone-waveform-handle start" id="toneStartHandle-${toneId}"></div>
                    <div class="tone-waveform-handle end" id="toneEndHandle-${toneId}"></div>
                    <div class="tone-waveform-playhead" id="tonePlayhead-${toneId}"></div>
                </div>
            </div>
            <div class="tone-timebar">
                <div class="time-range">
                    开始: <input type="text" class="range-start-input" value="0.00" readonly> s
                </div>
                <div class="time-range">
                    结束: <input type="text" class="range-end-input" value="0.00" readonly> s
                </div>
                <div class="time-range">
                    时长: <span class="range-duration">0.00</span> s
                </div>
            </div>
        </div>
        <div class="tone-prompt-row">
            <input type="text" class="tone-text-input" maxlength="50" placeholder="语音对应的文字内容（最多50字）"
                   value="${promptText.replace(/"/g, '&quot;').replace(/</g, '&lt;')}">
            <button type="button" class="tone-asr-btn" title="识别语音内容并自动填入">
                <i class="fas fa-microphone"></i> 自动识别
            </button>
            <span class="tone-char-count">${promptText.length}/50</span>
        </div>
    `;

    const fileInput = item.querySelector('.tone-file-input');
    const playBtn = item.querySelector('.tone-play-btn');
    const canvas = item.querySelector('.tone-waveform-canvas');
    const nameInput = item.querySelector('.tone-name-input');
    const textInput = item.querySelector('.tone-text-input');
    const charCount = item.querySelector('.tone-char-count');
    const asrBtn = item.querySelector('.tone-asr-btn');

    fileInput.addEventListener('change', (e) => handleToneFileSelect(e, toneId));
    playBtn.addEventListener('click', () => toggleTonePlay(toneId));
    asrBtn.addEventListener('click', () => recognizeToneText(toneId));
    textInput.addEventListener('input', (e) => {
        charCount.textContent = e.target.value.length + '/50';
    });

    container.appendChild(item);

    // 创建 AudioEditor 实例
    const editor = new AudioEditor({
        wrapperId: `toneWrapper-${toneId}`,
        canvasId: `toneCanvas-${toneId}`,
        rangeId: `toneRange-${toneId}`,
        startHandleId: `toneStartHandle-${toneId}`,
        endHandleId: `toneEndHandle-${toneId}`,
        progressId: '',
        playheadId: `tonePlayhead-${toneId}`,
        currentTimeId: '',
        totalTimeId: '',
        rangeStartTimeId: '',
        rangeEndTimeId: '',
        scopeEl: item
    });
    editor.adjustEnabled = true;

    editor.onLoad = () => {
        playBtn.disabled = false;
        // 加载完成后同步区间到时间输入框
        if (editor.onRangeChange) editor.onRangeChange(editor.rangeStart, editor.rangeEnd);
    };
    editor.onRangeChange = (start, end) => {
        const rangeStartInput = item.querySelector('.range-start-input');
        const rangeEndInput = item.querySelector('.range-end-input');
        const durationSpan = item.querySelector('.range-duration');
        if (rangeStartInput) rangeStartInput.value = start.toFixed(2);
        if (rangeEndInput) rangeEndInput.value = end.toFixed(2);
        if (durationSpan) durationSpan.textContent = (end - start).toFixed(2);
    };

    toneAudioStates[toneId].editor = editor;

    if (waveformPath) {
        editor.loadWaveform(AudioEditor.getAudioUrl(waveformPath)).then(() => {
            const ts = toneAudioStates[toneId];
            if (!ts) return;
            // 回显已保存的音频范围；无有效范围时默认全程
            let start = ts.savedRangeStart;
            let end = ts.savedRangeEnd;
            if (!(end > 0 && end > start)) {
                start = 0;
                end = editor.duration || 0;
            }
            editor.setRange(start, end);
            ts.rangeStart = editor.rangeStart;
            ts.rangeEnd = editor.rangeEnd;
            if (editor.onRangeChange) editor.onRangeChange(editor.rangeStart, editor.rangeEnd);
        }).catch(() => {});
    }
}

function removeVoiceToneItem(btn) {
    const item = btn.closest('.voice-tone-item');
    if (!item) return;
    const toneId = item.dataset.toneId;
    if (toneId && toneAudioStates[toneId]) {
        const ts = toneAudioStates[toneId];
        if (ts.editor) {
            ts.editor.stop();
        }
        if (ts.audioUrl) {
            URL.revokeObjectURL(ts.audioUrl);
            ts.audioUrl = null;
        }
        delete toneAudioStates[toneId];
    }
    item.remove();
}

function handleToneFileSelect(event, toneId) {
    const file = event.target.files[0];
    if (!file) return;

    const ts = toneAudioStates[toneId];
    if (!ts || !ts.editor) return;

    if (ts.editor) {
        ts.editor.stop();
    }
    if (ts.audioUrl) {
        URL.revokeObjectURL(ts.audioUrl);
    }

    ts.file = file;
    ts.audioUrl = URL.createObjectURL(file);
    ts.voicePath = '';
    ts.originalPath = '';
    ts.savedRangeStart = 0;
    ts.savedRangeEnd = 0;
    ts.size = (file.size / 1024).toFixed(1) + 'KB';

    // 重置编辑器状态
    ts.editor.hasAudio = false;
    ts.editor.loaded = false;
    ts.editor.data = [];
    ts.editor.duration = 0;
    ts.editor.audioPath = '';

    const item = document.querySelector(`.voice-tone-item[data-tone-id="${toneId}"]`);
    if (item) {
        const fileNameEl = item.querySelector('.tone-file-name');
        fileNameEl.textContent = file.name;
        const playBtn = item.querySelector('.tone-play-btn');
        if (playBtn) playBtn.disabled = true;
    }

    ts.editor.loadWaveform(ts.audioUrl).catch(() => {});
}

function toggleTonePlay(toneId) {
    const ts = toneAudioStates[toneId];
    if (!ts || !ts.editor || !ts.editor.hasAudio) return;

    const item = document.querySelector(`.voice-tone-item[data-tone-id="${toneId}"]`);
    const playBtn = item ? item.querySelector('.tone-play-btn') : null;

    if (ts.editor.isPlaying) {
        ts.editor.stop();
        if (playBtn) playBtn.innerHTML = '<i class="fas fa-play"></i>';
    } else {
        ts.editor.onPlayEnd = () => {
            if (playBtn) playBtn.innerHTML = '<i class="fas fa-play"></i>';
        };
        ts.editor.play();
        if (playBtn) playBtn.innerHTML = '<i class="fas fa-pause"></i>';
    }
}

async function recognizeToneText(toneId) {
    const ts = toneAudioStates[toneId];
    if (!ts) return;

    const item = document.querySelector(`.voice-tone-item[data-tone-id="${toneId}"]`);
    if (!item) return;
    const asrBtn = item.querySelector('.tone-asr-btn');
    const textInput = item.querySelector('.tone-text-input');
    const charCount = item.querySelector('.tone-char-count');

    // 优先用新选择的文件，否则下载已有音频字节转为上传文件
    let audioFile = ts.file;
    if (!audioFile) {
        const path = ts.originalPath || ts.voicePath;
        if (!path) {
            showToast('请先选择语音文件', 'warning');
            return;
        }
        try {
            const resp = await fetch(AudioEditor.getAudioUrl(path));
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const blob = await resp.blob();
            const ext = (path.split('.').pop() || 'wav').toLowerCase();
            audioFile = new File([blob], `tone_audio.${ext}`, { type: blob.type || 'audio/wav' });
        } catch (e) {
            console.error('读取音频文件失败:', e);
            showToast('音频文件读取失败', 'error');
            return;
        }
    }

    // 按当前选中的音频范围识别
    const editor = ts.editor;
    const rangeStart = editor && editor.hasAudio ? editor.rangeStart : 0;
    const rangeEnd = editor && editor.hasAudio ? editor.rangeEnd : 0;

    const formData = new FormData();
    formData.append('audio', audioFile);
    formData.append('range_start', String(rangeStart || 0));
    formData.append('range_end', String(rangeEnd || 0));
    formData.append('force_simplified', 'true');

    if (asrBtn) {
        asrBtn.disabled = true;
        asrBtn.classList.add('loading');
        asrBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 识别中';
    }

    try {
        const result = await apiRequest('/api/asr/transcribe', {
            method: 'POST',
            body: formData,
            errorPrefix: '识别失败'
        });
        if (result.success && result.text) {
            let text = result.text;
            if (text.length > 50) {
                text = text.slice(0, 50);
                showToast('识别结果超过50字，已自动截断', 'warning');
            }
            textInput.value = text;
            if (charCount) charCount.textContent = text.length + '/50';
            showToast('语音识别完成', 'success');
        } else {
            showToast('未识别到有效文字内容', 'warning');
        }
    } catch (e) {
        console.error('语音识别失败:', e);
        showToast('语音识别失败: ' + (e.message || e), 'error');
    } finally {
        if (asrBtn) {
            asrBtn.disabled = false;
            asrBtn.classList.remove('loading');
            asrBtn.innerHTML = '<i class="fas fa-microphone"></i> 自动识别';
        }
    }
}