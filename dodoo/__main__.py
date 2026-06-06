import argparse
import asyncio
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dodoo", description="Dodoo ERP core")
    sub = parser.add_subparsers(dest="command")

    srv = sub.add_parser("server", help="Start the HTTP server")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8069)
    srv.add_argument("--database-url", default="")

    mod = sub.add_parser("module", help="Module management")
    mod_sub = mod.add_subparsers(dest="module_command")
    inst = mod_sub.add_parser("install", help="Install a module")
    inst.add_argument("name")

    return parser


async def _run_server(args: argparse.Namespace) -> None:
    import uvicorn

    from dodoo import Environment
    from dodoo.http.app import create_app

    env = await Environment.create(database_url=args.database_url)
    app = create_app(env)
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_config=None,
        access_log=True,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _run_module_install(args: argparse.Namespace) -> None:
    from dodoo import Environment
    from dodoo.core.exceptions import CycleError, ModuleLoadError

    env = await Environment.create()
    try:
        await env.modules.install(args.name)
        print(f"Module '{args.name}' installed successfully.")
    except (ModuleLoadError, CycleError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await env.close()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "server":
        asyncio.run(_run_server(args))
    elif args.command == "module" and args.module_command == "install":
        asyncio.run(_run_module_install(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
