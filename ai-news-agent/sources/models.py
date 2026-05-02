"""
Modelos de datos del proyecto AI News Agent.

Define las dataclasses principales que se usan en todo el pipeline:
Article, ContentSignal, Script y Briefing.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    """Representa un articulo o noticia recolectada de cualquier fuente."""

    title: str
    url: str
    source: str
    published_at: datetime
    summary: str = ""
    trending_score: float = 0.0
    virality_score: float = 0.0
    virality_factors: list[str] = field(default_factory=list)
    engagement: int = 0
    # Para tracking de menciones cruzadas entre fuentes
    cross_mentions: int = 0


@dataclass
class ContentSignal:
    """Representa una senal de contenido detectada de un influencer."""

    influencer: str
    platform: str  # tiktok, youtube, x, blog
    topic: str
    format: str  # tutorial, news, hot_take, comparison, listicle
    hook: str
    engagement: int = 0
    url: str = ""
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class Script:
    """Representa un script generado para TikTok."""

    title: str = ""
    hook: str = ""
    body: str = ""
    cta: str = ""
    hashtags: list[str] = field(default_factory=list)
    recommended_format: str = ""
    virality_score: float = 0.0
    virality_reasoning: str = ""
    inspired_by: str = ""


@dataclass
class Briefing:
    """Representa el briefing completo generado para el dia."""

    date: str = ""
    top_news: list[Article] = field(default_factory=list)
    scripts: list[Script] = field(default_factory=list)
    content_signals: list[ContentSignal] = field(default_factory=list)
    raw_analysis: str = ""
