# SolidWorks 参数编辑器 Skill

> 🛠️ Hermes 原生 Skill —— 用自然语言对话修改 SolidWorks CAD 尺寸，自带设计标准检查。

## 这是什么

把「手动打开 SolidWorks → 找尺寸 → 改参数 → 重建 → 导出」这个流程，变成一句人话：

```
"FD7111503 胶长改成 60mm"
```

AI 自动：查参数映射 → 检查设计标准 → 修改 CAD → 导出 STEP。

## 为什么做这个

工厂里改 CAD 图纸是日常操作。现有流程是人对着图纸一个个找尺寸名称，输入新值。这个 Skill 做的事情：

1. **参数提取一次**（`extract_sw_params.py`）：把 SolidWorks 里的机器名（`D1@Sketch1`）导出
2. **标注中文标签**：告诉 AI「`D1@Sketch1` = 胶长」
3. **写入设计标准**：告诉 AI「胶长范围 50-65mm，超出要报警」
4. **日常使用**：一句话修改，AI 自动检查标准

## 文件结构

```
solidworks-param-editor/
  SKILL.md                         ← Skill 主文件（工作流程）
  scripts/
    sw_modify.py                   ← CLI 参数修改器
    extract_sw_params.py           ← 参数提取器（每个零件跑一次）
  templates/
    params_labeled.json            ← 参数标注模板
    standards.md                   ← 零件设计标准模板
    mechanical-standards.md        ← 通用机械设计规范
```

## 快速开始

### 前提

- Windows + SolidWorks（已安装）
- Hermes Agent（Windows 版）
- Python + `pip install pywin32`

### 第 1 步：提取参数

```
python scripts/extract_sw_params.py "C:\parts\FD7111503.SLDPRT"
```

生成 `FD7111503_params.json`，里面是所有参数的机器名和当前值。

### 第 2 步：标注

把 `params.json` 改名为 `params_labeled.json`，给每个参数加中文标签：

```json
{
  "part_name": "FD7111503 后吸",
  "sldprt_path": "C:\\parts\\FD7111503.SLDPRT",
  "parameters": {
    "D1@Sketch1": { "value": 55.5, "label": "胶长", "min": 50, "max": 65 }
  }
}
```

### 第 3 步：写标准（可选但推荐）

在零件目录下创建 `standards.md`，写入设计规则。

### 第 4 步：日常使用

在 Hermes 中对话：

```
"FD7111503 胶长改 60，导出 STEP"
```

## 依赖

- [Hermes Agent](https://github.com/nousresearch/hermes-agent)
- SolidWorks 2018+
- Python 3.8+ with pywin32

## 作者

飞达橡塑 · 梁辰

## 许可证

MIT
