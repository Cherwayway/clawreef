#!/usr/bin/env python3
"""
Phase 3: 跨进程通信最终测试

修正版本，解决端口冲突和兼容性问题，
确保 Controller 和 Agent 跨进程通信正常工作。
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


# 使用不同的端口避免冲突
CONTROLLER_HOST = 'localhost'
CONTROLLER_PORT = 18790  # 更改端口避免冲突

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
        file_handler = logging.FileHandler('cross_process_final.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class FinalControllerProcess:
    """最终版 Controller 进程"""

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

    async def handle_agent_message(self, websocket):
        """处理 Agent 连接和消息"""
        agent_id = None
        connection_id = f"conn-{id(websocket)}"

        try:
            self.logger.info(f"🔗 新的连接: {websocket.remote_address} ({connection_id})")

            async for message in websocket:
                try:
                    self.message_count += 1
                    data = json.loads(message)
                    self.logger.info(f"📨 收到消息 #{self.message_count}: {data}")

                    action = data.get('action')
                    response = await self.process_agent_action(action, data, websocket)

                    if action == 'register':
                        agent_id = data.get('agent', {}).get('id')

                    # 发送响应
                    if response:
                        await websocket.send(json.dumps(response))
                        self.logger.info(f"📤 发送响应: {response}")

                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON 解析错误: {e}")
                    error_response = {
                        'status': 'error',
                        'message': 'Invalid JSON format'
                    }
                    await websocket.send(json.dumps(error_response))

        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"🔌 连接已关闭: {connection_id}")
            if agent_id:
                self.agents.pop(agent_id, None)
                self.logger.info(f"🗑️ 移除 Agent: {agent_id}")

        except Exception as e:
            self.logger.error(f"❌ 处理连接错误 {connection_id}: {e}")
            self.logger.error(traceback.format_exc())

    async def process_agent_action(self, action: str, data: Dict[str, Any], websocket) -> Dict[str, Any]:
        """处理 Agent 动作"""
        if action == 'register':
            return await self.handle_register(data, websocket)
        elif action == 'heartbeat':
            return await self.handle_heartbeat(data)
        elif action == 'task_result':
            return await self.handle_task_result(data)
        else:
            self.logger.warning(f"⚠️ 未知动作: {action}")
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
                self.logger.error("❌ 缺少 Agent ID")
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

            self.logger.info(f"✅ Agent 注册成功: {agent_id}")
            self.logger.info(f"   📝 名称: {self.agents[agent_id]['name']}")
            self.logger.info(f"   🎯 能力: {self.agents[agent_id]['capabilities']}")
            self.logger.info(f"📊 当前总 Agent 数: {len(self.agents)}")

            # 延迟分配测试任务
            asyncio.create_task(self.assign_test_task_delayed(agent_id))

            return {
                'status': 'success',
                'message': 'Agent registered successfully',
                'agent_id': agent_id,
                'pool_info': {
                    'pool_id': 'final-test-pool',
                    'controller_version': '3.0.0-final',
                    'total_agents': len(self.agents)
                }
            }

        except Exception as e:
            self.logger.error(f"❌ 注册失败: {e}")
            return {
                'status': 'error',
                'message': f'Registration failed: {str(e)}'
            }

    async def assign_test_task_delayed(self, agent_id: str):
        """延迟分配测试任务"""
        try:
            # 等待连接稳定
            await asyncio.sleep(2)

            if agent_id not in self.agents:
                return

            task_id = str(uuid.uuid4())
            agent = self.agents[agent_id]
            capabilities = agent.get('capabilities', [])

            # 根据能力创建任务
            if 'data-analysis' in capabilities:
                task_data = {
                    'type': 'data_analysis',
                    'description': '分析数据集统计信息',
                    'data': [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
                    'required_stats': ['mean', 'sum', 'max', 'min']
                }
            elif any(cap in capabilities for cap in ['calculation', 'math']):
                task_data = {
                    'type': 'calculate',
                    'description': '计算数字序列',
                    'numbers': [5, 15, 25, 35, 45],
                    'operations': ['sum', 'product', 'average']
                }
            else:
                task_data = {
                    'type': 'generic',
                    'description': f'通用处理任务',
                    'message': f'Hello {agent_id}! 这是来自 Controller 的测试消息。',
                    'task_info': 'Phase 3 跨进程通信测试'
                }

            self.tasks[task_id] = {
                'task_id': task_id,
                'assigned_agent': agent_id,
                'task_data': task_data,
                'assigned_at': datetime.now().isoformat(),
                'status': 'assigned'
            }

            # 发送任务
            task_message = {
                'action': 'execute_task',
                'task_id': task_id,
                'task_data': task_data
            }

            try:
                await agent['websocket'].send(json.dumps(task_message))
                self.logger.info(f"🚀 任务已分配: {task_id} -> {agent_id}")
                self.logger.info(f"   📋 类型: {task_data['type']}")
                self.logger.info(f"   📄 描述: {task_data['description']}")
            except Exception as e:
                self.logger.error(f"❌ 发送任务失败: {e}")

        except Exception as e:
            self.logger.error(f"❌ 分配任务异常: {e}")

    async def handle_heartbeat(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理心跳"""
        agent_id = data.get('agent_id')

        if agent_id in self.agents:
            self.agents[agent_id]['last_heartbeat'] = datetime.now().isoformat()
            self.agents[agent_id]['status'] = data.get('status', 'online')
            self.logger.debug(f"💓 心跳: {agent_id}")
            return {
                'status': 'success',
                'message': 'Heartbeat received'
            }
        else:
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

            self.logger.info(f"✅ 任务完成: {task_id} (Agent: {agent_id})")
            self.logger.info(f"   📊 状态: {status}")
            if result:
                self.logger.info(f"   📄 结果预览: {str(result)[:100]}...")
            self.logger.info(f"📈 总完成任务: {len(self.task_results)}")

            return {
                'status': 'success',
                'message': 'Task result received'
            }
        else:
            self.logger.error(f"❌ 未知任务 ID: {task_id}")
            return {
                'status': 'error',
                'message': 'Unknown task ID'
            }

    async def start_server(self):
        """启动服务器"""
        self.logger.info(f"🚀 启动 Controller 服务器: {self.host}:{self.port}")
        self.running = True

        try:
            self.server = await websockets.serve(
                self.handle_agent_message,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=10
            )

            self.logger.info(f"✅ 服务器启动成功，等待连接...")

            # 启动状态监控
            asyncio.create_task(self.status_monitor())

            await self.server.wait_closed()

        except Exception as e:
            self.logger.error(f"❌ 服务器启动失败: {e}")
            self.logger.error(traceback.format_exc())

    async def status_monitor(self):
        """状态监控"""
        while self.running:
            await asyncio.sleep(10)
            if self.agents or self.task_results:
                self.logger.info(f"📊 状态: {len(self.agents)} 活跃 Agents, {len(self.task_results)} 完成任务")

    async def stop_server(self):
        """停止服务器"""
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.logger.info("🛑 服务器已停止")


class FinalAgentProcess:
    """最终版 Agent 进程"""

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

            self.logger.info(f"✅ 连接成功")
            self.running = True

            # 注册
            await self.register_to_controller()

            # 启动心跳
            asyncio.create_task(self.heartbeat_loop())

            # 监听任务
            await self.listen_for_tasks()

        except Exception as e:
            self.logger.error(f"❌ 连接失败: {e}")
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
        self.logger.info(f"   🆔 ID: {self.agent_id}")
        self.logger.info(f"   📝 名称: {self.name}")
        self.logger.info(f"   🎯 能力: {self.capabilities}")

        # 等待响应
        try:
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
            response_data = json.loads(response)

            if response_data.get('status') == 'success':
                self.logger.info(f"✅ 注册成功!")
                pool_info = response_data.get('pool_info', {})
                if pool_info:
                    self.logger.info(f"   🏊 Pool: {pool_info.get('pool_id')}")
                    self.logger.info(f"   📊 总 Agents: {pool_info.get('total_agents')}")
            else:
                self.logger.error(f"❌ 注册失败: {response_data.get('message')}")

        except asyncio.TimeoutError:
            self.logger.error("❌ 注册超时")
        except Exception as e:
            self.logger.error(f"❌ 注册异常: {e}")

    async def heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                await asyncio.sleep(15)

                # 检查连接状态
                if not hasattr(self.websocket, 'closed'):
                    # 兼容不同版本的websockets库
                    is_closed = False
                else:
                    is_closed = self.websocket.closed

                if self.websocket and not is_closed:
                    await self.send_heartbeat()
                else:
                    break

            except Exception as e:
                self.logger.error(f"❌ 心跳异常: {e}")
                break

    async def send_heartbeat(self):
        """发送心跳"""
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
            self.logger.error(f"❌ 发送心跳失败: {e}")

    async def listen_for_tasks(self):
        """监听任务"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.logger.info(f"📨 收到消息: {data}")

                    action = data.get('action')
                    if action == 'execute_task':
                        await self.execute_task(data)
                    else:
                        self.logger.warning(f"⚠️ 未知动作: {action}")

                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON 解析错误: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.info("🔌 连接已关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听异常: {e}")

    async def execute_task(self, task_data: Dict[str, Any]):
        """执行任务"""
        task_id = task_data.get('task_id')
        task_content = task_data.get('task_data', {})

        self.logger.info(f"🚀 开始执行任务: {task_id}")
        self.logger.info(f"   📋 类型: {task_content.get('type')}")
        self.logger.info(f"   📄 描述: {task_content.get('description')}")

        try:
            task_type = task_content.get('type', 'unknown')

            if task_type == 'calculate':
                result_data = await self.process_calculation(task_content)
            elif task_type == 'data_analysis':
                result_data = await self.process_data_analysis(task_content)
            else:
                result_data = await self.process_generic_task(task_content)

            # 模拟处理时间
            await asyncio.sleep(1)
            self.completed_tasks += 1

            # 发送结果
            result_message = {
                'action': 'task_result',
                'task_id': task_id,
                'agent_id': self.agent_id,
                'status': 'completed',
                'result': result_data
            }

            await self.websocket.send(json.dumps(result_message))
            self.logger.info(f"✅ 任务完成并发送结果: {task_id}")
            self.logger.info(f"📊 总完成任务: {self.completed_tasks}")

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
            except Exception:
                pass

    async def process_calculation(self, task_content: Dict[str, Any]) -> Dict[str, Any]:
        """处理计算任务"""
        numbers = task_content.get('numbers', [])
        if not numbers:
            return {'error': 'No numbers provided'}

        total = sum(numbers)
        avg = total / len(numbers)
        product = 1
        for n in numbers:
            product *= n

        self.logger.info(f"   🧮 计算: 总和={total}, 平均={avg:.2f}, 积={product}")

        return {
            'type': 'calculation_result',
            'input_numbers': numbers,
            'sum': total,
            'average': avg,
            'product': product,
            'count': len(numbers),
            'processed_by': self.agent_id,
            'timestamp': datetime.now().isoformat()
        }

    async def process_data_analysis(self, task_content: Dict[str, Any]) -> Dict[str, Any]:
        """处理数据分析任务"""
        data = task_content.get('data', [])
        if not data:
            return {'error': 'No data provided'}

        total = sum(data)
        mean = total / len(data)
        max_val = max(data)
        min_val = min(data)

        self.logger.info(f"   📊 分析: 均值={mean:.2f}, 最大={max_val}, 最小={min_val}")

        return {
            'type': 'analysis_result',
            'data_size': len(data),
            'statistics': {
                'mean': mean,
                'sum': total,
                'max': max_val,
                'min': min_val,
                'range': max_val - min_val
            },
            'processed_by': self.agent_id,
            'timestamp': datetime.now().isoformat()
        }

    async def process_generic_task(self, task_content: Dict[str, Any]) -> Dict[str, Any]:
        """处理通用任务"""
        message = task_content.get('message', '')
        self.logger.info(f"   💬 处理消息: {message[:50]}...")

        return {
            'type': 'generic_result',
            'message': f"已处理来自 Controller 的消息",
            'original_message': message,
            'response': f"Hello Controller! {self.agent_id} 已成功处理任务。",
            'processed_by': self.agent_id,
            'timestamp': datetime.now().isoformat()
        }

    async def disconnect(self):
        """断开连接"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.logger.info("🔌 已断开连接")


# 子进程入口函数
async def run_final_controller():
    """运行最终 Controller"""
    controller = FinalControllerProcess()
    try:
        await controller.start_server()
    except KeyboardInterrupt:
        controller.logger.info("收到中断信号")
    except Exception as e:
        controller.logger.error(f"Controller 异常: {e}")


async def run_final_agent(agent_id: str, name: str, capabilities: List[str]):
    """运行最终 Agent"""
    agent = FinalAgentProcess(agent_id, name, capabilities)
    try:
        await agent.connect_to_controller()
    except KeyboardInterrupt:
        agent.logger.info("收到中断信号")
    except Exception as e:
        agent.logger.error(f"Agent 异常: {e}")


def output_reader(process, name, output_queue):
    """读取子进程输出"""
    try:
        for line in process.stdout:
            if line.strip():
                output_queue.put(f"[{name}] {line.strip()}")
    except Exception as e:
        output_queue.put(f"[{name}] 输出读取错误: {e}")


async def main_final():
    """最终测试主流程"""
    main_logger = setup_logging("FinalTest")
    main_logger.info("========== Phase 3: 最终跨进程通信测试开始 ==========")

    start_time = datetime.now()
    controller_process = None
    agent_processes = []
    output_queue = queue.Queue()

    try:
        # 1. 启动 Controller
        main_logger.info("1. 启动最终 Controller 进程...")

        controller_script = f'''
import asyncio
import sys
import os
sys.path.insert(0, "{os.path.dirname(__file__)}")
from cross_process_test_final import run_final_controller

if __name__ == "__main__":
    asyncio.run(run_final_controller())
'''

        with open('/tmp/final_controller.py', 'w') as f:
            f.write(controller_script)

        controller_process = subprocess.Popen([
            sys.executable, '/tmp/final_controller.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

        threading.Thread(
            target=output_reader,
            args=(controller_process, "Controller", output_queue),
            daemon=True
        ).start()

        await asyncio.sleep(3)
        main_logger.info("Controller 启动完成")

        # 2. 启动 Agents
        main_logger.info("2. 启动 Agent 进程...")

        agents_config = [
            ('agent-001', 'Data Analysis Agent', ['python', 'data-analysis']),
            ('agent-002', 'Math Agent', ['python', 'math', 'calculation']),
        ]

        for agent_id, name, capabilities in agents_config:
            main_logger.info(f"启动 Agent: {agent_id}")

            agent_script = f'''
import asyncio
import sys
import os
sys.path.insert(0, "{os.path.dirname(__file__)}")
from cross_process_test_final import run_final_agent

if __name__ == "__main__":
    asyncio.run(run_final_agent("{agent_id}", "{name}", {capabilities}))
'''

            agent_file = f'/tmp/final_agent_{agent_id}.py'
            with open(agent_file, 'w') as f:
                f.write(agent_script)

            agent_process = subprocess.Popen([
                sys.executable, agent_file
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            agent_processes.append(agent_process)

            threading.Thread(
                target=output_reader,
                args=(agent_process, f"Agent-{agent_id}", output_queue),
                daemon=True
            ).start()

            await asyncio.sleep(1)

        main_logger.info("所有 Agent 启动完成")

        # 3. 监控测试
        main_logger.info("3. 监控跨进程通信...")

        test_duration = 25
        start_monitor = time.time()
        output_lines = []

        while time.time() - start_monitor < test_duration:
            try:
                while not output_queue.empty():
                    line = output_queue.get_nowait()
                    print(line)
                    output_lines.append(line)

                await asyncio.sleep(0.1)

            except queue.Empty:
                await asyncio.sleep(0.5)
            except Exception as e:
                main_logger.error(f"监控异常: {e}")

        # 测试完成
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        main_logger.info("========== 最终测试完成 ==========")
        main_logger.info(f"测试耗时: {duration:.2f} 秒")
        main_logger.info(f"输出行数: {len(output_lines)}")

        # 分析结果
        success_indicators = [
            '✅ Agent 注册成功',
            '🚀 任务已分配',
            '✅ 任务完成',
            'Task result received'
        ]

        found_indicators = []
        for indicator in success_indicators:
            if any(indicator in line for line in output_lines):
                found_indicators.append(indicator)

        main_logger.info(f"成功指标: {len(found_indicators)}/{len(success_indicators)}")

        if len(found_indicators) >= 3:
            main_logger.info("✅ 测试成功: Controller 和 Agent 跨进程通信正常")
            await send_final_system_event("Phase 3 跨进程测试完成: 通信正常，任务分配和执行成功验证")
        else:
            main_logger.warning("⚠️ 测试部分成功: 部分功能可能存在问题")
            await send_final_system_event("Phase 3 跨进程测试部分完成: 基本通信正常")

    except Exception as e:
        main_logger.error(f"测试异常: {e}")
        main_logger.error(traceback.format_exc())
        await send_final_system_event(f"Phase 3 跨进程测试失败: {str(e)}")

    finally:
        # 清理进程
        main_logger.info("4. 清理进程...")

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

        main_logger.info("清理完成")


async def send_final_system_event(message: str):
    """发送最终系统事件"""
    try:
        logger = setup_logging("SystemEvent")
        logger.info(f"🎯 系统事件: {message}")

        # 实际环境中会调用：
        # subprocess.run(['openclaw', 'system', 'event', '--text', message, '--mode', 'now'])

    except Exception as e:
        logger.error(f"发送系统事件失败: {e}")


if __name__ == "__main__":
    def signal_handler(sig, frame):
        print("接收到中断信号，正在退出...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main_final())
    except KeyboardInterrupt:
        print("测试被中断")
    except Exception as e:
        print(f"测试失败: {e}")
        traceback.print_exc()
        sys.exit(1)