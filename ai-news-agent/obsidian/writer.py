"""
Escritor de briefs al vault de Obsidian.

Genera archivos .md con frontmatter YAML compatibles con Obsidian,
escritos en el directorio Briefs/ del vault.
"""

import logging
from datetime import datetime
from pathlib import Path

from sources.models import Article, Briefing, ContentSignal, Script

logger = logging.getLogger("obsidian.writer")


class ObsidianWriter:
    """Escribe briefs y notas al vault de Obsidian."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.briefs_dir = self.vault_path / "Briefs"

    def write_brief(self, briefing: Briefing) -> bool:
        """Escribe el briefing diario como archivo Markdown en Briefs/.

        Args:
            briefing: El briefing completo generado por el pipeline

        Returns:
            True si se escribio correctamente, False si hubo error
        """
        try:
            # Crear directorio si no existe
            self.briefs_dir.mkdir(parents=True, exist_ok=True)

            # Nombre del archivo: YYYY-MM-DD-brief.md
            date_str = briefing.date or datetime.now().strftime("%Y-%m-%d")
            filename = f"{date_str}-brief.md"
            filepath = self.briefs_dir / filename

            # Generar contenido
            content = self._build_brief_content(briefing, date_str)

            # Escribir archivo
            filepath.write_text(content, encoding="utf-8")
            logger.info(f"Brief escrito en Obsidian: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Error escribiendo brief a Obsidian: {e}")
            return False

    def _build_brief_content(self, briefing: Briefing, date_str: str) -> str:
        """Construye el contenido Markdown del brief con frontmatter."""
        # Calcular virality promedio
        virality_scores = [a.virality_score for a in briefing.top_news if a.virality_score > 0]
        virality_avg = int(sum(virality_scores) / len(virality_scores)) if virality_scores else 0

        # Detectar top sources
        sources = list({a.source for a in briefing.top_news})[:5]

        # Frontmatter
        lines: list[str] = [
            "---",
            f"date: {date_str}",
            f"virality_avg: {virality_avg}",
            f"top_sources: [{', '.join(sources)}]",
            "tags: [ai-news, daily-brief]",
            "---",
            "",
            f"# AI News Brief — {self._format_date_display(date_str)}",
            "",
        ]

        # Top 5 noticias
        lines.append("## Top 5 Noticias")
        lines.append("")
        for i, article in enumerate(briefing.top_news[:5], 1):
            virality_icon = self._virality_icon(article.virality_score)
            lines.append(f"### {i}. {article.title}")
            lines.append("")
            lines.append(f"- **Fuente:** {article.source}")
            lines.append(f"- **Virality:** {virality_icon} {article.virality_score:.0f}/100")
            lines.append(f"- **Link:** [{article.title}]({article.url})")
            if article.summary:
                lines.append(f"- **Resumen:** {article.summary}")
            if article.virality_factors:
                lines.append(f"- **Factores:** {', '.join(article.virality_factors)}")
            lines.append("")

        # Scripts TikTok
        lines.append("## Scripts TikTok")
        lines.append("")
        for i, script in enumerate(briefing.scripts, 1):
            lines.append(f"### Script {i}: {script.title}")
            lines.append("")
            lines.append(f"**Formato:** {script.recommended_format}")
            lines.append(f"**Virality:** {self._virality_icon(script.virality_score)} {script.virality_score:.0f}/100")
            if script.inspired_by:
                lines.append(f"**Inspirado en:** {script.inspired_by}")
            lines.append("")
            lines.append(f"> **HOOK:** {script.hook}")
            lines.append("")
            lines.append(f"**Cuerpo:**")
            lines.append("")
            lines.append(script.body)
            lines.append("")
            lines.append(f"**CTA:** {script.cta}")
            lines.append("")
            if script.hashtags:
                lines.append(f"**Hashtags:** {' '.join(script.hashtags)}")
                lines.append("")
            if script.virality_reasoning:
                lines.append(f"*{script.virality_reasoning}*")
                lines.append("")

        # Influencer Signals
        if briefing.content_signals:
            lines.append("## Influencer Signals")
            lines.append("")
            lines.append("| Influencer | Plataforma | Tema | Formato | Engagement |")
            lines.append("|---|---|---|---|---|")
            for signal in briefing.content_signals[:10]:
                topic_short = signal.topic[:50] + "..." if len(signal.topic) > 50 else signal.topic
                eng = f"{signal.engagement:,}" if signal.engagement else "—"
                lines.append(
                    f"| {signal.influencer} | {signal.platform} | "
                    f"{topic_short} | {signal.format} | {eng} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _format_date_display(self, date_str: str) -> str:
        """Formatea la fecha para el titulo (May 2, 2026)."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%B %-d, %Y")
        except (ValueError, Exception):
            return date_str

    def _virality_icon(self, score: float) -> str:
        """Retorna un icono segun el virality score."""
        if score >= 70:
            return "🔥"
        elif score >= 50:
            return "⚡"
        elif score >= 30:
            return "📊"
        return "📝"
