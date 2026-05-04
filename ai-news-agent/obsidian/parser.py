"""
Parser de archivos Markdown de Obsidian.

Extrae frontmatter YAML y contenido del cuerpo,
ademas de listas y links en formato Markdown.
"""

import re
from typing import Any


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parsea frontmatter YAML y retorna (metadata, body).

    Args:
        content: Contenido completo del archivo .md

    Returns:
        Tupla de (diccionario con frontmatter, cuerpo sin frontmatter)
    """
    import yaml

    frontmatter: dict[str, Any] = {}
    body = content

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = match.group(2)

    return frontmatter, body


def parse_markdown_list(body: str) -> list[str]:
    """Extrae items de listas Markdown (- item o * item).

    Args:
        body: Texto Markdown

    Returns:
        Lista de strings con el contenido de cada item
    """
    items: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        match = re.match(r"^[-*]\s+(.+)$", line)
        if match:
            items.append(match.group(1).strip())
    return items


def parse_markdown_links(body: str) -> list[tuple[str, str]]:
    """Extrae links en formato [texto](url) del Markdown.

    Args:
        body: Texto Markdown

    Returns:
        Lista de tuplas (texto, url)
    """
    return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)


def extract_urls(body: str) -> list[str]:
    """Extrae todas las URLs de un texto (inline o en links Markdown).

    Args:
        body: Texto Markdown

    Returns:
        Lista de URLs encontradas
    """
    urls: list[str] = []
    # URLs en links Markdown
    for _, url in parse_markdown_links(body):
        urls.append(url)
    # URLs standalone (http/https)
    standalone = re.findall(r"(?<!\()https?://[^\s\)>\]]+", body)
    for url in standalone:
        if url not in urls:
            urls.append(url)
    return urls


def extract_handles(body: str) -> list[str]:
    """Extrae handles de redes sociales (@usuario).

    Args:
        body: Texto Markdown

    Returns:
        Lista de handles (incluyendo el @)
    """
    return re.findall(r"@[\w]+", body)
