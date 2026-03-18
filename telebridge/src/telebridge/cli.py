"""Main CLI entry point for telebridge."""

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="telebridge",
        description="Telegram bridge for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="subcommands", required=False)

    # Run subcommand (default)
    run_parser = subparsers.add_parser("run", help="Run the telebridge bot")
    run_parser.add_argument(
        "--config", "-c",
        help="Path to config.toml file",
    )
    run_parser.set_defaults(func=cmd_run)

    # Hook subcommand
    hook_parser = subparsers.add_parser("hook", help="Handle SessionStart hook callback (reads JSON from stdin)")
    hook_parser.set_defaults(func=cmd_hook)

    # Install-hook subcommand
    install_parser = subparsers.add_parser("install-hook", help="Install SessionStart hook in Claude Code settings")
    install_parser.set_defaults(func=cmd_install_hook)

    args = parser.parse_args()

    # Default to 'run' if no subcommand provided
    if not hasattr(args, 'func'):
        args.config = None
        cmd_run(args)
        return

    # Call the appropriate function
    args.func(args)


def cmd_run(args: argparse.Namespace) -> None:
    """Run the telebridge bot."""
    from telebridge.app import TelebridgeApp
    from telebridge.config import load_config

    config = load_config(args.config)
    app = TelebridgeApp(config)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        sys.exit(0)


def cmd_hook(args: argparse.Namespace) -> None:
    """Handle SessionStart hook callback."""
    from telebridge.hook import handle_hook

    handle_hook()


def cmd_install_hook(args: argparse.Namespace) -> None:
    """Install SessionStart hook in Claude Code settings."""
    from telebridge.hook import install_hook

    installed = install_hook()
    if installed:
        print("Hook installed successfully.")
    else:
        print("Hook already installed.")
