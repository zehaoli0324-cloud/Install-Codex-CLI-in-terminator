"""
Codex + DeepSeek 命令行入口。

用法：
  codex-deepseek                  启动代理 + 配置
  codex-deepseek proxy            仅启动代理
  codex-deepseek setup            仅生成配置
"""

import argparse
import os
import sys
import textwrap

from . import __version__
from .proxy import run_proxy, PROXY_HOST, PROXY_PORT, DEFAULT_MODEL
from .config import setup_all


def save_api_key(api_key):
    """保存 API Key 到 ~/.bashrc"""
    rc = os.path.expanduser("~/.bashrc")
    with open(rc, "a") as f:
        line = "\nexport DEEPSEEK_API_KEY=" + api_key + "\n"
        f.write(line)
    os.environ["DEEPSEEK_API_KEY"] = api_key
    print("已保存到 " + rc)


def main():
    parser = argparse.ArgumentParser(
        description="Codex + DeepSeek — 让 Codex CLI 用 DeepSeek 模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例：
              codex-deepseek                 启动代理 + 配置
              codex-deepseek proxy           仅启动代理
              codex-deepseek setup           仅生成配置文件
              codex-deepseek --port 9090     指定端口
        """),
    )
    parser.add_argument("--version", action="version", version=f"codex-deepseek v{__version__}")
    parser.add_argument("--port", type=int, default=PROXY_PORT, help=f"代理端口 (默认: {PROXY_PORT})")
    parser.add_argument("--host", default=PROXY_HOST, help=f"监听地址 (默认: {PROXY_HOST})")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名 (默认: {DEFAULT_MODEL})")

    sub = parser.add_subparsers(dest="command", help="子命令")
    sub.add_parser("proxy", help="仅启动代理服务器")
    sub.add_parser("setup", help="仅生成 Codex 配置文件")
    set_key = sub.add_parser("set-key", help="设置/更换 DeepSeek API Key")
    set_key.add_argument("key", nargs="?", help="API Key（不传则交互输入）")

    args = parser.parse_args()

    if args.command == "setup":
        setup_all(model=args.model)
        print("\n配置已生成。运行 'codex' 即可使用 DeepSeek。")

    elif args.command == "set-key":
        key = args.key or input("请输入新的 DeepSeek API Key: ").strip()
        if key:
            save_api_key(key)
            print("✅ API Key 已更新")
        else:
            print("❌ API Key 不能为空", file=sys.stderr)
            sys.exit(1)

    elif args.command == "proxy":
        if not os.environ.get("DEEPSEEK_API_KEY"):
            print("错误: 请设置 DEEPSEEK_API_KEY 环境变量", file=sys.stderr)
            sys.exit(1)
        print(f"启动代理 http://{args.host}:{args.port}")
        print(f"模型: {args.model}")
        print("在另一个终端运行 'codex' 即可使用\n")
        run_proxy(host=args.host, port=args.port)

    else:
        # 默认：配置 + 启动代理
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            api_key = input("请输入 DeepSeek API Key: ").strip()
            if api_key:
                save_api_key(api_key)
            else:
                print("错误: 需要 API Key", file=sys.stderr)
                sys.exit(1)

        setup_all(model=args.model)
        print(f"\n启动代理 http://{args.host}:{args.port} ...")
        print("在另一个终端运行 'codex'，然后按 Enter 退出\n")

        # 后台启动代理
        import threading
        server_stop = [False]

        def serve():
            server = None
            try:
                from .proxy import ThreadingProxy, ProxyHandler
                server = ThreadingProxy((args.host, args.port), ProxyHandler)
                while not server_stop[0]:
                    server.handle_request()
            except KeyboardInterrupt:
                pass
            finally:
                if server:
                    server.server_close()

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

        server_stop[0] = True
        print("\n已退出")
