"""Validation helpers for LLM-generated MDX articles."""

import re


_METADATA_EXPORT = re.compile(r"^export const metadata[ \t]*=", re.MULTILINE)
_METADATA_END = re.compile(r"^};[ \t]*$", re.MULTILINE)


def validate_mdx_article(content: str, minimum_length: int) -> tuple[bool, str]:
    """Validate the MDX shape required for generated and translated articles."""
    if not content or not content.strip():
        return False, "Empty content"

    normalized = content.lstrip("\ufeff \t\r\n")
    first_export = _METADATA_EXPORT.search(normalized)
    if first_export is None or first_export.start() != 0:
        return False, "MDX must start with an export const metadata block"

    metadata_count = len(_METADATA_EXPORT.findall(normalized))
    if metadata_count != 1:
        return False, f"Expected exactly one metadata export, found {metadata_count}"

    metadata_end = _METADATA_END.search(normalized, first_export.end())
    if metadata_end is None:
        return False, "Metadata export is missing its closing };"

    if not normalized[metadata_end.end():].strip():
        return False, "Article body is missing after metadata export"

    if len(normalized) < minimum_length:
        return False, f"Content too short ({len(normalized)} chars)"

    return True, ""
