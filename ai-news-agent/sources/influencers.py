"""
Tracker de contenido de influencers de AI/tech.

Monitorea RSS feeds de blogs y canales de YouTube de influencers top,
y opcionalmente sus cuentas de X/Twitter via Apify, para detectar
temas y formatos que se pueden adaptar para audiencia latina en TikTok.
"""

import logging
import os
import re
from datetime import datetime, timezone
from time import mktime

import feedparser
import requests

from sources.models import ContentSignal

logger = logging.getLogger("sources.influencers")

HTTP_TIMEOUT: int = 30


def _detect_format(title: str) -> str:
    """Detecta el formato de contenido basado en el titulo.

    Args:
        title: Titulo del contenido.

    Returns:
        Formato detectado: tutorial, comparison, listicle, hot_take, o news.
    """
    title_lower = title.lower()

    if any(kw in title_lower for kw in ["tutorial", "how to", "guide", "learn", "step by step", "curso"]):
        return "tutorial"
    if any(kw in title_lower for kw in ["vs", "versus", "comparison", "compared", "better"]):
        return "comparison"
    if any(kw in title_lower for kw in ["top", "best", "list", "ranking", "tools", "must have"]):
        return "listicle"
    if any(kw in title_lower for kw in ["opinion", "think", "wrong", "hot take", "unpopular", "overrated"]):
        return "hot_take"

    return "news"


def _parse_date(entry: feedparser.FeedParserDict) -> datetime:
    """Extrae fecha de publicacion de un entry de feedparser."""
    time_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if time_struct:
        try:
            return datetime.fromtimestamp(mktime(time_struct), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    return datetime.now(tz=timezone.utc)


def _fetch_rss_signals(rss_feeds: list[dict]) -> list[ContentSignal]:
    """Recolecta content signals desde RSS feeds de influencers.

    Args:
        rss_feeds: Lista de dicts con name, url, platform.

    Returns:
        Lista de ContentSignal de feeds RSS.
    """
    signals: list[ContentSignal] = []

    for feed_info in rss_feeds:
        name = feed_info.get("name", "Unknown")
        url = feed_info.get("url", "")
        platform = feed_info.get("platform", "blog")

        if not url:
            continue

        logger.info(f"Fetching influencer feed: {name} ({platform})")

        try:
            response = requests.get(
                url,
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": "AINewsAgent/1.0 (influencer tracker)"},
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            # Tomar las ultimas 5 entradas del feed
            for entry in feed.entries[:5]:
                title = getattr(entry, "title", "") or ""
                if not title:
                    continue

                link = getattr(entry, "link", "") or ""
                published_at = _parse_date(entry)

                # Extraer resumen para el hook
                summary = getattr(entry, "summary", "") or ""
                summary_clean = re.sub(r"<[^>]+>", "", summary)[:100]

                signal = ContentSignal(
                    influencer=name,
                    platform=platform,
                    topic=title,
                    format=_detect_format(title),
                    hook=title[:100],
                    engagement=0,  # No disponible via RSS
                    url=link,
                    detected_at=published_at,
                )
                signals.append(signal)

            logger.info(f"Influencer {name}: {min(5, len(feed.entries))} signals recolectados")

        except requests.RequestException as e:
            logger.warning(f"Error fetching influencer {name}: {e}")
        except Exception as e:
            logger.error(f"Error procesando influencer {name}: {e}")

    return signals


def _fetch_twitter_signals(handles: list[str]) -> list[ContentSignal]:
    """Recolecta content signals de influencers en X/Twitter via Apify.

    Solo funciona si APIFY_TOKEN esta configurado. Si no, retorna lista vacia.

    Args:
        handles: Lista de handles de Twitter (ej: ["@sama", "@ylecun"]).

    Returns:
        Lista de ContentSignal de Twitter.
    """
    token = os.getenv("APIFY_TOKEN", "")
    if not token:
        logger.info("APIFY_TOKEN no configurado, saltando influencers de X/Twitter")
        return []

    signals: list[ContentSignal] = []

    for handle in handles:
        clean_handle = handle.lstrip("@")
        logger.info(f"Buscando tweets de influencer: @{clean_handle}")

        try:
            run_url = f"https://api.apify.com/v2/acts/apidojo~tweet-scraper/runs?token={token}"
            payload = {
                "searchTerms": [f"from:{clean_handle}"],
                "maxTweets": 5,
                "searchMode": "live",
            }

            response = requests.post(run_url, json=payload, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            run_data = response.json()
            run_id = run_data.get("data", {}).get("id", "")

            if not run_id:
                continue

            # Esperar brevemente a que termine
            import time
            time.sleep(10)

            dataset_url = (
                f"https://api.apify.com/v2/actor-runs/{run_id}"
                f"/dataset/items?token={token}"
            )
            dataset_response = requests.get(dataset_url, timeout=HTTP_TIMEOUT)
            dataset_response.raise_for_status()
            items = dataset_response.json()

            for item in items[:3]:
                text = item.get("full_text", "") or item.get("text", "")
                if not text:
                    continue

                retweets = item.get("retweet_count", 0) or 0
                favorites = item.get("favorite_count", 0) or 0

                signal = ContentSignal(
                    influencer=f"@{clean_handle}",
                    platform="x",
                    topic=text[:200],
                    format=_detect_format(text),
                    hook=text[:100],
                    engagement=retweets + favorites,
                    url=f"https://x.com/{clean_handle}",
                    detected_at=datetime.now(tz=timezone.utc),
                )
                signals.append(signal)

        except Exception as e:
            logger.warning(f"Error buscando tweets de @{clean_handle}: {e}")

    logger.info(f"X/Twitter influencers: {len(signals)} signals recolectados")
    return signals


def fetch_influencer_signals(config: dict) -> list[ContentSignal]:
    """Recolecta content signals de influencers de AI/tech.

    Combina feeds RSS de blogs/YouTube con datos de X/Twitter (si hay token).

    Args:
        config: Diccionario con 'rss_feeds' y 'twitter_handles'.

    Returns:
        Lista combinada de ContentSignal de todas las plataformas.
    """
    rss_feeds = config.get("rss_feeds", [])
    twitter_handles = config.get("twitter_handles", [])

    logger.info(
        f"Iniciando tracker de influencers: {len(rss_feeds)} feeds RSS, "
        f"{len(twitter_handles)} handles de Twitter"
    )

    # Recolectar de ambas fuentes
    rss_signals = _fetch_rss_signals(rss_feeds)
    twitter_signals = _fetch_twitter_signals(twitter_handles)

    all_signals = rss_signals + twitter_signals

    logger.info(
        f"Influencer tracker completo: {len(all_signals)} signals totales "
        f"({len(rss_signals)} RSS + {len(twitter_signals)} Twitter)"
    )
    return all_signals
