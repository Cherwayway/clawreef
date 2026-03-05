#!/usr/bin/env python3
"""
Claw Pool Controller - Federation Manager (Phase 2)

多Pool联邦管理：
- 跨Pool任务调度和负载均衡
- Pool间资源共享和发现
- 联邦安全和认证
- 跨域网络通信

Usage:
    python federation_manager.py --init-federation      # 初始化联邦配置
    python federation_manager.py --join-pool <url>      # 加入联邦Pool
    python federation_manager.py --list-pools           # 列出联邦Pool
    python federation_manager.py --federation-stats     # 联邦统计信息
    python federation_manager.py --start-coordinator    # 启动联邦协调器
"""

import asyncio
import json
import argparse
import sqlite3
import uuid
import aiohttp
import ssl
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
import logging
import hashlib
import hmac
from dataclasses import dataclass, asdict

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PoolStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    UNREACHABLE = "unreachable"

class FederationRole(Enum):
    COORDINATOR = "coordinator"        # 联邦协调者
    PARTICIPANT = "participant"       # 联邦参与者
    OBSERVER = "observer"             # 联邦观察者

@dataclass
class PoolInfo:
    pool_id: str
    name: str
    endpoint: str
    status: PoolStatus
    role: FederationRole
    capabilities: List[str]
    max_capacity: int
    current_load: int
    last_heartbeat: datetime
    trust_level: float          # 信任度 0.0-1.0
    region: str
    version: str

@dataclass
class FederatedTask:
    task_id: str
    original_pool: str
    target_pool: str
    task_data: Dict
    priority: int
    deadline: Optional[datetime]
    cost_limit: Optional[float]
    preferred_regions: List[str]

class FederationManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.db_path = self._get_database_path()

        # 联邦配置
        self.pool_id = None
        self.federation_id = None
        self.role = FederationRole.PARTICIPANT
        self.coordinator_endpoint = None

        # 认证配置
        self.api_key = None
        self.shared_secret = None

        # Pool注册表
        self.federated_pools = {}  # pool_id -> PoolInfo
        self.pool_capabilities = {}
        self.load_balancing_weights = {}

        # 统计信息
        self.federation_stats = {
            'tasks_routed': 0,
            'pools_discovered': 0,
            'cross_pool_executions': 0,
            'federation_errors': 0
        }

        self.init_database()
        self.load_config()

        # 网络连接池
        self.session = None
        self.running = False

    def _get_default_config_path(self) -> str:
        """获取默认联邦配置路径"""
        openclaw_dir = Path.home() / ".openclaw" / "federation"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        return str(openclaw_dir / "federation_config.json")

    def _get_database_path(self) -> str:
        """获取联邦数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_federation.db")

    def init_database(self):
        """初始化联邦数据库"""
        with sqlite3.connect(self.db_path) as conn:
            # 联邦Pool注册表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS federated_pools (
                    pool_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    status TEXT DEFAULT 'offline',
                    role TEXT DEFAULT 'participant',
                    capabilities TEXT,          -- JSON数组
                    max_capacity INTEGER DEFAULT 0,
                    current_load INTEGER DEFAULT 0,
                    last_heartbeat TIMESTAMP,
                    trust_level REAL DEFAULT 0.5,
                    region TEXT,
                    version TEXT,
                    joined_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 跨Pool任务路由记录
            conn.execute('''
                CREATE TABLE IF NOT EXISTS federated_tasks (
                    task_id TEXT PRIMARY KEY,
                    original_pool TEXT NOT NULL,
                    target_pool TEXT NOT NULL,
                    task_data TEXT NOT NULL,   -- JSON
                    priority INTEGER DEFAULT 2,
                    deadline TIMESTAMP,
                    cost_limit REAL,
                    preferred_regions TEXT,    -- JSON数组
                    status TEXT DEFAULT 'pending',
                    routed_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_time TIMESTAMP,
                    execution_cost REAL,
                    result TEXT                -- JSON
                )
            ''')

            # 联邦性能统计
            conn.execute('''
                CREATE TABLE IF NOT EXISTS federation_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    pool_count INTEGER,
                    total_capacity INTEGER,
                    avg_load_factor REAL,
                    cross_pool_tasks INTEGER,
                    network_latency REAL,
                    federation_efficiency REAL
                )
            ''')

            # 联邦认证和安全
            conn.execute('''
                CREATE TABLE IF NOT EXISTS federation_auth (
                    pool_id TEXT PRIMARY KEY,
                    api_key TEXT NOT NULL,
                    shared_secret TEXT NOT NULL,
                    permissions TEXT,          -- JSON数组
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_time TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

            conn.commit()
        logger.info(f"联邦数据库初始化完成: {self.db_path}")

    def load_config(self):
        """加载联邦配置"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)

                self.pool_id = config.get('pool_id')
                self.federation_id = config.get('federation_id')
                self.role = FederationRole(config.get('role', 'participant'))
                self.coordinator_endpoint = config.get('coordinator_endpoint')
                self.api_key = config.get('api_key')
                self.shared_secret = config.get('shared_secret')

                logger.info(f"联邦配置已加载: {self.pool_id}")
            else:
                self.create_default_config()
        except Exception as e:
            logger.error(f"加载联邦配置失败: {e}")
            self.create_default_config()

    def create_default_config(self):
        """创建默认联邦配置"""
        self.pool_id = f"pool_{uuid.uuid4().hex[:8]}"
        self.federation_id = "default_federation"
        self.api_key = self._generate_api_key()
        self.shared_secret = self._generate_shared_secret()

        default_config = {
            "pool_id": self.pool_id,
            "federation_id": self.federation_id,
            "role": self.role.value,
            "coordinator_endpoint": None,
            "api_key": self.api_key,
            "shared_secret": self.shared_secret,
            "discovery": {
                "enabled": True,
                "broadcast_interval": 30,
                "discovery_ports": [18791, 18792, 18793]
            },
            "routing": {
                "max_hops": 3,
                "timeout_seconds": 30,
                "retry_attempts": 2
            },
            "security": {
                "require_authentication": True,
                "encrypted_communication": True,
                "trusted_pools_only": False
            }
        }

        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)

        logger.info(f"创建默认联邦配置: {self.config_path}")

    async def init_federation(self, federation_name: str) -> str:
        """初始化新的联邦"""
        federation_id = f"fed_{uuid.uuid4().hex[:8]}"

        # 更新配置
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        config['federation_id'] = federation_id
        config['role'] = FederationRole.COORDINATOR.value
        self.federation_id = federation_id
        self.role = FederationRole.COORDINATOR

        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # 注册自己为协调者
        await self.register_pool(PoolInfo(
            pool_id=self.pool_id,
            name=federation_name,
            endpoint="http://localhost:18789",
            status=PoolStatus.ONLINE,
            role=FederationRole.COORDINATOR,
            capabilities=["general", "python", "data-analysis"],
            max_capacity=100,
            current_load=0,
            last_heartbeat=datetime.now(),
            trust_level=1.0,
            region="local",
            version="1.0.0"
        ))

        logger.info(f"联邦初始化完成: {federation_id}")
        return federation_id

    async def join_pool(self, pool_endpoint: str) -> bool:
        """加入联邦Pool"""
        try:
            async with aiohttp.ClientSession() as session:
                # 发现Pool信息
                discovery_url = f"{pool_endpoint}/api/federation/info"
                headers = self._create_auth_headers()

                async with session.get(discovery_url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        pool_data = await response.json()

                        pool_info = PoolInfo(
                            pool_id=pool_data["poolId"],
                            name=pool_data["name"],
                            endpoint=pool_endpoint,
                            status=PoolStatus.ONLINE,
                            role=FederationRole(pool_data.get("role", "participant")),
                            capabilities=pool_data.get("capabilities", []),
                            max_capacity=pool_data.get("maxCapacity", 0),
                            current_load=pool_data.get("currentLoad", 0),
                            last_heartbeat=datetime.now(),
                            trust_level=0.5,
                            region=pool_data.get("region", "unknown"),
                            version=pool_data.get("version", "unknown")
                        )

                        # 注册Pool
                        await self.register_pool(pool_info)

                        # 如果是协调者，请求加入联邦
                        if pool_info.role == FederationRole.COORDINATOR:
                            await self._request_federation_membership(pool_endpoint)

                        self.federation_stats['pools_discovered'] += 1
                        logger.info(f"成功加入Pool: {pool_info.name} ({pool_info.pool_id})")
                        return True
                    else:
                        logger.error(f"Pool连接失败: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"加入Pool失败: {e}")
            return False

    async def register_pool(self, pool_info: PoolInfo):
        """注册联邦Pool"""
        self.federated_pools[pool_info.pool_id] = pool_info

        # 保存到数据库
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO federated_pools (
                    pool_id, name, endpoint, status, role, capabilities,
                    max_capacity, current_load, last_heartbeat, trust_level,
                    region, version, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pool_info.pool_id, pool_info.name, pool_info.endpoint,
                pool_info.status.value, pool_info.role.value,
                json.dumps(pool_info.capabilities), pool_info.max_capacity,
                pool_info.current_load, pool_info.last_heartbeat.isoformat(),
                pool_info.trust_level, pool_info.region, pool_info.version,
                datetime.now().isoformat()
            ))
            conn.commit()

    async def route_federated_task(self, task_data: Dict, routing_preferences: Dict = None) -> Optional[str]:
        """路由联邦任务"""
        if not routing_preferences:
            routing_preferences = {}

        required_capabilities = task_data.get("capabilities", [])
        priority = task_data.get("priority", 2)
        preferred_regions = routing_preferences.get("regions", [])
        cost_limit = routing_preferences.get("costLimit")

        # 查找合适的Pool
        suitable_pools = self._find_suitable_pools(
            required_capabilities, preferred_regions, cost_limit
        )

        if not suitable_pools:
            logger.warning("没有找到合适的联邦Pool")
            return None

        # 选择最佳Pool
        target_pool = self._select_best_pool(suitable_pools, task_data)

        if not target_pool:
            return None

        # 创建联邦任务记录
        federated_task = FederatedTask(
            task_id=task_data.get("id", f"fed_task_{uuid.uuid4().hex[:12]}"),
            original_pool=self.pool_id,
            target_pool=target_pool.pool_id,
            task_data=task_data,
            priority=priority,
            deadline=None,
            cost_limit=cost_limit,
            preferred_regions=preferred_regions
        )

        # 提交任务到目标Pool
        success = await self._submit_task_to_pool(target_pool, federated_task)

        if success:
            # 保存路由记录
            await self._save_federated_task(federated_task)
            self.federation_stats['tasks_routed'] += 1
            logger.info(f"任务已路由到Pool {target_pool.name}: {federated_task.task_id}")
            return federated_task.task_id
        else:
            self.federation_stats['federation_errors'] += 1
            return None

    def _find_suitable_pools(self, capabilities: List[str], regions: List[str], cost_limit: float) -> List[PoolInfo]:
        """查找合适的Pool"""
        suitable_pools = []

        for pool in self.federated_pools.values():
            # 检查状态
            if pool.status != PoolStatus.ONLINE:
                continue

            # 检查能力匹配
            if capabilities and not all(cap in pool.capabilities for cap in capabilities):
                continue

            # 检查地理位置偏好
            if regions and pool.region not in regions:
                continue

            # 检查负载
            load_factor = pool.current_load / max(pool.max_capacity, 1)
            if load_factor > 0.9:  # 负载超过90%
                continue

            # 检查信任度
            if pool.trust_level < 0.3:
                continue

            suitable_pools.append(pool)

        return suitable_pools

    def _select_best_pool(self, pools: List[PoolInfo], task_data: Dict) -> Optional[PoolInfo]:
        """选择最佳Pool"""
        if not pools:
            return None

        # 计算每个Pool的评分
        pool_scores = []
        for pool in pools:
            score = self._calculate_pool_score(pool, task_data)
            pool_scores.append((score, pool))

        # 返回评分最高的Pool
        pool_scores.sort(key=lambda x: x[0], reverse=True)
        return pool_scores[0][1]

    def _calculate_pool_score(self, pool: PoolInfo, task_data: Dict) -> float:
        """计算Pool评分"""
        # 负载分数（负载越低分数越高）
        load_factor = pool.current_load / max(pool.max_capacity, 1)
        load_score = 1.0 - load_factor

        # 信任度分数
        trust_score = pool.trust_level

        # 能力匹配分数
        required_capabilities = task_data.get("capabilities", [])
        if required_capabilities:
            matched_capabilities = sum(1 for cap in required_capabilities if cap in pool.capabilities)
            capability_score = matched_capabilities / len(required_capabilities)
        else:
            capability_score = 1.0

        # 网络延迟分数（基于心跳时间）
        heartbeat_age = (datetime.now() - pool.last_heartbeat).total_seconds()
        latency_score = max(0, 1.0 - heartbeat_age / 300)  # 5分钟内心跳为满分

        # 综合评分
        final_score = (
            load_score * 0.3 +
            trust_score * 0.3 +
            capability_score * 0.25 +
            latency_score * 0.15
        )

        return final_score

    async def _submit_task_to_pool(self, pool: PoolInfo, federated_task: FederatedTask) -> bool:
        """向Pool提交任务"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            submit_url = f"{pool.endpoint}/api/federation/tasks"
            headers = self._create_auth_headers()

            payload = {
                "task": federated_task.task_data,
                "routing": {
                    "originalPool": federated_task.original_pool,
                    "priority": federated_task.priority,
                    "costLimit": federated_task.cost_limit,
                    "preferredRegions": federated_task.preferred_regions
                }
            }

            async with self.session.post(submit_url, json=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"任务提交成功: {result.get('taskId')}")
                    return True
                else:
                    logger.error(f"任务提交失败: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"提交任务到Pool失败: {e}")
            return False

    async def _save_federated_task(self, federated_task: FederatedTask):
        """保存联邦任务记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO federated_tasks (
                    task_id, original_pool, target_pool, task_data, priority,
                    deadline, cost_limit, preferred_regions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                federated_task.task_id, federated_task.original_pool,
                federated_task.target_pool, json.dumps(federated_task.task_data),
                federated_task.priority,
                federated_task.deadline.isoformat() if federated_task.deadline else None,
                federated_task.cost_limit,
                json.dumps(federated_task.preferred_regions)
            ))
            conn.commit()

    async def start_coordinator(self):
        """启动联邦协调器"""
        logger.info("启动联邦协调器...")
        self.running = True

        if not self.session:
            self.session = aiohttp.ClientSession()

        # 启动心跳监控
        heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

        # 启动Pool发现
        discovery_task = asyncio.create_task(self._pool_discovery())

        # 启动负载监控
        load_monitor_task = asyncio.create_task(self._load_monitor())

        try:
            await asyncio.gather(heartbeat_task, discovery_task, load_monitor_task)
        except KeyboardInterrupt:
            logger.info("联邦协调器停止")
        finally:
            await self.stop()

    async def _heartbeat_monitor(self):
        """心跳监控"""
        while self.running:
            try:
                for pool_id, pool in list(self.federated_pools.items()):
                    if pool_id == self.pool_id:  # 跳过自己
                        continue

                    # 检查心跳
                    success = await self._ping_pool(pool)

                    if success:
                        pool.status = PoolStatus.ONLINE
                        pool.last_heartbeat = datetime.now()
                    else:
                        # 连续失败后标记为离线
                        heartbeat_age = (datetime.now() - pool.last_heartbeat).total_seconds()
                        if heartbeat_age > 300:  # 5分钟无响应
                            pool.status = PoolStatus.UNREACHABLE

                    # 更新数据库
                    await self.register_pool(pool)

                await asyncio.sleep(30)  # 每30秒检查一次

            except Exception as e:
                logger.error(f"心跳监控出错: {e}")
                await asyncio.sleep(30)

    async def _ping_pool(self, pool: PoolInfo) -> bool:
        """Ping Pool检查连通性"""
        try:
            if not self.session:
                return False

            ping_url = f"{pool.endpoint}/api/federation/ping"
            headers = self._create_auth_headers()

            async with self.session.get(ping_url, headers=headers, timeout=10) as response:
                return response.status == 200

        except Exception:
            return False

    async def _pool_discovery(self):
        """Pool自动发现"""
        while self.running:
            try:
                # 广播发现请求
                await self._broadcast_discovery()

                # 监听发现响应
                await self._listen_discovery()

                await asyncio.sleep(60)  # 每分钟进行一次发现

            except Exception as e:
                logger.error(f"Pool发现出错: {e}")
                await asyncio.sleep(60)

    async def _broadcast_discovery(self):
        """广播发现请求"""
        # 简化实现：通过已知的协调者端点发现
        if self.coordinator_endpoint and self.role != FederationRole.COORDINATOR:
            await self.join_pool(self.coordinator_endpoint)

    async def _listen_discovery(self):
        """监听发现响应"""
        # 实际实现中应该监听UDP广播或多播消息
        pass

    async def _load_monitor(self):
        """负载监控"""
        while self.running:
            try:
                await self._update_federation_metrics()
                await asyncio.sleep(120)  # 每2分钟更新一次指标
            except Exception as e:
                logger.error(f"负载监控出错: {e}")
                await asyncio.sleep(120)

    async def _update_federation_metrics(self):
        """更新联邦指标"""
        total_pools = len(self.federated_pools)
        online_pools = sum(1 for p in self.federated_pools.values() if p.status == PoolStatus.ONLINE)
        total_capacity = sum(p.max_capacity for p in self.federated_pools.values())
        total_load = sum(p.current_load for p in self.federated_pools.values())
        avg_load_factor = (total_load / total_capacity) if total_capacity > 0 else 0

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO federation_metrics (
                    pool_count, total_capacity, avg_load_factor, cross_pool_tasks
                ) VALUES (?, ?, ?, ?)
            ''', (
                online_pools, total_capacity, avg_load_factor,
                self.federation_stats['cross_pool_executions']
            ))
            conn.commit()

    async def stop(self):
        """停止联邦管理器"""
        logger.info("停止联邦管理器...")
        self.running = False

        if self.session:
            await self.session.close()

    def get_federation_stats(self) -> Dict:
        """获取联邦统计信息"""
        pools_by_status = {}
        total_capacity = 0
        total_load = 0

        for pool in self.federated_pools.values():
            status = pool.status.value
            pools_by_status[status] = pools_by_status.get(status, 0) + 1
            total_capacity += pool.max_capacity
            total_load += pool.current_load

        return {
            "federationId": self.federation_id,
            "poolId": self.pool_id,
            "role": self.role.value,
            "totalPools": len(self.federated_pools),
            "poolsByStatus": pools_by_status,
            "totalCapacity": total_capacity,
            "totalLoad": total_load,
            "loadFactor": (total_load / total_capacity) if total_capacity > 0 else 0,
            "federationStats": self.federation_stats
        }

    def list_pools(self) -> List[Dict]:
        """列出联邦Pool"""
        pools_list = []
        for pool in self.federated_pools.values():
            pools_list.append({
                "poolId": pool.pool_id,
                "name": pool.name,
                "endpoint": pool.endpoint,
                "status": pool.status.value,
                "role": pool.role.value,
                "capabilities": pool.capabilities,
                "capacity": pool.max_capacity,
                "load": pool.current_load,
                "loadFactor": pool.current_load / max(pool.max_capacity, 1),
                "trustLevel": pool.trust_level,
                "region": pool.region,
                "lastHeartbeat": pool.last_heartbeat.isoformat()
            })
        return pools_list

    async def _request_federation_membership(self, coordinator_endpoint: str):
        """请求加入联邦"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            join_url = f"{coordinator_endpoint}/api/federation/join"
            headers = self._create_auth_headers()

            payload = {
                "poolId": self.pool_id,
                "name": f"Pool-{self.pool_id}",
                "endpoint": "http://localhost:18789",  # 自己的端点
                "capabilities": ["general", "python"],
                "maxCapacity": 50,
                "region": "local"
            }

            async with self.session.post(join_url, json=payload, headers=headers, timeout=15) as response:
                if response.status == 200:
                    logger.info("成功请求加入联邦")
                    return True
                else:
                    logger.error(f"加入联邦请求失败: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"请求加入联邦失败: {e}")
            return False

    def _create_auth_headers(self) -> Dict[str, str]:
        """创建认证头"""
        headers = {
            "User-Agent": f"ClawPool-Federation/{self.pool_id}",
            "Content-Type": "application/json"
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    def _generate_api_key(self) -> str:
        """生成API密钥"""
        return f"cp_{uuid.uuid4().hex}"

    def _generate_shared_secret(self) -> str:
        """生成共享密钥"""
        return uuid.uuid4().hex

def print_federation_stats(manager: FederationManager):
    """打印联邦统计信息"""
    stats = manager.get_federation_stats()

    print("🌐 Federation Statistics")
    print(f"   联邦ID: {stats['federationId']}")
    print(f"   Pool ID: {stats['poolId']}")
    print(f"   角色: {stats['role']}")
    print(f"   总Pool数: {stats['totalPools']}")

    print("\n📊 Pool状态分布:")
    for status, count in stats['poolsByStatus'].items():
        print(f"   {status}: {count}")

    print(f"\n⚡ 资源统计:")
    print(f"   总容量: {stats['totalCapacity']}")
    print(f"   当前负载: {stats['totalLoad']}")
    print(f"   负载率: {stats['loadFactor']:.2%}")

    print(f"\n🔀 联邦活动:")
    for key, value in stats['federationStats'].items():
        print(f"   {key}: {value}")

def print_pool_list(pools: List[Dict]):
    """打印Pool列表"""
    if not pools:
        print("❌ 没有发现联邦Pool")
        return

    print(f"🔗 联邦Pool列表 ({len(pools)} 个):\n")

    for i, pool in enumerate(pools, 1):
        status_icon = {
            "online": "🟢",
            "offline": "🔴",
            "maintenance": "🟡",
            "unreachable": "⚫"
        }.get(pool["status"], "❓")

        print(f"{i}. {status_icon} {pool['name']} ({pool['poolId']})")
        print(f"   端点: {pool['endpoint']}")
        print(f"   角色: {pool['role']}")
        print(f"   负载: {pool['load']}/{pool['capacity']} ({pool['loadFactor']:.1%})")
        print(f"   信任度: {pool['trustLevel']:.2f}")
        print(f"   地区: {pool['region']}")
        print(f"   能力: {', '.join(pool['capabilities'])}")
        print()

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Federation Manager')
    parser.add_argument('--init-federation', type=str,
                       help='初始化新联邦')
    parser.add_argument('--join-pool', type=str,
                       help='加入指定Pool')
    parser.add_argument('--list-pools', action='store_true',
                       help='列出联邦Pool')
    parser.add_argument('--federation-stats', action='store_true',
                       help='显示联邦统计')
    parser.add_argument('--start-coordinator', action='store_true',
                       help='启动联邦协调器')
    parser.add_argument('--config-path', type=str,
                       help='配置文件路径')

    args = parser.parse_args()

    manager = FederationManager(args.config_path)

    if args.init_federation:
        federation_id = await manager.init_federation(args.init_federation)
        print(f"✅ 联邦初始化完成: {federation_id}")

    elif args.join_pool:
        success = await manager.join_pool(args.join_pool)
        print("✅ 成功加入Pool" if success else "❌ 加入Pool失败")

    elif args.list_pools:
        pools = manager.list_pools()
        print_pool_list(pools)

    elif args.federation_stats:
        print_federation_stats(manager)

    elif args.start_coordinator:
        try:
            await manager.start_coordinator()
        except KeyboardInterrupt:
            print("\n用户中断，停止协调器")

    else:
        print("请指定操作：--init-federation, --join-pool, --list-pools, --federation-stats, 或 --start-coordinator")

if __name__ == '__main__':
    asyncio.run(main())