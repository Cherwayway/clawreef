#!/usr/bin/env python3
"""
Claw Pool Agent - Discovery Script

发现网络中的 Pool Controller，支持多种发现方式：
- mDNS/Bonjour 本地网络发现
- Tailscale 网络扫描
- 手动地址验证

Usage:
    python discover.py --scan                    # 自动扫描所有方式
    python discover.py --mdns                    # 只使用 mDNS 发现
    python discover.py --manual <url>            # 手动验证指定地址
"""

import asyncio
import json
import argparse
import subprocess
import socket
import websockets
import aiohttp
from typing import List, Optional, Dict
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PoolControllerDiscovery:
    def __init__(self):
        self.discovered_controllers = []
        self.timeout = 5  # 连接超时秒数

    async def discover_all(self) -> List[Dict]:
        """使用所有可用方式发现 Pool Controller"""
        logger.info("开始全方位扫描 Pool Controller...")

        tasks = [
            self.discover_mdns(),
            self.discover_tailscale(),
            self.discover_common_ports()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果并去重
        all_controllers = []
        for result in results:
            if isinstance(result, list):
                all_controllers.extend(result)

        # 按优先级排序：本地 > tailscale > 远程
        all_controllers.sort(key=self._priority_key)

        return self._deduplicate(all_controllers)

    async def discover_mdns(self) -> List[Dict]:
        """使用 mDNS/Bonjour 发现本地网络中的 Pool Controller"""
        logger.info("扫描本地网络 (mDNS)...")
        controllers = []

        try:
            # 使用 dns-sd 命令扫描 OpenClaw 服务
            result = subprocess.run([
                'dns-sd', '-B', '_openclaw._tcp'
            ], capture_output=True, text=True, timeout=self.timeout)

            if result.returncode == 0:
                # 解析 dns-sd 输出
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'pool-controller' in line.lower():
                        # 提取服务信息
                        parts = line.split()
                        if len(parts) >= 4:
                            service_name = parts[3]
                            controllers.append({
                                'type': 'mdns',
                                'name': service_name,
                                'url': f'ws://{service_name}.local:18789',
                                'priority': 1,
                                'discovered_by': 'mDNS'
                            })
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"mDNS 扫描失败: {e}")

        logger.info(f"mDNS 发现 {len(controllers)} 个 Controller")
        return controllers

    async def discover_tailscale(self) -> List[Dict]:
        """扫描 Tailscale 网络中的 Pool Controller"""
        logger.info("扫描 Tailscale 网络...")
        controllers = []

        try:
            # 获取 Tailscale 网络中的设备
            result = subprocess.run([
                'tailscale', 'status', '--json'
            ], capture_output=True, text=True, timeout=self.timeout)

            if result.returncode == 0:
                status = json.loads(result.stdout)
                peers = status.get('Peer', {})

                # 检查每个 peer 是否运行 Pool Controller
                check_tasks = []
                for peer_key, peer_info in peers.items():
                    if peer_info.get('Online'):
                        ip = peer_info.get('TailscaleIPs', [None])[0]
                        if ip:
                            check_tasks.append(
                                self._check_controller_at_ip(ip, 'tailscale', peer_info.get('HostName', ip))
                            )

                if check_tasks:
                    results = await asyncio.gather(*check_tasks, return_exceptions=True)
                    controllers = [r for r in results if isinstance(r, dict)]

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Tailscale 扫描失败: {e}")

        logger.info(f"Tailscale 发现 {len(controllers)} 个 Controller")
        return controllers

    async def discover_common_ports(self) -> List[Dict]:
        """扫描常见端口和地址"""
        logger.info("扫描常见地址...")
        controllers = []

        # 常见的 Controller 地址
        common_addresses = [
            'localhost:18789',
            '127.0.0.1:18789',
            'pool-controller:18789',
            'claw-pool:18789'
        ]

        check_tasks = [
            self._check_controller_url(f'ws://{addr}', 'common_port')
            for addr in common_addresses
        ]

        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        controllers = [r for r in results if isinstance(r, dict)]

        logger.info(f"常见地址发现 {len(controllers)} 个 Controller")
        return controllers

    async def verify_manual_url(self, url: str) -> Optional[Dict]:
        """手动验证指定的 Controller URL"""
        logger.info(f"验证手动指定的地址: {url}")

        if not url.startswith('ws://') and not url.startswith('wss://'):
            url = f'ws://{url}'

        return await self._check_controller_url(url, 'manual')

    async def _check_controller_at_ip(self, ip: str, discovery_type: str, hostname: str) -> Optional[Dict]:
        """检查指定 IP 是否运行 Pool Controller"""
        url = f'ws://{ip}:18789'
        result = await self._check_controller_url(url, discovery_type)

        if result:
            result['hostname'] = hostname

        return result

    async def _check_controller_url(self, url: str, discovery_type: str) -> Optional[Dict]:
        """检查指定 URL 是否为有效的 Pool Controller"""
        try:
            # 首先检查端口是否可达
            host, port = self._parse_websocket_url(url)
            if not await self._check_port(host, port):
                return None

            # 尝试 WebSocket 连接
            async with websockets.connect(url, timeout=self.timeout) as websocket:
                # 发送 ping 消息
                ping_msg = {
                    "method": "ping",
                    "params": {"type": "pool-discovery"}
                }
                await websocket.send(json.dumps(ping_msg))

                # 等待响应
                response = await asyncio.wait_for(
                    websocket.recv(), timeout=self.timeout
                )

                response_data = json.loads(response)

                # 验证是否为 Pool Controller
                if (response_data.get('status') == 'ok' and
                    'pool-controller' in response_data.get('reply', '').lower()):

                    return {
                        'type': discovery_type,
                        'url': url,
                        'status': 'available',
                        'response': response_data,
                        'priority': self._get_priority(discovery_type),
                        'discovered_by': f'{discovery_type.title()} Discovery'
                    }

        except Exception as e:
            logger.debug(f"检查 {url} 失败: {e}")
            return None

    async def _check_port(self, host: str, port: int) -> bool:
        """检查端口是否可达"""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=2
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    def _parse_websocket_url(self, url: str) -> tuple:
        """解析 WebSocket URL 获取 host 和 port"""
        url = url.replace('ws://', '').replace('wss://', '')
        if ':' in url:
            host, port = url.split(':', 1)
            return host, int(port)
        return url, 80

    def _get_priority(self, discovery_type: str) -> int:
        """获取发现类型的优先级"""
        priority_map = {
            'mdns': 1,
            'common_port': 2,
            'tailscale': 3,
            'manual': 4
        }
        return priority_map.get(discovery_type, 10)

    def _priority_key(self, controller: Dict) -> int:
        """排序用的优先级键"""
        return controller.get('priority', 10)

    def _deduplicate(self, controllers: List[Dict]) -> List[Dict]:
        """根据 URL 去重"""
        seen_urls = set()
        unique_controllers = []

        for controller in controllers:
            url = controller.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_controllers.append(controller)

        return unique_controllers

def print_discovery_results(controllers: List[Dict]):
    """打印发现结果"""
    if not controllers:
        print("❌ 未发现任何 Pool Controller")
        print("\n建议:")
        print("1. 确保 Pool Controller 正在运行")
        print("2. 检查网络连接")
        print("3. 验证防火墙设置")
        return

    print(f"✅ 发现 {len(controllers)} 个 Pool Controller:\n")

    for i, controller in enumerate(controllers, 1):
        print(f"{i}. {controller['url']}")
        print(f"   类型: {controller['discovered_by']}")
        print(f"   状态: {controller.get('status', 'unknown')}")

        if 'hostname' in controller:
            print(f"   主机: {controller['hostname']}")

        if 'response' in controller:
            response = controller['response']
            if 'reply' in response:
                print(f"   信息: {response['reply'][:100]}")
        print()

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Controller Discovery')
    parser.add_argument('--scan', action='store_true',
                       help='扫描所有可用的发现方式')
    parser.add_argument('--mdns', action='store_true',
                       help='只使用 mDNS 发现')
    parser.add_argument('--tailscale', action='store_true',
                       help='只使用 Tailscale 发现')
    parser.add_argument('--manual', type=str,
                       help='手动验证指定的 Controller URL')
    parser.add_argument('--output', type=str,
                       help='将结果保存到 JSON 文件')
    parser.add_argument('--timeout', type=int, default=5,
                       help='连接超时时间（秒）')

    args = parser.parse_args()

    discovery = PoolControllerDiscovery()
    discovery.timeout = args.timeout

    controllers = []

    if args.manual:
        controller = await discovery.verify_manual_url(args.manual)
        if controller:
            controllers = [controller]
    elif args.mdns:
        controllers = await discovery.discover_mdns()
    elif args.tailscale:
        controllers = await discovery.discover_tailscale()
    else:
        # 默认或 --scan
        controllers = await discovery.discover_all()

    print_discovery_results(controllers)

    # 保存结果到文件
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(controllers, f, indent=2)
        print(f"\n结果已保存到: {args.output}")

if __name__ == '__main__':
    asyncio.run(main())