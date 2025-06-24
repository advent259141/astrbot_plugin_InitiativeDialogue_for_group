# Description: 一个群聊主动对话插件，当群聊长时间无人说话时主动发送消息
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, register, Star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api import AstrBotConfig, logger
import asyncio
import os
import pathlib
import datetime
from .core.group_initiative_dialogue_core import GroupInitiativeDialogueCore
from .utils.data_loader import DataLoader


@register(
    "initiative_dialogue_for_group",
    "Jason",
    "群聊主动对话插件，当群聊长时间无人说话时主动发送消息",
    "1.0.0",
)
class InitiativeDialogueForGroup(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        # 基础配置
        self.config = config or {}

        # 打印收到的配置，用于调试
        logger.info(f"收到的配置内容: {self.config}")

        # 设置数据存储路径
        self.data_dir = (
            pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        )
        self.data_file = self.data_dir / "group_dialogue_storage.json"

        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)

        # 初始化核心对话模块
        self.dialogue_core = GroupInitiativeDialogueCore(self, self)

        # 初始化数据加载器并加载数据
        self.data_loader = DataLoader.get_instance(self)
        self.data_loader.load_data_from_storage()

        # 记录配置信息到日志
        logger.info(
            f"已加载群聊主动对话配置，不活跃时间阈值: {self.dialogue_core.inactive_time_seconds}秒, "
            f"随机回复窗口: {self.dialogue_core.max_response_delay_seconds}秒, "
            f"时间限制: {'启用' if self.dialogue_core.time_limit_enabled else '禁用'}, "
            f"活动时间: {self.dialogue_core.activity_start_hour}点-{self.dialogue_core.activity_end_hour}点, "
            f"最大连续消息数: {self.dialogue_core.max_consecutive_messages}条"
        )
        
        # 添加白名单信息日志
        logger.info(
            f"白名单功能状态: {'启用' if self.dialogue_core.whitelist_enabled else '禁用'}, "
            f"白名单群组数量: {len(self.dialogue_core.whitelist_groups)}"
        )

        # 启动检查任务
        asyncio.create_task(self.dialogue_core.start_checking_inactive_conversations())

        # 启动定期保存数据任务
        asyncio.create_task(self.data_loader.start_periodic_save())

        logger.info("群聊主动对话插件初始化完成，检测任务已启动")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """处理群聊消息"""
        group_id = event.get_group_id()
        if not group_id:
            return
            
        message_str = event.message_str

        # 检查消息是否包含系统提示词标记
        if "[SYS_PROMPT]" in message_str:
            logger.debug(f"检测到系统提示词消息，跳过计数重置: {message_str[:50]}...")
            return
            
        # 委托给核心模块处理
        await self.dialogue_core.handle_group_message(group_id, event)
        
        # 调试日志，查看当前计数
        current_count = self.dialogue_core.consecutive_message_count.get(group_id, 0)
        logger.debug(f"群组 {group_id} 当前计数为 {current_count}")
        
        # 如果群组曾收到过主动消息，这里直接处理重置计数逻辑
        if group_id in self.dialogue_core.groups_received_initiative:
            old_count = self.dialogue_core.consecutive_message_count.get(group_id, 0)
            self.dialogue_core.consecutive_message_count[group_id] = 0
            
            # 同时也重置last_initiative_types中的计数
            if group_id in self.dialogue_core.last_initiative_types:
                old_info = self.dialogue_core.last_initiative_types[group_id]
                old_info["count"] = 0
                self.dialogue_core.last_initiative_types[group_id] = old_info
            
            logger.info(f"群组 {group_id} 有人发言，计数从 {old_count} 重置为 0")
            
            # 移除标记，表示已处理该回复
            self.dialogue_core.groups_received_initiative.discard(group_id)
            
            # 立即保存数据以确保计数重置被保存
            if hasattr(self, 'data_loader'):
                try:
                    self.data_loader.save_data_to_storage()
                    logger.info(f"群组 {group_id} 计数重置后数据已保存")
                except Exception as save_error:
                    logger.error(f"保存重置计数数据时出错: {str(save_error)}")

    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("正在停止群聊主动对话插件...")

        # 在终止前打印当前状态
        for group_id, count in self.dialogue_core.consecutive_message_count.items():
            logger.info(f"群组 {group_id} 的最终连续消息计数: {count}")

        # 保存当前数据
        self.data_loader.save_data_to_storage()

        # 停止核心模块的检查任务
        await self.dialogue_core.stop_checking_inactive_conversations()

        # 停止定期保存数据的任务
        await self.data_loader.stop_periodic_save()

    @filter.command("group_initiative_test")
    async def test_group_initiative_message(self, event: AstrMessageEvent):
        """测试群聊主动消息生成"""
        if not event.is_admin():
            yield event.plain_result("只有管理员可以使用此命令")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令只能在群聊中使用")
            return

        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(
                event.unified_msg_origin
            )
        )
        unified_msg_origin = event.unified_msg_origin

        prompts = self.dialogue_core.initiative_prompts
        time_period = "测试"

        yield await self.dialogue_core.message_manager.generate_and_send_message(
            group_id=group_id,
            conversation_id=conversation_id,
            unified_msg_origin=unified_msg_origin,
            prompts=prompts,
            message_type="测试",
            time_period=time_period,
        )
