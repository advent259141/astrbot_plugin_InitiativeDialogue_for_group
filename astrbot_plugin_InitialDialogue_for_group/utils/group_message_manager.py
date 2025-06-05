# 群聊消息管理器 - 处理群聊消息生成和发送逻辑

import json
import random
import logging
import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator
from astrbot.api.all import (
    AstrBotMessage,
    MessageType,
    MessageMember,
    MessageChain,
    MessageEventResult,
)
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain

logger = logging.getLogger("group_message_manager")


class GroupMessageManager:
    """群聊消息管理器，负责生成和发送各类群聊消息"""

    def __init__(self, parent):
        """初始化群聊消息管理器

        Args:
            parent: 父插件实例，用于访问上下文
        """
        self.parent = parent
        self.context = parent.context

    async def generate_and_send_message(
        self,
        group_id: str,
        conversation_id: str,
        unified_msg_origin: str,
        prompts: List[str],
        message_type: str = "一般",
        time_period: Optional[str] = None,
        extra_context: Optional[str] = None,
    ):
        """生成并发送群聊消息

        Args:
            group_id: 群组ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
            prompts: 可用的提示词列表
            message_type: 消息类型描述（用于日志）
            time_period: 时间段描述（如"早上"、"下午"等）
            extra_context: 额外的上下文信息
        """
        try:
            _, _, session_id = self.parse_unified_msg_origin(unified_msg_origin)
            # 获取对话对象
            conversation = await self.context.conversation_manager.get_conversation(
                unified_msg_origin, conversation_id
            )

            if not conversation:
                logger.error(
                    f"无法获取群组 {group_id} 的对话，会话ID: {conversation_id} 可能不存在"
                )
                return False

            # 获取对话历史和系统提示
            system_prompt = "你是一个可爱的AI助手，喜欢和用户互动。你现在在一个群聊中，可以适当活跃气氛。"

            # 获取当前对话的人格设置
            if conversation:
                persona_id = conversation.persona_id
                # 获取对话使用的人格设置
                system_prompt = self._get_system_prompt(persona_id, system_prompt)

            # 随机选择一个提示词
            prompt = random.choice(prompts)

            # 添加特殊标识，用于识别这是系统提示词而非用户消息
            system_marker = "[SYS_PROMPT]"
            
            # 调整提示词，针对群聊场景
            adjusted_prompt = f"{system_marker} {prompt}"
            context_requirement = "请确保回复贴合当前的群聊上下文情景，保持友好和活跃的语气。"

            if time_period:
                adjusted_prompt = f"{system_marker} {prompt}，现在是{time_period}，请保持与你的人格设定一致的风格，确保回复符合你的人设特点。{context_requirement}"
            else:
                adjusted_prompt = f"{system_marker} {prompt}，请保持与你的人格设定一致的风格，确保回复符合你的人设特点。{context_requirement}"

            if extra_context:
                # 将 extra_context 放在通用要求之前，确保其优先被考虑
                adjusted_prompt = f"{adjusted_prompt.replace(context_requirement, '')} {extra_context} {context_requirement}"

            # 获取LLM工具管理器
            func_tools_mgr = self.context.get_llm_tool_manager()

            # 调用LLM获取回复
            logger.info(f"正在为群组 {group_id} 生成{message_type}消息内容...")
            logger.debug(f"使用的提示词: {adjusted_prompt}")

            platform = self.context.get_platform("aiocqhttp")
            fake_event = self.create_fake_event(
                message_str=adjusted_prompt,
                bot=platform.bot,
                umo=unified_msg_origin,
                sender_id=group_id,
                session_id=session_id,
            )
            platform.commit_event(fake_event)
            
            # 仅在为主动消息类型时添加到标记集合中
            if message_type == "主动消息":
                if hasattr(self.parent, 'dialogue_core') and hasattr(self.parent.dialogue_core, 'groups_received_initiative'):
                    self.parent.dialogue_core.groups_received_initiative.add(group_id)
                
            return fake_event.request_llm(
                prompt=adjusted_prompt,
                func_tool_manager=func_tools_mgr,
                image_urls=[],
                system_prompt=system_prompt,
                conversation=conversation,
            )

        except Exception as e:
            logger.error(f"生成并发送群聊消息时发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def create_fake_event(self, message_str: str, bot, umo: str, session_id: str, sender_id: str = "123456"):
        """创建虚拟事件用于LLM调用"""
        try:
            from astrbot.core.platform.platform_metadata import PlatformMetadata
            from .aiocqhttp_message_event import AiocqhttpMessageEvent
        except ImportError:
            logger.error("无法导入所需模块，请检查AstrBot版本兼容性")
            return None

        # 使用配置中的self_id
        self_id = getattr(self.parent, 'config', {}).get("self_id", "")
        if not self_id:
            logger.warning("配置中未设置self_id，使用默认值，可能会导致异常")
            self_id = sender_id

        abm = AstrBotMessage()
        abm.message_str = message_str
        abm.message = [Plain(message_str)]
        abm.self_id = self_id
        abm.sender = MessageMember(user_id=sender_id)

        if "group" in umo.lower():
            # 群消息
            group_id = umo.split("_")[-1] if "_" in umo else sender_id
            try:
                abm.raw_message = {
                    "message_type": "group",
                    "group_id": int(group_id),
                    "user_id": int(sender_id),
                    "message": message_str,
                }
            except ValueError:
                abm.raw_message = {
                    "message_type": "group", 
                    "group_id": group_id,
                    "user_id": sender_id,
                    "message": message_str,
                }
        else:
            # 私聊消息（备用）
            try:
                abm.raw_message = {
                    "message_type": "private",
                    "user_id": int(sender_id),
                    "message": message_str,
                }
            except ValueError:
                abm.raw_message = {
                    "message_type": "private",
                    "user_id": sender_id,
                    "message": message_str,
                }

        abm.session_id = session_id
        abm.type = MessageType.GROUP_MESSAGE

        meta = PlatformMetadata("aiocqhttp", "fake_adapter")
        event = AiocqhttpMessageEvent(
            message_str=message_str,
            message_obj=abm,
            platform_meta=meta,
            session_id=session_id,
            bot=bot,
        )
        event.is_wake = True
        event.call_llm = False

        return event

    def _get_system_prompt(self, persona_id: Optional[str], default_prompt: str) -> str:
        """获取系统提示词"""
        try:
            if not persona_id:
                return default_prompt

            personas = self.context.provider_manager.personas
            
            for persona in personas:
                if persona.persona_id == persona_id:
                    return persona.prompt or default_prompt

            return default_prompt

        except Exception as e:
            logger.error(f"获取系统提示词时出错: {str(e)}")
            return default_prompt

    def parse_unified_msg_origin(self, unified_msg_origin: str) -> tuple:
        """解析统一消息来源"""
        try:
            parts = unified_msg_origin.split(":")
            if len(parts) >= 3:
                return parts[0], parts[1], parts[2]
            else:
                return "unknown", "unknown", unified_msg_origin
        except Exception as e:
            logger.error(f"解析统一消息来源时出错: {str(e)}")
            return "unknown", "unknown", unified_msg_origin
