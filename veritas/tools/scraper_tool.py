import json
import re
import random
from typing import Dict, Optional
from urllib.parse import urlparse
from crewai_tools import tool
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from veritas.config import logger
from app.services.telemetry import log_event

# --- Configuration Constants ---
TIMEOUT = 15  # Slightly increased to allow for redirects/handshakes
MAX_CONTENT_LENGTH = 25000  # Cap purely to prevent context window overflow
MIN_CONTENT_LENGTH = 250  # Threshold to consider a scrape failed

# Common browser agents to rotate (Anti-blocking strategy)
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
]

@tool("web_scraper_tool")
def web_scraper_tool(url: str, job_id: str) -> str:
    """
    BATTLE-TESTED web scraper for news articles using multi-strategy extraction.
    
    Strategies (in priority order):
    1. JSON-LD (Schema.org): Extracts structured data provided for Google News.
    2. Semantic Extraction: Targets specific HTML5 <article> tags.
    3. Density Scoring: Algorithms to identify the cluster of text with highest paragraph density.
    
    Input: Valid news article URL
    Output: JSON string with url, source, author, date, content, scraped_successfully
    """
    # 1. Strict Input Validation
    if not url or not isinstance(url, str):
        return _json_error("No URL provided")
    
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return _json_error(f"Invalid protocol: {url}", url)

    logger.info(f"Initiating scrape: {url}")
    log_event(
        job_id= job_id,
        source= "Web-Scraping-Tool",
        event_type= "START",
        message="Initiating DOM Content Scrape on URLs",
        meta={"URL" : url}
    )

    # 2. Network Request (with exponential backoff & rotation)
    session = _create_resilient_session()
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',  # Do Not Track
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }

    try:
        response = session.get(url, headers=headers, timeout=TIMEOUT, verify=False) # verify=False for broader compatibility
        response.raise_for_status()
        
        # Auto-detect encoding if headers are wrong (fixes garbled text)
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding
            
    except Exception as e:
        logger.error(f"Network error for {url}: {e}")
        log_event(
        job_id= job_id,
        source= "Web-Scraping-Tool",
        event_type= "Failed",
        message="Network Error for URL",
        meta={"URL" : url}
    )
        return _json_error(f"Network failed: {str(e)}", url)

    # 3. HTML Parsing
    try:
        # 'lxml' is faster/better if available, fallback to 'html.parser'
        # We assume standard env, so sticking to html.parser for compatibility as requested
        soup = BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        log_event(
        job_id= job_id,
        source= "Web-Scraping-Tool",
        event_type= "Failed",
        message="HTML Parsing Failed - BS4 ",
        meta={"URL" : url}
    )
        return _json_error(f"Parsing failed: {str(e)}", url)

    # 4. DATA EXTRACTION PIPELINE
    
    # Metadata (Optimized)
    metadata = _extract_metadata(soup, url)
    
    # Content Strategy 1: JSON-LD (The Gold Standard)
    content = _extract_json_ld(soup)
    extraction_method = "json-ld"
    
    # Content Strategy 2: Semantic & Density Fallback
    if not content or len(content) < MIN_CONTENT_LENGTH:
        # Clean the DOM before heuristic analysis
        _cleanup_dom(soup)
        content = _extract_content_heuristic(soup)
        extraction_method = "heuristic"

    # 5. Final Validation & Cleaning
    content = _clean_text_final(content)
    content_len = len(content)
    
    success = content_len >= MIN_CONTENT_LENGTH
    
    if success:
        logger.info(f"Scraped {url} via {extraction_method} ({content_len} chars)")
    else:
        logger.warning(f"Scrape low confidence {url}: only {content_len} chars found")

    log_event(
        job_id= job_id,
        source= "Web-Scraping-Tool",
        event_type= "END",
        message="Suceeded : DOM Content Scrape on URL Successful",
        meta={"URL" : url}
    )
    result = {
        "url": url,
        "source": metadata['source'],
        "author": metadata['author'],
        "date": metadata['date'],
        "content": content if success else None,
        "scraped_successfully": success,
        "meta": {
            "method": extraction_method,
            "length": content_len,
            "title": metadata['title']
        }
    }
    
    return json.dumps(result, indent=2, ensure_ascii=False)


# --- Core Logic Helpers ---

def _create_resilient_session() -> requests.Session:
    """Creates a session with automatic retries for connection errors."""
    session = requests.Session()
    # Retry on: 500, 502, 503, 504 errors + connection breaks
    retries = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def _extract_json_ld(soup: BeautifulSoup) -> Optional[str]:
    """
    Strategy 1: Check for Schema.org 'Article' or 'NewsArticle' JSON.
    This bypasses HTML parsing issues entirely.
    """
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.get_text())
            # Normalize to list to handle single objects
            if isinstance(data, dict):
                data = [data]
            
            for entry in data:
                if not isinstance(entry, dict): continue
                
                dtype = entry.get('@type', '')
                if isinstance(dtype, list): dtype = dtype[0] # handle list types
                
                if dtype in ['Article', 'NewsArticle', 'BlogPosting']:
                    # Return articleBody if present
                    if 'articleBody' in entry:
                        return entry['articleBody']
        except:
            continue
    return None

def _extract_content_heuristic(soup: BeautifulSoup) -> str:
    """
    Strategy 2 & 3: Semantic Targeting + Density Scoring.
    Finds the HTML node with the highest concentration of text.
    """
    
    # 2a. Target common main content wrappers directly
    best_text = ""
    
    # Priority tags
    candidates = soup.find_all(['article', 'main'])
    
    # Priority classes (regex)
    content_patterns = re.compile(r'(article|post|story|main|content|body-text)', re.I)
    div_candidates = soup.find_all('div', class_=content_patterns)
    
    all_candidates = list(candidates) + list(div_candidates)
    
    if not all_candidates:
        # Fallback: scan URL for all paragraphs if no container found
        all_candidates = [soup]

    best_score = 0
    best_node = None

    # Score each candidate
    for node in all_candidates:
        # Count high-quality paragraphs (must have some length, not just links)
        paragraphs = node.find_all('p', recursive=True)
        score = 0
        current_text = []
        
        for p in paragraphs:
            txt = p.get_text(strip=True)
            if len(txt) > 50: # Threshold for "real" sentence
                score += len(txt)
                current_text.append(txt)
                
            # Penalize if it contains too many links (link density)
            links = p.find_all('a')
            if links:
                link_len = sum(len(a.get_text(strip=True)) for a in links)
                if link_len > len(txt) * 0.5: # Over 50% link text? Probably navigation/sidebar
                    score -= len(txt) 

        if score > best_score:
            best_score = score
            best_node = current_text

    if best_node:
        return "\n\n".join(best_node)
    
    # Last resort: just grab all P tags from body
    body_ps = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 60]
    return "\n\n".join(body_ps)

def _cleanup_dom(soup: BeautifulSoup):
    """Mutates soup to remove non-content elements before extraction."""
    # 1. Decompose specific tags
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 
                     'noscript', 'iframe', 'svg', 'form', 'button', 'input']):
        tag.decompose()
        
    # 2. Decompose by class/id patterns (Ads, Sidebars, Promos)
    noise_pattern = re.compile(r'(ad-|banner|promo|social|sidebar|menu|popup|subscribe|newsletter|cookie)', re.I)
    
    # Be careful not to delete 'article-body' or 'main-content' when deleting 'content-ad'
    for tag in soup.find_all(attrs={'class': noise_pattern}):
        # Safety check: Don't delete if it looks like main content
        id_str = str(tag.get('id', ''))
        class_str = str(tag.get('class', ''))
        if 'main' in class_str or 'article' in class_str or 'story' in class_str:
            continue
        tag.decompose()

def _extract_metadata(soup: BeautifulSoup, url: str) -> Dict:
    """Extracts meta fields with high reliability."""
    meta = {
        "title": "",
        "author": "Unknown",
        "date": "Unknown",
        "source": urlparse(url).netloc.replace("www.", "")
    }
    
    # Title
    og_title = soup.find("meta", property="og:title")
    if og_title: meta['title'] = og_title.get("content", "")
    else: 
        t = soup.find("title")
        if t: meta['title'] = t.get_text(strip=True)

    # Author (Hierarchy)
    meta_authors = [
        ("meta", {"name": "author"}),
        ("meta", {"property": "article:author"}),
        ("a", {"rel": "author"}),
        ("span", {"class": re.compile(r'author', re.I)})
    ]
    for tag, attrs in meta_authors:
        elem = soup.find(tag, attrs)
        if elem:
            txt = elem.get("content") or elem.get_text(strip=True)
            if txt and len(txt) < 50:
                meta['author'] = txt
                break
    
    # Date (Hierarchy)
    meta_dates = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "date"}),
        ("time", {})
    ]
    for tag, attrs in meta_dates:
        elem = soup.find(tag, attrs)
        if elem:
            date_str = elem.get("content") or elem.get("datetime")
            if date_str:
                meta['date'] = date_str
                break
                
    return meta

def _clean_text_final(text: str) -> str:
    """Post-processing text cleanup."""
    if not text: return ""
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common boilerplate phrases that survive DOM cleaning
    patterns_to_remove = [
        r'Share this article',
        r'Click here to read',
        r'Follow us on',
        r'Sign up for',
        r'All rights reserved',
        r'Copyright \d{4}'
    ]
    for pat in patterns_to_remove:
        text = re.sub(pat, '', text, flags=re.I)
        
    return text.strip()

def _json_error(msg: str, url: str = None) -> str:
    return json.dumps({
        "error": msg,
        "url": url,
        "scraped_successfully": False
    })

# import json
# import re
# import time
# from typing import Dict
# from urllib.parse import urlparse
# from crewai_tools import tool
# import requests
# from bs4 import BeautifulSoup
# from veritas.config import Config, logger

# # Optimized retry configuration
# MAX_RETRIES = 1  # Only 1 retry (2 total attempts)
# RETRY_DELAY = 1  # seconds
# TIMEOUT = 12  # Reduced from 20s to 12s

# @tool("web_scraper_tool")
# def web_scraper_tool(url: str) -> str:
#     """
#     OPTIMIZED web scraper for news articles using requests + BeautifulSoup.
    
#     Optimizations:
#     - Fast html.parser (no lxml dependency)
#     - 12s timeout (balanced speed/reliability)
#     - 1 retry (2 total attempts max)
#     - Top 3 content extraction strategies only
#     - Streamlined metadata extraction
#     - Efficient single-pass text cleaning
    
#     Input: Valid news article URL
#     Output: JSON with url, source, author, date, content, scraped_successfully
#     """
#     # Input validation
#     if not url or not url.strip():
#         return json.dumps({
#             "error": "No URL provided",
#             "url": None,
#             "content": None,
#             "scraped_successfully": False
#         })
    
#     url = url.strip()
    
#     if not url.startswith(('http://', 'https://')):
#         return json.dumps({
#             "error": "Invalid URL format",
#             "url": url,
#             "content": None,
#             "scraped_successfully": False
#         })
    
#     if len(url) > 2000:
#         return json.dumps({
#             "error": "URL too long",
#             "url": url[:100] + "...",
#             "content": None,
#             "scraped_successfully": False
#         })
    
#     logger.info(f"Scraping: {url}")
    
#     # Attempt scraping with retry
#     last_error = None
#     for attempt in range(MAX_RETRIES + 1):
#         try:
#             if attempt > 0:
#                 logger.info(f"Retry {attempt}/{MAX_RETRIES}")
#                 time.sleep(RETRY_DELAY)
            
#             result = _scrape_fast(url)
            
#             if result.get('scraped_successfully'):
#                 return json.dumps(result, indent=2, ensure_ascii=False)
#             else:
#                 last_error = result.get('error', 'Unknown error')
                
#         except KeyboardInterrupt:
#             raise
#         except Exception as e:
#             last_error = str(e)
#             logger.error(f"Attempt {attempt + 1} failed: {e}")
    
#     # All attempts failed
#     logger.error(f"All scraping attempts failed for {url}")
#     return json.dumps({
#         "url": url,
#         "error": f"Failed after {MAX_RETRIES + 1} attempts: {last_error}",
#         "content": None,
#         "source": "Unknown",
#         "author": "Unknown",
#         "date": "Unknown",
#         "scraped_successfully": False
#     }, indent=2)


# def _scrape_fast(url: str) -> Dict:
#     """
#     Optimized core scraping logic.
#     """
#     headers = {
#         'User-Agent': Config.USER_AGENT,
#         'Accept': 'text/html,application/xhtml+xml',
#         'Accept-Language': 'en-US,en;q=0.9',
#         'Connection': 'keep-alive',
#         'Cache-Control': 'max-age=0'
#     }
    
#     # Make HTTP request
#     try:
#         response = requests.get(
#             url, 
#             headers=headers, 
#             timeout=TIMEOUT,
#             allow_redirects=True,
#             verify=True
#         )
#         response.raise_for_status()
#     except requests.exceptions.SSLError:
#         # Quick SSL fallback
#         try:
#             response = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
#             response.raise_for_status()
#         except Exception as e:
#             return {"url": url, "error": f"SSL error: {str(e)}", "scraped_successfully": False}
#     except requests.Timeout:
#         return {"url": url, "error": f"Timeout ({TIMEOUT}s)", "scraped_successfully": False}
#     except requests.RequestException as e:
#         return {"url": url, "error": f"Request failed: {str(e)}", "scraped_successfully": False}
    
#     # Validate response
#     content_type = response.headers.get('Content-Type', '').lower()
#     if 'text/html' not in content_type and 'application/xhtml' not in content_type:
#         return {"url": url, "error": f"Not HTML: {content_type}", "scraped_successfully": False}
    
#     content_length = len(response.content)
#     if content_length < 500:
#         return {"url": url, "error": f"Response too small ({content_length}B)", "scraped_successfully": False}
    
#     # Parse HTML - USE FAST html.parser
#     try:
#         soup = BeautifulSoup(response.content, 'html.parser')
#     except Exception as e:
#         return {"url": url, "error": f"Parse failed: {str(e)}", "scraped_successfully": False}
    
#     # Extract metadata (streamlined - max 2 strategies per field)
#     source = _get_source(soup, url)
#     author = _get_author(soup)
#     date = _get_date(soup)
    
#     # Extract content (TOP 3 strategies only)
#     content = _extract_content_fast(soup)
#     content_len = len(content) if content else 0
    
#     # Validate
#     if not content or content_len < 100:
#         return {
#             "url": url,
#             "warning": f"Insufficient content ({content_len} chars)",
#             "content": content,
#             "content_length": content_len,
#             "source": source,
#             "author": author,
#             "date": date,
#             "scraped_successfully": False
#         }
    
#     # Success
#     logger.info(f"Scraped successfully: {content_len} chars")
#     return {
#         "url": url,
#         "source": source,
#         "author": author,
#         "date": date,
#         "content": content,
#         "content_length": content_len,
#         "scraped_successfully": True,
#         "error": None
#     }


# def _get_source(soup: BeautifulSoup, url: str) -> str:
#     """Extract source - 2 strategies only."""
#     # Strategy 1: OG site name
#     og_site = soup.find('meta', property='og:site_name')
#     if og_site and og_site.get('content'):
#         return og_site['content'].strip()
    
#     # Strategy 2: Domain fallback
#     domain = urlparse(url).netloc
#     return domain.replace('www.', '').strip()


# def _get_author(soup: BeautifulSoup) -> str:
#     """Extract author - 2 strategies only."""
#     # Strategy 1: Meta author tag
#     author_meta = soup.find('meta', attrs={'name': 'author'})
#     if author_meta and author_meta.get('content'):
#         return author_meta['content'].strip()
    
#     # Strategy 2: Common author class
#     author_span = soup.find('span', class_=re.compile(r'author', re.I))
#     if author_span:
#         text = author_span.get_text(strip=True)
#         if text and len(text) < 100:
#             return re.sub(r'^(by|author:?)\s+', '', text, flags=re.I).strip()
    
#     return "Unknown"


# def _get_date(soup: BeautifulSoup) -> str:
#     """Extract date - 2 strategies only."""
#     # Strategy 1: Time tag with datetime
#     time_tag = soup.find('time')
#     if time_tag:
#         dt = time_tag.get('datetime')
#         if dt:
#             return dt.strip()
    
#     # Strategy 2: Meta published time
#     date_meta = soup.find('meta', property='article:published_time')
#     if date_meta and date_meta.get('content'):
#         return date_meta['content'].strip()
    
#     return "Unknown"


# def _extract_content_fast(soup: BeautifulSoup) -> str:
#     """
#     OPTIMIZED: Only top 3 content extraction strategies.
#     Stops at first success >300 chars.
#     """
#     # Remove noise ONCE upfront
#     for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 
#                      'noscript', 'iframe', 'form', 'button']):
#         tag.decompose()
    
#     # Remove noise by class/id
#     noise = ['ad', 'banner', 'promo', 'social', 'comment', 'sidebar', 'menu', 'cookie']
#     for pattern in noise:
#         for elem in soup.find_all(attrs={'class': re.compile(pattern, re.I)}):
#             elem.decompose()
    
#     # STRATEGY 1: Article tag with itemprop (most reliable)
#     article_body = soup.find('div', attrs={'itemprop': 'articleBody'})
#     if article_body:
#         content = _clean_text_fast(article_body.get_text(separator=' '))
#         if len(content) > 300:
#             return content
    
#     # STRATEGY 2: Semantic article tag
#     article = soup.find('article')
#     if article:
#         content = _clean_text_fast(article.get_text(separator=' '))
#         if len(content) > 300:
#             return content
    
#     # STRATEGY 3: Common content divs
#     content_div = soup.find('div', class_=re.compile(r'article[-_]?(body|content)', re.I))
#     if content_div:
#         content = _clean_text_fast(content_div.get_text(separator=' '))
#         if len(content) > 300:
#             return content
    
#     # No strategy worked
#     return ""


# def _clean_text_fast(text: str) -> str:
#     """
#     OPTIMIZED: Single-pass text cleaning with combined regex.
#     """
#     if not text:
#         return ""
    
#     # Single pass: whitespace + noise removal
#     text = re.sub(
#         r'\s+|Advertisement|ADVERTISEMENT|Sponsored|Continue Reading|\S+@\S+|https?://\S+',
#         ' ',
#         text,
#         flags=re.I
#     )
    
#     text = text.strip()
    
#     # Length limit
#     if len(text) > 12000:
#         text = text[:12000] + "..."
    
#     return text
