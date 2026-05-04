#!/usr/bin/env python3
"""
AI News Agent — Orquestador principal.

Recolecta noticias de AI/tech de multiples fuentes, las analiza con Claude API,
genera scripts para TikTok, y envia un briefing por email y Slack.

Uso:
    python main.py                    # Ejecucion normal
    python main.py --dry-run          # Sin enviar email/Slack
    python main.py --source rss       # Solo una fuente especifica
    python main.py --schedule         # Ejecutar con scheduler diario
"""

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Importar modulos del proyecto
from sources.rss import fetch_rss_articles
from sources.hackernews import fetch_hackernews_articles
from sources.reddit import fetch_reddit_articles
from sources.arxiv import fetch_arxiv_articles
from sources.apify_twitter import fetch_twitter_articles
from sources.influencers import fetch_influencer_signals
from sources.models import Article, ContentSignal

from processor.dedup import deduplicate_articles
from processor.virality import score_all_articles
from processor.ranker import rank_articles

from llm.analyzer import analyze_news

from delivery.email_sender import send_email_briefing
from delivery.slack_sender import send_slack_briefing

from obsidian.reader import ObsidianReader
from obsidian.writer import ObsidianWriter


def setup_logging() -> None:
    """Configura el logging con formato estandar del proyecto."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def load_config() -> dict:
    """Carga la configuracion desde config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_obsidian_reader() -> ObsidianReader | None:
    """Intenta crear un ObsidianReader desde OBSIDIAN_VAULT_PATH.

    Returns:
        ObsidianReader si el vault existe, None si no esta configurado o no existe.
    """
    logger = logging.getLogger("main")
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path:
        logger.info("OBSIDIAN_VAULT_PATH no configurado, usando solo config.yaml")
        return None
    try:
        reader = ObsidianReader(vault_path)
        logger.info(f"Obsidian vault conectado: {vault_path}")
        return reader
    except FileNotFoundError:
        logger.warning(f"Obsidian vault no encontrado en: {vault_path}. Usando config.yaml como fallback")
        return None


def load_obsidian_writer() -> ObsidianWriter | None:
    """Intenta crear un ObsidianWriter desde OBSIDIAN_VAULT_PATH.

    Returns:
        ObsidianWriter si el vault existe, None si no esta configurado.
    """
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path or not Path(vault_path).exists():
        return None
    return ObsidianWriter(vault_path)


def merge_obsidian_config(config: dict, reader: ObsidianReader) -> dict:
    """Sobreescribe la configuracion de config.yaml con datos del vault de Obsidian.

    Solo sobreescribe las secciones que existen en el vault.
    Si un archivo del vault esta vacio o no existe, se mantiene config.yaml.

    Args:
        config: Configuracion base desde config.yaml
        reader: ObsidianReader inicializado

    Returns:
        Config actualizado con datos de Obsidian
    """
    logger = logging.getLogger("main")

    # RSS feeds desde Obsidian
    obsidian_feeds = reader.read_rss_feeds()
    if obsidian_feeds:
        config["rss_feeds"] = obsidian_feeds
        logger.info(f"RSS feeds cargados desde Obsidian: {len(obsidian_feeds)}")

    # Influencers desde Obsidian
    obsidian_influencers = reader.read_influencers()
    if obsidian_influencers:
        if obsidian_influencers.get("rss_feeds"):
            config.setdefault("influencers", {})["rss_feeds"] = obsidian_influencers["rss_feeds"]
        if obsidian_influencers.get("twitter_handles"):
            config.setdefault("influencers", {})["twitter_handles"] = obsidian_influencers["twitter_handles"]
        logger.info("Influencers cargados desde Obsidian")

    # Keywords desde Obsidian
    obsidian_keywords = reader.read_keywords()
    if obsidian_keywords:
        # Mapear keywords a las secciones correspondientes de config
        if "hackernews" in obsidian_keywords or "hn_keywords" in obsidian_keywords:
            hn_keywords = obsidian_keywords.get("hackernews") or obsidian_keywords.get("hn_keywords", [])
            if hn_keywords:
                config.setdefault("hackernews", {})["keywords"] = hn_keywords
        if "high_value" in obsidian_keywords or "high_value_keywords" in obsidian_keywords:
            hv_keywords = obsidian_keywords.get("high_value") or obsidian_keywords.get("high_value_keywords", [])
            if hv_keywords:
                config.setdefault("ranking", {})["high_value_keywords"] = hv_keywords
        logger.info("Keywords cargados desde Obsidian")

    # Learnings desde Obsidian (se pasan al analyzer via config)
    learnings = reader.read_learnings()
    if learnings:
        config["_obsidian_learnings"] = learnings
        logger.info("Learnings cargados desde Obsidian")

    return config


def collect_sources(config: dict, source_filter: str | None = None) -> tuple[list[Article], list[ContentSignal]]:
    """Recolecta articulos de todas las fuentes en paralelo.

    Args:
        config: Configuracion completa desde config.yaml.
        source_filter: Si se especifica, solo ejecuta esa fuente.

    Returns:
        Tupla de (articulos, content_signals).
    """
    logger = logging.getLogger("main")
    all_articles: list[Article] = []
    all_signals: list[ContentSignal] = []

    # Definir las tareas de recoleccion
    tasks: dict[str, callable] = {
        "rss": lambda: fetch_rss_articles(config.get("rss_feeds", [])),
        "hackernews": lambda: fetch_hackernews_articles(config.get("hackernews", {})),
        "reddit": lambda: fetch_reddit_articles(config.get("reddit_subreddits", [])),
        "arxiv": lambda: fetch_arxiv_articles(config.get("arxiv", {})),
        "twitter": lambda: fetch_twitter_articles(config.get("apify", {})),
    }

    # Si hay filtro, solo ejecutar esa fuente
    if source_filter:
        if source_filter not in tasks:
            logger.error(f"Fuente desconocida: {source_filter}. Opciones: {list(tasks.keys())}")
            return [], []
        tasks = {source_filter: tasks[source_filter]}

    # Ejecutar fuentes en paralelo
    logger.info(f"Ejecutando {len(tasks)} fuentes en paralelo...")
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_source = {
            executor.submit(task): name
            for name, task in tasks.items()
        }

        for future in as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                result = future.result()
                if isinstance(result, list) and result:
                    all_articles.extend(result)
                    logger.info(f"[{source_name}] {len(result)} articulos recolectados")
                else:
                    logger.info(f"[{source_name}] 0 articulos")
            except Exception as e:
                logger.error(f"[{source_name}] Error: {e}")

    # Recolectar signals de influencers (siempre, a menos que haya filtro de fuente)
    if not source_filter or source_filter == "influencers":
        try:
            logger.info("Recolectando content signals de influencers...")
            all_signals = fetch_influencer_signals(config.get("influencers", {}))
            logger.info(f"Content signals recolectados: {len(all_signals)}")
        except Exception as e:
            logger.error(f"Error recolectando influencer signals: {e}")

    return all_articles, all_signals


def run_pipeline(
    config: dict,
    dry_run: bool = False,
    source_filter: str | None = None,
    obsidian_writer: ObsidianWriter | None = None,
) -> None:
    """Ejecuta el pipeline completo del agente.

    Pasos:
    1. Recolectar de todas las fuentes
    2. Deduplicar
    3. Calcular virality scores
    4. Rankear
    5. Analizar con Claude API
    6. Enviar briefing por email, Slack y Obsidian

    Args:
        config: Configuracion completa.
        dry_run: Si True, no envia email/Slack/Obsidian.
        source_filter: Si se especifica, solo ejecuta esa fuente.
        obsidian_writer: Writer para guardar el brief en Obsidian (opcional).
    """
    logger = logging.getLogger("main")
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("AI News Agent — Iniciando pipeline")
    logger.info(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Modo: {'DRY RUN' if dry_run else 'PRODUCCION'}")
    if source_filter:
        logger.info(f"Filtro de fuente: {source_filter}")
    logger.info("=" * 60)

    # --- Paso 1: Recolectar ---
    logger.info("[PASO 1/6] Recolectando noticias de fuentes...")
    articles, signals = collect_sources(config, source_filter)
    total_collected = len(articles)
    logger.info(f"Total recolectado: {total_collected} articulos, {len(signals)} signals")

    if not articles:
        logger.warning("No se recolectaron articulos. Abortando pipeline.")
        return

    # --- Paso 2: Deduplicar ---
    logger.info("[PASO 2/6] Deduplicando articulos...")
    source_priority = config.get("source_priority", {})
    articles = deduplicate_articles(articles, source_priority)
    total_after_dedup = len(articles)
    logger.info(f"Despues de deduplicacion: {total_after_dedup} articulos")

    # --- Paso 3: Calcular virality scores ---
    logger.info("[PASO 3/6] Calculando virality scores...")
    virality_config = config.get("virality", {})
    articles = score_all_articles(articles, virality_config)

    # --- Paso 4: Rankear ---
    logger.info("[PASO 4/6] Rankeando articulos...")
    ranking_config = config.get("ranking", {})
    top_articles = rank_articles(articles, signals, ranking_config)
    logger.info(f"Top {len(top_articles)} articulos seleccionados")

    # --- Paso 5: Analizar con Claude API ---
    logger.info("[PASO 5/6] Analizando con Claude API...")
    llm_config = config.get("llm", {})
    learnings = config.get("_obsidian_learnings", "")
    briefing = analyze_news(top_articles, signals, llm_config, learnings=learnings)
    logger.info(
        f"Briefing generado: {len(briefing.top_news)} noticias, "
        f"{len(briefing.scripts)} scripts"
    )

    # --- Paso 6: Enviar briefing ---
    if dry_run:
        logger.info("[PASO 6/6] DRY RUN — Imprimiendo briefing en consola...")
        _print_briefing(briefing)
    else:
        logger.info("[PASO 6/6] Enviando briefing...")
        email_sent = send_email_briefing(briefing)
        slack_sent = send_slack_briefing(briefing)
        logger.info(f"Email: {'enviado' if email_sent else 'no enviado'}")
        logger.info(f"Slack: {'enviado' if slack_sent else 'no enviado'}")

        # Escribir a Obsidian si esta configurado
        if obsidian_writer:
            obsidian_ok = obsidian_writer.write_brief(briefing)
            logger.info(f"Obsidian: {'escrito' if obsidian_ok else 'error al escribir'}")

    # --- Resumen final ---
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("RESUMEN")
    logger.info(f"  Articulos recolectados: {total_collected}")
    logger.info(f"  Despues de dedup: {total_after_dedup}")
    logger.info(f"  Top seleccionados: {len(top_articles)}")
    logger.info(f"  Scripts generados: {len(briefing.scripts)}")
    logger.info(f"  Tiempo total: {elapsed:.1f} segundos")
    logger.info("=" * 60)


def _print_briefing(briefing) -> None:
    """Imprime el briefing en consola (modo dry-run)."""
    print("\n" + "=" * 60)
    print(f"BRIEFING DE AI — {briefing.date}")
    print("=" * 60)

    print("\n--- TOP 5 NOTICIAS ---")
    for i, article in enumerate(briefing.top_news[:5], 1):
        print(f"\n{i}. [{article.source}] {article.title}")
        print(f"   Virality: {article.virality_score:.0f}/100")
        print(f"   URL: {article.url}")
        if article.summary:
            print(f"   {article.summary[:150]}")

    print("\n--- SCRIPTS DE TIKTOK ---")
    for i, script in enumerate(briefing.scripts, 1):
        print(f"\nSCRIPT {i}: {script.title}")
        print(f"  Formato: {script.recommended_format}")
        print(f"  Virality: {script.virality_score:.0f}/100")
        print(f"  HOOK: {script.hook}")
        print(f"  CUERPO: {script.body[:200]}...")
        print(f"  CTA: {script.cta}")
        print(f"  Hashtags: {' '.join(script.hashtags)}")
        if script.inspired_by:
            print(f"  Inspirado en: {script.inspired_by}")

    print("\n--- INFLUENCER SIGNALS ---")
    for signal in briefing.content_signals[:10]:
        print(f"  {signal.influencer} ({signal.platform}): {signal.topic[:80]}")

    if briefing.raw_analysis and not briefing.raw_analysis.startswith("Error"):
        print("\n--- ANALISIS COMPLETO ---")
        print(briefing.raw_analysis[:2000])

    print("\n" + "=" * 60)


def main() -> None:
    """Punto de entrada principal del agente."""
    parser = argparse.ArgumentParser(
        description="AI News Agent — Recolecta noticias de AI/tech y genera scripts para TikTok"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecutar sin enviar email/Slack (imprime en consola)",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["rss", "hackernews", "reddit", "arxiv", "twitter", "influencers"],
        help="Ejecutar solo una fuente especifica (para debugging)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Ejecutar con scheduler diario (7:00 AM PST)",
    )

    args = parser.parse_args()

    # Configurar logging
    setup_logging()
    logger = logging.getLogger("main")

    # Cargar configuracion
    try:
        config = load_config()
        logger.info("Configuracion cargada desde config.yaml")
    except Exception as e:
        logger.error(f"Error cargando configuracion: {e}")
        sys.exit(1)

    # Integrar Obsidian (leer fuentes del vault si esta disponible)
    obsidian_reader = load_obsidian_reader()
    if obsidian_reader:
        config = merge_obsidian_config(config, obsidian_reader)

    obsidian_writer = load_obsidian_writer()

    if args.schedule:
        # Modo scheduler: ejecutar cada dia a las 7:00 AM
        import schedule as sched

        run_hour = int(os.getenv("RUN_HOUR", "7"))
        run_minute = int(os.getenv("RUN_MINUTE", "0"))
        schedule_time = f"{run_hour:02d}:{run_minute:02d}"

        logger.info(f"Scheduler activado. Ejecutando diariamente a las {schedule_time}")

        sched.every().day.at(schedule_time).do(
            run_pipeline, config=config, dry_run=args.dry_run,
            source_filter=args.source, obsidian_writer=obsidian_writer
        )

        while True:
            sched.run_pending()
            time.sleep(60)
    else:
        # Ejecucion unica
        run_pipeline(config, dry_run=args.dry_run, source_filter=args.source,
                     obsidian_writer=obsidian_writer)


if __name__ == "__main__":
    main()
