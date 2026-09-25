#!/usr/bin/env python3
"""
seoscout CLI — unified entry point.

Usage:
    seoscout search --keywords FILE
    seoscout collect --keywords FILE
    seoscout generate --keywords FILE [--prompt FILE] [--overwrite] [--test]
    seoscout translate --keywords FILE --lang es,pt,de [--prompt FILE] [--overwrite] [--test]
    seoscout run --keywords FILE
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__


def add_output_dir_argument(parser):
    parser.add_argument(
        "--output-dir",
        help="Exact directory for this run's project data (overrides .env OUTPUT_DIR)",
    )


def _derive_project(keywords_file: str) -> str:
    """Derive project name from topic_name in JSON, or fall back to filename."""
    try:
        with open(keywords_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        topic = data.get('topic_name', '').strip()
        if topic:
            return topic.replace(' ', '_').lower()
    except Exception:
        pass
    base = os.path.splitext(os.path.basename(keywords_file))[0]
    return base.replace(' ', '_').lower()


def main():
    parser = argparse.ArgumentParser(
        prog="seoscout",
        description="Keyword research, content collection, article generation & translation CLI for SEO"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── search ──
    search_parser = subparsers.add_parser(
        "search",
        help="Search keywords on YouTube and Google → search_results.json"
    )
    search_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    add_output_dir_argument(search_parser)

    # ── collect ──
    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect YouTube transcripts and web content from search results"
    )
    collect_parser.add_argument(
        "--project", "-p",
        help="Project name (auto-derived from keywords file if not set)"
    )
    collect_parser.add_argument(
        "--keywords", "-k",
        help="Keywords JSON file (used to derive project name if --project not set)"
    )
    add_output_dir_argument(collect_parser)

    # ── generate ──
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate Markdown articles from collected material using LLM"
    )
    gen_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    gen_parser.add_argument(
        "--prompt",
        help="Path to custom prompt template (default: built-in)"
    )
    gen_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing articles"
    )
    gen_parser.add_argument(
        "--test", action="store_true",
        help="Test mode: only generate 2 articles"
    )
    add_output_dir_argument(gen_parser)

    # ── translate ──
    trans_parser = subparsers.add_parser(
        "translate",
        help="Translate English articles to other languages using LLM"
    )
    trans_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file (used to derive project name)"
    )
    trans_parser.add_argument(
        "--lang", "-l",
        help="Target languages, comma-separated (e.g. es,pt,de,fr,ja). If not set, reads from 'languages' field in keywords JSON."
    )
    trans_parser.add_argument(
        "--prompt",
        help="Path to custom translation prompt template (default: built-in)"
    )
    trans_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing translations"
    )
    trans_parser.add_argument(
        "--test", action="store_true",
        help="Test mode: only translate 1 article"
    )
    add_output_dir_argument(trans_parser)

    # ── run (search + collect + generate) ──
    run_parser = subparsers.add_parser(
        "run",
        help="Search, collect, generate (and translate if languages set) in one step"
    )
    run_parser.add_argument(
        "--keywords", "-k", required=True,
        help="Path to keywords JSON file"
    )
    run_parser.add_argument(
        "--prompt",
        help="Path to custom prompt template for generation"
    )
    run_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing articles"
    )
    add_output_dir_argument(run_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Derive project name
    if args.command in ("search", "generate", "run"):
        args.project = _derive_project(args.keywords)
        print(f"📁 Project: {args.project}\n")
    elif args.command == "collect":
        if args.project:
            pass
        elif args.keywords:
            args.project = _derive_project(args.keywords)
        else:
            print("❌ Need --project or --keywords to identify project")
            sys.exit(1)
    elif args.command == "translate":
        args.project = _derive_project(args.keywords)
        print(f"📁 Project: {args.project}\n")

    exit_code = 0
    if args.command == "search":
        asyncio.run(_run_search(args))
    elif args.command == "collect":
        asyncio.run(_run_collect(args))
    elif args.command == "generate":
        asyncio.run(_run_generate(args))
    elif args.command == "translate":
        asyncio.run(_run_translate(args))
    elif args.command == "run":
        exit_code = asyncio.run(_run_all(args))

    sys.exit(exit_code)


async def _run_search(args):
    from .search import run_search
    await run_search(args.project, args.keywords, output_dir=args.output_dir)


async def _run_collect(args):
    from .collect import run_collect
    await run_collect(args.project, output_dir=args.output_dir)


async def _run_generate(args):
    from .generate import run_generate
    await run_generate(
        args.project,
        args.keywords,
        prompt_path=args.prompt,
        overwrite=args.overwrite,
        test=args.test,
        output_dir=args.output_dir,
    )


async def _run_translate(args):
    from .translate import run_translate
    from .core.utils import load_languages_from_json

    # --lang not provided → read from keywords JSON
    if not args.lang:
        langs = load_languages_from_json(args.keywords)
        if not langs:
            print("❌ No --lang specified and no 'languages' field in keywords JSON")
            sys.exit(1)
        args.lang = ",".join(langs)
        print(f"🌐 Languages from JSON: {args.lang}\n")

    await run_translate(
        args.project,
        args.lang,
        prompt_path=args.prompt,
        overwrite=args.overwrite,
        test=args.test,
        output_dir=args.output_dir,
    )


async def _run_all(args):
    from .search import run_search
    from .collect import run_collect
    from .generate import run_generate
    from .translate import run_translate
    from .core.utils import load_languages_from_json

    await run_search(args.project, args.keywords, output_dir=args.output_dir)
    await run_collect(args.project, output_dir=args.output_dir)
    await run_generate(
        args.project,
        args.keywords,
        prompt_path=args.prompt,
        overwrite=args.overwrite,
        output_dir=args.output_dir,
    )

    # If languages are specified in JSON, auto-translate
    langs = load_languages_from_json(args.keywords)
    if langs:
        lang_str = ",".join(langs)
        print(f"\n{'='*70}")
        print(f"  Step 4: Translate [{args.project}] → {lang_str}")
        print(f"{'='*70}")
        await run_translate(
            args.project,
            lang_str,
            prompt_path=None,
            overwrite=args.overwrite,
            output_dir=args.output_dir,
        )

    if verify_run_output(args.keywords, args.output_dir, args.project):
        return 0
    return 1


def verify_run_output(keywords_file: str, output_dir: str | None, project: str) -> bool:
    """Confirm exactly one MDX article exists for every keyword and language."""
    from .core.utils import load_keywords_from_json, load_languages_from_json
    from .generate import keyword_to_slug

    entries = load_keywords_from_json(keywords_file)
    data_dir = Path(output_dir).resolve() if output_dir else Path(
        os.getenv("OUTPUT_DIR", "./output")
    ) / project.replace('.', '_').replace('/', '_')
    en_dir = data_dir / "articles" / "en"

    expected_en = set()
    for entry in entries:
        relative = Path(keyword_to_slug(entry["keyword"]) + ".mdx")
        if entry.get("category"):
            relative = Path(entry["category"].lower().replace(" ", "-")) / relative
        expected_en.add(relative)

    if len(expected_en) != len(entries):
        print("❌ One-page validation failed: keyword filename collision")
        return False

    actual_en = {
        path.relative_to(en_dir)
        for path in en_dir.glob("**/*.mdx")
    } if en_dir.exists() else set()

    valid = True
    if actual_en != expected_en:
        print(
            "❌ One-page validation failed: "
            f"expected {len(expected_en)} English MDX, found {len(actual_en)}"
        )
        missing = expected_en - actual_en
        unexpected = actual_en - expected_en
        if missing:
            print(f"   Missing: {', '.join(map(str, sorted(missing)))}")
        if unexpected:
            print(f"   Unexpected: {', '.join(map(str, sorted(unexpected)))}")
        valid = False

    languages = load_languages_from_json(keywords_file)
    if len(set(languages)) != len(languages):
        print("❌ One-page validation failed: duplicate language codes")
        valid = False

    for language in languages:
        language_dir = data_dir / "articles" / language
        actual_language = {
            path.relative_to(language_dir)
            for path in language_dir.glob("**/*.mdx")
        } if language_dir.exists() else set()
        if actual_language != expected_en:
            print(
                "❌ Translation validation failed "
                f"[{language}]: expected {len(expected_en)} MDX, found {len(actual_language)}"
            )
            valid = False

    if valid:
        print(
            f"✅ One-page validation passed: {len(expected_en)} English MDX"
            + (f", {len(languages)} language(s)" if languages else "")
        )
    return valid


if __name__ == "__main__":
    main()
