import os
import time
import torch
import threading
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer
import logging

logger = logging.getLogger(__name__)

from core.global_manager import global_manager

class QwenModel:
    def __init__(self, model_path):
        self.model_path = model_path
        self.tokenizer = None
        self.model = None
        self.device = None
        self._load_model()
    
    def _load_model(self):
        logger.info(f"[Qwen] 开始加载模型，路径: {self.model_path}")
        
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            logger.info(f"[Qwen] GPU可用，设备: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            logger.warning("[Qwen] GPU不可用，将使用CPU（速度较慢）")
        
        try:
            logger.info("[Qwen] 正在加载tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                use_fast=False
            )
            logger.info("[Qwen] Tokenizer加载完成")
            
            logger.info("[Qwen] 正在加载模型...")
            
            model_kwargs = {
                "trust_remote_code": True,
                "dtype": torch.float16 if self.device.type == "cuda" else torch.float32,
                "low_cpu_mem_usage": True,
            }

            # 读取模型 config 判断是否为预量化模型
            from transformers import AutoConfig
            try:
                auto_config = AutoConfig.from_pretrained(self.model_path, trust_remote_code=True)
                quant_method = getattr(auto_config, "quantization_config", {}).get("quant_method", "")
                if quant_method == "bitsandbytes":
                    logger.info("[Qwen] 检测到预量化 4-bit 模型，直接加载量化权重")
                else:
                    # 非预量化模型，运行时 4-bit 量化（兼容旧路径）
                    try:
                        from transformers import BitsAndBytesConfig
                        logger.info("[Qwen] 非预量化模型，启用运行时 4-bit 量化...")
                        model_kwargs["quantization_config"] = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_use_double_quant=False,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_compute_dtype=torch.float16
                        )
                        logger.info("[Qwen] 4-bit量化配置已设置")
                    except ImportError as e:
                        logger.info(f"[Qwen] 无法使用4-bit量化，使用默认加载方式: {e}")
            except Exception as e:
                logger.warning(f"[Qwen] 读取模型配置失败，回退到运行时量化: {e}")
                try:
                    from transformers import BitsAndBytesConfig
                    model_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_use_double_quant=False,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16
                    )
                except ImportError:
                    pass
            
            try:
                import flash_attn
                model_kwargs["attn_implementation"] = "flash_attention_2"
                logger.info("[Qwen] 使用FlashAttention-2...")
            except ImportError:
                logger.info("[Qwen] flash_attn未安装，使用默认attention")
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                **model_kwargs
            )

            # 预量化模型或运行时量化模型（is_quantized=True）已在加载时部署到 GPU，
            # 不能调用 .to() 移动设备
            is_quantized = getattr(self.model, "is_quantized", False)
            if not is_quantized and "quantization_config" not in model_kwargs and self.device.type == "cuda":
                logger.info(f"[Qwen] 正在将模型移动到 {self.device}...")
                self.model = self.model.to(self.device)
            
            self.model.eval()
            
            logger.info(f"[Qwen] 模型加载成功，设备: {self.device}")
        except Exception as e:
            logger.error(f"[Qwen] 加载模型失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    

    def generate_stream(self, text, agent_description=None, generate_params=None):
        if not self.tokenizer or not self.model:
            yield {"type": "error", "content": "模型未加载"}
            return

        logger.info(f"[Qwen] 收到流式生成请求: '{text[:30]}...'")

        try:
            from domain.prompts import get_system_prompt

            system_prompt = get_system_prompt(agent_description)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]

            prompt_text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            # Qwen3.5 默认开启思考模式，手动替换为空思考以禁用思考，加速生成
            if prompt_text.endswith("<think>\n"):
                prompt_text = prompt_text[:-len("<think>\n")] + "<think>\n\n</think>\n\n"
            elif prompt_text.rstrip().endswith("<think>"):
                prompt_text = prompt_text.rstrip()[:-len("<think>")] + "<think>\n\n</think>\n\n"

            with torch.no_grad():
                encoded = self.tokenizer(prompt_text, return_tensors="pt")
                input_ids = encoded.input_ids.to(self.device)
                attention_mask = encoded.get("attention_mask")
                if attention_mask is not None:
                    attention_mask = attention_mask.to(self.device)

            logger.info("[Qwen] 开始流式生成...")

            streamer = TextIteratorStreamer(
                self.tokenizer,
                skip_prompt=True,
                skip_special_tokens=True
            )

            if generate_params is None:
                generate_params = global_manager.qwen_generate_params
            # num_beams<=1 时移除 beam search 专用参数，避免 transformers 警告/报错
            if generate_params.get("num_beams", 1) <= 1:
                generate_params = {k: v for k, v in generate_params.items()
                                   if k not in ("length_penalty", "early_stopping", "num_beams")}
            generate_kwargs = dict(
                input_ids=input_ids,
                pad_token_id=self.tokenizer.eos_token_id,
                streamer=streamer,
                **generate_params,
            )
            if attention_mask is not None:
                generate_kwargs["attention_mask"] = attention_mask

            def _generate_with_no_grad():
                with torch.no_grad():
                    self.model.generate(**generate_kwargs)

            thread = threading.Thread(target=_generate_with_no_grad)
            thread.start()

            full_text = ""
            in_think = False

            for token_text in streamer:
                if token_text:
                    if '<think>' in token_text:
                        in_think = True
                        parts = token_text.split('<think>')
                        if len(parts) > 1 and parts[1]:
                            if '</think>' in parts[1]:
                                final_part = parts[1].split('</think>', 1)[1]
                                full_text += final_part
                                if final_part:
                                    yield {"type": "text", "content": final_part}
                                in_think = False
                            else:
                                full_text += parts[1]
                                continue
                        continue

                    if in_think:
                        if '</think>' in token_text:
                            parts = token_text.split('</think>', 1)
                            if len(parts) > 1 and parts[1]:
                                full_text += parts[1]
                                yield {"type": "text", "content": parts[1]}
                            in_think = False
                        else:
                            full_text += token_text
                            continue

                    if '[思考]' in token_text:
                        parts = token_text.split('[思考]')
                        if len(parts) > 1 and parts[1]:
                            full_text += parts[1]
                            yield {"type": "text", "content": parts[1]}
                        continue

                    full_text += token_text
                    yield {"type": "text", "content": token_text}

            thread.join(timeout=5)

            del input_ids
            del attention_mask
            del encoded

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            from domain.prompts import process_response
            processed_text = process_response(full_text)

            if processed_text != full_text:
                yield {"type": "correction", "content": processed_text}

            yield {"type": "finish", "content": ""}
            logger.info("[Qwen] 流式生成完成")

        except Exception as e:
            logger.error(f"[Qwen] 流式生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            yield {"type": "error", "content": f"生成失败: {str(e)}"}

    def generate(self, text, agent_description=None, generate_params=None):
        """同步生成完整对话结果(对 generate_stream 的封装)。

        累积流式输出的 text 片段,correction 视为对全文的修正版本直接替换,
        遇 finish 结束,遇 error 返回空字符串。
        """
        full_text = ""
        for chunk in self.generate_stream(
            text,
            agent_description=agent_description,
            generate_params=generate_params,
        ):
            chunk_type = chunk.get("type")
            if chunk_type == "text":
                full_text += chunk.get("content", "")
            elif chunk_type == "correction":
                full_text = chunk.get("content", "")
            elif chunk_type == "finish":
                break
            elif chunk_type == "error":
                logger.error(f"[Qwen] 同步生成失败: {chunk.get('content')}")
                return ""
        return full_text

    def is_loaded(self):
        return self.model is not None and self.tokenizer is not None
    
    def release(self):
        """释放模型内存"""
        try:
            if self.model is not None:
                # 将模型移回CPU以释放GPU内存
                if self.device and self.device.type == "cuda":
                    self.model = self.model.to(torch.device("cpu"))
                del self.model
                self.model = None
                logger.info("[Qwen] 模型已释放")
            
            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None
            
            # 清理GPU缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            
            import gc
            gc.collect()
            logger.info("[Qwen] 内存已清理")
        except Exception as e:
            logger.error(f"[Qwen] 释放模型失败: {e}")