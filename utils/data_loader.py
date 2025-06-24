# 单例模式数据读取器 - 群聊版

import asyncio
import datetime
import json
from astrbot.api import logger
from typing import Dict, Any


class DataLoader:
    """数据加载器, 单例模式"""

    _instance = None

    @classmethod
    def get_instance(cls, plugin_instance=None):
        if cls._instance is None and plugin_instance is not None:
            cls._instance = cls(plugin_instance)
        return cls._instance

    def __init__(self, plugin_instance):
        if DataLoader._instance is not None:
            raise RuntimeError("Please use get_instance() to access the instance.")
        self.plugin = plugin_instance
        self.data_dir = plugin_instance.data_dir
        self.data_file = plugin_instance.data_file
        self.dialogue_core = plugin_instance.dialogue_core

        self.save_data_task = None

        DataLoader._instance = self

    def load_data_from_storage(self) -> None:
        try:
            if self.data_file.exists():
                with open(self.data_file, "r", encoding="utf-8") as f:
                    stored_data = json.load(f)

                    # 处理时间戳转换 (group_records)
                    if "group_records" in stored_data:
                        for group_id, record in stored_data["group_records"].items():
                            if "timestamp" in record and isinstance(
                                record["timestamp"], str
                            ):
                                try:
                                    record["timestamp"] = (
                                        datetime.datetime.fromisoformat(
                                            record["timestamp"]
                                        )
                                    )
                                except ValueError:
                                    record["timestamp"] = datetime.datetime.now()
                    
                    # 处理时间戳转换 (last_initiative_messages)
                    if "last_initiative_messages" in stored_data:
                        for group_id, record in stored_data[
                            "last_initiative_messages"
                        ].items():
                            if "timestamp" in record and isinstance(
                                record["timestamp"], str
                            ):
                                try:
                                    record["timestamp"] = (
                                        datetime.datetime.fromisoformat(
                                            record["timestamp"]
                                        )
                                    )
                                except ValueError:
                                    record["timestamp"] = datetime.datetime.now()
                    
                    # 处理时间戳转换 (last_initiative_types)
                    if "last_initiative_types" in stored_data:
                        for group_id, record in stored_data["last_initiative_types"].items():
                            if "timestamp" in record and isinstance(record["timestamp"], str):
                                try:
                                    record["timestamp"] = datetime.datetime.fromisoformat(record["timestamp"])
                                except ValueError:
                                    record["timestamp"] = datetime.datetime.now()

                    # 传递所有数据给对话核心
                    self.dialogue_core.set_data(
                        group_records=stored_data.get("group_records", {}),
                        last_initiative_messages=stored_data.get(
                            "last_initiative_messages", {}
                        ),
                        groups_received_initiative=set(
                            stored_data.get("groups_received_initiative", [])
                        ),
                        consecutive_message_count=stored_data.get("consecutive_message_count", {}),
                        last_initiative_types=stored_data.get("last_initiative_types", {})
                    )
                        
            logger.info(f"成功从 {self.data_file} 加载群组数据")
        except Exception as e:
            logger.error(f"从存储加载数据时发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def save_data_to_storage(self) -> None:
        """将数据保存到本地存储"""
        try:
            core_data = self.dialogue_core.get_data()

            data_to_save = {
                "group_records": self._prepare_records_for_save(
                    core_data.get("group_records", {})
                ),
                "last_initiative_messages": self._prepare_records_for_save(
                    core_data.get("last_initiative_messages", {})
                ),
                "groups_received_initiative": list(
                    core_data.get("groups_received_initiative", [])
                ),
                "consecutive_message_count": core_data.get("consecutive_message_count", {}),
                "last_initiative_types": self._prepare_records_for_save(
                    core_data.get("last_initiative_types", {})
                ),
            }

            # 确保数据目录存在
            self.data_file.parent.mkdir(exist_ok=True)
            
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            logger.info(f"群组数据已保存到 {self.data_file}")
        except Exception as e:
            logger.error(f"保存数据到存储时发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _prepare_records_for_save(self, records: Dict[str, Any]) -> Dict[str, Any]:
        """准备记录以便保存，将datetime对象转换为ISO格式字符串"""
        prepared_records = {}

        # 检查 records 是否为字典
        if not isinstance(records, dict):
            logger.warning(f"_prepare_records_for_save 接收到的 records 不是字典: {type(records)}")
            return prepared_records

        for key, value in records.items():
            # 如果值是字典，递归处理
            if isinstance(value, dict):
                prepared_records[key] = self._prepare_records_for_save(value)
            # 如果值是 datetime 对象，转换为 ISO 格式字符串
            elif isinstance(value, datetime.datetime):
                prepared_records[key] = value.isoformat()
            elif isinstance(value, datetime.date):
                prepared_records[key] = value.isoformat()
            # 其他类型的值直接复制
            else:
                prepared_records[key] = value

        return prepared_records

    async def start_periodic_save(self) -> None:
        """启动定期保存数据的任务"""
        if self.save_data_task is not None:
            logger.warning("定期保存数据任务已在运行中")
            return

        logger.info("启动定期保存数据任务")
        self.save_data_task = asyncio.create_task(self._periodic_save_data())

    async def stop_periodic_save(self) -> None:
        """停止定期保存数据的任务"""
        if self.save_data_task is not None and not self.save_data_task.done():
            self.save_data_task.cancel()
            try:
                await self.save_data_task
            except asyncio.CancelledError:
                pass

            self.save_data_task = None
            logger.info("定期保存数据任务已取消")

    async def _periodic_save_data(self) -> None:
        """定期保存数据的异步任务"""
        try:
            while True:
                await asyncio.sleep(300)  # 每5分钟保存一次
                self.save_data_to_storage()
        except asyncio.CancelledError:
            self.save_data_to_storage()
            logger.info("定期保存数据任务已取消")
            raise
        except Exception as e:
            logger.error(f"定期保存数据任务发生错误: {str(e)}")
