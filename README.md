# SolidWorks 参数编辑器 Skill

> 🛠️ Hermes 原生 Skill -- 用自然语言对话修改 SolidWorks CAD 尺寸，支持方程式联动，自带设计标准检查。

## 这是什么

把「手动打开 SolidWorks -> 找尺寸 -> 改参数 -> 重建 -> 导出」这个流程，变成一句人话：

```
"边沿孔数量改成 3"
```

AI 自动：查参数映射 -> 检查设计标准 -> 修改方程式变量 -> 重建模型 -> 导出 STEP。

## 工作原理

```
你: "边沿孔数量改成 3"
  -> 读 params_labeled.json -> 匹配 "边沿孔数量" = 全局变量 N1
  -> 读 standards.md -> N1=3 在合理范围内 -> ✅
  -> terminal 执行 sw_modify.py "N1=3"
  -> SolidWorks 重建 -> F(阵列间距) 自动从 13.75 变为 27.5
  -> 导出 STEP
```

## 文件结构

```
solidworks-param-editor/
  SKILL.md                         ← Skill 主文件（工作流程 + API 坑指南）
  scripts/
    extract_full.py                ← 完整提取器（方程式 + 自定义属性 + 尺寸）
    extract_sw_params.py           ← 尺寸提取器（每个零件跑一次）
    sw_modify.py                   ← 参数修改器（支持尺寸 + 方程式全局变量）
  templates/
    params_labeled.json            ← 参数标注模板
    standards.md                   ← 零件设计标准模板
    mechanical-standards.md        ← 通用机械设计规范
```

## 快速开始

### 前提

- Windows + SolidWorks 2018+（已安装）
- Hermes Agent（Windows 版）
- Python 3.8+ + `pip install pywin32`

### 第 1 步：提取参数

```bash
# 完整提取（推荐）：方程式 + 自定义属性 + 尺寸
python scripts/extract_full.py "C:\parts\part.SLDPRT"

# 仅尺寸
python scripts/extract_sw_params.py "C:\parts\part.SLDPRT"
```

生成 `_full.json` / `_params.json`，包含所有参数的机器名和当前值。

### 第 2 步：标注

把生成的 JSON 改名为 `params_labeled.json`，给每个参数加中文标签：

```json
{
  "equations": {
    "L":  { "value": 100.0, "label": "总长", "drives": ["D1@凸台-拉伸2"] },
    "N1": { "value": 5,     "label": "边沿孔数量", "drives": ["D1@阵列(线性)1"] }
  },
  "dimensions": {
    "D1@草图1": { "value": 30.0, "label": "胶条宽度" }
  }
}
```

### 第 3 步：写设计标准（可选但推荐）

在零件目录下创建 `standards.md`，写入设计规则和变量依赖关系。

### 第 4 步：日常使用

在 Hermes 中对话：

```
"边沿孔数量改成 3"     → AI 改全局变量 N1=3，F/N2 自动联动
"总长改成 120"         → AI 改全局变量 L=120，F 自动重算
"胶条宽度改成 35"       → AI 改尺寸 D1@草图1=35
```

## 方程式联动

此 Skill 支持SolidWorks **方程式（全局变量）**驱动的零件。修改全局变量时，所有关联尺寸自动更新：

```
L (总长) ──┐
A (边距A) ─┤
C (边距C) ─┤──> F (阵列间距) = (L-A-C-2*Q)/(N1-1)  ← 自动计算
Q (距离) ──┤
N1 (数量) ─┘──> N2 (错孔数量) = N1-1                ← 自动计算
```

| 修改 | 联动效果 |
|------|---------|
| L=120 | F: 13.75→18.75, D1@草图22: 11.875→14.375 |
| N1=3 | F: 13.75→27.5, N2: 4→2, 3个阵列特征全部更新 |

## 三个脚本

### extract_full.py（完整提取）

```bash
python scripts/extract_full.py "C:\parts\part.SLDPRT"
```

输出 `partname_full.json`，包含：
- **方程式**：全局变量名、值、是否为全局变量、计算值
- **自定义属性**：代号、名称、材料、日期等 29 个属性
- **尺寸**：所有特征的尺寸名 + 值 + 类型

### extract_sw_params.py（尺寸提取）

```bash
python scripts/extract_sw_params.py "C:\parts\part.SLDPRT"
```

仅遍历特征树提取尺寸，输出 `partname_params.json`。

### sw_modify.py（参数修改）

```bash
# 修改方程式全局变量
python scripts/sw_modify.py "C:\part.SLDPRT" "L=120" --step "C:\output\modified.STEP"

# 修改尺寸（支持短名模糊匹配）
python scripts/sw_modify.py "C:\part.SLDPRT" "D1@草图1=35" --step "C:\output\modified.STEP"

# 列出所有方程式和尺寸
python scripts/sw_modify.py "C:\part.SLDPRT" --list
```

智能匹配优先级：
1. 方程式全局变量名（如 `L`、`N1`、`A`）
2. 精确尺寸名（如 `D1@草图1`）
3. 短名模糊匹配（`L` → `L@凸台-拉伸1@PartName.Part`）

修改后自动：重建模型 → 显示方程式更新结果 → 保存 SLDPRT → 导出 STEP。

## pywin32 COM API 坑指南

SolidWorks COM via pywin32 有几个大坑，本 Skill 已全部踩过并修复：

| 坑 | 症状 | 解决方案 |
|----|------|---------|
| 属性 vs 方法 | `GetTitle()` 报 `'str' object is not callable` | pywin32 动态模式下 `GetTitle`/`EditRebuild3`/`Save` 是属性，不加 `()` |
| OpenDoc6 ByRef | `类型不匹配` 错误 | 用 `OpenDoc(path, type)` 替代 `OpenDoc6` |
| GetDimensions 不存在 | `AttributeError` | 手动遍历特征树 `FirstFeature` → `GetFirstDisplayDimension` |
| SaveAs 参数过多 | `无效的参数数目` | 只传文件名 `model.SaveAs(path)` |
| 方程式变量匹配 | `L` 找不到 | 用 `EquationMgr` 提取全局变量名 + 构建短名映射 |

## 安装到 Hermes

```bash
# 方法 1: 直接克隆到 skills 目录
git clone https://github.com/lci-ang/solidworks-param-editor.git \
  ~/AppData/Local/hermes/skills/solidworks-param-editor

# 方法 2: Hermes CLI（如果已发布到 hub）
hermes skills install https://github.com/lci-ang/solidworks-param-editor
```

安装后 `/reset` 开新会话即可使用。

## 依赖

- [Hermes Agent](https://github.com/nousresearch/hermes-agent)
- SolidWorks 2018+（需在运行时保持打开状态）
- Python 3.8+ with pywin32

## 已验证环境

- Windows 10 + SolidWorks 2022 + Python 3.11 + pywin32
- 实测零件：实测：54 尺寸 + 17 方程式 + 29 自定义属性
- 方程式联动验证：L/N1 修改后 F/N2/D1@草图22 全部正确更新

## 作者

lci-ang

## 许可证

MIT
