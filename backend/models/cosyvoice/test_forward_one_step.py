import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch
import logging
logging.basicConfig(level=logging.INFO)

from llm.llm import Qwen2Encoder

model_path = 'c:/MyProjects/ai/CosyChat/pretrained_models/cosyvoice/iic_CosyVoice2-0.5B/CosyVoice-BlankEN'

print(f"Loading Qwen2Encoder from: {model_path}")
encoder = Qwen2Encoder(model_path)
encoder.eval()

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
encoder = encoder.to(device)

print("\n=== Testing forward_one_step with different input shapes ===")

batch_size = 1
hidden_size = 896

print("\n--- Test 1: Initial call with multiple tokens ---")
xs = torch.randn(batch_size, 5, hidden_size).to(device)
seq_len = xs.shape[1]
masks = torch.tril(torch.ones((batch_size, seq_len, seq_len), device=device)).to(torch.bool)

print(f"  xs shape: {xs.shape}")
print(f"  masks shape: {masks.shape}")
print(f"  masks[:, -1, :]: {masks[:, -1, :]}")

y_pred, cache = encoder.forward_one_step(xs, masks, cache=None)
print(f"  y_pred shape: {y_pred.shape}")
print(f"  cache type: {type(cache)}")

if cache is not None:
    try:
        print(f"  cache[0][0] shape: {cache[0][0].shape}")
    except:
        try:
            from transformers.cache_utils import DynamicCache
            if isinstance(cache, DynamicCache):
                print(f"  cache is DynamicCache")
                if hasattr(cache, 'layers') and cache.layers:
                    first_layer = cache.layers[0]
                    if hasattr(first_layer, 'keys'):
                        print(f"  first_layer.keys shape: {first_layer.keys.shape}")
        except:
            print(f"  cache type: {type(cache)}")

print("\n--- Test 2: Second call with single token and cache ---")
xs2 = torch.randn(batch_size, 1, hidden_size).to(device)
seq_len2 = xs2.shape[1]
masks2 = torch.tril(torch.ones((batch_size, seq_len + seq_len2, seq_len + seq_len2), device=device)).to(torch.bool)

print(f"  xs2 shape: {xs2.shape}")
print(f"  masks2 shape: {masks2.shape}")
print(f"  masks2[:, -1, :]: {masks2[:, -1, :]}")

y_pred2, cache2 = encoder.forward_one_step(xs2, masks2, cache=cache)
print(f"  y_pred2 shape: {y_pred2.shape}")

print("\n=== Analysis ===")
print("The issue: when using cache, attention_mask should indicate")
print("which positions in the CURRENT input are valid, not the full sequence.")
print("In transformers 4.57.3, when past_key_values is provided,")
print("attention_mask only needs to cover the NEW tokens, not all previous ones.")
