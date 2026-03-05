#!/bin/bash

# Claw Pool 安装脚本
# 用于快速设置开发和测试环境

echo "🦞 Claw Pool 安装脚本"
echo "======================"

# 检查 Python 版本
echo "检查 Python 环境..."
python3 --version
if [ $? -ne 0 ]; then
    echo "❌ 错误: 需要 Python 3.8 或更高版本"
    exit 1
fi

# 检查 OpenClaw
echo "检查 OpenClaw..."
openclaw --version
if [ $? -ne 0 ]; then
    echo "❌ 错误: 需要安装 OpenClaw"
    echo "   请访问 https://openclaw.com 获取安装指南"
    exit 1
fi

# 安装 Python 依赖
echo "安装 Python 依赖包..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Python 依赖安装完成"
else
    echo "❌ Python 依赖安装失败"
    exit 1
fi

# 创建必要的目录
echo "创建运行时目录..."
mkdir -p ~/.openclaw/logs
mkdir -p ~/.openclaw/pool_data

# 设置脚本执行权限
echo "设置脚本权限..."
chmod +x skills/claw-pool-agent/scripts/*.py
chmod +x skills/claw-pool-controller/scripts/*.py

echo "✅ Claw Pool 安装完成！"
echo ""
echo "下一步："
echo "1. 配置 Pool Controller:"
echo "   cd skills/claw-pool-controller"
echo "   cp config/pool.json ~/.openclaw/pool-controller.json"
echo ""
echo "2. 配置 Pool Agent:"
echo "   cd skills/claw-pool-agent"
echo "   cp config/pool.json ~/.openclaw/pool-agent.json"
echo ""
echo "3. 查看文档:"
echo "   cat README.md"
echo ""
echo "🎉 开始使用 Claw Pool!"