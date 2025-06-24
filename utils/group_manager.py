# 群组管理器 - 处理群组相关的管理逻辑

import logging
import datetime
from typing import Dict, Any, Optional, Set

logger = logging.getLogger("group_manager")


class GroupManager:
    """群组管理器，负责管理群组信息和状态"""

    def __init__(self, parent):
        """初始化群组管理器

        Args:
            parent: 父插件实例，用于访问上下文和配置
        """
        self.parent = parent
        self.context = parent.context

    def is_group_whitelisted(self, group_id: str, whitelist: Set[str], whitelist_enabled: bool) -> bool:
        """检查群组是否在白名单中

        Args:
            group_id: 群组ID
            whitelist: 白名单群组集合
            whitelist_enabled: 是否启用白名单

        Returns:
            bool: 如果启用白名单且群组在白名单中，或者未启用白名单，返回True
        """
        if not whitelist_enabled:
            return True
        return group_id in whitelist

    def get_group_info(self, group_id: str) -> Dict[str, Any]:
        """获取群组信息

        Args:
            group_id: 群组ID

        Returns:
            Dict[str, Any]: 群组信息字典
        """
        # 这里可以扩展获取群组名称、成员数量等信息
        return {
            "group_id": group_id,
            "last_checked": datetime.datetime.now(),
        }

    def log_group_activity(self, group_id: str, activity_type: str, details: Optional[str] = None):
        """记录群组活动日志

        Args:
            group_id: 群组ID
            activity_type: 活动类型
            details: 详细信息
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] 群组 {group_id} - {activity_type}"
        if details:
            log_message += f": {details}"
        
        logger.info(log_message)

    def should_send_initiative_message(
        self, 
        group_id: str, 
        last_active_time: datetime.datetime,
        inactive_threshold: int,
        current_count: int,
        max_count: int
    ) -> bool:
        """判断是否应该向群组发送主动消息

        Args:
            group_id: 群组ID
            last_active_time: 最后活跃时间
            inactive_threshold: 不活跃阈值（秒）
            current_count: 当前连续消息计数
            max_count: 最大连续消息数

        Returns:
            bool: 是否应该发送主动消息
        """
        # 检查是否达到最大连续消息数
        if current_count >= max_count:
            logger.debug(f"群组 {group_id} 已达到最大连续消息数 {max_count}")
            return False

        # 检查不活跃时间
        now = datetime.datetime.now()
        inactive_seconds = (now - last_active_time).total_seconds()
        
        if inactive_seconds < inactive_threshold:
            logger.debug(f"群组 {group_id} 不活跃时间 {inactive_seconds:.0f}s 未达到阈值 {inactive_threshold}s")
            return False

        return True

    def format_group_stats(self, group_records: Dict[str, Any], consecutive_counts: Dict[str, int]) -> str:
        """格式化群组统计信息

        Args:
            group_records: 群组记录字典
            consecutive_counts: 连续消息计数字典

        Returns:
            str: 格式化的统计信息
        """
        if not group_records:
            return "当前没有监控的群组"

        stats_lines = ["群组监控统计:"]
        for group_id, record in group_records.items():
            last_active = record.get("timestamp", "未知")
            count = consecutive_counts.get(group_id, 0)
            
            if isinstance(last_active, datetime.datetime):
                last_active_str = last_active.strftime("%Y-%m-%d %H:%M:%S")
            else:
                last_active_str = str(last_active)
                
            stats_lines.append(f"- 群组 {group_id}: 最后活跃 {last_active_str}, 连续消息数: {count}")

        return "\n".join(stats_lines)

    def handle_llm_response_context(self, group_id: str, response_text: str, conversation_id: str) -> bool:
        """处理LLM回复的上下文管理
        
        Args:
            group_id: 群组ID
            response_text: LLM回复文本
            conversation_id: 会话ID
            
        Returns:
            bool: 是否成功处理
        """
        try:
            # 记录群组活动
            self.log_group_activity(
                group_id, 
                "LLM回复", 
                f"回复内容: {response_text[:50]}{'...' if len(response_text) > 50 else ''}"
            )
            
            # 这里可以添加更多的上下文处理逻辑
            # 例如：更新群组状态、记录互动历史等
            
            return True
            
        except Exception as e:
            logger.error(f"处理群组 {group_id} 的LLM回复上下文时出错: {str(e)}")
            return False

    def create_group_conversation_id(self, group_id: str, message_type: str = "group") -> str:
        """创建群组会话ID
        
        Args:
            group_id: 群组ID
            message_type: 消息类型
            
        Returns:
            str: 会话ID
        """
        return f"group_{group_id}_{message_type}"

    def get_group_unified_msg_origin(self, group_id: str, platform: str = "aiocqhttp") -> str:
        """获取群组统一消息来源
        
        Args:
            group_id: 群组ID
            platform: 平台名称
            
        Returns:
            str: 统一消息来源
        """
        return f"{platform}:group:{group_id}"
