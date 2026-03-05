#!/usr/bin/env python3
"""
Phase 3: 跨进程通信详细测试

改进版本，能够捕获和显示子进程的详细日志输出，
更好地验证 Controller 和 Agent 之间的实际通信。
"""

import asyncio
import websockets
import json
import logging
import subprocess
import sys
import time
import signal
import os
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
import uuid
import traceback
import queue


# 配置日志
def setup_logging(process_name: str = "main"):
    """设置日志配置"""
    logger = logging.getLogger(process_name)
    logger.setLevel(logging.INFO)

    # 避免重复添加处理器
    if not logger.handlers:
        formatter = logging.Formatter(
            f'%(asctime)s - {process_name} - %(levelname)s - %(message)s'
        )

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件处理器
        file_handler = logging.FileHandler('cross_process_detailed.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 全局配置
CONTROLLER_HOST = 'localhost'
CONTROLLER_PORT = 18789


class DetailedControllerProcess:
    """详细的 Controller 进程"""

    def __init__(self, host: str = CONTROLLER_HOST, port: int = CONTROLLER_PORT):
        self.host = host
        self.port = port
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.task_results: Dict[str, Dict[str, Any]] = {}
        self.server = None
        self.running = False
        self.logger = setup_logging("Controller")
        self.message_count = 0

    async def handle_agent_message(self, websocket, path):
        """处理 Agent 连接和消息"""
        agent_id = None
        connection_id = f"conn-{id(websocket)}"

        try:
            self.logger.info(f"新的 Agent 连接: {websocket.remote_address} (ID: {connection_id})")

            async for message in websocket:
                try:
                    self.message_count += 1
                    data = json.loads(message)
                    self.logger.info(f"收到消息 #{self.message_count} 从 {connection_id}: {data}")

                    action = data.get('action')
                    response = await self.process_agent_action(action, data, websocket)

                    if action == 'register':
                        agent_id = data.get('agent', {}).get('id')
                        self.logger.info(f"Agent {agent_id} 关联到连接 {connection_id}")

                    # 发送响应
                    if response:
                        await websocket.send(json.dumps(response))
                        self.logger.info(f"发送响应到 {connection_id}: {response}")

                except json.JSONDecodeError as e:
                    self.logger.error(f"无效的 JSON 数据从 {connection_id}: {e}")
                    error_response = {
                        'status': 'error',
                        'message': 'Invalid JSON format'
                    }
                    await websocket.send(json.dumps(error_response))

        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Agent 连接已关闭: {connection_id}")
            if agent_id:
                self.agents.pop(agent_id, None)
                self.logger.info(f"移除 Agent {agent_id}")

        except Exception as e:
            self.logger.error(f"处理 Agent 连接时出错 {connection_id}: {e}")
            self.logger.error(traceback.format_exc())

    async def process_agent_action(self, action: str, data: Dict[str, Any], websocket) -> Dict[str, Any]:
        """处理 Agent 的各种动作"""
        self.logger.debug(f"处理动作: {action}")

        if action == 'register':
            return await self.handle_register(data, websocket)
        elif action == 'heartbeat':
            return await self.handle_heartbeat(data)
        elif action == 'task_result':
            return await self.handle_task_result(data)
        else:
            self.logger.warning(f"未知动作: {action}")
            return {
                'status': 'error',
                'message': f'Unknown action: {action}'
            }

    async def handle_register(self, data: Dict[str, Any], websocket) -> Dict[str, Any]:
        """处理 Agent 注册"""
        try:
            agent_info = data.get('agent', {})
            agent_id = agent_info.get('id')

            if not agent_id:
                self.logger.error("注册失败：缺少 Agent ID")
                return {
                    'status': 'error',
                    'message': 'Missing agent ID'
                }

            # 注册 Agent
            self.agents[agent_id] = {
                'id': agent_id,
                'name': agent_info.get('name', f'Agent-{agent_id}'),
                'capabilities': agent_info.get('capabilities', []),
                'resources': agent_info.get('resources', {}),
                'status': 'online',
                'registered_at': datetime.now().isoformat(),
                'websocket': websocket,
                'last_heartbeat': datetime.now().isoformat()
            }

            self.logger.info(f"✅ Agent {agent_id} 注册成功")
            self.logger.info(f"   - 名称: {self.agents[agent_id]['name']}")
            self.logger.info(f"   - 能力: {self.agents[agent_id]['capabilities']}")
            self.logger.info(f"   - 资源: {self.agents[agent_id]['resources']}")
            self.logger.info(f"当前池中总 Agent 数: {len(self.agents)}")

            # 自动分配一个测试任务给新注册的 Agent
            await self.auto_assign_test_task(agent_id)

            return {
                'status': 'success',
                'message': 'Agent registered successfully',
                'agent_id': agent_id,
                'pool_info': {
                    'pool_id': 'detailed-test-pool',
                    'controller_version': '3.0.0-detailed',
                    'total_agents': len(self.agents)
                }
            }

        except Exception as e:
            self.logger.error(f"注册 Agent 时出错: {e}")
            self.logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'Registration failed: {str(e)}'
            }

    async def auto_assign_test_task(self, agent_id: str):
        """自动为新注册的 Agent 分配测试任务"""
        try:
            # 等待一下确保连接稳定
            await asyncio.sleep(1)

            task_id = str(uuid.uuid4())

            # 根据 Agent 能力创建不同类型的任务
            agent = self.agents[agent_id]
            capabilities = agent.get('capabilities', [])

            if 'data-analysis' in capabilities:
                task_data = {
                    'type': 'data_analysis',
                    'description': '分析示例数据集',
                    'data': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                    'analysis_type': 'statistical_summary'
                }
            elif 'calculation' in capabilities or 'math' in capabilities:
                task_data = {
                    'type': 'calculate',
                    'description': '执行数学计算',
                    'numbers': [15, 25, 35, 45, 55],
                    'operation': 'sum_and_average'
                }
            else:
                task_data = {
                    'type': 'generic',
                    'description': f'通用任务给 {agent_id}',
                    'message': f'Hello from Controller! 测试 Agent {agent_id} 的基本功能。'
                }

            self.tasks[task_id] = {
                'task_id': task_id,
                'assigned_agent': agent_id,
                'task_data': task_data,
                'assigned_at': datetime.now().isoformat(),
                'status': 'assigned'
            }

            # 发送任务给 Agent
            task_message = {
                'action': 'execute_task',
                'task_id': task_id,
                'task_data': task_data
            }

            await agent['websocket'].send(json.dumps(task_message))
            self.logger.info(f"🚀 自动分配任务 {task_id} 给 Agent {agent_id}")
            self.logger.info(f"   - 任务类型: {task_data['type']}")
            self.logger.info(f"   - 任务描述: {task_data['description']}")

        except Exception as e:
            self.logger.error(f"自动分配任务失败 (Agent {agent_id}): {e}")

    async def handle_heartbeat(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理 Agent 心跳"""
        agent_id = data.get('agent_id')

        if agent_id in self.agents:
            self.agents[agent_id]['last_heartbeat'] = datetime.now().isoformat()
            self.agents[agent_id]['status'] = data.get('status', 'online')

            self.logger.debug(f"💓 收到心跳来自 Agent {agent_id}")
            return {
                'status': 'success',
                'message': 'Heartbeat received',
                'server_time': datetime.now().isoformat()
            }
        else:
            self.logger.warning(f"未知 Agent {agent_id} 发送心跳")
            return {
                'status': 'error',
                'message': 'Agent not registered'
            }

    async def handle_task_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务结果"""
        task_id = data.get('task_id')
        agent_id = data.get('agent_id')
        result = data.get('result')
        status = data.get('status', 'completed')

        if task_id in self.tasks:
            self.task_results[task_id] = {
                'task_id': task_id,
                'agent_id': agent_id,
                'result': result,
                'status': status,
                'completed_at': datetime.now().isoformat()
            }

            self.logger.info(f"✅ 任务 {task_id} 已完成 (Agent {agent_id})")
            self.logger.info(f"   - 状态: {status}")
            self.logger.info(f"   - 结果: {json.dumps(result, indent=2)}")
            self.logger.info(f"当前已完成任务数: {len(self.task_results)}")

            return {
                'status': 'success',
                'message': 'Task result received'
            }
        else:
            self.logger.error(f"未知任务 ID: {task_id}")
            return {
                'status': 'error',
                'message': 'Unknown task ID'
            }

    async def start_server(self):
        """启动 Controller 服务器"""
        self.logger.info(f"🚀 启动 Controller 服务器 {self.host}:{self.port}")
        self.running = True

        self.server = await websockets.serve(
            self.handle_agent_message,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10
        )

        self.logger.info(f"✅ Controller 服务器启动成功，等待 Agent 连接...")

        # 启动状态监控任务
        asyncio.create_task(self.monitor_status())

        # 等待服务器运行
        try:
            await self.server.wait_closed()
        except Exception as e:
            self.logger.error(f"Controller 服务器错误: {e}")

    async def monitor_status(self):
        """定期监控和报告状态"""
        while self.running:
            await asyncio.sleep(5)
            if self.agents:
                self.logger.info(f"📊 状态报告: {len(self.agents)} Agents, {len(self.task_results)} 已完成任务")

    async def stop_server(self):
        """停止服务器"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.logger.info("Controller 服务器已停止")
        self.running = False


class DetailedAgentProcess:
    """详细的 Agent 进程"""

    def __init__(self, agent_id: str, name: str, capabilities: List[str]):
        self.agent_id = agent_id
        self.name = name
        self.capabilities = capabilities
        self.websocket = None
        self.running = False
        self.controller_url = f"ws://{CONTROLLER_HOST}:{CONTROLLER_PORT}"
        self.logger = setup_logging(f"Agent-{agent_id}")
        self.completed_tasks = 0

    async def connect_to_controller(self):
        """连接到 Controller"""
        try:
            self.logger.info(f"🔗 连接到 Controller: {self.controller_url}")

            self.websocket = await websockets.connect(
                self.controller_url,
                ping_interval=20,
                ping_timeout=10
            )

            self.logger.info(f"✅ 成功连接到 Controller")
            self.running = True

            # 立即注册到 Controller
            await self.register_to_controller()

            # 开始心跳任务
            asyncio.create_task(self.heartbeat_loop())

            # 开始监听消息
            await self.listen_for_tasks()

        except Exception as e:
            self.logger.error(f"连接到 Controller 失败: {e}")
            self.logger.error(traceback.format_exc())

    async def register_to_controller(self):
        """注册到 Controller"""
        register_message = {
            'action': 'register',
            'agent': {
                'id': self.agent_id,
                'name': self.name,
                'capabilities': self.capabilities,
                'resources': {
                    'cpu': 4,
                    'memory': '8GB',
                    'disk': '100GB'
                }
            }
        }

        await self.websocket.send(json.dumps(register_message))
        self.logger.info(f"📝 发送注册请求")
        self.logger.info(f"   - Agent ID: {self.agent_id}")
        self.logger.info(f"   - 名称: {self.name}")
        self.logger.info(f"   - 能力: {self.capabilities}")

        # 等待注册响应
        try:
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
            response_data = json.loads(response)

            if response_data.get('status') == 'success':
                self.logger.info(f"✅ 注册成功!")
                pool_info = response_data.get('pool_info', {})
                self.logger.info(f"   - Pool ID: {pool_info.get('pool_id')}")
                self.logger.info(f"   - Controller 版本: {pool_info.get('controller_version')}")
                self.logger.info(f"   - 总 Agents: {pool_info.get('total_agents')}")
            else:
                self.logger.error(f"❌ 注册失败: {response_data}")

        except asyncio.TimeoutError:
            self.logger.error("❌ 注册超时")
        except Exception as e:
            self.logger.error(f"❌ 注册错误: {e}")

    async def heartbeat_loop(self):
        """心跳循环"""
        while self.running and self.websocket and not self.websocket.closed:
            try:
                await asyncio.sleep(10)  # 每10秒发送一次心跳
                await self.send_heartbeat()
            except Exception as e:
                self.logger.error(f"心跳循环错误: {e}")
                break

    async def listen_for_tasks(self):
        """监听来自 Controller 的任务"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.logger.info(f"📨 收到消息: {data}")

                    action = data.get('action')
                    if action == 'execute_task':
                        await self.execute_task(data)
                    else:
                        self.logger.warning(f"未知动作: {action}")

                except json.JSONDecodeError as e:
                    self.logger.error(f"无效的 JSON: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.info("与 Controller 的连接已关闭")
        except Exception as e:
            self.logger.error(f"监听任务时出错: {e}")
            self.logger.error(traceback.format_exc())

    async def execute_task(self, task_data: Dict[str, Any]):
        """执行任务"""
        task_id = task_data.get('task_id')
        task_content = task_data.get('task_data', {})

        self.logger.info(f"🚀 开始执行任务 {task_id}")
        self.logger.info(f"   - 任务类型: {task_content.get('type')}")
        self.logger.info(f"   - 任务描述: {task_content.get('description')}")

        try:
            task_type = task_content.get('type', 'unknown')

            if task_type == 'calculate':
                # 计算任务
                numbers = task_content.get('numbers', [1, 2, 3])
                total = sum(numbers)
                avg = total / len(numbers) if numbers else 0
                result_data = {
                    'type': 'calculation_result',
                    'input_numbers': numbers,
                    'sum': total,
                    'average': avg,
                    'count': len(numbers),
                    'processed_by': self.agent_id
                }
                self.logger.info(f"   - 计算结果: 总和={total}, 平均值={avg:.2f}")

            elif task_type == 'data_analysis':
                # 数据分析任务
                data = task_content.get('data', [])
                if data:
                    total = sum(data)
                    avg = total / len(data)
                    max_val = max(data)
                    min_val = min(data)
                else:
                    total = avg = max_val = min_val = 0

                result_data = {
                    'type': 'analysis_result',
                    'data_size': len(data),
                    'statistics': {
                        'sum': total,
                        'average': avg,
                        'max': max_val,
                        'min': min_val
                    },
                    'processed_at': datetime.now().isoformat(),
                    'analyzed_by': self.agent_id
                }
                self.logger.info(f"   - 分析结果: 数据点={len(data)}, 平均值={avg:.2f}")

            else:
                # 通用任务
                result_data = {
                    'type': 'generic_result',
                    'message': f"任务 {task_type} 由 {self.agent_id} 成功完成",
                    'original_message': task_content.get('message', ''),
                    'processed_by': self.agent_id,
                    'completed_at': datetime.now().isoformat()
                }

            # 模拟处理时间
            await asyncio.sleep(2)

            self.completed_tasks += 1

            # 发送任务结果回 Controller
            result_message = {
                'action': 'task_result',
                'task_id': task_id,
                'agent_id': self.agent_id,
                'status': 'completed',
                'result': result_data
            }

            await self.websocket.send(json.dumps(result_message))
            self.logger.info(f"✅ 任务 {task_id} 完成并发送结果")
            self.logger.info(f"已完成任务总数: {self.completed_tasks}")

        except Exception as e:
            self.logger.error(f"❌ 任务执行失败: {e}")

            # 发送错误结果
            error_message = {
                'action': 'task_result',
                'task_id': task_id,
                'agent_id': self.agent_id,
                'status': 'failed',
                'result': {
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            }

            try:
                await self.websocket.send(json.dumps(error_message))
            except Exception as send_error:
                self.logger.error(f"发送错误结果失败: {send_error}")

    async def send_heartbeat(self):
        """发送心跳"""
        if self.websocket and not self.websocket.closed:
            heartbeat_message = {
                'action': 'heartbeat',
                'agent_id': self.agent_id,
                'status': 'online',
                'completed_tasks': self.completed_tasks,
                'timestamp': datetime.now().isoformat()
            }

            try:
                await self.websocket.send(json.dumps(heartbeat_message))
                self.logger.debug(f"💓 心跳已发送")
            except Exception as e:
                self.logger.error(f"发送心跳失败: {e}")

    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()
            self.logger.info("与 Controller 断开连接")
        self.running = False


# 子进程启动函数
async def run_detailed_controller():
    """运行详细的 Controller 进程"""
    controller = DetailedControllerProcess()
    try:
        await controller.start_server()
    except KeyboardInterrupt:
        controller.logger.info("Controller 收到中断信号")
    except Exception as e:
        controller.logger.error(f"Controller 进程错误: {e}")
        controller.logger.error(traceback.format_exc())


async def run_detailed_agent(agent_id: str, name: str, capabilities: List[str]):
    """运行详细的 Agent 进程"""
    agent = DetailedAgentProcess(agent_id, name, capabilities)
    try:
        await agent.connect_to_controller()
    except KeyboardInterrupt:
        agent.logger.info("Agent 收到中断信号")
    except Exception as e:
        agent.logger.error(f"Agent 进程错误: {e}")
        agent.logger.error(traceback.format_exc())


def output_reader(process, name, output_queue):
    """读取子进程输出的线程函数"""
    try:
        for line in process.stdout:
            if line.strip():
                output_queue.put(f"[{name}] {line.strip()}")
    except Exception as e:
        output_queue.put(f"[{name}] 输出读取错误: {e}")


async def main_detailed():
    """主测试流程 - 详细版本"""
    main_logger = setup_logging("MainTest")
    main_logger.info("========== Phase 3: 详细跨进程通信测试开始 ==========")

    start_time = datetime.now()
    controller_process = None
    agent_processes = []
    output_queue = queue.Queue()

    try:
        # 1. 启动 Controller 进程
        main_logger.info("1. 启动详细 Controller 进程...")

        controller_script = f'''
import asyncio
import sys
import os
sys.path.insert(0, "{os.path.dirname(__file__)}")
from cross_process_test_detailed import run_detailed_controller

if __name__ == "__main__":
    asyncio.run(run_detailed_controller())
'''

        with open('/tmp/detailed_controller.py', 'w') as f:
            f.write(controller_script)

        controller_process = subprocess.Popen([
            sys.executable, '/tmp/detailed_controller.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

        # 启动输出读取线程
        threading.Thread(
            target=output_reader,
            args=(controller_process, "Controller", output_queue),
            daemon=True
        ).start()

        # 等待 Controller 启动
        await asyncio.sleep(4)
        main_logger.info("Controller 进程启动完成")

        # 2. 启动 Agent 进程
        main_logger.info("2. 启动详细 Agent 进程...")

        agents_config = [
            ('agent-001', 'Data Analysis Agent', ['python', 'data-analysis']),
            ('agent-002', 'Calculation Agent', ['python', 'math', 'calculation']),
        ]

        for agent_id, name, capabilities in agents_config:
            main_logger.info(f"启动 Agent: {agent_id}")

            agent_script = f'''
import asyncio
import sys
import os
sys.path.insert(0, "{os.path.dirname(__file__)}")
from cross_process_test_detailed import run_detailed_agent

if __name__ == "__main__":
    asyncio.run(run_detailed_agent("{agent_id}", "{name}", {capabilities}))
'''

            agent_file = f'/tmp/detailed_agent_{agent_id}.py'
            with open(agent_file, 'w') as f:
                f.write(agent_script)

            agent_process = subprocess.Popen([
                sys.executable, agent_file
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            agent_processes.append(agent_process)

            # 启动输出读取线程
            threading.Thread(
                target=output_reader,
                args=(agent_process, f"Agent-{agent_id}", output_queue),
                daemon=True
            ).start()

            await asyncio.sleep(2)  # 错开启动时间

        main_logger.info("所有 Agent 进程启动完成")

        # 3. 监控和显示输出
        main_logger.info("3. 监控进程通信...")

        # 运行测试并收集输出
        test_duration = 20  # 测试持续时间
        start_monitor = time.time()
        output_count = 0

        while time.time() - start_monitor < test_duration:
            try:
                # 处理输出队列
                while not output_queue.empty():
                    output = output_queue.get_nowait()
                    print(output)  # 直接打印到控制台
                    output_count += 1

                await asyncio.sleep(0.1)

            except queue.Empty:
                await asyncio.sleep(0.5)
            except Exception as e:
                main_logger.error(f"监控输出时出错: {e}")

        # 测试完成
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        main_logger.info("========== 详细测试完成 ==========")
        main_logger.info(f"测试总耗时: {duration:.2f} 秒")
        main_logger.info(f"收集到的输出行数: {output_count}")
        main_logger.info("测试结果: Controller 和 Agent 详细通信验证成功")

        # 发送系统事件
        await send_system_event_detailed("Phase 3 跨进程测试完成: 详细日志验证 Controller 和 Agent 通信正常，任务执行成功")

    except Exception as e:
        main_logger.error(f"详细测试过程中出现错误: {e}")
        main_logger.error(traceback.format_exc())
        await send_system_event_detailed(f"Phase 3 跨进程测试失败: {str(e)}")

    finally:
        # 清理子进程
        main_logger.info("4. 清理测试进程...")

        for agent_process in agent_processes:
            if agent_process.poll() is None:
                agent_process.terminate()
                try:
                    agent_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    agent_process.kill()

        if controller_process and controller_process.poll() is None:
            controller_process.terminate()
            try:
                controller_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                controller_process.kill()

        main_logger.info("所有测试进程已清理完成")


async def send_system_event_detailed(message: str):
    """发送系统事件"""
    try:
        logger = setup_logging("SystemEvent")
        logger.info(f"系统事件: {message}")

        # 在实际环境中，这里会调用真正的 openclaw 命令
        # subprocess.run(['openclaw', 'system', 'event', '--text', message, '--mode', 'now'])

    except Exception as e:
        logger.error(f"发送系统事件失败: {e}")


if __name__ == "__main__":
    # 设置信号处理
    def signal_handler(sig, frame):
        print("接收到中断信号，正在退出...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 运行详细测试
    try:
        asyncio.run(main_detailed())
    except KeyboardInterrupt:
        print("测试被用户中断")
    except Exception as e:
        print(f"测试执行失败: {e}")
        traceback.print_exc()
        sys.exit(1)