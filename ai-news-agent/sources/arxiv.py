"""
Recolector de papers desde la API de ArXiv.

Consulta la API Atom de ArXiv para obtener los papers mas recientes
en categorias de AI/ML (cs.AI, cs.LG, cs.CL), parsea la respuesta
XML y retorna una lista de Article.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from sources.models import Article

# Configuracion del logger con formato estandar del proyecto
logger = logging.getLogger(__name__)

# Timeout global para peticiones HTTP en segundos
HTTP_TIMEOUT: int = 30

# Namespace de Atom usado por ArXiv en sus respuestas XML
ARXIV_ATOM_NS: str = "http://www.w3.org/2005/Atom"

# URL base de la API de ArXiv
ARXIV_API_URL: str = "http://export.arxiv.org/api/query"


def _clean_whitespace(text: str) -> str:
    """Limpia espacios en blanco excesivos de un texto.

    Reemplaza saltos de linea y multiples espacios por un solo espacio.

    Args:
        text: Texto a limpiar.

    Returns:
        Texto limpio sin saltos de linea ni espacios duplicados.
    """
    # Reemplazar saltos de linea y tabs por espacios
    text = re.sub(r"[\n\r\t]+", " ", text)
    # Colapsar multiples espacios en uno solo
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _build_search_query(categories: list[str]) -> str:
    """Construye el parametro search_query para la API de ArXiv.

    Combina las categorias con operador OR para buscar papers
    que pertenezcan a cualquiera de las categorias especificadas.

    Args:
        categories: Lista de categorias de ArXiv (ej: ["cs.AI", "cs.LG", "cs.CL"]).

    Returns:
        String con la query formateada para la API (ej: "cat:cs.AI+OR+cat:cs.LG").
    """
    # Cada categoria se envuelve con el prefijo "cat:"
    cat_terms: list[str] = [f"cat:{cat}" for cat in categories]
    # Unir con " OR " — requests se encarga de URL-encode correctamente
    return " OR ".join(cat_terms)


def _parse_published_date(date_str: str) -> datetime:
    """Parsea una fecha ISO 8601 de ArXiv a datetime.

    ArXiv usa formato como "2026-04-30T18:00:00Z".

    Args:
        date_str: Fecha en formato ISO 8601.

    Returns:
        Datetime con timezone UTC. Si falla el parseo, retorna datetime.now(UTC).
    """
    if not date_str:
        return datetime.now(tz=timezone.utc)

    try:
        # Intentar parsear formato ISO 8601 con Z al final
        clean_date: str = date_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean_date)
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parseando fecha de ArXiv '{date_str}': {e}")
        return datetime.now(tz=timezone.utc)


def _extract_authors(entry: ET.Element) -> str:
    """Extrae y une los nombres de los autores de un entry de ArXiv.

    Args:
        entry: Elemento XML <entry> del response de ArXiv.

    Returns:
        String con los nombres de los autores separados por coma.
    """
    authors: list[str] = []

    for author_elem in entry.findall(f"{{{ARXIV_ATOM_NS}}}author"):
        name_elem = author_elem.find(f"{{{ARXIV_ATOM_NS}}}name")
        if name_elem is not None and name_elem.text:
            authors.append(name_elem.text.strip())

    return ", ".join(authors)


def _extract_primary_link(entry: ET.Element) -> str:
    """Extrae el link principal (pagina del paper) de un entry de ArXiv.

    Busca el tag <id> que contiene la URL canonica del paper.
    Tambien revisa los tags <link> como fallback.

    Args:
        entry: Elemento XML <entry> del response de ArXiv.

    Returns:
        URL del paper, o cadena vacia si no se encuentra.
    """
    # El tag <id> contiene la URL canonica del paper (ej: http://arxiv.org/abs/2406.12345v1)
    id_elem = entry.find(f"{{{ARXIV_ATOM_NS}}}id")
    if id_elem is not None and id_elem.text:
        return id_elem.text.strip()

    # Fallback: buscar en los tags <link>
    for link_elem in entry.findall(f"{{{ARXIV_ATOM_NS}}}link"):
        link_type: str = link_elem.get("type", "")
        link_rel: str = link_elem.get("rel", "")
        if link_type == "text/html" or link_rel == "alternate":
            href: str = link_elem.get("href", "")
            if href:
                return href

    return ""


def _extract_category(entry: ET.Element) -> str:
    """Extrae la categoria principal de un entry de ArXiv.

    Busca el tag <category> con el namespace de ArXiv.
    Tambien busca en el namespace de Atom como fallback.

    Args:
        entry: Elemento XML <entry> del response de ArXiv.

    Returns:
        Nombre de la categoria (ej: "cs.AI"), o "unknown" si no se encuentra.
    """
    # Buscar tags <category> con atributo term (namespace ArXiv o Atom)
    # ArXiv usa el namespace de Atom para las categorias
    for cat_elem in entry.findall(f"{{{ARXIV_ATOM_NS}}}category"):
        term: str = cat_elem.get("term", "")
        if term:
            return term

    return "unknown"


def fetch_arxiv_articles(config: dict) -> list[Article]:
    """Recolecta papers recientes desde la API de ArXiv.

    Consulta la API de ArXiv buscando papers en las categorias configuradas,
    ordenados por fecha de envio descendente. Parsea la respuesta XML (Atom)
    y crea un Article por cada paper encontrado.

    Args:
        config: Diccionario de configuracion con claves:
            - 'categories': Lista de categorias ArXiv (ej: ["cs.AI", "cs.LG", "cs.CL"])
            - 'max_results': Numero maximo de papers a retornar (default: 10)

    Returns:
        Lista de Article con los papers recolectados.
    """
    # Extraer parametros de configuracion
    categories: list[str] = config.get("categories", ["cs.AI", "cs.LG", "cs.CL"])
    max_results: int = config.get("max_results", 10)

    # Construir la query de busqueda
    search_query: str = _build_search_query(categories)

    # Parametros de la peticion a la API
    params: dict = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }

    logger.info(
        f"Consultando ArXiv API: categorias={categories}, max_results={max_results}"
    )

    articles: list[Article] = []

    try:
        # Realizar la peticion HTTP con timeout
        response = requests.get(
            ARXIV_API_URL,
            params=params,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": "AINewsAgent/1.0 (Python; ArXiv client)"},
        )
        response.raise_for_status()

        # Parsear la respuesta XML
        root: ET.Element = ET.fromstring(response.content)

        # Buscar todos los elementos <entry> en el namespace Atom
        entries: list[ET.Element] = root.findall(f"{{{ARXIV_ATOM_NS}}}entry")

        if not entries:
            logger.warning("ArXiv API no retorno ningun paper")
            return articles

        for entry in entries:
            # Extraer titulo — campo obligatorio
            title_elem = entry.find(f"{{{ARXIV_ATOM_NS}}}title")
            title: str = ""
            if title_elem is not None and title_elem.text:
                title = _clean_whitespace(title_elem.text)

            if not title:
                continue

            # Extraer link del paper
            url: str = _extract_primary_link(entry)
            if not url:
                continue

            # Extraer abstract/summary
            summary_elem = entry.find(f"{{{ARXIV_ATOM_NS}}}summary")
            summary: str = ""
            if summary_elem is not None and summary_elem.text:
                summary = _clean_whitespace(summary_elem.text)
                # Limitar longitud del abstract a 500 caracteres
                if len(summary) > 500:
                    summary = summary[:497] + "..."

            # Extraer autores
            authors: str = _extract_authors(entry)

            # Agregar autores al resumen si hay espacio
            if authors and summary:
                summary = f"Autores: {authors}. {summary}"
            elif authors:
                summary = f"Autores: {authors}"

            # Extraer fecha de publicacion
            published_elem = entry.find(f"{{{ARXIV_ATOM_NS}}}published")
            published_str: str = ""
            if published_elem is not None and published_elem.text:
                published_str = published_elem.text
            published_at: datetime = _parse_published_date(published_str)

            # Extraer categoria
            category: str = _extract_category(entry)

            # Crear el Article con fuente "ArXiv"
            article = Article(
                title=title,
                url=url,
                source=f"ArXiv ({category})",
                published_at=published_at,
                summary=summary,
            )
            articles.append(article)

        logger.info(f"ArXiv: {len(articles)} papers recolectados de {len(entries)} entries")

    except requests.exceptions.Timeout:
        logger.error(f"Timeout al consultar ArXiv API ({HTTP_TIMEOUT}s)")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error HTTP al consultar ArXiv API: {e}")
    except ET.ParseError as e:
        logger.error(f"Error parseando XML de ArXiv: {e}")
    except Exception as e:
        logger.error(f"Error inesperado al procesar ArXiv: {e}")

    return articles
