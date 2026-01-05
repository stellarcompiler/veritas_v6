from crewai import Agent
from langchain_google_genai import ChatGoogleGenerativeAI
from veritas.config import Config, logger

try:
    # Initialize LLM with higher temperature for better reasoning
    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0.1,
        verbose=False,
        google_api_key=Config.GOOGLE_API_KEY
    )
    
    verdict_agent = Agent(
        role="Senior Fact-Checking Analyst",
        goal=(
            "Determine if a news claim is REAL, FAKE, or UNVERIFIED by analyzing "
            "entity quality, sensationalism scores, and evidence from web sources. "
            "Provide clear, evidence-based verdicts in JSON format."
        ),
        backstory=(
            "You are an expert fact-checker with 15 years of experience in investigative journalism. "
            "You excel at cross-referencing claims against credible sources and detecting misinformation patterns. "
            "You provide direct, structured verdicts without unnecessary elaboration. "
            "You understand that high sensationalism doesn't always mean fake news, but it's a red flag. "
            "You always base conclusions on evidence, not assumptions."
        ),
        verbose=True,
        memory=True,
        allow_delegation=False,
        llm=llm
    )
    
    logger.info("Verdict Agent initialized successfully.")
    
except Exception as e:
    logger.error(f"Failed to initialize Verdict Agent: {e}")
    raise RuntimeError(f"Verdict Agent initialization failed: {e}")
