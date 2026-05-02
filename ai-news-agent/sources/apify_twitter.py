"""
Recolector de tweets desde X/Twitter usando Apify como scraper.

Este modulo es OPCIONAL: solo funciona si la variable de entorno
APIFY_TOKEN esta configurada. Si no hay token o si Apify falla,
retorna una lista vacia sin crashear — las demas fuentes continuan.
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests

from sources.models import Article

# Configuracion del logger con formato estandar del proyecto
logger = logging.getLogger(__name__)

# Timeout global para peticiones HTTP en segundos
HTTP_TIMEOUT: int = 30

# Tiempo maximo de espera para que termine un run de Apify (en segundos)
APIFY_MAX_WAIT: int = 60

# Intervalo de polling para verificar el estado del run de Apify
APIFY_POLL_INTERVAL: int = 5

# URL base de la API de Apify v2
APIFY_BASE_URL: str = "https://api.apify.com/v2"

# Actor de Apify para scraping de tweets
APIFY_ACTOR_ID: str = "apidojo~tweet-scraper"


def _get_apify_token() -> str | None:
    """Obtiene el token de Apify desde las variables de entorno.

    Returns:
        Token de Apify como string, o None si no esta configurado.
    """
    token: str | None = os.getenv("APIFY_TOKEN")
    if not token:
        return None
    return token.strip()


def _start_actor_run(
    token: str, search_terms: list[str], max_tweets: int
) -> str | None:
    """Inicia un run del actor de scraping de tweets en Apify.

    Envia una peticion POST para ejecutar el actor con los terminos de
    busqueda especificados.

    Args:
        token: Token de autenticacion de Apify.
        search_terms: Lista de terminos a buscar en Twitter.
        max_tweets: Numero maximo de tweets a recolectar.

    Returns:
        ID del run iniciado, o None si fallo.
    """
    url: str = f"{APIFY_BASE_URL}/acts/{APIFY_ACTOR_ID}/runs"
    params: dict = {"token": token}

    # Cuerpo de la peticion con los parametros del actor
    body: dict = {
        "searchTerms": search_terms,
        "maxTweets": max_tweets,
        "searchMode": "live",
    }

    logger.info(
        f"Iniciando actor de Apify con terminos: {search_terms}, max_tweets={max_tweets}"
    )

    try:
        response = requests.post(
            url,
            params=params,
            json=body,
            timeout=HTTP_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        data: dict = response.json()
        run_id: str = data.get("data", {}).get("id", "")

        if not run_id:
            logger.error("Apify no retorno un run ID valido")
            return None

        logger.info(f"Actor de Apify iniciado con run ID: {run_id}")
        return run_id

    except requests.exceptions.Timeout:
        logger.error(f"Timeout al iniciar actor de Apify ({HTTP_TIMEOUT}s)")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error HTTP al iniciar actor de Apify: {e}")
    except Exception as e:
        logger.error(f"Error inesperado al iniciar actor de Apify: {e}")

    return None


def _wait_for_run(token: str, run_id: str) -> bool:
    """Espera a que un run de Apify termine.

    Hace polling del estado del run cada APIFY_POLL_INTERVAL segundos,
    hasta un maximo de APIFY_MAX_WAIT segundos.

    Args:
        token: Token de autenticacion de Apify.
        run_id: ID del run a monitorear.

    Returns:
        True si el run termino exitosamente (SUCCEEDED), False en caso contrario.
    """
    url: str = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
    params: dict = {"token": token}

    elapsed: float = 0.0
    # Estados terminales de Apify
    terminal_states: set[str] = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}

    logger.info(f"Esperando a que termine el run de Apify {run_id}...")

    while elapsed < APIFY_MAX_WAIT:
        try:
            response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
            response.raise_for_status()

            data: dict = response.json()
            status: str = data.get("data", {}).get("status", "UNKNOWN")

            if status == "SUCCEEDED":
                logger.info(f"Run de Apify {run_id} completado exitosamente")
                return True

            if status in terminal_states:
                logger.warning(f"Run de Apify {run_id} termino con estado: {status}")
                return False

            # El run sigue en progreso — esperar antes de volver a consultar
            logger.debug(
                f"Run de Apify {run_id} en estado '{status}', esperando {APIFY_POLL_INTERVAL}s..."
            )

        except requests.exceptions.RequestException as e:
            logger.warning(f"Error consultando estado del run de Apify: {e}")

        time.sleep(APIFY_POLL_INTERVAL)
        elapsed += APIFY_POLL_INTERVAL

    logger.warning(
        f"Timeout esperando run de Apify {run_id} ({APIFY_MAX_WAIT}s transcurridos)"
    )
    return False


def _fetch_run_results(token: str, run_id: str) -> list[dict]:
    """Obtiene los resultados (items del dataset) de un run completado de Apify.

    Args:
        token: Token de autenticacion de Apify.
        run_id: ID del run completado.

    Returns:
        Lista de diccionarios con los datos de cada tweet.
    """
    url: str = f"{APIFY_BASE_URL}/actor-runs/{run_id}/dataset/items"
    params: dict = {"token": token}

    try:
        response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()

        items: list[dict] = response.json()
        logger.info(f"Apify retorno {len(items)} items del dataset")
        return items

    except requests.exceptions.Timeout:
        logger.error(f"Timeout al obtener resultados de Apify ({HTTP_TIMEOUT}s)")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error HTTP al obtener resultados de Apify: {e}")
    except Exception as e:
        logger.error(f"Error inesperado al obtener resultados de Apify: {e}")

    return []


def _parse_tweet_date(date_str: str) -> datetime:
    """Parsea la fecha de un tweet a datetime.

    Twitter usa varios formatos de fecha. Intentamos los mas comunes.

    Args:
        date_str: Fecha del tweet como string.

    Returns:
        Datetime con timezone UTC. Si falla, retorna datetime.now(UTC).
    """
    if not date_str:
        return datetime.now(tz=timezone.utc)

    # Formatos comunes de fecha en Twitter/Apify
    formats: list[str] = [
        "%a %b %d %H:%M:%S %z %Y",  # "Wed Oct 10 20:19:24 +0000 2018"
        "%Y-%m-%dT%H:%M:%S.%fZ",     # ISO 8601 con milisegundos
        "%Y-%m-%dT%H:%M:%SZ",         # ISO 8601 sin milisegundos
        "%Y-%m-%d %H:%M:%S",          # Formato simple
    ]

    for fmt in formats:
        try:
            parsed: datetime = datetime.strptime(date_str, fmt)
            # Asegurar que tiene timezone UTC
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue

    # Fallback: intentar con fromisoformat
    try:
        clean_date: str = date_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean_date)
    except (ValueError, TypeError):
        pass

    logger.warning(f"No se pudo parsear fecha de tweet: '{date_str}'")
    return datetime.now(tz=timezone.utc)


def _tweet_to_article(tweet: dict) -> Article | None:
    """Convierte un diccionario de tweet de Apify a un Article.

    Args:
        tweet: Diccionario con los datos del tweet retornados por Apify.

    Returns:
        Article si se pudo convertir, None si faltan datos esenciales.
    """
    # Extraer texto del tweet (varios campos posibles segun el actor)
    text: str = (
        tweet.get("full_text", "")
        or tweet.get("text", "")
        or tweet.get("tweet_text", "")
        or ""
    )

    if not text:
        return None

    # Extraer nombre de usuario
    user: str = (
        tweet.get("user", {}).get("screen_name", "")
        if isinstance(tweet.get("user"), dict)
        else tweet.get("screen_name", "")
        or tweet.get("username", "")
        or "unknown"
    )

    # Calcular engagement total (retweets + likes)
    retweet_count: int = int(tweet.get("retweet_count", 0) or 0)
    favorite_count: int = int(tweet.get("favorite_count", 0) or 0)
    engagement: int = retweet_count + favorite_count

    # Extraer fecha de creacion
    date_str: str = tweet.get("created_at", "") or tweet.get("date", "") or ""
    published_at: datetime = _parse_tweet_date(date_str)

    # Construir URL del tweet si hay ID
    tweet_id: str = str(tweet.get("id_str", "") or tweet.get("id", "") or "")
    url: str = ""
    if tweet_id and user:
        url = f"https://x.com/{user}/status/{tweet_id}"

    # Usar el texto como titulo (truncado) y como resumen (completo)
    title: str = text[:120] + "..." if len(text) > 120 else text

    return Article(
        title=title,
        url=url,
        source="X/Twitter",
        published_at=published_at,
        summary=f"@{user}: {text}",
        engagement=engagement,
    )


def fetch_twitter_articles(config: dict) -> list[Article]:
    """Recolecta tweets desde X/Twitter usando Apify como scraper.

    Este modulo es completamente opcional. Si no hay token de Apify
    configurado, o si cualquier paso falla, retorna una lista vacia
    sin afectar al resto del pipeline.

    Args:
        config: Diccionario de configuracion con claves:
            - 'search_terms': Lista de terminos de busqueda
              (ej: ["AI news", "LLM release", "startup funding"])
            - 'max_tweets': Numero maximo de tweets por busqueda (default: 50)

    Returns:
        Lista de Article con los tweets recolectados, o lista vacia si falla.
    """
    # Verificar que existe el token de Apify
    token: str | None = _get_apify_token()
    if not token:
        logger.warning(
            "APIFY_TOKEN no esta configurado. "
            "Saltando recoleccion de X/Twitter. "
            "Configura APIFY_TOKEN en .env para habilitar esta fuente."
        )
        return []

    # Extraer parametros de configuracion
    search_terms: list[str] = config.get(
        "search_terms", ["AI news", "LLM release", "startup funding", "tech launch"]
    )
    max_tweets: int = config.get("max_tweets", 50)

    articles: list[Article] = []

    try:
        # Paso 1: Iniciar el actor de Apify
        run_id: str | None = _start_actor_run(token, search_terms, max_tweets)
        if not run_id:
            logger.warning("No se pudo iniciar el actor de Apify, saltando X/Twitter")
            return []

        # Paso 2: Esperar a que termine el run
        success: bool = _wait_for_run(token, run_id)
        if not success:
            logger.warning(
                f"El run de Apify {run_id} no termino exitosamente, saltando X/Twitter"
            )
            return []

        # Paso 3: Obtener los resultados del dataset
        raw_tweets: list[dict] = _fetch_run_results(token, run_id)
        if not raw_tweets:
            logger.warning("Apify no retorno tweets")
            return []

        # Paso 4: Convertir cada tweet a Article
        for tweet in raw_tweets:
            article: Article | None = _tweet_to_article(tweet)
            if article:
                articles.append(article)

        logger.info(
            f"X/Twitter: {len(articles)} tweets convertidos a articles "
            f"de {len(raw_tweets)} tweets crudos"
        )

    except Exception as e:
        # Captura general — NUNCA debe crashear el pipeline por Apify
        logger.error(
            f"Error inesperado en recoleccion de X/Twitter: {e}. "
            f"Continuando con las demas fuentes."
        )
        return []

    return articles
