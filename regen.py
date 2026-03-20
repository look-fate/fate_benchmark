#!/usr/bin/env python3
"""
重新生成 AI 回答：对缓存中指定的命主重新调用排盘+解盘 API，更新缓存中的 solve_response。
用法:
    python3 regen.py <person_id>                     # 在所有缓存中查找
    python3 regen.py <person_id> <person_id> ...     # 批量重跑
    python3 regen.py --all-failed                    # 自动找出所有评分缺失的命主
"""
import argparse
import json
import os
import time

from benchmark import (
    birth_to_timestamp,
    call_bazi_arrange,
    call_bazi_solve,
    format_questions_with_options,
    get_result_dir,
    load_cache,
    save_cache,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_score_dir(mode):
    return os.path.join(SCRIPT_DIR, 'scores' if mode == 1 else f'scores-{mode}')


def infer_mode_from_cache_file(cache_file):
    dirname = os.path.basename(os.path.dirname(cache_file))
    if dirname.startswith('result-'):
        suffix = dirname.split('-', 1)[1]
        if suffix.isdigit():
            return int(suffix)
    return 1


def find_person_in_caches(person_id, result_dir=None):
    """在所有缓存文件中查找指定 person_id，返回 (cache_file, cache_dict)"""
    if result_dir is None:
        result_dirs = sorted(
            os.path.join(SCRIPT_DIR, d)
            for d in os.listdir(SCRIPT_DIR)
            if d.startswith('result-') and os.path.isdir(os.path.join(SCRIPT_DIR, d))
        )
    else:
        result_dirs = [result_dir]

    for current_result_dir in result_dirs:
        if not os.path.isdir(current_result_dir):
            continue
        for f in sorted(os.listdir(current_result_dir)):
            if not f.endswith('_cache.json'):
                continue
            cache_file = os.path.join(current_result_dir, f)
            cache = load_cache(cache_file)
            if person_id in cache:
                return cache_file, cache
    return None, None


def find_all_failed(result_dir, score_dir):
    """找出所有评分中缺失的 person_id，返回列表"""
    missing = []
    if not os.path.isdir(result_dir):
        return missing

    for f in sorted(os.listdir(result_dir)):
        if not f.endswith('_cache.json'):
            continue
        dataset_name = f.replace('_cache.json', '')
        cache_file = os.path.join(result_dir, f)
        score_file = os.path.join(score_dir, f'{dataset_name}.json')

        cache = load_cache(cache_file)
        if os.path.exists(score_file):
            with open(score_file, 'r', encoding='utf-8') as fp:
                scored = json.load(fp)
            scored_ids = set(d['person_id'] for d in scored.get('details', []))
        else:
            scored_ids = set()

        for pid in cache:
            if pid not in scored_ids:
                missing.append(pid)
    return missing


def regen_person(person_id, mode=None, theory=1, agent_id=4, result_dir=None):
    """重新排盘+解盘，更新缓存"""
    cache_file, cache = find_person_in_caches(person_id, result_dir=result_dir)
    if not cache:
        print(f"[{person_id}] 未在任何缓存中找到，跳过")
        return False

    pdata = cache[person_id]
    profile = pdata['profile']
    birth = profile['birth']
    gender = profile['gender']

    timestamp = birth_to_timestamp(
        birth['year'], birth['month'], birth['day'],
        birth['hour'], birth.get('minute', 0)
    )
    gender_int = 1 if gender == 'male' else 0

    print(f"\n{'=' * 60}")
    print(f"[{person_id}]")
    print(f"  出生: {birth['year']}-{birth['month']:02d}-{birth['day']:02d} {birth['hour']:02d}:{birth.get('minute', 0):02d}")
    print(f"  性别: {gender}")

    # Step 1: 排盘
    print(f"  [排盘] ...")
    try:
        status, arrange_resp = call_bazi_arrange(timestamp, gender_int)
    except Exception as e:
        print(f"  [排盘错误] {e}")
        return False

    if status != 200:
        print(f"  [排盘失败] status={status}")
        return False

    raw_data = arrange_resp.get('data', arrange_resp) if isinstance(arrange_resp, dict) else arrange_resp
    if isinstance(raw_data, dict):
        raw_data['gender'] = '男' if gender == 'male' else '女'
    raw_json_str = json.dumps(raw_data, ensure_ascii=False)

    if isinstance(raw_data, dict):
        pillars = []
        for key in ['yearPillar', 'monthPillar', 'dayPillar', 'hourPillar']:
            p = raw_data.get(key, {})
            if p:
                pillars.append(f"{p.get('heavenlyStems', '?')}{p.get('earthlyBranches', '?')}")
        print(f"  [四柱] {' '.join(pillars)}")

    # Step 2: 解盘
    questions = pdata['questions']
    question_text = format_questions_with_options(questions)
    print(f"  [解盘] 发送 {len(questions)} 个问题...")

    try:
        solve_mode = mode if mode is not None else infer_mode_from_cache_file(cache_file)
        status2, solve_resp = call_bazi_solve(
            question_text,
            raw_json_str,
            agent_id=agent_id,
            mode=solve_mode,
            theory=theory,
        )
    except Exception as e:
        print(f"  [解盘错误] {e}")
        return False

    print(f"  [解盘响应] status={status2}, resp={solve_resp}")

    # 更新缓存
    old_uuid = pdata.get('solve_response', {}).get('data', '?')
    new_uuid = solve_resp.get('data', '?')
    pdata['solve_response'] = solve_resp
    save_cache(cache_file, cache)
    print(f"  [更新缓存] {old_uuid} -> {new_uuid}")

    return True


def main():
    parser = argparse.ArgumentParser(description="重新生成指定命主的解盘缓存")
    parser.add_argument('person_ids', nargs='*', help='要重跑的 person_id')
    parser.add_argument('--all-failed', action='store_true', help='自动找出评分缺失的命主')
    parser.add_argument('--mode', type=int, choices=[0, 1], help='解盘接口 mode；也用于默认结果目录')
    parser.add_argument('--theory', type=int, default=1, help='解盘接口 theory，默认 1')
    parser.add_argument('--agent-id', type=int, default=4, help='解盘接口 agentId，默认 4')
    args = parser.parse_args()

    if not args.all_failed and not args.person_ids:
        parser.print_help()
        return

    result_dir = get_result_dir(args.mode) if args.mode is not None else None
    score_dir = get_score_dir(args.mode) if args.mode is not None else get_score_dir(1)

    if args.all_failed:
        if result_dir is None:
            result_dir = get_result_dir(1)
        person_ids = find_all_failed(result_dir, score_dir)
        if not person_ids:
            print("没有缺失的命主")
            return
        print(f"找到 {len(person_ids)} 个缺失命主: {person_ids}")
    else:
        person_ids = args.person_ids

    success = 0
    for i, pid in enumerate(person_ids):
        if regen_person(
            pid,
            mode=args.mode,
            theory=args.theory,
            agent_id=args.agent_id,
            result_dir=result_dir,
        ):
            success += 1
        if i < len(person_ids) - 1:
            print("\n  等待 60 秒...")
            time.sleep(60)

    print(f"\n完成: {success}/{len(person_ids)} 个命主重新生成成功")
    if success > 0:
        print("接下来运行 python3 patch_scores.py 补全评分")


if __name__ == '__main__':
    main()
