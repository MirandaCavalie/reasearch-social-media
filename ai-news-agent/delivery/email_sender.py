"""
Modulo de envio de briefing por email via Gmail SMTP.

Construye un email HTML profesional con las noticias, scripts de TikTok,
signals de influencers y ventanas de oportunidad, y lo envia usando
Gmail con autenticacion por App Password.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sources.models import Briefing

# Configurar logger con formato estandar del proyecto
logger = logging.getLogger("delivery.email_sender")

# Constantes de conexion SMTP
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT = 30


def _virality_badge(score: float) -> str:
    """
    Genera un badge HTML coloreado segun el virality score.

    Rojo para score > 70 (alto potencial viral)
    Naranja para score > 50 (potencial moderado)
    Gris para el resto (potencial bajo)
    """
    if score > 70:
        color = "#e74c3c"
        label = "VIRAL"
    elif score > 50:
        color = "#f39c12"
        label = "TRENDING"
    else:
        color = "#95a5a6"
        label = "NORMAL"

    return (
        f'<span style="background-color:{color};color:#fff;padding:2px 8px;'
        f'border-radius:12px;font-size:12px;font-weight:bold;">'
        f'{label} {score:.0f}/100</span>'
    )


def _build_html_email(briefing: Briefing) -> str:
    """
    Construye el cuerpo HTML del email con todas las secciones del briefing.

    Secciones:
    1. Top 5 noticias con resumenes y virality scores
    2. 3 scripts de TikTok con formato y virality score
    3. Signals de influencers
    4. Ventanas de oportunidad (del analisis raw)
    """
    # Estilos CSS inline para compatibilidad con clientes de email
    html_parts: list[str] = []

    # Inicio del documento HTML con estilos base
    html_parts.append("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
             background-color:#f5f5f5;margin:0;padding:20px;color:#333;">
<div style="max-width:700px;margin:0 auto;background-color:#fff;
            border-radius:12px;overflow:hidden;
            box-shadow:0 2px 10px rgba(0,0,0,0.1);">
""")

    # Header principal
    html_parts.append(f"""
<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            padding:30px;color:#fff;">
  <h1 style="margin:0;font-size:24px;">Tu Briefing de AI</h1>
  <p style="margin:5px 0 0 0;opacity:0.9;font-size:14px;">{briefing.date}</p>
</div>
""")

    # ========================================
    # SECCION 1: Top 5 Noticias
    # ========================================
    html_parts.append("""
<div style="padding:25px;">
  <h2 style="color:#333;border-bottom:2px solid #667eea;padding-bottom:10px;
             font-size:20px;">Top 5 Noticias del Dia</h2>
""")

    if briefing.top_news:
        for i, article in enumerate(briefing.top_news[:5], 1):
            badge = _virality_badge(article.virality_score)
            # Formatear factores de viralidad como tags
            factors_html = ""
            if article.virality_factors:
                factor_tags = " ".join(
                    f'<span style="background-color:#eef2ff;color:#667eea;'
                    f'padding:2px 6px;border-radius:4px;font-size:11px;">{f}</span>'
                    for f in article.virality_factors[:3]
                )
                factors_html = f'<div style="margin-top:5px;">{factor_tags}</div>'

            html_parts.append(f"""
  <div style="margin-bottom:20px;padding:15px;background-color:#fafafa;
              border-radius:8px;border-left:4px solid #667eea;">
    <div style="display:flex;justify-content:space-between;align-items:center;
                margin-bottom:8px;">
      <span style="font-size:12px;color:#888;font-weight:bold;">{article.source}</span>
      {badge}
    </div>
    <h3 style="margin:0 0 8px 0;font-size:16px;">
      <a href="{article.url}" style="color:#333;text-decoration:none;"
         target="_blank">{i}. {article.title}</a>
    </h3>
    <p style="margin:0;color:#666;font-size:14px;line-height:1.5;">
      {article.summary if article.summary else "Sin resumen disponible."}
    </p>
    {factors_html}
  </div>
""")
    else:
        html_parts.append("""
  <p style="color:#888;font-style:italic;">No hay noticias disponibles para hoy.</p>
""")

    html_parts.append("</div>")

    # ========================================
    # SECCION 2: Scripts de TikTok
    # ========================================
    html_parts.append("""
<div style="padding:0 25px 25px 25px;">
  <h2 style="color:#333;border-bottom:2px solid #e74c3c;padding-bottom:10px;
             font-size:20px;">Scripts para TikTok</h2>
""")

    if briefing.scripts:
        for i, script in enumerate(briefing.scripts, 1):
            badge = _virality_badge(script.virality_score)
            # Formatear hashtags como tags visuales
            hashtags_html = ""
            if script.hashtags:
                hashtag_tags = " ".join(
                    f'<span style="background-color:#fff0f0;color:#e74c3c;'
                    f'padding:2px 6px;border-radius:4px;font-size:11px;">{h}</span>'
                    for h in script.hashtags
                )
                hashtags_html = f'<div style="margin-top:10px;">{hashtag_tags}</div>'

            # Seccion de inspiracion si existe
            inspired_html = ""
            if script.inspired_by:
                inspired_html = (
                    f'<div style="margin-top:10px;padding:8px;background-color:#fff8e1;'
                    f'border-radius:4px;font-size:12px;color:#f57f17;">'
                    f'Inspirado en: {script.inspired_by}</div>'
                )

            html_parts.append(f"""
  <div style="margin-bottom:25px;padding:20px;background-color:#fafafa;
              border-radius:8px;border-left:4px solid #e74c3c;">
    <div style="display:flex;justify-content:space-between;align-items:center;
                margin-bottom:10px;">
      <h3 style="margin:0;font-size:16px;color:#333;">Script {i}: {script.title}</h3>
      {badge}
    </div>

    <div style="margin-bottom:10px;">
      <span style="font-size:11px;font-weight:bold;color:#888;text-transform:uppercase;">
        Formato:</span>
      <span style="font-size:13px;color:#555;"> {script.recommended_format}</span>
    </div>

    <div style="background-color:#e74c3c;color:#fff;padding:10px 15px;
                border-radius:6px;margin-bottom:10px;">
      <span style="font-size:11px;font-weight:bold;opacity:0.8;">HOOK:</span>
      <p style="margin:5px 0 0 0;font-size:14px;font-weight:bold;">
        {script.hook}</p>
    </div>

    <div style="margin-bottom:10px;">
      <span style="font-size:11px;font-weight:bold;color:#888;text-transform:uppercase;">
        Cuerpo:</span>
      <p style="margin:5px 0 0 0;color:#555;font-size:13px;line-height:1.6;">
        {script.body}</p>
    </div>

    <div style="margin-bottom:10px;">
      <span style="font-size:11px;font-weight:bold;color:#888;text-transform:uppercase;">
        CTA:</span>
      <p style="margin:5px 0 0 0;color:#555;font-size:13px;">{script.cta}</p>
    </div>

    <div style="margin-bottom:5px;">
      <span style="font-size:11px;font-weight:bold;color:#888;text-transform:uppercase;">
        Por que es viral:</span>
      <p style="margin:5px 0 0 0;color:#555;font-size:12px;font-style:italic;">
        {script.virality_reasoning}</p>
    </div>

    {hashtags_html}
    {inspired_html}
  </div>
""")
    else:
        html_parts.append("""
  <p style="color:#888;font-style:italic;">No se generaron scripts para hoy.</p>
""")

    html_parts.append("</div>")

    # ========================================
    # SECCION 3: Signals de Influencers
    # ========================================
    html_parts.append("""
<div style="padding:0 25px 25px 25px;">
  <h2 style="color:#333;border-bottom:2px solid #27ae60;padding-bottom:10px;
             font-size:20px;">Influencer Radar</h2>
""")

    if briefing.content_signals:
        for signal in briefing.content_signals:
            # Icono segun plataforma
            platform_colors: dict[str, str] = {
                "youtube": "#FF0000",
                "tiktok": "#000000",
                "x": "#1DA1F2",
                "blog": "#27ae60",
            }
            platform_color = platform_colors.get(signal.platform.lower(), "#888")

            html_parts.append(f"""
  <div style="margin-bottom:12px;padding:12px;background-color:#fafafa;
              border-radius:6px;display:flex;align-items:flex-start;">
    <div style="flex:1;">
      <div style="margin-bottom:4px;">
        <strong style="color:#333;font-size:14px;">{signal.influencer}</strong>
        <span style="background-color:{platform_color};color:#fff;padding:1px 6px;
                     border-radius:4px;font-size:10px;margin-left:5px;">
          {signal.platform.upper()}</span>
        <span style="color:#888;font-size:12px;margin-left:5px;">
          Engagement: {signal.engagement:,}</span>
      </div>
      <p style="margin:0;color:#555;font-size:13px;">
        <strong>Tema:</strong> {signal.topic}</p>
      <p style="margin:2px 0 0 0;color:#888;font-size:12px;">
        <strong>Hook:</strong> "{signal.hook}" |
        <strong>Formato:</strong> {signal.format}</p>
      {"<a href='" + signal.url + "' style='color:#667eea;font-size:12px;' target='_blank'>Ver contenido original</a>" if signal.url else ""}
    </div>
  </div>
""")
    else:
        html_parts.append("""
  <p style="color:#888;font-style:italic;">
    No se detectaron signals de influencers en las ultimas 24 horas.</p>
""")

    html_parts.append("</div>")

    # ========================================
    # SECCION 4: Ventanas de Oportunidad
    # ========================================
    html_parts.append("""
<div style="padding:0 25px 25px 25px;">
  <h2 style="color:#333;border-bottom:2px solid #f39c12;padding-bottom:10px;
             font-size:20px;">Ventanas de Oportunidad</h2>
  <div style="padding:15px;background-color:#fffbf0;border-radius:8px;
              border-left:4px solid #f39c12;">
    <p style="color:#555;font-size:13px;line-height:1.6;margin:0;">
""")

    # Extraer la seccion de ventanas del analisis raw, si existe
    # Si no hay contenido especifico, mostrar un resumen generico
    if briefing.raw_analysis and briefing.raw_analysis not in (
        "API key not configured",
        "",
    ) and not briefing.raw_analysis.startswith("Error"):
        # Intentar extraer solo la parte relevante o mostrar una version truncada
        raw_text = briefing.raw_analysis
        # Limitar a 500 caracteres para el email
        if len(raw_text) > 500:
            summary_text = raw_text[:500] + "..."
        else:
            summary_text = raw_text
        # Escapar HTML basico y convertir saltos de linea
        summary_text = summary_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        summary_text = summary_text.replace("\n", "<br>")
        html_parts.append(summary_text)
    else:
        html_parts.append(
            "Revisa las noticias de arriba y los signals de influencers para "
            "identificar temas que ya son virales en ingles pero aun no se han "
            "cubierto en espanol. Esa ventana es tu oportunidad."
        )

    html_parts.append("""
    </p>
  </div>
</div>
""")

    # Footer
    html_parts.append(f"""
<div style="padding:20px;background-color:#f5f5f5;text-align:center;
            border-top:1px solid #eee;">
  <p style="margin:0;color:#aaa;font-size:12px;">
    AI News Agent | Generado automaticamente el {briefing.date}
  </p>
</div>
</div>
</body>
</html>
""")

    return "".join(html_parts)


def send_email_briefing(briefing: Briefing) -> bool:
    """
    Envia el briefing completo por email usando Gmail SMTP.

    Requiere las variables de entorno GMAIL_USER y GMAIL_APP_PASSWORD.
    Si no estan configuradas, loguea una advertencia y retorna False
    sin crashear.

    Args:
        briefing: El Briefing completo generado por el analyzer

    Returns:
        True si el email se envio exitosamente, False en caso contrario
    """
    # Verificar credenciales de Gmail
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        logger.warning(
            "GMAIL_USER y/o GMAIL_APP_PASSWORD no estan configurados. "
            "Saltando envio de email."
        )
        return False

    # Construir el email
    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_user
    msg["To"] = gmail_user  # Se envia a si mismo
    msg["Subject"] = f"\U0001f3ac Tu briefing de AI \u2014 {briefing.date}"

    # Construir el cuerpo HTML
    html_body = _build_html_email(briefing)

    # Crear version de texto plano como fallback
    text_body = _build_text_fallback(briefing)

    # Adjuntar ambas versiones (el cliente elige cual mostrar)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    logger.info(f"Enviando email a {gmail_user}...")

    try:
        # Conectar al servidor SMTP de Gmail
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        logger.info(f"Email enviado exitosamente a {gmail_user}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Error de autenticacion con Gmail. Verifica GMAIL_USER y "
            "GMAIL_APP_PASSWORD. Recuerda usar un App Password, no tu "
            "contrasena normal."
        )
        return False
    except smtplib.SMTPException as e:
        logger.error(f"Error SMTP al enviar email: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al enviar email: {e}")
        return False


def _build_text_fallback(briefing: Briefing) -> str:
    """
    Construye una version en texto plano del briefing como fallback
    para clientes de email que no soportan HTML.
    """
    lines: list[str] = []
    lines.append(f"Tu Briefing de AI - {briefing.date}")
    lines.append("=" * 50)
    lines.append("")

    # Noticias
    lines.append("TOP 5 NOTICIAS")
    lines.append("-" * 30)
    for i, article in enumerate(briefing.top_news[:5], 1):
        lines.append(f"\n{i}. {article.title}")
        lines.append(f"   Fuente: {article.source}")
        lines.append(f"   Virality: {article.virality_score:.0f}/100")
        lines.append(f"   {article.summary}")
        lines.append(f"   Link: {article.url}")

    # Scripts
    lines.append(f"\n{'=' * 50}")
    lines.append("SCRIPTS DE TIKTOK")
    lines.append("-" * 30)
    for i, script in enumerate(briefing.scripts, 1):
        lines.append(f"\nScript {i}: {script.title}")
        lines.append(f"Formato: {script.recommended_format}")
        lines.append(f"Virality: {script.virality_score:.0f}/100")
        lines.append(f"\nHOOK: {script.hook}")
        lines.append(f"\nCUERPO: {script.body}")
        lines.append(f"\nCTA: {script.cta}")
        lines.append(f"\nHashtags: {' '.join(script.hashtags)}")
        if script.inspired_by:
            lines.append(f"\nInspirado en: {script.inspired_by}")

    # Signals
    lines.append(f"\n{'=' * 50}")
    lines.append("INFLUENCER RADAR")
    lines.append("-" * 30)
    for signal in briefing.content_signals:
        lines.append(
            f"\n{signal.influencer} ({signal.platform}): {signal.topic}"
        )
        lines.append(f"  Hook: \"{signal.hook}\"")
        lines.append(f"  Formato: {signal.format} | Engagement: {signal.engagement:,}")

    lines.append(f"\n{'=' * 50}")
    lines.append("Generado automaticamente por AI News Agent")

    return "\n".join(lines)
