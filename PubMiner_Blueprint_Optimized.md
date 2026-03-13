# PubMiner: 智能医学文献批量挖掘与结构化分析工具

## 优化版开发蓝图与架构规范 (Optimized Master Blueprint v2.0)

---

## 一、 项目概述

### 项目名称
**PubMiner**

### 核心定位
基于 Python 和大语言模型（LLM）的**模块化、高并发、可扩展**医学文献挖掘工具。

### 主要工作流
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  文献检索模块   │ ──▶ │  全文获取模块   │ ──▶ │  LLM提取模块    │ ──▶ │  导出输出模块   │
│   (Fetcher)     │     │  (Downloader)   │     │  (Extractor)    │     │   (Exporter)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │                       │
   关键词/PMID            PMC BioC API             智谱GLM-4               规范化CSV
   元数据批量获取         章节筛选过滤             结构化JSON提取          自定义字段
```

### 核心特性
- ✅ **异步高并发**：全面采用 aiohttp + asyncio，千级文献处理吞吐量
- ✅ **生态集成**：Biopython 处理 NCBI E-utilities，避免重复造轮子
- ✅ **强类型校验**：Pydantic v2 驱动，自动生成 Schema 并验证 LLM 输出
- ✅ **断点续传**：支持任务中断后从断点恢复，避免重复处理
- ✅ **进度可视化**：实时进度条和详细日志追踪
- ✅ **领域可扩展**：支持用户自定义提取字段，无需修改代码

---

## 二、 核心架构与技术选型

### 架构设计原则
```
┌────────────────────────────────────────────────────────────────────────────┐
│                           PubMiner 架构分层图                              │
├────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      CLI Layer (命令行接口层)                        │   │
│  │              main.py + argparse + rich progress                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Core Layer (核心基础层)                           │   │
│  │     config.py | exceptions.py | logger.py | cache.py | state.py    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   Module Layer (功能模块层)                          │   │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │   │
│  │  │  Fetcher  │ │Downloader │ │ Extractor │ │ Exporter  │           │   │
│  │  │(Biopython)│ │ (aiohttp) │ │ (ZhipuAI) │ │ (Pandas)  │           │   │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                  Data Layer (数据模型层)                             │   │
│  │               Pydantic v2 Models + JSON Schema                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘
```

### 技术栈详细选型

| 层级 | 技术选型 | 版本要求 | 选型理由 |
|------|----------|----------|----------|
| 异步运行时 | asyncio + aiohttp | ≥3.8 | 原生支持，无额外依赖 |
| NCBI交互 | Biopython | ≥1.81 | 官方生态，XML解析成熟 |
| 数据校验 | Pydantic | ≥2.0 | 性能优异，Schema自动生成 |
| 进度显示 | rich | ≥13.0 | 美观、线程安全的进度条 |
| 配置管理 | pydantic-settings + PyYAML | - | 类型安全的配置加载 |
| 数据处理 | pandas | ≥2.0 | CSV导出与数据清洗 |
| LLM API | zhipuai | ≥2.0 | 智谱官方SDK |

### 关键技术决策

#### 1. 异步适配策略
```python
# Biopython 同步 → 异步适配模式
async def async_entrez_call(func, *args, **kwargs):
    """将同步的 Entrez 调用包装为异步"""
    return await asyncio.to_thread(func, *args, **kwargs)
```

#### 2. Pydantic Schema 驱动
```python
# 从 Pydantic Model 自动生成 LLM 所需的 JSON Schema
class BaseExtractionModel(BaseModel):
    rationale: str = Field(description="研究动因")
    # ...

# 自动生成给 LLM 的 Schema
schema = BaseExtractionModel.model_json_schema()
```

#### 3. 断点续传机制
```python
# 使用 JSON 文件记录处理状态
class StateManager:
    def save_checkpoint(self, pmid: str, stage: str, data: dict):
        """保存处理检查点"""
        
    def load_checkpoint(self) -> dict:
        """加载上次处理状态"""
```

---

## 三、 优化版项目目录结构

```
PubMiner/
├── pubminer/
│   ├── __init__.py
│   │
│   ├── core/                          # 核心基础设置
│   │   ├── __init__.py
│   │   ├── config.py                  # 全局配置 (Pydantic Settings + YAML)
│   │   ├── exceptions.py              # 自定义异常层次结构
│   │   ├── logger.py                  # 结构化异步日志 (rich + logging)
│   │   ├── cache.py                   # 内存/磁盘缓存管理器
│   │   └── state.py                   # 断点续传状态管理器
│   │
│   ├── fetcher/                       # 模块1: 文献检索与元数据
│   │   ├── __init__.py
│   │   ├── pubmed_client.py           # Entrez 异步客户端
│   │   ├── models.py                  # LiteratureMetadata Pydantic 模型
│   │   └── utils.py                   # PMID验证、日期解析等工具
│   │
│   ├── downloader/                    # 模块2: 全文下载器
│   │   ├── __init__.py
│   │   ├── base.py                    # 抽象基类 (支持扩展其他源)
│   │   ├── pmc_bioc.py                # PMC BioC API 客户端
│   │   ├── pdf_fallback.py            # PDF 备选下载 (Unpaywall等)
│   │   ├── section_parser.py          # 章节解析与过滤逻辑
│   │   └── models.py                  # FullTextDocument Pydantic 模型
│   │
│   ├── extractor/                     # 模块3: LLM 结构化提取
│   │   ├── __init__.py
│   │   ├── base.py                    # 抽象提取器基类 (支持扩展其他LLM)
│   │   ├── zhipu_client.py            # 智谱 GLM-4 异步客户端
│   │   ├── schemas/                   # Pydantic 提取模型
│   │   │   ├── __init__.py
│   │   │   ├── base_info.py           # 基础通用信息模型
│   │   │   └── custom.py              # 动态自定义模型生成器
│   │   ├── prompts/                   # 提示词模板管理
│   │   │   ├── __init__.py
│   │   │   ├── system_prompt.py       # 系统提示词
│   │   │   └── user_prompt.py         # 用户提示词模板
│   │   ├── validators.py              # LLM输出后处理器
│   │   └── rate_limiter.py            # API速率限制器
│   │
│   ├── exporter/                      # 模块4: 数据输出
│   │   ├── __init__.py
│   │   ├── csv_writer.py              # CSV导出 (规范化表头)
│   │   ├── json_writer.py             # JSON导出 (备选)
│   │   └── column_mapping.py          # 中英文 → 规范化表头映射
│   │
│   └── cli/                           # 命令行界面
│       ├── __init__.py
│       ├── main.py                    # CLI入口点
│       └── commands/                  # 子命令
│           ├── search.py              # pubminer search
│           ├── extract.py             # pubminer extract
│           └── export.py              # pubminer export
│
├── tests/                             # 测试目录
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── output/                            # 导出结果目录
│   ├── csv/
│   ├── json/
│   └── checkpoints/                   # 断点文件
│
├── config/                            # 配置文件目录
│   ├── default.yaml                   # 默认配置
│   ├── custom_fields.yaml             # 自定义字段定义
│   └── column_mapping.yaml            # 表头映射配置
│
├── main.py                            # 主程序入口 (简捷入口)
├── pyproject.toml                     # 项目元数据 (替代setup.py)
├── requirements.txt                   # 依赖清单
└── README.md                          # 项目文档
```

---

## 四、 核心模块详细设计规范

### 模块 1：Fetcher (文献基础信息获取)

#### 设计要点
1. **异步适配**：使用 `asyncio.to_thread()` 包装同步 Entrez 调用
2. **速率限制**：自动遵守 NCBI API 限制 (3 req/s 无key, 10 req/s 有key)
3. **批量处理**：支持历史服务器 (WebEnv) 进行大批量检索
4. **断点续传**：记录已获取的 PMID，支持中断恢复

#### 核心数据模型
```python
# pubminer/fetcher/models.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

class LiteratureMetadata(BaseModel):
    """文献元数据模型"""
    pmid: str = Field(..., description="PubMed ID")
    pmcid: Optional[str] = Field(None, description="PMC ID (如有)")
    doi: Optional[str] = Field(None, description="DOI")
    title: str = Field(..., description="文章标题")
    authors: List[str] = Field(default_factory=list, description="作者列表")
    journal: str = Field("", description="期刊名称")
    pub_date: Optional[date] = Field(None, description="发表日期")
    abstract: str = Field("", description="摘要")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    mesh_terms: List[str] = Field(default_factory=list, description="MeSH主题词")
    
    # 全文可用性标记
    has_pmc_fulltext: bool = Field(False, description="是否有PMC全文")
    
    class Config:
        # 导出时字段顺序
        json_schema_extra = {
            "example": {
                "pmid": "12345678",
                "pmcid": "PMC1234567",
                "title": "Example Article Title"
            }
        }
```

#### 异步客户端设计
```python
# pubminer/fetcher/pubmed_client.py
import asyncio
from Bio import Entrez
from typing import List, Optional
from .models import LiteratureMetadata

class AsyncPubMedClient:
    """异步 PubMed 客户端"""
    
    def __init__(
        self, 
        email: str, 
        api_key: Optional[str] = None,
        rate_limit: float = 0.34  # ~3 req/s without key
    ):
        Entrez.email = email
        Entrez.api_key = api_key
        if api_key:
            rate_limit = 0.1  # ~10 req/s with key
        
        self._rate_limiter = asyncio.Semaphore(1)
        self._last_request_time = 0
        self._min_interval = rate_limit
    
    async def _rate_limited_call(self, func, *args, **kwargs):
        """带速率限制的异步调用"""
        async with self._rate_limiter:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            
            result = await asyncio.to_thread(func, *args, **kwargs)
            self._last_request_time = asyncio.get_event_loop().time()
            return result
    
    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_range: Optional[tuple] = None
    ) -> List[str]:
        """搜索并返回 PMID 列表"""
        search_args = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "usehistory": "y"
        }
        
        if date_range:
            search_args["mindate"] = date_range[0]
            search_args["maxdate"] = date_range[1]
        
        handle = await self._rate_limited_call(
            Entrez.esearch, **search_args
        )
        record = Entrez.read(handle)
        handle.close()
        
        return record["IdList"]
    
    async def fetch_metadata(
        self,
        pmids: List[str],
        batch_size: int = 200
    ) -> List[LiteratureMetadata]:
        """批量获取文献元数据"""
        results = []
        
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            
            handle = await self._rate_limited_call(
                Entrez.efetch,
                db="pubmed",
                id=",".join(batch),
                rettype="xml",
                retmode="xml"
            )
            
            records = Entrez.read(handle)
            handle.close()
            
            for record in records:
                metadata = self._parse_pubmed_record(record)
                results.append(metadata)
        
        return results
```

---

### 模块 2：Downloader (全文与章节获取)

#### 设计要点
1. **BioC 优先**：优先使用 NCBI BioC API 获取结构化全文
2. **章节过滤**：智能过滤，只保留研究相关章节
3. **多源备选**：支持 PDF 下载作为备选方案
4. **Token 优化**：移除参考文献、致谢等非核心内容

#### 章节类型定义
```python
# pubminer/downloader/section_parser.py
from enum import Enum
from typing import Dict, List

class SectionType(Enum):
    """文献章节类型"""
    ABSTRACT = "ABSTRACT"
    INTRODUCTION = "INTRO"
    METHODS = "METHODS"
    RESULTS = "RESULTS"
    DISCUSSION = "DISCUSSION"
    CONCLUSION = "CONCLUSION"
    REFERENCES = "REFERENCES"  # 过滤
    ACKNOWLEDGMENTS = "ACK"    # 过滤
    SUPPLEMENT = "SUPPL"       # 可选
    OTHER = "OTHER"

# 章节过滤配置
SECTION_FILTER = {
    # 保留的章节类型
    "keep": [
        SectionType.ABSTRACT,
        SectionType.INTRODUCTION,
        SectionType.METHODS,
        SectionType.RESULTS,
        SectionType.DISCUSSION,
        SectionType.CONCLUSION
    ],
    # 默认丢弃的章节类型
    "discard": [
        SectionType.REFERENCES,
        SectionType.ACKNOWLEDGMENTS
    ]
}

# 章节标题映射（处理不同期刊的命名差异）
SECTION_TITLE_MAP = {
    "introduction": SectionType.INTRODUCTION,
    "background": SectionType.INTRODUCTION,
    "methods": SectionType.METHODS,
    "methodology": SectionType.METHODS,
    "materials and methods": SectionType.METHODS,
    "results": SectionType.RESULTS,
    "findings": SectionType.RESULTS,
    "discussion": SectionType.DISCUSSION,
    "conclusion": SectionType.CONCLUSION,
    "conclusions": SectionType.CONCLUSION,
    "abstract": SectionType.ABSTRACT,
    "summary": SectionType.ABSTRACT,
    "references": SectionType.REFERENCES,
    "bibliography": SectionType.REFERENCES,
    "acknowledgments": SectionType.ACKNOWLEDGMENTS,
    "acknowledgements": SectionType.ACKNOWLEDGMENTS,
}

class BioCSectionParser:
    """BioC 章节解析器"""
    
    def __init__(self, keep_sections: List[SectionType] = None):
        self.keep_sections = keep_sections or SECTION_FILTER["keep"]
    
    def parse_bioc_document(self, bioc_data: dict) -> Dict[SectionType, str]:
        """解析 BioC 文档并按章节分类"""
        sections = {}
        
        for passage in bioc_data.get("documents", [{}])[0].get("passages", []):
            section_type = self._classify_section(passage)
            
            if section_type in self.keep_sections:
                text = passage.get("text", "")
                if section_type not in sections:
                    sections[section_type] = text
                else:
                    sections[section_type] += "\n\n" + text
        
        return sections
    
    def _classify_section(self, passage: dict) -> SectionType:
        """根据段落信息判断章节类型"""
        # 优先使用 BioC 标注的章节类型
        infons = passage.get("infons", {})
        if "section_type" in infons:
            section_str = infons["section_type"].upper()
            for st in SectionType:
                if st.value in section_str:
                    return st
        
        # 备选：根据标题判断
        if "title" in infons:
            title = infons["title"].lower()
            for key, section_type in SECTION_TITLE_MAP.items():
                if key in title:
                    return section_type
        
        return SectionType.OTHER
    
    def get_filtered_text(self, bioc_data: dict) -> str:
        """获取过滤后的全文"""
        sections = self.parse_bioc_document(bioc_data)
        
        # 按章节顺序拼接
        ordered_sections = [
            SectionType.ABSTRACT,
            SectionType.INTRODUCTION,
            SectionType.METHODS,
            SectionType.RESULTS,
            SectionType.DISCUSSION,
            SectionType.CONCLUSION
        ]
        
        parts = []
        for st in ordered_sections:
            if st in sections and sections[st]:
                parts.append(f"[{st.value}]\n{sections[st]}")
        
        return "\n\n".join(parts)
```

#### BioC API 客户端
```python
# pubminer/downloader/pmc_bioc.py
import aiohttp
from typing import Optional, Dict
from .section_parser import BioCSectionParser
from .models import FullTextDocument

class BioCAPIClient:
    """NCBI BioC API 异步客户端"""
    
    BASE_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"
    
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.parser = BioCSectionParser()
    
    async def fetch_fulltext(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
        format: str = "json"
    ) -> Optional[Dict]:
        """获取全文 BioC 格式数据"""
        url = f"{self.BASE_URL}/BioC_{format}/{pmcid}/unicode"
        
        for attempt in range(self.max_retries):
            try:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        if format == "json":
                            return await response.json()
                        return await response.text()
                    elif response.status == 404:
                        # 文章不在 PMC OA Subset 中
                        return None
                    else:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # 指数退避
        
        return None
    
    async def get_filtered_text(
        self,
        session: aiohttp.ClientSession,
        pmcid: str
    ) -> Optional[FullTextDocument]:
        """获取过滤后的全文"""
        bioc_data = await self.fetch_fulltext(session, pmcid)
        
        if not bioc_data:
            return None
        
        filtered_text = self.parser.get_filtered_text(bioc_data)
        
        return FullTextDocument(
            pmcid=pmcid,
            raw_bioc=bioc_data,
            filtered_text=filtered_text,
            sections=self.parser.parse_bioc_document(bioc_data)
        )
```

---

### 模块 3：Extractor (LLM 结构化提取)

#### 设计要点
1. **Schema 驱动**：Pydantic Model 自动生成 JSON Schema
2. **动态扩展**：支持运行时添加自定义字段
3. **输出校验**：自动重试校验失败的提取
4. **并发控制**：API 调用速率限制

#### 基础提取模型
```python
# pubminer/extractor/schemas/base_info.py
from pydantic import BaseModel, Field
from typing import Optional, List

class BaseExtractionModel(BaseModel):
    """基础通用信息提取模型
    
    包含所有医学文献通用的结构化信息字段
    """
    
    # === 研究背景与目标 ===
    rationale: str = Field(
        default="",
        description="研究动因/研究背景：为什么进行这项研究"
    )
    framework: str = Field(
        default="",
        description="理论框架或模型：研究依据的理论基础"
    )
    lit_gaps: str = Field(
        default="",
        description="现有研究成果及不足：文献中的研究空白"
    )
    objectives: str = Field(
        default="",
        description="明确的研究目标"
    )
    hypotheses: str = Field(
        default="",
        description="研究问题或假设"
    )
    
    # === 研究方法 ===
    sample_n: str = Field(
        default="",
        description="研究样本数量"
    )
    region: str = Field(
        default="",
        description="研究区域/地点"
    )
    conditions: str = Field(
        default="",
        description="实验条件/研究条件"
    )
    data_source: str = Field(
        default="",
        description="数据来源"
    )
    methods: str = Field(
        default="",
        description="方法与工具（统计方法/模型/软件）"
    )
    
    # === 变量设定 ===
    iv: str = Field(
        default="",
        description="自变量 (Independent Variable)"
    )
    dv: str = Field(
        default="",
        description="因变量 (Dependent Variable)"
    )
    cv: str = Field(
        default="",
        description="控制变量 (Control Variable)"
    )
    
    # === 研究结果 ===
    findings: str = Field(
        default="",
        description="核心发现（定量/定性结果）"
    )
    stats_conclusion: str = Field(
        default="",
        description="主要数据分析结论"
    )
    hyp_evidence: str = Field(
        default="",
        description="支持/反驳假设的证据"
    )
    interpretation: str = Field(
        default="",
        description="结果解释"
    )
    
    # === 讨论与意义 ===
    comparison: str = Field(
        default="",
        description="与前人研究的比较"
    )
    theory_value: str = Field(
        default="",
        description="理论意义"
    )
    practical_value: str = Field(
        default="",
        description="实践价值/应用价值"
    )
    future_work: str = Field(
        default="",
        description="未来研究方向"
    )
    
    # === 研究局限 ===
    data_limit: str = Field(
        default="",
        description="数据局限性"
    )
    method_limit: str = Field(
        default="",
        description="方法学局限性"
    )
    validity_limit: str = Field(
        default="",
        description="外部效度/适用范围问题"
    )
```

#### 自定义字段动态生成器
```python
# pubminer/extractor/schemas/custom.py
from pydantic import BaseModel, Field, create_model
from typing import Type, Dict, Any, List, Literal
from enum import Enum

class CustomFieldDefinition(BaseModel):
    """自定义字段定义"""
    name: str                          # 字段名（英文，用于表头）
    description: str                   # 字段描述（喂给LLM）
    field_type: str = "str"            # 字段类型: str, int, float, enum
    enum_values: List[str] = []        # 如果是enum类型，枚举值列表
    required: bool = False             # 是否必填
    default: Any = ""                  # 默认值

class DynamicSchemaBuilder:
    """动态 Schema 构建器"""
    
    @staticmethod
    def create_custom_model(
        base_model: Type[BaseModel],
        custom_fields: List[CustomFieldDefinition]
    ) -> Type[BaseModel]:
        """动态创建包含自定义字段的模型"""
        
        # 获取基础字段
        base_fields = {
            name: (field.annotation, field.default)
            for name, field in base_model.model_fields.items()
        }
        
        # 添加自定义字段
        custom_fields_dict = {}
        for cf in custom_fields:
            field_type = str
            default = cf.default if cf.default else ""
            
            if cf.field_type == "int":
                field_type = int
                default = cf.default if cf.default else 0
            elif cf.field_type == "float":
                field_type = float
                default = cf.default if cf.default else 0.0
            elif cf.field_type == "enum" and cf.enum_values:
                # 创建枚举类型
                enum_name = f"{cf.name.title()}Enum"
                field_type = Enum(enum_name, {v.upper(): v for v in cf.enum_values})
                default = None
            
            custom_fields_dict[cf.name] = (
                field_type,
                Field(default=default, description=cf.description)
            )
        
        # 合并字段
        all_fields = {**base_fields, **custom_fields_dict}
        
        # 动态创建模型
        return create_model(
            "CustomExtractionModel",
            __base__=base_model,
            **custom_fields_dict
        )

# 预定义：衰老生物标志物研究的自定义字段
AGING_BIOMARKER_FIELDS = [
    CustomFieldDefinition(
        name="biomarker_name",
        description="文章中研究的生物标志物名称",
        field_type="str"
    ),
    CustomFieldDefinition(
        name="biomarker_type",
        description="属于单个生物标志物还是组合生物标志物",
        field_type="enum",
        enum_values=["Single", "Composite"]
    ),
    CustomFieldDefinition(
        name="biomarker_category",
        description="生物标志物的分类",
        field_type="enum",
        enum_values=["Protein", "DNA", "RNA", "Metabolite", "Other"]
    ),
    CustomFieldDefinition(
        name="population_ethnicity",
        description="研究样本人群的种族",
        field_type="str"
    ),
    CustomFieldDefinition(
        name="gender_ratio",
        description="研究样本的男女比例",
        field_type="str"
    ),
    CustomFieldDefinition(
        name="biomarker_desc",
        description="关于该生物标志物的具体描述",
        field_type="str"
    )
]
```

#### 智谱 API 客户端
```python
# pubminer/extractor/zhipu_client.py
from zhipuai import ZhipuAI
from pydantic import BaseModel, ValidationError
from typing import Type, Dict, Any, List, Optional
import asyncio
import json
from .rate_limiter import RateLimiter

class ZhipuExtractor:
    """智谱 GLM-4 异步提取器"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "glm-4-flash",
        max_retries: int = 3,
        rate_limit: float = 0.5  # 秒/请求
    ):
        self.client = ZhipuAI(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(rate_limit)
    
    async def extract(
        self,
        text: str,
        schema_model: Type[BaseModel],
        custom_instructions: str = ""
    ) -> Dict[str, Any]:
        """执行结构化提取"""
        
        # 获取 JSON Schema
        json_schema = schema_model.model_json_schema()
        
        # 构建提示词
        system_prompt = self._build_system_prompt(json_schema, custom_instructions)
        user_prompt = self._build_user_prompt(text)
        
        # 带重试的提取
        for attempt in range(self.max_retries):
            try:
                await self.rate_limiter.acquire()
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1  # 低温度，提高一致性
                )
                
                # 解析并验证 JSON
                result = json.loads(response.choices[0].message.content)
                
                # Pydantic 验证
                validated = schema_model(**result)
                
                return validated.model_dump()
                
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt == self.max_retries - 1:
                    return {"error": str(e), "raw_response": response.choices[0].message.content}
                continue
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        
        return {"error": "Max retries exceeded"}
    
    async def batch_extract(
        self,
        documents: List[Dict[str, str]],
        schema_model: Type[BaseModel],
        concurrency: int = 5
    ) -> List[Dict[str, Any]]:
        """批量提取（并发控制）"""
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def limited_extract(doc):
            async with semaphore:
                result = await self.extract(doc["text"], schema_model)
                result["pmid"] = doc["pmid"]
                return result
        
        tasks = [limited_extract(doc) for doc in documents]
        return await asyncio.gather(*tasks)
    
    def _build_system_prompt(
        self,
        json_schema: dict,
        custom_instructions: str
    ) -> str:
        """构建系统提示词"""
        schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)
        
        return f"""你是一位专业的医学文献分析专家。你的任务是从给定的医学研究文献中提取结构化信息。

## 输出要求
1. 严格按照提供的 JSON Schema 格式输出
2. 所有字段都必须填写，如果文献中未提及某信息，填写 "未提及" 或相应默认值
3. 保持信息的准确性和完整性，不要编造或推测
4. 使用简洁、规范的表达方式

{custom_instructions}

## JSON Schema
```json
{schema_str}
```

## 重要提示
- 直接输出 JSON 对象，不要包含任何其他文字
- 确保输出是合法的 JSON 格式
- 字段值使用中文或英文均可，保持一致性"""

    def _build_user_prompt(self, text: str) -> str:
        """构建用户提示词"""
        # 文本截断（控制 Token 数量）
        max_chars = 15000  # 约 5000 tokens
        truncated_text = text[:max_chars]
        if len(text) > max_chars:
            truncated_text += "\n...[文本已截断]..."
        
        return f"""请从以下文献内容中提取结构化信息：

---
{truncated_text}
---

请按照指定的 JSON Schema 格式输出提取结果。"""
```

---

### 模块 4：Exporter (数据输出)

#### 表头映射规范
```python
# pubminer/exporter/column_mapping.py
from typing import Dict

# 中文字段名 → 规范化英文表头
COLUMN_MAPPING: Dict[str, str] = {
    # 元数据
    "pmid": "pmid",
    "pmcid": "pmcid",
    "doi": "doi",
    "title": "title",
    "authors": "authors",
    "journal": "journal",
    "pub_date": "pub_date",
    "abstract": "abstract",
    "keywords": "keywords",
    "mesh_terms": "mesh_terms",
    "has_pmc_fulltext": "has_fulltext",
    
    # 研究背景
    "rationale": "rationale",          # 研究动因
    "framework": "framework",          # 理论框架
    "lit_gaps": "lit_gaps",            # 现有研究不足
    "objectives": "objectives",        # 研究目标
    "hypotheses": "hypotheses",        # 研究假设
    
    # 研究方法
    "sample_n": "sample_n",            # 样本量
    "region": "region",                # 研究区域
    "conditions": "conditions",        # 实验条件
    "data_source": "data_source",      # 数据来源
    "methods": "methods",              # 方法工具
    
    # 变量设定
    "iv": "iv",                        # 自变量
    "dv": "dv",                        # 因变量
    "cv": "cv",                        # 控制变量
    
    # 研究结果
    "findings": "findings",            # 核心发现
    "stats_conclusion": "stats_concl", # 统计结论
    "hyp_evidence": "hyp_evidence",    # 假设证据
    "interpretation": "interpretation",# 结果解释
    
    # 讨论意义
    "comparison": "vs_prior",          # 与前人比较
    "theory_value": "theory_value",    # 理论意义
    "practical_value": "practical_val",# 实践价值
    "future_work": "future_work",      # 未来方向
    
    # 局限性
    "data_limit": "data_limit",        # 数据局限
    "method_limit": "method_limit",    # 方法局限
    "validity_limit": "validity",      # 效度局限
    
    # 自定义字段（衰老生物标志物示例）
    "biomarker_name": "biomarker",
    "biomarker_type": "marker_type",
    "biomarker_category": "marker_cat",
    "population_ethnicity": "ethnicity",
    "gender_ratio": "gender_ratio",
    "biomarker_desc": "marker_desc"
}

# 列顺序定义（输出 CSV 时的列顺序）
COLUMN_ORDER = [
    # 元数据（固定在最前）
    "pmid", "pmcid", "doi", "title", "authors", "journal", "pub_date",
    
    # 研究背景
    "rationale", "framework", "lit_gaps", "objectives", "hypotheses",
    
    # 研究方法
    "sample_n", "region", "conditions", "data_source", "methods",
    
    # 变量设定
    "iv", "dv", "cv",
    
    # 研究结果
    "findings", "stats_concl", "hyp_evidence", "interpretation",
    
    # 讨论意义
    "vs_prior", "theory_value", "practical_val", "future_work",
    
    # 局限性
    "data_limit", "method_limit", "validity",
    
    # 自定义字段（动态追加）
    # ...
    
    # 辅助信息（固定在最后）
    "has_fulltext", "abstract", "keywords", "mesh_terms"
]
```

#### CSV 导出器
```python
# pubminer/exporter/csv_writer.py
import pandas as pd
from typing import List, Dict, Optional
from pathlib import Path
from .column_mapping import COLUMN_MAPPING, COLUMN_ORDER

class CSVExporter:
    """规范化 CSV 导出器"""
    
    def __init__(
        self,
        custom_columns: Optional[List[str]] = None
    ):
        self.custom_columns = custom_columns or []
    
    def export(
        self,
        metadata_list: List[Dict],
        extraction_results: List[Dict],
        output_path: str,
        include_abstract: bool = False
    ) -> str:
        """合并数据并导出为 CSV"""
        
        # 构建数据字典（以 PMID 为键）
        data_map = {}
        
        # 合并元数据
        for meta in metadata_list:
            pmid = meta.get("pmid")
            if pmid:
                data_map[pmid] = {"pmid": pmid, **meta}
        
        # 合并提取结果
        for result in extraction_results:
            pmid = result.get("pmid")
            if pmid in data_map:
                data_map[pmid].update(result)
            else:
                data_map[pmid] = {"pmid": pmid, **result}
        
        # 转换为 DataFrame
        df = pd.DataFrame(list(data_map.values()))
        
        # 重命名列
        df = df.rename(columns=COLUMN_MAPPING)
        
        # 排序列
        all_columns = COLUMN_ORDER.copy()
        # 添加自定义列
        for col in self.custom_columns:
            if col not in all_columns:
                all_columns.append(col)
        
        # 只保留存在的列
        existing_cols = [col for col in all_columns if col in df.columns]
        df = df[existing_cols]
        
        # 可选：移除摘要列
        if not include_abstract and "abstract" in df.columns:
            df = df.drop(columns=["abstract"])
        
        # 导出
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        
        return str(output_path)
```

---

## 五、 配置系统设计

### 配置文件结构
```yaml
# config/default.yaml

# NCBI API 配置
ncbi:
  email: "your_email@example.com"      # 必填，NCBI 要求
  api_key: ""                           # 可选，有 key 可提高速率限制
  tool_name: "PubMiner"
  rate_limit:
    without_key: 0.34                   # 秒/请求 (~3 req/s)
    with_key: 0.1                       # 秒/请求 (~10 req/s)

# 智谱 API 配置
zhipu:
  api_key: "${ZHIPU_API_KEY}"           # 支持环境变量
  model: "glm-4-flash"                  # 模型选择：glm-4, glm-4-flash
  temperature: 0.1
  max_tokens: 4096
  rate_limit: 0.5                       # 秒/请求

# 文献检索配置
search:
  max_results: 100                      # 最大返回结果数
  batch_size: 200                       # 批量获取大小
  date_range: null                      # 日期范围 ["2020/01/01", "2024/12/31"]

# 全文下载配置
download:
  sections:                             # 保留的章节类型
    - "ABSTRACT"
    - "INTRO"
    - "METHODS"
    - "RESULTS"
    - "DISCUSSION"
    - "CONCLUSION"
  timeout: 30                           # 请求超时（秒）
  max_retries: 3                        # 最大重试次数

# LLM 提取配置
extraction:
  base_fields: true                     # 是否提取基础字段
  custom_fields_file: null              # 自定义字段配置文件路径
  max_retries: 3                        # 验证失败重试次数
  concurrency: 5                        # 并发数

# 输出配置
output:
  directory: "./output"
  format: "csv"                         # csv, json, both
  include_abstract: false               # 是否包含摘要
  filename_prefix: "pubminer_result"

# 断点续传配置
checkpoint:
  enabled: true
  directory: "./output/checkpoints"
  auto_resume: true                     # 自动恢复中断的任务
```

### 自定义字段配置
```yaml
# config/custom_fields.yaml

# 衰老生物标志物研究自定义字段示例
fields:
  - name: "biomarker_name"
    description: "文章中研究的生物标志物名称"
    type: "string"
    
  - name: "biomarker_type"
    description: "属于单个生物标志物还是组合生物标志物"
    type: "enum"
    values: ["Single", "Composite", "Unknown"]
    
  - name: "biomarker_category"
    description: "生物标志物的分子分类"
    type: "enum"
    values: ["Protein", "DNA", "RNA", "Metabolite", "Epigenetic", "Other"]
    
  - name: "population_ethnicity"
    description: "研究样本人群的种族/族裔"
    type: "string"
    
  - name: "gender_ratio"
    description: "研究样本的男女比例（如 'Male: 45%, Female: 55%'）"
    type: "string"
    
  - name: "biomarker_desc"
    description: "关于该生物标志物的具体描述和研究发现"
    type: "string"

# 自定义提示词增强
additional_instructions: |
  对于生物标志物研究，请特别关注：
  1. 标志物的具体测量方法和单位
  2. 标志物与衰老的关联强度
  3. 是否经过独立队列验证
```

---

## 六、 断点续传与状态管理

```python
# pubminer/core/state.py
import json
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime
from enum import Enum

class ProcessingStage(Enum):
    """处理阶段"""
    FETCHED = "fetched"           # 元数据已获取
    DOWNLOADED = "downloaded"     # 全文已下载
    EXTRACTED = "extracted"       # 信息已提取
    COMPLETED = "completed"       # 处理完成
    FAILED = "failed"             # 处理失败

class StateManager:
    """断点续传状态管理器"""
    
    def __init__(self, checkpoint_dir: str = "./output/checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.checkpoint_dir / "processing_state.json"
        self._state: Dict = self._load_state()
    
    def _load_state(self) -> Dict:
        """加载状态文件"""
        if self.state_file.exists():
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "query": "",
            "total_pmids": 0,
            "pmids": {}  # {pmid: {"stage": "...", "data": {...}}}
        }
    
    def _save_state(self):
        """保存状态文件"""
        self._state["last_updated"] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)
    
    def set_query(self, query: str, total: int):
        """设置查询信息"""
        self._state["query"] = query
        self._state["total_pmids"] = total
        self._save_state()
    
    def update_pmid(
        self,
        pmid: str,
        stage: ProcessingStage,
        data: Optional[Dict] = None
    ):
        """更新 PMID 处理状态"""
        if pmid not in self._state["pmids"]:
            self._state["pmids"][pmid] = {}
        
        self._state["pmids"][pmid]["stage"] = stage.value
        self._state["pmids"][pmid]["updated_at"] = datetime.now().isoformat()
        
        if data:
            self._state["pmids"][pmid]["data"] = data
        
        self._save_state()
    
    def get_pending_pmids(
        self,
        target_stage: ProcessingStage
    ) -> Set[str]:
        """获取需要处理的 PMID（未达到目标阶段的）"""
        pending = set()
        for pmid, info in self._state["pmids"].items():
            current = ProcessingStage(info.get("stage", ""))
            if current.value < target_stage.value:
                pending.add(pmid)
        return pending
    
    def get_completed_data(self) -> Dict[str, Dict]:
        """获取已完成的数据"""
        completed = {}
        for pmid, info in self._state["pmids"].items():
            if info.get("stage") == ProcessingStage.COMPLETED.value:
                completed[pmid] = info.get("data", {})
        return completed
    
    def get_progress(self) -> Dict:
        """获取处理进度"""
        stages = {stage.value: 0 for stage in ProcessingStage}
        for info in self._state["pmids"].values():
            stage = info.get("stage", "fetched")
            stages[stage] = stages.get(stage, 0) + 1
        
        return {
            "total": self._state["total_pmids"],
            "stages": stages,
            "completed": stages.get(ProcessingStage.COMPLETED.value, 0),
            "failed": stages.get(ProcessingStage.FAILED.value, 0)
        }
```

---

## 七、 主程序流程

```python
# main.py
import asyncio
import argparse
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from pubminer.core.config import Config
from pubminer.core.state import StateManager, ProcessingStage
from pubminer.fetcher.pubmed_client import AsyncPubMedClient
from pubminer.fetcher.models import LiteratureMetadata
from pubminer.downloader.pmc_bioc import BioCAPIClient
from pubminer.extractor.zhipu_client import ZhipuExtractor
from pubminer.extractor.schemas.base_info import BaseExtractionModel
from pubminer.extractor.schemas.custom import DynamicSchemaBuilder, AGING_BIOMARKER_FIELDS
from pubminer.exporter.csv_writer import CSVExporter

console = Console()

async def run_pipeline(
    query: str = None,
    pmid_file: str = None,
    config_path: str = "config/default.yaml",
    custom_fields_file: str = None
):
    """主处理流程"""
    
    # 1. 加载配置
    config = Config.from_yaml(config_path)
    state = StateManager(config.checkpoint.directory)
    
    # 2. 初始化客户端
    pubmed_client = AsyncPubMedClient(
        email=config.ncbi.email,
        api_key=config.ncbi.api_key
    )
    bioc_client = BioCAPIClient()
    extractor = ZhipuExtractor(
        api_key=config.zhipu.api_key,
        model=config.zhipu.model
    )
    
    # 3. 获取 PMID 列表
    if pmid_file:
        with open(pmid_file, 'r') as f:
            pmids = [line.strip() for line in f if line.strip()]
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("搜索 PubMed...", total=None)
            pmids = await pubmed_client.search(query, max_results=config.search.max_results)
    
    console.print(f"[green]找到 {len(pmids)} 篇文献[/green]")
    state.set_query(query or pmid_file, len(pmids))
    
    # 4. 获取元数据
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console
    ) as progress:
        task = progress.add_task("获取文献元数据...", total=len(pmids))
        metadata_list = await pubmed_client.fetch_metadata(pmids)
        progress.update(task, completed=len(pmids))
    
    # 更新状态
    for meta in metadata_list:
        state.update_pmid(meta.pmid, ProcessingStage.FETCHED, meta.model_dump())
    
    # 5. 下载全文
    fulltexts = []
    async with aiohttp.ClientSession() as session:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("下载全文...", total=len(metadata_list))
            
            for meta in metadata_list:
                if meta.pmcid:
                    doc = await bioc_client.get_filtered_text(session, meta.pmcid)
                    if doc:
                        fulltexts.append({
                            "pmid": meta.pmid,
                            "pmcid": meta.pmcid,
                            "text": doc.filtered_text
                        })
                        state.update_pmid(meta.pmid, ProcessingStage.DOWNLOADED)
                progress.update(task, advance=1)
    
    console.print(f"[green]成功下载 {len(fulltexts)} 篇全文[/green]")
    
    # 6. 构建提取 Schema
    if custom_fields_file:
        # 加载自定义字段
        custom_fields = load_custom_fields(custom_fields_file)
        schema_model = DynamicSchemaBuilder.create_custom_model(
            BaseExtractionModel, custom_fields
        )
    else:
        schema_model = BaseExtractionModel
    
    # 7. LLM 提取
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console
    ) as progress:
        task = progress.add_task("LLM 结构化提取...", total=len(fulltexts))
        
        extraction_results = await extractor.batch_extract(
            fulltexts,
            schema_model,
            concurrency=config.extraction.concurrency
        )
        
        for result in extraction_results:
            if "error" not in result:
                state.update_pmid(result["pmid"], ProcessingStage.EXTRACTED, result)
            else:
                state.update_pmid(result["pmid"], ProcessingStage.FAILED, result)
            progress.update(task, advance=1)
    
    # 8. 导出结果
    exporter = CSVExporter()
    output_path = exporter.export(
        metadata_list,
        extraction_results,
        f"{config.output.directory}/{config.output.filename_prefix}.csv"
    )
    
    # 9. 显示结果摘要
    progress_info = state.get_progress()
    
    table = Table(title="处理结果摘要")
    table.add_column("指标", style="cyan")
    table.add_column("数量", style="green")
    
    table.add_row("总计文献", str(progress_info["total"]))
    table.add_row("成功提取", str(progress_info["completed"]))
    table.add_row("处理失败", str(progress_info["failed"]))
    table.add_row("输出文件", output_path)
    
    console.print(table)
    
    return output_path

def main():
    parser = argparse.ArgumentParser(
        description="PubMiner: 智能医学文献批量挖掘与结构化分析工具"
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-q", "--query", help="PubMed 搜索关键词")
    group.add_argument("-f", "--file", help="PMID 列表文件路径")
    
    parser.add_argument("-c", "--config", default="config/default.yaml", help="配置文件路径")
    parser.add_argument("--custom-fields", help="自定义字段配置文件")
    parser.add_argument("-o", "--output", help="输出目录")
    
    args = parser.parse_args()
    
    asyncio.run(run_pipeline(
        query=args.query,
        pmid_file=args.file,
        config_path=args.config,
        custom_fields_file=args.custom_fields
    ))

if __name__ == "__main__":
    main()
```

---

## 八、 使用示例

### 命令行使用

```bash
# 1. 使用关键词搜索并提取
python main.py -q "aging biomarkers AND humans" -c config/default.yaml

# 2. 使用 PMID 列表文件
python main.py -f pmids.txt -c config/default.yaml

# 3. 使用自定义字段配置
python main.py -q "senescence markers" --custom-fields config/custom_fields.yaml

# 4. 指定输出目录
python main.py -q "longevity" -o ./results/
```

### Python API 使用

```python
import asyncio
from pubminer import PubMiner

async def main():
    # 初始化
    miner = PubMiner(config_path="config/default.yaml")
    
    # 搜索并提取
    results = await miner.process(
        query="aging biomarkers AND humans",
        max_results=50,
        custom_fields="config/custom_fields.yaml"
    )
    
    # 导出
    results.to_csv("output.csv")
    
    # 查看结果
    print(results.summary())

asyncio.run(main())
```

---

## 九、 关键优化点总结

| 优化项 | 原方案 | 优化后 | 收益 |
|--------|--------|--------|------|
| 项目结构 | 4层模块 | 6层分层架构 | 更清晰的职责划分 |
| 状态管理 | 未提及 | 完整的断点续传机制 | 中断后可恢复 |
| 进度显示 | 未提及 | rich 进度条 | 更好的用户体验 |
| 章节解析 | 简单描述 | 完整的枚举+映射系统 | 更准确的过滤 |
| Schema生成 | 静态定义 | 动态生成器 | 无需改代码扩展 |
| 配置系统 | 简单YAML | Pydantic Settings | 类型安全+验证 |
| 错误处理 | 基础重试 | 分层异常+重试策略 | 更健壮 |
| 列顺序 | 未定义 | 明确的顺序定义 | 更好的可读性 |

---

## 十、 依赖清单

```txt
# requirements.txt

# 核心依赖
aiohttp>=3.9.0
asyncio>=3.4.3

# NCBI 交互
biopython>=1.81

# 数据处理
pydantic>=2.5.0
pydantic-settings>=2.1.0
pandas>=2.0.0

# LLM API
zhipuai>=2.0.0

# CLI & 显示
rich>=13.0.0
argparse

# 配置
pyyaml>=6.0

# 可选依赖
openpyxl>=3.1.0    # Excel 导出
orjson>=3.9.0      # 更快的 JSON 处理
```

---

此优化版蓝图完善了原方案的多个关键细节，提供了更完整、更健壮的实现指南。如需进一步细化某个模块或开始编码实现，请告知！
