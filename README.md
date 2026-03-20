# BaziQA

八字命理 AI 能力基准测试框架。通过标准化的选择题数据集，评估 AI 八字分析的准确率，并按多个维度（流年运势、感情、六亲、事业等）进行统计。

数据集来源于论文 **[BaziQA-Benchmark: Evaluating Symbolic and Temporally Compositional Reasoning in Large Language Models](https://arxiv.org/abs/2602.12889)**。

## 工作流程

```
数据集 (data/*.json)
    ↓
benchmark.py  →  排盘API + 解盘AI  →  缓存结果 (result-1/*_cache.json)
    ↓
score.py  →  Gemini 分类 & 提取答案  →  评分结果 (scores/*.json)
    ↓
stats.py  →  多维度汇总报告
```

## 项目结构

```
├── benchmark.py   # 基准测试：调用排盘/解盘 API，缓存结果
├── score.py       # 评分系统：用 Gemini 提取 AI 答案并评分
├── stats.py       # 统计汇总：多维度准确率报告
├── data/          # 数据集（按竞赛年份组织）
├── result-1/      # 排盘/解盘缓存结果
└── scores/        # 评分结果及汇总
```

## 环境配置

在项目根目录创建 `.env` 文件：

```env
AUTH_TOKEN=你的lookfate授权token
GEMINI_KEY=你的Gemini API密钥
GEMINI_BASE=https://api.apiplus.org/v1       # 可选，默认值如左
GEMINI_MODEL=gemini-3-flash-preview          # 可选，默认值如左
```

## 使用方法

### 1. 运行基准测试

```bash
# 运行 data/ 下所有数据集
python benchmark.py

# 运行指定数据集
python benchmark.py data/contest8_2025.json
```

已测试过的命例会缓存，不会重复请求。

### 2. 评分

```bash
# 默认读取 result-1/ 并输出到 scores/
python score.py

# 自定义目录
python score.py <结果目录> <输出目录>
```

### 3. 统计汇总

```bash
# 默认读取 scores/ 目录
python stats.py

# 指定目录
python stats.py <评分目录>
```

## 评分维度

| 维度 | 说明 |
|------|------|
| 流年运势 | 特定年份发生的事件、运势起伏 |
| 感情 | 恋爱、婚姻、离婚 |
| 六亲 | 父母、兄弟姐妹、子女 |
| 事业 | 职业、工作、创业 |
| 性格 | 性格特征、外表描述 |
| 学业 | 读书、学历 |
| 财富 | 财运、投资 |
| 健康 | 疾病、身体状况 |
| 其他 | 无法归入以上类别 |

## 数据集格式

每个数据集为 JSON 文件，第一项为元数据，后续为命主信息：

```json
[
  {"contest_id": "...", "total_questions": 50},
  {
    "person_id": "person_001",
    "name": "某某",
    "profile": {
      "birth": {"year": 1990, "month": 1, "day": 15, "hour": 8, "minute": 0},
      "gender": "male"
    },
    "questions": [
      {
        "question": "命主的职业是？",
        "options": ["A. 教师", "B. 医生", "C. 工程师", "D. 律师"],
        "answer": "C"
      }
    ]
  }
]
```
