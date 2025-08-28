#!/usr/bin/env python3
# manage_config.py
#
# Utility script to add or remove site entries and update the
# configuration file.  This script simplifies modifying `config.yaml`
# without manually editing YAML.  It also creates parser stubs for
# new sites by copying the generic parser template.  Usage examples:
#
#   python manage_config.py add-site npc "Nigeria Property Centre" https://example.com
#   python manage_config.py remove-site npc
#   python manage_config.py add-location "Lekki Phase 1"
#   python manage_config.py remove-location "Ikate"

import argparse
from pathlib import Path
from shutil import copyfile
import yaml


CONFIG_PATH = Path(__file__).parent / "config.yaml"
PARSERS_DIR = Path(__file__).parent / "parsers"
TEMPLATE_PATH = PARSERS_DIR / "specials.py"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def add_site(key: str, name: str, url: str, parser: str = "special") -> None:
    config = load_config()
    config.setdefault("sites", {})[key] = {"name": name, "url": url, "parser": parser}
    if key not in config.get("enabled_sites", []):
        config.setdefault("enabled_sites", []).append(key)
    # Create a parser stub if it doesn't exist
    parser_file = PARSERS_DIR / f"{key}.py"
    if not parser_file.exists():
        # Copy the specials template as a starting point
        copyfile(TEMPLATE_PATH, parser_file)
    save_config(config)


def remove_site(key: str) -> None:
    config = load_config()
    config.get("sites", {}).pop(key, None)
    if key in config.get("enabled_sites", []):
        config["enabled_sites"].remove(key)
    parser_file = PARSERS_DIR / f"{key}.py"
    if parser_file.exists() and parser_file.is_file():
        parser_file.unlink()
    save_config(config)


def add_location(location: str) -> None:
    config = load_config()
    config.setdefault("locations", [])
    if location not in config["locations"]:
        config["locations"].append(location)
        save_config(config)


def remove_location(location: str) -> None:
    config = load_config()
    if location in config.get("locations", []):
        config["locations"].remove(location)
        save_config(config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage config.yaml for the Realtor scraper")
    sub = parser.add_subparsers(dest="command")

    add_site_parser = sub.add_parser("add-site", help="Add a new site definition")
    add_site_parser.add_argument("key")
    add_site_parser.add_argument("name")
    add_site_parser.add_argument("url")
    add_site_parser.add_argument("--parser", default="special")

    remove_site_parser = sub.add_parser("remove-site", help="Remove a site definition")
    remove_site_parser.add_argument("key")

    add_loc_parser = sub.add_parser("add-location", help="Add a target location")
    add_loc_parser.add_argument("location")

    remove_loc_parser = sub.add_parser("remove-location", help="Remove a target location")
    remove_loc_parser.add_argument("location")

    args = parser.parse_args()
    if args.command == "add-site":
        add_site(args.key, args.name, args.url, args.parser)
        print(f"Added site {args.key}")
    elif args.command == "remove-site":
        remove_site(args.key)
        print(f"Removed site {args.key}")
    elif args.command == "add-location":
        add_location(args.location)
        print(f"Added location {args.location}")
    elif args.command == "remove-location":
        remove_location(args.location)
        print(f"Removed location {args.location}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()