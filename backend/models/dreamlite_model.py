import os
import json
import torch
from utils.logger import logger


def _is_quantized_model(model_path):
    """检查模型是否为量化模型"""
    text_encoder_config = os.path.join(model_path, "text_encoder", "config.json")
    if os.path.exists(text_encoder_config):
        try:
            with open(text_encoder_config, "r", encoding="utf-8") as f:
                config = json.load(f)
            if "quantization_config" in config:
                return True
        except Exception:
            pass
    model_index = os.path.join(model_path, "model_index.json")
    if os.path.exists(model_index):
        try:
            with open(model_index, "r", encoding="utf-8") as f:
                index = json.load(f)
            if index.get("quantized", False):
                return True
        except Exception:
            pass
    return False


class DreamLiteModel:
    """DreamLite 模型包装类（图像/视频生成）。

    仅负责模型加载/卸载/状态管理，实际推理流水线由独立脚本驱动。
    """

    def __init__(self, model_path: str, device: str = "cuda"):
        self.model_path = model_path
        self.device = device if torch.cuda.is_available() else "cpu"
        self.pipeline = None
        self._loaded = False
        self._load()

    def _load(self):
        try:
            from models.dreamlite import DreamLiteMobilePipeline, DreamLiteUNetModel
            from diffusers import AutoencoderTiny
            from transformers import (
                AutoTokenizer,
                Qwen3VLForConditionalGeneration,
                Qwen3VLProcessor,
            )
            from diffusers.schedulers import FlowMatchEulerDiscreteScheduler

            quantized = _is_quantized_model(self.model_path)
            logger.info(f"[DreamLite] 正在从 {self.model_path} 加载模型（device={self.device}, dtype=bfloat16, quantized={quantized}）")

            # 1. 加载 tokenizer 和 processor
            logger.info("[DreamLite] 加载 tokenizer/processor...")
            tokenizer = AutoTokenizer.from_pretrained(os.path.join(self.model_path, "tokenizer"))
            processor = Qwen3VLProcessor.from_pretrained(os.path.join(self.model_path, "processor"))
            logger.info("[DreamLite] tokenizer/processor 加载完成")

            # 2. 加载 scheduler
            logger.info("[DreamLite] 加载 scheduler...")
            scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
                os.path.join(self.model_path, "scheduler")
            )
            logger.info("[DreamLite] scheduler 加载完成")

            # 3. 加载 VAE
            logger.info("[DreamLite] 加载 VAE...")
            vae = AutoencoderTiny.from_pretrained(
                os.path.join(self.model_path, "vae"),
            )
            vae = vae.to(self.device, dtype=torch.bfloat16)
            logger.info("[DreamLite] VAE 加载完成")

            # 4. 加载 text_encoder
            logger.info("[DreamLite] 加载 text_encoder...")
            if quantized and torch.cuda.is_available():
                text_encoder = Qwen3VLForConditionalGeneration.from_pretrained(
                    os.path.join(self.model_path, "text_encoder"),
                    device_map="auto",
                    trust_remote_code=True,
                    dtype=torch.bfloat16,
                )
                logger.info("[DreamLite] 量化 text_encoder 加载完成（4bit NF4）")
            else:
                text_encoder = Qwen3VLForConditionalGeneration.from_pretrained(
                    os.path.join(self.model_path, "text_encoder"),
                    trust_remote_code=True,
                    dtype=torch.bfloat16,
                )
                text_encoder = text_encoder.to(self.device)
                logger.info("[DreamLite] text_encoder 加载完成")

            # 5. 加载 UNet
            logger.info("[DreamLite] 加载 UNet...")
            unet = DreamLiteUNetModel.from_pretrained(
                os.path.join(self.model_path, "unet"),
            )
            unet = unet.to(self.device, dtype=torch.bfloat16)
            logger.info("[DreamLite] UNet 加载完成")

            # 6. 组装 pipeline
            self.pipeline = DreamLiteMobilePipeline(
                text_encoder=text_encoder,
                tokenizer=tokenizer,
                processor=processor,
                vae=vae,
                unet=unet,
                scheduler=scheduler,
            )

            self._loaded = True
            logger.info("[DreamLite] 模型加载完成")

            if torch.cuda.is_available():
                mem_allocated = torch.cuda.memory_allocated() / 1024**3
                logger.info(f"[DreamLite] 显存占用: {mem_allocated:.2f} GB")
        except Exception as e:
            logger.error(f"[DreamLite] 模型加载失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._loaded = False
            raise

    def is_loaded(self) -> bool:
        return self._loaded

    def generate(self, prompt: str, image=None, num_inference_steps: int = 4,
                 width: int = 1024, height: int = 1024, seed: int = 42):
        if not self._loaded:
            raise RuntimeError("DreamLite 模型未加载")
        logger.info(
            f"[DreamLite] 开始生成: prompt='{prompt[:30]}...', "
            f"steps={num_inference_steps}, size={width}x{height}"
        )
        generator = torch.Generator("cpu").manual_seed(seed)
        result = self.pipeline(
            prompt=prompt,
            image=image,
            height=height,
            width=width,
            num_inference_steps=num_inference_steps,
            generator=generator,
        )
        return result

    def release(self):
        try:
            if self.pipeline is not None:
                del self.pipeline
                self.pipeline = None
            self._loaded = False
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("[DreamLite] 模型资源已释放")
        except Exception as e:
            logger.error(f"[DreamLite] 释放失败: {e}")
