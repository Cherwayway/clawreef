#!/usr/bin/env python3
"""
Claw Pool Controller - Monitor Service

监控服务：
- 实时龙虾状态监控
- 任务执行统计和性能指标
- 系统健康度评估
- 告警通知和事件推送

Usage:
    python monitor.py --start                # 启动监控服务
    python monitor.py --status               # 查看实时状态
    python monitor.py --lobster <device-id>  # 查看龙虾详情
    python monitor.py --report               # 生成状态报告
"""

import asyncio
import json
import argparse
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PoolMonitor:
    def __init__(self, registry_db_path: Optional[str] = None, tasks_db_path: Optional[str] = None):
        self.registry_db_path = registry_db_path or self._get_registry_db_path()
        self.tasks_db_path = tasks_db_path or self._get_tasks_db_path()
        self.running = False
        self.monitoring_interval = 10  # 每10秒检查一次

        # 告警阈值
        self.thresholds = {
            "lobster_offline_minutes": 5,
            "task_queue_size": 50,
            "task_failure_rate": 0.2,
            "avg_execution_time_minutes": 10
        }

        # 告警历史
        self.alert_history = []

    def _get_registry_db_path(self) -> str:
        """获取注册表数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_registry.db")

    def _get_tasks_db_path(self) -> str:
        """获取任务数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_tasks.db")

    def get_pool_overview(self) -> Dict:
        """获取池的总体概览"""
        try:
            # 龙虾统计
            lobster_stats = self._get_lobster_statistics()

            # 任务统计
            task_stats = self._get_task_statistics()

            # 性能指标
            performance_stats = self._get_performance_statistics()

            # 健康度评估
            health_score = self._calculate_health_score(lobster_stats, task_stats, performance_stats)

            return {
                "timestamp": datetime.now().isoformat(),
                "lobsters": lobster_stats,
                "tasks": task_stats,
                "performance": performance_stats,
                "health": {
                    "score": health_score,
                    "status": self._get_health_status(health_score)
                }
            }

        except Exception as e:
            logger.error(f"获取池概览失败: {e}")
            return {"error": str(e)}

    def _get_lobster_statistics(self) -> Dict:
        """获取龙虾统计信息"""
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                # 总体数量
                cursor = conn.execute('SELECT COUNT(*) FROM lobsters')
                total_lobsters = cursor.fetchone()[0]

                # 按状态统计
                cursor = conn.execute('''
                    SELECT status, COUNT(*) FROM lobsters GROUP BY status
                ''')
                status_counts = dict(cursor.fetchall())

                # 在线龙虾详情
                cursor = conn.execute('''
                    SELECT device_id, display_name, capabilities, last_heartbeat, status
                    FROM lobsters
                    WHERE status IN ('online', 'idle', 'busy')
                    ORDER BY last_heartbeat DESC
                ''')

                online_lobsters = []
                for row in cursor.fetchall():
                    capabilities = json.loads(row[2]) if row[2] else []
                    last_heartbeat = row[3]

                    # 计算上次心跳距离现在的时间
                    heartbeat_lag = None
                    if last_heartbeat:
                        heartbeat_time = datetime.fromisoformat(last_heartbeat)
                        heartbeat_lag = (datetime.now() - heartbeat_time).total_seconds()

                    online_lobsters.append({
                        "deviceId": row[0],
                        "displayName": row[1],
                        "capabilities": capabilities,
                        "status": row[4],
                        "heartbeatLag": heartbeat_lag
                    })

                return {
                    "total": total_lobsters,
                    "statusCounts": status_counts,
                    "online": online_lobsters,
                    "onlineCount": len(online_lobsters)
                }

        except Exception as e:
            logger.error(f"获取龙虾统计失败: {e}")
            return {}

    def _get_task_statistics(self) -> Dict:
        """获取任务统计信息"""
        try:
            with sqlite3.connect(self.tasks_db_path) as conn:
                # 总体统计
                cursor = conn.execute('SELECT COUNT(*) FROM tasks')
                total_tasks = cursor.fetchone()[0]

                # 按状态统计
                cursor = conn.execute('''
                    SELECT status, COUNT(*) FROM tasks GROUP BY status
                ''')
                status_counts = dict(cursor.fetchall())

                # 最近24小时统计
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM tasks
                    WHERE created_time > datetime('now', '-24 hours')
                ''')
                tasks_24h = cursor.fetchone()[0]

                # 当前队列大小（pending + assigned 状态）
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM tasks
                    WHERE status IN ('pending', 'assigned')
                ''')
                queue_size = cursor.fetchone()[0]

                # 最近完成的任务
                cursor = conn.execute('''
                    SELECT task_id, task_type, status, created_time,
                           completed_time, assigned_to
                    FROM tasks
                    WHERE completed_time IS NOT NULL
                    ORDER BY completed_time DESC
                    LIMIT 10
                ''')

                recent_completed = []
                for row in cursor.fetchall():
                    duration = None
                    if row[3] and row[4]:  # created_time and completed_time
                        created = datetime.fromisoformat(row[3])
                        completed = datetime.fromisoformat(row[4])
                        duration = (completed - created).total_seconds()

                    recent_completed.append({
                        "taskId": row[0],
                        "taskType": row[1],
                        "status": row[2],
                        "duration": duration,
                        "assignedTo": row[5]
                    })

                return {
                    "total": total_tasks,
                    "statusCounts": status_counts,
                    "last24Hours": tasks_24h,
                    "queueSize": queue_size,
                    "recentCompleted": recent_completed
                }

        except Exception as e:
            logger.error(f"获取任务统计失败: {e}")
            return {}

    def _get_performance_statistics(self) -> Dict:
        """获取性能统计信息"""
        try:
            with sqlite3.connect(self.tasks_db_path) as conn:
                # 平均执行时间
                cursor = conn.execute('''
                    SELECT AVG(
                        CAST((julianday(completed_time) - julianday(created_time)) * 86400 AS INTEGER)
                    ) as avg_duration
                    FROM tasks
                    WHERE status = 'completed'
                    AND completed_time IS NOT NULL
                    AND created_time IS NOT NULL
                    AND datetime(completed_time) > datetime('now', '-24 hours')
                ''')
                row = cursor.fetchone()
                avg_execution_time = row[0] if row[0] else 0

                # 成功率（最近24小时）
                cursor = conn.execute('''
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
                    FROM tasks
                    WHERE created_time > datetime('now', '-24 hours')
                    AND status IN ('completed', 'failed', 'cancelled')
                ''')
                row = cursor.fetchone()
                total_finished = row[0] if row[0] else 0
                completed_count = row[1] if row[1] else 0
                success_rate = completed_count / total_finished if total_finished > 0 else 0

                # 吞吐量（最近1小时每分钟完成的任务数）
                cursor = conn.execute('''
                    SELECT COUNT(*) / 60.0 as throughput
                    FROM tasks
                    WHERE status = 'completed'
                    AND completed_time > datetime('now', '-1 hour')
                ''')
                row = cursor.fetchone()
                throughput = row[0] if row[0] else 0

                return {
                    "avgExecutionTime": avg_execution_time,
                    "successRate": success_rate,
                    "throughput": throughput,
                    "failureRate": 1 - success_rate if total_finished > 0 else 0
                }

        except Exception as e:
            logger.error(f"获取性能统计失败: {e}")
            return {}

    def _calculate_health_score(self, lobster_stats: Dict, task_stats: Dict, perf_stats: Dict) -> float:
        """计算系统健康度分数 (0-100)"""
        try:
            score = 100.0

            # 龙虾健康度 (权重: 30%)
            lobster_health = 0
            if lobster_stats.get("total", 0) > 0:
                online_ratio = lobster_stats.get("onlineCount", 0) / lobster_stats["total"]
                lobster_health = online_ratio * 30
            score *= (lobster_health + 70) / 100

            # 任务队列健康度 (权重: 25%)
            queue_size = task_stats.get("queueSize", 0)
            if queue_size > self.thresholds["task_queue_size"]:
                score *= 0.75  # 队列积压扣分

            # 任务成功率 (权重: 30%)
            success_rate = perf_stats.get("successRate", 1.0)
            score *= success_rate

            # 平均执行时间 (权重: 15%)
            avg_time = perf_stats.get("avgExecutionTime", 0) / 60  # 转换为分钟
            if avg_time > self.thresholds["avg_execution_time_minutes"]:
                score *= 0.85  # 执行时间过长扣分

            return max(0, min(100, score))

        except Exception as e:
            logger.error(f"计算健康度分数失败: {e}")
            return 50.0  # 默认中等健康度

    def _get_health_status(self, score: float) -> str:
        """根据分数获取健康状态"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        elif score >= 40:
            return "poor"
        else:
            return "critical"

    def get_lobster_details(self, device_id: str) -> Optional[Dict]:
        """获取指定龙虾的详细信息"""
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                cursor = conn.execute('''
                    SELECT * FROM lobsters WHERE device_id = ?
                ''', (device_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                lobster_info = {
                    "deviceId": row[0],
                    "displayName": row[1],
                    "capabilities": json.loads(row[2]) if row[2] else [],
                    "resources": json.loads(row[3]) if row[3] else {},
                    "status": row[4],
                    "registrationTime": row[5],
                    "lastHeartbeat": row[6],
                    "lastSeen": row[7],
                    "location": json.loads(row[8]) if row[8] else {},
                    "pricing": json.loads(row[9]) if row[9] else {},
                    "owner": row[10],
                    "platform": json.loads(row[11]) if row[11] else {},
                    "openclawVersion": row[12]
                }

            # 获取该龙虾的任务执行历史
            with sqlite3.connect(self.tasks_db_path) as conn:
                cursor = conn.execute('''
                    SELECT task_id, task_type, status, created_time,
                           assigned_time, completed_time
                    FROM tasks
                    WHERE assigned_to = ?
                    ORDER BY created_time DESC
                    LIMIT 20
                ''', (device_id,))

                task_history = []
                for row in cursor.fetchall():
                    task_history.append({
                        "taskId": row[0],
                        "taskType": row[1],
                        "status": row[2],
                        "createdTime": row[3],
                        "assignedTime": row[4],
                        "completedTime": row[5]
                    })

                lobster_info["taskHistory"] = task_history

            return lobster_info

        except Exception as e:
            logger.error(f"获取龙虾详情失败 {device_id}: {e}")
            return None

    async def check_alerts(self):
        """检查告警条件"""
        try:
            overview = self.get_pool_overview()

            alerts = []

            # 检查离线龙虾
            for lobster in overview.get("lobsters", {}).get("online", []):
                heartbeat_lag = lobster.get("heartbeatLag")
                if heartbeat_lag and heartbeat_lag > self.thresholds["lobster_offline_minutes"] * 60:
                    alerts.append({
                        "type": "lobster_heartbeat",
                        "severity": "warning",
                        "message": f"龙虾 {lobster['displayName']} 心跳延迟 {heartbeat_lag//60:.1f} 分钟",
                        "deviceId": lobster["deviceId"]
                    })

            # 检查任务队列积压
            queue_size = overview.get("tasks", {}).get("queueSize", 0)
            if queue_size > self.thresholds["task_queue_size"]:
                alerts.append({
                    "type": "queue_backlog",
                    "severity": "warning",
                    "message": f"任务队列积压 {queue_size} 个任务",
                    "queueSize": queue_size
                })

            # 检查任务失败率
            failure_rate = overview.get("performance", {}).get("failureRate", 0)
            if failure_rate > self.thresholds["task_failure_rate"]:
                alerts.append({
                    "type": "high_failure_rate",
                    "severity": "error",
                    "message": f"任务失败率过高: {failure_rate:.1%}",
                    "failureRate": failure_rate
                })

            # 检查系统健康度
            health_score = overview.get("health", {}).get("score", 100)
            if health_score < 50:
                alerts.append({
                    "type": "system_health",
                    "severity": "critical",
                    "message": f"系统健康度低: {health_score:.1f}",
                    "healthScore": health_score
                })

            # 处理新告警
            for alert in alerts:
                await self._handle_alert(alert)

            return alerts

        except Exception as e:
            logger.error(f"检查告警失败: {e}")
            return []

    async def _handle_alert(self, alert: Dict):
        """处理告警"""
        alert_key = f"{alert['type']}_{alert.get('deviceId', '')}"

        # 避免重复告警
        if not self._should_send_alert(alert_key, alert):
            return

        logger.warning(f"🚨 告警: {alert['message']}")

        # 记录告警历史
        alert_record = {
            **alert,
            "timestamp": datetime.now().isoformat(),
            "alertKey": alert_key
        }
        self.alert_history.append(alert_record)

        # 保持告警历史不超过1000条
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]

        # TODO: 发送告警通知（邮件、Webhook、Slack等）

    def _should_send_alert(self, alert_key: str, alert: Dict) -> bool:
        """判断是否应该发送告警（避免告警轰炸）"""
        # 检查最近30分钟内是否已发送相同告警
        cutoff_time = datetime.now() - timedelta(minutes=30)

        for historical_alert in self.alert_history:
            if (historical_alert.get("alertKey") == alert_key and
                datetime.fromisoformat(historical_alert["timestamp"]) > cutoff_time):
                return False

        return True

    async def start_monitoring(self):
        """启动监控服务"""
        logger.info("启动监控服务...")
        self.running = True

        while self.running:
            try:
                # 检查告警
                alerts = await self.check_alerts()

                if alerts:
                    logger.info(f"检测到 {len(alerts)} 个告警")

                # 等待下次检查
                await asyncio.sleep(self.monitoring_interval)

            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def stop_monitoring(self):
        """停止监控服务"""
        logger.info("停止监控服务...")
        self.running = False

    def generate_report(self) -> Dict:
        """生成详细的状态报告"""
        try:
            overview = self.get_pool_overview()

            # 添加告警历史
            overview["alerts"] = {
                "recent": [alert for alert in self.alert_history
                          if datetime.fromisoformat(alert["timestamp"]) >
                          datetime.now() - timedelta(hours=24)],
                "totalCount": len(self.alert_history)
            }

            # 添加趋势数据（这里简化处理）
            overview["trends"] = {
                "note": "趋势数据需要更完整的历史记录实现"
            }

            return overview

        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return {"error": str(e)}

def print_pool_status(monitor: PoolMonitor):
    """打印池状态"""
    overview = monitor.get_pool_overview()

    if "error" in overview:
        print(f"❌ 获取状态失败: {overview['error']}")
        return

    print("🏊‍♂️ Claw Pool Status")
    print(f"   时间: {overview['timestamp']}")

    # 龙虾状态
    lobsters = overview.get("lobsters", {})
    print(f"\n🦞 龙虾状态:")
    print(f"   总数: {lobsters.get('total', 0)}")
    print(f"   在线: {lobsters.get('onlineCount', 0)}")

    status_counts = lobsters.get("statusCounts", {})
    for status, count in status_counts.items():
        print(f"   {status}: {count}")

    # 任务状态
    tasks = overview.get("tasks", {})
    print(f"\n📋 任务状态:")
    print(f"   总任务数: {tasks.get('total', 0)}")
    print(f"   队列大小: {tasks.get('queueSize', 0)}")
    print(f"   最近24h: {tasks.get('last24Hours', 0)}")

    # 性能指标
    performance = overview.get("performance", {})
    print(f"\n⚡ 性能指标:")
    print(f"   平均执行时间: {performance.get('avgExecutionTime', 0):.2f}秒")
    print(f"   成功率: {performance.get('successRate', 0):.2%}")
    print(f"   吞吐量: {performance.get('throughput', 0):.2f}任务/分钟")

    # 健康度
    health = overview.get("health", {})
    health_score = health.get("score", 0)
    health_status = health.get("status", "unknown")

    health_icon = {
        "excellent": "🟢",
        "good": "🟡",
        "fair": "🟠",
        "poor": "🔴",
        "critical": "💀"
    }.get(health_status, "❓")

    print(f"\n{health_icon} 系统健康度: {health_score:.1f}/100 ({health_status})")

def print_lobster_details(monitor: PoolMonitor, device_id: str):
    """打印龙虾详细信息"""
    details = monitor.get_lobster_details(device_id)

    if not details:
        print(f"❌ 龙虾 {device_id} 不存在")
        return

    print(f"🦞 龙虾详情: {details['displayName']} ({device_id})")
    print(f"   状态: {details['status']}")
    print(f"   能力: {', '.join(details['capabilities'])}")

    resources = details.get("resources", {})
    if resources:
        print(f"   资源:")
        for key, value in resources.items():
            print(f"     {key}: {value}")

    print(f"   注册时间: {details.get('registrationTime')}")
    print(f"   最后心跳: {details.get('lastHeartbeat')}")

    task_history = details.get("taskHistory", [])
    if task_history:
        print(f"\n📋 最近任务 (最新 {min(5, len(task_history))} 个):")
        for task in task_history[:5]:
            status_icon = {
                "completed": "✅",
                "failed": "❌",
                "running": "⚡",
                "pending": "⏳"
            }.get(task["status"], "❓")

            print(f"   {status_icon} {task['taskId']} ({task['taskType']})")
            print(f"      创建: {task['createdTime']}")
            if task['completedTime']:
                print(f"      完成: {task['completedTime']}")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Monitor Service')
    parser.add_argument('--start', action='store_true',
                       help='启动监控服务')
    parser.add_argument('--status', action='store_true',
                       help='查看实时状态')
    parser.add_argument('--lobster', type=str,
                       help='查看龙虾详情')
    parser.add_argument('--report', action='store_true',
                       help='生成状态报告')
    parser.add_argument('--registry-db', type=str,
                       help='注册表数据库路径')
    parser.add_argument('--tasks-db', type=str,
                       help='任务数据库路径')

    args = parser.parse_args()

    monitor = PoolMonitor(args.registry_db, args.tasks_db)

    if args.status:
        print_pool_status(monitor)
    elif args.lobster:
        print_lobster_details(monitor, args.lobster)
    elif args.report:
        report = monitor.generate_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.start:
        try:
            await monitor.start_monitoring()
        except KeyboardInterrupt:
            print("\n用户中断，停止监控服务")
            await monitor.stop_monitoring()
    else:
        print("请指定操作：--start, --status, --lobster, 或 --report")

if __name__ == '__main__':
    asyncio.run(main())