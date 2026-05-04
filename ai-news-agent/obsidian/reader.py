"""
Lector de archivos del vault de Obsidian.

Lee configuracion de fuentes (RSS, influencers, keywords)
y learnings desde archivos .md del vault.
"""

import logging
from pathlib import Path

from obsidian.parser import (
    extract_handles,
    extract_urls,
    parse_frontmatter,
    parse_markdown_list,
)

logger = logging.getLogger("obsidian.reader")


class ObsidianReader:
    """Lee archivos de configuracion y contenido desde un vault de Obsidian."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Vault de Obsidian no encontrado: {vault_path}")

    def _read_file(self, relative_path: str) -> str | None:
        """Lee un archivo del vault. Retorna None si no existe."""
        file_path = self.vault_path / relative_path
        if not file_path.exists():
            logger.warning(f"Archivo no encontrado en vault: {relative_path}")
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error leyendo {relative_path}: {e}")
            return None

    def read_rss_feeds(self) -> list[dict[str, str]]:
        """Lee URLs de RSS desde Sources/rss-feeds.md.

        Espera un formato con listas Markdown donde cada item tiene:
        - [Nombre del feed](url)
        o simplemente:
        - url

        Returns:
            Lista de dicts con 'name' y 'url'
        """
        content = self._read_file("Sources/rss-feeds.md")
        if not content:
            return []

        _, body = parse_frontmatter(content)
        feeds: list[dict[str, str]] = []

        for line in body.splitlines():
            line = line.strip()
            if not line.startswith(("-", "*")):
                continue

            # Intentar formato [nombre](url)
            import re
            link_match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", line)
            if link_match:
                feeds.append({"name": link_match.group(1), "url": link_match.group(2)})
                continue

            # Intentar URL directa en el item
            url_match = re.search(r"(https?://[^\s]+)", line)
            if url_match:
                url = url_match.group(1)
                # Usar el texto antes de la URL como nombre, o la URL misma
                name = re.sub(r"^[-*]\s*", "", line).replace(url, "").strip(" -—:")
                feeds.append({"name": name or url, "url": url})

        logger.info(f"RSS feeds leidos de Obsidian: {len(feeds)}")
        return feeds

    def read_influencers(self) -> dict:
        """Lee handles y feeds de influencers desde Sources/influencers.md.

        Espera formato con secciones para RSS feeds y Twitter handles.

        Returns:
            Dict con 'rss_feeds' y 'twitter_handles'
        """
        content = self._read_file("Sources/influencers.md")
        if not content:
            return {}

        _, body = parse_frontmatter(content)

        result: dict = {"rss_feeds": [], "twitter_handles": []}

        # Detectar secciones por headers
        current_section = ""
        for line in body.splitlines():
            stripped = line.strip()

            if stripped.startswith("#"):
                header = stripped.lstrip("#").strip().lower()
                if "rss" in header or "youtube" in header or "blog" in header:
                    current_section = "rss"
                elif "twitter" in header or "x/" in header or "handles" in header:
                    current_section = "twitter"
                continue

            if not stripped.startswith(("-", "*")):
                continue

            if current_section == "twitter":
                handles = extract_handles(stripped)
                result["twitter_handles"].extend(handles)
            elif current_section == "rss":
                import re
                link_match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", stripped)
                if link_match:
                    # Detectar plataforma por URL
                    url = link_match.group(2)
                    platform = "blog"
                    if "youtube.com" in url:
                        platform = "youtube"
                    result["rss_feeds"].append({
                        "name": link_match.group(1),
                        "url": url,
                        "platform": platform,
                    })
                else:
                    url_match = re.search(r"(https?://[^\s]+)", stripped)
                    if url_match:
                        url = url_match.group(1)
                        platform = "youtube" if "youtube.com" in url else "blog"
                        name = re.sub(r"^[-*]\s*", "", stripped).replace(url, "").strip(" -—:")
                        result["rss_feeds"].append({
                            "name": name or url,
                            "url": url,
                            "platform": platform,
                        })

        logger.info(
            f"Influencers leidos de Obsidian: {len(result['rss_feeds'])} RSS, "
            f"{len(result['twitter_handles'])} Twitter"
        )
        return result

    def read_keywords(self) -> dict[str, list[str]]:
        """Lee keywords de filtrado desde Sources/keywords.md.

        Espera secciones con headers (## HN Keywords, ## High Value, etc.)
        y listas de keywords bajo cada seccion.

        Returns:
            Dict con categoria -> lista de keywords
        """
        content = self._read_file("Sources/keywords.md")
        if not content:
            return {}

        _, body = parse_frontmatter(content)

        keywords: dict[str, list[str]] = {}
        current_section = ""

        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                current_section = stripped.lstrip("#").strip().lower().replace(" ", "_")
                keywords[current_section] = []
                continue

            if current_section and stripped.startswith(("-", "*")):
                item = stripped.lstrip("-* ").strip()
                if item:
                    keywords[current_section].append(item)

        logger.info(f"Keywords leidas de Obsidian: {sum(len(v) for v in keywords.values())} total")
        return keywords

    def read_learnings(self) -> str:
        """Lee learnings desde Learnings/what-works.md.

        Retorna el contenido completo para usar como contexto
        adicional en el system prompt de Claude.

        Returns:
            Contenido del archivo o string vacio
        """
        content = self._read_file("Learnings/what-works.md")
        if not content:
            return ""

        _, body = parse_frontmatter(content)
        logger.info(f"Learnings cargados de Obsidian: {len(body)} caracteres")
        return body.strip()
