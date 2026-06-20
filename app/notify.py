"""
飞书通知模块 — 通过 Webhook 推送发布状态消息。
成功通知受 NOTIFY_ON_SUCCESS 开关控制；失败通知始终发送。
发送失败只记录日志，不影响主流程。
"""
from __future__ import annotations

import logging

import aiohttp

from .config import Config

logger = logging.getLogger(__name__)


async def send_blocked(reason: str, cfg: Config) -> None:
    """广告/黑名单过滤通知（受 notify_on_blocked 开关控制）"""
    if not cfg.feishu_webhook or not cfg.notify_on_blocked:
        return
    await _send(f"🚫 消息已过滤\n原因：{reason}", cfg.feishu_webhook)


async def send_success(name: str, episode_raw: str, url: str, cfg: Config) -> None:
    """发布成功通知（受 notify_on_success 开关控制）"""
    if not cfg.feishu_webhook or not cfg.notify_on_success:
        return
    ep = f" {episode_raw}" if episode_raw else ""
    text = f"✅ 发布成功\n片名：《{name}》{ep}\n链接：{url}"
    await _send(text, cfg.feishu_webhook)


async def send_failure(
    name: str, error: str, retry_count: int, retry_max: int, cfg: Config
) -> None:
    """发布失败通知（始终发送，不受开关控制）"""
    if not cfg.feishu_webhook:
        return
    text = (
        f"🚨 发布失败\n"
        f"片名：《{name}》\n"
        f"错误：{error[:200]}\n"
        f"重试：{retry_count} / {retry_max}"
    )
    await _send(text, cfg.feishu_webhook)


async def send_dead(name: str, error: str, cfg: Config) -> None:
    """彻底失败通知（重试耗尽，需人工介入）"""
    if not cfg.feishu_webhook:
        return
    text = (
        f"❌ 已彻底放弃\n"
        f"片名：《{name}》\n"
        f"已重试 {cfg.retry_max} 次均失败\n"
        f"最后错误：{error[:200]}\n"
        f"请检查 Typecho 服务是否正常"
    )
    await _send(text, cfg.feishu_webhook)


async def _send(text: str, webhook: str) -> None:
    """向飞书 Webhook 发送 text 类型消息"""
    payload = {"msg_type": "text", "content": {"text": text}}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("飞书通知发送失败 | status=%d", resp.status)
    except Exception as e:
        # 通知失败不能影响主流程
        logger.warning("飞书通知异常 | error=%s", e)
