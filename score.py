#!/usr/bin/env python3
"""
BaziQA 评分系统 - 多维度评估 AI 八字分析准确率
流程: 读取缓存结果 -> 获取AI回答 -> Gemini评分 -> 多维度统计 -> 存储结果
"""
import argparse
import json
import os
import re
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── lookfate API 配置 ──
LOOKFATE_BASE = "https://api.lookfate.com"

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

LOOKFATE_TOKEN = os.environ.get("AUTH_TOKEN", "")
LOOKFATE_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9',
    'authorization': LOOKFATE_TOKEN,
    'origin': 'https://www.lookfate.com',
    'referer': 'https://www.lookfate.com/',
    'site-id': '1',
    'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15'
}

# ── Gemini API 配置 (OpenAI 协议) ──
GEMINI_BASE = os.environ.get("GEMINI_BASE", "https://api.apiplus.org/v1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")

# ── 评分维度 ──
DIMENSIONS = ["流年运势", "感情", "六亲", "事业", "性格", "学业", "财富", "健康", "其他"]


MAX_RETRIES = 5
RETRY_DELAY = 10  # 秒


def get_result_dir(mode):
    return os.path.join(SCRIPT_DIR, f'result-{mode}')


def get_score_dir(mode):
    return os.path.join(SCRIPT_DIR, 'scores' if mode == 1 else f'scores-{mode}')


def _retry(func, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    """通用重试包装器"""
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == retries:
                raise
            print(f"  [重试 {attempt}/{retries}] {e}，{delay}秒后重试...")
            time.sleep(delay)


def fetch_ai_answer(uuid):
    """通过 UUID 获取 AI 的完整回答"""
    url = f"{LOOKFATE_BASE}/agent/get-record-detail?uuid={uuid}"
    resp = requests.get(url, headers=LOOKFATE_HEADERS, timeout=30)
    data = resp.json()
    if data.get("code") != 200:
        print(f"  [获取回答失败] uuid={uuid}, resp={data}")
        return None
    messages = data.get("data", {}).get("messages", [])
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            # 去除 <think>...</think> 标签内容
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            return content.strip()
    return None


def call_gemini(system_prompt, user_prompt, temperature=0.1):
    """调用 Gemini API (OpenAI 协议)"""
    headers = {
        "Authorization": f"Bearer {GEMINI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GEMINI_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    resp = requests.post(f"{GEMINI_BASE}/chat/completions", headers=headers, json=payload, timeout=60)
    result = resp.json()
    return result["choices"][0]["message"]["content"]


def classify_and_extract(questions, ai_answer):
    """
    使用 Gemini 一次性完成:
    1. 对每道题分类到维度
    2. 从 AI 回答中提取 AI 选择的答案
    返回: list[dict] 每题 {"question_index", "dimension", "ai_choice"}
    """
    system_prompt = """你是一个八字命理评测专家。你需要完成两个任务：

任务1: 将每道选择题归类到以下维度之一：
- 流年运势: 特定年份发生的事件、运势起伏
- 感情: 恋爱、婚姻、离婚、感情状况
- 六亲: 父母、兄弟姐妹、子女相关
- 事业: 职业、工作、创业
- 性格: 性格特征、外表描述
- 学业: 读书、学历、学习
- 财富: 财运、投资、财务状况
- 健康: 疾病、身体状况、手术
- 其他: 无法归入以上类别的

注意：如果一道题同时涉及多个维度，选择最核心的那个维度。比如"哪年结婚"主要是感情，"哪年父亲去世"主要是六亲，"哪年创业开店"主要是事业。

任务2: 从 AI 的回答文本中提取它对每道题选择的答案(A/B/C/D)。
- AI 可能用"倾向于X"、"答案是X"、"选X"等方式表达
- 如果 AI 没有明确选择，标记为"N"

请严格按以下JSON格式返回，不要有其他文字：
[
  {"question_index": 1, "dimension": "维度名", "ai_choice": "A"},
  ...
]"""

    questions_text = ""
    for i, q in enumerate(questions, 1):
        options_str = " / ".join(q["options"])
        questions_text += f"第{i}题: {q['question']}\n选项: {options_str}\n\n"

    user_prompt = f"""以下是需要分析的选择题：

{questions_text}

以下是 AI 的回答文本：
---
{ai_answer}
---

请对每道题进行维度分类，并提取AI选择的答案。严格返回JSON数组。"""

    raw = call_gemini(system_prompt, user_prompt)
    # 提取 JSON
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return []


def score_person(person_id, person_data, ai_answer):
    """对单个命主进行评分"""
    questions = person_data["questions"]
    results = classify_and_extract(questions, ai_answer)

    scored = []
    for i, q in enumerate(questions):
        correct = q["answer"].upper()
        # 找到对应的分类结果
        matched = None
        for r in results:
            if r.get("question_index") == i + 1:
                matched = r
                break
        if not matched:
            matched = {"question_index": i + 1, "dimension": "其他", "ai_choice": "N"}

        ai_choice = matched.get("ai_choice", "N").upper()
        dimension = matched.get("dimension", "其他")
        if dimension not in DIMENSIONS:
            dimension = "其他"

        is_correct = ai_choice == correct
        scored.append({
            "question_index": i + 1,
            "question": q["question"],
            "correct_answer": correct,
            "ai_answer": ai_choice,
            "is_correct": is_correct,
            "dimension": dimension,
        })
    return scored


def compute_stats(all_scored):
    """计算多维度统计"""
    # 总体统计
    total = len(all_scored)
    correct = sum(1 for s in all_scored if s["is_correct"])
    no_answer = sum(1 for s in all_scored if s["ai_answer"] == "N")

    stats = {
        "总体": {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
            "no_answer": no_answer,
        }
    }

    # 按维度统计
    for dim in DIMENSIONS:
        dim_items = [s for s in all_scored if s["dimension"] == dim]
        if not dim_items:
            continue
        dim_total = len(dim_items)
        dim_correct = sum(1 for s in dim_items if s["is_correct"])
        stats[dim] = {
            "total": dim_total,
            "correct": dim_correct,
            "accuracy": round(dim_correct / dim_total * 100, 1) if dim_total > 0 else 0,
        }

    return stats


def print_report(stats, dataset_name):
    """打印报告"""
    print(f"\n{'=' * 60}")
    print(f"  评分报告: {dataset_name}")
    print(f"{'=' * 60}")

    overall = stats["总体"]
    print(f"\n  总体准确率: {overall['correct']}/{overall['total']} = {overall['accuracy']}%")
    if overall["no_answer"] > 0:
        print(f"  未作答题数: {overall['no_answer']}")

    print(f"\n  {'维度':<10} {'正确/总数':<12} {'准确率':<10}")
    print(f"  {'-' * 35}")
    for dim in DIMENSIONS:
        if dim in stats:
            s = stats[dim]
            print(f"  {dim:<10} {s['correct']}/{s['total']:<10} {s['accuracy']}%")

    print(f"{'=' * 60}\n")


def _save_dataset_result(dataset_name, data, output_dir):
    """保存单个数据集的评分结果，文件名与数据集同名"""
    output_file = os.path.join(output_dir, f"{dataset_name}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"评分结果已保存: {output_file}")


def run_scoring(result_dir, output_dir):
    """对指定结果目录进行评分"""
    cache_files = sorted([
        f for f in os.listdir(result_dir)
        if f.endswith('_cache.json')
    ])

    if not cache_files:
        print(f"在 {result_dir} 中未找到缓存文件")
        return

    print(f"找到 {len(cache_files)} 个缓存文件")
    os.makedirs(output_dir, exist_ok=True)

    grand_scored = []

    for cache_file in cache_files:
        dataset_name = cache_file.replace('_cache.json', '')
        score_file = os.path.join(output_dir, f"{dataset_name}.json")
        if os.path.exists(score_file):
            print(f"\n[跳过] {dataset_name} 已有评分结果: {score_file}")
            continue
        print(f"\n{'#' * 60}")
        print(f"评分数据集: {dataset_name}")

        cache_path = os.path.join(result_dir, cache_file)
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)

        dataset_scored = []

        for person_id, person_data in cache.items():
            solve_resp = person_data.get("solve_response", {})
            uuid = solve_resp.get("data")
            if not uuid or solve_resp.get("code") != 200:
                print(f"  [{person_id}] 无有效UUID，跳过")
                continue

            print(f"  [{person_id}] 获取AI回答... uuid={uuid}")
            try:
                ai_answer = _retry(fetch_ai_answer, uuid)
            except Exception as e:
                print(f"  [{person_id}] 获取回答最终失败: {e}，跳过")
                continue
            if not ai_answer:
                print(f"  [{person_id}] 获取回答为空，跳过")
                continue

            print(f"  [{person_id}] AI回答长度: {len(ai_answer)} 字符")
            print(f"  [{person_id}] 调用Gemini分类和提取答案...")

            try:
                scored = _retry(score_person, person_id, person_data, ai_answer)
            except Exception as e:
                print(f"  [{person_id}] 评分最终失败: {e}，跳过")
                continue

            for s in scored:
                s["person_id"] = person_id
                s["dataset"] = dataset_name
                mark = "✓" if s["is_correct"] else "✗"
                print(f"    Q{s['question_index']}: {mark} AI={s['ai_answer']} 正确={s['correct_answer']} [{s['dimension']}]")

            dataset_scored.extend(scored)
            time.sleep(15)  # 避免 API 限流

        # 数据集统计 & 立即保存
        if dataset_scored:
            stats = compute_stats(dataset_scored)
            print_report(stats, dataset_name)
            dataset_result = {
                "stats": stats,
                "details": dataset_scored,
            }
            _save_dataset_result(dataset_name, dataset_result, output_dir)
            grand_scored.extend(dataset_scored)

    # 最终汇总报告
    if grand_scored:
        grand_stats = compute_stats(grand_scored)
        print_report(grand_stats, "所有数据集汇总")


def main():
    parser = argparse.ArgumentParser(description="对结果缓存进行评分")
    parser.add_argument('result_dir', nargs='?', help='结果目录，默认使用当前 mode 对应目录')
    parser.add_argument('output_dir', nargs='?', help='评分输出目录，默认使用当前 mode 对应目录')
    parser.add_argument('--mode', type=int, default=1, choices=[0, 1], help='默认目录使用的 mode，默认 1')
    args = parser.parse_args()

    result_dir = args.result_dir or get_result_dir(args.mode)
    output_dir = args.output_dir or get_score_dir(args.mode)

    run_scoring(result_dir, output_dir)


if __name__ == '__main__':
    main()
