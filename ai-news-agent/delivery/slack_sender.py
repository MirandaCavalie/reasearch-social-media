"""
Modulo de envio de briefing por Slack webhook.

Construye un mensaje con Slack Block Kit que incluye noticias,
scripts de TikTok y signals de influencers, y lo envia via
Slack Incoming Webhook.
"""

import json
import logging
import os

import requests

from sources.models import Briefing

# Configurar logger con formato estandar del proyecto
logger = logging.getLogger("delivery.slack_sender")

# Timeout para la peticion HTTP al webhook
REQUEST_TIMEOUT = 30


def _virality_emoji(score: float) -> str:
    """
    Retorna un emoji indicador segun el virality score.

    Fuego para score > 70 (alto potencial viral)
    Rayo para score > 50 (potencial moderado)
    Circulo blanco para el resto
    """
    if score > 70:
        return ":fire:"
    elif score > 50:
        return ":zap:"
    else:
        return ":white_circle:"


def _build_slack_blocks(briefing: Briefing) -> list[dict]:
    """
    Construye los bloques de Slack Block Kit para el mensaje del briefing.

    Estructura:
    - Header con fecha
    - Seccion de top 5 noticias con links y virality emoji
    - Divider
    - Seccion de 3 scripts (hook + formato)
    - Divider
    - Seccion de influencer radar
    """
    blocks: list[dict] = []

    # ========================================
    # Header principal
    # ========================================
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f":movie_camera: Tu Briefing de AI - {briefing.date}",
            "emoji": True,
        },
    })

    # ========================================
    # SECCION: Top 5 Noticias
    # ========================================
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*:newspaper: Top 5 Noticias del Dia*",
        },
    })

    if briefing.top_news:
        # Construir la lista de noticias con formato markdown de Slack
        news_lines: list[str] = []
        for i, article in enumerate(briefing.top_news[:5], 1):
            emoji = _virality_emoji(article.virality_score)
            # Formato: emoji numero. titulo (fuente) - virality score
            news_lines.append(
                f"{emoji} *{i}.* <{article.url}|{article.title}> "
                f"_({article.source})_ - Virality: {article.virality_score:.0f}/100"
            )
            # Agregar resumen breve si existe
            if article.summary:
                # Limitar el resumen a 150 caracteres para Slack
                resumen = article.summary[:150]
                if len(article.summary) > 150:
                    resumen += "..."
                news_lines.append(f"    _{resumen}_")

        # Slack tiene un limite de 3000 caracteres por bloque de texto
        news_text = "\n".join(news_lines)
        if len(news_text) > 2900:
            news_text = news_text[:2900] + "\n..."

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": news_text,
            },
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No hay noticias disponibles para hoy._",
            },
        })

    # Divider entre secciones
    blocks.append({"type": "divider"})

    # ========================================
    # SECCION: Scripts de TikTok
    # ========================================
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*:clapper: Scripts para TikTok*",
        },
    })

    if briefing.scripts:
        for i, script in enumerate(briefing.scripts, 1):
            emoji = _virality_emoji(script.virality_score)

            # Construir bloque de cada script
            script_text_parts: list[str] = [
                f"{emoji} *Script {i}: {script.title}*",
                f":mega: *Hook:* \"{script.hook}\"",
                f":movie_camera: *Formato:* {script.recommended_format}",
                f":chart_with_upwards_trend: *Virality:* {script.virality_score:.0f}/100",
            ]

            # Agregar hashtags si existen
            if script.hashtags:
                hashtags_str = " ".join(script.hashtags)
                script_text_parts.append(f":label: *Hashtags:* {hashtags_str}")

            # Agregar inspiracion si existe
            if script.inspired_by:
                script_text_parts.append(
                    f":bulb: *Inspirado en:* {script.inspired_by}"
                )

            script_text = "\n".join(script_text_parts)

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": script_text,
                },
            })

            # Separador ligero entre scripts (excepto el ultimo)
            if i < len(briefing.scripts):
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "---",
                        }
                    ],
                })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No se generaron scripts para hoy._",
            },
        })

    # Divider antes del influencer radar
    blocks.append({"type": "divider"})

    # ========================================
    # SECCION: Influencer Radar
    # ========================================
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*:satellite: Influencer Radar*",
        },
    })

    if briefing.content_signals:
        # Construir la lista de signals
        signal_lines: list[str] = []
        for signal in briefing.content_signals:
            # Icono segun plataforma
            platform_emoji: dict[str, str] = {
                "youtube": ":youtube:",
                "tiktok": ":tiktok:",
                "x": ":bird:",
                "blog": ":memo:",
            }
            p_emoji = platform_emoji.get(signal.platform.lower(), ":globe_with_meridians:")

            # Formatear engagement con separador de miles
            engagement_str = f"{signal.engagement:,}" if signal.engagement else "N/A"

            # Construir linea para cada signal
            line_parts = [
                f"{p_emoji} *{signal.influencer}* ({signal.platform})",
                f"    Tema: _{signal.topic}_",
                f"    Hook: \"{signal.hook}\"",
                f"    Formato: {signal.format} | Engagement: {engagement_str}",
            ]

            # Agregar URL si existe
            if signal.url:
                line_parts.append(f"    <{signal.url}|Ver contenido original>")

            signal_lines.extend(line_parts)
            signal_lines.append("")  # Linea vacia como separador

        signal_text = "\n".join(signal_lines)

        # Respetar limite de caracteres de Slack por bloque
        if len(signal_text) > 2900:
            signal_text = signal_text[:2900] + "\n..."

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": signal_text,
            },
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "_No se detectaron signals de influencers en las "
                    "ultimas 24 horas._"
                ),
            },
        })

    # Footer con contexto
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f":robot_face: Generado automaticamente por AI News Agent | "
                    f"{briefing.date}"
                ),
            }
        ],
    })

    return blocks


def send_slack_briefing(briefing: Briefing) -> bool:
    """
    Envia el briefing por Slack usando un Incoming Webhook.

    Requiere la variable de entorno SLACK_WEBHOOK_URL.
    Si no esta configurada, loguea un mensaje informativo y retorna False
    sin crashear.

    Args:
        briefing: El Briefing completo generado por el analyzer

    Returns:
        True si el mensaje se envio exitosamente, False en caso contrario
    """
    # Verificar que el webhook este configurado
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        logger.info(
            "SLACK_WEBHOOK_URL no esta configurado. Saltando envio a Slack."
        )
        return False

    # Construir los bloques del mensaje
    blocks = _build_slack_blocks(briefing)

    # Payload del webhook con Block Kit
    payload: dict = {
        "blocks": blocks,
        # Texto de fallback para notificaciones
        "text": f"Tu Briefing de AI - {briefing.date}",
    }

    logger.info(
        f"Enviando briefing a Slack ({len(blocks)} bloques)..."
    )

    try:
        # Enviar POST al webhook con timeout de seguridad
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )

        # Verificar respuesta del webhook
        if response.status_code == 200 and response.text == "ok":
            logger.info("Briefing enviado exitosamente a Slack")
            return True
        else:
            logger.error(
                f"Error al enviar a Slack: status={response.status_code}, "
                f"response={response.text}"
            )
            return False

    except requests.exceptions.Timeout:
        logger.error(
            f"Timeout al enviar a Slack (>{REQUEST_TIMEOUT}s). "
            f"Verifica la URL del webhook."
        )
        return False
    except requests.exceptions.ConnectionError:
        logger.error(
            "Error de conexion al enviar a Slack. Verifica tu conexion "
            "a internet y la URL del webhook."
        )
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error HTTP al enviar a Slack: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al enviar a Slack: {e}")
        return False
