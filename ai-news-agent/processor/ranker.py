"""
Modulo de ranking de articulos por score combinado.

Combina tres senales para determinar la relevancia final de cada articulo:
- trending_score (40%): basado en recencia, engagement y keywords de alto valor
- virality_score (40%): potencial viral para audiencia latina (calculado en virality.py)
- influencer_signal (20%): si un influencer top ya cubrio el tema en ingles
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any

from sources.models import Article, ContentSignal

# Configuracion del logger con formato: [TIMESTAMP] [LEVEL] [MODULE] mensaje
logger = logging.getLogger("processor.ranker")


def _calculate_trending_score(
    article: Article,
    ranking_config: dict[str, Any],
) -> float:
    """
    Calcula el trending score de un articulo individual.

    Factores considerados:
    - Base score: 10
    - Bonus de recencia: si fue publicado dentro de las ultimas N horas
    - Bonus de menciones cruzadas: por cada mencion cruzada detectada
    - Bonus de engagement: basado en log10 del engagement (ej: HN score)
    - Keywords de alto valor: multiplicador si el titulo contiene keywords clave

    Args:
        article: El articulo a evaluar.
        ranking_config: Configuracion de ranking desde config.yaml.

    Returns:
        El trending score calculado.
    """
    score: float = 10.0  # Score base

    # --- Bonus de recencia ---
    recency_hours: int = ranking_config.get("recency_bonus_hours", 6)
    recency_multiplier: float = ranking_config.get("recency_multiplier", 2.0)

    ahora: datetime = datetime.now(timezone.utc)

    # Asegurar que published_at tenga timezone para comparacion
    published: datetime = article.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)

    horas_desde_publicacion: float = (
        (ahora - published).total_seconds() / 3600.0
    )

    if horas_desde_publicacion <= recency_hours:
        score *= recency_multiplier
        logger.debug(
            f"Bonus de recencia para '{article.title}': "
            f"publicado hace {horas_desde_publicacion:.1f}h "
            f"(multiplicador x{recency_multiplier})"
        )

    # --- Bonus de menciones cruzadas ---
    cross_mention_bonus: float = ranking_config.get("cross_mention_bonus", 1.5)
    # Limitar a maximo 3 menciones cruzadas para evitar inflacion
    menciones_cap: int = min(article.cross_mentions, 3)

    if menciones_cap > 0:
        score *= cross_mention_bonus ** menciones_cap
        logger.debug(
            f"Bonus de menciones cruzadas para '{article.title}': "
            f"{menciones_cap} menciones (multiplicador x{cross_mention_bonus ** menciones_cap:.2f})"
        )

    # --- Bonus de engagement ---
    hn_threshold: int = ranking_config.get("hn_score_threshold", 100)

    if article.engagement > hn_threshold:
        engagement_bonus: float = math.log10(article.engagement) * 5
        score += engagement_bonus
        logger.debug(
            f"Bonus de engagement para '{article.title}': "
            f"engagement={article.engagement}, bonus={engagement_bonus:.2f}"
        )

    # --- Keywords de alto valor ---
    high_value_keywords: list[str] = ranking_config.get("high_value_keywords", [])
    high_value_multiplier: float = ranking_config.get("high_value_multiplier", 1.3)
    title_lower: str = article.title.lower()

    for keyword in high_value_keywords:
        if keyword.lower() in title_lower:
            score *= high_value_multiplier
            logger.debug(
                f"Keyword de alto valor '{keyword}' en '{article.title}' "
                f"(multiplicador x{high_value_multiplier})"
            )
            break  # Solo aplicar una vez el multiplicador

    return score


def _calculate_influencer_signal(
    article: Article,
    signals: list[ContentSignal],
) -> float:
    """
    Calcula la senal de influencer para un articulo.

    Verifica si algun influencer ya cubrio un tema relacionado al articulo.
    La deteccion se hace por overlap de palabras entre el topic del signal
    y el titulo del articulo.

    Args:
        article: El articulo a evaluar.
        signals: Lista de ContentSignals de influencers.

    Returns:
        1.0 si hay match con algun influencer, 0.0 en caso contrario.
    """
    if not signals:
        return 0.0

    title_words: set[str] = set(article.title.lower().split())

    for signal in signals:
        # Extraer palabras del topic del influencer
        topic_words: set[str] = set(signal.topic.lower().split())

        # Verificar si hay overlap significativo (al menos una palabra en comun)
        overlap: set[str] = title_words & topic_words

        # Filtrar palabras muy cortas (menos de 3 caracteres) para evitar
        # falsos positivos con articulos, preposiciones, etc.
        meaningful_overlap: set[str] = {
            word for word in overlap if len(word) >= 3
        }

        if meaningful_overlap:
            logger.debug(
                f"Influencer signal detectado: '{signal.influencer}' "
                f"cubrio '{signal.topic}' que hace match con "
                f"'{article.title}' (overlap: {meaningful_overlap})"
            )
            return 1.0

    return 0.0


def rank_articles(
    articles: list[Article],
    signals: list[ContentSignal],
    ranking_config: dict[str, Any],
) -> list[Article]:
    """
    Rankea articulos por score combinado de trending, viralidad e influencer signal.

    El score combinado se calcula como:
        combined = trending * w_trending + virality * w_virality + influencer * 100 * w_influencer

    Los pesos por defecto son: trending=0.4, virality=0.4, influencer=0.2

    Args:
        articles: Lista de articulos (ya deben tener virality_score calculado).
        signals: Lista de ContentSignals de influencers para detectar cobertura.
        ranking_config: Configuracion de ranking desde config.yaml, incluyendo
                        pesos, parametros de recencia, engagement, etc.

    Returns:
        Lista de los top_n articulos ordenados por score combinado descendente.
    """
    logger.info(
        f"Iniciando ranking de {len(articles)} articulos "
        f"con {len(signals)} signals de influencers"
    )

    # Obtener pesos de la configuracion
    weights: dict[str, float] = ranking_config.get("weights", {})
    weight_trending: float = weights.get("trending", 0.4)
    weight_virality: float = weights.get("virality", 0.4)
    weight_influencer: float = weights.get("influencer_signal", 0.2)
    top_n: int = ranking_config.get("top_n", 10)

    # Calcular scores para cada articulo
    ranking_results: list[tuple[Article, float]] = []

    for article in articles:
        # Paso 1: Calcular trending_score
        trending: float = _calculate_trending_score(article, ranking_config)
        article.trending_score = trending

        # Paso 2: Calcular influencer signal
        influencer_signal: float = _calculate_influencer_signal(
            article, signals
        )

        # Paso 3: Score combinado
        combined_score: float = (
            trending * weight_trending
            + article.virality_score * weight_virality
            + influencer_signal * 100 * weight_influencer
        )

        ranking_results.append((article, combined_score))

        logger.debug(
            f"Ranking '{article.title}': "
            f"trending={trending:.2f} (x{weight_trending}), "
            f"virality={article.virality_score:.1f} (x{weight_virality}), "
            f"influencer={influencer_signal:.1f} (x{weight_influencer}) "
            f"-> combined={combined_score:.2f}"
        )

    # Ordenar por score combinado descendente
    ranking_results.sort(key=lambda x: x[1], reverse=True)

    # Tomar los top_n
    top_articles: list[Article] = [
        article for article, _ in ranking_results[:top_n]
    ]

    # Logear resultados del ranking
    logger.info(f"Top {len(top_articles)} articulos rankeados:")
    for i, (article, score) in enumerate(ranking_results[:top_n], 1):
        logger.info(
            f"  #{i}: [{score:.2f}] {article.title} "
            f"(trending={article.trending_score:.1f}, "
            f"virality={article.virality_score:.1f}, "
            f"fuente={article.source})"
        )

    return top_articles
