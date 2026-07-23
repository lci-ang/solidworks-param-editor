---
name: solidworks-param-editor
description: Hermes-native SolidWorks parameter editor with part knowledge base — modify CAD dimensions via natural language, with built-in design standards and constraints.
version: 2.1.0
author: lc
tags: [cad, solidworks, parametric, automation, windows]
---

# SolidWorks Parametric Editor Skill

## Core Philosophy

**AI is best at modifying existing parts, not creating from scratch.**

The workflow:
1. Engineer designs the part in SolidWorks (done once)
2. Extract parameters → label them → add standards
3. AI modifies parameters on demand, respecting standards

## Architecture

```
你: "胶长改成 60mm"
  → 读 params_labeled.json → 匹配参数名
  → 读 standards.md → 检查 "胶长标准范围 50-65mm" → ✅ 合规
  → terminal 执行 sw_modify.py → 完成
```

## Directory Structure

```
parts/
  FD7111503/
    params_labeled.json    ← 参数名 → 值 → 中文标签
    standards.md           ← 这个零件的设计标准/规则
  bracket/
    params_labeled.json
    standards.md
```

## params_labeled.json

```json
{
  "part_name": "FD7111503 后吸（胶长55.5）",
  "sldprt_path": "C:\\parts\\FD7111503.SLDPRT",
  "output_dir": "C:\\parts\\output",
  "parameters": {
    "D1@Sketch1":       { "value": 55.5, "label": "胶长",     "min": 50, "max": 65, "step": 0.5 },
    "D2@Sketch1":       { "value": 5.0,  "label": "胶直径",   "min": 3,  "max": 8,  "step": 0.5 },
    "D1@Boss-Extrude1": { "value": 15,   "label": "壳体高度", "min": 10, "max": 20, "step": 1 },
    "D3@Sketch2":       { "value": 4.0,  "label": "壁厚",     "min": 2,  "max": 6,  "step": 0.5 }
  }
}
```

`min`/`max`/`step` are optional — add them when you know the valid range.

## standards.md

Each part gets a knowledge base. Hermes reads it as context before modifying.

```markdown
# FD7111503 后吸 设计标准

## 基本信息
- 材料: 天然橡胶 NR
- 用途: 吸盘密封件
- 客户: xxx

## 关键参数标准
- 胶长: 标准值 55.5mm，常用范围 50-65mm，步长 0.5mm
- 胶直径: 标准值 5.0mm，范围 3-8mm
- 壁厚: 最小 2mm（防止撕裂）
- 壳体高度: 与装配空间匹配，通常 15mm

## 设计规则
- 胶长与胶直径的比例应在 8:1 到 12:1 之间
- 壁厚不能小于胶直径的 40%
- 修改孔径时需要同步检查孔间距

## 常见变体
- FD7111503-55 → 胶长 55.5mm（标准款）
- FD7111503-60 → 胶长 60mm（加长款）
- FD7111503-50 → 胶长 50mm（短款）
```

## Workflow

### Adding a new part

1. Windows: `python extract_sw_params.py "C:\path\to\part.SLDPRT"` → `part_params.json`
2. Rename to `params_labeled.json`, add `label` for each parameter
3. Create `standards.md` with design rules
4. Done — AI now knows this part

### Daily use

```
"FD7111503 胶长改 60"
  → 读 params_labeled.json → "胶长" = "D1@Sketch1"
  → 读 standards.md → 60 在 50-65 范围内 → ✅
  → terminal: sw_modify.py ... "D1@Sketch1=60"
  → "已修改，导出到 C:\parts\output\"
```

If a value violates standards:
```
"胶长改 80"
  → standards.md → 范围 50-65 → 80 超出！
  → "⚠️ 胶长标准范围 50-65mm，80mm 超出。常用变体最大 65mm。确定？"
```

## Execution Commands

List params:
```
python references/extract_sw_params.py "C:\parts\FD7111503.SLDPRT"
```

Modify params:
```
python references/sw_modify.py "C:\parts\FD7111503.SLDPRT" "D1@Sketch1=60" "D1@Hole1=1.5" --step "C:\parts\output\modified.STEP"
```

## Pitfalls

- `standards.md` is the most important file — without it, AI has no domain knowledge
- Start with simple standards, add rules gradually as you discover them
- `min`/`max` in params_labeled.json are soft guards — AI warns but doesn't block
- Standards are per-part; shared company standards can be a separate file
