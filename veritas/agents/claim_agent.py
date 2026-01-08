import os
from crewai import Agent
from langchain_google_genai import ChatGoogleGenerativeAI
from veritas.tools.nlp import spacy_claim_analyzer_tool
from veritas.config import Config, logger

try:
    # Initialize LLM with error handling
    llm = ChatGoogleGenerativeAI(
        model= "gemma-3-27b-it",
        temperature= 0.1,
        verbose=Config.VERBOSE_STATE,
        google_api_key="AIzaSyDTyWWxQpPadx1tIhsVY5-Gh8IEt1KfzNw"
    )
    
    claim_agent = Agent(
        role="Lead Claim Analyst",
        goal=(
            "Analyze incoming news claims to extract factual entities and "
            "detect linguistic sensationalism using specialized NLP tools."
        ),
        backstory=(
            "You are 'Veritas', a senior data journalist and computational linguist. "
            "You do not trust intuition; you trust data. Your job is to strictly "
            "parse claims into their components (Entities) and judge their "
            "emotional weight (Sensationalism) using your NLP tools. "
            "You are the first line of defense in the fake news detection pipeline. "
            "You handle errors gracefully and always provide structured output."
        ),
        tools=[spacy_claim_analyzer_tool],
        verbose=Config.VERBOSE_STATE,
        memory=True,
        allow_delegation=False,
        llm=llm
    )
    
    logger.info("Claim Agent initialized successfully.")
    
except Exception as e:
    logger.error(f"Failed to initialize Claim Agent: {e}")
    raise RuntimeError(f"Claim Agent initialization failed: {e}")
