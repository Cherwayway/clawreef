#!/usr/bin/env uv run python
"""
ClawReef CLI - 龙虾池连接工具

极简的龙虾池创建和加入工具：
- uv run python reef_cli.py create --name "My Reef" → 启动 Controller 并输出邀请码
- uv run python reef_cli.py join <invite_code> → 连接到池
"""

import argparse
import asyncio
import base64
import json
import logging
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import os

# 添加项目路径以导入测试代码
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 导入已有的 WebSocket 通信类
try:
    from tests.cross_process_test_final import FinalControllerProcess, FinalAgentProcess
except ImportError as e:
    print(f"错误: 无法导入 WebSocket 通信模块: {e}")
    print(f"项目根目录: {project_root}")
    print("请检查项目结构或安装依赖")
    sys.exit(1)

# 默认配置
DEFAULT_PORT = 18789
REEF_CODE_PREFIX = "reef_"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """设置日志配置"""
    logger = logging.getLogger("reef_cli")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def detect_network_addresses() -> List[str]:
    """自动检测网络地址（局域网 IP + Tailscale IP）"""
    addresses = []

    try:
        # 使用 UDP socket 连接外部地址获取本地 IP（最可靠的方法）
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            if local_ip and local_ip not in addresses:
                addresses.append(local_ip)
    except Exception:
        pass

    try:
        # 检查是否有 Tailscale IP (100.x.x.x 网段)
        result = subprocess.run(['tailscale', 'ip'], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            tailscale_ip = result.stdout.strip()
            if tailscale_ip.startswith('100.') and tailscale_ip not in addresses:
                addresses.append(tailscale_ip)
    except Exception:
        pass

    # 确保至少有一个地址
    if not addresses:
        addresses.append('localhost')

    return addresses


def check_tunnel_availability() -> Dict[str, bool]:
    """检测可用的隧道工具"""
    tunnels = {}

    # 检测 ngrok
    try:
        result = subprocess.run(['ngrok', 'version'],
                                capture_output=True, text=True, timeout=5)
        tunnels['ngrok'] = result.returncode == 0
    except Exception:
        tunnels['ngrok'] = False

    # 检测 cloudflared
    try:
        result = subprocess.run(['cloudflared', '--version'],
                                capture_output=True, text=True, timeout=5)
        tunnels['cloudflare'] = result.returncode == 0
    except Exception:
        tunnels['cloudflare'] = False

    # 检测 tailscale (已经在 detect_network_addresses 中检测)
    try:
        result = subprocess.run(['tailscale', 'status'],
                                capture_output=True, text=True, timeout=5)
        tunnels['tailscale'] = result.returncode == 0
    except Exception:
        tunnels['tailscale'] = False

    return tunnels


def create_ngrok_tunnel(port: int) -> Optional[str]:
    """创建 ngrok 隧道"""
    try:
        print("🔗 创建 ngrok 隧道...")

        # 启动 ngrok 隧道
        process = subprocess.Popen(
            ['ngrok', 'http', str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # 等待隧道启动
        time.sleep(3)

        # 获取隧道信息
        try:
            import requests
            response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=5)
            data = response.json()

            for tunnel in data.get('tunnels', []):
                if tunnel.get('proto') == 'https':
                    public_url = tunnel.get('public_url')
                    if public_url:
                        # 转换为 WebSocket URL
                        ws_url = public_url.replace('https://', 'wss://')
                        print(f"✅ ngrok 隧道已创建: {ws_url}")
                        return ws_url
        except Exception:
            pass

        print("⚠️  无法获取 ngrok 隧道信息")
        return None

    except Exception as e:
        print(f"❌ 创建 ngrok 隧道失败: {e}")
        return None


def create_cloudflare_tunnel(port: int) -> Optional[str]:
    """创建 Cloudflare 隧道 (简化实现)"""
    try:
        print("🔗 检测 Cloudflare 隧道...")
        # 这里只是检测工具是否可用，实际使用需要用户配置
        # 完整实现需要用户预先配置 cloudflared
        print("⚠️  Cloudflare Tunnel 需要预先配置，请参考官方文档")
        return None
    except Exception as e:
        print(f"❌ Cloudflare 隧道检测失败: {e}")
        return None


def setup_tunnel(tunnel_type: str, port: int) -> Optional[str]:
    """设置隧道并返回公网 URL"""
    if tunnel_type == 'ngrok':
        return create_ngrok_tunnel(port)
    elif tunnel_type == 'cloudflare':
        return create_cloudflare_tunnel(port)
    elif tunnel_type == 'auto':
        # 自动选择可用的隧道
        available = check_tunnel_availability()
        print(f"🔍 检测到可用隧道工具: {[k for k, v in available.items() if v]}")

        # 优先级: ngrok > cloudflare > tailscale
        if available.get('ngrok'):
            return create_ngrok_tunnel(port)
        elif available.get('cloudflare'):
            return create_cloudflare_tunnel(port)
        elif available.get('tailscale'):
            print("✅ 检测到 Tailscale，已在网络地址中包含")
            return None
        else:
            print("⚠️  未检测到可用的隧道工具")
            return None

    return None


def generate_invite_code(name: str, hosts: List[str], port: int, tunnel_url: Optional[str] = None) -> str:
    """生成邀请码"""
    invite_data = {
        "name": name,
        "hosts": hosts,
        "port": port,
        "created": int(time.time())
    }

    # 如果有隧道 URL，添加到邀请码中
    if tunnel_url:
        invite_data["tunnel_url"] = tunnel_url

    json_data = json.dumps(invite_data)
    encoded_data = base64.b64encode(json_data.encode()).decode()

    return f"{REEF_CODE_PREFIX}{encoded_data}"


def parse_invite_code(invite_code: str) -> Dict[str, Any]:
    """解析邀请码"""
    if not invite_code.startswith(REEF_CODE_PREFIX):
        raise ValueError(f"邀请码必须以 '{REEF_CODE_PREFIX}' 开头")

    encoded_data = invite_code[len(REEF_CODE_PREFIX):]

    try:
        json_data = base64.b64decode(encoded_data).decode()
        return json.loads(json_data)
    except Exception as e:
        raise ValueError(f"邀请码格式错误: {e}")


class ReefController:
    """龙虾池 Controller 包装器"""

    def __init__(self, name: str, port: int = DEFAULT_PORT, tunnel: str = "auto"):
        self.name = name
        self.port = port
        self.tunnel_type = tunnel
        self.hosts = detect_network_addresses()
        self.tunnel_url = None
        self.controller = None
        self.logger = setup_logging()

    def get_invite_code(self) -> str:
        """获取邀请码"""
        return generate_invite_code(self.name, self.hosts, self.port, self.tunnel_url)

    async def start(self):
        """启动 Controller"""
        print(f"🚀 启动龙虾池: {self.name}")
        print(f"📡 监听端口: {self.port}")
        print(f"🌐 可用地址: {', '.join(self.hosts)}")

        # 设置隧道（如果需要）
        if self.tunnel_type != "none":
            print(f"🔍 检测隧道工具...")
            self.tunnel_url = setup_tunnel(self.tunnel_type, self.port)
            if self.tunnel_url:
                print(f"📡 公网地址: {self.tunnel_url}")

        # 创建 Controller 实例
        self.controller = FinalControllerProcess(host='0.0.0.0', port=self.port)

        # 显示邀请码
        invite_code = self.get_invite_code()
        print("=" * 60)
        print("🎯 邀请码生成成功！")
        print(f"📋 邀请码: {invite_code}")
        print("=" * 60)
        print("📤 分享此邀请码给其他用户，他们可以使用以下命令加入:")
        print(f"   uv run python reef_cli.py join {invite_code}")
        print("=" * 60)
        sys.stdout.flush()

        # 启动服务器
        await self.controller.start_server()


class ReefAgent:
    """龙虾池 Agent 包装器"""

    def __init__(self, invite_code: str):
        self.invite_code = invite_code
        self.invite_data = parse_invite_code(invite_code)
        self.agent = None
        self.logger = setup_logging()

        # 生成 Agent ID 和基本配置
        self.agent_id = f"reef-agent-{str(uuid.uuid4())[:8]}"
        self.agent_name = f"Agent {self.agent_id}"
        self.capabilities = ['python', 'data-analysis', 'calculation', 'generic']

    async def connect(self):
        """连接到龙虾池"""
        pool_name = self.invite_data.get('name', 'Unknown Pool')
        hosts = self.invite_data.get('hosts', [])
        port = self.invite_data.get('port', DEFAULT_PORT)
        tunnel_url = self.invite_data.get('tunnel_url')
        created = self.invite_data.get('created', 0)

        self.logger.info(f"🌊 准备加入龙虾池: {pool_name}")
        self.logger.info(f"🌐 可选地址: {', '.join(hosts)}")
        self.logger.info(f"📡 端口: {port}")
        if tunnel_url:
            self.logger.info(f"🌍 公网地址: {tunnel_url}")

        created_time = datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f"📅 池创建时间: {created_time}")

        # 优先尝试隧道连接（如果有）
        connected = False
        connection_attempts = []

        # 添加隧道 URL 到连接尝试列表（如果有）
        if tunnel_url:
            connection_attempts.append(('tunnel', tunnel_url, None))

        # 添加常规地址到连接尝试列表
        for host in hosts:
            connection_attempts.append(('host', host, port))

        # 尝试连接
        for connection_type, address, addr_port in connection_attempts:
            try:
                if connection_type == 'tunnel':
                    self.logger.info(f"🔗 尝试隧道连接: {address}")
                    # 创建隧道连接的 Agent
                    agent = ReefAgentTunnelClient(self.agent_id, self.agent_name, self.capabilities, address)
                    await agent.connect_to_controller()
                else:
                    self.logger.info(f"🔗 尝试连接: {address}:{addr_port}")
                    # 创建常规连接的 Agent
                    agent = ReefAgentClient(self.agent_id, self.agent_name, self.capabilities, address, addr_port)
                    await agent.connect_to_controller()

                connected = True
                self.logger.info(f"✅ 成功连接到龙虾池！")
                self.logger.info(f"🆔 Agent ID: {self.agent_id}")
                break

            except Exception as e:
                if connection_type == 'tunnel':
                    self.logger.warning(f"❌ 隧道连接失败: {e}")
                else:
                    self.logger.warning(f"❌ 连接 {address}:{addr_port} 失败: {e}")
                continue

        if not connected:
            self.logger.error("❌ 无法连接到任何地址，请检查:")
            self.logger.error("   1. 网络连接是否正常")
            self.logger.error("   2. Controller 是否在运行")
            self.logger.error("   3. 邀请码是否有效")
            raise ConnectionError("无法连接到龙虾池")


class ReefAgentTunnelClient(FinalAgentProcess):
    """隧道连接的 Agent 客户端"""

    def __init__(self, agent_id: str, name: str, capabilities: List[str], tunnel_url: str):
        super().__init__(agent_id, name, capabilities)
        self.controller_url = tunnel_url
        self.logger = setup_logging()

    async def connect_to_controller(self):
        """通过隧道连接到 Controller"""
        try:
            self.logger.info(f"🔗 通过隧道连接到 Controller: {self.controller_url}")

            # 导入 websockets 模块
            import websockets

            self.websocket = await websockets.connect(
                self.controller_url,
                ping_interval=20,
                ping_timeout=10
            )

            self.logger.info(f"✅ 隧道 WebSocket 连接成功")
            self.running = True

            # 注册
            await self.register_to_controller()

            # 启动心跳
            asyncio.create_task(self.heartbeat_loop())

            # 监听任务
            await self.listen_for_tasks()

        except Exception as e:
            self.logger.error(f"❌ 隧道连接失败: {e}")
            raise


class ReefAgentClient(FinalAgentProcess):
    """自定义的 Agent 客户端"""

    def __init__(self, agent_id: str, name: str, capabilities: List[str], host: str, port: int):
        super().__init__(agent_id, name, capabilities)
        self.controller_url = f"ws://{host}:{port}"
        self.logger = setup_logging()
        self.host = host
        self.port = port

    async def connect_to_controller(self):
        """连接到指定的 Controller"""
        try:
            self.logger.info(f"🔗 连接到 Controller: {self.controller_url}")

            # 导入 websockets 模块
            import websockets

            self.websocket = await websockets.connect(
                self.controller_url,
                ping_interval=20,
                ping_timeout=10
            )

            self.logger.info(f"✅ WebSocket 连接成功")
            self.running = True

            # 注册
            await self.register_to_controller()

            # 启动心跳
            asyncio.create_task(self.heartbeat_loop())

            # 监听任务
            await self.listen_for_tasks()

        except Exception as e:
            self.logger.error(f"❌ 连接失败: {e}")
            raise


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="ClawReef - 龙虾池连接工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  创建龙虾池:
    uv run python reef_cli.py create --name "Cherway's Reef"

  加入龙虾池:
    uv run python reef_cli.py join reef_eyJuYW1lIjoiQ2hlcndheSdzIFJlZWYiLCJob3N0cyI6WyIxOTIuMTY4LjEuMTAwIl0sInBvcnQiOjE4Nzg5LCJjcmVhdGVkIjoxNzA5NjI1NjAwfQ==
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # create 命令
    create_parser = subparsers.add_parser('create', help='创建龙虾池')
    create_parser.add_argument('--name', required=True, help='龙虾池名称')
    create_parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'端口号 (默认: {DEFAULT_PORT})')
    create_parser.add_argument('--tunnel', choices=['auto', 'ngrok', 'cloudflare', 'none'],
                               default='auto', help='隧道类型 (默认: auto)')
    create_parser.add_argument('--verbose', '-v', action='store_true', help='详细日志')

    # join 命令
    join_parser = subparsers.add_parser('join', help='加入龙虾池')
    join_parser.add_argument('invite_code', help='邀请码')
    join_parser.add_argument('--verbose', '-v', action='store_true', help='详细日志')

    args = parser.parse_args()

    # 设置日志级别
    log_level = "DEBUG" if getattr(args, 'verbose', False) else "INFO"
    logger = setup_logging(log_level)

    if args.command == 'create':
        # 创建龙虾池
        logger.info("🌊 ClawReef - 创建龙虾池")

        controller = ReefController(args.name, args.port, args.tunnel)

        try:
            asyncio.run(controller.start())
        except KeyboardInterrupt:
            logger.info("🛑 收到中断信号，正在关闭龙虾池...")
        except Exception as e:
            logger.error(f"❌ 创建龙虾池失败: {e}")
            sys.exit(1)

    elif args.command == 'join':
        # 加入龙虾池
        logger.info("🏊 ClawReef - 加入龙虾池")

        try:
            agent = ReefAgent(args.invite_code)
            asyncio.run(agent.connect())
        except ValueError as e:
            logger.error(f"❌ 邀请码错误: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            logger.info("🛑 收到中断信号，正在断开连接...")
        except Exception as e:
            logger.error(f"❌ 加入龙虾池失败: {e}")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
