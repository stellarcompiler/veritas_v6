from crewai import Agent
from langchain_google_genai import ChatGoogleGenerativeAI
from veritas.tools.search_tool import serp_search_tool
from veritas.tools.scraper_tool import web_scraper_tool
from veritas.tools.summarizer_tool import content_summarizer_tool
from veritas.config import Config, logger

try:
    # Initialize LLM with error handling
    llm = ChatGoogleGenerativeAI(
        model="gemma-3-27b-it",
        temperature=0.1,
        verbose=Config.VERBOSE_STATE,
        google_api_key=Config.GOOGLE_API_KEY
    )
    
    researcher_agent = Agent(
        role="Senior Research Analyst",
        goal=(
            "Gather external evidence from web sources by searching for named entities, "
            "scraping relevant articles, and providing concise summaries. "
            "DO NOT make verdicts or conclusions - only collect and summarize data. "
            "Handle failures gracefully and continue with partial results."
        ),
        backstory=(
            "You are a meticulous data collector for Veritas. "
            "Your sole responsibility is to find and extract factual information from the web. "
            "You take the entities identified by the Claim Analyst and search for them systematically. "
            "You never make judgments - you only report what you find. "
            "You are thorough but concise, providing minimal-token summaries to conserve context. "
            "When tools fail, you adapt and work with what's available - resilience is your strength."
        ),
        tools=[serp_search_tool, web_scraper_tool, content_summarizer_tool],
        verbose=Config.VERBOSE_STATE,
        memory=True,
        allow_delegation=False,
        llm=llm
    )
    
    logger.info("Researcher Agent initialized successfully.")
    
except Exception as e:
    logger.error(f"Failed to initialize Researcher Agent: {e}")
    raise RuntimeError(f"Researcher Agent initialization failed: {e}")
