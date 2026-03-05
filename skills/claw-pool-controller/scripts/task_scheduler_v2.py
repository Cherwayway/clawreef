#!/usr/bin/env python3
"""
Claw Pool Controller - Advanced Task Scheduler v2 (Phase 2)

高级任务调度服务：
- 任务依赖关系管理 (DAG)
- 条件优先级调度
- 资源预留和批处理
- 智能重试和故障处理
- 调度性能分析

Usage:
    python task_scheduler_v2.py --start                    # 启动高级调度器
    python task_scheduler_v2.py --submit <task.json>       # 提交带依赖的任务
    python task_scheduler_v2.py --workflow <workflow.json> # 提交工作流
    python task_scheduler_v2.py --dependencies <task-id>   # 查看任务依赖图
    python task_scheduler_v2.py --analytics                # 调度性能分析
"""

import asyncio
import json
import argparse
import sqlite3
import uuid
import heapq
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum
import logging
import networkx as nx  # 用于依赖图分析
from dataclasses import dataclass, asdict

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    WAITING = "waiting"          # 等待依赖完成
    READY = "ready"              # 依赖已完成，等待调度
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"          # 因依赖失败被阻塞

class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5                 # 系统关键任务

class DependencyType(Enum):
    HARD = "hard"                # 强依赖：父任务必须成功完成
    SOFT = "soft"                # 软依赖：父任务完成即可（成功或失败）
    CONDITIONAL = "conditional"   # 条件依赖：基于条件判断

@dataclass
class TaskDependency:
    parent_task_id: str
    child_task_id: str
    dependency_type: DependencyType
    condition: Optional[str] = None  # 条件依赖的判断条件

@dataclass
class SchedulingContext:
    """调度上下文"""
    available_resources: Dict[str, int]
    resource_reservations: Dict[str, int]
    priority_boosts: Dict[str, float]
    batch_groups: Dict[str, List[str]]

class AdvancedTaskScheduler:
    def __init__(self, db_path: Optional[str] = None, registry_db_path: Optional[str] = None):
        self.db_path = db_path or self._get_default_db_path()
        self.registry_db_path = registry_db_path or self._get_registry_db_path()

        # 任务队列（支持多优先级）
        self.priority_queues = {priority: [] for priority in TaskPriority}
        self.active_tasks = {}
        self.task_assignments = {}

        # 依赖关系管理
        self.dependency_graph = nx.DiGraph()
        self.dependencies = {}  # task_id -> List[TaskDependency]
        self.waiting_tasks = set()  # 等待依赖的任务

        # 调度配置
        self.max_retries = 3
        self.task_timeout = 300
        self.scheduling_interval = 2  # 更频繁的调度检查
        self.batch_size_limit = 10

        # 调度统计
        self.scheduling_stats = {
            'total_scheduled': 0,
            'dependency_resolved': 0,
            'batch_scheduled': 0,
            'priority_boosts': 0
        }

        self.init_database()
        self.running = False

    def _get_default_db_path(self) -> str:
        """获取默认任务数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        return str(openclaw_dir / "pool_tasks_v2.db")

    def _get_registry_db_path(self) -> str:
        """获取注册表数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_registry.db")

    def init_database(self):
        """初始化高级任务数据库"""
        with sqlite3.connect(self.db_path) as conn:
            # 主任务表（扩展版）
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks_v2 (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'pending',
                    assigned_to TEXT,
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    assigned_time TIMESTAMP,
                    started_time TIMESTAMP,
                    completed_time TIMESTAMP,
                    result TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    timeout_seconds INTEGER DEFAULT 300,
                    required_capabilities TEXT,
                    required_resources TEXT,     -- JSON: {"cpu": 2, "memory": "4GB"}
                    estimated_duration INTEGER, -- 预估执行时间（秒）
                    actual_duration INTEGER,    -- 实际执行时间
                    user_id TEXT,
                    session_key TEXT,
                    batch_id TEXT,              -- 批次ID
                    workflow_id TEXT,           -- 工作流ID
                    tags TEXT,                  -- JSON数组：标签
                    scheduling_hints TEXT       -- JSON：调度提示
                )
            ''')

            # 任务依赖关系表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_task_id TEXT NOT NULL,
                    child_task_id TEXT NOT NULL,
                    dependency_type TEXT DEFAULT 'hard',
                    condition_expr TEXT,        -- 条件表达式
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_time TIMESTAMP,
                    UNIQUE(parent_task_id, child_task_id)
                )
            ''')

            # 工作流定义表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    definition TEXT NOT NULL,   -- JSON工作流定义
                    status TEXT DEFAULT 'active',
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 调度统计表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduling_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    queue_sizes TEXT,           -- JSON: 各优先级队列大小
                    scheduling_latency REAL,    -- 调度延迟
                    dependency_resolution_time REAL,
                    throughput INTEGER,         -- 吞吐量
                    resource_utilization TEXT  -- JSON: 资源利用率
                )
            ''')

            # 资源预留表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS resource_reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    reserved_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    released_time TIMESTAMP
                )
            ''')

            conn.commit()
        logger.info(f"高级任务数据库初始化完成: {self.db_path}")

    async def submit_task(self, task_data: Dict, dependencies: List[Dict] = None) -> str:
        """提交带依赖的任务"""
        task_id = task_data.get("id") or f"task_{uuid.uuid4().hex[:12]}"
        task_type = task_data.get("type", "general")
        content = task_data.get("content", "")
        metadata = task_data.get("metadata", {})
        priority = TaskPriority(metadata.get("priority", 2)).value

        logger.info(f"提交高级任务: {task_id} (类型: {task_type}, 依赖: {len(dependencies or [])})")

        try:
            with sqlite3.connect(self.db_path) as conn:
                # 保存任务
                conn.execute('''
                    INSERT INTO tasks_v2 (
                        task_id, task_type, content, metadata, priority,
                        timeout_seconds, required_capabilities, required_resources,
                        estimated_duration, max_retries, user_id, session_key,
                        batch_id, workflow_id, tags, scheduling_hints
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, task_type, content, json.dumps(metadata), priority,
                    metadata.get("timeout", self.task_timeout),
                    json.dumps(task_data.get("capabilities", [task_type])),
                    json.dumps(metadata.get("resources", {})),
                    metadata.get("estimatedDuration", 60),
                    metadata.get("maxRetries", self.max_retries),
                    metadata.get("userId"),
                    metadata.get("sessionKey"),
                    metadata.get("batchId"),
                    metadata.get("workflowId"),
                    json.dumps(metadata.get("tags", [])),
                    json.dumps(metadata.get("schedulingHints", {}))
                ))

                # 保存依赖关系
                if dependencies:
                    for dep in dependencies:
                        conn.execute('''
                            INSERT OR IGNORE INTO task_dependencies (
                                parent_task_id, child_task_id, dependency_type, condition_expr
                            ) VALUES (?, ?, ?, ?)
                        ''', (
                            dep["parentTaskId"],
                            task_id,
                            dep.get("type", "hard"),
                            dep.get("condition")
                        ))

                    # 更新依赖图
                    self._update_dependency_graph(task_id, dependencies)

                    # 检查是否有循环依赖
                    if self._has_circular_dependency():
                        conn.rollback()
                        raise ValueError("检测到循环依赖")

                conn.commit()

            # 添加到相应队列
            await self._enqueue_task(task_id, priority, dependencies)

            return task_id

        except Exception as e:
            logger.error(f"提交任务失败: {e}")
            raise

    async def submit_workflow(self, workflow_data: Dict) -> str:
        """提交工作流"""
        workflow_id = workflow_data.get("id") or f"workflow_{uuid.uuid4().hex[:8]}"
        name = workflow_data.get("name", "Unnamed Workflow")
        description = workflow_data.get("description", "")
        tasks = workflow_data.get("tasks", [])

        logger.info(f"提交工作流: {workflow_id} ({len(tasks)} 个任务)")

        try:
            with sqlite3.connect(self.db_path) as conn:
                # 保存工作流定义
                conn.execute('''
                    INSERT INTO workflows (workflow_id, name, description, definition)
                    VALUES (?, ?, ?, ?)
                ''', (workflow_id, name, description, json.dumps(workflow_data)))

                conn.commit()

            # 提交工作流中的所有任务
            task_ids = []
            for task in tasks:
                task["metadata"] = task.get("metadata", {})
                task["metadata"]["workflowId"] = workflow_id

                dependencies = task.get("dependencies", [])
                task_id = await self.submit_task(task, dependencies)
                task_ids.append(task_id)

            logger.info(f"工作流 {workflow_id} 提交完成，包含 {len(task_ids)} 个任务")
            return workflow_id

        except Exception as e:
            logger.error(f"提交工作流失败: {e}")
            raise

    async def _enqueue_task(self, task_id: str, priority: int, dependencies: List[Dict] = None):
        """将任务加入队列"""
        if dependencies:
            # 有依赖的任务进入等待状态
            self.waiting_tasks.add(task_id)
            await self._update_task_status(task_id, TaskStatus.WAITING)
            logger.debug(f"任务 {task_id} 进入等待状态（有 {len(dependencies)} 个依赖）")
        else:
            # 无依赖的任务直接进入就绪队列
            priority_enum = TaskPriority(priority)
            heapq.heappush(self.priority_queues[priority_enum], (
                datetime.now().timestamp(),
                task_id
            ))
            await self._update_task_status(task_id, TaskStatus.READY)
            logger.debug(f"任务 {task_id} 加入 {priority_enum.name} 优先级队列")

    async def schedule_tasks(self):
        """高级任务调度循环"""
        while self.running:
            try:
                start_time = datetime.now()

                # 1. 解析依赖关系，移动就绪任务到队列
                await self._resolve_dependencies()

                # 2. 执行优先级调度
                await self._priority_scheduling()

                # 3. 批处理调度
                await self._batch_scheduling()

                # 4. 更新调度统计
                scheduling_latency = (datetime.now() - start_time).total_seconds()
                await self._update_scheduling_metrics(scheduling_latency)

                await asyncio.sleep(self.scheduling_interval)

            except Exception as e:
                logger.error(f"调度循环出错: {e}")
                await asyncio.sleep(self.scheduling_interval)

    async def _resolve_dependencies(self):
        """解析并处理任务依赖关系"""
        if not self.waiting_tasks:
            return

        resolved_tasks = []

        for task_id in list(self.waiting_tasks):
            if await self._check_dependencies_resolved(task_id):
                resolved_tasks.append(task_id)
                self.waiting_tasks.discard(task_id)

        # 将已解析依赖的任务移到就绪队列
        for task_id in resolved_tasks:
            task = await self._get_task_from_db(task_id)
            if task:
                priority_enum = TaskPriority(task["priority"])
                heapq.heappush(self.priority_queues[priority_enum], (
                    datetime.now().timestamp(),
                    task_id
                ))
                await self._update_task_status(task_id, TaskStatus.READY)
                self.scheduling_stats['dependency_resolved'] += 1
                logger.info(f"依赖已解析，任务 {task_id} 进入就绪队列")

    async def _check_dependencies_resolved(self, task_id: str) -> bool:
        """检查任务的所有依赖是否已完成"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT parent_task_id, dependency_type, condition_expr
                    FROM task_dependencies
                    WHERE child_task_id = ?
                ''', (task_id,))

                dependencies = cursor.fetchall()

                for parent_id, dep_type, condition in dependencies:
                    parent_task = await self._get_task_from_db(parent_id)

                    if not parent_task:
                        continue

                    if dep_type == DependencyType.HARD.value:
                        if parent_task["status"] != TaskStatus.COMPLETED.value:
                            return False
                    elif dep_type == DependencyType.SOFT.value:
                        if parent_task["status"] not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
                            return False
                    elif dep_type == DependencyType.CONDITIONAL.value:
                        if not self._evaluate_condition(parent_task, condition):
                            return False

                return True

        except Exception as e:
            logger.error(f"检查依赖失败: {e}")
            return False

    def _evaluate_condition(self, parent_task: Dict, condition: str) -> bool:
        """评估条件依赖"""
        if not condition:
            return parent_task["status"] == TaskStatus.COMPLETED.value

        try:
            # 简单的条件评估（可以扩展为更复杂的表达式解析器）
            context = {
                "status": parent_task["status"],
                "result": json.loads(parent_task["result"] or "{}"),
                "duration": parent_task.get("actual_duration", 0)
            }

            # 支持基本的条件表达式
            return eval(condition, {"__builtins__": {}}, context)

        except Exception as e:
            logger.error(f"条件评估失败: {e}")
            return False

    async def _priority_scheduling(self):
        """优先级调度"""
        available_lobsters = await self._get_available_lobsters()
        if not available_lobsters:
            return

        scheduled_count = 0

        # 按优先级从高到低调度
        for priority in reversed(list(TaskPriority)):
            queue = self.priority_queues[priority]

            while queue and scheduled_count < len(available_lobsters):
                timestamp, task_id = heapq.heappop(queue)

                task = await self._get_task_from_db(task_id)
                if not task or task["status"] != TaskStatus.READY.value:
                    continue

                # 资源检查
                if not await self._check_resource_availability(task):
                    # 资源不足，放回队列
                    heapq.heappush(queue, (timestamp, task_id))
                    break

                # 寻找合适的龙虾
                suitable_lobster = await self._find_suitable_lobster(task, available_lobsters)
                if suitable_lobster:
                    await self._assign_task(task_id, suitable_lobster["deviceId"])
                    available_lobsters.remove(suitable_lobster)
                    scheduled_count += 1
                    self.scheduling_stats['total_scheduled'] += 1
                else:
                    heapq.heappush(queue, (timestamp, task_id))
                    break

        if scheduled_count > 0:
            logger.info(f"优先级调度完成，调度了 {scheduled_count} 个任务")

    async def _batch_scheduling(self):
        """批处理调度"""
        # 查找可批处理的任务组
        batch_groups = await self._identify_batch_groups()

        for batch_id, task_ids in batch_groups.items():
            if len(task_ids) >= 2:  # 至少2个任务才进行批处理
                await self._schedule_batch(batch_id, task_ids[:self.batch_size_limit])

    async def _identify_batch_groups(self) -> Dict[str, List[str]]:
        """识别可批处理的任务组"""
        batch_groups = defaultdict(list)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT task_id, batch_id, task_type, required_capabilities
                    FROM tasks_v2
                    WHERE status = 'ready' AND batch_id IS NOT NULL
                ''')

                for row in cursor.fetchall():
                    task_id, batch_id, task_type, capabilities = row
                    if batch_id:
                        batch_groups[batch_id].append(task_id)

        except Exception as e:
            logger.error(f"识别批处理组失败: {e}")

        return dict(batch_groups)

    async def _schedule_batch(self, batch_id: str, task_ids: List[str]):
        """调度批处理任务"""
        logger.info(f"调度批处理 {batch_id}，包含 {len(task_ids)} 个任务")

        # 为批处理预留资源
        available_lobsters = await self._get_available_lobsters()

        if len(available_lobsters) >= len(task_ids):
            # 有足够的龙虾，批量分配
            for i, task_id in enumerate(task_ids):
                task = await self._get_task_from_db(task_id)
                if task and i < len(available_lobsters):
                    await self._assign_task(task_id, available_lobsters[i]["deviceId"])

            self.scheduling_stats['batch_scheduled'] += len(task_ids)

    async def _check_resource_availability(self, task: Dict) -> bool:
        """检查任务所需资源是否可用"""
        required_resources = json.loads(task.get("required_resources") or "{}")
        if not required_resources:
            return True

        # 简单的资源检查逻辑
        # 实际应用中需要根据具体资源管理策略实现
        return True

    def _update_dependency_graph(self, task_id: str, dependencies: List[Dict]):
        """更新依赖图"""
        self.dependency_graph.add_node(task_id)
        for dep in dependencies:
            parent_id = dep["parentTaskId"]
            self.dependency_graph.add_edge(parent_id, task_id)

    def _has_circular_dependency(self) -> bool:
        """检测循环依赖"""
        try:
            list(nx.topological_sort(self.dependency_graph))
            return False
        except nx.NetworkXError:
            return True

    async def get_dependency_graph(self, task_id: str) -> Dict:
        """获取任务依赖图"""
        try:
            # 找出与指定任务相关的所有节点
            if task_id not in self.dependency_graph:
                return {"error": "任务不存在"}

            # 获取所有前置依赖
            predecessors = nx.ancestors(self.dependency_graph, task_id)
            # 获取所有后续任务
            successors = nx.descendants(self.dependency_graph, task_id)

            # 构建子图
            relevant_nodes = predecessors.union(successors).union({task_id})
            subgraph = self.dependency_graph.subgraph(relevant_nodes)

            return {
                "taskId": task_id,
                "nodes": list(relevant_nodes),
                "edges": list(subgraph.edges()),
                "dependencies": len(predecessors),
                "dependents": len(successors)
            }

        except Exception as e:
            logger.error(f"获取依赖图失败: {e}")
            return {"error": str(e)}

    async def _get_available_lobsters(self) -> List[Dict]:
        """获取可用的龙虾（复用基础版本逻辑）"""
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                cursor = conn.execute('''
                    SELECT device_id, display_name, capabilities, resources, status
                    FROM lobsters
                    WHERE status IN ('online', 'idle')
                ''')

                lobsters = []
                for row in cursor.fetchall():
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

    async def _find_suitable_lobster(self, task: Dict, available_lobsters: List[Dict]) -> Optional[Dict]:
        """寻找合适的龙虾（增强版）"""
        required_capabilities = json.loads(task.get("required_capabilities", "[]"))

        suitable_lobsters = []
        for lobster in available_lobsters:
            lobster_capabilities = lobster.get("capabilities", [])

            if all(cap in lobster_capabilities for cap in required_capabilities):
                suitable_lobsters.append(lobster)

        if not suitable_lobsters:
            return None

        # 使用负载均衡器选择最佳龙虾
        import random
        return random.choice(suitable_lobsters)

    async def _assign_task(self, task_id: str, device_id: str):
        """分配任务（增强版）"""
        logger.info(f"分配任务 {task_id} 给龙虾 {device_id}")

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE tasks_v2
                    SET status = ?, assigned_to = ?, assigned_time = ?
                    WHERE task_id = ?
                ''', (
                    TaskStatus.ASSIGNED.value,
                    device_id,
                    datetime.now().isoformat(),
                    task_id
                ))
                conn.commit()

            self.task_assignments[task_id] = device_id

        except Exception as e:
            logger.error(f"分配任务失败: {e}")

    async def _update_task_status(self, task_id: str, status: TaskStatus):
        """更新任务状态"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE tasks_v2 SET status = ? WHERE task_id = ?
                ''', (status.value, task_id))
                conn.commit()
        except Exception as e:
            logger.error(f"更新任务状态失败: {e}")

    async def _get_task_from_db(self, task_id: str) -> Optional[Dict]:
        """从数据库获取任务信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT * FROM tasks_v2 WHERE task_id = ?', (task_id,)
                )
                row = cursor.fetchone()

                if row:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None

    async def _update_scheduling_metrics(self, scheduling_latency: float):
        """更新调度指标"""
        try:
            queue_sizes = {
                priority.name: len(queue)
                for priority, queue in self.priority_queues.items()
            }

            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO scheduling_metrics (
                        queue_sizes, scheduling_latency, throughput
                    ) VALUES (?, ?, ?)
                ''', (
                    json.dumps(queue_sizes),
                    scheduling_latency,
                    self.scheduling_stats['total_scheduled']
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"更新调度指标失败: {e}")

    def get_scheduling_analytics(self) -> Dict:
        """获取调度分析数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 队列状态
                queue_status = {
                    priority.name: len(queue)
                    for priority, queue in self.priority_queues.items()
                }

                # 最近调度统计
                cursor = conn.execute('''
                    SELECT AVG(scheduling_latency), AVG(throughput)
                    FROM scheduling_metrics
                    WHERE metric_time > datetime('now', '-1 hour')
                ''')
                row = cursor.fetchone()
                avg_latency, avg_throughput = row or (0, 0)

                # 依赖解析统计
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM task_dependencies
                    WHERE resolved_time IS NOT NULL
                ''')
                resolved_deps = cursor.fetchone()[0]

                return {
                    "queueStatus": queue_status,
                    "waitingTasks": len(self.waiting_tasks),
                    "schedulingStats": self.scheduling_stats,
                    "performance": {
                        "avgSchedulingLatency": avg_latency,
                        "avgThroughput": avg_throughput,
                        "resolvedDependencies": resolved_deps
                    }
                }

        except Exception as e:
            logger.error(f"获取调度分析失败: {e}")
            return {"error": str(e)}

    async def start(self):
        """启动高级调度器"""
        logger.info("启动高级任务调度器...")
        self.running = True

        # 恢复等待任务和依赖图
        await self._restore_state()

        # 启动调度循环
        await self.schedule_tasks()

    async def stop(self):
        """停止调度器"""
        logger.info("停止高级任务调度器...")
        self.running = False

    async def _restore_state(self):
        """恢复调度器状态"""
        with sqlite3.connect(self.db_path) as conn:
            # 恢复依赖图
            cursor = conn.execute('''
                SELECT parent_task_id, child_task_id FROM task_dependencies
            ''')
            for parent_id, child_id in cursor.fetchall():
                self.dependency_graph.add_edge(parent_id, child_id)

            # 恢复等待任务
            cursor = conn.execute('''
                SELECT task_id FROM tasks_v2 WHERE status = 'waiting'
            ''')
            for (task_id,) in cursor.fetchall():
                self.waiting_tasks.add(task_id)

            # 恢复就绪队列
            cursor = conn.execute('''
                SELECT task_id, priority, created_time FROM tasks_v2
                WHERE status = 'ready'
            ''')
            for task_id, priority, created_time in cursor.fetchall():
                priority_enum = TaskPriority(priority)
                timestamp = datetime.fromisoformat(created_time).timestamp()
                heapq.heappush(self.priority_queues[priority_enum], (timestamp, task_id))

        logger.info("调度器状态恢复完成")

def load_task_from_file(filename: str) -> Dict:
    """从文件加载任务"""
    with open(filename, 'r') as f:
        return json.load(f)

def print_dependency_graph(scheduler: AdvancedTaskScheduler, task_id: str):
    """打印任务依赖图"""
    import asyncio
    graph = asyncio.run(scheduler.get_dependency_graph(task_id))

    if "error" in graph:
        print(f"❌ 获取依赖图失败: {graph['error']}")
        return

    print(f"🔗 任务依赖图: {task_id}")
    print(f"   相关节点: {len(graph['nodes'])}")
    print(f"   依赖任务: {graph['dependencies']}")
    print(f"   被依赖: {graph['dependents']}")

    if graph['edges']:
        print("\n📊 依赖关系:")
        for parent, child in graph['edges']:
            print(f"   {parent} → {child}")

def print_scheduling_analytics(scheduler: AdvancedTaskScheduler):
    """打印调度分析"""
    analytics = scheduler.get_scheduling_analytics()

    if "error" in analytics:
        print(f"❌ 获取分析数据失败: {analytics['error']}")
        return

    print("📈 调度性能分析")
    print(f"   等待依赖的任务: {analytics['waitingTasks']}")

    print("\n📋 队列状态:")
    for priority, count in analytics['queueStatus'].items():
        if count > 0:
            print(f"   {priority}: {count}")

    print("\n📊 调度统计:")
    stats = analytics['schedulingStats']
    for key, value in stats.items():
        print(f"   {key}: {value}")

    perf = analytics['performance']
    print(f"\n⚡ 性能指标:")
    print(f"   平均调度延迟: {perf['avgSchedulingLatency']:.3f}s")
    print(f"   平均吞吐量: {perf['avgThroughput']:.1f}")
    print(f"   已解析依赖: {perf['resolvedDependencies']}")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Advanced Task Scheduler v2')
    parser.add_argument('--start', action='store_true',
                       help='启动高级调度器')
    parser.add_argument('--submit', type=str,
                       help='提交任务文件')
    parser.add_argument('--workflow', type=str,
                       help='提交工作流文件')
    parser.add_argument('--dependencies', type=str,
                       help='查看任务依赖图')
    parser.add_argument('--analytics', action='store_true',
                       help='显示调度性能分析')
    parser.add_argument('--db-path', type=str,
                       help='任务数据库路径')

    args = parser.parse_args()

    scheduler = AdvancedTaskScheduler(args.db_path)

    if args.submit:
        try:
            task_data = load_task_from_file(args.submit)
            dependencies = task_data.pop("dependencies", [])
            task_id = await scheduler.submit_task(task_data, dependencies)
            print(f"✅ 高级任务已提交: {task_id}")
        except Exception as e:
            print(f"❌ 提交任务失败: {e}")

    elif args.workflow:
        try:
            workflow_data = load_task_from_file(args.workflow)
            workflow_id = await scheduler.submit_workflow(workflow_data)
            print(f"✅ 工作流已提交: {workflow_id}")
        except Exception as e:
            print(f"❌ 提交工作流失败: {e}")

    elif args.dependencies:
        print_dependency_graph(scheduler, args.dependencies)

    elif args.analytics:
        print_scheduling_analytics(scheduler)

    elif args.start:
        try:
            await scheduler.start()
        except KeyboardInterrupt:
            print("\n用户中断，停止调度器")
            await scheduler.stop()

    else:
        print("请指定操作：--start, --submit, --workflow, --dependencies, 或 --analytics")

if __name__ == '__main__':
    asyncio.run(main())