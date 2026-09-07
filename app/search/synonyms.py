"""Search term synonym expansion for product search."""

from rapidfuzz import fuzz

SEARCH_SYNONYMS: dict[str, list[str]] = {
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
    "কালো": ["কালো", "black"], "সাদা": ["সাদা", "white"],
    "লাল": ["লাল", "red"], "নীল": ["নীল", "blue"],
    "সবুজ": ["সবুজ", "green"], "হলুদ": ["হলুদ", "yellow"],
    "গোলাপি": ["গোলাপি", "pink"], "ধূসর": ["ধূসর", "gray", "grey"],
    "বাদামী": ["বাদামী", "brown"], "বেগুনি": ["বেগুনি", "purple", "violet"],
    "মোবাইল": ["মোবাইল", "mobile", "phone", "smartphone", "cell phone"],
    "ল্যাপটপ": ["ল্যাপটপ", "laptop", "notebook"],
    "হেডফোন": ["হেডফোন", "headphone", "headphones", "earphone", "earbuds"],
    "চার্জার": ["চার্জার", "charger", "adapter"],
    "টেলিভিশন": ["টেলিভিশন", "television", "tv", "led tv"],
    "ক্যামেরা": ["ক্যামেরা", "camera"],
    "স্মার্টওয়াচ": ["স্মার্টওয়াচ", "smartwatch", "smart watch"],
    "পাওয়ার ব্যাংক": ["পাওয়ার ব্যাংক", "power bank", "powerbank"],
    "ফ্রিজ": ["ফ্রিজ", "fridge", "refrigerator"],
    "এসি": ["এসি", "ac", "air conditioner"],
    "ব্লেন্ডার": ["ব্লেন্ডার", "blender", "mixer grinder"],
    "রাইস কুকার": ["রাইস কুকার", "rice cooker"],
    "সাবান": ["সাবান", "soap"], "শ্যাম্পু": ["শ্যাম্পু", "shampoo"],
    "লিপস্টিক": ["লিপস্টিক", "lipstick"], "পারফিউম": ["পারফিউম", "perfume", "fragrance"],
    "ছোট": ["ছোট", "small"], "বড়": ["বড়", "large", "big"],
    "মাঝারি": ["মাঝারি", "medium"], "নতুন": ["নতুন", "new"],
    "পুরাতন": ["পুরাতন", "used", "second hand", "old"],
}


def _build_reverse_index(synonym_groups: dict[str, list[str]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for key, synonyms in synonym_groups.items():
        group = set(synonyms) | {key}
        for member in {s.lower() for s in group}:
            index[member] = group
    return index


_REVERSE_INDEX = _build_reverse_index(SEARCH_SYNONYMS)


def expand_terms(terms: list[str]) -> list[str]:
    """Expand exact synonyms and close typo variants generically."""
    expanded: set[str] = set()
    vocabulary = list(_REVERSE_INDEX)

    for term in terms:
        if not term:
            continue
        normalized = term.strip().lower()
        if not normalized:
            continue
        expanded.add(term.strip())

        group = _REVERSE_INDEX.get(normalized)
        if group:
            expanded.update(group)
            continue

        # Deterministic typo tolerance before any LLM call. A high threshold
        # avoids broadening ordinary product names into unrelated synonyms.
        if len(normalized) >= 4:
            close = max(
                vocabulary,
                key=lambda candidate: fuzz.ratio(normalized, candidate),
                default=None,
            )
            if close and fuzz.ratio(normalized, close) >= 82:
                expanded.update(_REVERSE_INDEX[close])

    return list(expanded)
