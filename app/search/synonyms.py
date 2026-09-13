"""Search term synonym expansion for product search."""

SEARCH_SYNONYMS: dict[str, list[str]] = {
    # --- Footwear & apparel ---
    "জুতা": ["জুতা", "shoe", "shoes", "footwear"],
    "স্যান্ডেল": ["স্যান্ডেল", "sandal", "sandals", "slipper", "slippers"],
    "শার্ট": ["শার্ট", "shirt", "shirts"],
    "প্যান্ট": ["প্যান্ট", "pant", "pants", "trouser", "trousers"],
    "টি-শার্ট": ["টি-শার্ট", "t-shirt", "tshirt", "tee"],
    "শাড়ি": ["শাড়ি", "saree", "sari"],
    "থ্রি-পিস": ["থ্রি-পিস", "three piece", "3 piece", "unstitched"],
    "পাঞ্জাবি": ["পাঞ্জাবি", "panjabi", "punjabi", "kurta"],
    "জ্যাকেট": ["জ্যাকেট", "jacket", "hoodie"],
    "ব্যাগ": ["ব্যাগ", "bag", "bags", "handbag", "backpack"],

    # --- Colors ---
    "কালো": ["কালো", "black"],
    "সাদা": ["সাদা", "white"],
    "লাল": ["লাল", "red"],
    "নীল": ["নীল", "blue"],
    "সবুজ": ["সবুজ", "green"],
    "হলুদ": ["হলুদ", "yellow"],
    "গোলাপি": ["গোলাপি", "pink"],
    "ধূসর": ["ধূসর", "gray", "grey"],
    "বাদামী": ["বাদামী", "brown"],
    "বেগুনি": ["বেগুনি", "purple", "violet"],

    # --- Electronics ---
    "মোবাইল": ["মোবাইল", "mobile", "phone", "smartphone", "cell phone"],
    "ল্যাপটপ": ["ল্যাপটপ", "laptop", "notebook"],
    "হেডফোন": ["হেডফোন", "headphone", "headphones", "earphone", "earbuds"],
    "চার্জার": ["চার্জার", "charger", "adapter"],
    "টেলিভিশন": ["টেলিভিশন", "television", "tv", "led tv"],
    "ক্যামেরা": ["ক্যামেরা", "camera"],
    "স্মার্টওয়াচ": ["স্মার্টওয়াচ", "smartwatch", "smart watch"],
    "পাওয়ার ব্যাংক": ["পাওয়ার ব্যাংক", "power bank", "powerbank"],

    # --- Home & kitchen ---
    "ফ্রিজ": ["ফ্রিজ", "fridge", "refrigerator"],
    "এসি": ["এসি", "ac", "air conditioner"],
    "ব্লেন্ডার": ["ব্লেন্ডার", "blender", "mixer grinder"],
    "রাইস কুকার": ["রাইস কুকার", "rice cooker"],

    # --- Beauty & personal care ---
    "সাবান": ["সাবান", "soap"],
    "শ্যাম্পু": ["শ্যাম্পু", "shampoo"],
    "লিপস্টিক": ["লিপস্টিক", "lipstick"],
    "পারফিউম": ["পারফিউম", "perfume", "fragrance"],

    # --- Sizes / general qualifiers ---
    "ছোট": ["ছোট", "small"],
    "বড়": ["বড়", "large", "big"],
    "মাঝারি": ["মাঝারি", "medium"],
    "নতুন": ["নতুন", "new"],
    "পুরাতন": ["পুরাতন", "used", "second hand", "old"],
}


def _build_reverse_index(
    synonym_groups: dict[str, list[str]],
) -> dict[str, set[str]]:
    """
    Build a lookup so ANY term (Bengali or English, any case)
    maps to its full synonym group.

    e.g. "shoe" -> {"জুতা", "shoe", "shoes", "footwear"}
         "কালো" -> {"কালো", "black"}
    """
    index: dict[str, set[str]] = {}

    for key, synonyms in synonym_groups.items():
        group = set(synonyms) | {key}
        normalized_group = {s.lower() for s in group}

        for member in normalized_group:
            index[member] = group

    return index


# Built once at import time.
_REVERSE_INDEX = _build_reverse_index(SEARCH_SYNONYMS)

# Lowercased index keys, used by the fuzzy typo fallback.
_FUZZY_KEYS = list(_REVERSE_INDEX.keys())

# A typo must be at least this similar (0-100) to a known term before
# its synonym group is attached. fuzz.ratio is InDel-based, so a
# transposed pair ("laptpo" vs "laptop", 6 chars) scores ~83.3. A
# cutoff of 78 covers single edits on words of 5+ chars (1-1/5=80)
# while refusing unrelated short words ("shirt"/"shoes" ratio is 60).
_FUZZY_THRESHOLD = 78.0


def _fuzzy_lookup(normalized: str) -> set[str] | None:
    """
    Best-effort typo tolerance: find the closest known synonym term
    and return its group. Uses rapidfuzz's token-free ratio which is
    edit-distance aware enough for single typos ("laptpo" -> "laptop").
    Returns None when nothing is close enough.
    """
    try:
        from rapidfuzz import process, fuzz
    except ImportError:  # pragma: no cover - rapidfuzz is a hard dep
        return None

    if not _FUZZY_KEYS or len(normalized) < 4:
        return None

    matches = process.extract(
        normalized,
        _FUZZY_KEYS,
        scorer=fuzz.ratio,
        limit=1,
        score_cutoff=_FUZZY_THRESHOLD,
    )

    if not matches:
        return None

    best_key = matches[0][0]
    return _REVERSE_INDEX.get(best_key)


def expand_terms(terms: list[str]) -> list[str]:
    """
    Expand a list of search terms into all their known synonyms
    (Bengali + English), so search matches products regardless of
    which language/word the user typed. Terms that exactly match a
    known synonym word also absorb common single-typo variants of
    themselves (fuzzy fallback, e.g. "laptpo" -> "laptop" group).

    Example:
        expand_terms(["shoe", "black"])
        -> ["shoe", "shoes", "footwear", "জুতা", "black", "কালো"]
    """
    expanded: set[str] = set()

    for term in terms:
        if not term:
            continue

        normalized = term.strip().lower()
        expanded.add(term.strip())

        group = _REVERSE_INDEX.get(normalized)
        if group is None:
            group = _fuzzy_lookup(normalized)

        if group:
            expanded.update(group)

    return list(expanded)