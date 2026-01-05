import json
from crewai_tools import tool
from serpapi import GoogleSearch
from veritas.config import Config, logger

@tool("serp_search_tool")
def serp_search_tool(query: str) -> str:
    """
    Search Google for the given query and return top 2 results prioritizing 
    news sources and fact-checking sites.
    
    Args:
        query: Search query string
    
    Returns:
        JSON string containing list of 2 search results with title, link, source, snippet, date
    """
    # Input validation
    if not query or not query.strip():
        logger.warning("Empty query provided to search tool")
        return json.dumps({
            "error": "Empty query",
            "results": []
        })
    
    if len(query) > 500:
        logger.warning(f"Query too long ({len(query)} chars), truncating")
        query = query[:500]

    logger.info(f"Searching SERP for: {query}")
    
    try:
        # Validate API key
        if not Config.SERPAPI_API_KEY:
            logger.error("SERPAPI_API_KEY not configured")
            return json.dumps({
                "error": "SERPAPI_API_KEY not configured",
                "results": []
            })
        
        # Prepare search parameters - REQUEST 2 RESULTS
        params = {
            "engine": "google",
            "q": query,
            "api_key": Config.SERPAPI_API_KEY,
            "num": 2,  # Changed from 5 to 2 as requested
            "gl": "us",
            "hl": "en",
            "tbm": "nws"  # Focus on news results
        }
        
        # Execute search
        try:
            search = GoogleSearch(params)
            results = search.get_dict()
        except Exception as search_error:
            logger.error(f"SERP API request failed: {search_error}")
            return json.dumps({
                "error": f"Search request failed: {str(search_error)}",
                "results": []
            })
        
        # Check for API errors
        if "error" in results:
            logger.error(f"SERP API returned error: {results['error']}")
            return json.dumps({
                "error": results.get("error", "Unknown API error"),
                "results": []
            })
        
        cleaned_results = []
        
        # Priority sources (fact-checkers + major news)
        priority_domains = [
            'snopes.com', 'politifact.com', 'factcheck.org', 
            'reuters.com', 'apnews.com', 'bbc.com', 'npr.org',
            'nytimes.com', 'washingtonpost.com', 'theguardian.com'
        ]

        # Extract News Results
        news_results = results.get("news_results", [])
        for result in news_results[:2]:  # Max 2 results
            try:
                url = result.get("link", "")
                domain = url.lower()
                is_priority = any(pd in domain for pd in priority_domains)
                
                cleaned_results.append({
                    "category": "news",
                    "title": result.get("title", "No title"),
                    "link": url,
                    "source": result.get("source", {}).get("name", "Unknown") if isinstance(result.get("source"), dict) else result.get("source", "Unknown"),
                    "snippet": result.get("snippet", ""),
                    "date": result.get("date", "Unknown"),
                    "priority": is_priority
                })
            except Exception as e:
                logger.warning(f"Failed to parse news result: {e}")
                continue

        # Fallback to Organic Results if not enough news
        if len(cleaned_results) < 2:
            organic_results = results.get("organic_results", [])
            for result in organic_results[:(2 - len(cleaned_results))]:
                try:
                    url = result.get("link", "")
                    domain = url.lower()
                    is_priority = any(pd in domain for pd in priority_domains)
                    
                    cleaned_results.append({
                        "category": "organic",
                        "title": result.get("title", "No title"),
                        "link": url,
                        "source": result.get("displayed_link", "Google Search"),
                        "snippet": result.get("snippet", ""),
                        "date": result.get("date", "Unknown"),
                        "priority": is_priority
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse organic result: {e}")
                    continue
        
        # Sort: priority sources first
        cleaned_results.sort(key=lambda x: x.get("priority", False), reverse=True)
        
        # Remove priority flag
        for result in cleaned_results:
            result.pop("priority", None)
        
        # Validate
        if not cleaned_results:
            logger.warning(f"No results found for query: {query}")
            return json.dumps({
                "warning": "No results found",
                "results": [],
                "query": query
            })
        
        logger.info(f"Found {len(cleaned_results)} search results")
        return json.dumps({
            "results": cleaned_results,
            "total": len(cleaned_results),
            "query": query,
            "error": None
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Unexpected error in SERP search: {e}", exc_info=True)
        return json.dumps({
            "error": f"Search failed: {str(e)}",
            "results": [],
            "query": query
        }, indent=2)
