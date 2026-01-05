from crewai import Task
from veritas.agents.claim_agent import claim_agent
from veritas.agents.researcher_agent import researcher_agent
from veritas.agents.verdict_agent import verdict_agent
from veritas.config import logger

def create_claim_analysis_task(claim_text: str, job_id : str) -> Task:
    """
    Task 1: Analyze claim for entities and sensationalism.
    """
    if not claim_text or not claim_text.strip():
        logger.error("Empty claim text provided to claim analysis task")
        raise ValueError("Claim text cannot be empty")
    
    return Task(
        description=(
             f"JOB_ID: {job_id}\n\n"
            f"Analyze the following claim: '{claim_text}'\n\n"
            "INSTRUCTIONS:\n"
            "1. Call the `spacy_claim_analyzer_tool` with the claim_text and job_id.\n"
            "2. Extract the results: entities (with confidence scores), entity_count, "
            "entity_quality_score, sensationalism_score.\n"
            "3. Write a brief 1-2 sentence analysis summary.\n"
            "4. Check for any warnings about entity quality.\n\n"
            "CRITICAL: Handle tool failures gracefully. If NLP analysis fails, "
            "return an error structure with empty entities and zero scores."
        ),
        expected_output=(
            "A JSON object containing:\n"
            "- 'entities': list of entities with text, label, confidence\n"
            "- 'entity_count': integer count of entities\n"
            "- 'entity_quality_score': 0-100 quality score\n"
            "- 'sensationalism_score': 0-100 sensationalism score\n"
            "- 'analysis': brief summary text\n"
            "- 'warning': string or null\n"
            "- 'error': string or null (if analysis failed)"
        ),
        agent=claim_agent
    )

def create_research_task(claim_text: str, context_task: Task, job_id: str) -> Task:
    """
    Task 2: Research claim using web sources.
    OPTIMIZED for Gemma-3-27b: Compact, clear instructions.
    """
    return Task(
        description=(
             f"JOB_ID: {job_id}\n\n"
            f"CLAIM: '{claim_text}'\n\n"
            "MISSION: Find web evidence about this claim.\n\n"
            "STEP 1: CHECK ENTITY QUALITY\n"
            "- Get entity_quality_score from previous task\n"
            "- If score < 30 OR warning = 'NO_ENTITIES': STOP\n"
            "- Return: {\"status\": \"INSUFFICIENT_ENTITIES\", \"warning\": \"...\"}\n\n"
            "STEP 2: BUILD SEARCH QUERY\n"
            "- Take top 2-3 entities (confidence > 0.5)\n"
            "- Combine with claim keywords\n"
            "- Example: claim='Biden tariffs China' → query='Biden China tariffs'\n"
            "- Keep query short (3-5 words)\n\n"
            "STEP 3: SEARCH\n"
            "- Call serp_search_tool(query, job_id)\n"
            "- Get 2 URLs from results\n"
            "- Pick credible sources: reuters.com, bbc.com, apnews.com, etc.\n\n"
            "STEP 4: SCRAPE (MAX 2 SITES)\n"
            "For each URL:\n"
            "1. Call web_scraper_tool(url, job_id)\n"
            "2. Check: scraped_successfully = true\n"
            "3. If success: save summary\n"
            "4. If fail: try next URL\n"
            "5. STOP after 2 successful scrapes\n\n"
            "STEP 5: SUMMARIZE\n"
            "For each scraped content:\n"
            "- Call content_summarizer_tool(content, job_id)\n"
            "- Keep summary under 120 words\n\n"
            "ERROR HANDLING:\n"
            "- Tool fails: continue to next\n"
            "- All fail: return status='RESEARCH_FAILED'\n"
            "- Partial OK: report what you got\n\n"
            "RULES:\n"
            "- MAX 2 successful scrapes\n"
            "- NO judgments (just collect data)\n"
            "- Return JSON structure below"
        ),
        expected_output=(
            "JSON:\n"
            "{\n"
            "  \"status\": \"RESEARCH_COMPLETE\" | \"INSUFFICIENT_ENTITIES\" | \"RESEARCH_FAILED\",\n"
            "  \"entities_searched\": [\"entity1\", \"entity2\"],\n"
            "  \"search_queries_used\": [\"query1\"],\n"
            "  \"sources\": [\n"
            "    {\n"
            "      \"url\": \"https://...\",\n"
            "      \"source_name\": \"Reuters\",\n"
            "      \"date\": \"2024-12-18\",\n"
            "      \"summary\": \"120-word summary\",\n"
            "      \"scraped_successfully\": true\n"
            "    }\n"
            "  ],\n"
            "  \"total_sources_found\": 2,\n"
            "  \"total_sources_scraped\": 2\n"
            "}"
        ),
        agent=researcher_agent,
        context=[context_task]
    )

def create_verdict_task(claim_text: str, context_tasks: list) -> Task:
    """
    Task 3: Analyze claim veracity based on research findings.
    SIMPLIFIED VERSION - Direct JSON output without tool calls.
    """
    if not claim_text or not claim_text.strip():
        logger.error("Empty claim text provided to verdict task")
        raise ValueError("Claim text cannot be empty")
    
    return Task(
        description=(
            f"ORIGINAL CLAIM: '{claim_text}'\n\n"
            "=== YOUR MISSION ===\n"
            "Analyze if this claim is REAL, FAKE, or UNVERIFIED based on:\n"
            "1. Claim Analysis data (entities, quality, sensationalism)\n"
            "2. Research findings (sources, summaries)\n\n"
            "=== DECISION LOGIC ===\n"
            "**UNVERIFIED** if:\n"
            "- Research status = INSUFFICIENT_ENTITIES or LOW_QUALITY_ENTITIES\n"
            "- No sources were successfully scraped\n"
            "- Evidence is contradictory or inconclusive\n\n"
            "**FAKE** if:\n"
            "- Sensationalism score > 70 AND entity_quality < 50\n"
            "- Sources directly contradict the claim\n"
            "- Multiple sources from known fact-checkers debunk it\n\n"
            "**REAL** if:\n"
            "- Multiple credible sources confirm the claim\n"
            "- Entity quality > 60 AND sources align with claim\n"
            "- Fact-checker sites verify it\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return ONLY a JSON object (no markdown, no extra text):\n"
            "{\n"
            '  "verdict": "REAL" or "FAKE" or "UNVERIFIED",\n'
            '  "confidence": 75,  // 0-100 integer\n'
            '  "reasoning": "Brief 2-3 sentence explanation based on evidence",\n'
            '  "sources_analyzed": {\n'
            '    "supporting": ["url1", "url2"],  // URLs that support the claim\n'
            '    "contradicting": ["url3"],  // URLs that contradict\n'
            '    "inconclusive": ["url4"]  // Neutral/unclear URLs\n'
            '  },\n'
            '  "key_factors": {\n'
            '    "entity_quality": 65,  // From claim analysis\n'
            '    "sensationalism": 45,  // From claim analysis\n'
            '    "sources_count": 3  // Successfully scraped sources\n'
            '  }\n'
            "}\n\n"
            "=== CRITICAL RULES ===\n"
            "1. Output ONLY the JSON object, nothing else\n"
            "2. Keep reasoning under 200 characters\n"
            "3. Categorize ALL researched URLs into supporting/contradicting/inconclusive\n"
            "4. Base verdict on EVIDENCE, not just sensationalism score\n"
            "5. If research failed, verdict must be UNVERIFIED with confidence < 30"
        ),
        expected_output=(
            'JSON object with keys: verdict, confidence, reasoning, sources_analyzed, key_factors.\n'
            'verdict must be one of: "REAL", "FAKE", "UNVERIFIED"\n'
            'confidence must be integer 0-100\n'
            'Keep output minimal and structured.'
        ),
        agent=verdict_agent,
        context=context_tasks
    )
