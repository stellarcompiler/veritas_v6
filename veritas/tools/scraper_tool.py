from crewai_tools import tool
import requests
import trafilatura
from newspaper import Article, Config as NewspaperConfig
from readability import Document
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil.parser import parse as parse_date
import json
import re

# ---------------- CONFIG ---------------- #

TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

MIN_CONTENT_LENGTH = 200
MAX_CONTENT_CHARS = 2500     # HARD CAP for agent context safety
MIN_TRUNCATED_CHARS = 800    # Avoid useless stubs

# --------------------------------------- #

@tool("web_scraper_tool")
def web_scraper_tool(url: str) -> dict:
    """
    CrewAI-safe web scraper with context-token protection.
    Returns TRUNCATED article content optimized for LLM agents.
    """

    def error(msg: str):
        return {
            "url": url,
            "scraped_successfully": False,
            "error": msg,
            "timestamp": datetime.utcnow().isoformat()
        }

    if not url or not url.startswith(("http://", "https://")):
        return error("Invalid URL")

    # -------- FETCH HTML -------- #
    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return error(f"Fetch failed: {e}")

    # -------- LEVEL 1: TRAFILATURA -------- #
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            with_metadata=True,
            output_format="json",
            favor_recall=True
        )

        if extracted:
            data = json.loads(extracted)
            content = data.get("text", "")

            if len(content) >= MIN_CONTENT_LENGTH:
                content = truncate_content(content)

                return {
                    "url": url,
                    "scraped_successfully": True,
                    "title": data.get("title", ""),
                    "content": content,
                    "author": data.get("author", ""),
                    "date": normalize_date(data.get("date")),
                    "source": data.get("sitename", ""),
                    "content_truncated": True,
                    "method": "trafilatura",
                    "timestamp": datetime.utcnow().isoformat()
                }
    except Exception:
        pass

    # -------- LEVEL 2: NEWSPAPER3K -------- #
    try:
        cfg = NewspaperConfig()
        cfg.browser_user_agent = USER_AGENT
        cfg.request_timeout = TIMEOUT

        article = Article(url, config=cfg)
        article.download()
        article.parse()

        if article.text and len(article.text) >= MIN_CONTENT_LENGTH:
            content = truncate_content(article.text)

            return {
                "url": url,
                "scraped_successfully": True,
                "title": article.title,
                "content": content,
                "author": ", ".join(article.authors),
                "date": normalize_date(article.publish_date),
                "source": article.source_url,
                "content_truncated": True,
                "method": "newspaper3k",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception:
        pass

    # -------- LEVEL 3: READABILITY -------- #
    try:
        doc = Document(html)
        soup = BeautifulSoup(doc.summary(), "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        if len(text) >= MIN_CONTENT_LENGTH:
            content = truncate_content(text)

            return {
                "url": url,
                "scraped_successfully": True,
                "title": doc.title(),
                "content": content,
                "author": "",
                "date": "",
                "source": "",
                "content_truncated": True,
                "method": "readability",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception:
        pass

    return error("Content extraction failed")


# ---------------- HELPERS ---------------- #

def truncate_content(text: str) -> str:
    """
    Truncate content intelligently:
    - Prefer paragraph boundaries
    - Preserve sentence completeness
    - Enforce hard token-safe cap
    """

    text = clean_text(text)

    if len(text) <= MAX_CONTENT_CHARS:
        return text

    paragraphs = re.split(r"\n{2,}", text)
    collected = []

    total_len = 0
    for p in paragraphs:
        if total_len + len(p) > MAX_CONTENT_CHARS:
            break
        collected.append(p)
        total_len += len(p)

        if total_len >= MIN_TRUNCATED_CHARS:
            break

    truncated = "\n\n".join(collected)

    # Final sentence-safe trim
    if len(truncated) > MAX_CONTENT_CHARS:
        truncated = truncated[:MAX_CONTENT_CHARS]
        truncated = re.sub(r"[.!?]\s+[^.!?]*$", ".", truncated)

    return truncated.strip()


def clean_text(text: str) -> str:
    """Lightweight cleanup before truncation"""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def normalize_date(date_val):
    if not date_val:
        return ""
    try:
        if isinstance(date_val, str):
            return parse_date(date_val, fuzzy=True).isoformat()
        return date_val.isoformat()
    except Exception:
        return ""
