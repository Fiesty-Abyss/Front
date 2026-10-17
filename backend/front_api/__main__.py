"""python -m front_api [--host 127.0.0.1] [--port 8000]"""

from __future__ import annotations

import argparse


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="启动 Front 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("front_api.main:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
