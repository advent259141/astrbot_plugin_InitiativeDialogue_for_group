# 群聊主动对话核心模块，检测群聊不活跃状态并发送主动消息

import asyncio
import datetime
import logging
import random
from typing import Dict, Any, Set, List, Optional

from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import ProviderRequest

from ..utils.group_message_manager import GroupMessageManager
from ..utils.group_manager import GroupManager
from ..utils.task_manager import TaskManager
from ..utils.config_manager import ConfigManager

# 配置日志
logger = logging.getLogger("group_initiative_dialogue_core")


class GroupInitiativeDialogueCore:
    """群聊主动对话核心类，管理群组状态并在适当时候发送主动消息"""

    def __init__(self, parent, star):
        """初始化群聊主动对话核心

        Args:
            parent: 父插件实例，用于访问上下文和配置
        """
        self.parent = parent
        self.star = star
        self.context = star.context

        # 加载配置
        self.config_manager = ConfigManager(parent.config)
        
        # 从time_settings获取核心配置参数
        time_settings = self.config_manager.get_module_config("time_settings")
        self.inactive_time_seconds = time_settings.get(
            "inactive_time_seconds", 7200
        )  # 默认2小时
        self.max_response_delay_seconds = time_settings.get(
            "max_response_delay_seconds", 3600
        )  # 默认1小时
        self.time_limit_enabled = time_settings.get("time_limit_enabled", True)
        self.probability_enabled = time_settings.get("probability_enabled", True)  # 是否启用概率发送
        self.activity_start_hour = time_settings.get("activity_start_hour", 8)
        self.activity_end_hour = time_settings.get("activity_end_hour", 23)
        self.max_consecutive_messages = time_settings.get("max_consecutive_messages", 3)

        # 从whitelist获取白名单配置（改为群组白名单）
        whitelist_config = self.config_manager.get_module_config("whitelist")
        self.whitelist_enabled = whitelist_config.get("enabled", False)
        self.whitelist_groups = set(whitelist_config.get("group_ids", []))

        # 群聊提示词配置 - 针对群聊场景调整
        self.initiative_prompts = [
            # 首次发送 - 表达注意到群聊冷清
            "请生成一条简短的消息，表达你注意到群里很久没人说话了，想活跃一下气氛，询问大家在做什么或者分享一些有趣的话题，保持符合你的人设特点。",
            "请生成一条简短的消息，表示发现群聊有点冷清，想和大家聊聊天，可以问候大家或者提起一些轻松的话题，保持符合你的人设特点。",
            "请生成一条简短的消息，表达你看到群里安静了很久，想要主动和大家互动，可以分享一些日常或者询问大家的近况，保持符合你的人设特点。",
            "请生成一条简短的消息，表示注意到群里没什么动静，想要活跃一下聊天氛围，可以提出一些有趣的话题或者简单问候，保持符合你的人设特点。",
            
            # 中间阶段 - 继续尝试活跃气氛
            "请生成一条简短的消息，表达你之前尝试活跃群聊但大家似乎都很忙，继续友好地尝试与群成员互动，保持符合你的人设特点。",
            "请生成一条简短的消息，表示理解大家可能都在忙，但还是想和群里的朋友们聊聊天，继续保持友好的互动态度，保持符合你的人设特点。",
            
            # 后期阶段 - 理解但依然关心
            "请生成一条简短的消息，表达你理解大家都有自己的事情要忙，但还是关心群里的朋友们，希望大家一切都好，保持符合你的人设特点。",
            "请生成一条简短的消息，表示虽然群里比较安静，但你依然在这里陪伴大家，随时欢迎大家来聊天，保持符合你的人设特点。",
            
            # 最终阶段 - 温和地减少频率
            "请生成一条简短的消息，表达你会继续默默关注群聊，不会频繁打扰大家，但随时欢迎大家有空时来聊天，保持符合你的人设特点。",
            "请生成一条简短的消息，表示你理解群聊有自己的节奏，会适当减少主动发言，但始终在这里陪伴着大家，保持符合你的人设特点。"
        ]

        # 记录每个群组收到的连续主动消息次数
        self.consecutive_message_count = {}

        # 群组数据
        self.group_records = {}
        self.last_initiative_messages = {}
        self.groups_received_initiative = set()
        
        # 群组最后收到的主动消息类型记录
        self.last_initiative_types = {}

        # 检查任务引用
        self.inactive_check_task = None

        # 初始化共享组件
        self.message_manager = GroupMessageManager(parent)
        self.group_manager = GroupManager(parent)
        self.task_manager = TaskManager(parent)

        logger.info(
            f"群聊主动对话核心初始化完成，不活跃时间阈值：{self.inactive_time_seconds}秒"
        )

    def get_data(self) -> Dict[str, Any]:
        """获取核心数据用于持久化

        Returns:
            Dict: 包含群组记录和主动消息记录的字典
        """
        return {
            "group_records": self.group_records,
            "last_initiative_messages": self.last_initiative_messages,
            "groups_received_initiative": self.groups_received_initiative,
            "consecutive_message_count": self.consecutive_message_count,
            "last_initiative_types": self.last_initiative_types,
        }

    def set_data(
        self,
        group_records: Dict[str, Any],
        last_initiative_messages: Dict[str, Any],
        groups_received_initiative: Set[str],
        consecutive_message_count: Dict[str, int] = None,
        last_initiative_types: Dict[str, str] = None,
    ) -> None:
        """设置核心数据，从持久化存储恢复

        Args:
            group_records: 群组记录字典
            last_initiative_messages: 最后主动消息记录字典
            groups_received_initiative: 已接收主动消息的群组ID集合
            consecutive_message_count: 连续消息计数字典 (可选)
            last_initiative_types: 最后消息类型字典 (可选)
        """
        self.group_records = group_records
        self.last_initiative_messages = last_initiative_messages
        self.groups_received_initiative = groups_received_initiative
        
        # 如果提供了计数数据，则加载它
        if consecutive_message_count is not None:
            self.consecutive_message_count = consecutive_message_count
            
        # 如果提供了最后消息类型数据，则加载它
        if last_initiative_types is not None:
            self.last_initiative_types = last_initiative_types

        logger.info(
            f"已加载群组数据，共有 {len(group_records)} 条群组记录，"
            f"{len(last_initiative_messages)} 条主动消息记录，"
            f"{len(groups_received_initiative)} 个群组已接收主动消息，"
            f"{len(self.consecutive_message_count)} 个群组的连续消息计数"
        )

    async def start_checking_inactive_conversations(self) -> None:
        """启动检查不活跃群聊的任务"""
        if self.inactive_check_task is not None:
            logger.warning("检查不活跃群聊任务已在运行中")
            return

        logger.info("启动检查不活跃群聊任务")
        self.inactive_check_task = asyncio.create_task(
            self._check_inactive_conversations_loop()
        )

    async def stop_checking_inactive_conversations(self) -> None:
        """停止检查不活跃群聊的任务"""
        if self.inactive_check_task is not None and not self.inactive_check_task.done():
            self.inactive_check_task.cancel()
            try:
                await self.inactive_check_task
            except asyncio.CancelledError:
                pass

            self.inactive_check_task = None
            logger.info("不活跃群聊检查任务已停止")

    async def _check_inactive_conversations_loop(self) -> None:
        """定期检查不活跃群聊的循环"""
        try:
            while True:
                # 每30秒检查一次
                await asyncio.sleep(30)

                # 如果启用了时间限制，检查当前是否在活动时间范围内
                if self.time_limit_enabled:
                    current_hour = datetime.datetime.now().hour
                    if not (
                        self.activity_start_hour
                        <= current_hour
                        < self.activity_end_hour
                    ):
                        # 不在活动时间范围内，跳过本次检查
                        continue

                # 获取当前时间
                now = datetime.datetime.now()

                # 遍历所有群组记录，检查不活跃状态
                for group_id, record in list(self.group_records.items()):
                    # 如果启用了白名单且群组不在白名单中，跳过
                    if self.whitelist_enabled and group_id not in self.whitelist_groups:
                        continue
                        
                    # 检查群组连续消息计数，如果已达到最大值，跳过
                    current_count = self.consecutive_message_count.get(group_id, 0)
                    if current_count >= self.max_consecutive_messages:
                        logger.debug(f"群组 {group_id} 已达到最大连续消息数 {self.max_consecutive_messages}，跳过")
                        continue

                    # 检查群组最后活跃时间
                    last_active = record.get("timestamp")
                    if not last_active:
                        continue

                    # 计算不活跃时间（秒）
                    inactive_seconds = (now - last_active).total_seconds()

                    # 如果超过阈值，安排发送主动消息
                    if inactive_seconds >= self.inactive_time_seconds:
                        # 为群组创建发送主动消息的任务
                        task_id = f"group_initiative_{group_id}_{int(now.timestamp())}"
                        
                        logger.info(f"群组 {group_id} 当前计数为 {current_count}，准备发送主动消息")
                        
                        # 计算随机延迟时间，增加自然感
                        await self.task_manager.schedule_task(
                            task_id=task_id,
                            coroutine_func=self._send_initiative_message,
                            random_delay=True,
                            min_delay=0,
                            max_delay=int(self.max_response_delay_seconds / 60),
                            group_id=group_id,
                            conversation_id=record["conversation_id"],
                            unified_msg_origin=record["unified_msg_origin"],
                        )
                        
                        # 从记录中移除该群组，防止重复发送
                        self.group_records.pop(group_id, None)

        except asyncio.CancelledError:
            logger.info("不活跃群聊检查循环已取消")
            raise
        except Exception as e:
            logger.error(f"检查不活跃群聊时发生错误: {str(e)}")

    async def _send_initiative_message(
        self, group_id: str, conversation_id: str, unified_msg_origin: str
    ) -> None:
        """发送主动消息给指定群组

        Args:
            group_id: 群组ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
        """
        # 再次检查群组是否在白名单中（如果启用了白名单）
        if self.whitelist_enabled and group_id not in self.whitelist_groups:
            logger.info(f"群组 {group_id} 不在白名单中，取消发送主动消息")
            return
        
        # 获取当前计数并增加1
        current_count = 0
        if group_id in self.last_initiative_types:
            last_info = self.last_initiative_types[group_id]
            current_count = last_info.get("count", 0)
            logger.info(f"从last_initiative_types获取到群组 {group_id} 的计数: {current_count}")
        else:
            # 如果没有记录，才从consecutive_message_count获取
            current_count = self.consecutive_message_count.get(group_id, 0)
            logger.info(f"从consecutive_message_count获取到群组 {group_id} 的计数: {current_count}")
        
        next_count = current_count + 1
        
        # 检测是否达到最大消息数
        if next_count > self.max_consecutive_messages:
            logger.info(f"群组 {group_id} 的计数 {next_count} 超过最大值 {self.max_consecutive_messages}，取消发送")
            return
        
        logger.info(f"准备向群组 {group_id} 发送第 {next_count} 次主动消息")
        
        # 获取当前时间段，用于调整消息内容
        current_hour = datetime.datetime.now().hour
        if 6 <= current_hour < 8:
            time_period = "早上"
        elif 8 <= current_hour < 11:
            time_period = "上午"
        elif 11 <= current_hour < 13:
            time_period = "午饭"
        elif 13 <= current_hour < 17:
            time_period = "下午"
        elif 17 <= current_hour < 19:
            time_period = "晚饭"
        elif 19 <= current_hour < 23:
            time_period = "晚上"
        else:
            time_period = "深夜"
        
        # 确定使用的提示词
        prompt_index = 0
        
        if next_count == 1:
            # 首次发送 - 随机选择前4个提示词之一
            prompt_index = random.randint(0, 3)
        elif next_count == 2:
            # 第二次发送 - 使用中间阶段提示词
            prompt_index = random.randint(4, 5)
        elif next_count == self.max_consecutive_messages:
            # 最后一次发送 - 使用最终阶段提示词
            prompt_index = random.randint(8, 9)
        else:
            # 其他情况 - 使用后期阶段提示词
            prompt_index = random.randint(6, 7)
        
        # 确保索引在有效范围内
        prompt_index = min(prompt_index, len(self.initiative_prompts) - 1)
        
        # 获取最终提示词
        selected_prompt = self.initiative_prompts[prompt_index]
        
        # 构建上下文提示词，针对群聊场景
        extra_context = f"现在是{time_period}，这是第{next_count}次主动在群聊中发言(请不要在回复中直接提及这个数字或'第几次'字样)，"
        extra_context += f"请根据目前的时间段({time_period})调整内容，"
        extra_context += "请记住你是在群聊中发言，可以适当使用一些活跃气氛的表达方式。"
            
        if next_count >= self.max_consecutive_messages:
            extra_context += "这将是最后一次主动在群聊发言，表达你将减少主动发言的意思。"
            
        # 记录本次主动消息的类型信息
        message_type_info = {
            "count": next_count, 
            "time_period": time_period,
            "timestamp": datetime.datetime.now()
        }
        
        try:
            # 使用消息管理器发送主动消息
            result = await self.message_manager.generate_and_send_message(
                group_id=group_id,
                conversation_id=conversation_id,
                unified_msg_origin=unified_msg_origin,
                prompts=[selected_prompt],  # 只使用选定的提示词
                message_type="群聊主动消息",
                time_period=time_period,
                extra_context=extra_context
            )

            # 消息发送后，更新计数和信息
            self.consecutive_message_count[group_id] = next_count
            
            # 记录本次主动消息的类型信息
            message_type_info = {
                "count": next_count, 
                "time_period": time_period,
                "timestamp": datetime.datetime.now()
            }
            self.last_initiative_types[group_id] = message_type_info
            
            # 打印确认日志，确保计数已更新
            logger.info(f"群组 {group_id} 的计数已更新：consecutive_message_count={next_count}, "
                       f"last_initiative_types.count={message_type_info['count']}")
            
            # 更新主动消息记录
            now = datetime.datetime.now()
            self.last_initiative_messages[group_id] = {
                "timestamp": now,
                "conversation_id": conversation_id,
                "unified_msg_origin": unified_msg_origin,
            }

            # 标记群组已接收主动消息
            self.groups_received_initiative.add(group_id)

            logger.info(f"已向群组 {group_id} 发送第 {next_count} 次主动消息")
            
            # 如果未达到最大连续发送次数，将群组重新加入记录以继续监控
            if next_count < self.max_consecutive_messages:
                # 将群组重新添加到记录中，以重新开始计时
                self.group_records[group_id] = {
                    "timestamp": now,
                    "conversation_id": conversation_id,
                    "unified_msg_origin": unified_msg_origin,
                }
                logger.info(f"群组 {group_id} 无人回应，已重新加入监控记录，当前连续发送次数: {next_count}")
            else:
                logger.info(f"群组 {group_id} 已达到最大连续发送次数({self.max_consecutive_messages})，停止连续发送")
            
            # 立即保存数据以确保计数不丢失
            if hasattr(self.parent, 'data_loader'):
                try:
                    self.parent.data_loader.save_data_to_storage()
                    logger.info(f"群组 {group_id} 的消息计数更新后数据已保存: {next_count}")
                except Exception as save_error:
                    logger.error(f"保存计数数据时出错: {str(save_error)}")
                
        except Exception as e:
            logger.error(f"发送主动消息给群组 {group_id} 时发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def handle_group_message(self, group_id: str, event: AstrMessageEvent) -> None:
        """处理群组消息，更新活跃状态

        Args:
            group_id: 群组ID
            event: 消息事件
        """
        # 获取会话信息
        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(
                event.unified_msg_origin
            )
        )
        unified_msg_origin = event.unified_msg_origin

        # 更新群组记录
        now = datetime.datetime.now()
        self.group_records[group_id] = {
            "timestamp": now,
            "conversation_id": conversation_id,
            "unified_msg_origin": unified_msg_origin,
        }

        logger.debug(f"已更新群组 {group_id} 的活跃状态，最后活跃时间：{now}")
