import argparse
import os

import uvicorn
from backend.app import app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mail_summariser backend")
    parser.add_argument("--host", default=os.getenv("BACKEND_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BACKEND_PORT", "8766")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
