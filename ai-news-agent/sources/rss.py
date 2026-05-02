"""
Recolector de articulos desde RSS feeds usando feedparser.

Cada feed se descarga con requests (timeout 30s) y luego se parsea
con feedparser para extraer titulo, link, fecha y resumen.
"""

import logging
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

from sources.models import Article

# Configuracion del logger con formato estandar del proyecto
logger = logging.getLogger(__name__)

# Timeout global para peticiones HTTP en segundos
HTTP_TIMEOUT: int = 30

# Ventana maxima de antiguedad para articulos (en horas)
MAX_AGE_HOURS: int = 48


def _parse_published_date(entry: feedparser.FeedParserDict) -> datetime:
    """Intenta extraer la fecha de publicacion de un entry de feedparser.

    Busca en published_parsed y updated_parsed. Si no encuentra ninguna,
    retorna la fecha/hora actual como fallback.

    Args:
        entry: Entrada parseada por feedparser.

    Returns:
        Fecha de publicacion como datetime con timezone UTC.
    """
    # Intentar con published_parsed primero, luego updated_parsed
    time_struct = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )

    if time_struct:
        try:
            return datetime.fromtimestamp(mktime(time_struct), tz=timezone.utc)
        except (ValueError, OverflowError, OSError) as e:
            logger.warning(f"Error parseando fecha de entry: {e}")

    # Fallback: usar la hora actual
    return datetime.now(tz=timezone.utc)


def _extract_summary(entry: feedparser.FeedParserDict) -> str:
    """Extrae el resumen de un entry de feedparser.

    Busca en el campo summary primero, luego en content si existe.
    Limpia tags HTML basicos.

    Args:
        entry: Entrada parseada por feedparser.

    Returns:
        Resumen como string limpio, o cadena vacia si no hay resumen.
    """
    # Intentar con summary primero
    summary: str = getattr(entry, "summary", "") or ""

    # Si no hay summary, intentar con content
    if not summary:
        content_list = getattr(entry, "content", [])
        if content_list and len(content_list) > 0:
            summary = content_list[0].get("value", "")

    # Limpieza basica de HTML (sin dependencias externas)
    # Remover tags HTML comunes
    import re

    summary = re.sub(r"<[^>]+>", "", summary)
    # Limitar longitud a 500 caracteres
    if len(summary) > 500:
        summary = summary[:497] + "..."

    return summary.strip()


def fetch_rss_articles(feeds: list[dict]) -> list[Article]:
    """Recolecta articulos de una lista de RSS feeds.

    Descarga cada feed con requests y lo parsea con feedparser.
    Si un feed falla, se registra el error y se continua con los demas.

    Args:
        feeds: Lista de diccionarios con claves 'name' y 'url'.
               Ejemplo: [{'name': 'TechCrunch AI', 'url': 'https://...'}]

    Returns:
        Lista de Article con los articulos recolectados de todos los feeds.
    """
    articles: list[Article] = []

    for feed_info in feeds:
        feed_name: str = feed_info.get("name", "Unknown")
        feed_url: str = feed_info.get("url", "")

        if not feed_url:
            logger.warning(f"Feed '{feed_name}' no tiene URL, saltando")
            continue

        logger.info(f"Descargando feed RSS: {feed_name} ({feed_url})")

        try:
            # Descargar el contenido del feed con timeout
            response = requests.get(
                feed_url,
                timeout=HTTP_TIMEOUT,
                headers={
                    "User-Agent": "AINewsAgent/1.0 (Python; feedparser)"
                },
            )
            response.raise_for_status()

            # Parsear el contenido con feedparser
            parsed = feedparser.parse(response.content)

            if parsed.bozo and not parsed.entries:
                logger.warning(
                    f"Feed '{feed_name}' tiene errores de parseo y no tiene entries: "
                    f"{parsed.bozo_exception}"
                )
                continue

            feed_articles_count: int = 0

            for entry in parsed.entries:
                # Extraer titulo — campo obligatorio
                title: str = getattr(entry, "title", "") or ""
                if not title:
                    continue

                # Extraer link
                link: str = getattr(entry, "link", "") or ""
                if not link:
                    continue

                # Extraer fecha y resumen
                published_at: datetime = _parse_published_date(entry)

                # Filtrar articulos con mas de 48 horas de antiguedad
                now = datetime.now(tz=timezone.utc)
                if (now - published_at) > timedelta(hours=MAX_AGE_HOURS):
                    continue

                summary: str = _extract_summary(entry)

                article = Article(
                    title=title.strip(),
                    url=link.strip(),
                    source=feed_name,
                    published_at=published_at,
                    summary=summary,
                )
                articles.append(article)
                feed_articles_count += 1

            logger.info(
                f"Feed '{feed_name}': {feed_articles_count} articulos recolectados"
            )

        except requests.exceptions.Timeout:
            logger.error(
                f"Timeout al descargar feed '{feed_name}' ({feed_url})"
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error HTTP al descargar feed '{feed_name}': {e}"
            )
        except Exception as e:
            logger.error(
                f"Error inesperado procesando feed '{feed_name}': {e}"
            )

    logger.info(
        f"RSS total: {len(articles)} articulos recolectados de {len(feeds)} feeds"
    )
    return articles
