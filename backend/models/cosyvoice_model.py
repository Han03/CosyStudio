import sys
import os
import time

_current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _current_dir)

import json
import logging
import torch
import numpy as np
import torchaudio
import librosa
from typing import Generator
from tqdm import tqdm

import cosyvoice
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2, CosyVoice3, AutoModel
from cosyvoice.cli.frontend import CosyVoiceFrontEnd
from cosyvoice.utils.file_utils import load_wav

logger = logging.getLogger(__name__)


def _is_4bit_quantized(model_dir):
    """检查是否为 4bit 量化模型"""
    return os.path.exists(os.path.join(model_dir, 'quantized_4bit.json'))


class CosyVoice2_4bit(CosyVoice2):
    """CosyVoice2 的 4bit 量化版本。

    继承 CosyVoice2，重写 __init__ 以支持 4bit 量化的 Qwen2ForCausalLM 加载。
    不修改 models/cosyvoice 目录下的核心代码。
    """

    def __init__(self, model_dir, load_jit=False, load_trt=False, load_vllm=False, fp16=False, trt_concurrent=1):
        from hyperpyyaml import load_hyperpyyaml
        from cosyvoice.cli.model import CosyVoice2Model
        from cosyvoice.utils.class_utils import get_model_type

        self.model_dir = model_dir
        self.fp16 = fp16

        # 1. 加载 yaml 配置
        hyper_yaml_path = '{}/cosyvoice2.yaml'.format(model_dir)
        with open(hyper_yaml_path, 'r') as f:
            configs = load_hyperpyyaml(f, overrides={'qwen_pretrain_path': os.path.join(model_dir, 'CosyVoice-BlankEN')})
        assert get_model_type(configs) == CosyVoice2Model, 'do not use {} for CosyVoice2 initialization!'.format(model_dir)

        # 2. 创建前端
        self.frontend = CosyVoiceFrontEnd(configs['get_tokenizer'],
                                          configs['feat_extractor'],
                                          '{}/campplus.onnx'.format(model_dir),
                                          '{}/speech_tokenizer_v2.onnx'.format(model_dir),
                                          '{}/spk2info.pt'.format(model_dir),
                                          configs['allowed_special'])
        self.sample_rate = configs['sample_rate']

        if torch.cuda.is_available() is False and (load_jit is True or load_trt is True or load_vllm is True or fp16 is True):
            load_jit, load_trt, load_vllm, fp16 = False, False, False, False
            logger.warning('[CosyVoice 4bit] no cuda device, set load_jit/load_trt/load_vllm/fp16 to False')

        # 3. 创建模型结构 (Qwen2LM + Qwen2Encoder + Qwen2ForCausalLM from CosyVoice-BlankEN)
        logger.info("[CosyVoice 4bit] 创建模型结构...")
        self.model = CosyVoice2Model(configs['llm'], configs['flow'], configs['hift'], fp16)

        # 4. 替换 Qwen2ForCausalLM 为 4bit 量化版本
        logger.info("[CosyVoice 4bit] 加载 4bit 量化 Qwen2ForCausalLM...")
        self._load_4bit_qwen2(model_dir)

        # 5. 加载额外层 (text_embedding, llm_decoder, speech_embedding 等)
        logger.info("[CosyVoice 4bit] 加载额外 LLM 层...")
        extra_path = '{}/llm_extra.pt'.format(model_dir)
        extra_state_dict = torch.load(extra_path, map_location=self.model.device, weights_only=True)
        # strict=False 因为 llm.model.* 已经通过 4bit 加载了
        self.model.llm.load_state_dict(extra_state_dict, strict=False)
        # 将除了 llm.model (Qwen2ForCausalLM, 已 4bit 在 GPU) 之外的层移到 device
        # 注意: 4bit 模型不能再 .to()，所以单独处理非 Qwen2 部分
        for name, module in self.model.llm.named_children():
            if name != 'llm':  # llm.llm 是 Qwen2Encoder，内部 llm.llm.model 是 4bit Qwen2
                module.to(self.model.device)
        self.model.llm.eval()
        logger.info("[CosyVoice 4bit] 额外 LLM 层加载完成")

        # 6. 加载 flow 和 hift
        logger.info("[CosyVoice 4bit] 加载 flow.pt 和 hift.pt...")
        flow_path = '{}/flow.pt'.format(model_dir)
        hift_path = '{}/hift.pt'.format(model_dir)

        self.model.flow.load_state_dict(
            torch.load(flow_path, map_location=self.model.device, weights_only=True), strict=True
        )
        self.model.flow.to(self.model.device).eval()

        hift_state_dict = {
            k.replace('generator.', ''): v
            for k, v in torch.load(hift_path, map_location=self.model.device, weights_only=True).items()
        }
        self.model.hift.load_state_dict(hift_state_dict, strict=True)
        self.model.hift.to(self.model.device).eval()

        if load_vllm:
            self.model.load_vllm('{}/vllm'.format(model_dir))
        if load_jit:
            self.model.load_jit('{}/flow.encoder.{}.zip'.format(model_dir, 'fp16' if self.fp16 is True else 'fp32'))
        if load_trt:
            self.model.load_trt('{}/flow.decoder.estimator.{}.mygpu.plan'.format(model_dir, 'fp16' if self.fp16 is True else 'fp32'),
                                '{}/flow.decoder.estimator.fp32.onnx'.format(model_dir),
                                trt_concurrent,
                                self.fp16)

        del configs
        logger.info("[CosyVoice 4bit] 模型加载完成")

    def _load_4bit_qwen2(self, model_dir):
        """加载 4bit 量化的 Qwen2ForCausalLM 并替换到模型中"""
        from transformers import Qwen2ForCausalLM, BitsAndBytesConfig

        llm_qwen2_dir = os.path.join(model_dir, 'llm_qwen2')
        if not os.path.exists(llm_qwen2_dir):
            raise FileNotFoundError(f"4bit Qwen2 目录不存在: {llm_qwen2_dir}")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if self.fp16 else torch.float32,
        )

        logger.info(f"[CosyVoice 4bit] 从 {llm_qwen2_dir} 加载 4bit Qwen2...")
        qwen2_model = Qwen2ForCausalLM.from_pretrained(
            llm_qwen2_dir,
            quantization_config=bnb_config,
            device_map="auto" if torch.cuda.is_available() else None,
            dtype=torch.bfloat16,
        )
        qwen2_model.eval()

        # 替换模型中的 Qwen2ForCausalLM
        # 结构: self.model.llm (Qwen2LM) .llm (Qwen2Encoder) .model (Qwen2ForCausalLM)
        self.model.llm.llm.model = qwen2_model

        if torch.cuda.is_available():
            mem_allocated = torch.cuda.memory_allocated() / 1024**3
            logger.info(f"[CosyVoice 4bit] Qwen2 4bit 加载完成, 显存占用: {mem_allocated:.2f} GB")


class CosyVoiceModel:
    def __init__(self, model_path):
        self.model_path = model_path
        self.spk2info_path = os.path.join(model_path, "spk2info.pt")
        self._frontend = None
        self._cosyvoice = None
        self._model_version = None

    def _detect_model_version(self):
        if os.path.exists(os.path.join(self.model_path, 'cosyvoice3.yaml')):
            return 3
        elif os.path.exists(os.path.join(self.model_path, 'cosyvoice2.yaml')):
            return 2
        elif os.path.exists(os.path.join(self.model_path, 'cosyvoice.yaml')):
            return 1
        return None

    def _get_frontend(self):
        if self._frontend is not None:
            return self._frontend

        self.cosyvoice = self._get_cosyvoice()
        self._frontend = self.cosyvoice.frontend
        self._model_version = self._detect_model_version()
        self._load_custom_speakers()
        logger.info(f"[CosyVoice] 已加载现有说话人: {len(self._frontend.spk2info)}个")
        return self._frontend

    def _custom_speakers_file(self):
        """自定义说话人的独立存储路径（不污染内置 spk2info.pt）"""
        return os.path.join(os.path.dirname(self.spk2info_path), "custom_speakers.pt")

    def _load_custom_speakers(self):
        """加载自定义说话人到 frontend.spk2info（不修改内置 spk2info.pt 文件）"""
        custom_file = self._custom_speakers_file()
        if not os.path.exists(custom_file):
            return
        try:
            custom_speakers = torch.load(custom_file, map_location='cpu', weights_only=False)
            device = self._frontend.device
            for spk_id, info in custom_speakers.items():
                moved_info = {}
                for k, v in info.items():
                    if isinstance(v, torch.Tensor):
                        moved_info[k] = v.to(device)
                    else:
                        moved_info[k] = v
                self._frontend.spk2info[spk_id] = moved_info
            logger.info(f"[CosyVoice] 加载自定义说话人: {len(custom_speakers)}个")
        except Exception as e:
            logger.warning(f"[CosyVoice] 加载自定义说话人失败: {e}")

    def _save_custom_speakers(self):
        """保存自定义说话人（只保存自定义的，不影响内置 spk2info.pt）"""
        custom_file = self._custom_speakers_file()
        builtin_spks = self._builtin_speaker_ids()
        custom_speakers = {
            spk_id: info for spk_id, info in self._frontend.spk2info.items()
            if spk_id not in builtin_spks
        }
        try:
            torch.save(custom_speakers, custom_file)
            logger.info(f"[CosyVoice] 保存自定义说话人: {len(custom_speakers)}个")
        except Exception as e:
            logger.error(f"[CosyVoice] 保存自定义说话人失败: {e}")

    def _builtin_speaker_ids(self):
        """获取内置说话人ID列表（从原始 spk2info.pt 读取）"""
        try:
            if os.path.exists(self.spk2info_path):
                builtin = torch.load(self.spk2info_path, map_location='cpu', weights_only=False)
                return set(builtin.keys())
        except Exception:
            pass
        return set()

    def _get_cosyvoice(self):
        if self._cosyvoice is not None:
            return self._cosyvoice

        kwargs = {'model_dir': self.model_path}
        if torch.cuda.is_available():
            kwargs['fp16'] = True
            logger.info("[CosyVoice] 启用FP16半精度加速")

        model_version = self._detect_model_version()

        # 检测是否为 4bit 量化模型
        if _is_4bit_quantized(self.model_path):
            logger.info("[CosyVoice] 检测到 4bit 量化模型，使用 4bit 加载路径")
            if model_version == 2:
                self._cosyvoice = CosyVoice2_4bit(**kwargs)
            else:
                logger.warning("[CosyVoice] 当前版本 4bit 仅支持 CosyVoice2，回退到标准加载")
                self._cosyvoice = AutoModel(**kwargs)
        else:
            self._cosyvoice = AutoModel(**kwargs)

        self._optimize_chunk_size()

        logger.info("[CosyVoice] CosyVoice模型加载完成")
        return self._cosyvoice

    def _optimize_chunk_size(self):
        """优化流式生成的chunk大小为512ms。"""
        try:
            cosyvoice = self._cosyvoice
            model = cosyvoice.model

            frame_rate = getattr(model, 'flow', None)
            if frame_rate and hasattr(frame_rate, 'input_frame_rate'):
                frame_rate = frame_rate.input_frame_rate
            else:
                frame_rate = 50

            target_chunk_ms = 512
            target_hop_len = int(frame_rate * target_chunk_ms / 1000)

            if hasattr(model, 'token_hop_len'):
                old_hop_len = model.token_hop_len
                model.token_hop_len = target_hop_len
                logger.info(f"[CosyVoice] token_hop_len 从 {old_hop_len} ({old_hop_len/frame_rate*1000:.0f}ms) 调整为 {target_hop_len} ({target_chunk_ms}ms)")

            if hasattr(model, 'token_max_hop_len'):
                old_max_len = model.token_max_hop_len
                model.token_max_hop_len = 4 * target_hop_len
                logger.info(f"[CosyVoice] token_max_hop_len 从 {old_max_len} 调整为 {model.token_max_hop_len}")

            if hasattr(model, 'token_min_hop_len'):
                old_min_len = model.token_min_hop_len
                model.token_min_hop_len = target_hop_len
                logger.info(f"[CosyVoice] token_min_hop_len 从 {old_min_len} 调整为 {model.token_min_hop_len}")

        except Exception as e:
            logger.warning(f"[CosyVoice] 调整chunk大小失败: {e}")

    def _prepare_text_for_cv3(self, text):
        """CosyVoice3的LLM要求文本token中包含<|endofprompt|>标记（id=151646），
        否则会触发assertion错误。在文本末尾添加该标记。
        """
        if self._model_version != 3:
            return text
        if not text:
            return text
        endofprompt_tag = '<|endofprompt|>'
        if endofprompt_tag in text:
            return text
        return text + endofprompt_tag

    def _preprocess_audio(self, audio_path, target_sample_rate=22050):
        """音频预处理：采样率统一、归一化、静音切除。

        参数:
            audio_path: 原始音频路径
            target_sample_rate: 目标采样率

        返回:
            处理后的音频路径（临时文件），失败返回None
        """
        try:
            import tempfile

            waveform, sr = librosa.load(audio_path, sr=None)

            if sr != target_sample_rate:
                waveform = librosa.resample(waveform, orig_sr=sr, target_sr=target_sample_rate)
                logger.debug(f"[CosyVoice] 采样率转换: {sr} -> {target_sample_rate}")

            waveform = waveform / np.max(np.abs(waveform))
            logger.debug(f"[CosyVoice] 音频归一化完成")

            intervals = librosa.effects.split(waveform, top_db=20)
            if len(intervals) > 0:
                non_silent_audio = []
                for interval in intervals:
                    non_silent_audio.append(waveform[interval[0]:interval[1]])
                if non_silent_audio:
                    waveform = np.concatenate(non_silent_audio)
                logger.debug(f"[CosyVoice] 静音切除完成，原长度: {len(waveform)/target_sample_rate:.2f}s")

            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            import soundfile as sf
            sf.write(temp_file.name, waveform, target_sample_rate, subtype='FLOAT')
            temp_file.close()

            logger.debug(f"[CosyVoice] 音频预处理完成，保存到: {temp_file.name}")
            return temp_file.name

        except Exception as e:
            logger.error(f"[CosyVoice] 音频预处理失败: {e}")
            return None

    def add_custom_speaker(self, speaker_id, voice_path, prompt_text):
        try:
            logger.info(f"[CosyVoice] 开始注册说话人: {speaker_id}，语音文件: {voice_path}，提示文本: {prompt_text}")

            cosyvoice = self._get_cosyvoice()
            frontend = self._get_frontend()

            if speaker_id in frontend.spk2info:
                logger.info(f"[CosyVoice] 说话人 {speaker_id} 已存在，先移除旧的")
                del frontend.spk2info[speaker_id]

            processed_voice_path = self._preprocess_audio(voice_path)
            if processed_voice_path is None:
                return {"status": "failed", "error": "音频预处理失败"}

            try:
                logger.info(f"[CosyVoice] 调用 add_zero_shot_spk 注册: {speaker_id}")
                cosyvoice.add_zero_shot_spk(prompt_text, processed_voice_path, speaker_id)
            finally:
                try:
                    os.remove(processed_voice_path)
                except Exception:
                    pass

            self._save_custom_speakers()
            logger.info(f"[CosyVoice] 说话人 {speaker_id} 注册完成并保存")

            return {"status": "success", "message": "说话人注册成功"}

        except Exception as e:
            import traceback
            logger.error(f"[CosyVoice] 注册说话人异常: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "failed", "error": str(e)}

    def backup_speaker(self, speaker_id):
        """备份说话人信息(深拷贝),用于编辑重训失败时恢复。

        返回 speaker info 字典的深拷贝;不存在或异常时返回 None。
        """
        try:
            frontend = self._get_frontend()
            info = frontend.spk2info.get(speaker_id)
            if info is None:
                return None
            import copy
            return copy.deepcopy(info)
        except Exception as e:
            logger.warning(f"[CosyVoice] 备份说话人 {speaker_id} 失败: {e}")
            return None

    def restore_speaker(self, speaker_id, info):
        """将备份的 speaker info 写回 frontend.spk2info(仅内存恢复,不写文件)。"""
        if info is None:
            return
        try:
            frontend = self._get_frontend()
            frontend.spk2info[speaker_id] = info
            logger.info(f"[CosyVoice] 已恢复说话人 {speaker_id} 的内存状态")
        except Exception as e:
            logger.error(f"[CosyVoice] 恢复说话人 {speaker_id} 失败: {e}")

    def list_speakers(self):
        try:
            frontend = self._get_frontend()
            builtin_spks = self._builtin_speaker_ids()
            custom_speakers = [
                spk_id for spk_id in frontend.spk2info.keys()
                if spk_id not in builtin_spks
            ]
            return custom_speakers
        except Exception as e:
            logger.error(f"[CosyVoice] 读取说话人列表失败: {e}")
            return []

    def remove_speaker(self, speaker_id):
        try:
            custom_file = self._custom_speakers_file()
            if os.path.exists(custom_file):
                custom_speakers = torch.load(custom_file, map_location='cpu', weights_only=False)
                if speaker_id in custom_speakers:
                    del custom_speakers[speaker_id]
                    torch.save(custom_speakers, custom_file)
                    logger.info(f"[CosyVoice] 说话人 {speaker_id} 已从缓存中移除")
                    frontend = self._get_frontend()
                    if speaker_id in frontend.spk2info:
                        del frontend.spk2info[speaker_id]
                    return {"status": "success", "message": f"说话人 {speaker_id} 已移除"}
                else:
                    return {"status": "warning", "message": f"说话人 {speaker_id} 不存在"}
            else:
                return {"status": "warning", "message": "缓存文件不存在"}
        except Exception as e:
            logger.error(f"[CosyVoice] 移除说话人失败: {e}")
            return {"status": "failed", "error": str(e)}

    def is_loaded(self):
        return self._cosyvoice is not None and self._frontend is not None

    def initialize(self):
        try:
            logger.info("[CosyVoice] 开始初始化前端和模型...")
            if torch.cuda.is_available():
                torch.backends.cuda.enable_flash_sdp(True)
                torch.backends.cudnn.benchmark = True
                logger.info("[CosyVoice] 已启用 Flash SDPA 和 cudnn benchmark")

            self._get_frontend()
            self._get_cosyvoice()

            logger.info("[CosyVoice] 前端和模型初始化完成")
            return True
        except Exception as e:
            logger.error(f"[CosyVoice] 初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _apply_fade_in(self, pcm, sample_rate, fade_duration_ms=20):
        """对PCM数据应用淡入效果，消除开头噪音。

        参数:
            pcm: PCM音频数据（numpy数组）
            sample_rate: 采样率
            fade_duration_ms: 淡入时长（毫秒）

        返回:
            处理后的PCM数据
        """
        fade_samples = int(sample_rate * fade_duration_ms / 1000)
        if len(pcm) <= fade_samples:
            fade_samples = len(pcm)
        
        fade_in_window = np.linspace(0, 1, fade_samples)
        pcm[:fade_samples] = pcm[:fade_samples] * fade_in_window
        return pcm

    def _trim_start_noise(self, pcm, sample_rate, trim_duration_ms=20):
        """裁剪开头的短暂噪音。

        参数:
            pcm: PCM音频数据（numpy数组）
            sample_rate: 采样率
            trim_duration_ms: 裁剪时长（毫秒）

        返回:
            处理后的PCM数据
        """
        trim_samples = int(sample_rate * trim_duration_ms / 1000)
        if len(pcm) > trim_samples:
            return pcm[trim_samples:]
        return pcm

    def _build_instruct_text(self, instruction):
        """构建 CosyVoice3 instruct 文本。

        instruction 为前端直接传入的自然语言指令，如 "请非常开心地说一句话"。
        返回完整的 instruct 文本格式为 "You are a helpful assistant. {instruction}。<|endofprompt|>"

        返回 None 表示不需要指令。
        """
        if not instruction:
            return None
        instruction = instruction.strip()
        if not instruction:
            return None
        instruct_text = f"You are a helpful assistant. {instruction}。<|endofprompt|>"
        logger.info(f"[CosyVoice] 应用指令: {instruct_text}")
        return instruct_text

    def _inference_with_instruct(self, cosyvoice, frontend, tts_text, instruct_text, speaker_id, speed):
        """使用指令模式合成语音（CosyVoice3 专用）。

        对注册说话人，手动覆盖 prompt_text 为指令文本，并移除
        llm_prompt_speech_token，使 LLM 根据指令生成对应语气。
        保留 flow_embedding/llm_embedding 用于音色保持。
        """
        if self._model_version == 3:
            tts_text = self._prepare_text_for_cv3(tts_text)
        
        try:
            model_input = frontend.frontend_zero_shot(tts_text, '', '', cosyvoice.sample_rate, speaker_id)
            
            instruct_token = frontend._extract_text_token(instruct_text)
            model_input['prompt_text'] = instruct_token[0]
            model_input['prompt_text_len'] = instruct_token[1]

            if 'llm_prompt_speech_token' in model_input:
                del model_input['llm_prompt_speech_token']
            if 'llm_prompt_speech_token_len' in model_input:
                del model_input['llm_prompt_speech_token_len']

            start_time = time.time()
            logger.info(f'[CosyVoice] 合成文本: {tts_text[:50]}...')
            for model_output in cosyvoice.model.tts(**model_input, stream=True, speed=speed):
                speech_len = model_output['tts_speech'].shape[1] / cosyvoice.sample_rate
                logger.info(f'[CosyVoice] 生成语音片段长度: {speech_len:.2f}s, RTF: {(time.time() - start_time) / speech_len:.2f}')
                yield model_output
                start_time = time.time()
        except Exception as e:
            logger.error(f'[CosyVoice] _inference_with_instruct 异常: {e}')
            import traceback
            logger.error(traceback.format_exc())
            raise

    def synthesize_pcm(self, text, speaker_id=None, voice_path=None, prompt_text=None, speed=1.0, instruction=None, seed=None):
        """
        直接输出PCM音频数据（不保存文件）

        Args:
            text: 要合成的文本
            speaker_id: 说话人ID
            voice_path: 参考音频路径（零样本合成时需要）
            prompt_text: 参考文本（零样本合成时需要）
            speed: 语速（默认1.0）
            instruction: 自然语言指令（如"请非常开心地说一句话"），
                         仅 CosyVoice3 生效，为空则使用默认语气
            seed: 随机种子（用于生成可重复的音频），默认为None（随机）

        Returns:
            Generator: 每次yield一个dict，包含type和pcm数据
        """
        try:
            if seed is not None:
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)

            logger.info(f"[CosyVoice] 开始PCM流式合成: text={text[:50]}..., speaker={speaker_id}, speed={speed}, instruction={instruction}, seed={seed}")

            cosyvoice = self._get_cosyvoice()
            frontend = self._get_frontend()
            speakers = cosyvoice.list_available_spks()

            first_chunk = True
            sample_rate = cosyvoice.sample_rate

            def _process_chunk(model_output):
                nonlocal first_chunk
                pcm = model_output['tts_speech'][0].cpu().numpy()

                if first_chunk:
                    pcm = self._trim_start_noise(pcm, sample_rate)
                    #pcm = self._apply_fade_in(pcm, sample_rate)
                    first_chunk = False

                return {"type": "pcm_chunk", "data": pcm, "sample_rate": sample_rate}

            if voice_path and prompt_text:
                instruct_text = self._build_instruct_text(instruction) if self._model_version == 3 else None
                if instruct_text:
                    logger.info(f"[CosyVoice] 使用instruct模式(voice_path)")
                    for model_output in cosyvoice.inference_instruct2(text, instruct_text, voice_path, '', stream=True, speed=speed, text_frontend=True):
                        yield _process_chunk(model_output)
                else:
                    logger.info("[CosyVoice] 使用zero_shot模式(voice_path)")
                    if self._model_version == 3:
                        prompt_text = self._prepare_text_for_cv3(prompt_text)
                    processed_text = self._prepare_text_for_cv3(text) if self._model_version == 3 else text
                    for model_output in cosyvoice.inference_zero_shot(processed_text, prompt_text, voice_path, '', stream=True, text_frontend=True, speed=speed):
                        yield _process_chunk(model_output)
            elif speaker_id and speaker_id in speakers:
                instruct_text = self._build_instruct_text(instruction) if self._model_version == 3 else None
                if instruct_text:
                    logger.info(f"[CosyVoice] 使用instruct模式(注册说话人), speaker={speaker_id}")
                    for model_output in self._inference_with_instruct(cosyvoice, frontend, text, instruct_text, speaker_id, speed):
                        yield _process_chunk(model_output)
                else:
                    if self._model_version == 3:
                        default_instruct = "You are a helpful assistant. 请用自然、清晰的语气朗读。<|endofprompt|>"
                        logger.info(f"[CosyVoice] 使用instruct模式(注册说话人, 默认语气), speaker={speaker_id}")
                        for model_output in self._inference_with_instruct(cosyvoice, frontend, text, default_instruct, speaker_id, speed):
                            yield _process_chunk(model_output)
                    else:
                        logger.info(f"[CosyVoice] 使用zero_shot模式(注册说话人), speaker={speaker_id}")
                        processed_text = text
                        for model_output in cosyvoice.inference_zero_shot(processed_text, '', '', speaker_id, stream=True, text_frontend=True, speed=speed):
                            yield _process_chunk(model_output)
            else:
                yield {"type": "error", "content": f"说话人 {speaker_id} 未注册"}

            logger.info(f"[CosyVoice] PCM流式合成完成")
            yield {"type": "pcm_finish", "sample_rate": sample_rate}

        except Exception as e:
            import traceback
            logger.error(f"[CosyVoice] PCM流式合成异常: {str(e)}")
            logger.error(traceback.format_exc())
            yield {"type": "error", "content": str(e)}

    def get_sample_rate(self):
        """获取采样率"""
        return self._get_cosyvoice().sample_rate

    def release(self):
        try:
            self._frontend = None
            self._cosyvoice = None

            from core.paths import OUTPUT_DIR as output_dir
            if os.path.exists(output_dir):
                import glob
                import time
                now = time.time()
                for file in glob.glob(os.path.join(output_dir, "*.wav")):
                    if os.path.getmtime(file) < now - 3600:
                        os.remove(file)
                        logger.info(f"[CosyVoice] 清理临时文件: {file}")

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            import gc
            gc.collect()
            logger.info("[CosyVoice] 模型资源已清理")
        except Exception as e:
            logger.error(f"[CosyVoice] 清理资源失败: {e}")
