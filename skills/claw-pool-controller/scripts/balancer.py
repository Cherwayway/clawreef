#!/usr/bin/env python3
"""
Claw Pool Controller - Load Balancer

负载均衡服务：
- 实时负载监控和分析
- 多种均衡策略（轮询、加权、最少连接）
- 动态负载调整
- 资源利用率优化

Usage:
    python balancer.py --test                    # 测试负载均衡算法
    python balancer.py --distribution            # 查看负载分布
    python balancer.py --strategy <algorithm>    # 调整均衡策略
    python balancer.py --simulate <tasks>        # 模拟负载均衡
"""

import asyncio
import json
import argparse
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging
import math

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BalancingStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_LEAST_CONNECTIONS = "weighted_least_connections"
    RESOURCE_BASED = "resource_based"
    CAPABILITY_AWARE = "capability_aware"
    HYBRID = "hybrid"
    GEOGRAPHICAL = "geographical"           # Phase 2: 地理位置优先
    AFFINITY_BASED = "affinity_based"      # Phase 2: 亲和性调度
    MULTI_CONSTRAINT = "multi_constraint"   # Phase 2: 多约束优化

class LoadBalancer:
    def __init__(self, registry_db_path: Optional[str] = None, tasks_db_path: Optional[str] = None):
        self.registry_db_path = registry_db_path or self._get_registry_db_path()
        self.tasks_db_path = tasks_db_path or self._get_tasks_db_path()

        # 当前策略
        self.strategy = BalancingStrategy.HYBRID

        # 轮询计数器
        self.round_robin_counter = 0

        # 权重配置
        self.weight_factors = {
            "cpu_weight": 0.3,
            "memory_weight": 0.3,
            "capability_weight": 0.2,
            "performance_weight": 0.2
        }

        # Phase 2: 地理和亲和性配置
        self.geographical_zones = {
            "us-east": ["10.0.1.0/24", "192.168.1.0/24"],
            "us-west": ["10.0.2.0/24", "192.168.2.0/24"],
            "eu-central": ["10.0.3.0/24", "192.168.3.0/24"],
            "asia-pacific": ["10.0.4.0/24", "192.168.4.0/24"]
        }

        self.affinity_rules = {
            "user_affinity": {},      # user_id -> preferred_lobster
            "task_affinity": {},      # task_type -> preferred_lobsters
            "data_affinity": {},      # data_location -> preferred_lobsters
            "cost_zones": {}          # cost_zone -> lobster_list
        }

    def _get_registry_db_path(self) -> str:
        """获取注册表数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_registry.db")

    def _get_tasks_db_path(self) -> str:
        """获取任务数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "pool_tasks.db")

    def select_lobster(self, available_lobsters: List[Dict], task_requirements: Dict) -> Optional[Dict]:
        """根据当前策略选择最适合的龙虾"""
        if not available_lobsters:
            return None

        if len(available_lobsters) == 1:
            return available_lobsters[0]

        # 根据策略选择
        if self.strategy == BalancingStrategy.ROUND_ROBIN:
            return self._round_robin_select(available_lobsters)
        elif self.strategy == BalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_select(available_lobsters)
        elif self.strategy == BalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_select(available_lobsters)
        elif self.strategy == BalancingStrategy.WEIGHTED_LEAST_CONNECTIONS:
            return self._weighted_least_connections_select(available_lobsters)
        elif self.strategy == BalancingStrategy.RESOURCE_BASED:
            return self._resource_based_select(available_lobsters)
        elif self.strategy == BalancingStrategy.CAPABILITY_AWARE:
            return self._capability_aware_select(available_lobsters, task_requirements)
        elif self.strategy == BalancingStrategy.HYBRID:
            return self._hybrid_select(available_lobsters, task_requirements)
        elif self.strategy == BalancingStrategy.GEOGRAPHICAL:
            return self._geographical_select(available_lobsters, task_requirements)
        elif self.strategy == BalancingStrategy.AFFINITY_BASED:
            return self._affinity_based_select(available_lobsters, task_requirements)
        elif self.strategy == BalancingStrategy.MULTI_CONSTRAINT:
            return self._multi_constraint_select(available_lobsters, task_requirements)
        else:
            return random.choice(available_lobsters)

    def _round_robin_select(self, lobsters: List[Dict]) -> Dict:
        """轮询算法"""
        selected = lobsters[self.round_robin_counter % len(lobsters)]
        self.round_robin_counter += 1
        logger.debug(f"轮询选择: {selected['displayName']}")
        return selected

    def _weighted_round_robin_select(self, lobsters: List[Dict]) -> Dict:
        """加权轮询算法"""
        # 计算权重
        weighted_lobsters = []
        for lobster in lobsters:
            weight = self._calculate_lobster_weight(lobster)
            weighted_lobsters.extend([lobster] * max(1, int(weight * 10)))

        if not weighted_lobsters:
            return random.choice(lobsters)

        selected = weighted_lobsters[self.round_robin_counter % len(weighted_lobsters)]
        self.round_robin_counter += 1
        logger.debug(f"加权轮询选择: {selected['displayName']}")
        return selected

    def _least_connections_select(self, lobsters: List[Dict]) -> Dict:
        """最少连接算法"""
        lobster_loads = []
        for lobster in lobsters:
            active_tasks = self._get_active_task_count(lobster['deviceId'])
            lobster_loads.append((active_tasks, lobster))

        # 选择活跃任务最少的龙虾
        selected = min(lobster_loads, key=lambda x: x[0])[1]
        logger.debug(f"最少连接选择: {selected['displayName']} (活跃任务: {min(lobster_loads, key=lambda x: x[0])[0]})")
        return selected

    def _weighted_least_connections_select(self, lobsters: List[Dict]) -> Dict:
        """加权最少连接算法"""
        lobster_scores = []
        for lobster in lobsters:
            active_tasks = self._get_active_task_count(lobster['deviceId'])
            weight = self._calculate_lobster_weight(lobster)
            # 分数 = 活跃任务数 / 权重，越小越好
            score = active_tasks / max(weight, 0.1)
            lobster_scores.append((score, lobster))

        selected = min(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"加权最少连接选择: {selected['displayName']}")
        return selected

    def _resource_based_select(self, lobsters: List[Dict]) -> Dict:
        """基于资源的选择算法"""
        lobster_scores = []
        for lobster in lobsters:
            resource_score = self._calculate_resource_score(lobster)
            lobster_scores.append((resource_score, lobster))

        # 选择资源分数最高的龙虾
        selected = max(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"资源导向选择: {selected['displayName']}")
        return selected

    def _capability_aware_select(self, lobsters: List[Dict], task_requirements: Dict) -> Dict:
        """能力感知选择算法"""
        required_capabilities = task_requirements.get("capabilities", [])

        lobster_scores = []
        for lobster in lobsters:
            lobster_capabilities = lobster.get("capabilities", [])

            # 计算能力匹配度
            if not required_capabilities:
                match_score = 1.0
            else:
                matched = sum(1 for cap in required_capabilities if cap in lobster_capabilities)
                match_score = matched / len(required_capabilities)

            # 考虑能力专精度（龙虾能力越专精分数越高）
            if lobster_capabilities:
                specialization_score = len(set(required_capabilities) & set(lobster_capabilities)) / len(lobster_capabilities)
            else:
                specialization_score = 0

            final_score = match_score * 0.7 + specialization_score * 0.3
            lobster_scores.append((final_score, lobster))

        selected = max(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"能力感知选择: {selected['displayName']}")
        return selected

    def _hybrid_select(self, lobsters: List[Dict], task_requirements: Dict) -> Dict:
        """混合算法（综合考虑多个因素）"""
        lobster_scores = []

        for lobster in lobsters:
            # 1. 能力匹配分数
            capability_score = self._calculate_capability_score(lobster, task_requirements)

            # 2. 资源分数
            resource_score = self._calculate_resource_score(lobster)

            # 3. 负载分数
            load_score = self._calculate_load_score(lobster)

            # 4. 性能历史分数
            performance_score = self._calculate_performance_score(lobster)

            # 综合评分
            final_score = (
                capability_score * self.weight_factors["capability_weight"] +
                resource_score * self.weight_factors["cpu_weight"] +
                load_score * self.weight_factors["memory_weight"] +
                performance_score * self.weight_factors["performance_weight"]
            )

            lobster_scores.append((final_score, lobster))

        selected = max(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"混合算法选择: {selected['displayName']} (分数: {max(lobster_scores, key=lambda x: x[0])[0]:.3f})")
        return selected

    def _calculate_lobster_weight(self, lobster: Dict) -> float:
        """计算龙虾权重"""
        resources = lobster.get("resources", {})

        # 基于CPU核心数的权重
        cpu_weight = float(resources.get("cpu", 1))

        # 基于内存大小的权重
        memory_str = resources.get("memory", "1GB")
        memory_gb = float(memory_str.replace("GB", "").replace("gb", ""))
        memory_weight = memory_gb / 4.0  # 以4GB为基准

        # 综合权重
        return max(0.1, cpu_weight * 0.6 + memory_weight * 0.4)

    def _calculate_capability_score(self, lobster: Dict, task_requirements: Dict) -> float:
        """计算能力匹配分数"""
        required_capabilities = task_requirements.get("capabilities", [])
        lobster_capabilities = lobster.get("capabilities", [])

        if not required_capabilities:
            return 1.0

        # 基础匹配分数
        matched = sum(1 for cap in required_capabilities if cap in lobster_capabilities)
        match_score = matched / len(required_capabilities)

        # 专精度奖励
        if lobster_capabilities:
            specialization_bonus = len(set(required_capabilities) & set(lobster_capabilities)) / len(lobster_capabilities) * 0.2
        else:
            specialization_bonus = 0

        return min(1.0, match_score + specialization_bonus)

    def _calculate_resource_score(self, lobster: Dict) -> float:
        """计算资源分数"""
        resources = lobster.get("resources", {})

        # CPU分数
        cpu_count = float(resources.get("cpu", 1))
        cpu_score = min(1.0, cpu_count / 8.0)  # 以8核为满分

        # 内存分数
        memory_str = resources.get("memory", "1GB")
        memory_gb = float(memory_str.replace("GB", "").replace("gb", ""))
        memory_score = min(1.0, memory_gb / 16.0)  # 以16GB为满分

        return (cpu_score + memory_score) / 2.0

    def _calculate_load_score(self, lobster: Dict) -> float:
        """计算负载分数（负载越低分数越高）"""
        active_tasks = self._get_active_task_count(lobster['deviceId'])
        max_tasks = 5  # 假设最大并发任务数为5

        # 负载分数：1.0 - (当前任务数 / 最大任务数)
        load_score = max(0.0, 1.0 - (active_tasks / max_tasks))
        return load_score

    def _calculate_performance_score(self, lobster: Dict) -> float:
        """计算性能历史分数"""
        device_id = lobster['deviceId']

        try:
            with sqlite3.connect(self.tasks_db_path) as conn:
                # 获取最近完成的任务统计
                cursor = conn.execute('''
                    SELECT
                        COUNT(*) as total_tasks,
                        AVG(CAST((julianday(completed_time) - julianday(created_time)) * 86400 AS INTEGER)) as avg_duration,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
                    FROM tasks
                    WHERE assigned_to = ?
                    AND completed_time IS NOT NULL
                    AND created_time > datetime('now', '-7 days')
                ''', (device_id,))

                row = cursor.fetchone()
                if not row or row[0] == 0:
                    return 0.5  # 默认中等分数

                total_tasks = row[0]
                avg_duration = row[1] or 60  # 默认60秒
                completed_tasks = row[2]

                # 成功率分数
                success_rate = completed_tasks / total_tasks
                success_score = success_rate

                # 速度分数（执行时间越短越好）
                speed_score = max(0.0, 1.0 - (avg_duration - 30) / 300)  # 30秒基准，300秒满分扣除

                return (success_score * 0.7 + speed_score * 0.3)

        except Exception as e:
            logger.error(f"计算性能分数失败: {e}")
            return 0.5

    def _get_active_task_count(self, device_id: str) -> int:
        """获取指定龙虾的活跃任务数"""
        try:
            with sqlite3.connect(self.tasks_db_path) as conn:
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM tasks
                    WHERE assigned_to = ?
                    AND status IN ('assigned', 'running')
                ''', (device_id,))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取活跃任务数失败: {e}")
            return 0

    # ===== Phase 2: Advanced Load Balancing Algorithms =====

    def _geographical_select(self, lobsters: List[Dict], task_requirements: Dict) -> Dict:
        """地理位置优先选择算法"""
        requester_location = task_requirements.get("location", {})
        preferred_zone = requester_location.get("zone")

        if not preferred_zone:
            # 如果没有指定位置偏好，使用混合算法
            return self._hybrid_select(lobsters, task_requirements)

        # 按地理距离评分
        lobster_scores = []
        for lobster in lobsters:
            geo_score = self._calculate_geographical_score(lobster, requester_location)
            resource_score = self._calculate_resource_score(lobster)
            latency_score = self._estimate_network_latency_score(lobster, requester_location)

            # 综合地理位置分数
            final_score = (
                geo_score * 0.5 +
                resource_score * 0.3 +
                latency_score * 0.2
            )
            lobster_scores.append((final_score, lobster))

        selected = max(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"地理位置优先选择: {selected['displayName']}")
        return selected

    def _affinity_based_select(self, lobsters: List[Dict], task_requirements: Dict) -> Dict:
        """亲和性调度选择算法"""
        user_id = task_requirements.get("userId")
        task_type = task_requirements.get("taskType", "general")
        data_location = task_requirements.get("dataLocation")

        lobster_scores = []
        for lobster in lobsters:
            device_id = lobster["deviceId"]

            # 1. 用户亲和性分数
            user_affinity_score = self._calculate_user_affinity_score(device_id, user_id)

            # 2. 任务类型亲和性分数
            task_affinity_score = self._calculate_task_affinity_score(device_id, task_type)

            # 3. 数据位置亲和性分数
            data_affinity_score = self._calculate_data_affinity_score(device_id, data_location)

            # 4. 成本优化分数
            cost_score = self._calculate_cost_score(device_id, task_requirements)

            # 5. 历史性能亲和性
            performance_affinity_score = self._calculate_performance_affinity_score(device_id, task_type)

            # 综合亲和性分数
            final_score = (
                user_affinity_score * 0.25 +
                task_affinity_score * 0.25 +
                data_affinity_score * 0.2 +
                cost_score * 0.15 +
                performance_affinity_score * 0.15
            )

            lobster_scores.append((final_score, lobster))

        selected = max(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"亲和性调度选择: {selected['displayName']}")
        return selected

    def _multi_constraint_select(self, lobsters: List[Dict], task_requirements: Dict) -> Dict:
        """多约束优化选择算法"""
        constraints = task_requirements.get("constraints", {})

        # 硬约束过滤
        filtered_lobsters = []
        for lobster in lobsters:
            if self._satisfies_hard_constraints(lobster, constraints):
                filtered_lobsters.append(lobster)

        if not filtered_lobsters:
            logger.warning("没有龙虾满足硬约束条件，降级到软约束")
            filtered_lobsters = lobsters

        # 多目标优化评分
        lobster_scores = []
        for lobster in filtered_lobsters:
            # 计算多个优化目标
            objectives = self._calculate_multi_objectives(lobster, task_requirements, constraints)

            # 使用加权和方法组合多个目标
            weights = constraints.get("weights", {
                "performance": 0.3,
                "cost": 0.25,
                "reliability": 0.2,
                "latency": 0.15,
                "availability": 0.1
            })

            final_score = sum(
                objectives.get(obj, 0) * weight
                for obj, weight in weights.items()
            )

            lobster_scores.append((final_score, lobster))

        selected = max(lobster_scores, key=lambda x: x[0])[1]
        logger.debug(f"多约束优化选择: {selected['displayName']}")
        return selected

    def _calculate_geographical_score(self, lobster: Dict, requester_location: Dict) -> float:
        """计算地理位置匹配分数"""
        lobster_location = lobster.get("location", {})

        # 区域匹配
        requester_zone = requester_location.get("zone", "unknown")
        lobster_zone = lobster_location.get("zone", "unknown")

        if requester_zone == lobster_zone:
            zone_score = 1.0
        elif self._zones_are_adjacent(requester_zone, lobster_zone):
            zone_score = 0.7
        else:
            zone_score = 0.3

        # 延迟估算（基于地理距离）
        latency_ms = lobster_location.get("estimatedLatency", 50)
        latency_score = max(0, 1.0 - latency_ms / 200.0)

        return (zone_score * 0.7 + latency_score * 0.3)

    def _estimate_network_latency_score(self, lobster: Dict, requester_location: Dict) -> float:
        """估算网络延迟分数"""
        lobster_ip = lobster.get("ipAddress", "127.0.0.1")
        requester_ip = requester_location.get("ipAddress", "127.0.0.1")

        # 简单的延迟估算（实际环境中可以使用ping或traceroute）
        try:
            import ipaddress
            lobster_net = ipaddress.ip_address(lobster_ip)
            requester_net = ipaddress.ip_address(requester_ip)

            # 如果在同一子网，延迟很低
            if str(lobster_net)[:7] == str(requester_net)[:7]:  # 简单的同网段判断
                return 1.0
            else:
                return 0.6
        except:
            return 0.5

    def _calculate_user_affinity_score(self, device_id: str, user_id: str) -> float:
        """计算用户亲和性分数"""
        if not user_id:
            return 0.5

        # 检查用户历史偏好
        user_preferences = self.affinity_rules["user_affinity"].get(user_id, {})
        if device_id in user_preferences.get("preferred", []):
            return 1.0
        elif device_id in user_preferences.get("avoided", []):
            return 0.1
        else:
            return 0.5

    def _calculate_task_affinity_score(self, device_id: str, task_type: str) -> float:
        """计算任务类型亲和性分数"""
        task_preferences = self.affinity_rules["task_affinity"].get(task_type, {})

        if device_id in task_preferences.get("optimized_for", []):
            return 1.0
        elif device_id in task_preferences.get("compatible", []):
            return 0.7
        else:
            return 0.5

    def _calculate_data_affinity_score(self, device_id: str, data_location: str) -> float:
        """计算数据位置亲和性分数"""
        if not data_location:
            return 0.5

        data_preferences = self.affinity_rules["data_affinity"].get(data_location, {})
        if device_id in data_preferences.get("local_access", []):
            return 1.0
        elif device_id in data_preferences.get("fast_access", []):
            return 0.8
        else:
            return 0.3

    def _calculate_cost_score(self, device_id: str, task_requirements: Dict) -> float:
        """计算成本优化分数"""
        cost_zone = task_requirements.get("costZone", "standard")
        budget_limit = task_requirements.get("budgetLimit", float('inf'))

        # 获取龙虾的成本信息
        device_cost = self._get_device_cost_info(device_id)

        if device_cost > budget_limit:
            return 0.0

        # 成本效益分数：成本越低分数越高
        max_cost = 100  # 假设的最大成本
        return max(0, 1.0 - device_cost / max_cost)

    def _calculate_performance_affinity_score(self, device_id: str, task_type: str) -> float:
        """计算历史性能亲和性分数"""
        try:
            with sqlite3.connect(self.tasks_db_path) as conn:
                # 获取该龙虾在该任务类型上的历史性能
                cursor = conn.execute('''
                    SELECT
                        AVG(CASE WHEN status = 'completed' THEN 1.0 ELSE 0.0 END) as success_rate,
                        AVG(actual_duration) as avg_duration
                    FROM tasks_v2
                    WHERE assigned_to = ? AND task_type = ?
                    AND completed_time > datetime('now', '-30 days')
                ''', (device_id, task_type))

                row = cursor.fetchone()
                if not row or row[0] is None:
                    return 0.5

                success_rate = row[0]
                avg_duration = row[1] or 60

                # 综合成功率和执行速度
                speed_score = max(0, 1.0 - (avg_duration - 30) / 300)
                return success_rate * 0.7 + speed_score * 0.3

        except Exception as e:
            logger.error(f"计算性能亲和性失败: {e}")
            return 0.5

    def _satisfies_hard_constraints(self, lobster: Dict, constraints: Dict) -> bool:
        """检查是否满足硬约束"""
        hard_constraints = constraints.get("hard", {})

        # 最小资源约束
        min_cpu = hard_constraints.get("minCpu", 0)
        min_memory = hard_constraints.get("minMemory", 0)

        resources = lobster.get("resources", {})
        lobster_cpu = float(resources.get("cpu", 1))
        lobster_memory_str = resources.get("memory", "1GB")
        lobster_memory = float(lobster_memory_str.replace("GB", "").replace("gb", ""))

        if lobster_cpu < min_cpu or lobster_memory < min_memory:
            return False

        # 必需能力约束
        required_capabilities = hard_constraints.get("requiredCapabilities", [])
        lobster_capabilities = lobster.get("capabilities", [])

        if not all(cap in lobster_capabilities for cap in required_capabilities):
            return False

        # 地理位置约束
        allowed_zones = hard_constraints.get("allowedZones", [])
        if allowed_zones:
            lobster_zone = lobster.get("location", {}).get("zone")
            if lobster_zone not in allowed_zones:
                return False

        return True

    def _calculate_multi_objectives(self, lobster: Dict, task_requirements: Dict, constraints: Dict) -> Dict[str, float]:
        """计算多个优化目标"""
        objectives = {}

        # 性能目标
        objectives["performance"] = self._calculate_resource_score(lobster)

        # 成本目标
        objectives["cost"] = self._calculate_cost_score(lobster["deviceId"], task_requirements)

        # 可靠性目标
        objectives["reliability"] = self._calculate_reliability_score(lobster["deviceId"])

        # 延迟目标
        objectives["latency"] = self._estimate_network_latency_score(lobster, task_requirements.get("location", {}))

        # 可用性目标
        objectives["availability"] = self._calculate_availability_score(lobster["deviceId"])

        return objectives

    def _zones_are_adjacent(self, zone1: str, zone2: str) -> bool:
        """判断两个区域是否相邻"""
        adjacency_map = {
            "us-east": ["us-west"],
            "us-west": ["us-east", "asia-pacific"],
            "eu-central": ["asia-pacific"],
            "asia-pacific": ["us-west", "eu-central"]
        }
        return zone2 in adjacency_map.get(zone1, [])

    def _get_device_cost_info(self, device_id: str) -> float:
        """获取设备成本信息"""
        # 简化实现，实际应从成本管理系统获取
        return hash(device_id) % 50 + 10  # 10-60的随机成本

    def _calculate_reliability_score(self, device_id: str) -> float:
        """计算可靠性分数"""
        try:
            with sqlite3.connect(self.tasks_db_path) as conn:
                cursor = conn.execute('''
                    SELECT
                        COUNT(*) as total_tasks,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
                    FROM tasks_v2
                    WHERE assigned_to = ?
                    AND created_time > datetime('now', '-7 days')
                ''', (device_id,))

                row = cursor.fetchone()
                if not row or row[0] == 0:
                    return 0.8  # 默认较高可靠性

                total_tasks, completed_tasks = row
                reliability = completed_tasks / total_tasks
                return reliability

        except Exception as e:
            logger.error(f"计算可靠性分数失败: {e}")
            return 0.8

    def _calculate_availability_score(self, device_id: str) -> float:
        """计算可用性分数"""
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                cursor = conn.execute('''
                    SELECT last_heartbeat FROM lobsters WHERE device_id = ?
                ''', (device_id,))

                row = cursor.fetchone()
                if not row:
                    return 0.5

                last_heartbeat = datetime.fromisoformat(row[0])
                time_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()

                # 心跳越新，可用性分数越高
                if time_since_heartbeat < 30:  # 30秒内
                    return 1.0
                elif time_since_heartbeat < 120:  # 2分钟内
                    return 0.8
                elif time_since_heartbeat < 300:  # 5分钟内
                    return 0.6
                else:
                    return 0.3

        except Exception as e:
            logger.error(f"计算可用性分数失败: {e}")
            return 0.5

    def get_load_distribution(self) -> Dict:
        """获取当前负载分布"""
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                cursor = conn.execute('''
                    SELECT device_id, display_name, status FROM lobsters
                    WHERE status IN ('online', 'idle', 'busy')
                ''')

                distribution = []
                for row in cursor.fetchall():
                    device_id, display_name, status = row
                    active_tasks = self._get_active_task_count(device_id)

                    distribution.append({
                        "deviceId": device_id,
                        "displayName": display_name,
                        "status": status,
                        "activeTasks": active_tasks,
                        "weight": self._calculate_lobster_weight({"deviceId": device_id})
                    })

                # 计算总体统计
                total_tasks = sum(item["activeTasks"] for item in distribution)
                total_lobsters = len(distribution)

                return {
                    "distribution": distribution,
                    "totalTasks": total_tasks,
                    "totalLobsters": total_lobsters,
                    "avgTasksPerLobster": total_tasks / total_lobsters if total_lobsters > 0 else 0,
                    "currentStrategy": self.strategy.value
                }

        except Exception as e:
            logger.error(f"获取负载分布失败: {e}")
            return {"error": str(e)}

    def simulate_load_balancing(self, num_tasks: int, task_types: List[str] = None) -> Dict:
        """模拟负载均衡"""
        if not task_types:
            task_types = ["general", "python", "data-analysis"]

        # 获取可用龙虾
        try:
            with sqlite3.connect(self.registry_db_path) as conn:
                cursor = conn.execute('''
                    SELECT device_id, display_name, capabilities, resources
                    FROM lobsters
                    WHERE status IN ('online', 'idle')
                ''')

                available_lobsters = []
                for row in cursor.fetchall():
                    available_lobsters.append({
                        "deviceId": row[0],
                        "displayName": row[1],
                        "capabilities": json.loads(row[2]) if row[2] else [],
                        "resources": json.loads(row[3]) if row[3] else {}
                    })

        except Exception as e:
            return {"error": f"获取龙虾列表失败: {e}"}

        if not available_lobsters:
            return {"error": "没有可用的龙虾"}

        # 模拟任务分配
        assignments = {lobster["deviceId"]: 0 for lobster in available_lobsters}
        assignment_details = []

        for i in range(num_tasks):
            # 生成随机任务
            task_type = random.choice(task_types)
            task_requirements = {
                "capabilities": [task_type],
                "priority": random.randint(1, 3)
            }

            # 选择龙虾
            selected = self.select_lobster(available_lobsters, task_requirements)
            if selected:
                assignments[selected["deviceId"]] += 1
                assignment_details.append({
                    "taskId": f"sim_task_{i+1}",
                    "taskType": task_type,
                    "assignedTo": selected["deviceId"],
                    "lobsterName": selected["displayName"]
                })

        # 计算分布统计
        task_counts = list(assignments.values())
        if task_counts:
            balance_score = 1.0 - (max(task_counts) - min(task_counts)) / max(max(task_counts), 1)
        else:
            balance_score = 1.0

        return {
            "totalTasks": num_tasks,
            "assignments": assignments,
            "assignmentDetails": assignment_details[-10:],  # 只显示最后10个
            "statistics": {
                "maxTasks": max(task_counts) if task_counts else 0,
                "minTasks": min(task_counts) if task_counts else 0,
                "avgTasks": sum(task_counts) / len(task_counts) if task_counts else 0,
                "balanceScore": balance_score,
                "strategy": self.strategy.value
            }
        }

def print_load_distribution(balancer: LoadBalancer):
    """打印负载分布"""
    distribution = balancer.get_load_distribution()

    if "error" in distribution:
        print(f"❌ 获取负载分布失败: {distribution['error']}")
        return

    print("⚖️ Load Distribution")
    print(f"   策略: {distribution['currentStrategy']}")
    print(f"   总任务数: {distribution['totalTasks']}")
    print(f"   总龙虾数: {distribution['totalLobsters']}")
    print(f"   平均任务/龙虾: {distribution['avgTasksPerLobster']:.2f}")
    print()

    # 按任务数排序
    sorted_lobsters = sorted(distribution['distribution'], key=lambda x: x['activeTasks'], reverse=True)

    for i, lobster in enumerate(sorted_lobsters, 1):
        status_icon = "🟢" if lobster['status'] == 'online' else "🟡"
        print(f"{i}. {status_icon} {lobster['displayName']}")
        print(f"   设备ID: {lobster['deviceId']}")
        print(f"   活跃任务: {lobster['activeTasks']}")
        print(f"   权重: {lobster.get('weight', 1.0):.2f}")
        print()

def print_simulation_results(results: Dict):
    """打印模拟结果"""
    if "error" in results:
        print(f"❌ 模拟失败: {results['error']}")
        return

    stats = results["statistics"]
    print("🎯 Load Balancing Simulation Results")
    print(f"   策略: {stats['strategy']}")
    print(f"   总任务数: {results['totalTasks']}")
    print(f"   均衡分数: {stats['balanceScore']:.3f}")
    print(f"   最大任务数: {stats['maxTasks']}")
    print(f"   最小任务数: {stats['minTasks']}")
    print(f"   平均任务数: {stats['avgTasks']:.2f}")

    print("\n📋 任务分配:")
    assignments = results["assignments"]
    for device_id, task_count in assignments.items():
        if task_count > 0:
            print(f"   {device_id}: {task_count} 任务")

    # 显示部分分配详情
    details = results.get("assignmentDetails", [])
    if details:
        print(f"\n🔍 分配示例 (最后 {len(details)} 个):")
        for detail in details:
            print(f"   {detail['taskId']} ({detail['taskType']}) → {detail['lobsterName']}")

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Load Balancer')
    parser.add_argument('--test', action='store_true',
                       help='测试负载均衡算法')
    parser.add_argument('--distribution', action='store_true',
                       help='查看当前负载分布')
    parser.add_argument('--strategy', type=str,
                       choices=[s.value for s in BalancingStrategy],
                       help='设置负载均衡策略')
    parser.add_argument('--simulate', type=int,
                       help='模拟指定数量的任务分配')
    parser.add_argument('--registry-db', type=str,
                       help='注册表数据库路径')
    parser.add_argument('--tasks-db', type=str,
                       help='任务数据库路径')

    args = parser.parse_args()

    balancer = LoadBalancer(args.registry_db, args.tasks_db)

    if args.strategy:
        try:
            balancer.strategy = BalancingStrategy(args.strategy)
            print(f"✅ 负载均衡策略已设置为: {args.strategy}")
        except ValueError:
            print(f"❌ 无效的策略: {args.strategy}")

    if args.distribution:
        print_load_distribution(balancer)
    elif args.simulate:
        results = balancer.simulate_load_balancing(args.simulate)
        print_simulation_results(results)
    elif args.test:
        # 测试所有策略
        strategies = list(BalancingStrategy)
        for strategy in strategies:
            balancer.strategy = strategy
            print(f"\n🧪 测试策略: {strategy.value}")
            results = balancer.simulate_load_balancing(20)
            if "error" not in results:
                stats = results["statistics"]
                print(f"   均衡分数: {stats['balanceScore']:.3f}")
                print(f"   任务分布: {stats['minTasks']} - {stats['maxTasks']} (平均 {stats['avgTasks']:.1f})")
    else:
        print("请指定操作：--test, --distribution, --strategy, 或 --simulate")

if __name__ == '__main__':
    asyncio.run(main())