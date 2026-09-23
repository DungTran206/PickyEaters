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


def get_address_coordinates(address: str) -> Optional[Tuple[float, float]]:
    """
    Determine coordinates from address with strict city scoping
    to prevent TP.HCM street names matching Hà Nội districts.
    """
    if not address:
        return None
    norm = normalize_text(address)

    is_hcm = any(c in norm for c in ["hcm", "ho chi minh", "sai gon", "tp.hcm", "tphcm"])
    is_hanoi = any(c in norm for c in ["ha noi", "hanoi"])

    hanoi_districts = [
        "thanh xuan", "cau giay", "ba dinh", "dong da", "hai ba trung",
        "hoan kiem", "tay ho", "nam tu liem", "bac tu liem", "ha dong",
        "long bien", "hoang mai"
    ]
    hcm_districts = [
        "quan 1", "quan 3", "quan 4", "quan 5", "quan 7", "quan 8",
        "quan 10", "binh thanh", "phu nhuan", "tan binh", "thu duc"
    ]

    # If address is explicitly in TP.HCM, only check TP.HCM districts
    if is_hcm and not is_hanoi:
        for d in hcm_districts:
            if d in norm and d in DISTRICT_COORDINATES:
                return DISTRICT_COORDINATES[d]
        return DISTRICT_COORDINATES["quan 1"]

    # If address is explicitly in Hà Nội, only check Hà Nội districts
    if is_hanoi and not is_hcm:
        for d in hanoi_districts:
            if d in norm and d in DISTRICT_COORDINATES:
                return DISTRICT_COORDINATES[d]
        return DISTRICT_COORDINATES["cau giay"]

    # General check: require district indicator or word boundary to avoid matching street names
    for d_name, coords in DISTRICT_COORDINATES.items():
        if f"quan {d_name}" in norm or f"huyen {d_name}" in norm or f", {d_name}" in norm:
            return coords
        # Exact match or starts with district
        if norm.startswith(d_name):
            return coords

    # Fallback to general substring
    for d_name, coords in DISTRICT_COORDINATES.items():
        if d_name in norm:
            return coords

    # City-level fallbacks
    if is_hanoi:
        return DISTRICT_COORDINATES["cau giay"]
    if is_hcm:
        return DISTRICT_COORDINATES["quan 1"]

    return None


def calculate_distance_km(user_address: str, restaurant_address: str, default_km: float = 2.5) -> float:
    """Calculate realistic distance between user address and restaurant address."""
    c1 = get_address_coordinates(user_address)
    c2 = get_address_coordinates(restaurant_address)
    if c1 and c2:
        dist = haversine_km(c1[0], c1[1], c2[0], c2[1])
        # If in the same district, give a realistic short localized distance
        if dist < 0.5:
            if default_km and 0.5 <= default_km <= 3.5:
                return default_km
            return 1.2
        return dist
    return default_km


# ---------------------------------------------------------------------------
# Data Loading & Enrichment (Local DB + Crawled Browser PoC)
# ---------------------------------------------------------------------------

def _load_crawled_data() -> Tuple[List[Restaurant], List[Dish], List[Promotion]]:
    """Load and convert real crawled data from GrabFood and ShopeeFood."""
    crawled_restaurants: List[Restaurant] = []
    crawled_menus: List[Dish] = []
    crawled_promos: List[Promotion] = []

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
            rests = data.get("restaurants", [])
            for idx, r in enumerate(rests):
                r_id = f"{prefix}_rest_{idx+1}"
                name = r.get("restaurant_name") or f"Quán {platform} #{idx+1}"
                address = r.get("address") or ("Cầu Giấy, Hà Nội" if idx == 0 else "Ba Đình, Hà Nội")
                rating = float(r.get("rating") or 4.7)

                rest_obj = Restaurant(
                    id=r_id,
                    name=name,
                    cuisine="Fast Food" if "burger" in name.lower() or "chicken" in name.lower() else "Vietnamese",
                    rating=rating,
                    distance_km=2.0,
                    delivery_fee=15000,
                    district="Cầu Giấy" if "cầu giấy" in address.lower() else "Ba Đình",
                    platform=platform,
                    delivery_time_mins=20,
                    address=address,
                    open_hours="08:00 - 22:00"
                )
                crawled_restaurants.append(rest_obj)

                # Promotion
                if r.get("promotion"):
                    promo_obj = Promotion(
                        id=f"promo_{r_id}",
                        restaurant_id=r_id,
                        code="FLASH_SALE" if "flash" in str(r.get("promotion")).lower() else "DEAL_HOT",
                        type="discount",
                        value=15000,
                        max_discount=30000,
                        minimum_order=50000,
                        description=str(r.get("promotion"))
                    )
                    crawled_promos.append(promo_obj)

                # Menu dishes
                menu = r.get("menu", [])
                for d_idx, d in enumerate(menu):
                    dish_id = f"{r_id}_d_{d_idx+1}"
                    dish_name = d.get("dish_name", "")
                    price = int(d.get("dish_price") or 65000)
                    desc = d.get("description") or ""
                    is_spicy = bool("cay" in dish_name.lower() or "chili" in desc.lower() or "spicy" in desc.lower() or "sốt cay" in desc.lower())

                    dish_obj = Dish(
                        id=dish_id,
                        restaurant_id=r_id,
                        name=dish_name,
                        price=price,
                        spicy=is_spicy,
                        cuisine=rest_obj.cuisine,
                        category="Main",
                        ingredients=[w for w in desc.split(",") if len(w.strip()) > 2],
                        description=desc
                    )
                    crawled_menus.append(dish_obj)
        except Exception as e:
            print(f"[Search] Warning loading crawled data from {fpath}: {e}")

    return crawled_restaurants, crawled_menus, crawled_promos


def load_restaurants(data_dir: str = DATA_DIR, reload: bool = False) -> List[Restaurant]:
    global _RESTAURANTS_CACHE
    if _RESTAURANTS_CACHE is None or reload:
        file_path = os.path.join(data_dir, "restaurants.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            base_restaurants = [Restaurant(**r) for r in data]

        # Merge with real crawled restaurants
        crawled_rests, _, _ = _load_crawled_data()
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
        _, crawled_dishes, _ = _load_crawled_data()
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
            base_promos = [Promotion(**p) for p in data]

        _, _, crawled_promos = _load_crawled_data()
        existing_promo_ids = {p.id for p in base_promos}
        for cp in crawled_promos:
            if cp.id not in existing_promo_ids:
                base_promos.append(cp)
                existing_promo_ids.add(cp.id)

        _PROMOTIONS_CACHE = base_promos
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
    "bun cha": ["bun cha", "nem cua be"],
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

    # Direct phrase match with word boundary
    kw_pattern = r'\b' + re.escape(norm_kw) + r'\b'
    if re.search(kw_pattern, combined):
        return True

    # Check synonyms with word boundaries
    for key, syns in KEYWORD_SYNONYMS.items():
        if norm_kw == key or norm_kw in syns:
            for s in syns:
                s_pat = r'\b' + re.escape(s) + r'\b'
                if re.search(s_pat, combined):
                    return True
            # Predefined specific food concept: do not loosely split into words
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
    data_dir: str = DATA_DIR
) -> List[Restaurant]:
    restaurants = load_restaurants(data_dir)
    results = []
    effective_address = user_address or location

    for r in restaurants:
        distance = r.distance_km
        if effective_address and r.address:
            distance = calculate_distance_km(effective_address, r.address, default_km=r.distance_km)
            r_copy = r.model_copy(update={"distance_km": distance})
        else:
            r_copy = r

        if radius_km is not None and r_copy.distance_km > radius_km:
            continue
        if minimum_rating is not None and r_copy.rating < minimum_rating:
            continue
        if cuisine and not _match_cuisine(cuisine, r_copy.cuisine, r_copy.name):
            continue

        results.append(r_copy)

    results.sort(key=lambda x: (x.distance_km, -x.rating))
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
        if excluded_concepts and any(
            normalize_text(concept) in normalize_text(f"{d.name} {d.description} {d.category}")
            for concept in excluded_concepts
        ):
            continue
        if disliked_ingredients and is_ingredient_disliked(d.ingredients, disliked_ingredients):
            continue

        results.append(d)

    results.sort(key=lambda x: x.price)
    return results


def search_with_radius_expansion(
    user_address: str = "Cầu Giấy, Hà Nội",
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
) -> Dict[str, Any]:
    """
    Search dishes and restaurants in two stages:
    1. First stage: scan within initial_radius (default 5.0 km)
    2. If fewer than 2 distinct recommendations are found, scale up to max_radius (10.0 km).
    """
    # When keyword is specified, don't over-restrict restaurant list by cuisine initially
    rest_cuisine_filter = None if keyword else cuisine

    # Stage 1: Initial 5.0 km radius
    rests_5km = search_restaurants(
        user_address=user_address,
        radius_km=initial_radius,
        minimum_rating=minimum_rating,
        cuisine=rest_cuisine_filter,
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
        )
        dishes_5km.extend(matched)

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
        )
        dishes_10km.extend(matched)

    # If still fewer than 2 dishes, relax cuisine filter if keyword was given
    if len(dishes_10km) < 2 and cuisine and keyword:
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
            )
            for m in matched:
                if m.id not in {d.id for d in dishes_10km}:
                    dishes_10km.append(m)

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


def get_restaurant_by_id(restaurant_id: str, data_dir: str = DATA_DIR, user_address: Optional[str] = None) -> Optional[Restaurant]:
    restaurants = load_restaurants(data_dir)
    for r in restaurants:
        if r.id == restaurant_id:
            if user_address and r.address:
                dist = calculate_distance_km(user_address, r.address, default_km=r.distance_km)
                return r.model_copy(update={"distance_km": dist})
            return r
    return None


def get_dish_by_id(dish_id: str, data_dir: str = DATA_DIR) -> Optional[Dish]:
    menus = load_menus(data_dir)
    for d in menus:
        if d.id == dish_id:
            return d
    return None
