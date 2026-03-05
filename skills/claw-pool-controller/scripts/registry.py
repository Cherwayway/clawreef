#!/usr/bin/env python3
"""
Claw Pool Controller - Registry Service

龙虾注册表管理服务：
- 处理龙虾注册请求和设备认证
- 维护龙虾能力和状态数据库
- 龙虾健康检查和故障检测
- 动态龙虾接入和移除

Usage:
    python registry.py --start                # 启动注册服务
    python registry.py --list                 # 查看注册的龙虾
    python registry.py --unregister <id>      # 注销指定龙虾
    python registry.py --export <file>        # 导出注册表
"""

import asyncio
import json
import argparse
import sqlite3
import websockets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LobsterRegistry:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self._get_default_db_path()
        self.active_connections = {}  # device_id -> websocket
        self.heartbeat_timers = {}    # device_id -> timer
        self.init_database()

    def _get_default_db_path(self) -> str:
        """获取默认数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        return str(openclaw_dir / "pool_registry.db")

    def init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS lobsters (
                    device_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    capabilities TEXT NOT NULL,  -- JSON array
                    resources TEXT NOT NULL,     -- JSON object
                    status TEXT DEFAULT 'offline',
                    registration_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_heartbeat TIMESTAMP,
                    last_seen TIMESTAMP,
                    location TEXT,               -- JSON object
                    pricing TEXT,                -- JSON object
                    owner TEXT,
                    platform TEXT,               -- JSON object
                    openclaw_version TEXT,
                    registration_data TEXT       -- Full registration JSON
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS registration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    action TEXT,  -- 'register', 'unregister', 'status_change'
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT  -- JSON
                )
            ''')

            conn.commit()
        logger.info(f"数据库初始化完成: {self.db_path}")

    async def handle_registration(self, websocket, registration_data: Dict) -> Dict:
        """处理龙虾注册请求"""
        lobster_data = registration_data.get("lobster", {})
        device_id = lobster_data.get("deviceId")

        if not device_id:
            return {
                "action": "register_ack",
                "status": "rejected",
                "message": "缺少设备ID"
            }

        logger.info(f"处理龙虾注册: {device_id}")

        try:
            # 验证注册数据
            validation_result = self._validate_registration(lobster_data)
            if not validation_result["valid"]:
                return {
                    "action": "register_ack",
                    "status": "rejected",
                    "message": validation_result["message"]
                }

            # 生成注册ID
            registration_id = f"reg_{uuid.uuid4().hex[:12]}"

            # 保存到数据库
            self._save_lobster_registration(device_id, lobster_data, registration_id)

            # 添加到活跃连接
            self.active_connections[device_id] = websocket

            # 启动心跳检查
            await self._start_heartbeat_check(device_id)

            # 记录历史
            self._record_history(device_id, "register", {"registration_id": registration_id})

            logger.info(f"龙虾 {device_id} 注册成功")

            return {
                "action": "register_ack",
                "status": "approved",
                "registrationId": registration_id,
                "poolInfo": {
                    "poolId": "main-pool",
                    "version": "1.0.0",
                    "supportedTaskTypes": [
                        "general", "python", "data-analysis",
                        "web-scraping", "document-processing", "code-generation"
                    ],
                    "heartbeatInterval": 30000,
                    "taskTimeout": 300000
                }
            }

        except Exception as e:
            logger.error(f"处理注册请求失败: {e}")
            return {
                "action": "register_ack",
                "status": "error",
                "message": f"注册失败: {str(e)}"
            }

    def _validate_registration(self, lobster_data: Dict) -> Dict:
        """验证注册数据"""
        required_fields = ["deviceId", "displayName", "capabilities"]

        for field in required_fields:
            if field not in lobster_data:
                return {"valid": False, "message": f"缺少必需字段: {field}"}

        capabilities = lobster_data.get("capabilities", [])
        if not isinstance(capabilities, list) or len(capabilities) == 0:
            return {"valid": False, "message": "能力列表不能为空"}

        return {"valid": True, "message": "验证通过"}

    def _save_lobster_registration(self, device_id: str, lobster_data: Dict, registration_id: str):
        """保存龙虾注册信息到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO lobsters (
                    device_id, display_name, capabilities, resources,
                    status, last_seen, location, pricing, owner,
                    platform, openclaw_version, registration_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id,
                lobster_data.get("displayName"),
                json.dumps(lobster_data.get("capabilities", [])),
                json.dumps(lobster_data.get("resources", {})),
                "online",
                datetime.now().isoformat(),
                json.dumps(lobster_data.get("location", {})),
                json.dumps(lobster_data.get("pricing", {})),
                lobster_data.get("owner"),
                json.dumps(lobster_data.get("platform", {})),
                lobster_data.get("openclaw", {}).get("version"),
                json.dumps(lobster_data)
            ))
            conn.commit()

    async def handle_heartbeat(self, device_id: str, heartbeat_data: Dict):
        """处理心跳消息"""
        logger.debug(f"收到心跳: {device_id}")

        try:
            lobster_data = heartbeat_data.get("lobster", {})

            # 更新数据库中的心跳时间和状态
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE lobsters
                    SET last_heartbeat = ?, status = ?, last_seen = ?
                    WHERE device_id = ?
                ''', (
                    datetime.now().isoformat(),
                    lobster_data.get("status", "unknown"),
                    datetime.now().isoformat(),
                    device_id
                ))
                conn.commit()

            # 重置心跳定时器
            await self._reset_heartbeat_timer(device_id)

        except Exception as e:
            logger.error(f"处理心跳失败 {device_id}: {e}")

    async def _start_heartbeat_check(self, device_id: str):
        """启动心跳检查定时器"""
        if device_id in self.heartbeat_timers:
            self.heartbeat_timers[device_id].cancel()

        # 90秒无心跳认为离线
        timer = asyncio.create_task(self._heartbeat_timeout_check(device_id, 90))
        self.heartbeat_timers[device_id] = timer

    async def _reset_heartbeat_timer(self, device_id: str):
        """重置心跳检查定时器"""
        if device_id in self.heartbeat_timers:
            self.heartbeat_timers[device_id].cancel()

        timer = asyncio.create_task(self._heartbeat_timeout_check(device_id, 90))
        self.heartbeat_timers[device_id] = timer

    async def _heartbeat_timeout_check(self, device_id: str, timeout_seconds: int):
        """心跳超时检查"""
        try:
            await asyncio.sleep(timeout_seconds)

            # 检查是否仍然超时
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT last_heartbeat FROM lobsters WHERE device_id = ?
                ''', (device_id,))
                row = cursor.fetchone()

                if row and row[0]:
                    last_heartbeat = datetime.fromisoformat(row[0])
                    if datetime.now() - last_heartbeat > timedelta(seconds=timeout_seconds):
                        await self._mark_lobster_offline(device_id)

        except asyncio.CancelledError:
            # 定时器被取消，正常情况
            pass
        except Exception as e:
            logger.error(f"心跳超时检查失败 {device_id}: {e}")

    async def _mark_lobster_offline(self, device_id: str):
        """标记龙虾为离线状态"""
        logger.warning(f"龙虾心跳超时，标记为离线: {device_id}")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE lobsters SET status = 'offline' WHERE device_id = ?
            ''', (device_id,))
            conn.commit()

        # 移除活跃连接
        self.active_connections.pop(device_id, None)

        # 记录历史
        self._record_history(device_id, "offline", {"reason": "heartbeat_timeout"})

    async def unregister_lobster(self, device_id: str) -> bool:
        """注销指定龙虾"""
        logger.info(f"注销龙虾: {device_id}")

        try:
            # 取消心跳定时器
            if device_id in self.heartbeat_timers:
                self.heartbeat_timers[device_id].cancel()
                del self.heartbeat_timers[device_id]

            # 关闭连接
            if device_id in self.active_connections:
                websocket = self.active_connections[device_id]
                await websocket.close()
                del self.active_connections[device_id]

            # 从数据库删除
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM lobsters WHERE device_id = ?', (device_id,))
                conn.commit()

            # 记录历史
            self._record_history(device_id, "unregister", {})

            return True

        except Exception as e:
            logger.error(f"注销龙虾失败 {device_id}: {e}")
            return False

    def get_registered_lobsters(self) -> List[Dict]:
        """获取所有注册的龙虾"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT device_id, display_name, capabilities, resources,
                       status, registration_time, last_heartbeat, last_seen
                FROM lobsters
                ORDER BY registration_time DESC
            ''')

            lobsters = []
            for row in cursor.fetchall():
                lobsters.append({
                    "deviceId": row[0],
                    "displayName": row[1],
                    "capabilities": json.loads(row[2]) if row[2] else [],
                    "resources": json.loads(row[3]) if row[3] else {},
                    "status": row[4],
                    "registrationTime": row[5],
                    "lastHeartbeat": row[6],
                    "lastSeen": row[7]
                })

            return lobsters

    def get_lobster_by_id(self, device_id: str) -> Optional[Dict]:
        """根据ID获取龙虾详细信息"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM lobsters WHERE device_id = ?
            ''', (device_id,))
            row = cursor.fetchone()

            if row:
                return {
                    "deviceId": row[0],
                    "displayName": row[1],
                    "capabilities": json.loads(row[2]) if row[2] else [],
                    "resources": json.loads(row[3]) if row[3] else {},
                    "status": row[4],
                    "registrationTime": row[5],
                    "lastHeartbeat": row[6],
                    "lastSeen": row[7],
                    "location": json.loads(row[8]) if row[8] else {},
                    "pricing": json.loads(row[9]) if row[9] else {},
                    "owner": row[10],
                    "platform": json.loads(row[11]) if row[11] else {},
                    "openclawVersion": row[12],
                    "registrationData": json.loads(row[13]) if row[13] else {}
                }
            return None

    def get_available_lobsters(self, capabilities: List[str] = None) -> List[Dict]:
        """获取可用的龙虾（根据能力筛选）"""
        with sqlite3.connect(self.db_path) as conn:
            query = '''
                SELECT device_id, display_name, capabilities, resources, status
                FROM lobsters
                WHERE status IN ('online', 'idle')
            '''

            cursor = conn.execute(query)
            lobsters = []

            for row in cursor.fetchall():
                lobster_capabilities = json.loads(row[2]) if row[2] else []

                # 如果指定了能力要求，检查匹配
                if capabilities:
                    if not all(cap in lobster_capabilities for cap in capabilities):
                        continue

                lobsters.append({
                    "deviceId": row[0],
                    "displayName": row[1],
                    "capabilities": lobster_capabilities,
                    "resources": json.loads(row[3]) if row[3] else {},
                    "status": row[4]
                })

            return lobsters

    def _record_history(self, device_id: str, action: str, details: Dict):
        """记录操作历史"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO registration_history (device_id, action, details)
                VALUES (?, ?, ?)
            ''', (device_id, action, json.dumps(details)))
            conn.commit()

    def get_statistics(self) -> Dict:
        """获取注册统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            # 总体统计
            cursor = conn.execute('SELECT COUNT(*) FROM lobsters')
            total_lobsters = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM lobsters WHERE status = "online"')
            online_lobsters = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM lobsters WHERE status = "offline"')
            offline_lobsters = cursor.fetchone()[0]

            # 能力统计
            cursor = conn.execute('SELECT capabilities FROM lobsters')
            all_capabilities = set()
            for row in cursor.fetchall():
                if row[0]:
                    caps = json.loads(row[0])
                    all_capabilities.update(caps)

            return {
                "totalLobsters": total_lobsters,
                "onlineLobsters": online_lobsters,
                "offlineLobsters": offline_lobsters,
                "activeConnections": len(self.active_connections),
                "availableCapabilities": list(all_capabilities),
                "registrationRate": self._calculate_registration_rate()
            }

    def _calculate_registration_rate(self) -> Dict:
        """计算注册速率"""
        with sqlite3.connect(self.db_path) as conn:
            # 最近24小时的注册数量
            cursor = conn.execute('''
                SELECT COUNT(*) FROM registration_history
                WHERE action = 'register'
                AND timestamp > datetime('now', '-24 hours')
            ''')
            last_24h = cursor.fetchone()[0]

            # 最近7天的注册数量
            cursor = conn.execute('''
                SELECT COUNT(*) FROM registration_history
                WHERE action = 'register'
                AND timestamp > datetime('now', '-7 days')
            ''')
            last_7d = cursor.fetchone()[0]

            return {
                "last24Hours": last_24h,
                "last7Days": last_7d
            }

    def export_registry(self, filename: str):
        """导出注册表到文件"""
        lobsters = self.get_registered_lobsters()
        stats = self.get_statistics()

        export_data = {
            "exportTime": datetime.now().isoformat(),
            "statistics": stats,
            "lobsters": lobsters
        }

        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"注册表已导出到: {filename}")

def print_lobsters_list(registry: LobsterRegistry):
    """打印龙虾列表"""
    lobsters = registry.get_registered_lobsters()

    if not lobsters:
        print("❌ 没有注册的龙虾")
        return

    print(f"🦞 已注册龙虾 ({len(lobsters)} 个):\n")

    for i, lobster in enumerate(lobsters, 1):
        status_icon = "🟢" if lobster["status"] == "online" else "🔴"
        print(f"{i}. {status_icon} {lobster['displayName']} ({lobster['deviceId']})")
        print(f"   能力: {', '.join(lobster['capabilities'])}")
        print(f"   状态: {lobster['status']}")
        print(f"   注册时间: {lobster['registrationTime']}")

        if lobster['lastHeartbeat']:
            print(f"   最后心跳: {lobster['lastHeartbeat']}")
        print()

def print_statistics(registry: LobsterRegistry):
    """打印统计信息"""
    stats = registry.get_statistics()

    print("📊 注册表统计信息")
    print(f"   总龙虾数: {stats['totalLobsters']}")
    print(f"   在线龙虾: {stats['onlineLobsters']}")
    print(f"   离线龙虾: {stats['offlineLobsters']}")
    print(f"   活跃连接: {stats['activeConnections']}")
    print(f"   可用能力: {', '.join(stats['availableCapabilities'])}")
    print(f"   注册速率:")
    print(f"     最近24小时: {stats['registrationRate']['last24Hours']}")
    print(f"     最近7天: {stats['registrationRate']['last7Days']}")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Registry Service')
    parser.add_argument('--start', action='store_true',
                       help='启动注册服务')
    parser.add_argument('--list', action='store_true',
                       help='查看注册的龙虾')
    parser.add_argument('--stats', action='store_true',
                       help='显示统计信息')
    parser.add_argument('--unregister', type=str,
                       help='注销指定龙虾')
    parser.add_argument('--export', type=str,
                       help='导出注册表到文件')
    parser.add_argument('--db-path', type=str,
                       help='数据库文件路径')

    args = parser.parse_args()

    registry = LobsterRegistry(args.db_path)

    if args.list:
        print_lobsters_list(registry)
    elif args.stats:
        print_statistics(registry)
    elif args.unregister:
        success = await registry.unregister_lobster(args.unregister)
        print("✅ 注销成功" if success else "❌ 注销失败")
    elif args.export:
        registry.export_registry(args.export)
    elif args.start:
        logger.info("启动注册服务...")
        # 这里需要集成到主要的 WebSocket 服务器中
        print("⚠️  注册服务需要与 WebSocket 服务器集成")
        print("   请使用 pool controller 的主服务启动")
    else:
        print("请指定操作：--start, --list, --stats, --unregister, 或 --export")

if __name__ == '__main__':
    asyncio.run(main())