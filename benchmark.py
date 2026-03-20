#!/usr/bin/env python3
"""
BaziQA Benchmark - 测试 AI 八字分析能力
流程: 读取数据集 -> 调用排盘API -> 调用解盘AI -> 记录结果
已问过的命例会缓存到 result-<mode>/<dataset>_cache.json，不会重复请求
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_env():
    env_file = os.path.join(SCRIPT_DIR, '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

BASE_URL = "https://api.lookfate.com"
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9',
    'authorization': AUTH_TOKEN,
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    'origin': 'https://www.lookfate.com',
    'pragma': 'no-cache',
    'referer': 'https://www.lookfate.com/',
    'site-id': '1',
    'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
}


def get_result_dir(mode):
    return os.path.join(SCRIPT_DIR, f'result-{mode}')


def load_cache(cache_file):
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache_file, cache):
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def birth_to_timestamp(year, month, day, hour, minute=0):
    china_tz = timezone(timedelta(hours=8))
    dt = datetime(year, month, day, hour, minute, tzinfo=china_tz)
    return int(dt.timestamp())


def call_bazi_arrange(timestamp, gender_int):
    payload = {"time": timestamp, "gender": gender_int, "zaoWan": False}
    print(f"  [排盘请求] timestamp={timestamp}, gender={gender_int}")
    resp = requests.post(f"{BASE_URL}/helper/bazi-arrange", headers=HEADERS, json=payload, timeout=30)
    return resp.status_code, resp.json()


def call_bazi_solve(question_text, raw_json_str, agent_id=4, mode=1, theory=1):
    payload = {
        "agentId": agent_id,
        "question": question_text,
        "raw": raw_json_str,
        "mode": mode,
        "theory": theory
    }
    resp = requests.post(
        f"{BASE_URL}/agent/bazi-solve",
        headers=HEADERS,
        json=payload,
        timeout=120,
        stream=True
    )
    return resp.status_code, resp.json()


def format_questions_with_options(questions):
    parts = []
    for i, q in enumerate(questions, 1):
        text = f"{i}. {q['question']}"
        for opt in q['options']:
            text += f"\n{opt}"
        parts.append(text)
    return "\n\n".join(parts)


def process_person(person, person_index, cache, cache_file, mode=1, theory=1, agent_id=4):
    person_id = person['person_id']

    # 检查缓存，已问过则跳过
    if person_id in cache:
        print(f"\n{'=' * 60}")
        print(f"[{person_index}] {person.get('name', person_id)} - 已缓存，跳过")
        return cache[person_id]

    profile = person['profile']
    birth = profile['birth']
    gender = profile['gender']

    timestamp = birth_to_timestamp(
        birth['year'], birth['month'], birth['day'],
        birth['hour'], birth.get('minute', 0)
    )
    gender_int = 0 if gender == 'male' else 1

    result = {
        'person_id': person_id,
        'name': person.get('name', ''),
        'birth': birth,
        'gender': gender,
        'timestamp': timestamp,
        'gender_int': gender_int,
    }

    print(f"\n{'=' * 60}")
    print(f"[{person_index}] {person.get('name', person_id)}")
    print(f"  出生: {birth['year']}-{birth['month']:02d}-{birth['day']:02d} "
          f"{birth['hour']:02d}:{birth.get('minute', 0):02d}")
    print(f"  性别: {gender} (API gender={gender_int})")
    print(f"  时间戳: {timestamp}")

    # Step 1: 排盘
    try:
        status, arrange_resp = call_bazi_arrange(timestamp, gender_int)
    except Exception as e:
        print(f"  [排盘错误] {e}")
        result['arrange_error'] = str(e)
        return result

    print(f"  [排盘响应] status={status}")
    result['arrange_status'] = status
    result['arrange_response'] = arrange_resp

    if status != 200:
        print(f"  [排盘失败] {json.dumps(arrange_resp, ensure_ascii=False)[:200]}")
        return result

    # 提取 raw 数据
    if isinstance(arrange_resp, dict) and 'data' in arrange_resp:
        raw_data = arrange_resp['data']
    else:
        raw_data = arrange_resp

    if isinstance(raw_data, dict):
        raw_data['gender'] = '男' if gender == 'male' else '女'

    raw_json_str = json.dumps(raw_data, ensure_ascii=False)
    result['raw_data_preview'] = raw_json_str[:300]

    # 打印排盘关键信息
    if isinstance(raw_data, dict):
        for pillar_key in ['yearPillar', 'monthPillar', 'dayPillar', 'hourPillar']:
            p = raw_data.get(pillar_key, {})
            if p:
                hs = p.get('heavenlyStems', '?')
                eb = p.get('earthlyBranches', '?')
                print(f"  {pillar_key}: {hs}{eb}")

    # Step 2: 构建问题
    questions = person['questions']
    question_text = format_questions_with_options(questions)
    print(question_text)
    print(f"\n  [解盘] 发送 {len(questions)} 个问题...")

    # Step 3: 解盘
    try:
        status2, solve_resp = call_bazi_solve(
            question_text,
            raw_json_str,
            agent_id=agent_id,
            mode=mode,
            theory=theory,
        )
    except Exception as e:
        print(f"  [解盘错误] {e}")
        result['solve_error'] = str(e)
        return result

    print(f"  [解盘响应] status={status2}, resp={solve_resp}")

    # 缓存: person_id -> {问题、正确答案、solve响应}
    questions = person['questions']
    cache[person_id] = {
        'profile': person['profile'],
        'questions': [{'question': q['question'], 'options': q['options'], 'answer': q['answer']} for q in questions],
        'solve_response': solve_resp
    }
    save_cache(cache_file, cache)
    print(f"  [缓存] 已保存 {person_id}")

    return cache[person_id]


def run_dataset(dataset_file, mode=1, theory=1, agent_id=4):
    print(f"\n{'#' * 60}")
    print(f"数据集: {dataset_file}")

    with open(dataset_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    metadata = data[0]
    persons = data[1:]

    print(f"竞赛: {metadata.get('contest_id', 'unknown')}")
    print(f"命主数量: {len(persons)}")
    print(f"总题数: {metadata.get('total_questions', 'unknown')}")

    # 加载缓存
    output_dir = get_result_dir(mode)
    basename = os.path.basename(dataset_file).replace('.json', '')
    cache_file = os.path.join(output_dir, f'{basename}_cache.json')
    cache = load_cache(cache_file)
    cached_count = sum(1 for p in persons if p['person_id'] in cache)
    print(f"已缓存: {cached_count}/{len(persons)}")
    print(f"模式: mode={mode}, theory={theory}, agent_id={agent_id}")
    print(f"结果目录: {output_dir}")

    for idx, person in enumerate(persons, 1):
        was_cached = person['person_id'] in cache
        process_person(
            person,
            idx,
            cache,
            cache_file,
            mode=mode,
            theory=theory,
            agent_id=agent_id,
        )
        if not was_cached and idx < len(persons):
            print(f"\n  等待 30 秒...")
            time.sleep(30)

    print(f"\n[汇总] {os.path.basename(dataset_file)}: 共 {len(persons)} 个命主")
    print(f"结果已保存: {cache_file}")


def main():
    import glob

    parser = argparse.ArgumentParser(description="运行 BaziQA 基准测试")
    parser.add_argument('dataset_files', nargs='*', help='要运行的数据集文件，默认运行 data/ 下全部 JSON')
    parser.add_argument('--mode', type=int, default=1, choices=[0, 1], help='解盘接口 mode，默认 1')
    parser.add_argument('--theory', type=int, default=1, help='解盘接口 theory，默认 1')
    parser.add_argument('--agent-id', type=int, default=4, help='解盘接口 agentId，默认 4')
    args = parser.parse_args()

    dataset_dir = os.path.join(SCRIPT_DIR, 'data')

    if args.dataset_files:
        # 指定文件则只跑指定的
        dataset_files = args.dataset_files
    else:
        # 默认跑 data/ 下所有 JSON
        dataset_files = sorted(glob.glob(os.path.join(dataset_dir, '*.json')))

    print(f"共 {len(dataset_files)} 个数据集")

    for dataset_file in dataset_files:
        run_dataset(
            dataset_file,
            mode=args.mode,
            theory=args.theory,
            agent_id=args.agent_id,
        )


if __name__ == '__main__':
    main()
