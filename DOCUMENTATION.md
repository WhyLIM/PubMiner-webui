# 📚 PubMiner2 使用手册

## 快速启动

### 启动后端

```powershell
cd PubMiner
python api_server.py
```

访问: http://localhost:8000

### 启动前端

```powershell
pnpm dev
```

访问: http://localhost:3001

---

## 核心功能

- **文献检索**: PubMed 关键词搜索或 PMID 列表
- **全文获取**: PMC BioC API 自动下载
- **智能提取**: 智谱 GLM-4 结构化信息提取
- **数据导出**: CSV 格式输出

### 元数据提取字段

**基础信息**: PMID, PMCID, DOI, 标题, 作者, 第一作者, 单位
**期刊信息**: 期刊名, 缩写, ISSN, 卷期页码
**出版信息**: 出版日期, 年份, 出版状态, 文章类型
**内容信息**: 摘要, 关键词, MeSH 主题词, 语言
**引用信息**: 被引次数, 引用文章列表, 参考文献数, 参考文献列表
**其他**: 文章状态, 最后修订日期, 基金信息

---

## 技术栈

**前端**: Next.js 16 + TypeScript + Tailwind CSS + shadcn/ui
**后端**: Python 3.13 + FastAPI + Biopython + ZhipuAI

---

## 关键配置

### Coding Plan 端点（默认启用）

**配置文件**: `PubMiner/config/default.yaml`

```yaml
zhipu:
  use_coding_plan: true  # 使用 Coding Plan 专属端点
```

**端点地址**:

- Coding Plan: `https://open.bigmodel.cn/api/coding/paas/v4`
- 标准端点: `https://open.bigmodel.cn/api/paas/v4`

---

## 常见问题

### 1. 端口被占用

```powershell
# 查找进程
netstat -ano | findstr :8000

# 结束进程
taskkill /PID <进程ID> /F
```

### 2. UTF-8 编码问题

已在 `api_server.py` 中自动处理，无需手动设置。

### 3. BioCAPIClient 方法错误

正确方法名: `batch_download()` (不是 `download_batch()`)

### 4. ZhipuExtractor 参数错误

`batch_extract()` 需要 `schema_model` 参数：
```python
# 正确调用
extraction_results = await extractor.batch_extract(
    fulltext_docs,
    schema_model,  # 必需参数
    concurrency=config.extraction.concurrency
)
```

### 5. 文件下载 404 错误

**问题**: 前端请求 `/api/results/output/api_result_xxx.csv` 返回 404

**原因**: 后端返回的文件名包含路径

**修复**:
```python
# 错误 ❌
tasks[task_id]["result_file"] = str(csv_path)  # 包含完整路径

# 正确 ✅
tasks[task_id]["result_file"] = Path(csv_path).name  # 只返回文件名
```

### 6. CSV 只有元数据没有 LLM 提取结果

**原因**:
1. 没有成功下载全文（PMCID 为空或全文不可用）
2. 全文下载失败

**解决方案**:
- 检查日志中的 "Found X articles with PMC full text"
- 如果为 0，说明这些文章没有 PMC 全文
- 如果有全文但下载失败，检查网络连接和 PMC API 状态

---

## 项目结构

```
PubMiner2/
├── src/                    # Next.js 前端
├── PubMiner/              # Python 后端
│   ├── api_server.py     # FastAPI 服务
│   ├── config/           # 配置文件
│   └── pubminer/         # 核心模块
├── README.md             # 项目简介
└── DOCUMENTATION.md      # 本文档
```

---

## API 端点

- `POST /api/search` - PubMed 搜索
- `POST /api/extract` - 启动提取任务
- `GET /api/tasks/{task_id}` - 查询任务状态
- `GET /api/results/{filename}` - 下载结果

完整 API 文档: http://localhost:8000/docs

---

**更新时间**: 2026-03-06
