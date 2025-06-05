# 任务管理器 - 处理异步任务的创建和管理

import asyncio
import logging
import datetime
import random
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger("task_manager")


class TaskManager:
    """任务管理器，负责创建和管理异步任务"""

    def __init__(self, parent):
        """初始化任务管理器

        Args:
            parent: 父插件实例，用于管理任务引用
        """
        self.parent = parent

        # 确保任务存储字典存在
        if not hasattr(self.parent, "_message_tasks"):
            self.parent._message_tasks = {}

    async def schedule_task(
        self,
        task_id: str,
        coroutine_func: Callable[..., Any],
        delay_minutes: int = 0,
        random_delay: bool = False,
        min_delay: int = 1,
        max_delay: int = 30,
        **kwargs,
    ) -> asyncio.Task:
        """创建并调度一个延迟执行的任务

        Args:
            task_id: 任务唯一标识符
            coroutine_func: 异步协程函数
            delay_minutes: 固定延迟分钟数
            random_delay: 是否使用随机延迟
            min_delay: 随机延迟最小分钟数
            max_delay: 随机延迟最大分钟数
            **kwargs: 传递给协程函数的参数

        Returns:
            asyncio.Task: 创建的任务对象
        """
        # 计算实际延迟时间
        actual_delay = delay_minutes
        if random_delay:
            actual_delay = random.randint(min_delay, max_delay)

        # 创建任务
        async def delayed_task():
            try:
                # 等待指定的延迟时间
                await asyncio.sleep(actual_delay * 60)
                # 执行实际任务
                await coroutine_func(**kwargs)
            except asyncio.CancelledError:
                logger.info(f"任务 {task_id} 已被取消")
                raise
            except Exception as e:
                logger.error(f"任务 {task_id} 执行出错: {str(e)}")

        # 创建任务并存储
        task = asyncio.create_task(delayed_task())
        self.parent._message_tasks[task_id] = task

        # 设置完成回调以清理任务引用
        def remove_task(t, tid=task_id):
            if tid in self.parent._message_tasks:
                self.parent._message_tasks.pop(tid, None)

        task.add_done_callback(remove_task)

        # 记录任务调度信息
        scheduled_time = datetime.datetime.now() + datetime.timedelta(
            minutes=actual_delay
        )
        logger.info(
            f"任务 {task_id} 已调度，将在 {actual_delay} 分钟后({scheduled_time.strftime('%H:%M')})执行"
        )

        return task

    def cancel_all_tasks(self) -> None:
        """取消所有正在运行的任务"""
        for task_id, task in list(self.parent._message_tasks.items()):
            if not task.done():
                task.cancel()
                logger.info(f"任务 {task_id} 已取消")

        self.parent._message_tasks.clear()

    def cancel_task(self, task_id: str) -> bool:
        """取消指定ID的任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        if task_id in self.parent._message_tasks:
            task = self.parent._message_tasks[task_id]
            if not task.done():
                task.cancel()
                logger.info(f"任务 {task_id} 已取消")
                return True

        return False
