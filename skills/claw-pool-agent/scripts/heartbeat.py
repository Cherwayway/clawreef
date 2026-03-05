#!/usr/bin/env python3
"""
Claw Pool Agent - Heartbeat Script

维护与 Pool Controller 的连接：
- 定期心跳上报
- 状态同步 (idle/busy/error/maintenance)
- 资源使用率监控
- 连接故障检测和自动重连

Usage:
    python heartbeat.py                        # 启动心跳服务
    python heartbeat.py --once                 # 发送一次心跳
    python heartbeat.py --status-only          # 只显示当前状态
    python heartbeat.py --daemon               # 后台守护进程模式
"""

import asyncio
import json
import argparse
import os
import time
import psutil
import websockets
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import logging
import signal
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PoolAgentHeartbeat:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        self.registration_file = self._get_registration_file()
        self.status_file = self._get_status_file()

        self.current_status = "idle"  # idle/busy/error/maintenance
        self.current_task = None
        self.last_heartbeat = None
        self.websocket = None
        self.running = True
        self.heartbeat_interval = self.config.get("agent", {}).get("heartbeatInterval", 30000) / 1000

        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        script_dir = Path(__file__).parent
        return str(script_dir.parent / "config" / "pool.json")

    def _load_config(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"配置文件未找到: {self.config_path}")
            return {"agent": {}}

    def _get_registration_file(self) -> str:
        """获取注册信息文件路径"""
        return str(Path.home() / ".openclaw" / "pool_registration.json")

    def _get_status_file(self) -> str:
        """获取状态文件路径"""
        return str(Path.home() / ".openclaw" / "pool_status.json")

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，正在优雅关闭...")
        self.running = False

    def _load_registration_info(self) -> Optional[Dict]:
        """加载注册信息"""
        try:
            with open(self.registration_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error("未找到注册信息，请先运行 register.py")
            return None

    def _get_system_resources(self) -> Dict:
        """获取当前系统资源使用情况"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpuUsage": round(cpu_percent, 1),
                "memoryUsage": round(memory.used / (1024**3), 2),  # GB
                "memoryTotal": round(memory.total / (1024**3), 2),  # GB
                "memoryPercent": round(memory.percent, 1),
                "diskUsage": round(disk.percent, 1),
                "loadAverage": os.getloadavg() if hasattr(os, 'getloadavg') else None,
                "uptime": int(time.time() - psutil.boot_time())
            }
        except Exception as e:
            logger.warning(f"获取系统资源信息失败: {e}")
            return {}

    def _get_openclaw_status(self) -> Dict:
        """获取 OpenClaw 状态信息"""
        try:
            # 这里可以调用 OpenClaw API 获取更详细的状态
            return {
                "activeAgents": self._count_active_agents(),
                "activeSessions": self._count_active_sessions(),
                "lastTaskTime": self._get_last_task_time()
            }
        except Exception as e:
            logger.warning(f"获取 OpenClaw 状态失败: {e}")
            return {}

    def _count_active_agents(self) -> int:
        """统计活跃的代理数量"""
        # 这里需要实现具体的统计逻辑
        return 0

    def _count_active_sessions(self) -> int:
        """统计活跃会话数量"""
        # 这里需要实现具体的统计逻辑
        return 0

    def _get_last_task_time(self) -> Optional[str]:
        """获取最后任务时间"""
        # 这里需要实现具体的获取逻辑
        return None

    def _prepare_heartbeat_data(self, registration_info: Dict) -> Dict:
        """准备心跳数据"""
        return {
            "action": "heartbeat",
            "lobster": {
                "deviceId": registration_info["deviceId"],
                "status": self.current_status,
                "currentTask": self.current_task,
                "queuedTasks": 0,  # TODO: 实现任务队列统计
                "resources": self._get_system_resources(),
                "openclaw": self._get_openclaw_status(),
                "lastError": None,  # TODO: 实现错误状态追踪
                "uptime": int(time.time() * 1000),  # 毫秒时间戳
                "heartbeatTime": datetime.now().isoformat()
            }
        }

    def _save_status(self, status_data: Dict):
        """保存当前状态到文件"""
        try:
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2)
        except Exception as e:
            logger.warning(f"保存状态文件失败: {e}")

    async def send_heartbeat(self, registration_info: Dict) -> bool:
        """发送一次心跳"""
        controller_url = registration_info["controllerUrl"]

        try:
            heartbeat_data = self._prepare_heartbeat_data(registration_info)

            # 保存当前状态
            self._save_status(heartbeat_data)

            async with websockets.connect(controller_url, timeout=10) as websocket:
                request = {
                    "method": "agent",
                    "params": {
                        "agentId": "pool-controller",
                        "messages": [{
                            "role": "user",
                            "content": json.dumps(heartbeat_data)
                        }],
                        "sessionKey": f"heartbeat-{registration_info['deviceId']}"
                    }
                }

                await websocket.send(json.dumps(request))
                response_raw = await asyncio.wait_for(websocket.recv(), timeout=5)
                response = json.loads(response_raw)

                if response.get("status") == "ok":
                    self.last_heartbeat = datetime.now()
                    logger.debug("心跳发送成功")

                    # 处理 Controller 的响应
                    reply = response.get("reply", "{}")
                    if reply and reply != "{}":
                        reply_data = json.loads(reply)
                        await self._handle_controller_response(reply_data)

                    return True
                else:
                    logger.error(f"心跳发送失败: {response.get('error')}")
                    return False

        except Exception as e:
            logger.error(f"发送心跳时出错: {e}")
            return False

    async def _handle_controller_response(self, response: Dict):
        """处理 Controller 的响应"""
        action = response.get("action")

        if action == "task_assignment":
            # 接收到任务分配
            task = response.get("task")
            logger.info(f"接收到新任务: {task.get('id', 'unknown')}")
            await self._handle_task_assignment(task)

        elif action == "status_update":
            # 状态更新请求
            new_status = response.get("status")
            if new_status in ["idle", "busy", "maintenance"]:
                self.current_status = new_status
                logger.info(f"状态更新为: {new_status}")

        elif action == "ping":
            # 简单的 ping 响应
            logger.debug("收到 Controller ping")

    async def _handle_task_assignment(self, task: Dict):
        """处理任务分配"""
        task_id = task.get("id")
        task_type = task.get("type")

        logger.info(f"开始处理任务 {task_id} (类型: {task_type})")

        self.current_status = "busy"
        self.current_task = {
            "id": task_id,
            "type": task_type,
            "startTime": datetime.now().isoformat()
        }

        try:
            # 这里应该调用 task_handler.py 来执行任务
            # 目前只是一个占位符
            await asyncio.sleep(1)  # 模拟任务执行

            logger.info(f"任务 {task_id} 执行完成")

        except Exception as e:
            logger.error(f"任务 {task_id} 执行失败: {e}")

        finally:
            self.current_status = "idle"
            self.current_task = None

    async def start_heartbeat_loop(self) -> bool:
        """启动心跳循环"""
        registration_info = self._load_registration_info()
        if not registration_info:
            return False

        logger.info(f"启动心跳服务 (间隔: {self.heartbeat_interval}秒)")
        logger.info(f"连接到: {registration_info['controllerUrl']}")

        consecutive_failures = 0
        max_failures = 5

        while self.running:
            try:
                success = await self.send_heartbeat(registration_info)

                if success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                if consecutive_failures >= max_failures:
                    logger.error(f"连续 {max_failures} 次心跳失败，进入错误状态")
                    self.current_status = "error"

                # 等待下次心跳
                await asyncio.sleep(self.heartbeat_interval)

            except KeyboardInterrupt:
                logger.info("用户中断，停止心跳服务")
                break
            except Exception as e:
                logger.error(f"心跳循环出错: {e}")
                consecutive_failures += 1
                await asyncio.sleep(min(self.heartbeat_interval, 10))

        return True

def print_current_status():
    """打印当前状态"""
    status_file = Path.home() / ".openclaw" / "pool_status.json"

    try:
        with open(status_file, 'r') as f:
            status = json.load(f)

        lobster = status.get("lobster", {})
        print(f"🦞 Lobster Status")
        print(f"   Device ID: {lobster.get('deviceId', 'unknown')}")
        print(f"   Status: {lobster.get('status', 'unknown')}")
        print(f"   Current Task: {lobster.get('currentTask', 'None')}")
        print(f"   Heartbeat Time: {lobster.get('heartbeatTime', 'unknown')}")

        resources = lobster.get("resources", {})
        if resources:
            print(f"   Resources:")
            print(f"     CPU: {resources.get('cpuUsage', 'unknown')}%")
            print(f"     Memory: {resources.get('memoryUsage', 'unknown')}GB / {resources.get('memoryTotal', 'unknown')}GB ({resources.get('memoryPercent', 'unknown')}%)")
            print(f"     Disk: {resources.get('diskUsage', 'unknown')}%")

    except FileNotFoundError:
        print("❌ 未找到状态信息")
        print("   请先启动心跳服务或发送一次心跳")
    except Exception as e:
        print(f"❌ 读取状态失败: {e}")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Agent Heartbeat')
    parser.add_argument('--config', type=str,
                       help='配置文件路径')
    parser.add_argument('--once', action='store_true',
                       help='只发送一次心跳')
    parser.add_argument('--status-only', action='store_true',
                       help='只显示当前状态')
    parser.add_argument('--daemon', action='store_true',
                       help='后台守护进程模式')
    parser.add_argument('--interval', type=int, default=30,
                       help='心跳间隔（秒）')

    args = parser.parse_args()

    if args.status_only:
        print_current_status()
        return

    heartbeat = PoolAgentHeartbeat(args.config)

    # 覆盖配置的心跳间隔
    if args.interval:
        heartbeat.heartbeat_interval = args.interval

    if args.once:
        registration_info = heartbeat._load_registration_info()
        if registration_info:
            success = await heartbeat.send_heartbeat(registration_info)
            print("✅ 心跳发送成功" if success else "❌ 心跳发送失败")
        else:
            print("❌ 未找到注册信息")
    else:
        # 启动心跳循环
        if args.daemon:
            # TODO: 实现守护进程模式
            logger.info("守护进程模式暂未实现，使用前台模式")

        success = await heartbeat.start_heartbeat_loop()
        if not success:
            sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())