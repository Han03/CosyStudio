"""
DreamLite 模型 4bit 量化脚本

使用 bitsandbytes NF4 量化 text_encoder (Qwen3VL)，可选量化 UNet。
量化后模型可以节省约 60-75% 的显存和磁盘空间。

用法:
    python quantize_dreamlite.py --model_path <源模型路径> --output_path <输出路径> [--quantize_unet]

注意:
- text_encoder 量化收益最大 (4GB -> ~1GB)，质量损失极小
- UNet 量化可能影响生成质量，建议先不测 UNet
- VAE 只有 ~5MB，不需要量化
"""

import os
import sys
import argparse
import shutil
import json
import torch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def copy_non_model_files(src_dir, dst_dir):
    """复制非模型文件（配置、tokenizer等）"""
    os.makedirs(dst_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        src_item = os.path.join(src_dir, item)
        dst_item = os.path.join(dst_dir, item)
        if os.path.isdir(src_item):
            if item in ("text_encoder", "unet", "vae"):
                continue
            shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
        else:
            shutil.copy2(src_item, dst_item)
    print(f"[INFO] 非模型文件已复制到 {dst_dir}")


def quantize_text_encoder(model_path, output_path):
    """
    量化 text_encoder (Qwen3VL) 为 4bit NF4

    注意: bitsandbytes 量化模型无法直接保存为标准 safetensors，
    这里使用 load_in_4bit 加载后，用 state_dict 方式保存。
    实际使用时仍需用 load_in_4bit=True 加载。
    """
    from transformers import Qwen3VLForConditionalGeneration, AutoConfig
    from transformers import BitsAndBytesConfig

    print("\n" + "=" * 60)
    print("[TEXT_ENCODER] 开始量化 text_encoder")
    print("=" * 60)

    text_encoder_dir = os.path.join(model_path, "text_encoder")
    text_encoder_out = os.path.join(output_path, "text_encoder")
    os.makedirs(text_encoder_out, exist_ok=True)

    # 复制配置文件
    for f in os.listdir(text_encoder_dir):
        if not f.endswith(".safetensors") and not f.endswith(".bin"):
            src = os.path.join(text_encoder_dir, f)
            dst = os.path.join(text_encoder_out, f)
            if os.path.isfile(src):
                shutil.copy2(src, dst)

    print("[TEXT_ENCODER] 正在加载原始模型 (bfloat16)...")

    # 先用低内存模式加载
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        text_encoder_dir,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    print("[TEXT_ENCODER] 模型加载完成，正在保存量化模型...")

    # bitsandbytes 量化模型保存方式
    model.save_pretrained(text_encoder_out, safe_serialization=True)

    # 标记为量化模型
    config_path = os.path.join(text_encoder_out, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["quantization_config"] = {
        "quant_method": "bitsandbytes",
        "load_in_4bit": True,
        "bnb_4bit_use_double_quant": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "bfloat16",
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"[TEXT_ENCODER] 量化完成，输出: {text_encoder_out}")

    # 计算大小
    original_size = sum(
        os.path.getsize(os.path.join(text_encoder_dir, f))
        for f in os.listdir(text_encoder_dir)
        if f.endswith((".safetensors", ".bin"))
    )
    quantized_size = sum(
        os.path.getsize(os.path.join(text_encoder_out, f))
        for f in os.listdir(text_encoder_out)
        if f.endswith((".safetensors", ".bin"))
    )
    print(f"[TEXT_ENCODER] 原始: {original_size / 1024**3:.2f} GB")
    print(f"[TEXT_ENCODER] 量化后: {quantized_size / 1024**3:.2f} GB")
    print(f"[TEXT_ENCODER] 节省: {(1 - quantized_size / original_size) * 100:.1f}%")

    del model
    torch.cuda.empty_cache()


def quantize_unet(model_path, output_path):
    """
    量化 UNet 为 4bit

    注意: 扩散模型 UNet 的 4bit 量化可能影响生成质量，
    建议仅在显存紧张时使用。
    """
    print("\n" + "=" * 60)
    print("[UNet] 开始量化 UNet")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
    from dreamlite.models.unets import DreamLiteUNetModel

    unet_dir = os.path.join(model_path, "unet")
    unet_out = os.path.join(output_path, "unet")
    os.makedirs(unet_out, exist_ok=True)

    print("[UNet] 正在加载原始 UNet...")

    unet = DreamLiteUNetModel.from_pretrained(unet_dir)
    unet = unet.to(torch.bfloat16)

    # 使用 torchao 进行 4bit 量化
    try:
        import torchao
        from torchao.quantization import quantize_, int4_weight_only
        print("[UNet] 使用 torchao 进行 4bit 量化...")

        unet = unet.to("cuda")
        quantize_(unet, int4_weight_only(group_size=32))

        print("[UNet] 量化完成，正在保存...")
        unet.save_pretrained(unet_out, safe_serialization=True)

    except ImportError:
        print("[UNET] torchao 不可用，尝试使用 bitsandbytes...")
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        unet = DreamLiteUNetModel.from_pretrained(
            unet_dir,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
        )
        unet.save_pretrained(unet_out, safe_serialization=True)

    # 标记为量化模型
    config_path = os.path.join(unet_out, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        config["quantized"] = True
        config["quant_method"] = "int4"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"[UNet] 量化完成，输出: {unet_out}")

    # 计算大小
    original_size = sum(
        os.path.getsize(os.path.join(unet_dir, f))
        for f in os.listdir(unet_dir)
        if f.endswith((".safetensors", ".bin"))
    )
    quantized_size = sum(
        os.path.getsize(os.path.join(unet_out, f))
        for f in os.listdir(unet_out)
        if f.endswith((".safetensors", ".bin"))
    )
    print(f"[UNet] 原始: {original_size / 1024**2:.2f} MB")
    print(f"[UNet] 量化后: {quantized_size / 1024**2:.2f} MB")
    print(f"[UNet] 节省: {(1 - quantized_size / original_size) * 100:.1f}%")

    del unet
    torch.cuda.empty_cache()


def copy_vae(model_path, output_path):
    """复制 VAE（太小，不需要量化）"""
    vae_dir = os.path.join(model_path, "vae")
    vae_out = os.path.join(output_path, "vae")
    if os.path.exists(vae_dir):
        shutil.copytree(vae_dir, vae_out, dirs_exist_ok=True)
        print(f"[VAE] 已复制 VAE 到 {vae_out}")


def main():
    parser = argparse.ArgumentParser(description="DreamLite 模型 4bit 量化工具")
    parser.add_argument(
        "--model_path",
        type=str,
        required=True,
        help="源模型目录路径",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="量化后模型输出目录",
    )
    parser.add_argument(
        "--quantize_unet",
        action="store_true",
        help="是否同时量化 UNet（可能影响质量，谨慎使用）",
    )
    parser.add_argument(
        "--quantize_text_encoder",
        action="store_true",
        default=True,
        help="量化 text_encoder（默认开启，收益最大）",
    )

    args = parser.parse_args()

    model_path = os.path.abspath(args.model_path)
    output_path = os.path.abspath(args.output_path)

    if not os.path.exists(model_path):
        print(f"[ERROR] 模型路径不存在: {model_path}")
        sys.exit(1)

    print("=" * 60)
    print("DreamLite 模型 4bit 量化工具")
    print("=" * 60)
    print(f"源模型: {model_path}")
    print(f"输出路径: {output_path}")
    print(f"量化 text_encoder: {args.quantize_text_encoder}")
    print(f"量化 UNet: {args.quantize_unet}")
    print("=" * 60)

    # 复制非模型文件
    copy_non_model_files(model_path, output_path)

    # 复制 VAE
    copy_vae(model_path, output_path)

    # 量化 text_encoder
    if args.quantize_text_encoder:
        try:
            quantize_text_encoder(model_path, output_path)
        except Exception as e:
            print(f"[ERROR] text_encoder 量化失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # 量化或复制 UNet
    unet_dir = os.path.join(model_path, "unet")
    unet_out = os.path.join(output_path, "unet")
    if args.quantize_unet:
        try:
            quantize_unet(model_path, output_path)
        except Exception as e:
            print(f"[ERROR] UNet 量化失败: {e}")
            import traceback
            traceback.print_exc()
            print("[WARN] UNet 量化失败，使用原始 UNet")
            if os.path.exists(unet_dir):
                shutil.copytree(unet_dir, unet_out, dirs_exist_ok=True)
    else:
        if os.path.exists(unet_dir):
            shutil.copytree(unet_dir, unet_out, dirs_exist_ok=True)
            print(f"[UNet] 已复制原始 UNet 到 {unet_out}")

    # 更新 model_index.json
    model_index_path = os.path.join(output_path, "model_index.json")
    if os.path.exists(model_index_path):
        with open(model_index_path, "r", encoding="utf-8") as f:
            model_index = json.load(f)
        model_index["quantized"] = True
        model_index["quant_method"] = "nf4" if args.quantize_text_encoder else "none"
        with open(model_index_path, "w", encoding="utf-8") as f:
            json.dump(model_index, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("量化完成!")
    print(f"输出目录: {output_path}")
    print("=" * 60)

    # 计算总大小
    total_original = 0
    total_quantized = 0
    for component in ["text_encoder", "unet", "vae"]:
        src_dir = os.path.join(model_path, component)
        dst_dir = os.path.join(output_path, component)
        if os.path.exists(src_dir):
            for f in os.listdir(src_dir):
                if f.endswith((".safetensors", ".bin")):
                    total_original += os.path.getsize(os.path.join(src_dir, f))
        if os.path.exists(dst_dir):
            for f in os.listdir(dst_dir):
                if f.endswith((".safetensors", ".bin")):
                    total_quantized += os.path.getsize(os.path.join(dst_dir, f))

    print(f"总原始大小: {total_original / 1024**3:.2f} GB")
    print(f"总量化后大小: {total_quantized / 1024**3:.2f} GB")
    print(f"节省空间: {(1 - total_quantized / total_original) * 100:.1f}%")


if __name__ == "__main__":
    main()
