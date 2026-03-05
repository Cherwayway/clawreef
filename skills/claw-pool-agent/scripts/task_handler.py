#!/usr/bin/env python3
"""
Claw Pool Agent - Task Handler

任务执行引擎：
- 接收来自 Pool Controller 的任务分配
- 调用 OpenClaw 工具执行任务
- 返回执行结果和性能指标
- 错误处理和重试机制

Usage:
    python task_handler.py --task-file <task.json>    # 执行指定任务文件
    python task_handler.py --listen                   # 监听任务分配
    python task_handler.py --test                     # 测试任务执行环境
"""

import asyncio
import json
import argparse
import os
import time
import subprocess
import tempfile
import websockets
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Any
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PoolTaskHandler:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        self.registration_file = self._get_registration_file()

        self.supported_task_types = [
            "general",
            "python",
            "data-analysis",
            "web-scraping",
            "document-processing",
            "code-generation",
            "text-processing"
        ]

        self.current_tasks = {}  # 当前正在执行的任务
        self.task_history = []   # 任务执行历史

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

    def _load_registration_info(self) -> Optional[Dict]:
        """加载注册信息"""
        try:
            with open(self.registration_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    async def execute_task(self, task: Dict) -> Dict:
        """执行单个任务"""
        task_id = task.get("id", f"task_{int(time.time())}")
        task_type = task.get("type", "general")
        task_content = task.get("content", "")
        task_metadata = task.get("metadata", {})

        logger.info(f"开始执行任务 {task_id} (类型: {task_type})")

        start_time = time.time()
        result = {
            "taskId": task_id,
            "status": "running",
            "startTime": datetime.now().isoformat(),
            "endTime": None,
            "duration": 0,
            "result": None,
            "error": None,
            "performance": {}
        }

        # 添加到当前任务列表
        self.current_tasks[task_id] = result

        try:
            # 根据任务类型选择执行方法
            if task_type == "python":
                task_result = await self._execute_python_task(task_content, task_metadata)
            elif task_type == "data-analysis":
                task_result = await self._execute_data_analysis_task(task_content, task_metadata)
            elif task_type == "web-scraping":
                task_result = await self._execute_web_scraping_task(task_content, task_metadata)
            elif task_type == "document-processing":
                task_result = await self._execute_document_processing_task(task_content, task_metadata)
            elif task_type == "code-generation":
                task_result = await self._execute_code_generation_task(task_content, task_metadata)
            else:
                # 通用任务，直接调用 OpenClaw
                task_result = await self._execute_general_task(task_content, task_metadata)

            # 更新结果
            result["status"] = "completed"
            result["result"] = task_result
            result["endTime"] = datetime.now().isoformat()
            result["duration"] = time.time() - start_time

            logger.info(f"任务 {task_id} 执行成功，耗时 {result['duration']:.2f}秒")

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            result["endTime"] = datetime.now().isoformat()
            result["duration"] = time.time() - start_time

            logger.error(f"任务 {task_id} 执行失败: {e}")

        finally:
            # 从当前任务列表移除
            self.current_tasks.pop(task_id, None)

            # 添加到历史记录
            self.task_history.append(result.copy())

            # 保持历史记录不超过 100 条
            if len(self.task_history) > 100:
                self.task_history = self.task_history[-100:]

        return result

    async def _execute_general_task(self, content: str, metadata: Dict) -> Any:
        """执行通用任务 - 直接调用 OpenClaw CLI"""
        logger.debug("执行通用任务...")

        try:
            # 创建临时文件存储任务内容
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(content)
                temp_file = f.name

            # 调用 OpenClaw CLI 执行任务
            cmd = ['openclaw', 'agent', '--input', temp_file]

            # 添加额外的参数
            model = metadata.get('model', 'claude-opus-4-6')
            if model:
                cmd.extend(['--model', model])

            timeout = metadata.get('timeout', 300)  # 默认5分钟

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout
            )

            stdout, stderr = await process.communicate()

            # 清理临时文件
            os.unlink(temp_file)

            if process.returncode == 0:
                return {
                    "output": stdout.decode('utf-8'),
                    "type": "text"
                }
            else:
                raise Exception(f"OpenClaw 执行失败: {stderr.decode('utf-8')}")

        except asyncio.TimeoutError:
            raise Exception("任务执行超时")
        except Exception as e:
            raise Exception(f"通用任务执行失败: {e}")

    async def _execute_python_task(self, content: str, metadata: Dict) -> Any:
        """执行 Python 任务"""
        logger.debug("执行 Python 任务...")

        try:
            # 使用 OpenClaw 的 Python 工具执行
            cmd = ['python', '-c', content]

            timeout = metadata.get('timeout', 300)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return {
                    "output": stdout.decode('utf-8'),
                    "errors": stderr.decode('utf-8') if stderr else None,
                    "type": "python_output"
                }
            else:
                raise Exception(f"Python 执行失败: {stderr.decode('utf-8')}")

        except asyncio.TimeoutError:
            raise Exception("Python 任务执行超时")
        except Exception as e:
            raise Exception(f"Python 任务执行失败: {e}")

    async def _execute_data_analysis_task(self, content: str, metadata: Dict) -> Any:
        """执行数据分析任务"""
        logger.debug("执行数据分析任务...")

        # 这里可以调用专门的数据分析工具
        # 目前使用通用方法
        return await self._execute_general_task(
            f"作为数据分析专家，请分析以下数据:\n{content}",
            metadata
        )

    async def _execute_web_scraping_task(self, content: str, metadata: Dict) -> Any:
        """执行网页抓取任务"""
        logger.debug("执行网页抓取任务...")

        # 这里可以调用专门的网页抓取工具
        return await self._execute_general_task(
            f"请进行网页抓取和数据提取:\n{content}",
            metadata
        )

    async def _execute_document_processing_task(self, content: str, metadata: Dict) -> Any:
        """执行文档处理任务"""
        logger.debug("执行文档处理任务...")

        return await self._execute_general_task(
            f"请处理以下文档:\n{content}",
            metadata
        )

    async def _execute_code_generation_task(self, content: str, metadata: Dict) -> Any:
        """执行代码生成任务"""
        logger.debug("执行代码生成任务...")

        return await self._execute_general_task(
            f"请生成代码:\n{content}",
            metadata
        )

    async def send_task_result(self, task_result: Dict, registration_info: Dict) -> bool:
        """将任务结果发送回 Controller"""
        controller_url = registration_info["controllerUrl"]

        try:
            async with websockets.connect(controller_url, timeout=10) as websocket:
                request = {
                    "method": "agent",
                    "params": {
                        "agentId": "pool-controller",
                        "messages": [{
                            "role": "user",
                            "content": json.dumps({
                                "action": "task_result",
                                "result": task_result
                            })
                        }],
                        "sessionKey": f"task-result-{task_result['taskId']}"
                    }
                }

                await websocket.send(json.dumps(request))
                response_raw = await websocket.recv()
                response = json.loads(response_raw)

                if response.get("status") == "ok":
                    logger.info(f"任务结果已发送: {task_result['taskId']}")
                    return True
                else:
                    logger.error(f"发送任务结果失败: {response.get('error')}")
                    return False

        except Exception as e:
            logger.error(f"发送任务结果时出错: {e}")
            return False

    async def listen_for_tasks(self, registration_info: Dict):
        """监听来自 Controller 的任务分配"""
        controller_url = registration_info["controllerUrl"]
        device_id = registration_info["deviceId"]

        logger.info(f"开始监听任务分配 ({controller_url})")

        while True:
            try:
                async with websockets.connect(controller_url) as websocket:
                    # 发送任务监听请求
                    listen_request = {
                        "method": "agent",
                        "params": {
                            "agentId": "pool-controller",
                            "messages": [{
                                "role": "user",
                                "content": json.dumps({
                                    "action": "listen_tasks",
                                    "deviceId": device_id
                                })
                            }],
                            "sessionKey": f"task-listener-{device_id}"
                        }
                    }

                    await websocket.send(json.dumps(listen_request))

                    # 持续监听消息
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            reply = data.get("reply", "{}")

                            if reply and reply != "{}":
                                reply_data = json.loads(reply)

                                if reply_data.get("action") == "task_assignment":
                                    task = reply_data.get("task")
                                    if task:
                                        # 异步执行任务
                                        asyncio.create_task(
                                            self._handle_assigned_task(task, registration_info)
                                        )

                        except Exception as e:
                            logger.error(f"处理消息时出错: {e}")

            except websockets.exceptions.ConnectionClosedError:
                logger.warning("连接断开，5秒后重试...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"监听任务时出错: {e}")
                await asyncio.sleep(10)

    async def _handle_assigned_task(self, task: Dict, registration_info: Dict):
        """处理分配的任务"""
        try:
            result = await self.execute_task(task)
            await self.send_task_result(result, registration_info)
        except Exception as e:
            logger.error(f"处理分配任务时出错: {e}")

    def get_status(self) -> Dict:
        """获取任务处理器状态"""
        return {
            "supportedTaskTypes": self.supported_task_types,
            "currentTasks": len(self.current_tasks),
            "currentTaskIds": list(self.current_tasks.keys()),
            "totalTasksExecuted": len(self.task_history),
            "recentTasks": self.task_history[-10:] if self.task_history else []
        }

    def test_environment(self) -> Dict:
        """测试任务执行环境"""
        logger.info("测试任务执行环境...")

        results = {
            "python": self._test_python(),
            "openclaw": self._test_openclaw(),
            "dependencies": self._test_dependencies()
        }

        return results

    def _test_python(self) -> Dict:
        """测试 Python 环境"""
        try:
            import sys
            import platform

            return {
                "status": "ok",
                "version": sys.version,
                "platform": platform.platform(),
                "executable": sys.executable
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _test_openclaw(self) -> Dict:
        """测试 OpenClaw 可用性"""
        try:
            result = subprocess.run(['openclaw', '--version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return {
                    "status": "ok",
                    "version": result.stdout.strip()
                }
            else:
                return {
                    "status": "error",
                    "error": result.stderr
                }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _test_dependencies(self) -> Dict:
        """测试依赖包"""
        required_packages = ['websockets', 'psutil']
        results = {}

        for package in required_packages:
            try:
                __import__(package)
                results[package] = {"status": "ok"}
            except ImportError as e:
                results[package] = {"status": "error", "error": str(e)}

        return results

def print_status(handler: PoolTaskHandler):
    """打印任务处理器状态"""
    status = handler.get_status()

    print("🔧 Task Handler Status")
    print(f"   支持的任务类型: {', '.join(status['supportedTaskTypes'])}")
    print(f"   当前执行中任务: {status['currentTasks']}")
    print(f"   总执行任务数: {status['totalTasksExecuted']}")

    if status['currentTaskIds']:
        print(f"   当前任务ID: {', '.join(status['currentTaskIds'])}")

    recent_tasks = status['recentTasks']
    if recent_tasks:
        print("\n📋 最近任务:")
        for task in recent_tasks[-5:]:  # 只显示最近5个
            print(f"   {task['taskId']}: {task['status']} ({task.get('duration', 0):.2f}s)")

def print_test_results(results: Dict):
    """打印测试结果"""
    print("🧪 Environment Test Results\n")

    for component, result in results.items():
        status_icon = "✅" if result.get("status") == "ok" else "❌"
        print(f"{status_icon} {component.upper()}")

        if result.get("status") == "ok":
            if "version" in result:
                print(f"   版本: {result['version']}")
            if "platform" in result:
                print(f"   平台: {result['platform']}")
        else:
            print(f"   错误: {result.get('error', 'Unknown error')}")
        print()

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Task Handler')
    parser.add_argument('--config', type=str,
                       help='配置文件路径')
    parser.add_argument('--task-file', type=str,
                       help='执行指定的任务文件')
    parser.add_argument('--listen', action='store_true',
                       help='监听来自 Controller 的任务分配')
    parser.add_argument('--test', action='store_true',
                       help='测试任务执行环境')
    parser.add_argument('--status', action='store_true',
                       help='显示当前状态')

    args = parser.parse_args()

    handler = PoolTaskHandler(args.config)

    if args.test:
        results = handler.test_environment()
        print_test_results(results)
        return

    if args.status:
        print_status(handler)
        return

    if args.task_file:
        # 执行指定的任务文件
        try:
            with open(args.task_file, 'r') as f:
                task = json.load(f)

            result = await handler.execute_task(task)
            print(f"任务执行完成: {result['status']}")

            if result['status'] == 'completed':
                print(f"执行时间: {result['duration']:.2f}秒")
                print(f"结果: {json.dumps(result['result'], indent=2)}")
            else:
                print(f"错误: {result['error']}")

        except FileNotFoundError:
            print(f"❌ 任务文件未找到: {args.task_file}")
        except Exception as e:
            print(f"❌ 执行任务文件失败: {e}")

    elif args.listen:
        # 监听任务分配
        registration_info = handler._load_registration_info()
        if not registration_info:
            print("❌ 未找到注册信息，请先运行 register.py")
            return

        try:
            await handler.listen_for_tasks(registration_info)
        except KeyboardInterrupt:
            print("\n用户中断，停止监听")

    else:
        print("请指定操作：--task-file, --listen, --test, 或 --status")

if __name__ == '__main__':
    asyncio.run(main())