"""
Modulo estimador de viralidad para audiencia latina en TikTok.

Calcula un virality_score (0-100) para cada articulo basado en
factores positivos y negativos configurables desde config.yaml.

El score estima el potencial viral ESPECIFICAMENTE para audiencia
latina/hispana en TikTok.
"""

import logging
import string
from typing import Any

from sources.models import Article

# Configuracion del logger con formato: [TIMESTAMP] [LEVEL] [MODULE] mensaje
logger = logging.getLogger("processor.virality")

# Stopwords reutilizadas para normalizacion de titulos (consistente con dedup.py)
STOPWORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "with", "by", "from", "this", "that",
    "it", "its", "has", "have", "had", "been", "be", "will", "would", "could",
    "should", "may", "might", "can", "do", "does", "did", "not", "no",
}


def _normalize_title_for_comparison(title: str) -> set[str]:
    """
    Normaliza un titulo para comparacion de menciones cruzadas.

    Args:
        title: Titulo original del articulo.

    Returns:
        Set de palabras normalizadas sin stopwords ni puntuacion.
    """
    title_lower: str = title.lower()
    title_clean: str = title_lower.translate(
        str.maketrans("", "", string.punctuation)
    )
    words: list[str] = title_clean.split()
    return {word for word in words if word not in STOPWORDS}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """
    Calcula la similitud de Jaccard entre dos conjuntos.

    Args:
        set_a: Primer conjunto de palabras.
        set_b: Segundo conjunto de palabras.

    Returns:
        Float entre 0.0 y 1.0 representando la similitud.
    """
    if not set_a and not set_b:
        return 0.0

    union: set[str] = set_a | set_b
    if not union:
        return 0.0

    intersection: set[str] = set_a & set_b
    return len(intersection) / len(union)


def _text_contains_keyword(text: str, keyword: str) -> bool:
    """
    Verifica si un texto contiene una keyword (busqueda case-insensitive).

    Args:
        text: Texto donde buscar.
        keyword: Keyword a buscar.

    Returns:
        True si la keyword esta presente en el texto.
    """
    return keyword.lower() in text.lower()


def calculate_virality_score(
    article: Article,
    virality_config: dict[str, Any],
    cross_mention_count: int = 0,
) -> tuple[float, list[str]]:
    """
    Calcula el virality score para un articulo individual.

    El score empieza en 30 (base) y se modifica segun factores positivos
    y negativos definidos en la configuracion.

    Factores positivos suman puntos (ej: controversial +15, relatable +20).
    Factores negativos restan puntos (ej: too_technical -15).
    Menciones cruzadas (>= 2 fuentes) agregan bonus de trending_english.

    Args:
        article: El articulo a evaluar.
        virality_config: Configuracion de viralidad desde config.yaml
                         con positive_factors y negative_factors.
        cross_mention_count: Cuantos otros articulos tienen un titulo similar
                             (indica que el tema esta trending en ingles).

    Returns:
        Tupla de (score, lista_de_factores) donde score esta entre 0 y 100.
    """
    score: float = 30.0  # Score base
    factors: list[str] = []

    # Texto combinado para busqueda de keywords
    search_text: str = f"{article.title} {article.summary}"

    # --- Evaluar factores positivos ---
    positive_factors: dict[str, Any] = virality_config.get("positive_factors", {})

    for factor_name, factor_config in positive_factors.items():
        # El factor trending_english se maneja aparte (por menciones cruzadas)
        if factor_name == "trending_english":
            continue

        keywords: list[str] = factor_config.get("keywords", [])
        factor_score: int = factor_config.get("score", 0)

        # Verificar si alguna keyword del factor aparece en el texto
        for keyword in keywords:
            if _text_contains_keyword(search_text, keyword):
                score += factor_score
                factors.append(f"{factor_name} (+{factor_score})")
                logger.debug(
                    f"Factor positivo '{factor_name}' detectado en "
                    f"'{article.title}' por keyword '{keyword}'"
                )
                break  # Solo contar una vez por factor

    # --- Factor especial: trending_english (por menciones cruzadas) ---
    if cross_mention_count >= 2:
        trending_config: dict[str, Any] = positive_factors.get(
            "trending_english", {}
        )
        trending_score: int = trending_config.get("score", 25)
        score += trending_score
        factors.append(
            f"trending_english (+{trending_score}, "
            f"{cross_mention_count} menciones cruzadas)"
        )
        logger.debug(
            f"Trending en ingles detectado para '{article.title}' "
            f"con {cross_mention_count} menciones cruzadas"
        )

    # --- Evaluar factores negativos ---
    negative_factors: dict[str, Any] = virality_config.get("negative_factors", {})

    for factor_name, factor_config in negative_factors.items():
        keywords = factor_config.get("keywords", [])
        factor_score = factor_config.get("score", 0)  # Ya viene negativo desde config

        for keyword in keywords:
            if _text_contains_keyword(search_text, keyword):
                # factor_score ya es negativo en la config (ej: -15)
                score += factor_score
                factors.append(f"{factor_name} ({factor_score})")
                logger.debug(
                    f"Factor negativo '{factor_name}' detectado en "
                    f"'{article.title}' por keyword '{keyword}'"
                )
                break  # Solo contar una vez por factor

    # --- Clampar score entre 0 y 100 ---
    score = max(0.0, min(100.0, score))

    logger.debug(
        f"Virality score para '{article.title}': {score:.1f} "
        f"con factores: {factors}"
    )

    return score, factors


def score_all_articles(
    articles: list[Article],
    virality_config: dict[str, Any],
) -> list[Article]:
    """
    Calcula el virality score para todos los articulos.

    Primero cuenta las menciones cruzadas entre articulos
    (usando similitud de Jaccard > 0.4 en titulos normalizados),
    luego calcula el virality score para cada uno.

    Las menciones cruzadas indican que un tema esta siendo cubierto
    por multiples fuentes, lo cual sugiere que es trending en ingles.

    Args:
        articles: Lista de articulos a evaluar.
        virality_config: Configuracion de viralidad desde config.yaml.

    Returns:
        La misma lista de articulos con virality_score y virality_factors actualizados.
    """
    logger.info(f"Calculando virality scores para {len(articles)} articulos")

    # --- Paso 1: Contar menciones cruzadas ---
    # Pre-calcular titulos normalizados
    normalized_titles: list[set[str]] = [
        _normalize_title_for_comparison(art.title) for art in articles
    ]

    # Para cada articulo, contar cuantos otros tienen titulo similar
    cross_mention_counts: list[int] = []
    umbral_cross_mention: float = 0.4

    for i in range(len(articles)):
        count: int = 0
        for j in range(len(articles)):
            if i == j:
                continue
            similitud: float = _jaccard_similarity(
                normalized_titles[i], normalized_titles[j]
            )
            if similitud > umbral_cross_mention:
                count += 1
        cross_mention_counts.append(count)

        # Actualizar el campo cross_mentions del articulo
        articles[i].cross_mentions = count

    # --- Paso 2: Calcular virality score para cada articulo ---
    for i, article in enumerate(articles):
        score, factors = calculate_virality_score(
            article=article,
            virality_config=virality_config,
            cross_mention_count=cross_mention_counts[i],
        )
        article.virality_score = score
        article.virality_factors = factors

    # Resumen de resultados
    scores: list[float] = [art.virality_score for art in articles]
    if scores:
        promedio: float = sum(scores) / len(scores)
        maximo: float = max(scores)
        minimo: float = min(scores)
        logger.info(
            f"Virality scores calculados: promedio={promedio:.1f}, "
            f"min={minimo:.1f}, max={maximo:.1f}"
        )
    else:
        logger.info("No hay articulos para calcular virality scores")

    return articles
