#!/usr/bin/env uv run python
"""
测试 ClawReef CLI 的核心功能
"""

import sys
import os
sys.path.insert(0, '.')
sys.path.insert(0, 'scripts')

from scripts.reef_cli import detect_network_addresses, generate_invite_code, parse_invite_code

def test_network_detection():
    """测试网络地址检测"""
    print("🌐 测试网络地址检测...")
    addresses = detect_network_addresses()
    print(f"检测到地址: {addresses}")
    assert len(addresses) > 0, "应该至少检测到一个地址"
    print("✅ 网络地址检测测试通过")

def test_invite_code():
    """测试邀请码生成和解析"""
    print("📋 测试邀请码生成和解析...")

    # 生成邀请码
    name = "Test Reef"
    hosts = ["192.168.1.100", "100.64.0.1"]
    port = 18789

    invite_code = generate_invite_code(name, hosts, port)
    print(f"生成的邀请码: {invite_code}")

    assert invite_code.startswith("reef_"), "邀请码应该以 reef_ 开头"

    # 解析邀请码
    parsed = parse_invite_code(invite_code)
    print(f"解析结果: {parsed}")

    assert parsed["name"] == name, "名称不匹配"
    assert parsed["hosts"] == hosts, "主机列表不匹配"
    assert parsed["port"] == port, "端口不匹配"
    assert "created" in parsed, "应该包含创建时间"

    print("✅ 邀请码生成和解析测试通过")

def main():
    print("🧪 开始测试 ClawReef CLI 核心功能...")

    try:
        test_network_detection()
        test_invite_code()

        print("🎉 所有测试通过!")
        print("\n📋 示例邀请码:")
        sample_code = generate_invite_code("Cherway's Reef", ["192.168.1.100", "100.64.0.1"], 18789)
        print(f"   {sample_code}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
