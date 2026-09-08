"""
Filler / stopword terms to strip out of natural-language chat queries
before they're used as product-search keywords.

The list intentionally covers common Bengali, Banglish and English
question/commerce vocabulary while preserving merchant-specific
product and category terms.
"""

STOPWORDS: set[str] = {
    # Banglish - existence / availability questions
    "ase", "achi", "ache", "asbe", "royeche", "royece", "naki",
    # Banglish - question / quantity words
    "ki", "koto", "kotoy", "koy", "kemon", "kironkom", "koirokom",
    "kon", "konta", "konti", "kono", "sob", "shob",
    # Banglish - grammar / possessive particles
    "er", "r", "eta", "ei", "eita", "oita", "ota", "oi", "egula", "ogula",
    "tar", "ta", "ti", "gula", "gulo", "gulor",
    # Banglish - want / need / search
    "chai", "lagbe", "lagbo", "dorkar", "khujchi", "khujtesi", "khujtechi",
    "dekhte", "dekhao", "dekhan", "den", "dao", "daw", "bolen", "bolo",
    # Banglish - price
    "dam", "damer", "damta", "price", "prices", "cost", "costs", "damkoto",
    # Banglish - politeness / filler
    "please", "plz", "pls", "vai", "bhai", "apu", "amar", "amake", "ache naki",
    "stoke", "stock",

    # Bengali script
    "আছে", "আছে কি", "কি", "কত", "কতো", "কেমন", "চাই", "লাগবে", "দাম", "দামের",
    "টা", "টি", "নাকি", "আমার", "আমাকে", "দিন", "দাও", "দেখাও", "দেখান",
    "স্টকে", "স্টক", "এর", "র", "মধ্যে", "টাকার", "টাকা", "জন্য", "ও", "আর",
    "এটা", "এইটা", "ওটা", "ওইটা", "কোন", "কোনটা", "কোনটি", "কোনো", "কতগুলো",

    # English - auxiliary / question verbs
    "do", "does", "did", "have", "has", "had", "is", "are", "am", "was", "were",
    "be", "been", "being", "will", "would", "can", "could", "should", "shall",
    "may", "might", "must", "let",
    # English - pronouns / demonstratives
    "i", "me", "my", "we", "us", "our", "you", "your", "he", "she", "it", "its",
    "they", "them", "their", "this", "that", "these", "those", "there", "here",
    # English - question / quantity words
    "what", "which", "where", "when", "how", "who", "whom", "why", "any", "some",
    "much", "many", "all", "everything", "anything", "one", "ones",
    # English - commerce filler
    "want", "wanted", "need", "needed", "looking", "look", "got", "get", "getting",
    "give", "giving", "tell", "show", "find", "search", "searching", "buy", "order",
    "available", "availability", "instock", "in", "stock",
    # English - articles / prepositions / conjunctions / price units
    "the", "a", "an", "of", "for", "to", "with", "on", "at", "from", "by", "about",
    "and", "or", "under", "below", "less", "than", "within", "over", "above", "around",
    "between", "taka", "tk", "bdt",
    # English - greetings / politeness
    "hello", "hi", "hey", "thanks", "thank",
}

_PUNCTUATION = ".,!?;:()[]{}\"'“”‘’—–…"


def strip_stopwords(terms: list[str]) -> list[str]:
    """Filter filler words while preserving meaningful search terms."""
    filtered = []
    for term in terms:
        cleaned = term.strip(_PUNCTUATION)
        if not cleaned:
            continue
        if cleaned.lower() in STOPWORDS:
            continue
        filtered.append(cleaned)
    return filtered
