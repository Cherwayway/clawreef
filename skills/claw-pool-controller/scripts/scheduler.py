#!/usr/bin/env python3
"""
Claw Pool Controller - Task Scheduler

任务调度服务：
- 接收用户任务请求
- 基于能力和负载的智能匹配
- 任务队列管理和优先级调度
- 超时处理和故障转移

Usage:
    python scheduler.py --start                # 启动调度器
    python scheduler.py --submit <task.json>   # 提交新任务
    python scheduler.py --queue                # 查看任务队列
    python scheduler.py --cancel <task-id>     # 取消任务
"""

import asyncio
import json
import argparse
import sqlite3
import uuid
import heapq
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class TaskScheduler:
    def __init__(self, db_path: Optional[str] = None, registry_db_path: Optional[str] = None):
        self.db_path = db_path or self._get_default_db_path()
        self.registry_db_path = registry_db_path or self._get_registry_db_path()

        # 任务队列（优先级队列）
        self.task_queue = []  # (priority, timestamp, task_id)
        self.active_tasks = {}  # task_id -> task_info
        self.task_assignments = {}  # task_id -> device_id

        # 调度配置
        self.max_retries = 3
        self.task_timeout = 300  # 默认5分钟超时
        self.scheduling_interval = 5  # 每5秒执行一次调度

        self.init_database()
        self.running = False

    def _get_default_db_path(self) -> str:
        """获取默认任务数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        return str(openclaw_dir / "pool_tasks.db")

    def _get_registry_db_path(self) -> str:
        """获取注册表数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_registry.db")

    def init_database(self):
        """初始化任务数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,            -- JSON
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'pending',
                    assigned_to TEXT,         -- device_id
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    assigned_time TIMESTAMP,
                    started_time TIMESTAMP,
                    completed_time TIMESTAMP,
                    result TEXT,              -- JSON
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    timeout_seconds INTEGER DEFAULT 300,
                    required_capabilities TEXT, -- JSON array
                    user_id TEXT,
                    session_key TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    action TEXT,  -- 'created', 'assigned', 'started', 'completed', 'failed', 'cancelled'
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT  -- JSON
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduling_stats (
                    date TEXT PRIMARY KEY,
                    total_tasks INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    failed_tasks INTEGER DEFAULT 0,
                    cancelled_tasks INTEGER DEFAULT 0,
                    avg_execution_time REAL DEFAULT 0,
                    peak_queue_size INTEGER DEFAULT 0
                )
            ''')

            conn.commit()
        logger.info(f"任务数据库初始化完成: {self.db_path}")

    async def submit_task(self, task_data: Dict) -> str:
        """提交新任务"""
        task_id = task_data.get("id") or f"task_{uuid.uuid4().hex[:12]}"
        task_type = task_data.get("type", "general")
        content = task_data.get("content", "")
        metadata = task_data.get("metadata", {})
        priority = TaskPriority(metadata.get("priority", 2)).value
        required_capabilities = task_data.get("capabilities", [task_type])

        logger.info(f"提交新任务: {task_id} (类型: {task_type}, 优先级: {priority})")

        try:
            # 保存到数据库
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO tasks (
                        task_id, task_type, content, metadata, priority,
                        timeout_seconds, required_capabilities, user_id, session_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, task_type, content, json.dumps(metadata), priority,
                    metadata.get("timeout", self.task_timeout),
                    json.dumps(required_capabilities),
                    metadata.get("userId"),
                    metadata.get("sessionKey")
                ))
                conn.commit()

            # 添加到队列
            heapq.heappush(self.task_queue, (
                -priority,  # 负数使得高优先级排在前面
                datetime.now().timestamp(),
                task_id
            ))

            # 记录历史
            self._record_task_history(task_id, "created", {"priority": priority})

            logger.info(f"任务 {task_id} 已加入队列")
            return task_id

        except Exception as e:
            logger.error(f"提交任务失败: {e}")
            raise

    async def schedule_tasks(self):
        """执行任务调度"""
        while self.running:
            try:
                await self._schedule_round()
                await asyncio.sleep(self.scheduling_interval)
            except Exception as e:
                logger.error(f"调度循环出错: {e}")
                await asyncio.sleep(self.scheduling_interval)

    async def _schedule_round(self):
        """执行一轮调度"""
        if not self.task_queue:
            return

        # 获取可用的龙虾
        available_lobsters = self._get_available_lobsters()
        if not available_lobsters:
            logger.debug("没有可用的龙虾")
            return

        # 处理队列中的任务
        scheduled_count = 0
        max_schedules_per_round = min(len(available_lobsters), len(self.task_queue))

        while self.task_queue and scheduled_count < max_schedules_per_round:
            try:
                priority, timestamp, task_id = heapq.heappop(self.task_queue)

                # 获取任务详细信息
                task = self._get_task_from_db(task_id)
                if not task:
                    logger.warning(f"任务 {task_id} 不存在，跳过")
                    continue

                if task["status"] != TaskStatus.PENDING.value:
                    logger.debug(f"任务 {task_id} 状态不是 pending，跳过")
                    continue

                # 查找合适的龙虾
                suitable_lobster = self._find_suitable_lobster(task, available_lobsters)
                if suitable_lobster:
                    await self._assign_task(task_id, suitable_lobster["deviceId"])
                    available_lobsters.remove(suitable_lobster)
                    scheduled_count += 1
                else:
                    # 没找到合适的龙虾，放回队列
                    heapq.heappush(self.task_queue, (priority, timestamp, task_id))
                    break

            except Exception as e:
                logger.error(f"调度任务时出错: {e}")

        if scheduled_count > 0:
            logger.info(f"本轮调度了 {scheduled_count} 个任务")

    def _get_available_lobsters(self) -> List[Dict]:
        """获取可用的龙虾"""
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                cursor = conn.execute('''
                    SELECT device_id, display_name, capabilities, resources, status
                    FROM lobsters
                    WHERE status IN ('online', 'idle')
                ''')

                lobsters = []
                for row in cursor.fetchall():
                    # 检查龙虾是否正在执行任务
                    if row[0] not in self.task_assignments.values():
                        lobsters.append({
                            "deviceId": row[0],
                            "displayName": row[1],
                            "capabilities": json.loads(row[2]) if row[2] else [],
                            "resources": json.loads(row[3]) if row[3] else {},
                            "status": row[4]
                        })

                return lobsters

        except Exception as e:
            logger.error(f"获取可用龙虾失败: {e}")
            return []

    def _find_suitable_lobster(self, task: Dict, available_lobsters: List[Dict]) -> Optional[Dict]:
        """为任务找到合适的龙虾"""
        required_capabilities = json.loads(task.get("required_capabilities", "[]"))

        # 筛选符合能力要求的龙虾
        suitable_lobsters = []
        for lobster in available_lobsters:
            lobster_capabilities = lobster.get("capabilities", [])

            # 检查能力匹配
            if all(cap in lobster_capabilities for cap in required_capabilities):
                suitable_lobsters.append(lobster)

        if not suitable_lobsters:
            return None

        # 根据负载均衡策略选择龙虾
        return self._select_best_lobster(suitable_lobsters, task)

    def _select_best_lobster(self, lobsters: List[Dict], task: Dict) -> Dict:
        """根据负载均衡策略选择最佳龙虾"""
        # 简单策略：随机选择
        # TODO: 实现更复杂的负载均衡算法
        import random
        return random.choice(lobsters)

    async def _assign_task(self, task_id: str, device_id: str):
        """分配任务给指定龙虾"""
        logger.info(f"分配任务 {task_id} 给龙虾 {device_id}")

        try:
            # 更新数据库
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE tasks
                    SET status = ?, assigned_to = ?, assigned_time = ?
                    WHERE task_id = ?
                ''', (
                    TaskStatus.ASSIGNED.value,
                    device_id,
                    datetime.now().isoformat(),
                    task_id
                ))
                conn.commit()

            # 更新内存状态
            self.task_assignments[task_id] = device_id

            # 记录历史
            self._record_task_history(task_id, "assigned", {"deviceId": device_id})

            # TODO: 通过 WebSocket 发送任务给龙虾
            # await self._send_task_to_lobster(task_id, device_id)

        except Exception as e:
            logger.error(f"分配任务失败: {e}")
            # 任务分配失败，放回队列
            task = self._get_task_from_db(task_id)
            if task:
                heapq.heappush(self.task_queue, (
                    -task["priority"],
                    datetime.now().timestamp(),
                    task_id
                ))

    async def handle_task_result(self, task_id: str, result_data: Dict):
        """处理任务执行结果"""
        status = result_data.get("status", TaskStatus.FAILED.value)
        result = result_data.get("result")
        error = result_data.get("error")
        duration = result_data.get("duration", 0)

        logger.info(f"任务 {task_id} 执行完成，状态: {status}")

        try:
            # 更新数据库
            with sqlite3.connect(self.db_path) as conn:
                if status == TaskStatus.COMPLETED.value:
                    conn.execute('''
                        UPDATE tasks
                        SET status = ?, result = ?, completed_time = ?
                        WHERE task_id = ?
                    ''', (
                        status,
                        json.dumps(result) if result else None,
                        datetime.now().isoformat(),
                        task_id
                    ))
                else:
                    conn.execute('''
                        UPDATE tasks
                        SET status = ?, error_message = ?, completed_time = ?
                        WHERE task_id = ?
                    ''', (
                        status,
                        error,
                        datetime.now().isoformat(),
                        task_id
                    ))
                conn.commit()

            # 清理内存状态
            self.active_tasks.pop(task_id, None)
            self.task_assignments.pop(task_id, None)

            # 记录历史
            self._record_task_history(task_id, status, {
                "duration": duration,
                "hasResult": result is not None,
                "hasError": error is not None
            })

        except Exception as e:
            logger.error(f"处理任务结果失败: {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定任务"""
        logger.info(f"取消任务: {task_id}")

        try:
            # 更新数据库状态
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT status FROM tasks WHERE task_id = ?', (task_id,)
                )
                row = cursor.fetchone()

                if not row:
                    logger.warning(f"任务 {task_id} 不存在")
                    return False

                current_status = row[0]
                if current_status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                    logger.warning(f"任务 {task_id} 已完成或已取消")
                    return False

                # 更新状态为已取消
                conn.execute('''
                    UPDATE tasks SET status = ?, completed_time = ?
                    WHERE task_id = ?
                ''', (TaskStatus.CANCELLED.value, datetime.now().isoformat(), task_id))
                conn.commit()

            # 从队列中移除（如果还在队列中）
            self.task_queue = [(p, t, tid) for p, t, tid in self.task_queue if tid != task_id]
            heapq.heapify(self.task_queue)

            # 清理内存状态
            self.active_tasks.pop(task_id, None)
            self.task_assignments.pop(task_id, None)

            # TODO: 如果任务正在执行，通知龙虾取消

            # 记录历史
            self._record_task_history(task_id, "cancelled", {})

            return True

        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False

    def _get_task_from_db(self, task_id: str) -> Optional[Dict]:
        """从数据库获取任务信息"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT * FROM tasks WHERE task_id = ?', (task_id,)
            )
            row = cursor.fetchone()

            if row:
                return {
                    "task_id": row[0],
                    "task_type": row[1],
                    "content": row[2],
                    "metadata": json.loads(row[3]) if row[3] else {},
                    "priority": row[4],
                    "status": row[5],
                    "assigned_to": row[6],
                    "created_time": row[7],
                    "assigned_time": row[8],
                    "started_time": row[9],
                    "completed_time": row[10],
                    "result": json.loads(row[11]) if row[11] else None,
                    "error_message": row[12],
                    "retry_count": row[13],
                    "timeout_seconds": row[14],
                    "required_capabilities": row[15],
                    "user_id": row[16],
                    "session_key": row[17]
                }
            return None

    def _record_task_history(self, task_id: str, action: str, details: Dict):
        """记录任务历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO task_history (task_id, action, details)
                    VALUES (?, ?, ?)
                ''', (task_id, action, json.dumps(details)))
                conn.commit()
        except Exception as e:
            logger.error(f"记录任务历史失败: {e}")

    def get_task_queue_status(self) -> Dict:
        """获取任务队列状态"""
        with sqlite3.connect(self.db_path) as conn:
            # 统计各状态任务数量
            cursor = conn.execute('''
                SELECT status, COUNT(*) FROM tasks GROUP BY status
            ''')
            status_counts = dict(cursor.fetchall())

            # 队列中待调度任务
            pending_count = len(self.task_queue)

            # 正在执行的任务
            running_count = len(self.active_tasks)

            return {
                "queueSize": pending_count,
                "runningTasks": running_count,
                "statusCounts": status_counts,
                "totalTasks": sum(status_counts.values()),
                "availableLobsters": len(self._get_available_lobsters())
            }

    def get_recent_tasks(self, limit: int = 20) -> List[Dict]:
        """获取最近的任务"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT task_id, task_type, status, priority, created_time,
                       assigned_time, completed_time, assigned_to
                FROM tasks
                ORDER BY created_time DESC
                LIMIT ?
            ''', (limit,))

            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "taskId": row[0],
                    "taskType": row[1],
                    "status": row[2],
                    "priority": row[3],
                    "createdTime": row[4],
                    "assignedTime": row[5],
                    "completedTime": row[6],
                    "assignedTo": row[7]
                })

            return tasks

    async def start(self):
        """启动调度器"""
        logger.info("启动任务调度器...")
        self.running = True

        # 从数据库恢复待调度任务到队列
        await self._restore_pending_tasks()

        # 启动调度循环
        await self.schedule_tasks()

    async def stop(self):
        """停止调度器"""
        logger.info("停止任务调度器...")
        self.running = False

    async def _restore_pending_tasks(self):
        """从数据库恢复待调度任务"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT task_id, priority, created_time
                FROM tasks
                WHERE status = 'pending'
                ORDER BY priority DESC, created_time ASC
            ''')

            restored_count = 0
            for row in cursor.fetchall():
                task_id, priority, created_time = row
                timestamp = datetime.fromisoformat(created_time).timestamp()

                heapq.heappush(self.task_queue, (-priority, timestamp, task_id))
                restored_count += 1

        if restored_count > 0:
            logger.info(f"从数据库恢复了 {restored_count} 个待调度任务")

def load_task_from_file(filename: str) -> Dict:
    """从文件加载任务"""
    with open(filename, 'r') as f:
        return json.load(f)

def print_queue_status(scheduler: TaskScheduler):
    """打印队列状态"""
    status = scheduler.get_task_queue_status()

    print("📋 Task Queue Status")
    print(f"   队列中任务: {status['queueSize']}")
    print(f"   执行中任务: {status['runningTasks']}")
    print(f"   可用龙虾: {status['availableLobsters']}")
    print(f"   总任务数: {status['totalTasks']}")

    print("\n📊 任务状态分布:")
    for status_name, count in status['statusCounts'].items():
        print(f"   {status_name}: {count}")

def print_recent_tasks(scheduler: TaskScheduler):
    """打印最近任务"""
    tasks = scheduler.get_recent_tasks(10)

    if not tasks:
        print("❌ 没有任务记录")
        return

    print(f"📝 最近任务 (最新 {len(tasks)} 个):\n")

    for i, task in enumerate(tasks, 1):
        status_icon = {
            "pending": "⏳",
            "assigned": "📤",
            "running": "⚡",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫"
        }.get(task["status"], "❓")

        print(f"{i}. {status_icon} {task['taskId']}")
        print(f"   类型: {task['taskType']}")
        print(f"   状态: {task['status']}")
        print(f"   优先级: {task['priority']}")
        print(f"   创建时间: {task['createdTime']}")

        if task['assignedTo']:
            print(f"   分配给: {task['assignedTo']}")
        if task['completedTime']:
            print(f"   完成时间: {task['completedTime']}")
        print()

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Task Scheduler')
    parser.add_argument('--start', action='store_true',
                       help='启动调度器')
    parser.add_argument('--submit', type=str,
                       help='提交任务文件')
    parser.add_argument('--queue', action='store_true',
                       help='查看队列状态')
    parser.add_argument('--tasks', action='store_true',
                       help='查看最近任务')
    parser.add_argument('--cancel', type=str,
                       help='取消指定任务')
    parser.add_argument('--db-path', type=str,
                       help='任务数据库路径')

    args = parser.parse_args()

    scheduler = TaskScheduler(args.db_path)

    if args.submit:
        try:
            task_data = load_task_from_file(args.submit)
            task_id = await scheduler.submit_task(task_data)
            print(f"✅ 任务已提交: {task_id}")
        except FileNotFoundError:
            print(f"❌ 任务文件未找到: {args.submit}")
        except Exception as e:
            print(f"❌ 提交任务失败: {e}")

    elif args.queue:
        print_queue_status(scheduler)

    elif args.tasks:
        print_recent_tasks(scheduler)

    elif args.cancel:
        success = await scheduler.cancel_task(args.cancel)
        print("✅ 任务已取消" if success else "❌ 取消任务失败")

    elif args.start:
        try:
            await scheduler.start()
        except KeyboardInterrupt:
            print("\n用户中断，停止调度器")
            await scheduler.stop()

    else:
        print("请指定操作：--start, --submit, --queue, --tasks, 或 --cancel")

if __name__ == '__main__':
    asyncio.run(main())