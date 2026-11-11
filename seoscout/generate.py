#!/usr/bin/env python3
"""
Step 3: Generate articles from collected material.

Reads collected/*.json (output from collect step), sends to LLM,
outputs MDX articles (JS export metadata) to articles/en/.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .core.config import Config
from .core.llm_client import LLMClient
from .core.mdx import validate_mdx_article
from .core.utils import load_json, save_json, ensure_dir


# ── helpers ─────────────────────────────────────────────────────

def keyword_to_slug(keyword: str) -> str:
    """'My Game beginner guide' → 'my-game-beginner-guide'"""
    return re.sub(r'[^a-z0-9-]', '', keyword.lower().replace(' ', '-'))


def keyword_to_filename(keyword: str) -> str:
    """'My Game beginner guide' → 'my_game_beginner_guide'"""
    return re.sub(r'[^a-z0-9_]', '', keyword.lower().replace(' ', '_'))


def load_prompt_template(prompt_path: str = None) -> str:
    """Load prompt template from file or use built-in default."""
    if prompt_path:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    # Built-in default
    default = Path(__file__).parent / "templates" / "generate.md"
    with open(default, 'r', encoding='utf-8') as f:
        return f.read()


def clean_llm_output(content: str) -> str:
    """Strip code fences and trim."""
    content = content.strip()
    if content.startswith('```markdown'):
        content = content[len('```markdown'):].lstrip('\n')
    elif content.startswith('```md'):
        content = content[len('```md'):].lstrip('\n')
    elif content.startswith('```'):
        content = content[3:].lstrip('\n')
    if content.rstrip().endswith('```'):
        content = content.rstrip()[:-3].rstrip()
    return content


def validate_markdown(content: str) -> tuple:
    """Validate generated output before it is saved as an MDX article."""
    return validate_mdx_article(content, minimum_length=200)


# ── main logic ──────────────────────────────────────────────────

async def run_generate(
    project: str,
    keywords_file: str,
    prompt_path: str = None,
    overwrite: bool = False,
    test: bool = False,
    output_dir: str | None = None,
):
    """Generate articles from collected material."""
    Config.init(project, output_dir=output_dir)

    print("=" * 70)
    print(f"  Step 3: Generate [{project}]")
    print("=" * 70)

    # Load prompt template
    prompt_template = load_prompt_template(prompt_path)
    print(f"  📝 Prompt template loaded ({len(prompt_template)} chars)\n")

    # Load keywords with categories from search_results.json
    search_results_path = f"{Config.OUT_DIR}/search_results.json"
    try:
        with open(search_results_path, 'r', encoding='utf-8') as f:
            sr_data = json.load(f)
        keyword_entries = []
        for kw in sr_data.get('keywords', []):
            keyword_entries.append({
                'keyword': kw['keyword'],
                'category': kw.get('category', ''),
            })
    except FileNotFoundError:
        # Fallback: load from keywords file directly
        try:
            with open(keywords_file, 'r', encoding='utf-8') as f:
                kw_data = json.load(f)
        except FileNotFoundError:
            print(f"  ❌ Keywords file not found: {keywords_file}")
            return 1

        keyword_entries = []
        if 'categories' in kw_data:
            for cat in kw_data['categories']:
                for kw in cat.get('keywords', []):
                    keyword_entries.append({'keyword': kw.strip(), 'category': cat.get('category', '')})
        else:
            for kw in kw_data.get('keywords', []):
                keyword_entries.append({'keyword': kw.strip(), 'category': ''})

    if not keyword_entries:
        print("  ❌ No keywords found")
        return 1

    if test:
        keyword_entries = keyword_entries[:2]
        print(f"  🧪 TEST MODE: {len(keyword_entries)} keywords\n")

    # Load collected material for each keyword
    collected_dir = f"{Config.OUT_DIR}/collected"
    articles_dir = f"{Config.DATA_DIR}/articles/en"
    ensure_dir(articles_dir)

    prompts = []
    skipped_no_data = 0
    skipped_exists = 0

    for entry in keyword_entries:
        keyword = entry['keyword']
        category = entry.get('category', '')
        slug = keyword_to_slug(keyword)
        fname = keyword_to_filename(keyword)

        # Look for collected file in category subdir or flat
        if category:
            cat_slug = category.lower().replace(' ', '-')
            collected_path = f"{collected_dir}/{cat_slug}/{fname}.json"
            if not os.path.exists(collected_path):
                collected_path = f"{collected_dir}/{fname}.json"
            output_path = f"{articles_dir}/{cat_slug}/{slug}.mdx"
        else:
            collected_path = f"{collected_dir}/{fname}.json"
            output_path = f"{articles_dir}/{slug}.mdx"

        if not os.path.exists(collected_path):
            skipped_no_data += 1
            continue

        if os.path.exists(output_path) and not overwrite:
            skipped_exists += 1
            continue

        # Load collected content
        merged = load_json(collected_path)
        if not merged or merged.get('total_sources', 0) == 0:
            skipped_no_data += 1
            continue

        merged_json = json.dumps(merged, indent=2, ensure_ascii=False)
        current_date = datetime.now().strftime('%Y-%m-%d')
        cat_slug_final = cat_slug if category else "general"

        prompt = prompt_template.format(
            merged_data=merged_json,
            current_date=current_date,
            category=cat_slug_final,
        )

        prompts.append((prompt, {'keyword': keyword, 'slug': slug, 'output_path': output_path}))

    if skipped_no_data > 0:
        print(f"  ⏭️  Skipped {skipped_no_data} keywords (no collected data)")
    if skipped_exists > 0:
        print(f"  ⏭️  Skipped {skipped_exists} keywords (article exists)")

    if not prompts:
        print("\n  ℹ️  Nothing to generate")
        return 1

    print(f"\n  📝 Generating {len(prompts)} articles...")
    print(f"     Batch size: {Config.GENERATE_BATCH_SIZE}")
    print(f"     Model: {Config.LLM_MODEL}\n")

    # Generate
    client = LLMClient()
    results = await client.generate_batch(prompts)

    # Save results with repair
    saved = 0
    failed = 0
    repair_prompts = []

    for meta, content in results:
        if not content:
            failed += 1
            continue

        cleaned = clean_llm_output(content)
        is_valid, err = validate_markdown(cleaned)

        if is_valid:
            output_path = meta['output_path']
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            saved += 1
            print(f"  ✅ {meta['slug']}.mdx")
        else:
            # Queue for repair
            repair_prompt = _build_repair_prompt(prompt_template, meta, cleaned, err)
            repair_prompts.append((repair_prompt, meta))

    # Repair pass
    if repair_prompts:
        print(f"\n  🔧 Repairing {len(repair_prompts)} articles...")
        repair_results = await client.generate_batch(
            repair_prompts,
            batch_size=min(10, len(repair_prompts)),
        )

        for meta, content in repair_results:
            if not content:
                failed += 1
                continue
            cleaned = clean_llm_output(content)
            is_valid, err = validate_markdown(cleaned)
            if is_valid:
                output_path = meta['output_path']
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned)
                saved += 1
                print(f"  ✅ (repaired) {meta['slug']}.mdx")
            else:
                failed += 1
                print(f"  ❌ {meta['slug']}.mdx — still invalid after repair")

    # Summary
    print("\n" + "=" * 70)
    print(f"  {'✅' if failed == 0 else '⚠️ '} Generate complete")
    print("=" * 70)
    print(f"  Saved:   {saved}")
    print(f"  Failed:  {failed}")
    print(f"  Output:  {articles_dir}/")
    client.print_stats()
    print("=" * 70)
    return 1 if failed else 0


def _build_repair_prompt(template: str, meta: dict, content: str, error: str) -> str:
    """Build a repair prompt asking LLM to fix the invalid output."""
    keyword = meta.get('keyword', 'unknown')
    return (
        f"The previous article draft for keyword \"{keyword}\" had issues:\n"
        f"  Error: {error}\n\n"
        f"Previous draft (for reference, do NOT repeat the same mistakes):\n"
        f"{content[:2000]}\n\n"
        f"Regenerate a COMPLETE article from scratch. Fix the issues above.\n"
        f"Output ONLY valid MDX starting with `export const metadata = {{`.\n"
        f"Use exactly one `export const metadata` block.\n"
        f"The metadata block must end with a line containing only `}};` before the article body.\n"
        f"Do not repeat the metadata export anywhere else in the document.\n"
        f"Do NOT wrap in code blocks."
    )
