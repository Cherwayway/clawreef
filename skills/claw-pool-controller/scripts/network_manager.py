#!/usr/bin/env python3
"""
Claw Pool Controller - Network Manager (Phase 2)

网络管理和部署服务：
- SSL/TLS 安全通信支持
- 跨网络部署配置
- 证书管理和轮换
- 网络质量监控

Usage:
    python network_manager.py --init-ssl          # 初始化SSL证书
    python network_manager.py --start-secure     # 启动安全服务
    python network_manager.py --check-network    # 网络质量检查
    python network_manager.py --tailscale-setup  # Tailscale配置
"""

import asyncio
import json
import argparse
import ssl
import socket
import subprocess
import ipaddress
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import aiohttp
import cryptography
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.ssl_cert_path = None
        self.ssl_key_path = None
        self.ca_cert_path = None

        # 网络监控数据
        self.network_stats = {}
        self.connection_pool = {}

        self.load_config()

    def _get_default_config_path(self) -> str:
        """获取默认网络配置路径"""
        openclaw_dir = Path.home() / ".openclaw" / "network"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        return str(openclaw_dir / "network_config.json")

    def load_config(self):
        """加载网络配置"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)

                self.ssl_cert_path = config.get('ssl', {}).get('cert_path')
                self.ssl_key_path = config.get('ssl', {}).get('key_path')
                self.ca_cert_path = config.get('ssl', {}).get('ca_path')

                logger.info(f"网络配置已加载: {self.config_path}")
            else:
                # 创建默认配置
                self.create_default_config()
        except Exception as e:
            logger.error(f"加载网络配置失败: {e}")
            self.create_default_config()

    def create_default_config(self):
        """创建默认网络配置"""
        openclaw_dir = Path.home() / ".openclaw"
        network_dir = openclaw_dir / "network"
        ssl_dir = network_dir / "ssl"
        ssl_dir.mkdir(parents=True, exist_ok=True)

        default_config = {
            "ssl": {
                "enabled": True,
                "cert_path": str(ssl_dir / "server.crt"),
                "key_path": str(ssl_dir / "server.key"),
                "ca_path": str(ssl_dir / "ca.crt"),
                "cert_validity_days": 365,
                "auto_renew": True
            },
            "network": {
                "bind_host": "0.0.0.0",
                "bind_port": 18789,
                "secure_port": 18790,
                "max_connections": 1000,
                "connection_timeout": 30,
                "keepalive_interval": 30
            },
            "tailscale": {
                "enabled": False,
                "advertise_routes": [],
                "accept_routes": True,
                "exit_node": False
            },
            "discovery": {
                "mdns_enabled": True,
                "broadcast_interval": 60,
                "network_scan_enabled": True,
                "trusted_networks": ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"]
            },
            "security": {
                "require_authentication": True,
                "allowed_origins": ["*"],
                "rate_limit": {
                    "enabled": True,
                    "requests_per_minute": 100
                }
            }
        }

        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)

        # 更新路径
        self.ssl_cert_path = default_config["ssl"]["cert_path"]
        self.ssl_key_path = default_config["ssl"]["key_path"]
        self.ca_cert_path = default_config["ssl"]["ca_path"]

        logger.info(f"默认网络配置已创建: {self.config_path}")

    async def init_ssl_certificates(self) -> bool:
        """初始化SSL证书"""
        logger.info("初始化SSL证书...")

        try:
            # 创建SSL目录
            ssl_dir = Path(self.ssl_cert_path).parent
            ssl_dir.mkdir(parents=True, exist_ok=True)

            # 生成CA证书
            ca_key, ca_cert = self._generate_ca_certificate()

            # 生成服务器证书
            server_key, server_cert = self._generate_server_certificate(ca_key, ca_cert)

            # 保存证书文件
            self._save_certificate(self.ca_cert_path, ca_cert)
            self._save_private_key(self.ca_cert_path.replace('.crt', '.key'), ca_key)
            self._save_certificate(self.ssl_cert_path, server_cert)
            self._save_private_key(self.ssl_key_path, server_key)

            logger.info("SSL证书初始化成功")
            return True

        except Exception as e:
            logger.error(f"SSL证书初始化失败: {e}")
            return False

    def _generate_ca_certificate(self) -> Tuple:
        """生成CA证书"""
        # 生成私钥
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # 创建证书
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Claw Pool"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Claw Pool CA"),
        ])

        ca_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            ca_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=3650)  # 10年有效期
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                crl_sign=True,
                digital_signature=False,
                key_encipherment=False,
                key_agreement=False,
                content_commitment=False,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True,
        ).sign(ca_key, hashes.SHA256())

        return ca_key, ca_cert

    def _generate_server_certificate(self, ca_key, ca_cert) -> Tuple:
        """生成服务器证书"""
        # 生成服务器私钥
        server_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # 获取本机IP地址
        local_ips = self._get_local_ip_addresses()

        # 创建SAN扩展
        san_list = [
            x509.DNSName("localhost"),
            x509.DNSName(socket.getfqdn()),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]

        # 添加所有本地IP
        for ip in local_ips:
            try:
                if ':' in ip:  # IPv6
                    san_list.append(x509.IPAddress(ipaddress.IPv6Address(ip)))
                else:  # IPv4
                    san_list.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
            except Exception:
                pass

        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Claw Pool"),
            x509.NameAttribute(NameOID.COMMON_NAME, socket.getfqdn()),
        ])

        server_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            server_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        ).add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                content_commitment=False,
                data_encipherment=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True,
        ).add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=True,
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        ).sign(ca_key, hashes.SHA256())

        return server_key, server_cert

    def _get_local_ip_addresses(self) -> List[str]:
        """获取本机所有IP地址"""
        ip_addresses = []

        # 获取所有网络接口
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:  # IPv4
                    if not addr.address.startswith('127.'):
                        ip_addresses.append(addr.address)
                elif addr.family == socket.AF_INET6:  # IPv6
                    if not addr.address.startswith('::1'):
                        ip_addresses.append(addr.address)

        return ip_addresses

    def _save_certificate(self, path: str, cert):
        """保存证书到文件"""
        with open(path, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # 设置适当的权限
        Path(path).chmod(0o644)

    def _save_private_key(self, path: str, key):
        """保存私钥到文件"""
        with open(path, 'wb') as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # 设置严格权限
        Path(path).chmod(0o600)

    def create_ssl_context(self, server_side: bool = True) -> ssl.SSLContext:
        """创建SSL上下文"""
        if server_side:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            if self.ssl_cert_path and Path(self.ssl_cert_path).exists():
                context.load_cert_chain(self.ssl_cert_path, self.ssl_key_path)
            else:
                logger.warning("SSL证书不存在，创建自签名证书")
                asyncio.create_task(self.init_ssl_certificates())
        else:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            if self.ca_cert_path and Path(self.ca_cert_path).exists():
                context.load_verify_locations(self.ca_cert_path)
            context.check_hostname = False  # 允许自签名证书
            context.verify_mode = ssl.CERT_NONE  # 在开发环境中

        return context

    async def setup_tailscale(self) -> bool:
        """配置Tailscale网络"""
        logger.info("配置Tailscale网络...")

        try:
            # 检查Tailscale是否已安装
            result = subprocess.run(['tailscale', '--version'],
                                  capture_output=True, text=True)

            if result.returncode != 0:
                logger.error("Tailscale未安装，请先安装Tailscale")
                return False

            # 获取当前状态
            status_result = subprocess.run(['tailscale', 'status', '--json'],
                                         capture_output=True, text=True)

            if status_result.returncode == 0:
                status = json.loads(status_result.stdout)

                if status.get('BackendState') == 'Running':
                    logger.info("Tailscale已连接")

                    # 配置路由广播
                    with open(self.config_path, 'r') as f:
                        config = json.load(f)

                    routes = config.get('tailscale', {}).get('advertise_routes', [])
                    if routes:
                        route_args = ['tailscale', 'up', '--advertise-routes=' + ','.join(routes)]
                        subprocess.run(route_args)
                        logger.info(f"已配置路由广播: {routes}")

                    return True
                else:
                    logger.warning("Tailscale未连接，请运行 'tailscale up'")
                    return False
            else:
                logger.error("无法获取Tailscale状态")
                return False

        except Exception as e:
            logger.error(f"Tailscale配置失败: {e}")
            return False

    async def check_network_quality(self) -> Dict:
        """检查网络质量和连通性"""
        logger.info("检查网络质量...")

        results = {
            "timestamp": datetime.now().isoformat(),
            "local_interfaces": [],
            "external_connectivity": {},
            "tailscale_status": {},
            "port_availability": {},
            "performance": {}
        }

        try:
            # 检查本地网络接口
            results["local_interfaces"] = await self._check_local_interfaces()

            # 检查外部连通性
            results["external_connectivity"] = await self._check_external_connectivity()

            # 检查Tailscale状态
            results["tailscale_status"] = await self._check_tailscale_status()

            # 检查端口可用性
            results["port_availability"] = await self._check_port_availability()

            # 性能测试
            results["performance"] = await self._run_performance_tests()

        except Exception as e:
            logger.error(f"网络质量检查失败: {e}")
            results["error"] = str(e)

        return results

    async def _check_local_interfaces(self) -> List[Dict]:
        """检查本地网络接口"""
        interfaces = []

        for interface, addrs in psutil.net_if_addrs().items():
            interface_info = {
                "name": interface,
                "addresses": [],
                "is_up": interface in psutil.net_if_stats() and psutil.net_if_stats()[interface].isup
            }

            for addr in addrs:
                if addr.family == socket.AF_INET:
                    interface_info["addresses"].append({
                        "type": "IPv4",
                        "address": addr.address,
                        "netmask": addr.netmask
                    })
                elif addr.family == socket.AF_INET6:
                    interface_info["addresses"].append({
                        "type": "IPv6",
                        "address": addr.address
                    })

            interfaces.append(interface_info)

        return interfaces

    async def _check_external_connectivity(self) -> Dict:
        """检查外部网络连通性"""
        connectivity = {}

        test_hosts = [
            ("google.com", 80),
            ("cloudflare.com", 443),
            ("github.com", 443)
        ]

        for host, port in test_hosts:
            try:
                start_time = asyncio.get_event_loop().time()
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=5
                )
                end_time = asyncio.get_event_loop().time()

                writer.close()
                await writer.wait_closed()

                connectivity[host] = {
                    "status": "reachable",
                    "latency_ms": round((end_time - start_time) * 1000, 2)
                }
            except Exception as e:
                connectivity[host] = {
                    "status": "unreachable",
                    "error": str(e)
                }

        return connectivity

    async def _check_tailscale_status(self) -> Dict:
        """检查Tailscale状态"""
        try:
            result = subprocess.run(['tailscale', 'status', '--json'],
                                  capture_output=True, text=True)

            if result.returncode == 0:
                status = json.loads(result.stdout)
                return {
                    "installed": True,
                    "connected": status.get('BackendState') == 'Running',
                    "self_ip": status.get('Self', {}).get('TailscaleIPs', []),
                    "peer_count": len(status.get('Peer', {})),
                    "status": status.get('BackendState', 'Unknown')
                }
            else:
                return {"installed": True, "connected": False, "error": result.stderr}

        except FileNotFoundError:
            return {"installed": False}
        except Exception as e:
            return {"installed": True, "error": str(e)}

    async def _check_port_availability(self) -> Dict:
        """检查关键端口的可用性"""
        ports_to_check = [18789, 18790, 8080, 22]  # Pool ports, web UI, SSH
        results = {}

        for port in ports_to_check:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result == 0:
                    results[port] = "in_use"
                else:
                    results[port] = "available"

            except Exception as e:
                results[port] = f"error: {e}"

        return results

    async def _run_performance_tests(self) -> Dict:
        """运行网络性能测试"""
        performance = {}

        try:
            # 测试DNS解析速度
            start_time = asyncio.get_event_loop().time()
            await asyncio.get_event_loop().getaddrinfo('google.com', None)
            dns_time = (asyncio.get_event_loop().time() - start_time) * 1000
            performance["dns_resolution_ms"] = round(dns_time, 2)

            # 测试本地回环延迟
            start_time = asyncio.get_event_loop().time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('127.0.0.1', 80))
            sock.close()
            loopback_time = (asyncio.get_event_loop().time() - start_time) * 1000
            performance["loopback_latency_ms"] = round(loopback_time, 2)

        except Exception as e:
            performance["error"] = str(e)

        return performance

    def get_network_info(self) -> Dict:
        """获取当前网络配置信息"""
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        return {
            "config_path": self.config_path,
            "ssl_enabled": config.get('ssl', {}).get('enabled', False),
            "ssl_cert_exists": self.ssl_cert_path and Path(self.ssl_cert_path).exists(),
            "bind_port": config.get('network', {}).get('bind_port', 18789),
            "secure_port": config.get('network', {}).get('secure_port', 18790),
            "tailscale_enabled": config.get('tailscale', {}).get('enabled', False),
            "mdns_enabled": config.get('discovery', {}).get('mdns_enabled', True)
        }

def print_network_info(manager: NetworkManager):
    """打印网络配置信息"""
    info = manager.get_network_info()

    print("🌐 网络配置信息")
    print(f"   配置文件: {info['config_path']}")
    print(f"   SSL启用: {'✅' if info['ssl_enabled'] else '❌'}")
    print(f"   SSL证书: {'✅' if info['ssl_cert_exists'] else '❌'}")
    print(f"   标准端口: {info['bind_port']}")
    print(f"   安全端口: {info['secure_port']}")
    print(f"   Tailscale: {'✅' if info['tailscale_enabled'] else '❌'}")
    print(f"   mDNS发现: {'✅' if info['mdns_enabled'] else '❌'}")

async def print_network_quality(manager: NetworkManager):
    """打印网络质量检查结果"""
    quality = await manager.check_network_quality()

    print("📊 网络质量检查")
    print(f"   检查时间: {quality['timestamp']}")

    # 本地接口
    print(f"\n🔌 本地网络接口 ({len(quality['local_interfaces'])} 个):")
    for interface in quality['local_interfaces']:
        status = "✅" if interface['is_up'] else "❌"
        print(f"   {status} {interface['name']}")
        for addr in interface['addresses']:
            print(f"     {addr['type']}: {addr['address']}")

    # 外部连通性
    print(f"\n🌍 外部连通性:")
    for host, result in quality['external_connectivity'].items():
        if result['status'] == 'reachable':
            print(f"   ✅ {host} ({result['latency_ms']}ms)")
        else:
            print(f"   ❌ {host} ({result.get('error', 'unreachable')})")

    # Tailscale状态
    ts = quality['tailscale_status']
    if ts.get('installed'):
        if ts.get('connected'):
            print(f"\n🔗 Tailscale: ✅ 已连接")
            print(f"   IP地址: {', '.join(ts.get('self_ip', []))}")
            print(f"   对等节点: {ts.get('peer_count', 0)} 个")
        else:
            print(f"\n🔗 Tailscale: ❌ 未连接")
    else:
        print(f"\n🔗 Tailscale: ❌ 未安装")

    # 端口状态
    print(f"\n🔌 端口状态:")
    for port, status in quality['port_availability'].items():
        icon = "🔴" if status == "in_use" else "🟢" if status == "available" else "❓"
        print(f"   {icon} 端口 {port}: {status}")

    # 性能指标
    if 'error' not in quality['performance']:
        print(f"\n⚡ 性能指标:")
        perf = quality['performance']
        if 'dns_resolution_ms' in perf:
            print(f"   DNS解析: {perf['dns_resolution_ms']}ms")
        if 'loopback_latency_ms' in perf:
            print(f"   本地延迟: {perf['loopback_latency_ms']}ms")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Network Manager')
    parser.add_argument('--init-ssl', action='store_true',
                       help='初始化SSL证书')
    parser.add_argument('--check-network', action='store_true',
                       help='检查网络质量')
    parser.add_argument('--tailscale-setup', action='store_true',
                       help='配置Tailscale')
    parser.add_argument('--info', action='store_true',
                       help='显示网络配置信息')
    parser.add_argument('--config-path', type=str,
                       help='配置文件路径')

    args = parser.parse_args()

    manager = NetworkManager(args.config_path)

    if args.init_ssl:
        success = await manager.init_ssl_certificates()
        print("✅ SSL证书初始化成功" if success else "❌ SSL证书初始化失败")

    elif args.check_network:
        await print_network_quality(manager)

    elif args.tailscale_setup:
        success = await manager.setup_tailscale()
        print("✅ Tailscale配置成功" if success else "❌ Tailscale配置失败")

    elif args.info:
        print_network_info(manager)

    else:
        print("请指定操作：--init-ssl, --check-network, --tailscale-setup, 或 --info")

if __name__ == '__main__':
    asyncio.run(main())
