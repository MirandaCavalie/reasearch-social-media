"""
Modulo de integracion con Obsidian vault.

Permite leer fuentes de configuracion y escribir briefs diarios
en formato Markdown con frontmatter YAML compatible con Obsidian.
"""

from obsidian.reader import ObsidianReader
from obsidian.writer import ObsidianWriter
from obsidian.parser import parse_frontmatter, parse_markdown_list

__all__ = ["ObsidianReader", "ObsidianWriter", "parse_frontmatter", "parse_markdown_list"]
