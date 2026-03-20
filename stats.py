#!/usr/bin/env python3
"""汇总 scores 目录下所有数据集的评分结果"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DIMENSIONS = ["流年运势", "感情", "六亲", "事业", "性格", "学业", "财富", "健康", "其他"]


def load_scores(score_dir):
    """加载所有评分 JSON 文件"""
    results = {}
    for f in sorted(os.listdir(score_dir)):
        if f.endswith('.json') and not f.startswith('_'):
            path = os.path.join(score_dir, f)
            with open(path, 'r', encoding='utf-8') as fp:
                results[f.replace('.json', '')] = json.load(fp)
    return results


def aggregate(results):
    """汇总所有数据集的维度统计"""
    totals = {}  # dim -> {total, correct}
    for data in results.values():
        stats = data.get("stats", {})
        for dim, s in stats.items():
            if dim == "总体":
                key = "总体"
            else:
                key = dim
            if key not in totals:
                totals[key] = {"total": 0, "correct": 0}
            totals[key]["total"] += s.get("total", 0)
            totals[key]["correct"] += s.get("correct", 0)
    return totals


def print_table(results, totals):
    """打印统计表格"""
    # 各数据集概览
    print(f"\n{'=' * 60}")
    print(f"  各数据集准确率")
    print(f"{'=' * 60}")
    print(f"  {'数据集':<25} {'正确/总数':<12} {'准确率':<10}")
    print(f"  {'-' * 50}")
    for name, data in results.items():
        s = data["stats"]["总体"]
        print(f"  {name:<25} {s['correct']}/{s['total']:<10} {s['accuracy']}%")

    # 汇总
    overall = totals.get("总体", {})
    total = overall.get("total", 0)
    correct = overall.get("correct", 0)
    acc = round(correct / total * 100, 1) if total > 0 else 0
    print(f"\n  {'汇总':<25} {correct}/{total:<10} {acc}%")

    # 维度统计
    print(f"\n{'=' * 60}")
    print(f"  各维度准确率（汇总）")
    print(f"{'=' * 60}")
    print(f"  {'维度':<12} {'正确/总数':<12} {'准确率':<10}")
    print(f"  {'-' * 40}")
    for dim in DIMENSIONS:
        if dim in totals:
            t = totals[dim]
            acc = round(t["correct"] / t["total"] * 100, 1) if t["total"] > 0 else 0
            print(f"  {dim:<12} {t['correct']}/{t['total']:<10} {acc}%")

    # 各数据集 x 维度明细
    print(f"\n{'=' * 60}")
    print(f"  各数据集 × 维度明细")
    print(f"{'=' * 60}")
    header = f"  {'数据集':<20}"
    for dim in DIMENSIONS:
        header += f" {dim:<8}"
    print(header)
    print(f"  {'-' * (20 + 9 * len(DIMENSIONS))}")
    for name, data in results.items():
        row = f"  {name:<20}"
        stats = data["stats"]
        for dim in DIMENSIONS:
            if dim in stats:
                s = stats[dim]
                row += f" {s['accuracy']:>5.1f}%  "
            else:
                row += f"    -    "
        print(row)

    print(f"{'=' * 60}\n")


def main():
    score_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCRIPT_DIR, 'scores')
    if not os.path.isdir(score_dir):
        print(f"目录不存在: {score_dir}")
        return

    results = load_scores(score_dir)
    if not results:
        print(f"在 {score_dir} 中未找到评分文件")
        return

    print(f"加载了 {len(results)} 个数据集的评分结果")
    totals = aggregate(results)
    print_table(results, totals)

    # 输出汇总 JSON
    summary = {"datasets": {}, "totals": {}}
    for name, data in results.items():
        summary["datasets"][name] = data["stats"]
    for key, t in totals.items():
        acc = round(t["correct"] / t["total"] * 100, 1) if t["total"] > 0 else 0
        summary["totals"][key] = {"total": t["total"], "correct": t["correct"], "accuracy": acc}

    out_file = os.path.join(score_dir, "_summary.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"汇总已保存: {out_file}")


if __name__ == '__main__':
    main()
