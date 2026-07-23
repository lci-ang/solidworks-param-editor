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
你: "长度改成 60mm"
  → 读 params_labeled.json → 匹配参数名
  → 读 standards.md → 检查 "长度标准范围 50-65mm" → ✅ 合规
  → terminal 执行 sw_modify.py → 完成
```

## Directory Structure

```
parts/
  mypart/
    params_labeled.json    ← 参数名 → 值 → 中文标签
    standards.md           ← 这个零件的设计标准/规则
  bracket/
    params_labeled.json
    standards.md
```

## params_labeled.json

```json
{
  "part_name": "MyPart",
  "sldprt_path": "C:\\parts\\part.SLDPRT",
  "output_dir": "C:\\parts\\output",
  "parameters": {
    "D1@Sketch1":       { "value": 55.5, "label": "长度",     "min": 50, "max": 65, "step": 0.5 },
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
# MyPart 设计标准

## 基本信息
- 材料: 天然橡胶 NR
- 用途: 吸盘密封件
- 客户: xxx

## 关键参数标准
- 长度: 标准值 55.5mm，常用范围 50-65mm，步长 0.5mm
- 胶直径: 标准值 5.0mm，范围 3-8mm
- 壁厚: 最小 2mm（防止撕裂）
- 壳体高度: 与装配空间匹配，通常 15mm

## 设计规则
- 长度与胶直径的比例应在 8:1 到 12:1 之间
- 壁厚不能小于胶直径的 40%
- 修改孔径时需要同步检查孔间距

## 常见变体
- MyPart-55 → 长度 55.5mm（标准款）
- MyPart-60 → 长度 60mm（加长款）
- MyPart-50 → 长度 50mm（短款）
```

## Workflow

### Adding a new part

1. Windows: `python extract_sw_params.py "C:\path\to\part.SLDPRT"` → `part_params.json`
2. Rename to `params_labeled.json`, add `label` for each parameter
3. Create `standards.md` with design rules
4. Done — AI now knows this part

### Daily use

```
"长度改 60"
  → 读 params_labeled.json → "长度" = "D1@Sketch1"
  → 读 standards.md → 60 在 50-65 范围内 → ✅
  → terminal: sw_modify.py ... "D1@Sketch1=60"
  → "已修改，导出到 C:\parts\output\"
```

If a value violates standards:
```
"长度改 80"
  → standards.md → 范围 50-65 → 80 超出！
  → "⚠️ 长度标准范围 50-65mm，80mm 超出。常用变体最大 65mm。确定？"
```

## Execution Commands

Extract all (equations + custom properties + dimensions):
```
python scripts/extract_full.py "C:\parts\part.SLDPRT"
```
Outputs `<partname>_full.json` with equations, custom properties, and dimensions.

List params (quick):
```
python scripts/extract_sw_params.py "C:\parts\part.SLDPRT"
```

Modify params (dimensions or equation variables):
```
python scripts/sw_modify.py "C:\parts\part.SLDPRT" "D1@Sketch1=60" --step "C:\parts\output\modified.STEP"
```

Modify equation global variable (e.g. change total length L=120):
```
python scripts/sw_modify.py "C:\parts\part.SLDPRT" "L=120" --step "C:\parts\output\modified.STEP"
```

Rollback to baseline (undo all modifications since last --new-snapshot):
```
python scripts/sw_modify.py "C:\parts\part.SLDPRT" --rollback
```

Accept current state as new baseline (clears rollback history):
```
python scripts/sw_modify.py "C:\parts\part.SLDPRT" --new-snapshot
```

## Rollback System

Every modification is guarded by a snapshot system:

1. **First modification**: Automatically saves a snapshot of all equation values + dimension values to `.sw_snapshots/<partname>_last.json`
2. **Subsequent modifications**: Snapshot is preserved - you can modify multiple times and still rollback to the original state
3. **`--rollback`**: Restores all equations and dimensions from the snapshot, rebuilds the model, saves SLDPRT
4. **`--new-snapshot`**: Saves current state as the new baseline (use when you're happy with the changes and want to start fresh)

```
用户: "A 改成 30"        → 修改 A=30, 快照保存原始值(A=25)
用户: "C 也改成 20"       → 修改 C=20, 快照不变
用户: "不对，回退"        → --rollback, 恢复 A=25 C=原始值
用户: "这次对了，继续"     → --new-snapshot, 当前状态成为新基线
```

## Save-As Mode (Non-Destructive)

Use `--save-as` to save the modified part as a **new SLDPRT file**, leaving the original unchanged:

```
python scripts/sw_modify.py "part.SLDPRT" "L=120" --save-as "output/part-L120.SLDPRT" --step "output/part-L120.STEP"
```

This is ideal for generating variants without corrupting the master part file.

## Batch Mode

Use `--batch` to generate multiple variants from a single JSON config file:

```json
[
  {"name": "标准款-L100-N5", "changes": {"L": 100, "N1": 5}, "step": true},
  {"name": "加长款-L120-N5", "changes": {"L": 120, "N1": 5}, "step": true},
  {"name": "短款-L80-N3",   "changes": {"L": 80,  "N1": 3}, "step": true}
]
```

```
python scripts/sw_modify.py "part.SLDPRT" --batch "batch_config.json"
```

Each variant is saved as `<output>/<name>.SLDPRT` + `<output>/<name>.STEP`. The original file is never modified.

## Equation-Aware Workflow

Some parts use SolidWorks **equations** (global variables) to drive dimensions. When `params_labeled.json` has an `equations` section:

1. User says "总长改 120" → match "总长" to equation variable `L`
2. Modify the **global variable**, not the driven dimension
3. SolidWorks auto-rebuilds: F (阵列间距) = (L-A-C-2*Q)/(N1-1) recalculates automatically
4. Do NOT directly modify equation-driven dimensions (they'll revert on rebuild)

Equation variables are modified the same way as dimensions:
```
python scripts/sw_modify.py "part.SLDPRT" "L=120"  # changes global variable L
```

## Pitfalls

- `standards.md` is the most important file - without it, AI has no domain knowledge
- Start with simple standards, add rules gradually as you discover them
- `min`/`max` in params_labeled.json are soft guards - AI warns but doesn't block
- Standards are per-part; shared company standards can be a separate file

### pywin32 COM API Quirks (Windows)

SolidWorks COM via pywin32 `Dispatch` has several gotchas:

1. **Properties vs Methods**: Many SW API members that look like methods are actually properties in pywin32 dynamic dispatch. Do NOT add `()`:
   - `model.GetTitle` (not `GetTitle()`)
   - `model.EditRebuild3` (not `EditRebuild3()`)
   - `model.Save` (not `Save()`)
2. **OpenDoc6 ByRef params fail**: `OpenDoc6` returns `(model, errors, warnings)` but pywin32 dynamic dispatch can't handle ByRef params. Use `sw.OpenDoc(path, swDocPART)` instead.
3. **Extension.GetDimensions() doesn't exist**: Must traverse the feature tree manually: `model.FirstFeature` -> `feat.GetFirstDisplayDimension` -> `feat.GetNextDisplayDimension(disp_dim)`.
4. **SaveAs params**: `model.SaveAs(step_output)` with just the filename works. Don't pass extra ByRef params.
5. **Save3 params**: `model.Save3(0, None, None)` or fallback to `model.Save`.
6. **Equation variables**: Use `model.GetEquationMgr` to access equations. `eq_mgr.Equation(i)` gets/sets equation string, `eq_mgr.Value(i)` gets computed value, `eq_mgr.GlobalVariable(i)` checks if it's a global variable.
7. **Dimension full names**: SW returns full names like `D1@草图1@PartName.Part`. Build a short-name map (split by `@`) for fuzzy matching when user says "L" instead of "L@凸台-拉伸1@PartName.Part".
