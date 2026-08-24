"""
CosyVoice2 模型 4bit 量化脚本

将 CosyVoice2-0.5B 中的 LLM (Qwen2ForCausalLM) 部分保存为可4bit加载的HF格式，
其余层保存为 llm_extra.pt。量化后的模型不依赖原始模型目录。

用法:
    python quantize_cosyvoice.py --model_path <源模型目录> --output_path <输出路径>

原理:
    CosyVoice2 的 llm.pt 是整个 Qwen2LM 模块的 state_dict，其中:
    - llm.model.* 对应 Qwen2ForCausalLM (约1.9GB，占大部分)
    - 其余为 text_embedding, text_encoder, llm_decoder, speech_embedding 等

    本脚本将 Qwen2ForCausalLM 部分保存为标准 HF 格式 (可用 BitsAndBytesConfig 4bit加载)，
    其余层保存为 llm_extra.pt，加载时合并。
"""

import os
import sys
import shutil
import json
import argparse
import torch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def split_llm_state_dict(llm_pt_path):
    """将 llm.pt 的 state_dict 拆分为 Qwen2 部分和额外层部分

    Returns:
        qwen2_state_dict: Qwen2ForCausalLM 的 state_dict (keys without 'llm.model.' prefix)
        extra_state_dict: 其余层的 state_dict (keys as-is)
    """
    print(f"[INFO] 加载 llm.pt: {llm_pt_path}")
    full_state_dict = torch.load(llm_pt_path, map_location='cpu', weights_only=True)
    print(f"[INFO] llm.pt 共 {len(full_state_dict)} 个参数")

    qwen2_state_dict = {}
    extra_state_dict = {}

    qwen2_prefix = 'llm.model.'
    for key, value in full_state_dict.items():
        if key.startswith(qwen2_prefix):
            # 去掉 'llm.model.' 前缀，得到 Qwen2ForCausalLM 的标准 key
            qwen2_key = key[len(qwen2_prefix):]
            qwen2_state_dict[qwen2_key] = value
        else:
            extra_state_dict[key] = value

    print(f"[INFO] Qwen2ForCausalLM 部分: {len(qwen2_state_dict)} 个参数")
    print(f"[INFO] 额外层部分: {len(extra_state_dict)} 个参数")

    # 打印额外层的 key 前缀，用于调试
    extra_prefixes = set()
    for key in extra_state_dict.keys():
        prefix = key.split('.')[0]
        extra_prefixes.add(prefix)
    print(f"[INFO] 额外层模块: {sorted(extra_prefixes)}")

    return qwen2_state_dict, extra_state_dict


def save_qwen2_as_hf(qwen2_state_dict, blanken_dir, output_dir):
    """将 Qwen2ForCausalLM 的 state_dict 保存为 4bit 量化 HF 格式

    流程:
        1. 创建 Qwen2ForCausalLM 并加载原始权重 (fp16)
        2. 临时保存为 fp16 格式
        3. 用 BitsAndBytesConfig 4bit 重新加载
        4. 保存 4bit 量化后的模型 (磁盘占用大幅减少)

    Args:
        qwen2_state_dict: Qwen2ForCausalLM 的 state_dict
        blanken_dir: CosyVoice-BlankEN 目录 (用于获取 config.json 和 tokenizer)
        output_dir: 输出目录 (llm_qwen2/)
    """
    from transformers import Qwen2ForCausalLM, AutoConfig, BitsAndBytesConfig
    import tempfile

    os.makedirs(output_dir, exist_ok=True)

    print(f"[INFO] 从 {blanken_dir} 加载 Qwen2 配置...")
    config = AutoConfig.from_pretrained(blanken_dir)

    # 步骤 1: 创建模型并加载原始权重
    print("[INFO] 创建 Qwen2ForCausalLM 模型并加载原始权重 (fp16)...")
    model = Qwen2ForCausalLM(config)
    missing, unexpected = model.load_state_dict(qwen2_state_dict, strict=False)
    if missing:
        print(f"[WARN] 缺失的 key: {missing[:5]}...")
    if unexpected:
        print(f"[WARN] 多余的 key: {unexpected[:5]}...")

    # 步骤 2: 临时保存为 fp16 格式
    tmp_dir = output_dir + '_tmp_fp16'
    print(f"[INFO] 临时保存 fp16 模型到 {tmp_dir}...")
    model.save_pretrained(tmp_dir, safe_serialization=True)
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 步骤 3: 用 4bit 量化重新加载
    print("[INFO] 用 BitsAndBytes NF4 4bit 量化重新加载...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    quantized_model = Qwen2ForCausalLM.from_pretrained(
        tmp_dir,
        quantization_config=bnb_config,
        device_map="auto" if torch.cuda.is_available() else None,
        torch_dtype=torch.bfloat16,
    )

    # 步骤 4: 保存 4bit 量化模型
    print(f"[INFO] 保存 4bit 量化模型到 {output_dir}...")
    quantized_model.save_pretrained(output_dir, safe_serialization=True)

    del quantized_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 清理临时目录
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[INFO] 已清理临时目录: {tmp_dir}")

    # 复制 tokenizer 文件
    for fname in ['tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt']:
        src = os.path.join(blanken_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(output_dir, fname))

    print("[INFO] Qwen2ForCausalLM 4bit 量化保存完成")


def save_extra_state_dict(extra_state_dict, output_path):
    """保存额外层的 state_dict"""
    print(f"[INFO] 保存额外层到 {output_path}...")
    torch.save(extra_state_dict, output_path)
    print("[INFO] 额外层保存完成")


def copy_model_files(src_dir, dst_dir):
    """复制模型目录中的非 llm.pt 文件"""
    # 需要复制的文件 (llm.pt 会被替换为 llm_qwen2/ + llm_extra.pt)
    skip_files = {'llm.pt', 'llm.rl.pt'}

    # 复制顶层文件
    for item in os.listdir(src_dir):
        src_path = os.path.join(src_dir, item)
        dst_path = os.path.join(dst_dir, item)

        if item in skip_files:
            continue

        if os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)
        elif os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)

    print(f"[INFO] 模型文件已复制到 {dst_dir}")


def create_marker_file(dst_dir):
    """创建 4bit 量化标记文件"""
    marker = {
        "quantized": True,
        "quant_method": "bitsandbytes",
        "bits": 4,
        "quant_type": "nf4",
        "quantized_component": "llm.model (Qwen2ForCausalLM)",
        "description": "CosyVoice2 with 4bit NF4 quantized Qwen2ForCausalLM"
    }
    marker_path = os.path.join(dst_dir, "quantized_4bit.json")
    with open(marker_path, 'w', encoding='utf-8') as f:
        json.dump(marker, f, indent=2, ensure_ascii=False)
    print(f"[INFO] 标记文件已创建: {marker_path}")


def main():
    parser = argparse.ArgumentParser(description="CosyVoice2 模型 4bit 量化工具")
    parser.add_argument(
        "--model_path",
        type=str,
        default=r"C:\MyProjects\ai\CosyChat\pretrained_models\cosyvoice\CosyVoice2-0.5B",
        help="源模型目录路径",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default=r"C:\MyProjects\ai\CosyChat\pretrained_models\cosyvoice\CosyVoice2-0.5B-4bit",
        help="量化后模型输出目录",
    )

    args = parser.parse_args()
    model_path = os.path.abspath(args.model_path)
    output_path = os.path.abspath(args.output_path)

    if not os.path.exists(model_path):
        print(f"[ERROR] 模型路径不存在: {model_path}")
        sys.exit(1)

    print("=" * 60)
    print("CosyVoice2 模型 4bit 量化工具")
    print("=" * 60)
    print(f"源模型: {model_path}")
    print(f"输出路径: {output_path}")
    print("=" * 60)

    os.makedirs(output_path, exist_ok=True)

    # 1. 复制所有模型文件 (除了 llm.pt)
    print("\n[步骤 1/5] 复制模型文件...")
    copy_model_files(model_path, output_path)

    # 2. 加载并拆分 llm.pt
    print("\n[步骤 2/5] 拆分 llm.pt...")
    llm_pt_path = os.path.join(model_path, 'llm.pt')
    qwen2_state_dict, extra_state_dict = split_llm_state_dict(llm_pt_path)

    # 3. 保存 Qwen2ForCausalLM 为 HF 格式
    print("\n[步骤 3/5] 保存 Qwen2ForCausalLM 为 HF 格式...")
    blanken_dir = os.path.join(model_path, 'CosyVoice-BlankEN')
    llm_qwen2_dir = os.path.join(output_path, 'llm_qwen2')
    save_qwen2_as_hf(qwen2_state_dict, blanken_dir, llm_qwen2_dir)

    # 4. 保存额外层
    print("\n[步骤 4/5] 保存额外层...")
    llm_extra_path = os.path.join(output_path, 'llm_extra.pt')
    save_extra_state_dict(extra_state_dict, llm_extra_path)

    # 5. 创建标记文件
    print("\n[步骤 5/5] 创建标记文件...")
    create_marker_file(output_path)

    # 计算大小
    print("\n" + "=" * 60)
    print("量化完成!")
    print("=" * 60)

    original_size = os.path.getsize(llm_pt_path)
    qwen2_size = sum(
        os.path.getsize(os.path.join(llm_qwen2_dir, f))
        for f in os.listdir(llm_qwen2_dir)
        if f.endswith(('.safetensors', '.bin'))
    )
    extra_size = os.path.getsize(llm_extra_path)

    print(f"原始 llm.pt: {original_size / 1024**2:.2f} MB")
    print(f"  - Qwen2 (HF格式): {qwen2_size / 1024**2:.2f} MB")
    print(f"  - 额外层: {extra_size / 1024**2:.2f} MB")
    print(f"输出目录: {output_path}")

    total_size = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(output_path)
        for f in files
    )
    print(f"输出目录总大小: {total_size / 1024**3:.2f} GB")


if __name__ == "__main__":
    main()
