#!/bin/bash
# Experiment only: Qwen3-VL-32B BF16 (66.7 GB) does not fit one 64 GB GCD, so it runs with
# tensor parallel 2 on GCD 2+3 — outside vlm_server's one-GPU rule, straight vllm serve.
docker rm -f mentormind-vlm-32b 2>/dev/null
docker run -d --name mentormind-vlm-32b \
  --device /dev/kfd --device /dev/dri --group-add 44 --group-add 109 \
  --security-opt seccomp=unconfined --ipc host --shm-size 16g \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -p 127.0.0.1:8101:8101 \
  -e HIP_VISIBLE_DEVICES=2,3 -e CUDA_VISIBLE_DEVICES=2,3 -e VLLM_ROCM_USE_AITER=0 -e HF_HUB_OFFLINE=1 \
  --entrypoint python3 vlm-engine:rocm -m vllm.entrypoints.cli.main serve Qwen/Qwen3-VL-32B-Instruct \
  --host 0.0.0.0 --port 8101 --served-model-name Qwen/Qwen3-VL-32B-Instruct \
  --tensor-parallel-size 2 --dtype bfloat16 --gpu-memory-utilization 0.90 --max-model-len 32768 \
  --max-num-seqs 4 --limit-mm-per-prompt '{"image":64,"video":0}' --mm-processor-kwargs '{"max_pixels":409600}'
