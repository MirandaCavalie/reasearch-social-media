Construye un agente en Python que se ejecute cada mañana a las 7:00 AM PST, recolecte las últimas noticias de AI, startups y tecnología de múltiples fuentes, las analice con Claude API, genere scripts listos para grabar en TikTok, y me envíe un briefing por email y Slack.

## CONTEXTO DEL PROYECTO

Soy un Data Scientist en San Francisco que quiere hacer la transición a AI Engineer. Quiero subir contenido de noticias de AI/tech a TikTok. Este agente debe hacer el research por mí cada mañana y entregarme todo listo para grabar.

Mi stack: Python, Node.js. Prefiero Python para este proyecto.

## ESTRUCTURA DEL PROYECTO
ai-news-agent/
├── main.py                    # Orquestador principal
├── config.yaml                # Configuración de fuentes, API keys, horarios
├── requirements.txt           # Dependencias
├── .env.example               # Template de variables de entorno
├── sources/
│   ├── init.py
│   ├── rss.py                 # Recolector de RSS feeds con feedparser
│   ├── hackernews.py          # Hacker News API (firebase)
│   ├── reddit.py              # Reddit via RSS (sin API key)
│   ├── arxiv.py               # ArXiv API para papers de AI/ML
│   ├── apify_twitter.py       # Apify actor para scraping de X/Twitter
│   └── influencers.py         # Tracker de contenido de influencers top de AI/tech
├── processor/
│   ├── init.py
│   ├── dedup.py               # Deduplicación por similitud de títulos
│   ├── ranker.py              # Ranking por relevancia y trending score
│   └── virality.py            # Estimador de potencial viral para público latino
├── llm/
│   ├── init.py
│   └── analyzer.py            # Claude API para análisis y generación de scripts
├── delivery/
│   ├── init.py
│   ├── email_sender.py        # Envío por Gmail SMTP
│   └── slack_sender.py        # Envío por Slack webhook
├── prompts/
│   └── system_prompt.md       # System prompt para Claude API
├── templates/
│   └── briefing.md            # Template del briefing en Markdown
└── README.md                  # Documentación del proyecto

## FUENTES DE DATOS (por orden de prioridad)

### 1. RSS Feeds (feedparser) — GRATIS, ESTABLE
Implementa recolección de estas fuentes con `feedparser`:
- TechCrunch AI: https://techcrunch.com/category/artificial-intelligence/feed/
- The Verge AI: https://www.theverge.com/rss/ai-artificial-intelligence/index.xml
- MIT Technology Review: https://www.technologyreview.com/feed/
- Anthropic Blog: https://www.anthropic.com/feed.xml
- OpenAI Blog: https://openai.com/blog/rss.xml
- Ars Technica: https://feeds.arstechnica.com/arstechnica/technology-lab
- TLDR AI Newsletter: https://tldr.tech/ai/rss
- The Batch (Andrew Ng): https://www.deeplearning.ai/the-batch/feed/

Para cada artículo extraer: título, URL, fecha de publicación, resumen/descripción, fuente.

### 2. Hacker News API — GRATIS, ESTABLE, SIN AUTH
Endpoint: https://hacker-news.firebaseio.com/v0/
- Usar /topstories.json para obtener los top 30 IDs
- Para cada ID, fetch /item/{id}.json
- Filtrar solo los que contengan keywords: AI, LLM, GPT, Claude, machine learning, neural, startup, YC, funding, launch
- Extraer: título, URL, score, número de comentarios

### 3. Reddit RSS — GRATIS, ESTABLE
Agregar .rss al final de URLs de subreddits:
- https://www.reddit.com/r/MachineLearning/hot/.rss
- https://www.reddit.com/r/LocalLLaMA/hot/.rss
- https://www.reddit.com/r/artificial/hot/.rss
- https://www.reddit.com/r/singularity/hot/.rss

Parsear con feedparser igual que los RSS normales.

### 4. ArXiv API — GRATIS, ESTABLE
Endpoint: http://export.arxiv.org/api/query
- Buscar papers de las últimas 24 horas en categorías: cs.AI, cs.LG, cs.CL
- Ordenar por fecha de envío (submittedDate)
- Tomar los top 10 por relevancia
- Extraer: título, autores, abstract, URL, categoría

### 5. Apify para X/Twitter — OPCIONAL, con créditos
Solo si la variable APIFY_TOKEN está configurada en .env.
Actor a usar: altimis/scweet (Scweet)
- Endpoint: https://api.apify.com/v2/acts/altimis~scweet/runs
- Buscar términos: "AI news", "LLM release", "startup funding", "tech launch"
- Máximo 50 tweets por búsqueda
- Extraer: texto del tweet, autor, engagement metrics, fecha
- Si Apify falla o no hay token, el agente debe continuar normalmente con las otras fuentes. NUNCA debe crashear por falta de Apify.

### 6. Influencer Tracker (influencers.py) — GRATIS vía RSS/Apify

El objetivo es monitorear qué están publicando los top influencers de AI/tech EN INGLÉS para detectar temas y formatos que yo pueda replicar/adaptar para audiencia latina en TikTok.

#### Influencers a trackear (configurable en config.yaml):

**TikTok/YouTube influencers de AI (trackear sus blogs/newsletters/RSS):**
- Riley Brown (@rileybrown.ai) — AI tools y tutorials
- Matt Wolfe (futuretools.io) — AI news y herramientas
- AI Jason (@AIJasonZ) — AI engineering tutorials
- Fireship (fireship.io) — Dev content, formato rápido
- Two Minute Papers (YouTube RSS) — Papers explicados
- Yannic Kilcher (YouTube RSS) — Deep dives en papers
- Andrej Karpathy — Blog/YouTube RSS

**X/Twitter influencers (trackear vía Apify si hay token):**
- @kaboron — AI agent updates
- @emaborovskis — AI research
- @DrJimFan — NVIDIA AI research
- @svpino — ML engineering
- @AndrewYNg — AI education
- @ylecun — Meta AI
- @sama — OpenAI
- @aaborovskis — AI startups

**Para blogs/YouTube:** Usar RSS feeds de sus canales y sitios.
**Para X/Twitter:** Usar Apify con el parámetro de handles específicos. Solo si hay token.

#### Qué extraer de cada influencer:
- Tema/tópico del post más reciente
- Formato usado (tutorial, hot take, news breakdown, comparison, listicle, story time)
- Engagement estimado (likes, views, comments si disponible)
- Hooks usados (primera línea o primeros 3 segundos)
- Hashtags usados

#### Output del tracker:
Una lista de "Content Signals" con:
ContentSignal:
influencer: str          # Nombre del influencer
platform: str            # tiktok, youtube, x, blog
topic: str               # Tema del contenido
format: str              # tutorial, news, hot_take, comparison, listicle
hook: str                # El hook o título que usaron
engagement: int          # Métrica de engagement si disponible
url: str                 # Link al contenido original
detected_at: datetime    # Cuándo se detectó

Estos ContentSignals se pasan a Claude API junto con las noticias para que los use como inspiración al generar scripts.

## PROCESAMIENTO

### Estimador de Viralidad (virality.py)

Cada artículo y cada ContentSignal debe recibir un "virality_score" de 0 a 100 que estima el potencial viral ESPECÍFICAMENTE para audiencia latina/hispana en TikTok.

#### Factores del virality_score:

**Factores positivos (suman puntos):**
- Tema controversial o que genera debate (+15): AI reemplazando trabajos, regulación, comparaciones de modelos
- Tiene ángulo personal/relatable (+20): "cómo esto te afecta", "lo que nadie te dice", historias personales
- Es novedad absoluta (+15): lanzamiento nuevo, funding, producto nuevo que nadie ha cubierto
- Tiene datos concretos y sorprendentes (+10): números, estadísticas, benchmarks que sorprendan
- El tema ya está trending en inglés pero NO en español (+25): ventana de oportunidad para ser el primero en español
- Se puede explicar en menos de 60 segundos (+10): simple y directo
- Tiene ángulo de San Francisco / Silicon Valley (+5): insider knowledge

**Factores negativos (restan puntos):**
- Demasiado técnico para audiencia general (-15): papers densos sin aplicación práctica
- Ya está saturado en español (-20): temas que ya cubrieron 10 creadores latinos
- Requiere contexto previo extenso (-10): no se entiende sin background
- Es solo una actualización menor (-10): patch notes, minor updates sin impacto real

#### Implementación:
- Usar keyword matching para detectar factores (listas de keywords por categoría en config.yaml)
- Para detectar si un tema ya está en español: buscar en los RSS de creadores de AI en español (opcional, mejora futura)
- El virality_score se agrega al Article dataclass y se usa en el ranking final

#### Cómo se integra con el ranking:
El ranking final combina:
- trending_score (ya existente) — peso: 40%
- virality_score — peso: 40%  
- influencer_signal (si un influencer top ya cubrió el tema en inglés) — peso: 20%

Los artículos con alto virality_score + señal de influencer + alto trending score son los que Claude API debe priorizar para los scripts.

### Deduplicación (dedup.py)
- Normalizar títulos: lowercase, remover puntuación, remover stopwords
- Usar similitud de Jaccard entre títulos (threshold 0.6)
- Si dos artículos son similares, quedarse con el de la fuente de mayor prioridad
- También deduplicar por URL exacta

### Ranking (ranker.py)
Asignar un "trending score" a cada artículo basado en:
- Recencia: artículos de las últimas 6 horas tienen bonus de 2x
- Menciones cruzadas: si el tema aparece en 2+ fuentes, bonus de 1.5x por fuente adicional
- Engagement (si disponible): HN score > 100 = bonus, Reddit upvotes si disponible
- Keywords de alto valor: "launch", "release", "funding", "open source", "breakthrough" = bonus 1.3x

El ranking final combina:
- trending_score — peso: 40%
- virality_score (de virality.py) — peso: 40%
- influencer_signal (si un influencer top ya cubrió el tema) — peso: 20%

Ordenar por score combinado descendente. Tomar los top 10.

## ANÁLISIS CON CLAUDE API (analyzer.py)

Usar el SDK de Anthropic (`anthropic` package).
Modelo: claude-sonnet-4-20250514
Max tokens: 4096

### System Prompt (guardarlo en prompts/system_prompt.md):

```markdown
Eres un content strategist experto en TikTok enfocado en AI, startups y tecnología. Vives en San Francisco y tu audiencia es gente tech-curious de habla hispana y bilingüe.

Tu superpoder: detectar qué contenido de AI/tech está funcionando en inglés y adaptarlo para la audiencia latina ANTES de que alguien más lo haga en español. Eres el puente entre Silicon Valley y Latinoamérica.

Tu trabajo es:
1. Analizar las noticias del día y seleccionar las 5 más relevantes e interesantes
2. Revisar los "Content Signals" de influencers top en inglés para detectar temas y formatos que están funcionando
3. Resumir cada noticia en 2-3 oraciones claras y accesibles
4. Generar 3 scripts completos para TikTok priorizando los temas con mayor potencial viral para audiencia latina

Al generar los scripts, considera los Content Signals de influencers:
- Si un influencer top ya cubrió un tema en inglés con alto engagement, ese tema tiene potencial COMPROBADO — adáptalo para público latino, no lo copies
- Observa los formatos que están funcionando (tutorial, hot take, comparison, listicle) y replica el formato, no el contenido
- Si un influencer usó un hook efectivo, inspírate en la estructura pero hazlo tuyo en español/Spanglish
- Prioriza temas que ya son virales en inglés pero que AÚN NO se han cubierto en español — esa ventana es oro

Para cada script de TikTok debes incluir:

**HOOK (primeros 3 segundos):** Una frase que detenga el scroll. Debe ser provocativa, curiosa o sorprendente. Ejemplos de estructura:
- "Esto va a cambiar cómo usas AI..."
- "Nadie está hablando de esto y es enorme..."
- "Acabo de enterarme de algo que tienes que saber..."
- "En Silicon Valley todos están hablando de esto..."
- "Los gringos ya están usando esto y en Latam nadie lo sabe..."

**CUERPO (30-45 segundos):** Explica la noticia de forma simple y directa. Usa analogías del mundo real. Evita jargon técnico excesivo. El tono es como si le contaras a un amigo inteligente pero no técnico. Incluye datos concretos cuando sea posible.

**CTA (últimos 5 segundos):** Call to action claro. Puede ser:
- Pregunta que invite a comentar
- "Sígueme para más noticias de AI"
- "Guarda este video para después"

**HASHTAGS:** 5-7 hashtags relevantes, mezcla de populares y nicho. Incluir hashtags en español Y en inglés para alcanzar ambas audiencias.

**FORMATO RECOMENDADO:** Indica qué formato de video funciona mejor para este script:
- 🗣️ Talking head (solo hablar a cámara)
- 📱 Screen recording + voz (mostrar la herramienta/producto)
- 📊 Green screen con imagen/gráfico de fondo
- ✂️ Duet/Stitch con el video original del influencer en inglés

**VIRALITY SCORE:** Incluir el virality_score estimado (0-100) de cada script y explicar brevemente POR QUÉ crees que tiene potencial viral.

**INSPIRACIÓN:** Si el script se inspiró en el contenido de un influencer específico, mencionarlo:
- "Inspirado en: @mattvolfe cubrió esto ayer con 500K views. Tu ángulo: ser el primero en explicarlo en español"

**FORMATO DE TEXTO:** Marca las pausas dramáticas con [PAUSA]. Marca cambios de tono con [ÉNFASIS]. Esto ayuda al momento de grabar.

Reglas de estilo:
- NO seas cringe. Nada de "¡ESTO ES INCREÍBLE!" o hipérboles innecesarias
- Sé conversacional, como si hablaras con un amigo
- Mezcla español e inglés naturalmente (Spanglish de SF)
- Sé específico, no genérico. Nombres, números, fechas
- Si una noticia tiene ángulo de San Francisco (compañía local, evento, etc.), resáltalo
- Piensa siempre: "¿esto le importa a alguien en CDMX, Bogotá, o Buenos Aires?" — si solo importa en SF, necesitas un ángulo universal
```

### Input al LLM:
Pasar las top 10 noticias rankeadas Y los Content Signals de influencers en formato estructurado:
=== NOTICIAS DEL DÍA ===
Noticia 1:

Título: ...
Fuente: ...
Fecha: ...
Resumen: ...
URL: ...
Trending Score: ...
Virality Score: .../100
Factores de viralidad: ...

Noticia 2:
...
=== CONTENT SIGNALS DE INFLUENCERS (últimas 24h) ===
Signal 1:

Influencer: @mattwolfe
Plataforma: YouTube
Tema: "New AI tool replaces Photoshop"
Formato: tutorial / demo
Hook: "This free AI tool just killed Photoshop"
Engagement: 450K views
URL: ...

Signal 2:
...

### Output esperado:
Parsear la respuesta de Claude para extraer:
- Las 5 noticias seleccionadas con resúmenes
- Los 3 scripts de TikTok completos (con virality score, formato recomendado, e inspiración de influencer)
- Para cada script: por qué se eligió ese tema y qué ventana de oportunidad hay en español

## ENTREGA

### Email (email_sender.py)
Usar `smtplib` con Gmail SMTP.
- Host: smtp.gmail.com
- Port: 587
- Requiere: GMAIL_USER y GMAIL_APP_PASSWORD en .env
- Subject: "🎬 Tu briefing de AI — {fecha de hoy}"
- Body: HTML formateado con:
  - Sección 1: Top 5 noticias con resúmenes y virality score
  - Sección 2: Los 3 scripts de TikTok con formato recomendado y virality score
  - Sección 3: "Qué están publicando los influencers" — resumen de Content Signals relevantes
  - Sección 4: "Ventanas de oportunidad" — temas virales en inglés que AÚN no se han cubierto en español
- Incluir links a las fuentes originales y a los videos/posts de influencers

### Slack (slack_sender.py)
Usar un Slack webhook.
- Requiere: SLACK_WEBHOOK_URL en .env
- Enviar un mensaje formateado con Slack Block Kit
- Sección 1: Top 5 noticias con links y virality score (🔥 para score > 70, ⚡ para > 50)
- Sección 2: Los 3 scripts de TikTok con formato recomendado
- Sección 3: "Influencer Radar" — qué publicaron los top influencers ayer
- Si el webhook no está configurado, skip silenciosamente

## CONFIGURACIÓN

### .env.example:
Requerido
ANTHROPIC_API_KEY=sk-ant-...
Email (opcional)
GMAIL_USER=tu@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
Slack (opcional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
Apify para X/Twitter (opcional)
APIFY_TOKEN=apify_api_...
Configuración
TIMEZONE=America/Los_Angeles
RUN_HOUR=7
RUN_MINUTE=0

### config.yaml:
Contener todas las URLs de RSS, subreddits, keywords de filtrado, y parámetros de ranking configurables sin tocar código.

## ORQUESTACIÓN (main.py)

El main.py debe:
1. Cargar configuración de .env y config.yaml
2. Ejecutar todas las fuentes en paralelo con asyncio o concurrent.futures
3. Agregar todos los resultados en una lista unificada
4. Deduplicar
5. Rankear
6. Enviar top 10 a Claude API
7. Parsear la respuesta
8. Enviar por email y Slack
9. Logging completo con `logging` module — cada paso debe loguearse
10. Manejar errores gracefully — si una fuente falla, continuar con las demás
11. Imprimir un resumen al final: cuántas noticias recolectadas, deduplicadas, enviadas

Incluir un modo `--dry-run` que hace todo excepto enviar el email/Slack (imprime en consola).
Incluir un modo `--source rss` para correr solo una fuente específica (útil para debugging).

## REQUIREMENTS.TXT
anthropic>=0.40.0
feedparser>=6.0.0
requests>=2.31.0
pyyaml>=6.0
python-dotenv>=1.0.0
schedule>=1.2.0

## README.md

Incluir:
- Descripción del proyecto
- Arquitectura (diagrama ASCII simple)
- Setup paso a paso (clonar, instalar deps, configurar .env)
- Cómo correrlo manualmente: `python main.py`
- Cómo correrlo en dry-run: `python main.py --dry-run`
- Cómo hacer deploy con cron o con schedule
- Costos estimados ($5-10/mes)
- Troubleshooting común

## RESTRICCIONES TÉCNICAS

- Python 3.10+
- No usar frameworks pesados (no LangChain, no CrewAI). Solo librerías simples.
- No usar base de datos. Guardar estado mínimo en archivos JSON si es necesario.
- Cada módulo debe ser testeable de forma independiente
- Usar type hints en todas las funciones
- Usar dataclasses o Pydantic para los modelos de datos (Article, ContentSignal, Script, Briefing)
  - Article debe incluir: title, url, source, published_at, summary, trending_score, virality_score, virality_factors
  - ContentSignal debe incluir: influencer, platform, topic, format, hook, engagement, url, detected_at
  - Script debe incluir: hook, body, cta, hashtags, recommended_format, virality_score, virality_reasoning, inspired_by
- Manejar timeouts en todas las llamadas HTTP (30 segundos max)
- El agente completo no debe tardar más de 3 minutos en ejecutarse
- Logging a stdout con formato: [TIMESTAMP] [LEVEL] [MODULE] mensaje

## TESTING

Crear un archivo test_sources.py que pruebe cada fuente individualmente:
- test_rss(): verificar que feedparser retorna artículos
- test_hackernews(): verificar que HN API responde
- test_reddit(): verificar que Reddit RSS funciona
- test_arxiv(): verificar que ArXiv retorna papers
- test_apify(): verificar conexión con Apify (skip si no hay token)
- test_influencers(): verificar que los RSS de influencers retornan contenido
- test_virality(): verificar que el virality scorer asigna scores correctos con datos de ejemplo
- test_ranking(): verificar que el ranking combinado (trending + virality + influencer signal) ordena correctamente

## IMPORTANTE

- Empieza por crear la estructura de archivos completa
- Implementa cada módulo uno por uno, testeando que funcione
- El agente debe ser robusto: si Twitter/Apify falla, las otras fuentes siguen
- Prioriza que funcione end-to-end antes de optimizar
- Usa f-strings, no .format()
- Comenta el código en español