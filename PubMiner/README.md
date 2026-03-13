# PubMiner

**智能医学文献批量挖掘与结构化分析工具**

一个基于 Python 和大语言模型（LLM）的模块化、高并发医学文献挖掘工具。

## 功能特点

- 🔍 **PubMed 检索**: 支持关键词搜索或 PMID 列表批量处理
- 📄 **全文获取**: 自动从 PMC BioC API 获取开放获取全文
- 🏷️ **章节过滤**: 智能筛选研究相关章节（方法、结果、讨论等）
- 🤖 **LLM 提取**: 基于智谱 GLM-4 的结构化信息提取
- 📊 **规范化输出**: 导出标准化的 CSV 数据表
- 💾 **断点续传**: 支持中断后从断点恢复处理

## 安装

```bash
# 克隆仓库
git clone https://github.com/your-repo/PubMiner.git
cd PubMiner

# 安装依赖
pip install -r requirements.txt

# 或使用 pip 安装
pip install -e .
```

## 配置

1. 复制默认配置文件：
```bash
cp config/default.yaml config/my_config.yaml
```

2. 编辑配置文件，设置必要的参数：
```yaml
ncbi:
  email: "your_email@example.com"  # 必填
  api_key: ""                       # 可选，提高速率限制

zhipu:
  api_key: "${ZHIPU_API_KEY}"       # 必填，设置环境变量
```

3. 设置环境变量：
```bash
export ZHIPU_API_KEY="your_zhipu_api_key"
```

## 使用方法

### 基本用法

```bash
# 使用关键词搜索
python main.py -q "aging biomarkers AND humans" -c config/my_config.yaml

# 使用 PMID 列表文件
python main.py -f pmids.txt -c config/my_config.yaml

# 使用自定义字段
python main.py -q "senescence markers" --custom-fields config/custom_fields.yaml
```

### 断点续传

如果处理被中断，可以使用 `--resume` 继续：

```bash
python main.py --resume -c config/my_config.yaml
```

### 命令行选项

| 选项 | 说明 |
|------|------|
| `-q, --query` | PubMed 搜索关键词 |
| `-f, --file` | PMID 列表文件路径 |
| `-c, --config` | 配置文件路径 |
| `--custom-fields` | 自定义字段配置文件 |
| `-o, --output` | 输出目录 |
| `--max-results` | 最大结果数量 |
| `-v, --verbose` | 详细日志 |
| `--resume` | 恢复中断的处理 |

## 输出字段

### 基础字段

| 字段 | 说明 |
|------|------|
| `rationale` | 研究动因 |
| `framework` | 理论框架 |
| `lit_gaps` | 现有研究不足 |
| `objectives` | 研究目标 |
| `hypotheses` | 研究假设 |
| `sample_n` | 样本数量 |
| `methods` | 方法与工具 |
| `findings` | 核心发现 |
| `theory_value` | 理论意义 |
| `practical_val` | 实践价值 |
| ... | ... |

### 自定义字段

在 `config/custom_fields.yaml` 中定义领域特定字段：

```yaml
fields:
  - name: "biomarker_name"
    description: "生物标志物名称"
    type: "string"

  - name: "biomarker_type"
    description: "标志物类型"
    type: "enum"
    values: ["Single", "Composite"]
```

## 项目结构

```
PubMiner/
├── pubminer/
│   ├── core/          # 核心模块（配置、异常、状态）
│   ├── fetcher/       # PubMed 检索模块
│   ├── downloader/    # 全文下载模块
│   ├── extractor/     # LLM 提取模块
│   ├── exporter/      # 数据导出模块
│   └── cli/           # 命令行接口
├── config/            # 配置文件
├── output/            # 输出目录
├── main.py            # 主入口
└── requirements.txt   # 依赖列表
```

## 注意事项

1. **NCBI API 限制**: 无 API key 时约 3 请求/秒，有 key 时约 10 请求/秒
2. **全文可用性**: 仅 PMC Open Access Subset 的文章可获取全文
3. **LLM 成本**: 大批量处理需考虑 API 调用成本
4. **网络连接**: 需要稳定的网络连接访问 NCBI 和智谱 API

## License

MIT License
