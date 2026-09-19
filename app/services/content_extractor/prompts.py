"""System Prompts, JSON Schemas, and data templates for Content Extractor Service."""

from typing import Any, Dict

DEFAULT_EXTRACTOR_SYSTEM_PROMPT = (
    "You are an elite recruitment and human resources data extraction specialist.\n\n"
    "CORE MISSION:\n"
    "Thoroughly analyze the provided job recruitment posting and extract all core factual details "
    "into the requested JSON schema.\n\n"
    "STRICT GROUNDING & ZERO HALLUCINATION PRINCIPLES:\n"
    "1. 100% SOURCE FIDELITY: Extract ONLY factual details that are explicitly and directly mentioned "
    "in the source text. Do NOT invent, assume, extrapolate, or hallucinate any unmentioned attributes, "
    "amenities, conditions, or perks.\n"
    "2. STRICT ABSENCE LAW: If a specific piece of information (such as salary, location, experience requirement, "
    "benefits, contact information, or call to action) is NOT explicitly mentioned in the text, IT DOES NOT EXIST. "
    "For scalar fields, assign null. For list fields, return an empty list []. "
    "NEVER fill missing fields with speculative defaults, guesses, or generic placeholders (e.g., NEVER assume "
    "'Competitive salary', 'Negotiable', 'Free meals', or 'Shuttle bus' unless explicitly stated in the input text).\n"
    "3. ORIGINAL LANGUAGE PRESERVATION: Retain the original language of the source text for all extracted values "
    "(e.g., if the job posting is written in Vietnamese, all extracted field values MUST remain in Vietnamese, "
    "do NOT translate them to English).\n"
    "4. STRICT JSON FORMAT: Output strictly valid JSON conforming exactly to the requested structure."
)

# Alias for default system prompt
DEFAULT_SYSTEM_PROMPT = DEFAULT_EXTRACTOR_SYSTEM_PROMPT

DEFAULT_EXTRACTOR_JSON_STRUCTURE: Dict[str, Any] = {
    "job_title": "Exact job title or recruitment position explicitly mentioned in the text (null if not mentioned)",
    "company_name": "Hiring company, employer, or organization name explicitly mentioned (null if not mentioned)",
    "salary_range": "Exact salary or compensation range explicitly stated in the text (null if not mentioned; NEVER invent or assume)",
    "work_location": "Specific workplace address, district, city, or work location explicitly stated (null if not mentioned)",
    "work_format": "Work arrangement explicitly mentioned (e.g., Full-time, Part-time, Shift, Seasonal; null if not mentioned)",
    "experience_required": "Prerequisite work experience, qualifications, or skill requirements explicitly stated (null if not mentioned)",
    "top_benefits": [
        "Key perk, welfare benefit, or allowance explicitly stated in the text (empty list [] if none mentioned; NEVER invent unmentioned perks)",
    ],
    "core_requirements": [
        "Core professional, physical, or technical requirement explicitly stated in the text (empty list [] if none mentioned)",
    ],
    "contact_info": "Contact details, phone number, recruiter email, address, or application instructions explicitly mentioned (null if not mentioned)",
    "call_to_action": "Explicit call-to-action sentence found in the text (null if not mentioned; do not fabricate)",
}

# Alias for default JSON structure
DEFAULT_JSON_STRUCTURE = DEFAULT_EXTRACTOR_JSON_STRUCTURE


