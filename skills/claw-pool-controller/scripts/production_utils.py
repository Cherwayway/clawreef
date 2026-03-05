#!/usr/bin/env python3
"""
Claw Pool Controller - Production Utilities (Phase 2)

生产就绪工具：
- 高级错误处理和重试机制
- 连接池和超时管理
- 完整的日志和监控
- 性能优化和资源管理

Usage:
    python production_utils.py --test-retry        # 测试重试机制
    python production_utils.py --test-pool         # 测试连接池
    python production_utils.py --start-monitor     # 启动监控服务
    python production_utils.py --health-check      # 健康检查
"""

import asyncio
import json
import argparse
import sqlite3
import uuid
import time
import psutil
import aiohttp
import backoff
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass, asdict
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import traceback
from contextlib import asynccontextmanager
from functools import wraps
import weakref
from concurrent.futures import ThreadPoolExecutor
import signal
import sys

# 配置结构化日志
class ProductionLogger:
    def __init__(self, name: str, log_dir: Optional[str] = None):
        self.log_dir = log_dir or str(Path.home() / ".openclaw" / "logs")
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # 清除默认处理器
        self.logger.handlers.clear()

        # 文件处理器 - 按大小轮转
        file_handler = RotatingFileHandler(
            f"{self.log_dir}/{name}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)

        # 错误文件处理器
        error_handler = RotatingFileHandler(
            f"{self.log_dir}/{name}_error.log",
            maxBytes=10*1024*1024,
            backupCount=10
        )
        error_handler.setLevel(logging.ERROR)

        # 日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(formatter)
        error_handler.setFormatter(formatter)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s - %(message)s'
        ))

        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger

# 全局日志管理器
_loggers = {}

def get_production_logger(name: str) -> logging.Logger:
    """获取生产环境日志器"""
    if name not in _loggers:
        _loggers[name] = ProductionLogger(name)
    return _loggers[name].get_logger()

logger = get_production_logger("production_utils")

class RetryPolicy(Enum):
    EXPONENTIAL_BACKOFF = "exponential"
    FIXED_INTERVAL = "fixed"
    LINEAR_BACKOFF = "linear"
    FIBONACCI = "fibonacci"

class CircuitBreakerState(Enum):
    CLOSED = "closed"        # 正常状态
    OPEN = "open"           # 熔断状态
    HALF_OPEN = "half_open" # 半开状态

@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL_BACKOFF
    exceptions: tuple = (Exception,)

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5      # 失败阈值
    success_threshold: int = 2      # 恢复阈值
    timeout: float = 60.0           # 熔断超时
    half_open_max_calls: int = 3    # 半开状态最大调用次数

class CircuitBreaker:
    """熔断器实现"""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    def call(self, func, *args, **kwargs):
        """执行带熔断器保护的调用"""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("熔断器进入半开状态")
            else:
                raise Exception("熔断器开启：服务不可用")

        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                raise Exception("熔断器半开：超过最大调用次数")
            self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置熔断器"""
        if self.last_failure_time is None:
            return False
        return time.time() - self.last_failure_time >= self.config.timeout

    def _on_success(self):
        """成功回调"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info("熔断器重置为关闭状态")
        else:
            self.failure_count = 0

    def _on_failure(self):
        """失败回调"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning("熔断器从半开变为开启状态")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"熔断器开启：失败次数达到阈值 {self.config.failure_threshold}")

def retry_with_backoff(retry_config: RetryConfig = None):
    """高级重试装饰器"""
    if retry_config is None:
        retry_config = RetryConfig()

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retry_config.exceptions as e:
                    last_exception = e

                    if attempt == retry_config.max_attempts - 1:
                        logger.error(f"重试失败，已达到最大次数 {retry_config.max_attempts}: {e}")
                        break

                    delay = _calculate_delay(retry_config, attempt)
                    logger.warning(f"第 {attempt + 1} 次重试失败，{delay:.2f}s 后重试: {e}")
                    await asyncio.sleep(delay)

            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_config.exceptions as e:
                    last_exception = e

                    if attempt == retry_config.max_attempts - 1:
                        break

                    delay = _calculate_delay(retry_config, attempt)
                    logger.warning(f"第 {attempt + 1} 次重试失败，{delay:.2f}s 后重试: {e}")
                    time.sleep(delay)

            raise last_exception

        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

def _calculate_delay(retry_config: RetryConfig, attempt: int) -> float:
    """计算重试延迟"""
    if retry_config.retry_policy == RetryPolicy.EXPONENTIAL_BACKOFF:
        delay = retry_config.base_delay * (retry_config.backoff_factor ** attempt)
    elif retry_config.retry_policy == RetryPolicy.FIXED_INTERVAL:
        delay = retry_config.base_delay
    elif retry_config.retry_policy == RetryPolicy.LINEAR_BACKOFF:
        delay = retry_config.base_delay * (attempt + 1)
    elif retry_config.retry_policy == RetryPolicy.FIBONACCI:
        delay = retry_config.base_delay * _fibonacci(attempt + 1)
    else:
        delay = retry_config.base_delay

    delay = min(delay, retry_config.max_delay)

    # 添加随机抖动
    if retry_config.jitter:
        import random
        jitter = random.uniform(0.1, 0.9)
        delay *= jitter

    return delay

def _fibonacci(n: int) -> int:
    """计算斐波那契数"""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

class ConnectionPool:
    """连接池管理器"""

    def __init__(self,
                 max_connections: int = 100,
                 max_idle_time: float = 300.0,
                 connection_timeout: float = 10.0):
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.connection_timeout = connection_timeout

        self._sessions = {}
        self._session_last_used = {}
        self._lock = asyncio.Lock()

        # 启动清理任务
        self._cleanup_task = None

    async def start(self):
        """启动连接池"""
        self._cleanup_task = asyncio.create_task(self._cleanup_idle_connections())
        logger.info(f"连接池启动：最大连接数 {self.max_connections}")

    async def stop(self):
        """停止连接池"""
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # 关闭所有连接
        for session in self._sessions.values():
            await session.close()

        self._sessions.clear()
        self._session_last_used.clear()
        logger.info("连接池已停止")

    @asynccontextmanager
    async def get_session(self, endpoint: str):
        """获取连接会话"""
        async with self._lock:
            session_key = self._get_session_key(endpoint)

            # 复用现有连接
            if session_key in self._sessions:
                session = self._sessions[session_key]
                if not session.closed:
                    self._session_last_used[session_key] = time.time()
                    yield session
                    return
                else:
                    # 连接已关闭，清理
                    del self._sessions[session_key]
                    del self._session_last_used[session_key]

            # 检查连接数限制
            if len(self._sessions) >= self.max_connections:
                await self._cleanup_oldest_connection()

            # 创建新连接
            timeout = aiohttp.ClientTimeout(total=self.connection_timeout)
            session = aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    ttl_dns_cache=300
                )
            )

            self._sessions[session_key] = session
            self._session_last_used[session_key] = time.time()

            logger.debug(f"创建新连接: {endpoint}")

        try:
            yield session
        except Exception as e:
            logger.error(f"连接使用过程中出错: {e}")
            # 出错时关闭连接
            await session.close()
            async with self._lock:
                if session_key in self._sessions:
                    del self._sessions[session_key]
                    del self._session_last_used[session_key]
            raise

    def _get_session_key(self, endpoint: str) -> str:
        """获取连接会话键"""
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def _cleanup_idle_connections(self):
        """清理空闲连接"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                current_time = time.time()
                idle_sessions = []

                async with self._lock:
                    for session_key, last_used in self._session_last_used.items():
                        if current_time - last_used > self.max_idle_time:
                            idle_sessions.append(session_key)

                    # 关闭空闲连接
                    for session_key in idle_sessions:
                        session = self._sessions.get(session_key)
                        if session:
                            await session.close()
                            del self._sessions[session_key]
                            del self._session_last_used[session_key]
                            logger.debug(f"清理空闲连接: {session_key}")

            except Exception as e:
                logger.error(f"清理空闲连接时出错: {e}")

    async def _cleanup_oldest_connection(self):
        """清理最旧的连接"""
        if not self._session_last_used:
            return

        oldest_key = min(self._session_last_used, key=self._session_last_used.get)
        session = self._sessions.get(oldest_key)

        if session:
            await session.close()
            del self._sessions[oldest_key]
            del self._session_last_used[oldest_key]
            logger.debug(f"清理最旧连接: {oldest_key}")

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self._get_default_db_path()
        self.metrics = {}
        self.start_time = time.time()

        self.init_database()

    def _get_default_db_path(self) -> str:
        """获取默认数据库路径"""
        openclaw_dir = Path.home() / ".openclaw"
        return str(openclaw_dir / "performance_metrics.db")

    def init_database(self):
        """初始化性能数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    tags TEXT,              -- JSON
                    host_info TEXT          -- JSON
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL,
                    memory_percent REAL,
                    disk_percent REAL,
                    network_io TEXT,        -- JSON
                    active_connections INTEGER,
                    error_rate REAL,
                    response_time REAL
                )
            ''')

            conn.commit()

    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """记录性能指标"""
        self.metrics[name] = {
            'value': value,
            'timestamp': time.time(),
            'tags': tags or {}
        }

        # 保存到数据库
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO performance_metrics (metric_name, metric_value, tags, host_info)
                    VALUES (?, ?, ?, ?)
                ''', (
                    name, value,
                    json.dumps(tags or {}),
                    json.dumps(self._get_host_info())
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"记录性能指标失败: {e}")

    def record_health_check(self):
        """记录系统健康检查"""
        try:
            # 系统资源使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()

            # 网络连接数
            connections = len(psutil.net_connections())

            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO system_health (
                        cpu_percent, memory_percent, disk_percent,
                        network_io, active_connections
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    cpu_percent, memory.percent, disk.percent,
                    json.dumps({
                        'bytes_sent': network.bytes_sent,
                        'bytes_recv': network.bytes_recv
                    }),
                    connections
                ))
                conn.commit()

        except Exception as e:
            logger.error(f"健康检查记录失败: {e}")

    def _get_host_info(self) -> Dict:
        """获取主机信息"""
        try:
            return {
                'hostname': psutil.os.uname().nodename,
                'platform': psutil.os.name,
                'python_version': sys.version.split()[0],
                'process_id': psutil.os.getpid()
            }
        except:
            return {}

    def get_metrics_summary(self, hours: int = 24) -> Dict:
        """获取指标摘要"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 最近的性能指标
                cursor = conn.execute('''
                    SELECT metric_name, AVG(metric_value), MAX(metric_value), MIN(metric_value)
                    FROM performance_metrics
                    WHERE metric_time > datetime('now', '-{} hours')
                    GROUP BY metric_name
                '''.format(hours))

                metrics_summary = {}
                for name, avg_val, max_val, min_val in cursor.fetchall():
                    metrics_summary[name] = {
                        'avg': avg_val,
                        'max': max_val,
                        'min': min_val
                    }

                # 系统健康摘要
                cursor = conn.execute('''
                    SELECT AVG(cpu_percent), AVG(memory_percent), AVG(disk_percent),
                           COUNT(*) as checks
                    FROM system_health
                    WHERE check_time > datetime('now', '-{} hours')
                '''.format(hours))

                health_row = cursor.fetchone()
                health_summary = {
                    'avg_cpu': health_row[0] or 0,
                    'avg_memory': health_row[1] or 0,
                    'avg_disk': health_row[2] or 0,
                    'health_checks': health_row[3] or 0
                }

                return {
                    'metrics': metrics_summary,
                    'health': health_summary,
                    'uptime_hours': (time.time() - self.start_time) / 3600
                }

        except Exception as e:
            logger.error(f"获取指标摘要失败: {e}")
            return {}

def performance_monitor(metric_name: str):
    """性能监控装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time

                # 记录成功执行时间
                monitor = getattr(func, '_performance_monitor', None)
                if monitor:
                    monitor.record_metric(
                        f"{metric_name}_execution_time",
                        execution_time,
                        {'status': 'success'}
                    )

                return result

            except Exception as e:
                execution_time = time.time() - start_time

                # 记录失败执行时间
                monitor = getattr(func, '_performance_monitor', None)
                if monitor:
                    monitor.record_metric(
                        f"{metric_name}_execution_time",
                        execution_time,
                        {'status': 'error', 'error_type': type(e).__name__}
                    )

                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                monitor = getattr(func, '_performance_monitor', None)
                if monitor:
                    monitor.record_metric(
                        f"{metric_name}_execution_time",
                        execution_time,
                        {'status': 'success'}
                    )

                return result

            except Exception as e:
                execution_time = time.time() - start_time

                monitor = getattr(func, '_performance_monitor', None)
                if monitor:
                    monitor.record_metric(
                        f"{metric_name}_execution_time",
                        execution_time,
                        {'status': 'error', 'error_type': type(e).__name__}
                    )

                raise

        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

class GracefulShutdown:
    """优雅停机管理器"""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.shutdown_callbacks = []
        self.is_shutting_down = False

        # 注册信号处理器
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def register_shutdown_callback(self, callback: Callable):
        """注册停机回调"""
        self.shutdown_callbacks.append(callback)

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"接收到停机信号: {signum}")
        asyncio.create_task(self.shutdown())

    async def shutdown(self):
        """执行优雅停机"""
        if self.is_shutting_down:
            return

        self.is_shutting_down = True
        logger.info("开始优雅停机...")

        # 执行停机回调
        shutdown_tasks = []
        for callback in self.shutdown_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    task = asyncio.create_task(callback())
                    shutdown_tasks.append(task)
                else:
                    callback()
            except Exception as e:
                logger.error(f"停机回调执行失败: {e}")

        # 等待所有停机任务完成
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                logger.warning("停机超时，强制退出")

        logger.info("优雅停机完成")

# 全局实例
_connection_pool = ConnectionPool()
_performance_monitor = PerformanceMonitor()
_graceful_shutdown = GracefulShutdown()

async def get_connection_pool() -> ConnectionPool:
    """获取全局连接池"""
    if not _connection_pool._cleanup_task:
        await _connection_pool.start()
    return _connection_pool

def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    return _performance_monitor

def get_graceful_shutdown() -> GracefulShutdown:
    """获取全局优雅停机管理器"""
    return _graceful_shutdown

async def test_retry_mechanism():
    """测试重试机制"""
    print("🔄 测试重试机制...")

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        retry_policy=RetryPolicy.EXPONENTIAL_BACKOFF
    ))
    async def flaky_function():
        import random
        if random.random() < 0.7:  # 70% 失败率
            raise Exception("模拟失败")
        return "成功"

    try:
        result = await flaky_function()
        print(f"✅ 重试成功: {result}")
    except Exception as e:
        print(f"❌ 重试失败: {e}")

async def test_connection_pool():
    """测试连接池"""
    print("🏊 测试连接池...")

    pool = await get_connection_pool()

    async def make_request(url: str):
        async with pool.get_session(url) as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return f"状态: {response.status}"
            except Exception as e:
                return f"错误: {e}"

    # 并发测试
    urls = [
        "http://httpbin.org/delay/1",
        "http://httpbin.org/delay/2",
        "http://httpbin.org/status/200",
    ]

    tasks = [make_request(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        print(f"   请求 {i+1}: {result}")

def test_performance_monitor():
    """测试性能监控"""
    print("📊 测试性能监控...")

    monitor = get_performance_monitor()

    # 记录一些测试指标
    monitor.record_metric("test_metric", 42.5, {"component": "test"})
    monitor.record_metric("response_time", 0.125, {"endpoint": "/api/test"})
    monitor.record_health_check()

    # 获取摘要
    summary = monitor.get_metrics_summary(24)
    print("   性能摘要:")
    for name, stats in summary.get('metrics', {}).items():
        print(f"     {name}: 平均 {stats['avg']:.3f}, 最大 {stats['max']:.3f}")

    health = summary.get('health', {})
    print(f"   系统健康: CPU {health.get('avg_cpu', 0):.1f}%, 内存 {health.get('avg_memory', 0):.1f}%")

async def start_monitoring_service():
    """启动监控服务"""
    print("🔍 启动监控服务...")

    monitor = get_performance_monitor()
    shutdown_manager = get_graceful_shutdown()

    # 注册停机回调
    pool = await get_connection_pool()
    shutdown_manager.register_shutdown_callback(pool.stop)

    try:
        while not shutdown_manager.is_shutting_down:
            # 定期健康检查
            monitor.record_health_check()

            # 记录一些运行时指标
            monitor.record_metric("service_uptime", time.time() - monitor.start_time)

            await asyncio.sleep(60)  # 每分钟检查一次

    except KeyboardInterrupt:
        print("\n接收到中断信号")
    finally:
        await shutdown_manager.shutdown()

def health_check() -> Dict:
    """系统健康检查"""
    print("🏥 执行健康检查...")

    health_status = {
        "status": "healthy",
        "checks": {},
        "timestamp": datetime.now().isoformat()
    }

    try:
        # CPU检查
        cpu_percent = psutil.cpu_percent(interval=1)
        health_status["checks"]["cpu"] = {
            "status": "healthy" if cpu_percent < 80 else "warning",
            "value": f"{cpu_percent:.1f}%"
        }

        # 内存检查
        memory = psutil.virtual_memory()
        health_status["checks"]["memory"] = {
            "status": "healthy" if memory.percent < 85 else "warning",
            "value": f"{memory.percent:.1f}%"
        }

        # 磁盘检查
        disk = psutil.disk_usage('/')
        health_status["checks"]["disk"] = {
            "status": "healthy" if disk.percent < 90 else "warning",
            "value": f"{disk.percent:.1f}%"
        }

        # 检查是否有警告
        if any(check["status"] == "warning" for check in health_status["checks"].values()):
            health_status["status"] = "warning"

    except Exception as e:
        health_status["status"] = "error"
        health_status["error"] = str(e)

    # 打印结果
    status_icon = {"healthy": "✅", "warning": "⚠️", "error": "❌"}[health_status["status"]]
    print(f"{status_icon} 系统状态: {health_status['status']}")

    for check_name, check_result in health_status["checks"].items():
        check_icon = {"healthy": "✅", "warning": "⚠️", "error": "❌"}[check_result["status"]]
        print(f"   {check_icon} {check_name}: {check_result['value']}")

    return health_status

async def main():
    parser = argparse.ArgumentParser(description='Claw Pool Production Utilities')
    parser.add_argument('--test-retry', action='store_true',
                       help='测试重试机制')
    parser.add_argument('--test-pool', action='store_true',
                       help='测试连接池')
    parser.add_argument('--test-monitor', action='store_true',
                       help='测试性能监控')
    parser.add_argument('--start-monitor', action='store_true',
                       help='启动监控服务')
    parser.add_argument('--health-check', action='store_true',
                       help='执行健康检查')

    args = parser.parse_args()

    if args.test_retry:
        await test_retry_mechanism()
    elif args.test_pool:
        await test_connection_pool()
    elif args.test_monitor:
        test_performance_monitor()
    elif args.start_monitor:
        await start_monitoring_service()
    elif args.health_check:
        health_check()
    else:
        print("请指定操作：--test-retry, --test-pool, --test-monitor, --start-monitor, 或 --health-check")

if __name__ == '__main__':
    asyncio.run(main())