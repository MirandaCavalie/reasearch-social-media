"""
Modulo de analisis con Claude API.

Toma las noticias rankeadas y los content signals de influencers,
los envia a Claude API con el system prompt, y parsea la respuesta
para generar el Briefing final del dia.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path

from sources.models import Article, Briefing, ContentSignal, Script

# Configurar logger con formato estandar del proyecto
logger = logging.getLogger("llm.analyzer")


def _load_system_prompt() -> str:
    """Carga el system prompt desde el archivo prompts/system_prompt.md."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"System prompt cargado desde {prompt_path} ({len(content)} caracteres)")
        return content
    except FileNotFoundError:
        logger.error(f"No se encontro el archivo de system prompt en {prompt_path}")
        return ""


def _build_user_message(articles: list[Article], signals: list[ContentSignal]) -> str:
    """
    Construye el mensaje de usuario con las noticias y signals en formato estructurado.

    Este formato permite a Claude API entender claramente cada noticia
    y cada signal de influencer para generar el briefing.
    """
    parts: list[str] = []

    # Seccion de noticias
    parts.append("=== NOTICIAS DEL DIA ===\n")
    for i, article in enumerate(articles, 1):
        # Formatear la fecha de publicacion de forma legible
        fecha = article.published_at.strftime("%Y-%m-%d %H:%M") if article.published_at else "N/A"
        # Unir factores de viralidad en una cadena separada por comas
        factores = ", ".join(article.virality_factors) if article.virality_factors else "Ninguno detectado"

        parts.append(
            f"Noticia {i}:\n"
            f"Titulo: {article.title}\n"
            f"Fuente: {article.source}\n"
            f"Fecha: {fecha}\n"
            f"Resumen: {article.summary}\n"
            f"URL: {article.url}\n"
            f"Trending Score: {article.trending_score:.1f}\n"
            f"Virality Score: {article.virality_score:.0f}/100\n"
            f"Factores de viralidad: {factores}\n"
        )

    # Seccion de content signals de influencers
    parts.append("\n=== CONTENT SIGNALS DE INFLUENCERS (ultimas 24h) ===\n")
    if signals:
        for i, signal in enumerate(signals, 1):
            parts.append(
                f"Signal {i}:\n"
                f"Influencer: {signal.influencer}\n"
                f"Plataforma: {signal.platform}\n"
                f"Tema: {signal.topic}\n"
                f"Formato: {signal.format}\n"
                f"Hook: {signal.hook}\n"
                f"Engagement: {signal.engagement}\n"
                f"URL: {signal.url}\n"
            )
    else:
        parts.append("No se detectaron content signals en las ultimas 24 horas.\n")

    return "\n".join(parts)


def _parse_script_section(section_text: str) -> Script:
    """
    Parsea una seccion individual de script del response de Claude.

    Busca campos como Titulo, Hook, Cuerpo, CTA, Hashtags, etc.
    y los extrae para crear un objeto Script.
    """
    script = Script()

    # Mapeo de patrones a campos del Script
    # Cada patron busca la etiqueta seguida de su contenido hasta la siguiente etiqueta o fin de seccion
    field_patterns: dict[str, str] = {
        "title": r"Titulo:\s*(.+?)(?=\n\w+:|$)",
        "hook": r"Hook:\s*(.+?)(?=\nCuerpo:|$)",
        "body": r"Cuerpo:\s*(.+?)(?=\nCTA:|$)",
        "cta": r"CTA:\s*(.+?)(?=\nHashtags:|$)",
        "hashtags_raw": r"Hashtags:\s*(.+?)(?=\nFormato Recomendado:|$)",
        "recommended_format": r"Formato Recomendado:\s*(.+?)(?=\nVirality Score:|$)",
        "virality_score_raw": r"Virality Score:\s*(.+?)(?=\nVirality Reasoning:|$)",
        "virality_reasoning": r"Virality Reasoning:\s*(.+?)(?=\nInspirado en:|$)",
        "inspired_by": r"Inspirado en:\s*(.+?)(?=\n\n|$)",
    }

    for field_name, pattern in field_patterns.items():
        match = re.search(pattern, section_text, re.DOTALL)
        if match:
            value = match.group(1).strip()

            if field_name == "title":
                script.title = value
            elif field_name == "hook":
                script.hook = value
            elif field_name == "body":
                script.body = value
            elif field_name == "cta":
                script.cta = value
            elif field_name == "hashtags_raw":
                # Parsear hashtags: pueden venir separados por comas o espacios
                hashtags = re.findall(r"#\w+", value)
                if not hashtags:
                    # Si no tienen #, separar por comas
                    hashtags = [tag.strip() for tag in value.split(",") if tag.strip()]
                script.hashtags = hashtags
            elif field_name == "recommended_format":
                script.recommended_format = value
            elif field_name == "virality_score_raw":
                # Extraer el numero del virality score (ej: "75/100" -> 75.0)
                score_match = re.search(r"(\d+)", value)
                if score_match:
                    script.virality_score = float(score_match.group(1))
            elif field_name == "virality_reasoning":
                script.virality_reasoning = value
            elif field_name == "inspired_by":
                script.inspired_by = value

    return script


def _parse_response(response_text: str, articles: list[Article], signals: list[ContentSignal]) -> Briefing:
    """
    Parsea la respuesta completa de Claude API para extraer el briefing.

    Divide la respuesta en secciones (TOP 5 NOTICIAS y SCRIPTS DE TIKTOK)
    y extrae la informacion estructurada de cada una.
    """
    briefing = Briefing(
        date=datetime.now().strftime("%Y-%m-%d"),
        raw_analysis=response_text,
        content_signals=signals,
    )

    # Extraer las top 5 noticias (usamos los articulos originales ya rankeados)
    briefing.top_news = articles[:5]

    # Extraer scripts de la seccion SCRIPTS DE TIKTOK
    scripts_section_match = re.search(
        r"=== SCRIPTS DE TIKTOK ===\s*(.+)",
        response_text,
        re.DOTALL,
    )

    if scripts_section_match:
        scripts_text = scripts_section_match.group(1)

        # Dividir por SCRIPT 1:, SCRIPT 2:, SCRIPT 3:
        script_sections = re.split(r"SCRIPT\s+\d+:", scripts_text)

        # El primer elemento es texto antes de SCRIPT 1, lo descartamos
        script_sections = [s.strip() for s in script_sections if s.strip()]

        for i, section in enumerate(script_sections[:3]):
            script = _parse_script_section(section)
            if not script.title:
                script.title = f"Script {i + 1}"
            briefing.scripts.append(script)
            logger.info(f"Script {i + 1} parseado: '{script.title}' (virality: {script.virality_score})")
    else:
        logger.warning("No se encontro la seccion '=== SCRIPTS DE TIKTOK ===' en la respuesta")

    logger.info(
        f"Briefing parseado: {len(briefing.top_news)} noticias, "
        f"{len(briefing.scripts)} scripts"
    )
    return briefing


def analyze_news(
    articles: list[Article],
    signals: list[ContentSignal],
    config: dict,
    learnings: str = "",
) -> Briefing:
    """
    Analiza las noticias y content signals usando Claude API.

    Envia las noticias rankeadas y los signals de influencers a Claude
    con el system prompt especializado para generar:
    - Top 5 noticias con resumenes
    - 3 scripts de TikTok listos para grabar
    - Analisis de ventanas de oportunidad

    Args:
        articles: Lista de articulos ya rankeados (top 10)
        signals: Lista de content signals de influencers
        config: Diccionario con 'model' y 'max_tokens' del LLM
        learnings: Texto de learnings de Obsidian para ajustar el system prompt

    Returns:
        Briefing completo con noticias, scripts y analisis
    """
    # Verificar que la API key este configurada
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error(
            "ANTHROPIC_API_KEY no esta configurada en las variables de entorno. "
            "No se puede realizar el analisis con Claude API."
        )
        return Briefing(
            date=datetime.now().strftime("%Y-%m-%d"),
            top_news=articles[:5],
            content_signals=signals,
            raw_analysis="API key not configured",
        )

    # Cargar el system prompt desde archivo
    system_prompt = _load_system_prompt()
    if not system_prompt:
        logger.error("System prompt vacio, el analisis podria no ser optimo")

    # Agregar learnings de Obsidian al system prompt si existen
    if learnings:
        system_prompt += (
            "\n\n=== LEARNINGS DEL CREADOR ===\n"
            "Usa estos aprendizajes previos para ajustar tus recomendaciones:\n\n"
            f"{learnings}"
        )
        logger.info(f"Learnings agregados al system prompt ({len(learnings)} caracteres)")

    # Construir el mensaje de usuario con datos estructurados
    user_message = _build_user_message(articles, signals)
    logger.info(
        f"Mensaje de usuario construido: {len(user_message)} caracteres, "
        f"{len(articles)} noticias, {len(signals)} signals"
    )

    # Parametros del modelo desde config
    model = config.get("model", "claude-sonnet-4-20250514")
    max_tokens = config.get("max_tokens", 4096)

    logger.info(f"Enviando request a Claude API (modelo: {model}, max_tokens: {max_tokens})")

    try:
        # Importar anthropic aqui para evitar error si no esta instalado
        import anthropic

        # Crear cliente de Anthropic (usa ANTHROPIC_API_KEY automaticamente)
        client = anthropic.Anthropic()

        # Llamada a la API de Claude
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
        )

        # Extraer el texto de la respuesta
        response_text = message.content[0].text
        logger.info(
            f"Respuesta recibida de Claude API: {len(response_text)} caracteres, "
            f"tokens usados: input={message.usage.input_tokens}, output={message.usage.output_tokens}"
        )

        # Parsear la respuesta para construir el Briefing
        briefing = _parse_response(response_text, articles, signals)
        return briefing

    except ImportError:
        logger.error(
            "El paquete 'anthropic' no esta instalado. "
            "Ejecuta: pip install anthropic"
        )
        return Briefing(
            date=datetime.now().strftime("%Y-%m-%d"),
            top_news=articles[:5],
            content_signals=signals,
            raw_analysis="Error: paquete anthropic no instalado",
        )
    except Exception as e:
        logger.error(f"Error al llamar a Claude API: {e}")
        return Briefing(
            date=datetime.now().strftime("%Y-%m-%d"),
            top_news=articles[:5],
            content_signals=signals,
            raw_analysis=f"Error en Claude API: {e}",
        )
