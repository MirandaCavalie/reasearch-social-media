"""
Modulo de deduplicacion de articulos.

Elimina articulos duplicados usando dos estrategias:
1. Deduplicacion por URL exacta
2. Deduplicacion por similitud de titulos (Jaccard similarity)
"""

import logging
import string
from typing import Optional

from sources.models import Article

# Configuracion del logger con formato: [TIMESTAMP] [LEVEL] [MODULE] mensaje
logger = logging.getLogger("processor.dedup")

# Stopwords en ingles para normalizar titulos
STOPWORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "with", "by", "from", "this", "that",
    "it", "its", "has", "have", "had", "been", "be", "will", "would", "could",
    "should", "may", "might", "can", "do", "does", "did", "not", "no",
}


def normalize_title(title: str) -> set[str]:
    """
    Normaliza un titulo para comparacion.

    Pasos:
    - Convierte a minusculas
    - Remueve signos de puntuacion
    - Divide en palabras
    - Remueve stopwords en ingles

    Args:
        title: El titulo original del articulo.

    Returns:
        Un set de palabras normalizadas (sin stopwords ni puntuacion).
    """
    # Convertir a minusculas
    title_lower: str = title.lower()

    # Remover signos de puntuacion
    title_clean: str = title_lower.translate(
        str.maketrans("", "", string.punctuation)
    )

    # Dividir en palabras y remover stopwords
    words: list[str] = title_clean.split()
    filtered_words: set[str] = {word for word in words if word not in STOPWORDS}

    return filtered_words


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """
    Calcula la similitud de Jaccard entre dos conjuntos de palabras.

    La similitud de Jaccard es: |interseccion| / |union|

    Args:
        set_a: Primer conjunto de palabras.
        set_b: Segundo conjunto de palabras.

    Returns:
        Un float entre 0.0 y 1.0 representando la similitud.
    """
    if not set_a and not set_b:
        return 0.0

    intersection: set[str] = set_a & set_b
    union: set[str] = set_a | set_b

    if not union:
        return 0.0

    return len(intersection) / len(union)


def _get_priority(article: Article, source_priority: dict[str, int]) -> int:
    """
    Obtiene la prioridad de un articulo segun su fuente.

    Menor numero = mayor prioridad.

    Args:
        article: El articulo a evaluar.
        source_priority: Diccionario de fuente -> prioridad numerica.

    Returns:
        El valor de prioridad (menor = mejor). Default 999 si la fuente no esta en el mapa.
    """
    return source_priority.get(article.source, 999)


def deduplicate_articles(
    articles: list[Article],
    source_priority: dict[str, int],
) -> list[Article]:
    """
    Deduplica una lista de articulos usando URL exacta y similitud de titulos.

    Estrategia en dos pasos:
    1. Deduplicacion por URL exacta: si dos articulos tienen la misma URL,
       se conserva el de la fuente con mayor prioridad (menor numero).
    2. Deduplicacion por similitud de titulo (Jaccard >= 0.6):
       si dos articulos tienen titulos similares, se conserva el de
       la fuente con mayor prioridad.

    Args:
        articles: Lista de articulos a deduplicar.
        source_priority: Diccionario de fuente -> prioridad numerica
                         (menor numero = mayor prioridad).

    Returns:
        Lista de articulos sin duplicados.
    """
    total_inicial: int = len(articles)
    logger.info(f"Iniciando deduplicacion de {total_inicial} articulos")

    # --- Paso 1: Deduplicacion por URL exacta ---
    url_map: dict[str, Article] = {}

    for article in articles:
        url_normalizada: str = article.url.strip().rstrip("/")

        if url_normalizada in url_map:
            # Ya existe un articulo con esta URL, conservar el de mayor prioridad
            existente: Article = url_map[url_normalizada]
            prioridad_existente: int = _get_priority(existente, source_priority)
            prioridad_nueva: int = _get_priority(article, source_priority)

            if prioridad_nueva < prioridad_existente:
                url_map[url_normalizada] = article
                logger.debug(
                    f"URL duplicada: conservando '{article.title}' de "
                    f"'{article.source}' sobre '{existente.source}'"
                )
        else:
            url_map[url_normalizada] = article

    articulos_post_url: list[Article] = list(url_map.values())
    removidos_url: int = total_inicial - len(articulos_post_url)

    if removidos_url > 0:
        logger.info(f"Paso 1 (URL exacta): {removidos_url} duplicados removidos")

    # --- Paso 2: Deduplicacion por similitud de titulo (Jaccard) ---
    # Pre-calcular titulos normalizados para cada articulo
    titulos_normalizados: list[tuple[Article, set[str]]] = [
        (art, normalize_title(art.title)) for art in articulos_post_url
    ]

    # Marcar indices de articulos a eliminar
    indices_a_eliminar: set[int] = set()
    umbral_similitud: float = 0.6

    for i in range(len(titulos_normalizados)):
        if i in indices_a_eliminar:
            continue

        art_i, titulo_i = titulos_normalizados[i]

        for j in range(i + 1, len(titulos_normalizados)):
            if j in indices_a_eliminar:
                continue

            art_j, titulo_j = titulos_normalizados[j]

            similitud: float = jaccard_similarity(titulo_i, titulo_j)

            if similitud >= umbral_similitud:
                # Los articulos son similares, eliminar el de menor prioridad
                prioridad_i: int = _get_priority(art_i, source_priority)
                prioridad_j: int = _get_priority(art_j, source_priority)

                if prioridad_i <= prioridad_j:
                    # Conservar i, eliminar j
                    indices_a_eliminar.add(j)
                    logger.debug(
                        f"Titulo similar (Jaccard={similitud:.2f}): "
                        f"conservando '{art_i.title}' ({art_i.source}), "
                        f"eliminando '{art_j.title}' ({art_j.source})"
                    )
                else:
                    # Conservar j, eliminar i
                    indices_a_eliminar.add(i)
                    logger.debug(
                        f"Titulo similar (Jaccard={similitud:.2f}): "
                        f"conservando '{art_j.title}' ({art_j.source}), "
                        f"eliminando '{art_i.title}' ({art_i.source})"
                    )
                    break  # i fue eliminado, no seguir comparando

    # Construir lista final excluyendo los indices marcados
    articulos_finales: list[Article] = [
        titulos_normalizados[i][0]
        for i in range(len(titulos_normalizados))
        if i not in indices_a_eliminar
    ]

    removidos_titulo: int = len(articulos_post_url) - len(articulos_finales)
    if removidos_titulo > 0:
        logger.info(
            f"Paso 2 (similitud de titulo): {removidos_titulo} duplicados removidos"
        )

    total_removidos: int = total_inicial - len(articulos_finales)
    logger.info(
        f"Deduplicacion completa: {total_inicial} -> {len(articulos_finales)} "
        f"articulos ({total_removidos} removidos en total)"
    )

    return articulos_finales
