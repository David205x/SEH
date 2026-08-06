"""启动本地 Evolution Experiment Observer。"""

from __future__ import annotations

import argparse
from pathlib import Path

from .server import serve


def main() -> None:
    """解析命令行并启动只读网页服务。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-root",
        required=True,
        type=Path,
        help="直接子目录包含 Evolution Run 的观察根目录。",
    )
    parser.add_argument(
        "--port",
        default=8766,
        type=int,
        help="仅本地监听的 HTTP 端口，默认 8766。",
    )
    args = parser.parse_args()
    serve(runs_root=args.runs_root, port=args.port)


if __name__ == "__main__":
    main()
