#!/usr/bin/env python3
"""
Claw Pool Agent - Registration Script

向 Pool Controller 注册龙虾，包含：
- 发送设备信息和能力
- 处理 Device Pairing 认证
- 存储注册凭证和会话信息

Usage:
    python register.py                                    # 使用配置文件中的设置
    python register.py --controller-url ws://host:port    # 手动指定 Controller
    python register.py --force                            # 强制重新注册
"""

import asyncio
import json
import argparse
import os
import platform
import psutil
import uuid
import websockets
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PoolAgentRegistrar:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        self.device_id = self._get_device_id()
        self.registration_file = self._get_registration_file()

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
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "agent": {
                "displayName": f"{platform.node()}-lobster",
                "capabilities": ["python", "general"],
                "resources": self._detect_resources(),
                "controllerUrl": "auto",
                "heartbeatInterval": 30000,
                "maxConcurrentTasks": 3,
                "pricing": {
                    "enabled": False,
                    "hourlyRate": 0.1,
                    "currency": "USD"
                }
            }
        }

    def _detect_resources(self) -> Dict:
        """自动检测系统资源"""
        memory_gb = round(psutil.virtual_memory().total / (1024**3))
        disk_gb = round(psutil.disk_usage('/').total / (1024**3))

        return {
            "cpu": psutil.cpu_count(),
            "memory": f"{memory_gb}GB",
            "disk": f"{disk_gb}GB",
            "platform": platform.system(),
            "architecture": platform.machine()
        }

    def _get_device_id(self) -> str:
        """获取或生成设备 ID"""
        device_file = Path.home() / ".openclaw" / "device_id"

        if device_file.exists():
            return device_file.read_text().strip()

        # 生成新的设备 ID
        device_id = f"lobster_{uuid.uuid4().hex[:12]}"
        device_file.parent.mkdir(parents=True, exist_ok=True)
        device_file.write_text(device_id)

        return device_id

    def _get_registration_file(self) -> str:
        """获取注册信息存储文件路径"""
        openclaw_dir = Path.home() / ".openclaw"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        return str(openclaw_dir / "pool_registration.json")

    async def discover_controller(self) -> Optional[str]:
        """自动发现 Pool Controller"""
        logger.info("自动发现 Pool Controller...")

        try:
            from .discover import PoolControllerDiscovery
            discovery = PoolControllerDiscovery()
            controllers = await discovery.discover_all()

            if controllers:
                # 选择优先级最高的 Controller
                best_controller = controllers[0]
                logger.info(f"发现 Controller: {best_controller['url']}")
                return best_controller['url']

        except ImportError:
            logger.warning("无法导入 discover 模块，跳过自动发现")

        return None

    async def register_to_pool(self, controller_url: Optional[str] = None, force: bool = False) -> bool:
        """注册到 Pool Controller"""

        # 检查是否已注册且未强制重新注册
        if not force and self._is_already_registered():
            logger.info("已注册到 Pool，使用 --force 强制重新注册")
            return True

        # 确定 Controller URL
        if not controller_url:
            controller_url = self.config.get("agent", {}).get("controllerUrl")

        if controller_url == "auto":
            controller_url = await self.discover_controller()

        if not controller_url:
            logger.error("无法确定 Pool Controller 地址")
            return False

        logger.info(f"正在向 {controller_url} 注册...")

        try:
            registration_data = self._prepare_registration_data()

            async with websockets.connect(controller_url) as websocket:
                # 发送注册请求
                request = {
                    "method": "agent",
                    "params": {
                        "agentId": "pool-controller",
                        "messages": [{
                            "role": "user",
                            "content": json.dumps({
                                "action": "register",
                                "lobster": registration_data
                            })
                        }],
                        "sessionKey": f"registration-{self.device_id}"
                    }
                }

                await websocket.send(json.dumps(request))

                # 等待响应
                response_raw = await websocket.recv()
                response = json.loads(response_raw)

                if response.get("status") == "ok":
                    reply_data = json.loads(response.get("reply", "{}"))

                    if reply_data.get("status") == "approved":
                        # 保存注册信息
                        registration_info = {
                            "deviceId": self.device_id,
                            "controllerUrl": controller_url,
                            "registrationId": reply_data.get("registrationId"),
                            "poolId": reply_data.get("poolInfo", {}).get("poolId"),
                            "registeredAt": datetime.now().isoformat(),
                            "lobsterData": registration_data
                        }

                        self._save_registration_info(registration_info)

                        logger.info("✅ 成功注册到 Pool!")
                        logger.info(f"   Pool ID: {registration_info['poolId']}")
                        logger.info(f"   Registration ID: {registration_info['registrationId']}")

                        return True
                    else:
                        logger.error(f"注册被拒绝: {reply_data.get('message', '未知原因')}")
                        return False
                else:
                    logger.error(f"注册失败: {response.get('error', '未知错误')}")
                    return False

        except Exception as e:
            logger.error(f"注册过程出错: {e}")
            return False

    def _prepare_registration_data(self) -> Dict:
        """准备注册数据"""
        agent_config = self.config.get("agent", {})

        return {
            "deviceId": self.device_id,
            "displayName": agent_config.get("displayName", f"{platform.node()}-lobster"),
            "capabilities": agent_config.get("capabilities", ["general"]),
            "resources": agent_config.get("resources", self._detect_resources()),
            "location": self._get_location_info(),
            "pricing": agent_config.get("pricing", {"enabled": False}),
            "owner": os.getenv("USER", "unknown"),
            "platform": {
                "os": platform.system(),
                "version": platform.version(),
                "architecture": platform.machine(),
                "python": platform.python_version()
            },
            "openclaw": {
                "version": self._get_openclaw_version()
            },
            "registrationTime": datetime.now().isoformat()
        }

    def _get_location_info(self) -> Dict:
        """获取位置信息"""
        # 简单的地理位置识别
        try:
            # 可以通过 Tailscale 或其他方式获取更准确的位置
            return {
                "region": "unknown",
                "timezone": str(datetime.now().astimezone().tzinfo)
            }
        except Exception:
            return {"region": "unknown"}

    def _get_openclaw_version(self) -> str:
        """获取 OpenClaw 版本"""
        try:
            result = subprocess.run(['openclaw', '--version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    def _is_already_registered(self) -> bool:
        """检查是否已经注册"""
        return os.path.exists(self.registration_file)

    def _save_registration_info(self, info: Dict):
        """保存注册信息"""
        with open(self.registration_file, 'w') as f:
            json.dump(info, f, indent=2)
        logger.debug(f"注册信息已保存到: {self.registration_file}")

    def get_registration_info(self) -> Optional[Dict]:
        """获取现有注册信息"""
        try:
            with open(self.registration_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    async def test_connection(self, controller_url: str) -> bool:
        """测试与 Controller 的连接"""
        logger.info(f"测试连接到 {controller_url}...")

        try:
            async with websockets.connect(controller_url, timeout=5) as websocket:
                ping_msg = {
                    "method": "ping",
                    "params": {"type": "connection-test"}
                }
                await websocket.send(json.dumps(ping_msg))

                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                response_data = json.loads(response)

                if response_data.get("status") == "ok":
                    logger.info("✅ 连接测试成功")
                    return True
                else:
                    logger.error(f"连接测试失败: {response_data}")
                    return False

        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False

def print_registration_status(registrar: PoolAgentRegistrar):
    """打印当前注册状态"""
    info = registrar.get_registration_info()

    if not info:
        print("❌ 未注册到任何 Pool")
        print("\n使用以下命令注册:")
        print("  python register.py --scan")
        return

    print("✅ 已注册到 Pool")
    print(f"   Pool ID: {info.get('poolId')}")
    print(f"   Controller: {info.get('controllerUrl')}")
    print(f"   注册时间: {info.get('registeredAt')}")
    print(f"   设备名称: {info.get('lobsterData', {}).get('displayName')}")

    capabilities = info.get('lobsterData', {}).get('capabilities', [])
    print(f"   能力列表: {', '.join(capabilities)}")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Agent Registration')
    parser.add_argument('--controller-url', type=str,
                       help='Pool Controller WebSocket URL')
    parser.add_argument('--config', type=str,
                       help='配置文件路径')
    parser.add_argument('--force', action='store_true',
                       help='强制重新注册')
    parser.add_argument('--test', action='store_true',
                       help='测试与 Controller 的连接')
    parser.add_argument('--status', action='store_true',
                       help='显示当前注册状态')

    args = parser.parse_args()

    registrar = PoolAgentRegistrar(args.config)

    if args.status:
        print_registration_status(registrar)
        return

    if args.test:
        controller_url = args.controller_url or registrar.config.get("agent", {}).get("controllerUrl")
        if controller_url and controller_url != "auto":
            await registrar.test_connection(controller_url)
        else:
            print("请指定 Controller URL 进行测试")
        return

    # 执行注册
    success = await registrar.register_to_pool(
        controller_url=args.controller_url,
        force=args.force
    )

    if success:
        print_registration_status(registrar)
    else:
        print("❌ 注册失败，请检查日志获取详细信息")

if __name__ == '__main__':
    asyncio.run(main())