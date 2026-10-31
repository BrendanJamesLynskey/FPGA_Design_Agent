# F1B candidates: OpenRouter's public model list, 2026-10-31 (tools/models.py at aa7404c)

| Model | Exists | $/M input | $/M output | Context | `reasoning` parameter | Other prices (input/output) |
|---|---|---|---|---|---|---|
| `openai/gpt-6-luna` | yes | $0.100 | $0.500 | 1,050,000 | yes (efforts: max, xhigh, high, medium, low, none; default medium; on by default) | $0.200/$0.750 for prompt ≥ 272,000 tokens |
| `deepseek/deepseek-v4.1-flash-1017` | yes | $0.150 | $0.600 | 1,048,576 | yes (efforts: max, high, low, none; default high; on by default) | $0.150/$0.600 for weekends, weekdays 00:00–01:00 UTC, weekdays 04:00–06:00 UTC, weekdays 10:00–00:00 UTC; $0.300/$1.200 for weekdays 01:00–04:00 UTC, weekdays 06:00–10:00 UTC |
| `z-ai/glm-5.3-flash` | yes | $0.024 | $0.114 | 1,048,576 | yes (efforts: max, high, low; default max; on by default; mandatory (no `none`)) |  |
| `minimax/minimax-m3.1-flash` | yes | $0.075 | $0.300 | 1,048,576 | yes (efforts: max, xhigh, high, medium, low; default max; mandatory (no `none`)) | $0.075/$0.300 for 15:00–01:00 UTC; $0.150/$0.600 for 01:00–15:00 UTC |

Filter used for the shortlist (same list): open weights (a Hugging Face id), `tools` and `structured_outputs` in supported_parameters, context ≥ 128k, list price ≤ luna's ($0.10/$0.50).

```
deepseek/deepseek-v4-flash                    in $0.091 out $0.182 ctx  1048576 weights deepseek-ai/DeepSeek-V4-Flash
deepseek/deepseek-v4.1-flash                  in $0.045 out $0.500 ctx  1048576 weights deepseek-ai/DeepSeek-V4.1-Flash
google/gemma-3-12b-it                         in $0.050 out $0.150 ctx   131072 weights google/gemma-3-12b-it
google/gemma-3-27b-it                         in $0.080 out $0.350 ctx   131072 weights google/gemma-3-27b-it
google/gemma-4-26b-a4b-it                     in $0.068 out $0.225 ctx   262144 weights google/gemma-4-26B-A4B-it
ibm-granite/granite-4.2-8b                    in $0.060 out $0.150 ctx   131072 weights ibm-granite/granite-4.2-8b
inclusionai/ling-3.0-flash-vl                 in $0.060 out $0.180 ctx   131072 weights inclusionAI/Ling-3.0-flash-VL
meta-llama/llama-3.1-8b-instruct              in $0.050 out $0.080 ctx   131072 weights meta-llama/Meta-Llama-3.1-8B-Instruct
meta-llama/llama-3.3-70b-instruct             in $0.100 out $0.320 ctx   131072 weights meta-llama/Llama-3.3-70B-Instruct
meta-llama/llama-4-scout                      in $0.100 out $0.300 ctx  1310720 weights meta-llama/Llama-4-Scout-17B-16E-Instruct
minimax/minimax-m3.1-flash                    in $0.075 out $0.300 ctx  1048576 weights MiniMaxAI/MiniMax-M3.1-Flash
mistralai/ministral-3b-2512                   in $0.100 out $0.100 ctx   131072 weights mistralai/Ministral-3-3B-Instruct-2512
mistralai/mistral-nemo                        in $0.029 out $0.030 ctx   131072 weights mistralai/Mistral-Nemo-Instruct-2407
mistralai/mistral-small-3.2-24b-instruct      in $0.075 out $0.200 ctx   256000 weights mistralai/Mistral-Small-3.2-24B-Instruct-2506
nex-agi/nex-n2.5-pro                          in $0.075 out $0.250 ctx   262144 weights nex-agi/Nex-N2.5-Pro
nvidia/nemotron-3-nano-30b-a3b                in $0.060 out $0.240 ctx   262144 weights nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16
nvidia/nemotron-3.5-lightning                 in $0.070 out $0.200 ctx   262144 weights nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16
openai/gpt-oss-20b                            in $0.018 out $0.090 ctx   131072 weights openai/gpt-oss-20b
openai/gpt-oss-safeguard-20b                  in $0.075 out $0.300 ctx   131072 weights openai/gpt-oss-safeguard-20b
prism-ml/ternary-bonsai-2-27b                 in $0.075 out $0.500 ctx   262144 weights prism-ml/Ternary-Bonsai-2-27B-gguf
prism-ml/ternary-bonsai-2-9b                  in $0.080 out $0.130 ctx   262144 weights prism-ml/Ternary-Bonsai-2-9B-gguf
qwen/qwen3-30b-a3b-instruct-2507              in $0.100 out $0.300 ctx   262144 weights Qwen/Qwen3-30B-A3B-Instruct-2507
qwen/qwen3-32b                                in $0.080 out $0.280 ctx   131072 weights Qwen/Qwen3-32B
qwen/qwen3-coder-30b-a3b-instruct             in $0.070 out $0.280 ctx   262144 weights Qwen/Qwen3-Coder-30B-A3B-Instruct
z-ai/glm-4.7-flash                            in $0.061 out $0.400 ctx   200000 weights zai-org/GLM-4.7-Flash
z-ai/glm-5.3-flash                            in $0.022 out $0.124 ctx  1048576 weights zai-org/GLM-5.3-Flash
```
