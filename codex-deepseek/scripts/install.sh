#!/bin/bash
# Codex + DeepSeek 一键安装脚本
set -e

echo "=============================="
echo " Codex + DeepSeek 安装"
echo "=============================="

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 需要 Python 3.10+"
    exit 1
fi
echo "✓ Python $(python3 --version)"

# 2. 检查/安装 Codex CLI
if ! command -v codex &>/dev/null; then
    echo "→ 安装 Codex CLI..."
    curl -fsSL https://chatgpt.com/codex/install.sh | sh
fi
echo "✓ Codex $(codex --version 2>&1 | head -1)"

# 3. 安装本项目
echo "→ 安装 codex-deepseek..."
pip3 install --user -e "$(dirname "$0")"
echo "✓ 安装完成"

# 4. API Key
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo ""
    read -p "请输入 DeepSeek API Key: " key
    if [ -n "$key" ]; then
        echo "export DEEPSEEK_API_KEY=$key" >> ~/.bashrc
        export DEEPSEEK_API_KEY=$key
        echo "✓ 已保存到 ~/.bashrc"
    fi
fi

echo ""
echo "=============================="
echo " 使用方式:"
echo "  codex-deepseek         启动代理 + 配置"
echo "  codex-deepseek proxy   仅启动代理"
echo "  codex-deepseek setup   仅生成配置"
echo ""
echo " 然后在另一个终端运行: codex"
echo "=============================="
