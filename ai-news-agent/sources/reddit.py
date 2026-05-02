"""
Recolector de articulos desde Reddit via RSS feeds.

Usa feedparser para parsear los feeds RSS publicos de subreddits.
No requiere API key ni autenticacion — solo agrega .rss a la URL del subreddit.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

from sources.models import Article

# Configuracion del logger con formato estandar del proyecto
logger = logging.getLogger(__name__)

# Timeout global para peticiones HTTP en segundos
HTTP_TIMEOUT: int = 30

# User-Agent personalizado para evitar bloqueos de Reddit
# Reddit bloquea requests sin User-Agent o con User-Agent generico
USER_AGENT: str = (
    "AINewsAgent/1.0 (Python; feedparser; "
    "compatible research bot; +https://github.com/ai-news-agent)"
)


def _parse_reddit_date(entry: feedparser.FeedParserDict) -> datetime:
    """Extrae la fecha de publicacion de un entry de Reddit RSS.

    Reddit usa el campo 'updated_parsed' en sus feeds RSS.
    Si no esta disponible, intenta con 'published_parsed'.

    Args:
        entry: Entrada parseada por feedparser.

    Returns:
        Fecha de publicacion como datetime con timezone UTC.
    """
    time_struct = getattr(entry, "updated_parsed", None) or getattr(
        entry, "published_parsed", None
    )

    if time_struct:
        try:
            return datetime.fromtimestamp(mktime(time_struct), tz=timezone.utc)
        except (ValueError, OverflowError, OSError) as e:
            logger.warning(f"Error parseando fecha de entry de Reddit: {e}")

    # Fallback: hora actual
    return datetime.now(tz=timezone.utc)


def _extract_reddit_summary(entry: feedparser.FeedParserDict) -> str:
    """Extrae el resumen/contenido de un entry de Reddit RSS.

    Los feeds de Reddit incluyen el contenido en el campo 'summary'
    o en 'content'. Se limpia el HTML basico.

    Args:
        entry: Entrada parseada por feedparser.

    Returns:
        Resumen limpio como string.
    """
    # Reddit pone el contenido en 'summary' o en 'content'
    raw_summary: str = getattr(entry, "summary", "") or ""

    if not raw_summary:
        content_list = getattr(entry, "content", [])
        if content_list and len(content_list) > 0:
            raw_summary = content_list[0].get("value", "")

    # Limpiar tags HTML
    clean_summary: str = re.sub(r"<[^>]+>", "", raw_summary)

    # Remover entidades HTML comunes
    clean_summary = clean_summary.replace("&amp;", "&")
    clean_summary = clean_summary.replace("&lt;", "<")
    clean_summary = clean_summary.replace("&gt;", ">")
    clean_summary = clean_summary.replace("&quot;", '"')
    clean_summary = clean_summary.replace("&#39;", "'")

    # Limitar longitud
    if len(clean_summary) > 500:
        clean_summary = clean_summary[:497] + "..."

    return clean_summary.strip()


def _extract_subreddit_name(url: str) -> str:
    """Extrae el nombre del subreddit desde la URL del feed RSS.

    Args:
        url: URL del feed RSS de Reddit.
             Ejemplo: 'https://www.reddit.com/r/MachineLearning/hot/.rss'

    Returns:
        Nombre del subreddit (e.g. 'r/MachineLearning') o 'Reddit' si no se puede extraer.
    """
    match = re.search(r"/(r/[^/]+)/", url)
    if match:
        return match.group(1)
    return "Reddit"


def fetch_reddit_articles(subreddit_urls: list[str]) -> list[Article]:
    """Recolecta articulos de multiples subreddits via RSS.

    Descarga y parsea el feed RSS de cada subreddit.
    Si un subreddit falla, se registra el error y se continua con los demas.

    Args:
        subreddit_urls: Lista de URLs RSS de subreddits.
                        Ejemplo: ['https://www.reddit.com/r/MachineLearning/hot/.rss']

    Returns:
        Lista de Article con los posts recolectados de todos los subreddits.
    """
    articles: list[Article] = []

    for feed_url in subreddit_urls:
        subreddit_name: str = _extract_subreddit_name(feed_url)
        logger.info(f"Descargando feed de Reddit: {subreddit_name} ({feed_url})")

        try:
            # Descargar el feed con User-Agent personalizado y timeout
            response = requests.get(
                feed_url,
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()

            # Parsear con feedparser
            parsed = feedparser.parse(response.content)

            if parsed.bozo and not parsed.entries:
                logger.warning(
                    f"Feed de Reddit '{subreddit_name}' tiene errores de parseo "
                    f"y no tiene entries: {parsed.bozo_exception}"
                )
                continue

            subreddit_count: int = 0

            for entry in parsed.entries:
                # Extraer titulo
                title: str = getattr(entry, "title", "") or ""
                if not title:
                    continue

                # Extraer link — Reddit RSS pone el link al post
                link: str = getattr(entry, "link", "") or ""
                if not link:
                    continue

                # Extraer fecha y resumen
                published_at: datetime = _parse_reddit_date(entry)

                # Filtrar posts con mas de 48 horas de antiguedad
                now = datetime.now(tz=timezone.utc)
                if (now - published_at) > timedelta(hours=48):
                    continue

                summary: str = _extract_reddit_summary(entry)

                # Construir la fuente con el nombre del subreddit
                source_name: str = f"Reddit ({subreddit_name})"

                article = Article(
                    title=title.strip(),
                    url=link.strip(),
                    source=source_name,
                    published_at=published_at,
                    summary=summary,
                )
                articles.append(article)
                subreddit_count += 1

            logger.info(
                f"Reddit '{subreddit_name}': {subreddit_count} posts recolectados"
            )

        except requests.exceptions.Timeout:
            logger.error(
                f"Timeout al descargar feed de Reddit '{subreddit_name}' "
                f"({feed_url})"
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error HTTP al descargar feed de Reddit '{subreddit_name}': {e}"
            )
        except Exception as e:
            logger.error(
                f"Error inesperado procesando feed de Reddit "
                f"'{subreddit_name}': {e}"
            )

    logger.info(
        f"Reddit total: {len(articles)} posts recolectados de "
        f"{len(subreddit_urls)} subreddits"
    )
    return articles
