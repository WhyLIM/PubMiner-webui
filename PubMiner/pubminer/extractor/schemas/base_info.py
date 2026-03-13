"""
Base extraction schema model.

Contains all common fields for medical literature extraction.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class BaseExtractionModel(BaseModel):
    """
    Base extraction model for medical literature.

    Contains all standard fields that are typically extracted
    from medical research articles.
    """

    # === Research Background ===
    rationale: str = Field(
        default="",
        description="研究动因/研究背景：为什么进行这项研究，研究的出发点是什么",
    )
    framework: str = Field(
        default="",
        description="理论框架或模型：研究依据的理论基础或概念框架",
    )
    lit_gaps: str = Field(
        default="",
        description="现有研究成果及不足：文献综述中发现的研究空白或不足",
    )
    objectives: str = Field(
        default="",
        description="明确的研究目标：本研究要解决的具体问题",
    )
    hypotheses: str = Field(
        default="",
        description="研究问题或假设：本研究要验证的假设或回答的问题",
    )

    # === Study Methods ===
    sample_n: str = Field(
        default="",
        description="研究样本数量：参与研究的人数或样本量",
    )
    region: str = Field(
        default="",
        description="研究区域/地点：研究开展的地理位置",
    )
    conditions: str = Field(
        default="",
        description="实验条件/研究条件：研究实施的具体条件或设置",
    )
    data_source: str = Field(
        default="",
        description="数据来源：数据的获取渠道或数据库",
    )
    methods: str = Field(
        default="",
        description="方法与工具：使用的统计方法、模型或软件工具",
    )

    # === Variable Definitions ===
    iv: str = Field(
        default="",
        description="自变量(Independent Variable)：研究者操纵或观察的主要因素",
    )
    dv: str = Field(
        default="",
        description="因变量(Dependent Variable)：研究者测量的结果变量",
    )
    cv: str = Field(
        default="",
        description="控制变量(Control Variable)：研究中控制的其他因素",
    )

    # === Research Results ===
    findings: str = Field(
        default="",
        description="核心发现：研究的定量或定性主要发现",
    )
    stats_conclusion: str = Field(
        default="",
        description="主要数据分析结论：统计学分析得出的结论",
    )
    hyp_evidence: str = Field(
        default="",
        description="支持/反驳假设的证据：结果是否支持研究假设",
    )
    interpretation: str = Field(
        default="",
        description="结果解释：对研究结果的解释和说明",
    )

    # === Discussion ===
    comparison: str = Field(
        default="",
        description="与前人研究比较：本研究结果与已有文献的对比",
    )
    theory_value: str = Field(
        default="",
        description="理论意义：研究结果的理论贡献",
    )
    practical_value: str = Field(
        default="",
        description="实践价值：研究结果的实际应用价值",
    )
    future_work: str = Field(
        default="",
        description="未来研究方向：作者建议的后续研究方向",
    )

    # === Limitations ===
    data_limit: str = Field(
        default="",
        description="数据局限性：数据相关的研究局限",
    )
    method_limit: str = Field(
        default="",
        description="方法学局限性：研究方法相关的局限",
    )
    validity_limit: str = Field(
        default="",
        description="外部效度/适用范围问题：研究结果的推广性限制",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "rationale": "探究衰老生物标志物与寿命的关系",
                "objectives": "验证端粒长度作为衰老标志物的有效性",
                "sample_n": "500",
                "findings": "端粒长度与年龄呈负相关(r=-0.45, p<0.001)",
            }
        }
