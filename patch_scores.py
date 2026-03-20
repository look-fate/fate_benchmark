#!/usr/bin/env python3
"""补全评分缺失的命主：找出 cache 中有但 scores 中缺失的命主，重新评分并合并"""
import argparse
import json
import os
import time

from benchmark import get_result_dir
from score import (
    get_score_dir,
    fetch_ai_answer,
    score_person,
    compute_stats,
    print_report,
    _retry,
    DIMENSIONS,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_missing(cache, scored_details):
    """找出缓存中有但评分中缺失的 person_id"""
    scored_ids = set(d['person_id'] for d in scored_details)
    return [pid for pid in cache if pid not in scored_ids]


def patch_dataset(dataset_name, result_dir, score_dir):
    cache_file = os.path.join(result_dir, f'{dataset_name}_cache.json')
    score_file = os.path.join(score_dir, f'{dataset_name}.json')

    if not os.path.exists(cache_file) or not os.path.exists(score_file):
        print(f"[跳过] {dataset_name}: 缓存或评分文件不存在")
        return

    with open(cache_file, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    with open(score_file, 'r', encoding='utf-8') as f:
        score_data = json.load(f)

    missing = find_missing(cache, score_data['details'])
    if not missing:
        print(f"[{dataset_name}] 无缺失，跳过")
        return

    print(f"\n[{dataset_name}] 发现 {len(missing)} 个缺失命主: {missing}")

    for i, pid in enumerate(missing):
        pdata = cache[pid]
        solve_resp = pdata.get('solve_response', {})
        uuid = solve_resp.get('data')

        if not uuid or solve_resp.get('code') != 200:
            print(f"  [{pid}] UUID 无效，跳过")
            continue

        print(f"  [{pid}] 获取 AI 回答... uuid={uuid}")
        try:
            ai_answer = _retry(fetch_ai_answer, uuid)
        except Exception as e:
            print(f"  [{pid}] 获取回答失败: {e}")
            continue

        if not ai_answer:
            print(f"  [{pid}] 回答为空，跳过")
            continue

        print(f"  [{pid}] AI 回答长度: {len(ai_answer)} 字符")
        print(f"  [{pid}] 调用 Gemini 评分...")

        try:
            scored = _retry(score_person, pid, pdata, ai_answer)
        except Exception as e:
            print(f"  [{pid}] 评分失败: {e}")
            continue

        for s in scored:
            s['person_id'] = pid
            s['dataset'] = dataset_name
            mark = "✓" if s['is_correct'] else "✗"
            print(f"    Q{s['question_index']}: {mark} AI={s['ai_answer']} 正确={s['correct_answer']} [{s['dimension']}]")

        score_data['details'].extend(scored)

        if i < len(missing) - 1:
            time.sleep(15)

    # 重新计算统计
    score_data['stats'] = compute_stats(score_data['details'])
    print_report(score_data['stats'], dataset_name)

    with open(score_file, 'w', encoding='utf-8') as f:
        json.dump(score_data, f, ensure_ascii=False, indent=2)
    print(f"  已更新: {score_file}")


def main():
    parser = argparse.ArgumentParser(description="补全评分缺失的命主")
    parser.add_argument('result_dir', nargs='?', help='结果目录，默认使用当前 mode 对应目录')
    parser.add_argument('score_dir', nargs='?', help='评分目录，默认使用当前 mode 对应目录')
    parser.add_argument('--mode', type=int, default=1, choices=[0, 1], help='默认目录使用的 mode，默认 1')
    args = parser.parse_args()

    result_dir = args.result_dir or get_result_dir(args.mode)
    score_dir = args.score_dir or get_score_dir(args.mode)

    if not os.path.isdir(result_dir):
        print(f"目录不存在: {result_dir}")
        return

    datasets = sorted(
        f.replace('_cache.json', '')
        for f in os.listdir(result_dir)
        if f.endswith('_cache.json')
    )

    for ds in datasets:
        patch_dataset(ds, result_dir, score_dir)

    # 重新生成汇总
    print("\n重新生成汇总...")
    os.system(f'python3 {os.path.join(SCRIPT_DIR, "stats.py")} "{score_dir}"')


if __name__ == '__main__':
    main()
