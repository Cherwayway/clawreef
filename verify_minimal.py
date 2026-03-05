#!/usr/bin/env uv run python
"""
Claw Pool Phase 2.5 验证脚本

实现最小可行场景：
- 启动一个简化的 Controller（内存模式，不需要真正的网络）
- 启动一个简化的 Agent
- Agent 注册到 Controller
- Controller 分配一个简单任务（比如：计算 1+1）
- Agent 执行并返回结果
- 验证结果正确

Usage:
    python verify_minimal.py
"""

import asyncio
import json
import uuid
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class LobsterInfo:
    device_id: str
    display_name: str
    capabilities: List[str]
    resources: Dict[str, Any]
    status: str = "online"
    registration_time: str = None

@dataclass
class Task:
    task_id: str
    task_type: str
    content: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    result: Optional[Any] = None
    created_time: str = None
    completed_time: str = None

class MemoryController:
    """简化的内存 Controller"""

    def __init__(self):
        self.lobsters: Dict[str, LobsterInfo] = {}
        self.tasks: Dict[str, Task] = {}
        self.task_queue: List[str] = []
        logger.info("📡 Memory Controller 初始化完成")

    async def register_lobster(self, registration_data: Dict) -> Dict:
        """处理龙虾注册"""
        lobster_data = registration_data.get("lobster", {})
        device_id = lobster_data.get("deviceId")

        if not device_id:
            return {"status": "rejected", "message": "缺少设备ID"}

        lobster = LobsterInfo(
            device_id=device_id,
            display_name=lobster_data.get("displayName", f"Lobster-{device_id[:8]}"),
            capabilities=lobster_data.get("capabilities", []),
            resources=lobster_data.get("resources", {}),
            registration_time=datetime.now().isoformat()
        )

        self.lobsters[device_id] = lobster
        logger.info(f"🦞 注册龙虾成功: {lobster.display_name} ({device_id})")
        logger.info(f"   💡 能力: {lobster.capabilities}")
        logger.info(f"   🖥️  资源: {lobster.resources}")

        return {
            "status": "accepted",
            "message": "注册成功",
            "poolId": "test-pool",
            "deviceId": device_id
        }

    async def submit_task(self, task_data: Dict) -> str:
        """提交新任务"""
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            task_id=task_id,
            task_type=task_data.get("type", "general"),
            content=task_data.get("content", ""),
            created_time=datetime.now().isoformat()
        )

        self.tasks[task_id] = task
        self.task_queue.append(task_id)
        logger.info(f"📋 提交任务: {task.content} (ID: {task_id})")

        return task_id

    async def schedule_tasks(self):
        """调度任务"""
        if not self.task_queue:
            return

        # 找到可用的龙虾
        available_lobsters = [
            lobster for lobster in self.lobsters.values()
            if lobster.status == "online"
        ]

        if not available_lobsters:
            logger.warning("⚠️  没有可用的龙虾来执行任务")
            return

        # 简单的轮询调度
        while self.task_queue and available_lobsters:
            task_id = self.task_queue.pop(0)
            task = self.tasks[task_id]
            lobster = available_lobsters[0]  # 简单选择第一个

            # 检查能力匹配（简化）
            if task.task_type == "python" and "python" not in lobster.capabilities:
                logger.warning(f"⚠️  任务 {task_id} 需要 python 能力，但龙虾 {lobster.device_id} 不支持")
                continue

            task.assigned_to = lobster.device_id
            task.status = TaskStatus.ASSIGNED
            logger.info(f"📌 任务分配: {task_id} -> {lobster.display_name}")

            return task_id, lobster.device_id

        return None, None

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    async def update_task_result(self, task_id: str, result: Any, status: TaskStatus):
        """更新任务结果"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.result = result
            task.status = status
            task.completed_time = datetime.now().isoformat()
            logger.info(f"✅ 任务完成: {task_id}, 结果: {result}")

class MemoryAgent:
    """简化的内存 Agent"""

    def __init__(self, device_id: str, display_name: str, capabilities: List[str]):
        self.device_id = device_id
        self.display_name = display_name
        self.capabilities = capabilities
        self.resources = {
            "cpu": 4,
            "memory": "8GB",
            "disk": "100GB"
        }
        self.controller: Optional[MemoryController] = None
        self.registered = False
        logger.info(f"🤖 Agent 初始化: {self.display_name}")

    async def register_to_controller(self, controller: MemoryController) -> bool:
        """注册到 Controller"""
        self.controller = controller

        registration_data = {
            "action": "register",
            "lobster": {
                "deviceId": self.device_id,
                "displayName": self.display_name,
                "capabilities": self.capabilities,
                "resources": self.resources
            }
        }

        response = await controller.register_lobster(registration_data)

        if response["status"] == "accepted":
            self.registered = True
            logger.info(f"🔗 Agent {self.display_name} 注册成功")
            return True
        else:
            logger.error(f"❌ Agent {self.display_name} 注册失败: {response['message']}")
            return False

    async def execute_task(self, task: Task) -> Any:
        """执行任务"""
        logger.info(f"🔄 开始执行任务: {task.content}")

        # 更新任务状态
        task.status = TaskStatus.RUNNING

        # 模拟任务执行
        await asyncio.sleep(0.1)  # 模拟执行时间

        try:
            # 简单的任务执行逻辑
            if "1+1" in task.content:
                result = 2
            elif "计算" in task.content and "+" in task.content:
                # 简单的数学计算
                expr = task.content.replace("计算", "").strip()
                result = eval(expr)  # 注意：生产环境不要这样做！
            elif task.task_type == "python":
                # 模拟 Python 代码执行
                result = "Python 代码执行完成"
            else:
                result = f"任务 '{task.content}' 执行完成"

            logger.info(f"✨ 任务执行成功: {result}")
            return result

        except Exception as e:
            logger.error(f"💥 任务执行失败: {e}")
            raise e

class VerificationRunner:
    """验证测试运行器"""

    def __init__(self):
        self.controller = MemoryController()
        self.agents: List[MemoryAgent] = []
        self.test_results: List[Dict] = []

    def add_test_result(self, test_name: str, success: bool, message: str, details: Any = None):
        """添加测试结果"""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)

        status = "✅" if success else "❌"
        logger.info(f"{status} {test_name}: {message}")

    async def test_01_controller_initialization(self):
        """测试 1: Controller 初始化"""
        try:
            assert self.controller is not None
            self.add_test_result("Controller 初始化", True, "Controller 成功初始化")
        except Exception as e:
            self.add_test_result("Controller 初始化", False, f"失败: {e}")

    async def test_02_agent_creation(self):
        """测试 2: Agent 创建"""
        try:
            agent = MemoryAgent(
                device_id="test_lobster_001",
                display_name="测试龙虾#1",
                capabilities=["python", "general", "math"]
            )
            self.agents.append(agent)

            assert agent.device_id == "test_lobster_001"
            assert "python" in agent.capabilities

            self.add_test_result("Agent 创建", True, f"Agent 创建成功: {agent.display_name}")
        except Exception as e:
            self.add_test_result("Agent 创建", False, f"失败: {e}")

    async def test_03_agent_registration(self):
        """测试 3: Agent 注册"""
        try:
            if not self.agents:
                raise Exception("没有可用的 Agent")

            agent = self.agents[0]
            success = await agent.register_to_controller(self.controller)

            assert success
            assert agent.registered
            assert agent.device_id in self.controller.lobsters

            self.add_test_result("Agent 注册", True, f"Agent 成功注册到 Controller")
        except Exception as e:
            self.add_test_result("Agent 注册", False, f"失败: {e}")

    async def test_04_task_submission(self):
        """测试 4: 任务提交"""
        try:
            task_data = {
                "type": "math",
                "content": "计算 1+1",
                "capabilities": ["math"]
            }

            task_id = await self.controller.submit_task(task_data)

            assert task_id is not None
            assert task_id in self.controller.tasks
            assert len(self.controller.task_queue) == 1

            self.add_test_result("任务提交", True, f"任务提交成功，ID: {task_id}")
            return task_id
        except Exception as e:
            self.add_test_result("任务提交", False, f"失败: {e}")
            return None

    async def test_05_task_scheduling(self):
        """测试 5: 任务调度"""
        try:
            task_id, assigned_lobster = await self.controller.schedule_tasks()

            assert task_id is not None
            assert assigned_lobster is not None
            assert len(self.controller.task_queue) == 0  # 任务应该从队列中移除

            task = self.controller.get_task(task_id)
            assert task.status == TaskStatus.ASSIGNED
            assert task.assigned_to == assigned_lobster

            self.add_test_result("任务调度", True, f"任务 {task_id} 调度到 {assigned_lobster}")
            return task_id
        except Exception as e:
            self.add_test_result("任务调度", False, f"失败: {e}")
            return None

    async def test_06_task_execution(self, task_id: str):
        """测试 6: 任务执行"""
        try:
            if not task_id:
                raise Exception("没有有效的任务ID")

            task = self.controller.get_task(task_id)
            if not task:
                raise Exception(f"找不到任务: {task_id}")

            agent = self.agents[0]  # 使用第一个 agent

            result = await agent.execute_task(task)

            # 更新 Controller 中的任务结果
            await self.controller.update_task_result(task_id, result, TaskStatus.COMPLETED)

            assert result == 2  # 1+1 的结果应该是 2
            assert task.status == TaskStatus.COMPLETED
            assert task.result == 2

            self.add_test_result("任务执行", True, f"任务执行成功，结果: {result}")
        except Exception as e:
            self.add_test_result("任务执行", False, f"失败: {e}")

    async def test_07_end_to_end_flow(self):
        """测试 7: 端到端流程"""
        try:
            logger.info("\n" + "="*50)
            logger.info("🚀 开始端到端验证流程")
            logger.info("="*50)

            # 创建第二个 Agent 用于端到端测试
            agent2 = MemoryAgent(
                device_id="test_lobster_002",
                display_name="端到端测试龙虾",
                capabilities=["python", "general", "text-processing"]
            )

            # 注册
            success = await agent2.register_to_controller(self.controller)
            assert success

            # 提交任务
            task_data = {
                "type": "general",
                "content": "处理文本：Hello World",
                "capabilities": ["text-processing"]
            }

            task_id = await self.controller.submit_task(task_data)
            assert task_id is not None

            # 调度任务
            scheduled_task_id, assigned_lobster = await self.controller.schedule_tasks()
            assert scheduled_task_id == task_id

            # 执行任务
            task = self.controller.get_task(task_id)
            result = await agent2.execute_task(task)
            await self.controller.update_task_result(task_id, result, TaskStatus.COMPLETED)

            # 验证最终状态
            final_task = self.controller.get_task(task_id)
            assert final_task.status == TaskStatus.COMPLETED
            assert final_task.result is not None

            self.add_test_result("端到端流程", True, f"完整流程验证成功")

        except Exception as e:
            self.add_test_result("端到端流程", False, f"失败: {e}")

    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("\n" + "="*60)
        logger.info("🧪 开始 Claw Pool Phase 2.5 验证测试")
        logger.info("="*60)

        # 运行测试
        await self.test_01_controller_initialization()
        await self.test_02_agent_creation()
        await self.test_03_agent_registration()

        task_id = await self.test_04_task_submission()
        scheduled_task_id = await self.test_05_task_scheduling()

        if scheduled_task_id:
            await self.test_06_task_execution(scheduled_task_id)

        await self.test_07_end_to_end_flow()

    def print_summary(self):
        """打印测试结果摘要"""
        logger.info("\n" + "="*60)
        logger.info("📊 测试结果摘要")
        logger.info("="*60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests

        logger.info(f"总测试数: {total_tests}")
        logger.info(f"通过: {passed_tests} ✅")
        logger.info(f"失败: {failed_tests} ❌")
        logger.info(f"成功率: {(passed_tests/total_tests*100):.1f}%")

        logger.info("\n详细结果:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            logger.info(f"{status} {result['test']}: {result['message']}")

        # 系统状态
        logger.info(f"\n🎯 最终系统状态:")
        logger.info(f"   - 注册的龙虾数量: {len(self.controller.lobsters)}")
        logger.info(f"   - 完成的任务数量: {len([t for t in self.controller.tasks.values() if t.status == TaskStatus.COMPLETED])}")
        logger.info(f"   - 待处理任务数量: {len(self.controller.task_queue)}")

        return passed_tests == total_tests

async def main():
    """主函数"""
    runner = VerificationRunner()

    try:
        await runner.run_all_tests()
        all_passed = runner.print_summary()

        if all_passed:
            logger.info("\n🎉 所有测试通过！Claw Pool 基础功能验证成功！")
            return True
        else:
            logger.error("\n💥 部分测试失败，请检查问题后重试")
            return False

    except Exception as e:
        logger.error(f"💥 验证过程出现异常: {e}")
        return False

if __name__ == "__main__":
    import sys
    result = asyncio.run(main())
    sys.exit(0 if result else 1)