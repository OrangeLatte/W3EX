from __future__ import annotations

import argparse
import asyncio

from w3ex.db.seed import seed_database
from w3ex.db.session import drop_db, get_session_factory, init_db
from w3ex.providers.mock.generator import MockDataset


async def cmd_init_db() -> None:
    await init_db()
    print("数据库表已创建")


async def cmd_seed(size: str) -> None:
    await init_db()
    dataset = MockDataset()
    factory = get_session_factory()
    async with factory() as session:
        counts = await seed_database(session, dataset)
    print(f"seed 完成（size={size}）: {counts}")


async def cmd_reset() -> None:
    await drop_db()
    print("数据库已删除")


def main() -> None:
    parser = argparse.ArgumentParser(prog="w3ex", description="Web3 Exchange CLI（行情+交易）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="创建全部表")
    seed_p = sub.add_parser("seed", help="写入种子数据（自选/报价单等表）")
    seed_p.add_argument("--size", choices=["small", "full"], default="small")
    sub.add_parser("reset", help="删除数据库")

    args = parser.parse_args()
    if args.command == "init-db":
        asyncio.run(cmd_init_db())
    elif args.command == "seed":
        asyncio.run(cmd_seed(args.size))
    elif args.command == "reset":
        asyncio.run(cmd_reset())


if __name__ == "__main__":
    main()
