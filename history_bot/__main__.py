"""Reproducible commands: doctor, download, ingest, retrieve, ask, evaluate."""
import argparse
import json
import sys

from .config import Settings
from .errors import BotError, InputError
from .ingest import download_catalogue, ingest


def main():
    parser = argparse.ArgumentParser(description="Orient BlackSwan History Bot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local configuration without network requests or revealing credentials")
    sub.add_parser("download", help="Download the exact catalogue PDF")
    ingest_parser = sub.add_parser("ingest", help="Create/reuse the persistent index")
    ingest_parser.add_argument("--rebuild", action="store_true", help="Replace this configuration's collection; stop the UI first")
    for name in ["retrieve", "ask"]:
        p = sub.add_parser(name)
        p.add_argument("question")
    sub.add_parser("evaluate", help="Run the assessment and additional checks with the real model")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.command == "doctor":
            from .diagnostics import diagnose
            result = diagnose(settings)
        elif args.command == "download":
            result = download_catalogue(settings)
        elif args.command == "ingest":
            result = ingest(settings, rebuild=args.rebuild)
        elif args.command == "evaluate":
            from .evaluation import evaluate
            result = evaluate(settings)
        else:
            from .service import CatalogueBot
            bot = CatalogueBot(settings)
            result = bot.retrieve(args.question) if args.command == "retrieve" else bot.ask(args.question).as_dict()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (BotError, InputError, ValueError, OSError) as exc:
        print(f"Application error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
