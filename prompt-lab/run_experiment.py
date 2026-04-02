#!/usr/bin/env python3
"""
Prompt 实验运行器
读取 prompt + 输入，调用模型，记录输出
用法: python3 run_experiment.py <exp_dir>
"""
import json
import subprocess
import sys
import os
from datetime import datetime

# 测试输入
TEST_INPUTS = [
    "今天天气怎么样？",
    "帮我写一个快速排序算法",
    "什么是量子计算？",
    "推荐三本关于AI的书",
    "解释一下什么是递归",
]

EXPECTED_CATEGORIES = ["weather", "coding", "science", "recommendation", "explanation"]

def run_single_test(prompt_path, user_input, run_id, exp_dir):
    """运行单次测试，返回结果"""
    with open(prompt_path) as f:
        system_prompt = f.read()
    
    # 构造完整的 prompt 用于输出记录
    full_prompt = f"""System Prompt:
{system_prompt}

---

User: {user_input}"""
    
    # 记录 prompt
    run_dir = os.path.join(exp_dir, "runs")
    os.makedirs(run_dir, exist_ok=True)
    
    prompt_file = os.path.join(run_dir, f"run-{run_id:03d}-prompt.txt")
    with open(prompt_file, "w") as f:
        f.write(full_prompt)
    
    print(f"  Run {run_id}: prompt saved to {prompt_file}")
    print(f"  Input: {user_input}")
    print(f"  → 请用该 prompt 在目标模型上运行，将输出保存到 run-{run_id:03d}-output.txt")
    
    return prompt_file

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 run_experiment.py <exp_dir>")
        sys.exit(1)
    
    exp_dir = sys.argv[1]
    prompt_path = os.path.join(exp_dir, "prompt.md")
    
    if not os.path.exists(prompt_path):
        print(f"Error: {prompt_path} not found")
        sys.exit(1)
    
    print(f"Running experiment from: {exp_dir}")
    print(f"Prompt: {prompt_path}")
    print(f"Test inputs: {len(TEST_INPUTS)}")
    print("=" * 50)
    
    run_id = 1
    for user_input in TEST_INPUTS:
        run_single_test(prompt_path, user_input, run_id, exp_dir)
        run_id += 1
    
    print("=" * 50)
    print(f"All {len(TEST_INPUTS)} runs prepared.")
    print(f"Next: run each prompt against the target model, save outputs to runs/")
    print(f"Then: python3 scorers/json_validator.py runs/run-XXX-output.txt scorers/task-01-schema.json")

if __name__ == "__main__":
    main()
