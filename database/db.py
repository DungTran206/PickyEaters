import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional
from database.models import UserPreference

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "food_agent.db"))
USERS_SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")


def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            name TEXT DEFAULT 'Bạn',
            district TEXT DEFAULT 'Cầu Giấy',
            address TEXT DEFAULT 'Cầu Giấy, Hà Nội',
            preferred_cuisines TEXT,
            preferred_flavors TEXT,
            disliked_ingredients TEXT,
            budget INTEGER,
            minimum_rating REAL,
            preferred_distance REAL,
            dietary_restrictions TEXT,
            liked_dishes TEXT,
            disliked_dishes TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()

    # Migration for existing DBs if columns are missing
    for col, col_type, default_val in [
        ("name", "TEXT", "'Bạn'"),
        ("district", "TEXT", "'Cầu Giấy'"),
        ("address", "TEXT", "'Cầu Giấy, Hà Nội'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE user_preferences ADD COLUMN {col} {col_type} DEFAULT {default_val}")
            conn.commit()
        except Exception:
            pass

    # Seed users if empty
    cursor.execute("SELECT COUNT(*) FROM user_preferences")
    count = cursor.fetchone()[0]
    if count == 0 and os.path.exists(USERS_SEED_PATH):
        try:
            with open(USERS_SEED_PATH, "r", encoding="utf-8") as f:
                users_data = json.load(f)
                for u in users_data:
                    save_user_preference(UserPreference(**u), conn=conn)
        except Exception as e:
            print(f"Error seeding user preferences: {e}")
    conn.close()


def row_to_preference(row: sqlite3.Row) -> UserPreference:
    keys = row.keys()
    return UserPreference(
        user_id=row["user_id"],
        name=row["name"] if "name" in keys and row["name"] else "Bạn",
        district=row["district"] if "district" in keys and row["district"] else "Cầu Giấy",
        address=row["address"] if "address" in keys and row["address"] else "Cầu Giấy, Hà Nội",
        preferred_cuisines=json.loads(row["preferred_cuisines"] or "[]"),
        preferred_flavors=json.loads(row["preferred_flavors"] or "[]"),
        disliked_ingredients=json.loads(row["disliked_ingredients"] or "[]"),
        budget=row["budget"] or 80000,
        minimum_rating=row["minimum_rating"] or 4.3,
        preferred_distance=row["preferred_distance"] or 5.0,
        dietary_restrictions=json.loads(row["dietary_restrictions"] or "[]"),
        liked_dishes=json.loads(row["liked_dishes"] or "[]"),
        disliked_dishes=json.loads(row["disliked_dishes"] or "[]"),
        updated_at=row["updated_at"]
    )


def get_user_preferences(user_id: str, db_path: str = DB_PATH) -> UserPreference:
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return row_to_preference(row)

    default_pref = UserPreference(
        user_id=user_id,
        name="Bạn",
        district="Cầu Giấy",
        address="Cầu Giấy, Hà Nội",
        preferred_cuisines=["Vietnamese"],
        preferred_flavors=[],
        disliked_ingredients=[],
        budget=80000,
        minimum_rating=4.3,
        preferred_distance=5.0,
        dietary_restrictions=[],
        liked_dishes=[],
        disliked_dishes=[],
        updated_at=datetime.now().isoformat()
    )
    save_user_preference(default_pref, db_path=db_path)
    return default_pref


def save_user_preference(pref: UserPreference, conn: Optional[sqlite3.Connection] = None, db_path: str = DB_PATH):
    should_close = False
    if conn is None:
        conn = get_db_connection(db_path)
        should_close = True

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_preferences (
            user_id, name, district, address, preferred_cuisines, preferred_flavors, disliked_ingredients,
            budget, minimum_rating, preferred_distance, dietary_restrictions,
            liked_dishes, disliked_dishes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name=excluded.name,
            district=excluded.district,
            address=excluded.address,
            preferred_cuisines=excluded.preferred_cuisines,
            preferred_flavors=excluded.preferred_flavors,
            disliked_ingredients=excluded.disliked_ingredients,
            budget=excluded.budget,
            minimum_rating=excluded.minimum_rating,
            preferred_distance=excluded.preferred_distance,
            dietary_restrictions=excluded.dietary_restrictions,
            liked_dishes=excluded.liked_dishes,
            disliked_dishes=excluded.disliked_dishes,
            updated_at=excluded.updated_at
    """, (
        pref.user_id,
        pref.name,
        pref.district,
        pref.address,
        json.dumps(pref.preferred_cuisines, ensure_ascii=False),
        json.dumps(pref.preferred_flavors, ensure_ascii=False),
        json.dumps(pref.disliked_ingredients, ensure_ascii=False),
        pref.budget,
        pref.minimum_rating,
        pref.preferred_distance,
        json.dumps(pref.dietary_restrictions, ensure_ascii=False),
        json.dumps(pref.liked_dishes, ensure_ascii=False),
        json.dumps(pref.disliked_dishes, ensure_ascii=False),
        datetime.now().isoformat()
    ))
    conn.commit()
    if should_close:
        conn.close()
    if should_close:
        conn.close()


def update_user_preference(
    user_id: str,
    preference_type: str,
    value: Any,
    db_path: str = DB_PATH
) -> UserPreference:
    pref = get_user_preferences(user_id, db_path=db_path)

    # Standardize field names
    type_map = {
        "disliked_ingredients": "disliked_ingredients",
        "disliked_ingredient": "disliked_ingredients",
        "dislike_ingredient": "disliked_ingredients",
        "disliked": "disliked_ingredients",
        "ingredients": "disliked_ingredients",
        "preferred_cuisines": "preferred_cuisines",
        "preferred_cuisine": "preferred_cuisines",
        "cuisine": "preferred_cuisines",
        "cuisines": "preferred_cuisines",
        "preferred_flavors": "preferred_flavors",
        "preferred_flavor": "preferred_flavors",
        "flavor": "preferred_flavors",
        "flavors": "preferred_flavors",
        "budget": "budget",
        "max_price": "budget",
        "price": "budget",
        "minimum_rating": "minimum_rating",
        "rating": "minimum_rating",
        "preferred_distance": "preferred_distance",
        "distance": "preferred_distance",
        "liked_dishes": "liked_dishes",
        "liked_dish": "liked_dishes",
        "disliked_dishes": "disliked_dishes",
        "dietary_restrictions": "dietary_restrictions",
        "name": "name",
        "user_name": "name",
        "address": "address",
        "user_address": "address",
        "location": "address",
        "district": "district"
    }

    target_field = type_map.get(preference_type.lower(), preference_type)

    if target_field in ["name", "address", "district"]:
        setattr(pref, target_field, str(value).strip())
    elif target_field in ["disliked_ingredients", "preferred_cuisines", "preferred_flavors", "dietary_restrictions", "liked_dishes", "disliked_dishes"]:
        current_list: list = getattr(pref, target_field, [])
        if isinstance(value, list):
            for item in value:
                clean_item = str(item).strip().lower()
                # Keep original casing if appropriate or store clean
                if clean_item not in [x.lower() for x in current_list]:
                    current_list.append(str(item).strip())
        elif isinstance(value, str):
            # Check if comma separated
            items = [x.strip() for x in value.split(",") if x.strip()]
            for item in items:
                if item.lower() not in [x.lower() for x in current_list]:
                    current_list.append(item)
        setattr(pref, target_field, current_list)
    elif target_field == "budget":
        try:
            val_num = int(float(value))
            pref.budget = val_num
        except (ValueError, TypeError):
            pass
    elif target_field == "minimum_rating":
        try:
            val_float = float(value)
            pref.minimum_rating = val_float
        except (ValueError, TypeError):
            pass
    elif target_field == "preferred_distance":
        try:
            val_dist = float(value)
            pref.preferred_distance = val_dist
        except (ValueError, TypeError):
            pass

    pref.updated_at = datetime.now().isoformat()
    save_user_preference(pref, db_path=db_path)
    return pref


def reset_database(db_path: str = DB_PATH):
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db(db_path)
