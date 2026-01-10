import json
from crewai_tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from veritas.config import Config, logger
from app.services.telemetry import log_event

# Initialize local LLM instance for this tool
try:
    llm_summarizer = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.1,
        google_api_key= Config.GOOGLE_API_KEY3
    )
    logger.info("Summarizer LLM initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize summarizer LLM: {e}")
    llm_summarizer = None

@tool("content_summarizer_tool")
def content_summarizer_tool(content: str, job_id: str) -> str:
    """
    Takes raw text content and returns a dense, minimal-token summary 
    focusing on factual claims, dates, and entities.
    
    Args:
        content: Raw text or JSON string containing article content
    
    Returns:
        Concise summary string or error message
    """
    # Input validation
    if not content or not isinstance(content, str):
        logger.warning("Empty or invalid content provided to summarizer")
        log_event(
        job_id= job_id,
        source= "Gemini-Summarizer-Tool",
        event_type= "START",
        message="Empty or invalid content provided to summarizer",
        meta={}
        )
        return "Error: No content provided for summarization"
    
    if len(content.strip()) < 50:
        logger.warning(f"Content too short for summarization: {len(content)} chars")
        log_event(
        job_id= job_id,
        source= "Gemini-Summarizer-Tool",
        event_type= "START",
        message="Content too short for summarization",
        meta={}
        )
        return "Error: Content too short to summarize (minimum 50 characters)"
    
    # Check if LLM is available
    if llm_summarizer is None:
        logger.error("Summarizer LLM not initialized")
        log_event(
        job_id= job_id,
        source= "Gemini-Summarizer-Tool",
        event_type= "START",
        message="Summarizer LLM not initialized",
        meta={}
        )
        return "Error: Summarization service unavailable"

    # Parse if it's a JSON string from the scraper
    text_to_summarize = content
    try:
        if content.strip().startswith("{"):
            data = json.loads(content)
            text_to_summarize = data.get("content", "")
            
            if not text_to_summarize:
                logger.warning("Parsed JSON but no 'content' field found")
                # Fallback to raw content
                text_to_summarize = content
    except json.JSONDecodeError:
        # Not JSON, use as-is
        text_to_summarize = content
    except Exception as e:
        logger.warning(f"Error parsing content as JSON: {e}")
        text_to_summarize = content
    
    # Validate extracted text
    if not text_to_summarize or len(text_to_summarize.strip()) < 50:
        logger.warning("Extracted content too short for summarization")
        return "Error: Extracted content too short to summarize"
    
    # Truncate if too long to fit in context
    max_content_length = 8000
    if len(text_to_summarize) > max_content_length:
        logger.info(f"Truncating content from {len(text_to_summarize)} to {max_content_length} chars")
        text_to_summarize = text_to_summarize[:max_content_length]

    # Create optimized prompt
    prompt = (
        "Summarize the following text efficiently in 100-150 words. "
        "Focus ONLY on: verifiable factual claims, key entities (people/orgs/places), "
        "dates, and specific events. "
        "Ignore advertisements, navigation text, and filler content. "
        "Be concise and factual.\n\n"
        f"TEXT: {text_to_summarize}"
    )
    
    try:
        logger.info("Generating content summary...")
        response = llm_summarizer.invoke(prompt)
        
        # Extract text from response
        if hasattr(response, 'content'):
            summary = response.content
        elif isinstance(response, str):
            summary = response
        else:
            summary = str(response)
        
        # Validate summary
        if not summary or len(summary.strip()) < 10:
            logger.warning("Generated summary too short or empty")
            return "Error: Failed to generate valid summary"
        
        # Truncate if still too long
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        logger.info(f"Summary generated successfully ({len(summary)} chars)")
        log_event(
        job_id= job_id,
        source= "Gemini-Summarizer-Tool",
        event_type= "END",
        message="Summary generated successfully",
        meta={}
        )
        return summary.strip()
    
    except Exception as e:
        logger.error(f"Summarization failed: {e}", exc_info=True)
        return f"Error: Summarization failed - {str(e)}"
