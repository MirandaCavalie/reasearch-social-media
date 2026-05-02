"""
Recolector de articulos desde Hacker News usando la Firebase API.

Obtiene los top stories, descarga cada item en paralelo con
ThreadPoolExecutor, y filtra por keywords relevantes de AI/tech.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from sources.models import Article

# Configuracion del logger con formato estandar del proyecto
logger = logging.getLogger(__name__)

# URL base de la API de Hacker News (Firebase)
HN_BASE_URL: str = "https://hacker-news.firebaseio.com/v0"

# Timeout global para peticiones HTTP en segundos
HTTP_TIMEOUT: int = 30

# Numero maximo de workers para descargas paralelas
MAX_WORKERS: int = 10


def _fetch_item(item_id: int) -> Optional[dict[str, Any]]:
    """Descarga un item individual de Hacker News por su ID.

    Args:
        item_id: ID numerico del item en HN.

    Returns:
        Diccionario con los datos del item, o None si falla la descarga.
    """
    url = f"{HN_BASE_URL}/item/{item_id}.json"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout al descargar item HN {item_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error descargando item HN {item_id}: {e}")
        return None


def _matches_keywords(title: str, keywords: list[str]) -> bool:
    """Verifica si un titulo contiene alguna de las keywords (case-insensitive).

    Args:
        title: Titulo del articulo a verificar.
        keywords: Lista de palabras clave a buscar.

    Returns:
        True si el titulo contiene al menos una keyword.
    """
    title_lower: str = title.lower()
    return any(keyword.lower() in title_lower for keyword in keywords)


def fetch_hackernews_articles(config: dict) -> list[Article]:
    """Recolecta articulos de Hacker News filtrados por keywords.

    Descarga los top stories, obtiene los detalles de cada uno en paralelo
    usando ThreadPoolExecutor, y filtra por keywords configuradas.

    Args:
        config: Diccionario de configuracion con las claves:
            - top_n (int): Cantidad de top stories a considerar (default: 30).
            - keywords (list[str]): Lista de palabras clave para filtrar.

    Returns:
        Lista de Article con los articulos que matchean las keywords.
    """
    top_n: int = config.get("top_n", 30)
    keywords: list[str] = config.get("keywords", [])

    if not keywords:
        logger.warning(
            "No hay keywords configuradas para Hacker News, "
            "usando keywords por defecto"
        )
        keywords = [
            "AI", "LLM", "GPT", "Claude", "machine learning",
            "neural", "startup", "YC", "funding", "launch",
        ]

    logger.info(
        f"Descargando top {top_n} stories de Hacker News "
        f"(filtro: {len(keywords)} keywords)"
    )

    # Paso 1: Obtener la lista de IDs de top stories
    try:
        response = requests.get(
            f"{HN_BASE_URL}/topstories.json", timeout=HTTP_TIMEOUT
        )
        response.raise_for_status()
        all_story_ids: list[int] = response.json()
    except requests.exceptions.Timeout:
        logger.error("Timeout al obtener top stories de Hacker News")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error obteniendo top stories de HN: {e}")
        return []

    # Tomar solo los primeros top_n IDs
    story_ids: list[int] = all_story_ids[:top_n]
    logger.info(f"Obtenidos {len(story_ids)} IDs de top stories")

    # Paso 2: Descargar detalles de cada story en paralelo
    items: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Crear un future por cada story ID
        future_to_id = {
            executor.submit(_fetch_item, sid): sid for sid in story_ids
        }

        for future in as_completed(future_to_id):
            story_id = future_to_id[future]
            try:
                item = future.result()
                if item is not None:
                    items.append(item)
            except Exception as e:
                logger.warning(
                    f"Error procesando future para story {story_id}: {e}"
                )

    logger.info(f"Descargados {len(items)} items de Hacker News")

    # Paso 3: Filtrar por keywords y crear Articles
    articles: list[Article] = []
    for item in items:
        title: str = item.get("title", "")
        if not title:
            continue

        # Filtrar: solo articulos que matcheen las keywords
        if not _matches_keywords(title, keywords):
            continue

        # Extraer URL — algunos posts de HN no tienen url externa
        url: str = item.get("url", "")
        if not url:
            # Usar el link al post en HN como fallback
            item_id = item.get("id", "")
            url = f"https://news.ycombinator.com/item?id={item_id}"

        # Convertir timestamp Unix a datetime
        timestamp: int = item.get("time", 0)
        if timestamp:
            published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            published_at = datetime.now(tz=timezone.utc)

        # Score y comentarios como engagement
        score: int = item.get("score", 0)
        num_comments: int = len(item.get("kids", []))

        # Crear el resumen con score y comentarios
        summary = f"HN Score: {score} | Comentarios: {num_comments}"
        if item.get("text"):
            # Algunos posts de tipo "Ask HN" tienen texto
            text = item["text"][:300]
            summary = f"{summary} | {text}"

        article = Article(
            title=title.strip(),
            url=url,
            source="Hacker News",
            published_at=published_at,
            summary=summary,
            engagement=score,
        )
        articles.append(article)

    logger.info(
        f"Hacker News: {len(articles)} articulos despues de filtrar "
        f"por keywords (de {len(items)} descargados)"
    )
    return articles
