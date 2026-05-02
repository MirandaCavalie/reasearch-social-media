#!/usr/bin/env python3
"""
Tests para el AI News Agent.

Prueba cada fuente individualmente y verifica que los procesadores
funcionen correctamente con datos de ejemplo.

Uso:
    python test_sources.py              # Correr todos los tests
    python test_sources.py test_rss     # Correr un test especifico
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Agregar el directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

from sources.models import Article, ContentSignal
from processor.dedup import deduplicate_articles, jaccard_similarity, normalize_title
from processor.virality import calculate_virality_score, score_all_articles
from processor.ranker import rank_articles

# Configurar logging para tests
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tests")


def test_rss() -> bool:
    """Verifica que feedparser retorna articulos de RSS feeds."""
    logger.info("=== TEST: RSS Feeds ===")
    try:
        from sources.rss import fetch_rss_articles

        feeds = [
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
        ]
        articles = fetch_rss_articles(feeds)

        assert len(articles) > 0, "No se obtuvieron articulos de RSS"
        assert articles[0].title, "El primer articulo no tiene titulo"
        assert articles[0].url, "El primer articulo no tiene URL"
        assert articles[0].source == "Ars Technica", f"Fuente incorrecta: {articles[0].source}"

        logger.info(f"PASS: RSS retorno {len(articles)} articulos")
        logger.info(f"  Ejemplo: {articles[0].title[:80]}")
        return True
    except Exception as e:
        logger.error(f"FAIL: RSS — {e}")
        return False


def test_hackernews() -> bool:
    """Verifica que Hacker News API responde."""
    logger.info("=== TEST: Hacker News ===")
    try:
        from sources.hackernews import fetch_hackernews_articles

        config = {"top_n": 10, "keywords": ["AI", "LLM", "startup"]}
        articles = fetch_hackernews_articles(config)

        # HN puede no tener articulos que matcheen keywords, pero la API debe responder
        assert isinstance(articles, list), "El resultado no es una lista"

        logger.info(f"PASS: HN retorno {len(articles)} articulos filtrados")
        if articles:
            logger.info(f"  Ejemplo: {articles[0].title[:80]}")
        return True
    except Exception as e:
        logger.error(f"FAIL: Hacker News — {e}")
        return False


def test_reddit() -> bool:
    """Verifica que Reddit RSS funciona."""
    logger.info("=== TEST: Reddit RSS ===")
    try:
        from sources.reddit import fetch_reddit_articles

        subreddits = ["https://www.reddit.com/r/MachineLearning/hot/.rss"]
        articles = fetch_reddit_articles(subreddits)

        assert len(articles) > 0, "No se obtuvieron articulos de Reddit"
        assert "Reddit" in articles[0].source, f"Fuente incorrecta: {articles[0].source}"

        logger.info(f"PASS: Reddit retorno {len(articles)} articulos")
        logger.info(f"  Ejemplo: {articles[0].title[:80]}")
        return True
    except Exception as e:
        logger.error(f"FAIL: Reddit — {e}")
        return False


def test_arxiv() -> bool:
    """Verifica que ArXiv API retorna papers."""
    logger.info("=== TEST: ArXiv ===")
    try:
        from sources.arxiv import fetch_arxiv_articles

        config = {"categories": ["cs.AI"], "max_results": 3}
        articles = fetch_arxiv_articles(config)

        assert len(articles) > 0, "No se obtuvieron papers de ArXiv"
        assert "ArXiv" in articles[0].source, f"Fuente incorrecta: {articles[0].source}"

        logger.info(f"PASS: ArXiv retorno {len(articles)} papers")
        logger.info(f"  Ejemplo: {articles[0].title[:80]}")
        return True
    except Exception as e:
        logger.error(f"FAIL: ArXiv — {e}")
        return False


def test_apify() -> bool:
    """Verifica conexion con Apify (skip si no hay token)."""
    logger.info("=== TEST: Apify/Twitter ===")
    if not os.getenv("APIFY_TOKEN"):
        logger.info("SKIP: APIFY_TOKEN no configurado")
        return True

    try:
        from sources.apify_twitter import fetch_twitter_articles

        config = {"search_terms": ["AI news"], "max_tweets": 5}
        articles = fetch_twitter_articles(config)

        assert isinstance(articles, list), "El resultado no es una lista"
        logger.info(f"PASS: Apify retorno {len(articles)} tweets")
        return True
    except Exception as e:
        logger.error(f"FAIL: Apify — {e}")
        return False


def test_influencers() -> bool:
    """Verifica que los RSS de influencers retornan contenido."""
    logger.info("=== TEST: Influencers ===")
    try:
        from sources.influencers import fetch_influencer_signals

        config = {
            "rss_feeds": [
                {
                    "name": "Fireship",
                    "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA",
                    "platform": "youtube",
                },
            ],
            "twitter_handles": [],
        }
        signals = fetch_influencer_signals(config)

        assert len(signals) > 0, "No se obtuvieron signals de influencers"
        assert signals[0].influencer == "Fireship", f"Influencer incorrecto: {signals[0].influencer}"
        assert signals[0].platform == "youtube", f"Plataforma incorrecta: {signals[0].platform}"

        logger.info(f"PASS: Influencers retorno {len(signals)} signals")
        logger.info(f"  Ejemplo: {signals[0].influencer} — {signals[0].topic[:60]}")
        return True
    except Exception as e:
        logger.error(f"FAIL: Influencers — {e}")
        return False


def test_virality() -> bool:
    """Verifica que el virality scorer asigna scores correctos."""
    logger.info("=== TEST: Virality Scorer ===")
    try:
        # Articulo con alto potencial viral
        viral_article = Article(
            title="OpenAI launches new free AI tool that replaces Photoshop",
            url="https://example.com/1",
            source="TechCrunch AI",
            published_at=datetime.now(tz=timezone.utc),
            summary="A new free tool that anyone can use to edit photos with AI",
        )

        # Articulo tecnico (bajo potencial viral)
        technical_article = Article(
            title="Convergence proof for gradient descent in batch normalization",
            url="https://example.com/2",
            source="ArXiv",
            published_at=datetime.now(tz=timezone.utc),
            summary="We prove convergence theorem for hyperparameter optimization",
        )

        # Configuracion de viralidad simplificada
        virality_config = {
            "positive_factors": {
                "controversial": {"score": 15, "keywords": ["replace", "kill"]},
                "relatable": {"score": 20, "keywords": ["free", "anyone", "you"]},
                "novelty": {"score": 15, "keywords": ["launch", "new", "release"]},
                "data_driven": {"score": 10, "keywords": ["benchmark", "percent"]},
                "trending_english": {"score": 25, "keywords": []},
                "simple_explainer": {"score": 10, "keywords": ["explained"]},
                "sf_angle": {"score": 5, "keywords": ["San Francisco"]},
            },
            "negative_factors": {
                "too_technical": {"score": -15, "keywords": ["theorem", "convergence", "gradient descent"]},
                "minor_update": {"score": -10, "keywords": ["patch", "hotfix"]},
            },
        }

        # Test articulo viral
        score_viral, factors_viral = calculate_virality_score(viral_article, virality_config)
        assert score_viral > 50, f"Score viral muy bajo: {score_viral}"
        assert len(factors_viral) > 0, "No se detectaron factores de viralidad"

        # Test articulo tecnico
        score_tech, factors_tech = calculate_virality_score(technical_article, virality_config)
        assert score_tech < score_viral, f"Score tecnico ({score_tech}) no deberia ser mayor que viral ({score_viral})"

        # Test con menciones cruzadas
        score_trending, _ = calculate_virality_score(viral_article, virality_config, cross_mention_count=3)
        assert score_trending > score_viral, "Menciones cruzadas deberian aumentar el score"

        logger.info(f"PASS: Virality scores — viral={score_viral:.0f}, tecnico={score_tech:.0f}, trending={score_trending:.0f}")
        logger.info(f"  Factores viral: {factors_viral}")
        return True
    except Exception as e:
        logger.error(f"FAIL: Virality — {e}")
        return False


def test_ranking() -> bool:
    """Verifica que el ranking combinado ordena correctamente."""
    logger.info("=== TEST: Ranking ===")
    try:
        now = datetime.now(tz=timezone.utc)

        # Crear articulos de prueba con diferentes caracteristicas
        articles = [
            Article(
                title="OpenAI releases GPT-5 with breakthrough performance",
                url="https://example.com/1",
                source="TechCrunch AI",
                published_at=now - timedelta(hours=1),
                summary="Major launch with benchmark improvements",
                engagement=500,
                virality_score=85,
                cross_mentions=3,
            ),
            Article(
                title="Minor patch update for obscure library",
                url="https://example.com/2",
                source="Reddit",
                published_at=now - timedelta(hours=48),
                summary="Bugfix patch for internal tool",
                engagement=5,
                virality_score=15,
                cross_mentions=0,
            ),
            Article(
                title="AI startup raises $100 million in funding round",
                url="https://example.com/3",
                source="The Verge AI",
                published_at=now - timedelta(hours=3),
                summary="Major funding for AI company",
                engagement=200,
                virality_score=70,
                cross_mentions=2,
            ),
        ]

        signals = [
            ContentSignal(
                influencer="@mattwolfe",
                platform="youtube",
                topic="GPT-5 released breakthrough AI performance",
                format="news",
                hook="GPT-5 just dropped",
                engagement=100000,
            ),
        ]

        ranking_config = {
            "recency_bonus_hours": 6,
            "recency_multiplier": 2.0,
            "cross_mention_bonus": 1.5,
            "hn_score_threshold": 100,
            "high_value_keywords": ["launch", "release", "funding", "open source"],
            "high_value_multiplier": 1.3,
            "weights": {"trending": 0.4, "virality": 0.4, "influencer_signal": 0.2},
            "top_n": 10,
        }

        ranked = rank_articles(articles, signals, ranking_config)

        assert len(ranked) == 3, f"Se esperaban 3 articulos, se obtuvieron {len(ranked)}"
        # El primer articulo deberia ser el de GPT-5 (reciente, viral, con signal de influencer)
        assert "GPT-5" in ranked[0].title, f"El primer articulo deberia ser GPT-5, fue: {ranked[0].title}"
        # El ultimo deberia ser el minor patch
        assert "patch" in ranked[-1].title.lower(), f"El ultimo deberia ser el patch, fue: {ranked[-1].title}"

        logger.info("PASS: Ranking ordena correctamente")
        for i, a in enumerate(ranked, 1):
            logger.info(f"  #{i}: {a.title[:50]} (trending={a.trending_score:.1f}, virality={a.virality_score:.0f})")
        return True
    except Exception as e:
        logger.error(f"FAIL: Ranking — {e}")
        return False


def test_dedup() -> bool:
    """Verifica que la deduplicacion funciona correctamente."""
    logger.info("=== TEST: Deduplicacion ===")
    try:
        now = datetime.now(tz=timezone.utc)

        articles = [
            Article(title="OpenAI launches GPT-5", url="https://example.com/1",
                    source="TechCrunch AI", published_at=now),
            Article(title="OpenAI launches GPT-5 model", url="https://example.com/2",
                    source="Reddit", published_at=now),
            Article(title="Something completely different about startups", url="https://example.com/3",
                    source="Hacker News", published_at=now),
            # Duplicado por URL exacta
            Article(title="OpenAI GPT-5 announcement", url="https://example.com/1",
                    source="Ars Technica", published_at=now),
        ]

        source_priority = {"TechCrunch AI": 1, "The Verge AI": 2, "Reddit": 10, "Hacker News": 9, "Ars Technica": 6}
        deduped = deduplicate_articles(articles, source_priority)

        # Deberia quedar: TechCrunch (original + URL dup conserva TechCrunch) y el de startups
        assert len(deduped) < len(articles), f"No se eliminaron duplicados: {len(deduped)} == {len(articles)}"
        assert len(deduped) == 2, f"Se esperaban 2, se obtuvieron {len(deduped)}"

        # Verificar Jaccard similarity
        sim = jaccard_similarity(
            normalize_title("OpenAI launches GPT-5"),
            normalize_title("OpenAI launches GPT-5 model"),
        )
        assert sim > 0.6, f"Jaccard similarity deberia ser > 0.6: {sim}"

        logger.info(f"PASS: Deduplicacion — de {len(articles)} a {len(deduped)}")
        return True
    except Exception as e:
        logger.error(f"FAIL: Deduplicacion — {e}")
        return False


def main() -> None:
    """Ejecuta todos los tests o uno especifico si se pasa como argumento."""
    tests = {
        "test_rss": test_rss,
        "test_hackernews": test_hackernews,
        "test_reddit": test_reddit,
        "test_arxiv": test_arxiv,
        "test_apify": test_apify,
        "test_influencers": test_influencers,
        "test_virality": test_virality,
        "test_ranking": test_ranking,
        "test_dedup": test_dedup,
    }

    # Si se pasa un test especifico como argumento
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name in tests:
            result = tests[test_name]()
            sys.exit(0 if result else 1)
        else:
            print(f"Test desconocido: {test_name}")
            print(f"Tests disponibles: {list(tests.keys())}")
            sys.exit(1)

    # Ejecutar todos los tests
    results: dict[str, bool] = {}
    for name, test_fn in tests.items():
        results[name] = test_fn()
        print()

    # Resumen
    print("=" * 60)
    print("RESUMEN DE TESTS")
    print("=" * 60)
    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\nResultado: {passed}/{total} tests pasaron")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
