"""Example customer-service expert profiles for multi-agent mode."""

from __future__ import annotations

import os

from agent_core.multi_agent.types import AgentProfile, MultiAgentHarnessOptions


def multi_agent_enabled() -> bool:
    return os.environ.get("ENABLE_MULTI_AGENT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def default_cs_profiles() -> list[AgentProfile]:
    return [
        AgentProfile(
            name="billing",
            description="处理订单、退款、发票与支付相关问题",
            system_prompt=(
                "你是计费与订单专家。根据用户任务简洁回答退款、订单状态、发票等问题。"
                "若信息不足，说明需要哪些订单号或账号信息。"
            ),
        ),
        AgentProfile(
            name="knowledge",
            description="解答产品政策、FAQ 与规则类问题",
            system_prompt=(
                "你是知识库与政策专家。基于常识与给定任务说明政策与 FAQ。"
                "回答简短、可执行；不确定时明确说明。"
            ),
        ),
        AgentProfile(
            name="logistics",
            description="查询物流、配送与签收状态",
            system_prompt=(
                "你是物流专家。根据任务描述物流状态与下一步建议。"
                "若缺少运单号，请指出需要的信息。"
            ),
        ),
    ]


def default_multi_agent_options() -> MultiAgentHarnessOptions:
    return MultiAgentHarnessOptions(
        profiles=default_cs_profiles(),
        max_concurrent_agents=4,
        routing_prompt=(
            "你是客服接待员。优先用自然语言安抚用户，需要查订单/政策/物流时调用 "
            "delegate_task 派给专家；汇总专家结果后再回复用户。"
            "单问题用 single；可并行的独立查询用 parallel；有依赖时用 chain（可用 {previous}）。"
        ),
    )
