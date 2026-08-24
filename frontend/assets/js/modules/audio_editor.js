/**
 * AudioEditor - 可复用的音频波形编辑组件
 * 
 * 功能：
 * - 波形可视化（Canvas 绘制）
 * - WAV 文件解析
 * - 播放/停止控制（支持区间播放）
 * - 区间选择（拖拽 handle）
 * - 进度跟踪（播放头 + 进度条）
 * - 自适应尺寸（DPR 感知）
 * 
 * 使用方式：
 * const editor = new AudioEditor({
 *     wrapperId: 'waveformWrapper-1',
 *     canvasId: 'waveformCanvas-1',
 *     rangeId: 'waveformRange-1',
 *     startHandleId: 'rangeStartHandle-1',
 *     endHandleId: 'rangeEndHandle-1',
 *     progressId: 'waveformProgress-1',
 *     playheadId: 'waveformPlayhead-1',
 *     currentTimeId: 'waveformCurrentTime-1',
 *     totalTimeId: 'waveformTotalTime-1',
 *     rangeStartTimeId: 'rangeStartTime-1',
 *     rangeEndTimeId: 'rangeEndTime-1'
 * });
 * 
 * await editor.loadWaveform('/api/media/file/content?path=audio.wav');
 * editor.play();
 */

class AudioEditor {
    /**
     * @param {Object} config - 配置对象
     * @param {string} config.wrapperId - 波形容器元素 ID
     * @param {string} config.canvasId - Canvas 元素 ID
     * @param {string} [config.rangeId] - 区间高亮元素 ID
     * @param {string} [config.startHandleId] - 起始拖拽 handle ID
     * @param {string} [config.endHandleId] - 结束拖拽 handle ID
     * @param {string} [config.progressId] - 进度条元素 ID
     * @param {string} [config.playheadId] - 播放头元素 ID
     * @param {string} [config.currentTimeId] - 当前时间显示元素 ID
     * @param {string} [config.totalTimeId] - 总时长显示元素 ID
     * @param {string} [config.rangeStartTimeId] - 区间起始时间显示元素 ID
     * @param {string} [config.rangeEndTimeId] - 区间结束时间显示元素 ID
     * @param {HTMLElement} [config.scopeEl] - 作用域元素（用于查找子元素，可选）
     */
    constructor(config) {
        this.config = config;
        
        // 状态
        this.canvas = null;
        this.ctx = null;
        this.data = [];
        this.duration = 0;
        this.currentTime = 0;
        this.rangeStart = 0;
        this.rangeEnd = 0;
        this.hasAudio = false;
        this.loaded = false;
        this.audioPath = '';
        this.adjustEnabled = false;
        this.isPlaying = false;
        this.zoom = 1;
        this.audio = null;
        
        // 查找 DOM 元素
        this._findElements();
        
        // 初始化交互
        if (this.canvas) {
            this._setupInteraction();
        }
    }
    
    /**
     * 查找 DOM 元素
     */
    _findElements() {
        const scope = this.config.scopeEl || document;
        const findById = (id) => id ? scope.querySelector(`#${id}`) : null;
        
        this.canvas = findById(this.config.canvasId);
        if (this.canvas) {
            this.ctx = this.canvas.getContext('2d');
        }
        
        this.wrapper = findById(this.config.wrapperId);
        this.rangeEl = findById(this.config.rangeId);
        this.startHandleEl = findById(this.config.startHandleId);
        this.endHandleEl = findById(this.config.endHandleId);
        this.progressEl = findById(this.config.progressId);
        this.playheadEl = findById(this.config.playheadId);
        this.currentTimeEl = findById(this.config.currentTimeId);
        this.totalTimeEl = findById(this.config.totalTimeId);
        this.rangeStartTimeEl = findById(this.config.rangeStartTimeId);
        this.rangeEndTimeEl = findById(this.config.rangeEndTimeId);
    }
    
    /**
     * 初始化交互事件
     */
    _setupInteraction() {
        if (!this.canvas) return;
        
        // 点击波形跳转播放位置
        this.canvas.addEventListener('click', (e) => {
            if (!this.hasAudio || this.duration === 0) return;
            
            const refEl = this.wrapper || this.canvas.parentElement;
            if (!refEl) return;
            const rect = refEl.getBoundingClientRect();
            if (rect.width <= 0) return;
            
            const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            this.currentTime = ratio * this.duration;
            
            // 限制在区间内
            if (this.currentTime < this.rangeStart) this.currentTime = this.rangeStart;
            if (this.currentTime > this.rangeEnd) this.currentTime = this.rangeEnd;
            
            this.updateProgress();
        });
        
        // 拖拽 handle
        this._setupHandleDrag(this.startHandleEl, 'start');
        this._setupHandleDrag(this.endHandleEl, 'end');
    }
    
    /**
     * 设置 handle 拖拽
     */
    _setupHandleDrag(handle, type) {
        if (!handle) return;
        
        let isDragging = false;
        
        const onStart = (e) => {
            e.preventDefault();
            e.stopPropagation();
            isDragging = true;
            handle.classList.add('dragging');
            
            const moveHandler = (ev) => {
                if (!isDragging) return;
                
                const refEl = this.wrapper || this.canvas.parentElement;
                if (!refEl) return;
                const rect = refEl.getBoundingClientRect();
                if (rect.width <= 0) return;
                
                const clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
                const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
                const time = ratio * this.duration;
                
                if (type === 'start') {
                    this.rangeStart = Math.min(time, this.rangeEnd - 0.1);
                } else {
                    this.rangeEnd = Math.max(time, this.rangeStart + 0.1);
                }
                
                this._updateRangeUI();
            };
            
            const endHandler = () => {
                if (!isDragging) return;
                isDragging = false;
                handle.classList.remove('dragging');
                
                document.removeEventListener('mousemove', moveHandler);
                document.removeEventListener('mouseup', endHandler);
                document.removeEventListener('touchmove', moveHandler);
                document.removeEventListener('touchend', endHandler);
                
                // 触发区间变化回调
                if (this.onRangeChange) {
                    this.onRangeChange(this.rangeStart, this.rangeEnd);
                }
            };
            
            document.addEventListener('mousemove', moveHandler);
            document.addEventListener('mouseup', endHandler);
            document.addEventListener('touchmove', moveHandler);
            document.addEventListener('touchend', endHandler);
        };
        
        handle.addEventListener('mousedown', onStart);
        handle.addEventListener('touchstart', onStart);
    }
    
    /**
     * 加载音频波形
     * @param {string} audioPath - 音频文件路径或 URL
     */
    async loadWaveform(audioPath) {
        if (!audioPath) return;
        
        // 若音频路径未变，保存当前区间和播放位置以便恢复
        const isSameAudio = this.audioPath === audioPath;
        const savedRangeStart = isSameAudio ? this.rangeStart : 0;
        const savedRangeEnd = isSameAudio ? this.rangeEnd : 0;
        const savedCurrentTime = isSameAudio ? this.currentTime : 0;
        
        try {
            const response = await fetch(audioPath);
            if (!response.ok) {
                throw new Error(`音频文件加载失败: ${response.status}`);
            }
            
            const arrayBuffer = await response.arrayBuffer();
            
            // 使用 Web Audio API 解码，支持 WAV/MP3/OGG 等所有浏览器支持的格式
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const audioCtx = new AudioCtx();
            const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
            audioCtx.close();
            
            const duration = audioBuffer.duration;
            const sampleRate = audioBuffer.sampleRate;
            
            // 提取 PCM 数据（取第一个通道，归一化到 [-1, 1]）
            const channelData = audioBuffer.getChannelData(0);
            const pcmSamples = new Float32Array(channelData.length);
            for (let i = 0; i < channelData.length; i++) {
                pcmSamples[i] = channelData[i];
            }
            
            // 降采样为波形峰值数据
            const numBars = 200;
            const blockSize = Math.max(1, Math.floor(pcmSamples.length / numBars));
            const waveformData = [];
            
            for (let i = 0; i < numBars; i++) {
                const start = i * blockSize;
                let maxVal = 0;
                for (let j = 0; j < blockSize && (start + j) < pcmSamples.length; j++) {
                    const abs = Math.abs(pcmSamples[start + j]);
                    if (abs > maxVal) maxVal = abs;
                }
                waveformData.push(maxVal);
            }
            
            // 归一化到 [0, 1]
            const maxVal = Math.max(...waveformData);
            if (maxVal > 0) {
                for (let i = 0; i < waveformData.length; i++) {
                    waveformData[i] = waveformData[i] / maxVal;
                }
            }
            
            // 更新状态
            this.data = waveformData;
            this.duration = duration;
            this.hasAudio = true;
            this.loaded = true;
            this.audioPath = audioPath;
            
            // 同一音频则恢复区间和播放位置，否则重置
            if (isSameAudio && savedRangeEnd > 0) {
                this.rangeStart = savedRangeStart;
                this.rangeEnd = savedRangeEnd;
                this.currentTime = savedCurrentTime;
            } else {
                this.rangeStart = 0;
                this.rangeEnd = duration;
                this.currentTime = 0;
            }
            
            // 更新总时长显示
            if (this.totalTimeEl) {
                this.totalTimeEl.textContent = AudioEditor.formatTime(this.duration);
            }
            
            // 重绘
            this.resize();
            this._updateRangeUI();
            this.updateProgress();
            
            // 触发加载完成回调
            if (this.onLoad) {
                this.onLoad(this.duration, this.audioPath);
            }
            
        } catch (e) {
            console.error('加载音频波形失败:', e);
            // 加载失败时重置状态
            this.hasAudio = false;
            this.loaded = false;
            throw e;
        }
    }
    
    /**
     * 调整尺寸（DPR 感知）
     */
    resize() {
        if (!this.canvas || !this.ctx) return;
        
        const wrapper = this.wrapper || this.canvas.parentElement;
        let width = 600;
        let height = 70;
        
        if (wrapper) {
            const rect = wrapper.getBoundingClientRect();
            if (rect.width > 0) {
                width = rect.width;
                height = rect.height;
            }
        }
        
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = width * dpr;
        this.canvas.height = height * dpr;
        this.canvas.style.width = '100%';
        this.canvas.style.height = '100%';
        
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        this.ctx.scale(dpr, dpr);
        
        this.drawWaveform();
    }
    
    /**
     * 绘制波形
     */
    drawWaveform() {
        if (!this.canvas || !this.ctx) return;
        
        const dpr = window.devicePixelRatio || 1;
        const width = this.canvas.width / dpr;
        const height = this.canvas.height / dpr;
        
        if (width <= 0 || height <= 0) return;
        
        this.ctx.clearRect(0, 0, width, height);
        
        if (this.data.length === 0) {
            this._drawEmptyWaveform(this.ctx, width, height);
            return;
        }
        
        const barWidth = 2;
        const gap = 1;
        const totalBarWidth = barWidth + gap;
        const totalBars = Math.max(1, Math.floor(width / totalBarWidth));
        
        const centerY = height / 2;
        const maxHeight = height * 0.75;
        
        const rangeStartRatio = this.duration > 0 ? this.rangeStart / this.duration : 0;
        const rangeEndRatio = this.duration > 0 ? this.rangeEnd / this.duration : 1;
        
        for (let i = 0; i < totalBars; i++) {
            const ratio = totalBars > 1 ? i / (totalBars - 1) : 0;
            const dataIndex = Math.min(Math.floor(ratio * (this.data.length - 1)), this.data.length - 1);
            const value = this.data[dataIndex];
            const barHeight = Math.max(2, value * maxHeight);
            
            const x = i * totalBarWidth;
            const topY = centerY - barHeight / 2;
            
            const barRatio = i / totalBars;
            if (barRatio >= rangeStartRatio && barRatio <= rangeEndRatio) {
                this.ctx.fillStyle = '#6c5ce7';
            } else {
                this.ctx.fillStyle = '#c5cbd6';
            }
            
            this.ctx.fillRect(x, topY, barWidth, barHeight);
        }
    }
    
    /**
     * 绘制空波形占位符
     */
    _drawEmptyWaveform(ctx, width, height) {
        ctx.strokeStyle = '#c5cbd6';
        ctx.lineWidth = 1;
        const centerY = height / 2;
        
        for (let i = 0; i < 40; i++) {
            const x = (i / 40) * width;
            const waveHeight = Math.sin(i * 0.5) * 8;
            ctx.beginPath();
            ctx.moveTo(x, centerY - waveHeight);
            ctx.lineTo(x, centerY + waveHeight);
            ctx.stroke();
        }
    }
    
    /**
     * 播放音频（支持区间播放）
     */
    play() {
        if (!this.hasAudio || !this.audioPath) return;
        
        // 停止当前播放
        if (this.audio) {
            this.audio.pause();
            this.audio = null;
        }
        
        this.isPlaying = true;
        this.currentTime = this.rangeStart;
        this.updateProgress();
        
        const audioUrl = AudioEditor.getAudioUrl(this.audioPath);
        this.audio = new Audio(audioUrl);
        this.audio.currentTime = this.rangeStart;
        
        this.audio.ontimeupdate = () => {
            if (!this.audio) return;
            this.currentTime = this.audio.currentTime;
            this.updateProgress();
            
            // 到达区间结束位置时停止
            if (this.currentTime >= this.rangeEnd) {
                this.stop();
                if (this.onPlayEnd) this.onPlayEnd();
            }
        };
        
        this.audio.onended = () => {
            this.stop();
            if (this.onPlayEnd) this.onPlayEnd();
        };
        
        this.audio.play().catch(e => {
            console.error('播放失败:', e);
            this.isPlaying = false;
        });
    }
    
    /**
     * 停止播放
     */
    stop() {
        if (this.audio) {
            this.audio.pause();
            this.audio = null;
        }
        
        this.isPlaying = false;
        this.currentTime = this.rangeStart;
        this.updateProgress();
    }
    
    /**
     * 更新进度显示
     */
    updateProgress() {
        const refEl = this.wrapper || (this.canvas ? this.canvas.parentElement : null);
        if (!refEl) return;
        
        const rect = refEl.getBoundingClientRect();
        if (rect.width <= 0) return;
        
        const progressWidth = (this.currentTime / Math.max(this.duration, 1)) * rect.width;
        
        if (this.progressEl) {
            this.progressEl.style.width = progressWidth + 'px';
        }
        
        if (this.playheadEl) {
            this.playheadEl.style.display = 'block';
            this.playheadEl.style.left = progressWidth + 'px';
        }
        
        if (this.currentTimeEl) {
            this.currentTimeEl.textContent = AudioEditor.formatTime(this.currentTime);
        }
    }
    
    /**
     * 设置区间调整启用状态
     */
    setAdjustEnabled(enabled) {
        this.adjustEnabled = enabled;
        
        if (!enabled) {
            this.rangeStart = 0;
            this.rangeEnd = this.duration;
        }
        
        this._updateRangeUI();
    }
    
    /**
     * 更新区间 UI
     */
    _updateRangeUI() {
        if (!this.hasAudio) return;
        
        if (!this.rangeEl || !this.startHandleEl || !this.endHandleEl) return;
        
        if (!this.adjustEnabled) {
            this.rangeEl.style.display = 'none';
            this.startHandleEl.style.display = 'none';
            this.endHandleEl.style.display = 'none';
            
            if (this.rangeStartTimeEl) {
                this.rangeStartTimeEl.textContent = '00:00';
            }
            if (this.rangeEndTimeEl) {
                this.rangeEndTimeEl.textContent = AudioEditor.formatTime(this.duration);
            }
            
            this.drawWaveform();
            return;
        }
        
        if (this.duration > 0) {
            const startRatio = this.rangeStart / this.duration;
            const endRatio = this.rangeEnd / this.duration;
            
            this.rangeEl.style.display = 'block';
            this.rangeEl.style.left = (startRatio * 100) + '%';
            this.rangeEl.style.right = (100 - endRatio * 100) + '%';
            
            this.startHandleEl.style.display = 'flex';
            this.startHandleEl.style.left = (startRatio * 100) + '%';
            
            this.endHandleEl.style.display = 'flex';
            this.endHandleEl.style.left = (endRatio * 100) + '%';
            
            if (this.rangeStartTimeEl) {
                this.rangeStartTimeEl.textContent = AudioEditor.formatTime(this.rangeStart);
            }
            if (this.rangeEndTimeEl) {
                this.rangeEndTimeEl.textContent = AudioEditor.formatTime(this.rangeEnd);
            }
        }
        
        this.drawWaveform();
    }
    
    /**
     * 重置区间
     */
    resetRange() {
        this.rangeStart = 0;
        this.rangeEnd = this.duration;
        this._updateRangeUI();
    }
    
    /**
     * 设置选择区间（用于回显已保存的范围），自动钳制到 [0, duration]
     * @param {number} start - 起始时间（秒）
     * @param {number} end - 结束时间（秒）
     */
    setRange(start, end) {
        if (!this.hasAudio || this.duration <= 0) return;
        this.rangeStart = Math.max(0, Math.min(parseFloat(start) || 0, this.duration));
        this.rangeEnd = Math.max(this.rangeStart, Math.min(parseFloat(end) || 0, this.duration));
        this.currentTime = this.rangeStart;
        this._updateRangeUI();
        this.updateProgress();
    }
    
    /**
     * 生成模拟波形（用于文本长度估算）
     */
    static generateMockWaveform(length) {
        const samples = Math.min(length * 5, 500);
        const data = [];
        for (let i = 0; i < samples; i++) {
            data.push(Math.random() * 0.8 + 0.2);
        }
        return data;
    }
    
    /**
     * 估算时长（基于文本长度）
     */
    static estimateDuration(textLength) {
        const charsPerSecond = 8;
        return Math.max(2, textLength / charsPerSecond);
    }
    
    /**
     * 解析 WAV PCM 数据
     */
    static parseWavPcmData(arrayBuffer) {
        const view = new DataView(arrayBuffer);
        
        if (arrayBuffer.byteLength < 44) return null;
        
        const riff = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
        if (riff !== 'RIFF') return null;
        
        const wave = String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11));
        if (wave !== 'WAVE') return null;
        
        let offset = 12;
        let sampleRate = 0;
        let numChannels = 0;
        let bitsPerSample = 0;
        let dataOffset = 0;
        let dataLength = 0;
        
        while (offset + 8 <= arrayBuffer.byteLength) {
            const chunkId = String.fromCharCode(
                view.getUint8(offset),
                view.getUint8(offset + 1),
                view.getUint8(offset + 2),
                view.getUint8(offset + 3)
            );
            const chunkSize = view.getUint32(offset + 4, true);
            
            if (chunkId === 'fmt ') {
                numChannels = view.getUint16(offset + 10, true);
                sampleRate = view.getUint32(offset + 12, true);
                bitsPerSample = view.getUint16(offset + 22, true);
            } else if (chunkId === 'data') {
                dataOffset = offset + 8;
                dataLength = chunkSize;
                break;
            }
            
            offset += 8 + chunkSize + (chunkSize % 2);
        }
        
        if (!dataOffset || !sampleRate || bitsPerSample !== 16 || numChannels < 1) return null;
        
        const samples = [];
        const bytesPerSample = bitsPerSample / 8;
        const blockAlign = numChannels * bytesPerSample;
        const numSamples = dataLength / blockAlign;
        
        for (let i = 0; i < numSamples; i++) {
            const sampleOffset = dataOffset + i * blockAlign;
            let sample = view.getInt16(sampleOffset, true);
            sample /= 32768;
            samples.push(sample);
        }
        
        return { samples, sampleRate };
    }
    
    /**
     * 获取音频 URL
     */
    static getAudioUrl(audioPath) {
        if (!audioPath) return '';
        if (audioPath.startsWith('http://') || audioPath.startsWith('https://') || audioPath.startsWith('blob:')) {
            return audioPath;
        }
        if (audioPath.startsWith('/')) {
            return audioPath;
        }
        return `/api/media/file/content?path=${encodeURIComponent(audioPath)}`;
    }
    
    /**
     * 格式化时间
     */
    static formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
}
