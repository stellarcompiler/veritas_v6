from crewai_tools import tool
import spacy
import json
from typing import Dict, List, Tuple
from collections import Counter
from veritas.config import Config, logger
from app.services.telemetry import log_event

# Global model cache
_nlp_model = None

def get_nlp_model():
    """Lazy load the SpaCy model to prevent import bottlenecks."""
    global _nlp_model
    if _nlp_model is None:
        try:
            logger.info(f"Loading SpaCy model: {Config.SPACY_MODEL}...")
            _nlp_model = spacy.load(Config.SPACY_MODEL)
            logger.info("SpaCy model loaded successfully.")
        except OSError:
            logger.error(f"Model '{Config.SPACY_MODEL}' not found. Please run: python -m spacy download {Config.SPACY_MODEL}")
            raise
    return _nlp_model

# Enhanced linguistic markers
INTENSIFIERS = {
    "very", "extremely", "highly", "deeply", "incredibly", "absolutely", 
    "totally", "completely", "utterly", "unbelievably", "insanely", "literally", 
    "massive", "huge", "enormous", "shocking", "devastating", "unprecedented",
    "catastrophic", "revolutionary", "groundbreaking", "astounding", "miraculous"
}

SENSATIONAL_VERBS = {
    "claim", "allege", "suggest", "insist", "assert", "declare", "proclaim",
    "reveal", "expose", "uncover", "discover", "slam", "blast", "destroy",
    "demolish", "crush", "annihilate", "shock", "stun", "amaze", "confess"
}

HEDGING_WORDS = {
    "allegedly", "reportedly", "supposedly", "apparently", "seemingly",
    "claimed", "suggested", "rumored", "unconfirmed", "unverified"
}

EMOTIONAL_ADJECTIVES = {
    "shocking", "devastating", "horrifying", "terrifying", "amazing", "incredible",
    "unbelievable", "outrageous", "scandalous", "explosive", "bombshell",
    "unprecedented", "historic", "catastrophic", "tragic", "miraculous"
}

def extract_quality_entities(doc) -> Tuple[List[Dict], int]:
    """
    Extract high-quality named entities with confidence scoring.
    Returns: (entities_list, entity_quality_score)
    """
    entities = []
    entity_types_count = Counter()
    
    # Priority entity types for news verification
    HIGH_VALUE_TYPES = {'PERSON', 'ORG', 'GPE', 'LOC', 'EVENT', 'PRODUCT', 'LAW'}
    MEDIUM_VALUE_TYPES = {'DATE', 'TIME', 'MONEY', 'PERCENT', 'QUANTITY'}
    
    seen = set()
    for ent in doc.ents:
        # Deduplicate and clean
        clean_text = ent.text.strip()
        if clean_text.lower() in seen or len(clean_text) < 2:
            continue
        seen.add(clean_text.lower())
        
        # Calculate entity confidence based on multiple factors
        confidence = 0.0
        
        # Factor 1: Entity type value
        if ent.label_ in HIGH_VALUE_TYPES:
            confidence += 0.5
            entity_types_count[ent.label_] += 1
        elif ent.label_ in MEDIUM_VALUE_TYPES:
            confidence += 0.3
        else:
            confidence += 0.1
        
        # Factor 2: Entity length (longer entities are usually more specific)
        word_count = len(clean_text.split())
        if word_count >= 2:
            confidence += 0.2
        if word_count >= 3:
            confidence += 0.1
            
        # Factor 3: Capitalization pattern (proper nouns)
        if clean_text[0].isupper() and not clean_text.isupper():
            confidence += 0.1
            
        # Factor 4: Check if entity appears in dependency tree as subject/object
        for token in ent:
            if token.dep_ in ('nsubj', 'nsubjpass', 'dobj', 'pobj'):
                confidence += 0.1
                break
        
        confidence = min(confidence, 1.0)
        
        entities.append({
            "text": clean_text,
            "label": ent.label_,
            "confidence": round(confidence, 2),
            "start_char": ent.start_char,
            "end_char": ent.end_char
        })
    
    # Sort by confidence descending
    entities.sort(key=lambda x: x['confidence'], reverse=True)
    
    # Calculate entity quality score
    quality_score = 0
    if len(entities) > 0:
        # Reward diversity of entity types
        type_diversity = len(entity_types_count) / len(HIGH_VALUE_TYPES | MEDIUM_VALUE_TYPES)
        
        # Reward high-value entities
        high_value_count = sum(1 for e in entities if e['label'] in HIGH_VALUE_TYPES)
        high_value_ratio = high_value_count / len(entities)
        
        # Reward average confidence
        avg_confidence = sum(e['confidence'] for e in entities) / len(entities)
        
        # Combined score (0-100)
        quality_score = int(
            (type_diversity * 30) + 
            (high_value_ratio * 40) + 
            (avg_confidence * 30)
        )
    
    return entities, quality_score


def analyze_grammatical_structure(doc) -> Dict[str, any]:
    """
    Analyze sentence structure for sensationalism indicators.
    Returns metrics based on syntax patterns.
    """
    metrics = {
        "passive_voice_count": 0,
        "imperative_count": 0,
        "exclamation_count": 0,
        "question_count": 0,
        "quote_count": 0,
        "avg_sentence_length": 0,
        "complex_sentence_ratio": 0,
        "fragment_count": 0,
        "intensifier_count": 0,
        "hedging_count": 0,
        "sensational_verb_count": 0,
        "emotional_adj_count": 0,
        "caps_lock_words": 0
    }
    
    sentence_lengths = []
    complex_sentences = 0
    
    for sent in doc.sents:
        sent_length = len([t for t in sent if not t.is_punct])
        sentence_lengths.append(sent_length)
        
        # Detect passive voice (auxiliary verb + past participle)
        for token in sent:
            if token.dep_ == "auxpass":
                metrics["passive_voice_count"] += 1
            
            # Check for sensational verbs
            if token.pos_ == "VERB" and token.lemma_.lower() in SENSATIONAL_VERBS:
                metrics["sensational_verb_count"] += 1
            
            # Check for emotional adjectives
            if token.pos_ == "ADJ" and token.lemma_.lower() in EMOTIONAL_ADJECTIVES:
                metrics["emotional_adj_count"] += 1
                
            # Check for intensifiers
            if token.lemma_.lower() in INTENSIFIERS:
                metrics["intensifier_count"] += 1
            
            # Check for hedging words
            if token.lemma_.lower() in HEDGING_WORDS:
                metrics["hedging_count"] += 1
            
            # ALL CAPS words (excluding single letters)
            if token.text.isupper() and len(token.text) > 1 and token.is_alpha:
                metrics["caps_lock_words"] += 1
        
        # Imperative detection (sentence starts with base verb)
        if len(sent) > 0 and sent[0].pos_ == "VERB" and sent[0].tag_ in ("VB", "VBP"):
            metrics["imperative_count"] += 1
        
        # Fragment detection (no main verb)
        has_main_verb = any(token.pos_ == "VERB" and token.dep_ in ("ROOT", "aux") for token in sent)
        if not has_main_verb and sent_length > 2:
            metrics["fragment_count"] += 1
        
        # Complex sentence (has subordinate clauses)
        has_subordinate = any(token.dep_ in ("mark", "advcl", "acl", "relcl") for token in sent)
        if has_subordinate:
            complex_sentences += 1
    
    # Punctuation analysis
    text = doc.text
    metrics["exclamation_count"] = text.count("!")
    metrics["question_count"] = text.count("?")
    metrics["quote_count"] = text.count('"') // 2  # Pairs of quotes
    
    # Average sentence length
    if sentence_lengths:
        metrics["avg_sentence_length"] = sum(sentence_lengths) / len(sentence_lengths)
        metrics["complex_sentence_ratio"] = complex_sentences / len(sentence_lengths)
    
    return metrics


def calculate_sensationalism_score(doc, gram_metrics: Dict) -> Tuple[int, str]:
    """
    Calculate sensationalism score based on grammatical analysis.
    Returns: (score 0-100, detailed_breakdown)
    """
    score = 0.0
    breakdown = []
    
    token_count = len([t for t in doc if not t.is_punct]) or 1
    sentence_count = len(list(doc.sents)) or 1
    
    # 1. Emotional Language (0-25 points)
    emotional_density = (
        gram_metrics["intensifier_count"] + 
        gram_metrics["emotional_adj_count"]
    ) / token_count
    emotional_score = min(emotional_density * 150, 25)
    score += emotional_score
    if emotional_score > 10:
        breakdown.append(f"High emotional language density: {emotional_score:.1f}/25")
    
    # 2. Sensational Verbs & Vocabulary (0-20 points)
    sensational_density = gram_metrics["sensational_verb_count"] / token_count
    sensational_score = min(sensational_density * 200, 20)
    score += sensational_score
    if sensational_score > 8:
        breakdown.append(f"Sensational vocabulary: {sensational_score:.1f}/20")
    
    # 3. Punctuation Abuse (0-15 points)
    exclamation_score = min(gram_metrics["exclamation_count"] * 5, 15)
    score += exclamation_score
    if exclamation_score > 5:
        breakdown.append(f"Excessive exclamations: {exclamation_score:.1f}/15")
    
    # 4. ALL CAPS Words (0-10 points)
    caps_score = min(gram_metrics["caps_lock_words"] * 3, 10)
    score += caps_score
    if caps_score > 3:
        breakdown.append(f"ALL CAPS usage: {caps_score:.1f}/10")
    
    # 5. Sentence Structure (0-15 points)
    # Short punchy sentences
    if gram_metrics["avg_sentence_length"] < 10:
        structure_score = 10
        breakdown.append(f"Short punchy sentences: {structure_score}/15")
    elif gram_metrics["avg_sentence_length"] < 15:
        structure_score = 5
    else:
        structure_score = 0
    
    # Sentence fragments
    fragment_ratio = gram_metrics["fragment_count"] / sentence_count
    structure_score += min(fragment_ratio * 15, 5)
    
    score += structure_score
    
    # 6. Imperative & Direct Address (0-10 points)
    imperative_score = min(gram_metrics["imperative_count"] * 5, 10)
    score += imperative_score
    if imperative_score > 3:
        breakdown.append(f"Imperative commands: {imperative_score:.1f}/10")
    
    # 7. Hedging Language (REDUCES score - indicates caution)
    hedging_penalty = min(gram_metrics["hedging_count"] * 2, 10)
    score -= hedging_penalty
    if hedging_penalty > 3:
        breakdown.append(f"Hedging language (reduces sensationalism): -{hedging_penalty:.1f}")
    
    # 8. Quote Density Bonus (0-5 points)
    # High quotes can indicate dramatization
    quote_density = gram_metrics["quote_count"] / sentence_count
    if quote_density > 0.5:
        quote_score = 5
        score += quote_score
        breakdown.append(f"High quote density: {quote_score}/5")
    
    # Normalize to 0-100
    final_score = max(0, min(int(score), 100))
    
    # Analysis text
    if final_score < 25:
        analysis = "Neutral, factual reporting style with minimal emotional language."
    elif final_score < 45:
        analysis = "Moderately emotive with some sensational elements present."
    elif final_score < 65:
        analysis = "Highly sensationalized with emotional manipulation tactics."
    else:
        analysis = "Extremely sensationalized, likely designed to provoke strong reactions."
    
    if breakdown:
        analysis += " Key indicators: " + "; ".join(breakdown[:3])
    
    return final_score, analysis


@tool("spacy_claim_analyzer_tool")
def spacy_claim_analyzer_tool(claim: str, job_id: str) -> str:
    """
    Advanced claim analyzer using SpaCy's linguistic features.
    Extracts high-quality named entities with confidence scores and performs 
    deep grammatical analysis for sensationalism detection.
    
    Returns JSON with:
    - entities: List of NERs with confidence scores and labels
    - entity_quality_score: Quality assessment of extracted entities (0-100)
    - sensationalism_score: Grammatical sensationalism score (0-100)
    - analysis: Detailed textual analysis
    - warning: Alert if entity quality is too low for verification
    """
# Log Tool Event
    log_event(
        job_id= job_id,
        source= "spaCy-NLP TOOL",
        event_type= "START",
        message="Starting NER Extraction-Meaning Extraction",
        meta={"NLP_model" : "spaCy - en_core_web_lg model"}
    )

    # Input validation
    if not claim or not claim.strip():
        logger.warning("Empty claim provided to NLP analyzer")
        return json.dumps({
            "error": "No text provided",
            "entities": [],
            "entity_count": 0,
            "entity_quality_score": 0,
            "sensationalism_score": 0,
            "grammatical_metrics": {},
            "analysis": "No text to analyze",
            "warning": "Empty input"
        })

    try:
        # Load NLP model with error handling
        try:
            nlp = get_nlp_model()
        except Exception as model_error:
            logger.error(f"Failed to load SpaCy model: {model_error}")
            return json.dumps({
                "error": f"Model loading failed: {str(model_error)}",
                "entities": [],
                "entity_count": 0,
                "entity_quality_score": 0,
                "sensationalism_score": 0,
                "grammatical_metrics": {},
                "analysis": "Model loading failed",
                "warning": "NLP model unavailable"
            })
        
        # Process text
        doc = nlp(claim)

        # Extract quality entities with confidence
        try:
            entities, entity_quality_score = extract_quality_entities(doc)
        except Exception as entity_error:
            logger.error(f"Entity extraction failed: {entity_error}")
            entities = []
            entity_quality_score = 0
        
        # Analyze grammatical structure
        try:
            gram_metrics = analyze_grammatical_structure(doc)
        except Exception as gram_error:
            logger.error(f"Grammatical analysis failed: {gram_error}")
            gram_metrics = {}
        
        # Calculate sensationalism score
        try:
            sensationalism_score, analysis = calculate_sensationalism_score(doc, gram_metrics)
        except Exception as sens_error:
            logger.error(f"Sensationalism calculation failed: {sens_error}")
            sensationalism_score = 0
            analysis = "Analysis calculation failed"
        
        # Generate warning if entity quality is too low
        warning = None
        if entity_quality_score < 30:
            warning = "LOW_ENTITY_QUALITY: Insufficient named entities detected. Text may be too vague or generic for fact verification."
        elif len(entities) == 0:
            warning = "NO_ENTITIES: No named entities found. Cannot proceed with verification."
        elif len([e for e in entities if e.get('confidence', 0) > 0.5]) < 2:
            warning = "LOW_CONFIDENCE_ENTITIES: Less than 2 high-confidence entities detected. Verification may be unreliable."
        
        result = {
            "entities": entities,
            "entity_count": len(entities),
            "entity_quality_score": entity_quality_score,
            "sensationalism_score": sensationalism_score,
            "grammatical_metrics": gram_metrics,
            "analysis": analysis,
            "warning": warning,
            "error": None
        }
        
        logger.info(f"Analyzed claim: {len(entities)} entities, quality={entity_quality_score}, sensationalism={sensationalism_score}")
        
        if warning:
            logger.warning(f"Entity quality warning: {warning}")
        
        log_event(
        job_id= job_id,
        source= "spaCy-NLP TOOL",
        event_type= "END",
        message="END : NER Extraction-Meaning Extraction Completed",
        meta={"NLP_model" : "spaCy - en_core_web_lg model"}
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
        

    except Exception as e:
        logger.error(f"Critical error in spacy_claim_analyzer_tool: {e}", exc_info=True)
        log_event(
        job_id= job_id,
        source= "spaCy-NLP TOOL",
        event_type= "FAILURE",
        message="FAILED to extract NER & Meaning",
        meta={"NLP_model" : "spaCy - en_core_web_lg model"}
        )
        return json.dumps({
            "error": f"Analysis failed: {str(e)}",
            "entities": [],
            "entity_count": 0,
            "entity_quality_score": 0,
            "sensationalism_score": 0,
            "grammatical_metrics": {},
            "analysis": "Critical analysis error",
            "warning": "Analysis system failure"
        }, indent=2)
