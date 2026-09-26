import json
import math
import os
import re
import unicodedata
from typing import List, Optional, Dict, Any, Tuple
from database.models import Restaurant, Dish, Promotion

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
POC_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "food-browser-poc", "artifacts", "results")

_RESTAURANTS_CACHE: Optional[List[Restaurant]] = None
_MENUS_CACHE: Optional[List[Dish]] = None
_PROMOTIONS_CACHE: Optional[List[Promotion]] = None


# ---------------------------------------------------------------------------
# Coordinate Database & Haversine Distance
# ---------------------------------------------------------------------------

DISTRICT_COORDINATES: Dict[str, Tuple[float, float]] = {
    # Hà Nội
    "cau giay": (21.0362, 105.7906),
    "ba dinh": (21.0341, 105.8239),
    "dong da": (21.0181, 105.8299),
    "hai ba trung": (21.0069, 105.8523),
    "hoan kiem": (21.0285, 105.8542),
    "tay ho": (21.0712, 105.8242),
    "thanh xuan": (20.9937, 105.8118),
    "nam tu liem": (21.0142, 105.7645),
    "bac tu liem": (21.0633, 105.7628),
    "ha dong": (20.9723, 105.7772),
    "long bien": (21.0364, 105.8925),
    "hoang mai": (20.9734, 105.8492),
    # TP.HCM
    "quan 1": (10.7769, 106.7009),
    "quan 3": (10.7844, 106.6844),
    "quan 4": (10.7634, 106.7022),
    "quan 5": (10.7554, 106.6669),
    "quan 7": (10.7340, 106.7219),
    "quan 8": (10.7423, 106.6631),
    "quan 10": (10.7746, 106.6670),
    "binh thanh": (10.8106, 106.7091),
    "phu nhuan": (10.7992, 106.6803),
    "tan binh": (10.8015, 106.6526),
    "thu duc": (10.8494, 106.7537),
}


def normalize_text(text: str) -> str:
    """Normalize Vietnamese text to lowercase without diacritics for flexible search."""
    if not text:
        return ""
    text = text.lower()
    text = text.replace("đ", "d").replace("Đ", "d")
    normalized = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return stripped.strip()


def mentions_concept(concept: str, text: str) -> bool:
    """True if `concept` appears in `text` as whole words (diacritic-insensitive).

    Whole-word matching keeps "gà" from matching "ngậy"/"bánh gạo" and "cơm" from "combo".
    """
    norm_concept = normalize_text(concept)
    if not norm_concept:
        return False
    return re.search(r"\b" + re.escape(norm_concept) + r"\b", normalize_text(text)) is not None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two GPS coordinates using Haversine formula."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


HANOI_DISTRICTS = [
    "thanh xuan", "cau giay", "ba dinh", "dong da", "hai ba trung", "hoan kiem", "tay ho",
    "nam tu liem", "bac tu liem", "ha dong", "long bien", "hoang mai",
]
HCM_DISTRICTS = [
    "quan 1", "quan 3", "quan 4", "quan 5", "quan 7", "quan 8", "quan 10",
    "binh thanh", "phu nhuan", "tan binh", "thu duc",
]

# District-level geocoding cannot measure distance inside one district; this labelled
# estimate is used for same-district pairs (distance_basis="same_district").
SAME_DISTRICT_KM = 1.5


def resolve_district(address: str) -> Optional[str]:
    """District key named in `address`, or None if it names no known district.

    Whole-word matching ("quan 1" never matches "quan 10"); when the city is stated only
    that city's districts are considered; with several matches the LAST one wins,
    since Vietnamese addresses read street → ward → district → city
    ("Hai Bà Trưng, Quận 1" is Quận 1). Never guesses a district from the city alone.
    """
    norm = normalize_text(address)
    if not norm:
        return None
    is_hcm = any(c in norm for c in ["hcm", "ho chi minh", "sai gon"])
    is_hanoi = any(c in norm for c in ["ha noi", "hanoi"])
    if is_hcm and not is_hanoi:
        pool = HCM_DISTRICTS
    elif is_hanoi and not is_hcm:
        pool = HANOI_DISTRICTS
    else:
        pool = HANOI_DISTRICTS + HCM_DISTRICTS

    best: Optional[Tuple[Tuple[int, int], str]] = None
    for district in pool:
        for match in re.finditer(r"\b" + re.escape(district) + r"\b", norm):
            key = (match.start(), len(district))
            if best is None or key > best[0]:
                best = (key, district)
    return best[1] if best else None


def get_address_coordinates(address: str) -> Optional[Tuple[float, float]]:
    """Centroid of the district named in `address`, or None if it can't be located."""
    district = resolve_district(address)
    return DISTRICT_COORDINATES.get(district) if district else None


DISTRICT_NAMES: Dict[str, str] = {
    "thanh xuan": "Thanh Xuân, Hà Nội", "cau giay": "Cầu Giấy, Hà Nội", "ba dinh": "Ba Đình, Hà Nội",
    "dong da": "Đống Đa, Hà Nội", "hai ba trung": "Hai Bà Trưng, Hà Nội", "hoan kiem": "Hoàn Kiếm, Hà Nội",
    "tay ho": "Tây Hồ, Hà Nội", "nam tu liem": "Nam Từ Liêm, Hà Nội", "bac tu liem": "Bắc Từ Liêm, Hà Nội",
    "ha dong": "Hà Đông, Hà Nội", "long bien": "Long Biên, Hà Nội", "hoang mai": "Hoàng Mai, Hà Nội",
    "quan 1": "Quận 1, TP.HCM", "quan 3": "Quận 3, TP.HCM", "quan 4": "Quận 4, TP.HCM",
    "quan 5": "Quận 5, TP.HCM", "quan 7": "Quận 7, TP.HCM", "quan 8": "Quận 8, TP.HCM",
    "quan 10": "Quận 10, TP.HCM", "binh thanh": "Bình Thạnh, TP.HCM", "phu nhuan": "Phú Nhuận, TP.HCM",
    "tan binh": "Tân Bình, TP.HCM", "thu duc": "Thủ Đức, TP.HCM",
}

# A map point farther than this from every known district centre is outside the covered area.
NEAREST_DISTRICT_MAX_KM = 6.0
# Floor for point-to-centre estimates, so a pin next to a centre isn't shown as "~0 km".
MIN_ESTIMATED_KM = 0.5

Coords = Tuple[float, float]


def nearest_district(latitude: float, longitude: float) -> Optional[str]:
    """District whose centre is closest to a map point, or None if none is within range.

    Approximation (no district boundaries): used to label a map pick, not to measure distance.
    """
    key, km = min(
        ((d, haversine_km(latitude, longitude, *c)) for d, c in DISTRICT_COORDINATES.items()),
        key=lambda pair: pair[1],
    )
    return key if km <= NEAREST_DISTRICT_MAX_KM else None


def district_label(address: Optional[str], coords: Optional[Coords] = None) -> str:
    """Display name of the user's district ("Thanh Xuân, Hà Nội"), or "" if unknown."""
    key = nearest_district(*coords) if coords is not None else resolve_district(address or "")
    return DISTRICT_NAMES.get(key, "") if key else ""


def is_locatable(address: Optional[str], coords: Optional[Coords] = None) -> bool:
    """True if we can estimate distances from this delivery location."""
    return coords is not None or bool(address and resolve_district(address))


def estimate_distance(
    user_address: str, restaurant_address: str, user_coords: Optional[Coords] = None
) -> Tuple[Optional[float], str]:
    """(km, basis) from the user to a restaurant.

    With user_coords (map pick) the distance runs from that exact point to the centre of the
    restaurant's district; otherwise both sides are district-level.
    basis: "district_centroid" (estimate using district centres), "same_district"
    (SAME_DISTRICT_KM estimate) or "unknown" (km is None — a side can't be located).
    """
    rest_district = resolve_district(restaurant_address)
    if not rest_district:
        return None, "unknown"
    if user_coords is not None:
        km = haversine_km(*user_coords, *DISTRICT_COORDINATES[rest_district])
        return max(km, MIN_ESTIMATED_KM), "district_centroid"
    user_district = resolve_district(user_address)
    if not user_district:
        return None, "unknown"
    if user_district == rest_district:
        return SAME_DISTRICT_KM, "same_district"
    return haversine_km(*DISTRICT_COORDINATES[user_district], *DISTRICT_COORDINATES[rest_district]), "district_centroid"


def _with_distance(restaurant: Restaurant, user_address: str, user_coords: Optional[Coords] = None) -> Restaurant:
    km, basis = estimate_distance(user_address, restaurant.address, user_coords)
    if km is None:
        return restaurant.model_copy(update={"distance_basis": "unknown"})
    return restaurant.model_copy(update={"distance_km": km, "distance_basis": basis})


# ---------------------------------------------------------------------------
# Data Loading & Enrichment (Local DB + Crawled Browser PoC)
# ---------------------------------------------------------------------------

# Crawled records often lack a delivery fee / delivery time. We keep a clearly-labelled
# estimate so a total price can be computed, and record it in Restaurant.estimated_fields.
ESTIMATED_DELIVERY_FEE = 15000
ESTIMATED_DELIVERY_MINS = 20


def _district_from_address(address: str) -> str:
    """The address segment naming a known district (source text), or "" if none."""
    for part in address.split(","):
        if any(key in normalize_text(part) for key in DISTRICT_COORDINATES):
            return part.strip()
    return ""


def _crawled_restaurant(r: Dict[str, Any], platform: str, r_id: str) -> Optional[Restaurant]:
    """Convert one crawled record, using only source values.

    - No address / address we cannot locate → skipped (distance and delivery area unknown).
    - Missing or out-of-range rating → None (never a made-up rating).
    - Missing delivery fee / time → labelled estimate in estimated_fields.
    - Missing cuisine → name-based guess, labelled as estimated.
    """
    address = (r.get("address") or "").strip()
    if not address or get_address_coordinates(address) is None:
        return None

    name = r.get("restaurant_name") or r.get("name") or ""
    if not name:
        return None

    raw_rating = r.get("rating")
    rating = float(raw_rating) if raw_rating is not None and 1.0 <= float(raw_rating) <= 5.0 else None

    estimated: List[str] = []
    delivery_fee = r.get("delivery_fee")
    if delivery_fee is None:
        delivery_fee = ESTIMATED_DELIVERY_FEE
        estimated.append("delivery_fee")
    delivery_mins = r.get("delivery_time_mins")
    if delivery_mins is None:
        delivery_mins = ESTIMATED_DELIVERY_MINS
        estimated.append("delivery_time_mins")
    cuisine = r.get("cuisine")
    if not cuisine:
        lowered = name.lower()
        cuisine = "Fast Food" if "burger" in lowered or "chicken" in lowered else "Vietnamese"
        estimated.append("cuisine")

    return Restaurant(
        id=r_id,
        name=name,
        cuisine=cuisine,
        rating=rating,
        # Recomputed from the address at query time; only used if the user's address can't be located.
        distance_km=float(r.get("distance_km") or 2.0),
        delivery_fee=int(delivery_fee),
        district=_district_from_address(address),
        platform=platform,
        delivery_time_mins=int(delivery_mins),
        address=address,
        open_hours=r.get("open_hours") or "",
        estimated_fields=estimated,
    )


def _load_crawled_data() -> Tuple[List[Restaurant], List[Dish]]:
    """Load crawled GrabFood/ShopeeFood data without inventing missing facts.

    Promotion text such as "Flash Sale" carries no amount or conditions, so no
    Promotion objects are created from it.
    """
    crawled_restaurants: List[Restaurant] = []
    crawled_menus: List[Dish] = []

    files = [
        (os.path.join(POC_RESULTS_DIR, "shopeefood.json"), "ShopeeFood", "sf"),
        (os.path.join(POC_RESULTS_DIR, "grabfood.json"), "GrabFood", "gf"),
        (os.path.join(POC_RESULTS_DIR, "shopeefood_thanhxuan.json"), "ShopeeFood", "sf_tx"),
    ]

    for fpath, platform, prefix in files:
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            skipped = 0
            for idx, r in enumerate(data.get("restaurants", [])):
                r_id = f"{prefix}_rest_{idx+1}"
                rest_obj = _crawled_restaurant(r, platform, r_id)
                if rest_obj is None:
                    skipped += 1
                    continue
                crawled_restaurants.append(rest_obj)

                for d_idx, d in enumerate(r.get("menu", [])):
                    dish_name = d.get("dish_name", "")
                    price = d.get("dish_price")
                    if not dish_name or price is None:
                        continue  # no invented prices
                    desc = d.get("description") or ""
                    is_spicy = bool("cay" in dish_name.lower() or "chili" in desc.lower() or "spicy" in desc.lower() or "sốt cay" in desc.lower())
                    crawled_menus.append(Dish(
                        id=f"{r_id}_d_{d_idx+1}",
                        restaurant_id=r_id,
                        name=dish_name,
                        price=int(price),
                        spicy=is_spicy,
                        cuisine=rest_obj.cuisine,
                        category="Main",
                        # No ingredient list in the crawl: derived from the description text.
                        ingredients=[w for w in desc.split(",") if len(w.strip()) > 2],
                        ingredients_source="description",
                        description=desc,
                    ))
            if skipped:
                print(f"[Search] Skipped {skipped} crawled restaurants without a locatable address in {os.path.basename(fpath)}")
        except Exception as e:
            print(f"[Search] Warning loading crawled data from {fpath}: {e}")

    return crawled_restaurants, crawled_menus


def load_restaurants(data_dir: str = DATA_DIR, reload: bool = False) -> List[Restaurant]:
    global _RESTAURANTS_CACHE
    if _RESTAURANTS_CACHE is None or reload:
        file_path = os.path.join(data_dir, "restaurants.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            base_restaurants = [Restaurant(**r) for r in data]

        # Merge with real crawled restaurants
        crawled_rests, _ = _load_crawled_data()
        existing_names = {normalize_text(r.name) for r in base_restaurants}
        for cr in crawled_rests:
            if normalize_text(cr.name) not in existing_names:
                base_restaurants.append(cr)
                existing_names.add(normalize_text(cr.name))

        _RESTAURANTS_CACHE = base_restaurants
    return _RESTAURANTS_CACHE


def load_menus(data_dir: str = DATA_DIR, reload: bool = False) -> List[Dish]:
    global _MENUS_CACHE
    if _MENUS_CACHE is None or reload:
        file_path = os.path.join(data_dir, "menus.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            base_menus = [Dish(**d) for d in data]

        # Merge with crawled dishes
        _, crawled_dishes = _load_crawled_data()
        existing_dish_ids = {d.id for d in base_menus}
        for cd in crawled_dishes:
            if cd.id not in existing_dish_ids:
                base_menus.append(cd)
                existing_dish_ids.add(cd.id)

        _MENUS_CACHE = base_menus
    return _MENUS_CACHE


def load_promotions(data_dir: str = DATA_DIR, reload: bool = False) -> List[Promotion]:
    global _PROMOTIONS_CACHE
    if _PROMOTIONS_CACHE is None or reload:
        file_path = os.path.join(data_dir, "promotions.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _PROMOTIONS_CACHE = [Promotion(**p) for p in data]
    return _PROMOTIONS_CACHE


# ---------------------------------------------------------------------------
# Search Queries & Multi-stage Radius Expansion (5km -> 10km)
# ---------------------------------------------------------------------------

def is_ingredient_disliked(dish_ingredients: List[str], disliked_list: List[str]) -> bool:
    """Check if any ingredient matches user's disliked ingredients."""
    if not disliked_list:
        return False

    synonyms = {
        "onion": ["onion", "hanh", "hanh tay", "hanh la", "scallion", "fried onion"],
        "hanh": ["onion", "hanh", "hanh tay", "hanh la", "scallion", "fried onion"],
        "hanh tay": ["onion", "hanh tay"],
        "scallion": ["scallion", "hanh la", "onion"],
        "chili": ["chili", "ot", "sa te"],
        "ot": ["chili", "ot", "sa te"],
        "garlic": ["garlic", "toi"],
        "toi": ["garlic", "toi"],
        "beef": ["beef", "bo", "thit bo"],
        "pork": ["pork", "heo", "thit heo", "lon"],
        "shrimp": ["shrimp", "tom"],
    }

    norm_disliked = set()
    for item in disliked_list:
        clean = normalize_text(item)
        norm_disliked.add(clean)
        for syn_key, syn_vals in synonyms.items():
            if clean in syn_key or syn_key in clean:
                for v in syn_vals:
                    norm_disliked.add(normalize_text(v))

    for ing in dish_ingredients:
        norm_ing = normalize_text(ing)
        for dis in norm_disliked:
            if dis in norm_ing or norm_ing in dis:
                return True

    return False


CUISINE_SYNONYMS = {
    "western": ["western", "fast food", "burger", "pizza", "fried chicken", "do tay", "mi y", "taco"],
    "korean": ["korean", "han quoc", "han", "k-pub", "tokbokki", "kimchi", "korea"],
    "japanese": ["japanese", "nhat ban", "nhat", "sushi", "ramen", "udon"],
    "thai": ["thai", "tom yum", "pad thai"],
    "vietnamese": ["vietnamese", "viet nam", "viet", "pho", "bun", "com", "banh mi", "ha thanh", "sai gon"],
    "vegetarian": ["vegetarian", "chay", "thuc duong"]
}

KEYWORD_SYNONYMS = {
    "xoi": ["xoi", "xoi xeo", "xoi ga", "xoi chim", "xoi suon", "xoi thit", "xoi bap", "xoi ngo", "xoi man", "xoi pate", "xoi thap cam", "xoi vo", "xoi nep"],
    "xoi xeo": ["xoi xeo", "xoi"],
    "xoi chim": ["xoi chim", "xoi"],
    "xoi suon": ["xoi suon", "xoi suon cay", "xoi"],
    "xoi ga": ["xoi ga", "xoi ga xe", "xoi"],
    "xoi thit": ["xoi thit", "xoi thit kho", "xoi"],
    "xoi bap": ["xoi bap", "xoi ngo", "xoi"],
    "xoi ngo": ["xoi ngo", "xoi bap", "xoi"],
    "ga ran": ["ga ran", "fried chicken", "ga xoi mo", "ga gion", "dui ga", "ga vien", "chicken", "ga"],
    "ga": ["ga", "chicken", "ga ran", "ga xoi mo", "ga xe", "dui ga"],
    "com tam": ["com tam", "com suon", "com ga", "com"],
    "com ga": ["com ga", "com ga xoi mo", "com dui ga"],
    "com suon": ["com suon", "com tam", "suon"],
    "com": ["com", "rice"],
    "bun bo": ["bun bo", "bun bo hue"],
    "bun cha": ["bun cha"],
    "pho": ["pho", "pho bo", "pho ga", "pho cuon", "pho tai"],
    "tokbokki": ["tokbokki", "topokki", "banh gao", "rice cake"],
    "mi cay": ["mi cay", "ramen", "mi"],
    "burger": ["burger", "hamburger"],
    "pizza": ["pizza"],
    "banh mi": ["banh mi", "bami"]
}


def _match_cuisine(target_cuisine: Optional[str], item_cuisine: str, item_name: str = "") -> bool:
    if not target_cuisine:
        return True
    norm_target = normalize_text(target_cuisine)
    norm_item_cuisine = normalize_text(item_cuisine)
    norm_item_name = normalize_text(item_name)

    target_pattern = r"(?<!\w)" + re.escape(norm_target) + r"(?!\w)"
    if re.search(target_pattern, norm_item_cuisine) or re.search(target_pattern, norm_item_name):
        return True

    for key, syns in CUISINE_SYNONYMS.items():
        target_matches_cuisine = norm_target == key or any(
            re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", norm_target) for s in syns
        )
        if target_matches_cuisine:
            if any(
                re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", value)
                for s in syns for value in (norm_item_cuisine, norm_item_name)
            ):
                return True
    return False


def _match_keyword(keyword: Optional[str], dish_name: str, dish_desc: str = "", dish_cuisine: str = "") -> bool:
    if not keyword:
        return True
    norm_kw = normalize_text(keyword).strip()
    norm_name = normalize_text(dish_name)
    norm_desc = normalize_text(dish_desc)
    norm_cui = normalize_text(dish_cuisine)
    combined = f"{norm_name} {norm_desc} {norm_cui}"

    # Disambiguation: "cơm gà xối mỡ" is fried oil basting rice, not sticky rice ("xôi")
    if norm_kw in ["xoi", "xoi xeo", "xoi chim", "xoi ga", "xoi suon"] and "xoi mo" in combined and "com" in combined:
        if not any(x in combined for x in ["xoi xeo", "xoi ga", "xoi chim", "xoi suon", "xoi thit", "xoi bap", "xoi ngo", "xoi man", "xoi pate", "xoi nep", "xoi vo"]):
            return False

    # Disambiguation: "phô mai" (cheese) or "phố cổ / phố" (street) is not "phở" (noodle soup)
    if norm_kw in ["pho", "pho bo", "pho ga", "pho tai"] and any(x in combined for x in ["pho mai", "pho co", "khu pho"]):
        if not re.search(r'\b(pho bo|pho ga|pho tai|pho nam|pho xao|pho tron|pho cuon|quan pho|banh pho)\b', combined):
            return False

    # Disambiguation: "miền nam/bắc/trung" (region) is not "miến" (glass noodles)
    if norm_kw in ["mien", "mien ga", "mien tron", "mien xao"] and any(r in combined for r in ["mien nam", "mien bac", "mien trung", "mien tay"]):
        if not re.search(r'\b(mien ga|mien luon|mien tron|mien xao|mien mang|bat mien|to mien)\b', combined):
            return False

    # Disambiguation: "chảo / trên chảo" (frying pan) is not "cháo" (porridge)
    if norm_kw in ["chao", "chao suon", "chao ga", "chao long"] and any(p in combined for p in ["tren chao", "chao bo", "chao nong", "chao gang"]):
        if not re.search(r'\b(chao suon|chao ga|chao long|chao dinh duong|chao vit|chao ca|chao ngo|bat chao|to chao|quan chao)\b', combined):
            return False

    # Disambiguation: "cánh gà / cánh gián" (wing) is not "canh" (soup)
    if norm_kw in ["canh", "bat canh", "to canh"] and any(c in combined for c in ["canh gian", "canh ga", "canh vit"]):
        if not re.search(r'\b(canh chua|canh rong bien|canh kho qua|canh rau|canh thit|canh ngao|canh cua|canh bau|canh bi|canh kim chi|bat canh|to canh)\b', combined):
            return False

    # Direct phrase match with word boundary
    kw_pattern = r'\b' + re.escape(norm_kw) + r'\b'
    if re.search(kw_pattern, combined):
        return True

    # Check synonyms with word boundaries
    for key, syns in KEYWORD_SYNONYMS.items():
        if norm_kw == key:
            for s in syns:
                s_pat = r'\b' + re.escape(s) + r'\b'
                if re.search(s_pat, combined):
                    return True
            return False
        elif norm_kw in syns:
            s_pat = r'\b' + re.escape(norm_kw) + r'\b'
            if re.search(s_pat, combined):
                return True
            return False

    # Multi-word match: all non-stopwords from query must be in text
    stop_words = {"mon", "ngon", "tim", "cho", "an", "do", "va", "hoac", "quan", "danh"}
    kw_words = [w for w in norm_kw.split() if w not in stop_words and len(w) >= 2]
    if kw_words:
        all_matched = all(re.search(r'\b' + re.escape(w) + r'\b', combined) for w in kw_words)
        if all_matched:
            return True

    return False


def search_restaurants(
    location: Optional[str] = None,
    user_address: Optional[str] = None,
    radius_km: Optional[float] = None,
    minimum_rating: Optional[float] = None,
    cuisine: Optional[str] = None,
    data_dir: str = DATA_DIR,
    user_coords: Optional[Coords] = None,
) -> List[Restaurant]:
    restaurants = load_restaurants(data_dir)
    results = []
    effective_address = user_address or location or ""
    has_location = bool(effective_address) or user_coords is not None

    for r in restaurants:
        r_copy = _with_distance(r, effective_address, user_coords) if has_location else r

        if radius_km is not None and (r_copy.distance_basis == "unknown" or r_copy.distance_km > radius_km):
            continue  # an unknown distance can't be shown to be within the radius
        if minimum_rating is not None and (r_copy.rating is None or r_copy.rating < minimum_rating):
            continue
        if cuisine and not _match_cuisine(cuisine, r_copy.cuisine, r_copy.name):
            continue

        results.append(r_copy)

    results.sort(key=lambda x: (x.distance_km, -(x.rating or 0.0)))
    return results


def search_dishes(
    keyword: Optional[str] = None,
    cuisine: Optional[str] = None,
    max_price: Optional[int] = None,
    min_price: Optional[int] = None,
    spicy: Optional[bool] = None,
    restaurant_id: Optional[str] = None,
    disliked_ingredients: Optional[List[str]] = None,
    excluded_concepts: Optional[List[str]] = None,
    semantic_keywords: Optional[List[str]] = None,
    data_dir: str = DATA_DIR
) -> List[Dish]:
    dishes = load_menus(data_dir)
    results = []

    for d in dishes:
        if restaurant_id and d.restaurant_id != restaurant_id:
            continue
        if max_price is not None and d.price > max_price:
            continue
        if min_price is not None and d.price < min_price:
            continue
        if spicy is not None and d.spicy != spicy:
            continue
        if cuisine and not _match_cuisine(cuisine, d.cuisine, d.description):
            continue
        if keyword and not _match_keyword(keyword, d.name, d.description, d.cuisine):
            continue
        if not keyword and semantic_keywords:
            if not any(_match_keyword(sk, d.name, d.description, d.cuisine) for sk in semantic_keywords):
                continue
        if excluded_concepts and any(
            mentions_concept(concept, f"{d.name} {d.description} {d.category}")
            for concept in excluded_concepts
        ):
            continue
        if disliked_ingredients and is_ingredient_disliked(d.ingredients, disliked_ingredients):
            continue

        results.append(d)

    results.sort(key=lambda x: x.price)
    return results


def search_with_radius_expansion(
    user_address: str = "",
    keyword: Optional[str] = None,
    cuisine: Optional[str] = None,
    max_price: Optional[int] = None,
    min_price: Optional[int] = None,
    spicy: Optional[bool] = None,
    disliked_ingredients: Optional[List[str]] = None,
    excluded_concepts: Optional[List[str]] = None,
    minimum_rating: Optional[float] = None,
    initial_radius: float = 5.0,
    max_radius: float = 10.0,
    semantic_keywords: Optional[List[str]] = None,
    secondary_keywords: Optional[List[str]] = None,
    user_coords: Optional[Coords] = None,
) -> Dict[str, Any]:
    """
    Search dishes and restaurants in two stages:
    1. First stage: scan within initial_radius (default 5.0 km)
    2. If fewer than 2 distinct recommendations are found, scale up to max_radius (10.0 km).
    """
    # When keyword or semantic_keywords is specified, don't over-restrict restaurant list by cuisine initially
    has_dish_hint = bool(keyword or semantic_keywords)
    rest_cuisine_filter = None if has_dish_hint else cuisine

    # Stage 1: Initial 5.0 km radius
    rests_5km = search_restaurants(
        user_address=user_address,
        radius_km=initial_radius,
        minimum_rating=minimum_rating,
        cuisine=rest_cuisine_filter,
        user_coords=user_coords,
    )
    rest_ids_5km = {r.id: r for r in rests_5km}

    dishes_5km = []
    for r_id in rest_ids_5km:
        matched = search_dishes(
            keyword=keyword,
            cuisine=cuisine,
            max_price=max_price,
            min_price=min_price,
            spicy=spicy,
            restaurant_id=r_id,
            disliked_ingredients=disliked_ingredients,
            excluded_concepts=excluded_concepts,
            semantic_keywords=semantic_keywords,
        )
        dishes_5km.extend(matched)
        if matched and secondary_keywords:
            for sk in secondary_keywords:
                sec_matched = search_dishes(
                    keyword=sk,
                    restaurant_id=r_id,
                    disliked_ingredients=disliked_ingredients,
                    excluded_concepts=excluded_concepts,
                )
                dishes_5km.extend(sec_matched)

    # Check if we have enough options in 5km (at least 2)
    if len(dishes_5km) >= 2:
        return {
            "dishes": dishes_5km,
            "restaurants": rests_5km,
            "search_radius_km": initial_radius,
            "is_radius_expanded": False,
            "message": f"Tìm thấy {len(dishes_5km)} món phù hợp ngay trong bán kính {initial_radius}km quanh {user_address}."
        }

    # Stage 2: Scale up to 10.0 km radius
    rests_10km = search_restaurants(
        user_address=user_address,
        radius_km=max_radius,
        minimum_rating=minimum_rating,
        cuisine=rest_cuisine_filter,
        user_coords=user_coords,
    )
    rest_ids_10km = {r.id: r for r in rests_10km}

    dishes_10km = []
    for r_id in rest_ids_10km:
        matched = search_dishes(
            keyword=keyword,
            cuisine=cuisine,
            max_price=max_price,
            min_price=min_price,
            spicy=spicy,
            restaurant_id=r_id,
            disliked_ingredients=disliked_ingredients,
            excluded_concepts=excluded_concepts,
            semantic_keywords=semantic_keywords,
        )
        dishes_10km.extend(matched)
        if matched and secondary_keywords:
            for sk in secondary_keywords:
                sec_matched = search_dishes(
                    keyword=sk,
                    restaurant_id=r_id,
                    disliked_ingredients=disliked_ingredients,
                    excluded_concepts=excluded_concepts,
                )
                dishes_10km.extend(sec_matched)

    # If still fewer than 2 dishes, relax cuisine filter if dish hint was given
    if len(dishes_10km) < 2 and cuisine and (keyword or semantic_keywords):
        for r_id in rest_ids_10km:
            matched = search_dishes(
                keyword=keyword,
                cuisine=None,
                max_price=max_price,
                min_price=min_price,
                spicy=spicy,
                restaurant_id=r_id,
                disliked_ingredients=disliked_ingredients,
                excluded_concepts=excluded_concepts,
                semantic_keywords=semantic_keywords,
            )
            dishes_10km.extend(matched)
            if matched and secondary_keywords:
                for sk in secondary_keywords:
                    sec_matched = search_dishes(
                        keyword=sk,
                        restaurant_id=r_id,
                        disliked_ingredients=disliked_ingredients,
                        excluded_concepts=excluded_concepts,
                    )
                    dishes_10km.extend(sec_matched)
            for m in matched:
                if m.id not in {d.id for d in dishes_10km}:
                    dishes_10km.append(m)

    # If 0 dishes found in 10km and max_price was set, check if dishes exist without max_price
    # so VALIDATE and RE-PLAN layers can detect budget_too_tight with structured evidence.
    if len(dishes_10km) == 0 and max_price is not None and (keyword or semantic_keywords):
        for r_id in rest_ids_10km:
            unbudgeted = search_dishes(
                keyword=keyword,
                cuisine=cuisine,
                max_price=None,
                restaurant_id=r_id,
                disliked_ingredients=disliked_ingredients,
                excluded_concepts=excluded_concepts,
                semantic_keywords=semantic_keywords,
            )
            dishes_10km.extend(unbudgeted)

    return {
        "dishes": dishes_10km,
        "restaurants": rests_10km,
        "search_radius_km": max_radius,
        "is_radius_expanded": True,
        "message": f"Bán kính 5.0km có ít lựa chọn, hệ thống đã tự động mở rộng bán kính lên {max_radius}km quanh {user_address} để tìm thêm món ngon cho bạn."
    }


def get_promotions(restaurant_id: Optional[str] = None, data_dir: str = DATA_DIR) -> List[Promotion]:
    promotions = load_promotions(data_dir)
    if not restaurant_id:
        return promotions
    return [p for p in promotions if p.restaurant_id == restaurant_id]


def get_restaurant_by_id(
    restaurant_id: str,
    data_dir: str = DATA_DIR,
    user_address: Optional[str] = None,
    user_coords: Optional[Coords] = None,
) -> Optional[Restaurant]:
    restaurants = load_restaurants(data_dir)
    for r in restaurants:
        if r.id == restaurant_id:
            if user_address or user_coords is not None:
                return _with_distance(r, user_address or "", user_coords)
            return r
    return None


def get_dish_by_id(dish_id: str, data_dir: str = DATA_DIR) -> Optional[Dish]:
    menus = load_menus(data_dir)
    for d in menus:
        if d.id == dish_id:
            return d
    return None
