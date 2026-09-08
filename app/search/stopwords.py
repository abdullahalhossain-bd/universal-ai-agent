"""
Filler / stopword terms to strip out of natural-language chat queries
before they're used as product-search keywords.

Chat users write full sentences ("laptop ase?", "ei ta ki available",
"laptop koto dam") rather than bare product names. Without filtering,
every word in the sentence becomes a required (AND) search term, so a
single filler word with no product-name match (e.g. "ase") silently
zeroes out results even when the actual product exists.

This list intentionally covers common Bengali (Latin-transliterated
"Banglish"), Bengali-script, AND English filler/question words. It is
not exhaustive — extend it as new false-negative queries are observed.
"""

STOPWORDS: set[str] = {
    # Banglish - existence / availability questions
    "ase", "achi", "ache", "asbe", "royeche", "royece",
    # Banglish - question / quantity words
    "ki", "koto", "kotoy", "kemon", "kironkom", "koirokom",
    # Banglish - want / need
    "chai", "lagbe", "lagbo", "dorkar", "khujchi", "khujtesi",
    # Banglish - price
    "dam", "damta", "price", "damkoto",
    # Banglish - generic filler / grammar particles
    "ta", "ti", "ta ki", "naki", "please", "plz", "pls", "vai", "bhai",
    "apu", "amar", "amake", "ache naki", "dekhao", "dekhan", "stoke",
    # Bengali script equivalents
    "আছে", "আছে কি", "কি", "কত", "কতো", "কেমন", "চাই", "লাগবে", "দাম",
    "টা", "টি", "নাকি", "আমার", "আমাকে", "দিন", "প্লিজ", "ভাই", "আপু",
    "দেখাও", "দেখান", "স্টকে", "স্টক", "এর", "মধ্যে", "টাকার", "টাকা",
    "জন্য", "ও", "আর",

    # English - auxiliary / question verbs ("do you have X?",
    # "does it come in X?", "can I get X?")
    "do", "does", "did", "have", "has", "had",
    "is", "are", "am", "was", "were", "be", "been", "being",
    "will", "would", "can", "could", "should", "shall", "may",
    "might", "must", "let",
    # English - pronouns
    "i", "me", "my", "we", "us", "our", "you", "your", "he", "she",
    "it", "its", "they", "them", "their", "this", "that", "these",
    "those", "there", "here",
    # English - question words
    "what", "which", "where", "when", "how", "who", "whom", "why",
    # English - quantity / existence
    "any", "some", "much", "many", "all", "everything", "anything",
    "one", "ones",
    # English - commerce-question filler verbs ("I want X",
    # "looking for X", "got X?", "show me X")
    "want", "wanted", "need", "needed", "looking", "look", "got",
    "get", "getting", "give", "giving", "tell", "show", "find",
    "search", "searching", "buy", "order", "available", "stock",
    "instock",
    # English - articles / prepositions / conjunctions
    "the", "a", "an", "of", "for", "to", "with", "in", "on", "at",
    "from", "by", "about", "and", "or", "under", "below", "less",
    "than", "within", "over", "above", "around", "between",
    "taka", "tk", "bdt", "cost", "costs",
    # English - greetings / politeness
    "hello", "hi", "hey", "thanks", "thank",
}


_PUNCTUATION = ".,!?;:()[]{}\"'“”‘’—–…"


def strip_stopwords(terms: list[str]) -> list[str]:
    """Filter out filler words, keeping only meaningful search terms.

    Punctuation is stripped from each token before the stopword
    check, so "have," or "(available)?" are filtered exactly like
    their bare forms.
    """
    filtered = []
    for term in terms:
        cleaned = term.strip(_PUNCTUATION)
        if not cleaned:
            continue
        if cleaned.lower() in STOPWORDS:
            continue
        filtered.append(cleaned)
    return filtered
