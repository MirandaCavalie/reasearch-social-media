# AI News Agent

Agente automatizado que recolecta noticias de AI/tech cada manana, las analiza con Claude API, y genera scripts listos para grabar en TikTok. Envia un briefing por email y Slack.

## Arquitectura

```
                    +------------------+
                    |    main.py       |
                    |  (orquestador)   |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v------+ +-----v-------+
     |  sources/   |  | processor/  | |    llm/      |
     |  (6 fuentes)|  | dedup       | | analyzer.py  |
     |  rss        |  | virality    | | (Claude API) |
     |  hackernews |  | ranker      | +--------------+
     |  reddit     |  +-------------+        |
     |  arxiv      |                  +------v------+
     |  twitter    |                  |  delivery/  |
     |  influencers|                  |  email      |
     +-----------  +                  |  slack      |
                                      +-------------+
```

**Flujo:**
1. Recolecta de 6 fuentes en paralelo (RSS, HN, Reddit, ArXiv, Twitter, Influencers)
2. Deduplica por URL y similitud de titulo
3. Calcula virality score para audiencia latina
4. Rankea combinando trending + virality + influencer signal
5. Envia top 10 a Claude API para analisis y generacion de scripts
6. Entrega briefing por email y Slack

## Setup

### 1. Clonar e instalar

```bash
cd ai-news-agent
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

**Requerido:**
- `ANTHROPIC_API_KEY` — Tu API key de Anthropic

**Opcional:**
- `GMAIL_USER` + `GMAIL_APP_PASSWORD` — Para envio por email
- `SLACK_WEBHOOK_URL` — Para envio a Slack
- `APIFY_TOKEN` — Para recolectar de X/Twitter

### 3. Configurar fuentes

Edita `config.yaml` para ajustar RSS feeds, subreddits, keywords, y parametros de ranking.

## Uso

### Ejecucion manual

```bash
# Ejecucion completa
python main.py

# Dry run (no envia email/Slack, imprime en consola)
python main.py --dry-run

# Solo una fuente (para debugging)
python main.py --source rss
python main.py --source hackernews
python main.py --source reddit
python main.py --source arxiv
python main.py --source twitter

# Modo scheduler (ejecuta diariamente a las 7:00 AM)
python main.py --schedule
```

### Tests

```bash
# Correr todos los tests
python test_sources.py

# Test individual
python test_sources.py test_rss
python test_sources.py test_virality
python test_sources.py test_ranking
```

## Deploy con cron

Para ejecutar cada dia a las 7:00 AM PST:

```bash
# Editar crontab
crontab -e

# Agregar (ajusta las rutas):
0 7 * * * cd /path/to/ai-news-agent && /path/to/venv/bin/python main.py >> /var/log/ai-news-agent.log 2>&1
```

## Costos estimados

- **Claude API**: ~$3-8/mes (1 llamada diaria con claude-sonnet-4-20250514)
- **Apify** (opcional): ~$0-5/mes con plan gratuito
- **Total**: ~$5-10/mes

## Troubleshooting

| Problema | Solucion |
|----------|----------|
| `ANTHROPIC_API_KEY not configured` | Configura tu API key en `.env` |
| `Gmail authentication error` | Usa un App Password, no tu contrasena normal |
| `Timeout al descargar feed` | Algunos feeds son lentos. Aumenta `HTTP_TIMEOUT` en el modulo |
| `Reddit retorna 429` | Reddit rate-limita. Espera unos minutos |
| `Apify falla` | Es opcional. El agente continua con las otras fuentes |
| `No se obtuvieron articulos` | Verifica tu conexion a internet y los URLs en config.yaml |
