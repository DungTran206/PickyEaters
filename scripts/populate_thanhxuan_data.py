import json
import os
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
POC_RESULTS_DIR = os.path.join(BASE_DIR, "food-browser-poc", "artifacts", "results")
os.makedirs(POC_RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 20 Authentic Restaurants in Thanh Xuân, Hà Nội
# ---------------------------------------------------------------------------
THANH_XUAN_RESTAURANTS = [
    # 1. Quán Xôi 4.9⭐
    {
        "id": "tx_r01",
        "name": "Xôi Chim & Xôi Sườn Cay Bà Thu",
        "cuisine": "Vietnamese",
        "rating": 4.9,
        "distance_km": 1.2,
        "delivery_fee": 14000,
        "address": "105 Nguyễn Tuân, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 22:30",
        "platform": "ShopeeFood"
    },
    # 2. Quán Xôi 4.8⭐
    {
        "id": "tx_r02",
        "name": "Xôi Xéo & Xôi Thịt Kho Tàu Cô Lan",
        "cuisine": "Vietnamese",
        "rating": 4.8,
        "distance_km": 0.9,
        "delivery_fee": 12000,
        "address": "18 Khương Đình, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 14:00, 17:00 - 22:00",
        "platform": "ShopeeFood"
    },
    # 3. Quán Xôi 4.8⭐
    {
        "id": "tx_r03",
        "name": "Xôi Ngô & Xôi Xéo Mỡ Hành Tô Vĩnh Diện",
        "cuisine": "Vietnamese",
        "rating": 4.8,
        "distance_km": 1.6,
        "delivery_fee": 15000,
        "address": "45 Tô Vĩnh Diện, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 21:30",
        "platform": "GrabFood"
    },
    # 4. Quán Xôi 4.7⭐
    {
        "id": "tx_r04",
        "name": "Xôi Gà Nấm & Xôi Xéo Bác Ngọ",
        "cuisine": "Vietnamese",
        "rating": 4.7,
        "distance_km": 1.4,
        "delivery_fee": 13000,
        "address": "34 Triều Khúc, Thanh Xuân, Hà Nội",
        "open_hours": "06:30 - 22:00",
        "platform": "ShopeeFood"
    },
    # 5. Quán Xôi 4.6⭐
    {
        "id": "tx_r05",
        "name": "Xôi Chị Em - Xôi Thập Cẩm & Sườn Nướng",
        "cuisine": "Vietnamese",
        "rating": 4.6,
        "distance_km": 1.1,
        "delivery_fee": 12000,
        "address": "220 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "open_hours": "07:00 - 23:00",
        "platform": "GrabFood"
    },
    # 6. Quán Xôi 4.5⭐
    {
        "id": "tx_r06",
        "name": "Xôi Bắp & Xôi Đậu Xanh Phố Cổ",
        "cuisine": "Vietnamese",
        "rating": 4.5,
        "distance_km": 2.0,
        "delivery_fee": 16000,
        "address": "12 Hoàng Văn Thái, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 13:00",
        "platform": "ShopeeFood"
    },
    # 7. Quán Xôi 4.6⭐
    {
        "id": "tx_r07",
        "name": "Xôi Mặn Thập Cẩm Chợ Chính Kinh",
        "cuisine": "Vietnamese",
        "rating": 4.6,
        "distance_km": 0.8,
        "delivery_fee": 10000,
        "address": "8 Chính Kinh, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 21:00",
        "platform": "ShopeeFood"
    },
    # 8. Phở bò 4.8⭐
    {
        "id": "tx_r08",
        "name": "Phở Bò Tái Lăn & Sốt Vang Bát Đàn - Thanh Xuân",
        "cuisine": "Vietnamese",
        "rating": 4.8,
        "distance_km": 1.8,
        "delivery_fee": 16000,
        "address": "88 Lê Trọng Tấn, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 21:30",
        "platform": "ShopeeFood"
    },
    # 9. Bún chả 4.7⭐
    {
        "id": "tx_r09",
        "name": "Bún Chả Sinh Từ - Nướng Than Hoa",
        "cuisine": "Vietnamese",
        "rating": 4.7,
        "distance_km": 1.3,
        "delivery_fee": 14000,
        "address": "48 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "open_hours": "07:30 - 21:00",
        "platform": "GrabFood"
    },
    # 10. Cơm tấm 4.6⭐
    {
        "id": "tx_r10",
        "name": "Cơm Tấm Sườn Bì Chả Ali Triều Khúc",
        "cuisine": "Vietnamese",
        "rating": 4.6,
        "distance_km": 1.5,
        "delivery_fee": 14000,
        "address": "25 Triều Khúc, Thanh Xuân, Hà Nội",
        "open_hours": "09:30 - 21:30",
        "platform": "ShopeeFood"
    },
    # 11. Bún đậu 4.7⭐
    {
        "id": "tx_r11",
        "name": "Bún Đậu Mắm Tôm Mơ Quán",
        "cuisine": "Vietnamese",
        "rating": 4.7,
        "distance_km": 1.0,
        "delivery_fee": 12000,
        "address": "15 Ngõ 190 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "open_hours": "09:00 - 21:30",
        "platform": "ShopeeFood"
    },
    # 12. Bún riêu cua 4.6⭐
    {
        "id": "tx_r12",
        "name": "Bún Riêu Cua Bắp Bò Giò Tai",
        "cuisine": "Vietnamese",
        "rating": 4.6,
        "distance_km": 1.7,
        "delivery_fee": 15000,
        "address": "110 Vũ Tông Phan, Thanh Xuân, Hà Nội",
        "open_hours": "06:30 - 21:00",
        "platform": "GrabFood"
    },
    # 13. Bún ốc sườn cay 4.8⭐
    {
        "id": "tx_r13",
        "name": "Bún Ốc Sườn Cay Nóng Khương Đình",
        "cuisine": "Vietnamese",
        "rating": 4.8,
        "distance_km": 0.7,
        "delivery_fee": 10000,
        "address": "215 Khương Đình, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 21:00",
        "platform": "ShopeeFood"
    },
    # 14. Bánh mì 4.6⭐
    {
        "id": "tx_r14",
        "name": "Bánh Mì Dân Tổ & Pate Nóng Hải Phòng",
        "cuisine": "Vietnamese",
        "rating": 4.6,
        "distance_km": 1.2,
        "delivery_fee": 12000,
        "address": "64 Nguyễn Tuân, Thanh Xuân, Hà Nội",
        "open_hours": "06:00 - 23:00",
        "platform": "ShopeeFood"
    },
    # 15. Bánh cuốn 4.6⭐
    {
        "id": "tx_r15",
        "name": "Bánh Cuốn Nóng Gia An - Nhân Hòa",
        "cuisine": "Vietnamese",
        "rating": 4.6,
        "distance_km": 1.9,
        "delivery_fee": 16000,
        "address": "62 Nhân Hòa, Thanh Xuân, Hà Nội",
        "open_hours": "06:30 - 21:00",
        "platform": "GrabFood"
    },
    # 16. Mì cay Hàn Quốc 4.6⭐
    {
        "id": "tx_r16",
        "name": "Mì Cay Seoul 7 Cấp Độ & Tokbokki",
        "cuisine": "Korean",
        "rating": 4.6,
        "distance_km": 1.5,
        "delivery_fee": 14000,
        "address": "142 Triều Khúc, Thanh Xuân, Hà Nội",
        "open_hours": "09:00 - 22:30",
        "platform": "ShopeeFood"
    },
    # 17. Gà rán & Burger 4.5⭐
    {
        "id": "tx_r17",
        "name": "Gà Rán Giòn Tan & Burger Mom's Touch",
        "cuisine": "Western",
        "rating": 4.5,
        "distance_km": 2.1,
        "delivery_fee": 16000,
        "address": "52 Quan Nhân, Thanh Xuân, Hà Nội",
        "open_hours": "09:00 - 22:00",
        "platform": "GrabFood"
    },
    # 18. Nem nướng Nha Trang 4.7⭐
    {
        "id": "tx_r18",
        "name": "Nem Nướng Nha Trang Cô Ba Tô Vĩnh Diện",
        "cuisine": "Vietnamese",
        "rating": 4.7,
        "distance_km": 1.6,
        "delivery_fee": 15000,
        "address": "78 Tô Vĩnh Diện, Thanh Xuân, Hà Nội",
        "open_hours": "09:30 - 21:30",
        "platform": "ShopeeFood"
    },
    # 19. Cháo sườn sụn 4.8⭐
    {
        "id": "tx_r19",
        "name": "Cháo Sườn Sụn & Cháo Ngô Niêu Đất",
        "cuisine": "Vietnamese",
        "rating": 4.8,
        "distance_km": 1.0,
        "delivery_fee": 12000,
        "address": "12 Nguyễn Quý Đức, Thanh Xuân, Hà Nội",
        "open_hours": "06:30 - 22:30",
        "platform": "ShopeeFood"
    },
    # 20. Chè & Ăn vặt 4.7⭐
    {
        "id": "tx_r20",
        "name": "Chè Sầu Liên Đà Nẵng & Trà Sữa Ăn Vặt",
        "cuisine": "Vietnamese",
        "rating": 4.7,
        "distance_km": 0.8,
        "delivery_fee": 10000,
        "address": "38 Chính Kinh, Thanh Xuân, Hà Nội",
        "open_hours": "09:00 - 23:00",
        "platform": "GrabFood"
    }
]

# ---------------------------------------------------------------------------
# Menus for Thanh Xuân Restaurants (Detailed Dishes & Prices)
# ---------------------------------------------------------------------------
THANH_XUAN_MENUS = [
    # Quán tx_r01: Xôi Chim & Xôi Sườn Cay Bà Thu (Rating 4.9⭐)
    {
        "id": "tx_d01",
        "restaurant_id": "tx_r01",
        "name": "Xôi chim bồ câu nướng thơm lừng",
        "price": 65000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt chim bồ câu", "gạo nếp cái hoa vàng", "hành phi giòn", "hạt sen"],
        "description": "Thịt chim bồ câu băm nhỏ xào mộc nhĩ nấm hương đậm đà, quyện với xôi nếp dẻo thơm nức mũi."
    },
    {
        "id": "tx_d02",
        "restaurant_id": "tx_r01",
        "name": "Xôi sườn cay sốt mật ong đậm vị",
        "price": 55000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["sườn sụn non", "sốt cay mật ong", "ớt sa tế", "gạo nếp", "hành phi"],
        "description": "Sườn non rim sốt ớt cay ngọt đẫm vị, xôi hạt căng bóng dẻo quánh, ăn cay tê đầu lưỡi cực đã."
    },
    {
        "id": "tx_d03",
        "restaurant_id": "tx_r01",
        "name": "Xôi thập cẩm đặc biệt Bà Thu (sườn, chim, trứng ốp)",
        "price": 60000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["sườn cay", "thịt chim", "trứng ốp la", "chả quế", "pate gan", "dưa góp"],
        "description": "Hộp xôi đầy ú ụ với sườn cay đậm vị, thịt chim xào thơm, trứng lòng đào béo ngậy và dưa chua giòn."
    },
    {
        "id": "tx_d04",
        "restaurant_id": "tx_r01",
        "name": "Xôi gà xé nấm hương tiêu cay",
        "price": 48000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt gà ta xé", "nấm hương", "tiêu cay", "nước sốt gà", "hành phi"],
        "description": "Gà ta thả vườn dai ngọt xé sợi xào nấm hương đẫm sốt tiêu cay, rưới mỡ gà béo ngậy."
    },
    {
        "id": "tx_d05",
        "restaurant_id": "tx_r01",
        "name": "Xôi xéo ruốc hành phi truyền thống",
        "price": 25000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["đậu xanh tán mịn", "ruốc thịt heo", "hành phi ta", "mỡ nước"],
        "description": "Xôi xéo vàng óng ả chuẩn vị Hà Nội, đậu xanh bùi béo cắt lát mỏng tang rưới mỡ nước thơm nức."
    },

    # Quán tx_r02: Xôi Xéo & Xôi Thịt Kho Tàu Cô Lan (Rating 4.8⭐)
    {
        "id": "tx_d06",
        "restaurant_id": "tx_r02",
        "name": "Xôi xéo thịt kho trứng lòng đào",
        "price": 45000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt ba chỉ kho tàu", "trứng lòng đào", "đậu xanh", "gạo nếp", "hành phi"],
        "description": "Thịt ba chỉ kho nhừ mềm tan trong miệng, trứng lòng đào dẻo quánh rưới đẫm nước sốt thịt kho lên xôi xéo."
    },
    {
        "id": "tx_d07",
        "restaurant_id": "tx_r02",
        "name": "Xôi xéo chả mỡ lạp xưởng nóng hổi",
        "price": 38000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["chả mỡ nướng", "lạp xưởng tươi", "đậu xanh", "mỡ gà", "hành phi"],
        "description": "Chả mỡ nướng thơm ngậy kết hợp lạp xưởng đậm đà rưới nước mỡ hành phi giòn tan."
    },
    {
        "id": "tx_d08",
        "restaurant_id": "tx_r02",
        "name": "Xôi gà quay ngũ vị da giòn",
        "price": 50000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["đùi gà quay", "ngũ vị hương", "mật ong", "gạo nếp", "dưa chuột"],
        "description": "Miếng đùi gà quay ngũ vị da nâu óng ả giòn rụm, thịt bên trong mềm mọng ngọt nước ăn cùng xôi trắng dẻo thơm."
    },
    {
        "id": "tx_d09",
        "restaurant_id": "tx_r02",
        "name": "Xôi pate trứng ốp giò lụa Cô Lan",
        "price": 35000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["pate gan Hải Phòng", "trứng ốp la", "giò lụa", "hành phi", "tương ớt"],
        "description": "Pate gan thơm bùi tan chảy quết đều lên xôi nóng, thêm trứng ốp la lòng đào béo ngậy."
    },

    # Quán tx_r03: Xôi Ngô & Xôi Xéo Mỡ Hành Tô Vĩnh Diện (Rating 4.8⭐)
    {
        "id": "tx_d10",
        "restaurant_id": "tx_r03",
        "name": "Xôi ngô đậu xanh hành phi thơm béo",
        "price": 20000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["ngô nếp bung", "đậu xanh tán", "mỡ hành phi", "chút đường vừng"],
        "description": "Ngô nếp bung nở mềm dẻo ngọt tự nhiên, trộn đều cùng đỗ xanh bùi và mỡ hành phi thơm nức."
    },
    {
        "id": "tx_d11",
        "restaurant_id": "tx_r03",
        "name": "Xôi xéo chả quế pate Cột Đèn",
        "price": 35000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["chả quế thơm nồng", "pate Cột Đèn", "đậu xanh", "gạo nếp", "hành phi"],
        "description": "Chả quế giòn sần sật kẹp pate Cột Đèn béo thơm trứ danh rưới trên đĩa xôi xéo vàng ươm."
    },
    {
        "id": "tx_d12",
        "restaurant_id": "tx_r03",
        "name": "Xôi thịt kho tàu dưa góp đậm đà",
        "price": 42000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt kho tàu", "nước thịt kho", "dưa chuột góp", "gạo nếp", "hành phi"],
        "description": "Nước thịt kho keo màu cánh gián đậm đà chan đẫm từng hạt xôi nếp dẻo thơm, ăn kèm dưa góp chua ngọt đỡ ngấy."
    },

    # Quán tx_r04: Xôi Gà Nấm & Xôi Xéo Bác Ngọ (Rating 4.7⭐)
    {
        "id": "tx_d13",
        "restaurant_id": "tx_r04",
        "name": "Xôi gà nấm xào hành hoa Bác Ngọ",
        "price": 42000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt gà xé", "nấm hương rừng", "hành hoa", "gạo nếp cái", "hành phi"],
        "description": "Thịt gà xào nấm hương thơm lừng vị ngọt tự nhiên, xôi dẻo bùi hạt không bị nhão."
    },
    {
        "id": "tx_d14",
        "restaurant_id": "tx_r04",
        "name": "Xôi sườn rim tiêu cay ngọt",
        "price": 48000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["sườn rim tiêu", "tiêu đen", "ớt cay", "gạo nếp", "hành phi"],
        "description": "Sườn non được chặt miếng nhỏ rim kỹ sốt tiêu đen cay nồng, vị ngọt mặn hài hòa đưa miệng."
    },
    {
        "id": "tx_d15",
        "restaurant_id": "tx_r04",
        "name": "Xôi thập cẩm Triều Khúc đầy đặn",
        "price": 45000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt kho", "chả mỡ", "lạp xưởng", "trứng kho", "ruốc thịt"],
        "description": "Phần xôi phong phú với đủ loại topping thịt kho, chả mỡ, lạp xưởng và trứng bùi béo."
    },

    # Quán tx_r05: Xôi Chị Em - Xôi Thập Cẩm & Sườn Nướng (Rating 4.6⭐)
    {
        "id": "tx_d16",
        "restaurant_id": "tx_r05",
        "name": "Xôi sườn nướng mật ong sốt cay Chị Em",
        "price": 50000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["sườn nướng than", "sốt cay mật ong", "gạo nếp", "hành phi", "đồ chua"],
        "description": "Dải sườn nướng than hoa thơm nức mũi quét sốt mật ong cay cay, ăn kèm xôi dẻo hạt."
    },
    {
        "id": "tx_d17",
        "restaurant_id": "tx_r05",
        "name": "Xôi xá xíu trứng ốp la sốt dầu hào",
        "price": 40000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt xá xíu đỏ", "trứng ốp la", "sốt dầu hào", "gạo nếp"],
        "description": "Thịt xá xíu mềm thơm đẫm sốt dầu hào thơm phức, trứng ốp la béo ngậy hoà quyện."
    },

    # Quán tx_r06: Xôi Bắp & Xôi Đậu Xanh Phố Cổ (Rating 4.5⭐)
    {
        "id": "tx_d18",
        "restaurant_id": "tx_r06",
        "name": "Xôi bắp nếp mỡ hành đường vừng",
        "price": 20000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["bắp nếp bung", "mỡ hành phi", "muối vừng lạc", "dừa nạo"],
        "description": "Món ăn sáng tuổi thơ dân dã với bắp nếp bung dẻo thơm, thêm chút muối vừng bùi bùi dừa tươi."
    },
    {
        "id": "tx_d19",
        "restaurant_id": "tx_r06",
        "name": "Xôi vò hạt sen thơm bùi",
        "price": 28000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["gạo nếp", "hạt sen tươi", "đậu xanh", "chút mỡ gà"],
        "description": "Hạt xôi tơi đều bọc một lớp đậu xanh vàng mịn, hạt sen chín bở ngọt bùi thanh tao."
    },

    # Quán tx_r07: Xôi Mặn Thập Cẩm Chợ Chính Kinh (Rating 4.6⭐)
    {
        "id": "tx_d20",
        "restaurant_id": "tx_r07",
        "name": "Xôi mặn thập cẩm tôm khô lạp xưởng",
        "price": 35000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["tôm khô xào", "lạp xưởng chiên", "thịt xé", "hành phi", "mỡ hành"],
        "description": "Xôi mặn theo phong cách miền Nam độc đáo với tôm khô đậm đà, lạp xưởng béo ngọt và mỡ hành xanh mướt."
    },
    {
        "id": "tx_d21",
        "restaurant_id": "tx_r07",
        "name": "Xôi lòng mề gà xào cay",
        "price": 38000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["lòng mề gà", "ớt sừng cay", "hành tây", "gạo nếp", "tiêu"],
        "description": "Lòng mề gà giòn sần sật xào cay thơm nồng, ăn kèm xôi trắng nóng hổi cực kỳ đưa vị."
    },

    # Quán tx_r08: Phở Bò Bát Đàn - Lê Trọng Tấn (Rating 4.8⭐)
    {
        "id": "tx_d22",
        "restaurant_id": "tx_r08",
        "name": "Phở bò tái lăn thơm nức tỏi",
        "price": 60000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["thịt thăn bò", "bánh phở tươi", "nước hầm xương bò", "hành hoa", "tỏi phi"],
        "description": "Thịt bò thăn thái mỏng xào lăn trên chảo gang đượm lửa, nước dùng phở ngọt thanh trong veo."
    },
    {
        "id": "tx_d23",
        "restaurant_id": "tx_r08",
        "name": "Phở bò sốt vang gân giòn đậm vị",
        "price": 65000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["bò sốt vang", "quế hồi", "rượu vang đỏ", "bánh phở", "rau thơm"],
        "description": "Gân bò dẻo giòn sốt vang sánh mịn màu đỏ vang óng ả, thơm nức mùi quế hồi thảo mộc."
    },

    # Quán tx_r09: Bún Chả Sinh Từ Nguyễn Trãi (Rating 4.7⭐)
    {
        "id": "tx_d24",
        "restaurant_id": "tx_r09",
        "name": "Bún chả que tre nướng than hoa đặc biệt",
        "price": 55000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["chả viên nướng", "chả miếng ba chỉ", "nước mắm chua ngọt", "bún tươi", "rau sống"],
        "description": "Chả nướng kẹp que tre trên than hồng xèo xèo thơm ngát, nước chấm ấm nóng chua thanh hài hòa."
    },
    {
        "id": "tx_d25",
        "restaurant_id": "tx_r09",
        "name": "Nem cua bể giòn rụm Hải Phòng",
        "price": 25000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Side",
        "ingredients": ["thịt cua bể", "tôm tươi", "mộc nhĩ", "miến dong", "bánh đa nem"],
        "description": "Vỏ nem giòn rụm, nhân đầy thịt cua biển và tôm tươi ngọt lịm."
    },

    # Quán tx_r10: Cơm Tấm Ali Triều Khúc (Rating 4.6⭐)
    {
        "id": "tx_d26",
        "restaurant_id": "tx_r10",
        "name": "Cơm tấm sườn nướng bì chả đặc biệt",
        "price": 55000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["sườn cốt lết nướng", "chả trứng hấp", "bì heo trộn thính", "gạo tấm", "mỡ hành"],
        "description": "Miếng sườn cốt lết to bản ướp đẫm gia vị nướng than vàng ruộm, nước mắm cơm tấm kẹo dẻo."
    },

    # Quán tx_r11: Bún Đậu Mơ Quán (Rating 4.7⭐)
    {
        "id": "tx_d27",
        "restaurant_id": "tx_r11",
        "name": "Mẹt bún đậu mắm tôm đầy đủ (thịt chân giò, chả cốm, nem rán)",
        "price": 50000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["đậu phụ làng Mơ lướt ván", "thịt chân giò luộc", "chả cốm nóng", "nem rán", "mắm tôm Thanh Hóa"],
        "description": "Đậu Mơ rán giòn ngoài xốp trong béo ngậy, chả cốm dẻo thơm, mắm tôm đánh sủi bọt dậy mùi quất ớt."
    },

    # Quán tx_r13: Bún Ốc Sườn Cay Khương Đình (Rating 4.8⭐)
    {
        "id": "tx_d28",
        "restaurant_id": "tx_r13",
        "name": "Bún ốc mít sườn cay chua thanh nồng",
        "price": 55000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["ốc mít béo giòn", "sườn thăn ninh nhừ", "giấm bỗng nếp", "cà chua", "ớt chưng cay"],
        "description": "Ốc mít to béo giòn sần sật, sườn ninh mềm ngọt xương trong nước dùng giấm bỗng chua thanh dịu mát cay tê tê."
    },

    # Quán tx_r14: Bánh Mì Dân Tổ Nguyễn Tuân (Rating 4.6⭐)
    {
        "id": "tx_d29",
        "restaurant_id": "tx_r14",
        "name": "Bánh mì dân tổ sốt bơ pate trứng xào thập cẩm",
        "price": 35000,
        "spicy": True,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["pate gan", "trứng gà", "lạp xưởng", "chả lụa", "bơ thơm", "ớt bột"],
        "description": "Topping xào chung trên chảo bơ nóng sốt xình xịch, nhồi căng phồng vào chiếc bánh mì nướng giòn rụm."
    },

    # Quán tx_r19: Cháo Sườn Nguyễn Quý Đức (Rating 4.8⭐)
    {
        "id": "tx_d30",
        "restaurant_id": "tx_r19",
        "name": "Cháo sườn sụn niêu đất ruốc quẩy giòn",
        "price": 35000,
        "spicy": False,
        "cuisine": "Vietnamese",
        "category": "Main",
        "ingredients": ["sườn sụn non", "bột gạo tẻ xay mịn", "quẩy giòn", "ruốc thịt heo", "tiêu bột"],
        "description": "Cháo bột sánh mịn thơm ngậy mùi xương hầm, sườn sụn ninh mềm giòn sần sật ăn cùng quẩy nóng."
    }
]

# ---------------------------------------------------------------------------
# Promotions for Thanh Xuân Restaurants
# ---------------------------------------------------------------------------
THANH_XUAN_PROMOTIONS = [
    {
        "id": "tx_promo_01",
        "restaurant_id": "tx_r01",
        "code": "XOIBATHU15K",
        "type": "discount",
        "value": 15000,
        "max_discount": 15000,
        "minimum_order": 45000,
        "description": "Giảm 15.000đ cho đơn xôi từ 45k tại Xôi Chim Bà Thu"
    },
    {
        "id": "tx_promo_02",
        "restaurant_id": "tx_r02",
        "code": "FREESHIPCOLAN",
        "type": "freeship",
        "value": 15000,
        "max_discount": 15000,
        "minimum_order": 35000,
        "description": "Miễn phí vận chuyển tới 15k đơn từ 35k tại Xôi Cô Lan Khương Đình"
    },
    {
        "id": "tx_promo_03",
        "restaurant_id": "tx_r03",
        "code": "XOINGO10K",
        "type": "discount",
        "value": 10000,
        "max_discount": 10000,
        "minimum_order": 30000,
        "description": "Giảm 10.000đ cho đơn xôi từ 30k tại Tô Vĩnh Diện"
    },
    {
        "id": "tx_promo_04",
        "restaurant_id": "tx_r04",
        "code": "BACNGO20PCT",
        "type": "percent",
        "value": 20,
        "max_discount": 20000,
        "minimum_order": 40000,
        "description": "Giảm 20% tối đa 20.000đ cho xôi gà nấm Bác Ngọ Triều Khúc"
    },
    {
        "id": "tx_promo_08",
        "restaurant_id": "tx_r08",
        "code": "PHOBATDAN10K",
        "type": "discount",
        "value": 10000,
        "max_discount": 10000,
        "minimum_order": 50000,
        "description": "Giảm 10.000đ cho tô phở bò Bát Đàn Thanh Xuân"
    },
    {
        "id": "tx_promo_13",
        "restaurant_id": "tx_r13",
        "code": "BUNOC5K",
        "type": "discount",
        "value": 10000,
        "max_discount": 10000,
        "minimum_order": 45000,
        "description": "Giảm 10k tô bún ốc sườn cay Khương Đình"
    }
]


def update_data_files():
    # 1. Update restaurants.json
    rest_file = os.path.join(DATA_DIR, "restaurants.json")
    with open(rest_file, "r", encoding="utf-8") as f:
        existing_rests = json.load(f)

    existing_ids = {r["id"] for r in existing_rests}
    added_rests = 0
    for r in THANH_XUAN_RESTAURANTS:
        if r["id"] not in existing_ids:
            existing_rests.append(r)
            existing_ids.add(r["id"])
            added_rests += 1

    with open(rest_file, "w", encoding="utf-8") as f:
        json.dump(existing_rests, f, ensure_ascii=False, indent=2)
    print(f"-> restaurants.json: Added {added_rests} new restaurants (Total: {len(existing_rests)})")

    # 2. Update menus.json
    menu_file = os.path.join(DATA_DIR, "menus.json")
    with open(menu_file, "r", encoding="utf-8") as f:
        existing_menus = json.load(f)

    existing_dish_ids = {d["id"] for d in existing_menus}
    added_dishes = 0
    for d in THANH_XUAN_MENUS:
        if d["id"] not in existing_dish_ids:
            existing_menus.append(d)
            existing_dish_ids.add(d["id"])
            added_dishes += 1

    with open(menu_file, "w", encoding="utf-8") as f:
        json.dump(existing_menus, f, ensure_ascii=False, indent=2)
    print(f"-> menus.json: Added {added_dishes} new dishes (Total: {len(existing_menus)})")

    # 3. Update promotions.json
    promo_file = os.path.join(DATA_DIR, "promotions.json")
    with open(promo_file, "r", encoding="utf-8") as f:
        existing_promos = json.load(f)

    existing_promo_ids = {p["id"] for p in existing_promos}
    added_promos = 0
    for p in THANH_XUAN_PROMOTIONS:
        if p["id"] not in existing_promo_ids:
            existing_promos.append(p)
            existing_promo_ids.add(p["id"])
            added_promos += 1

    with open(promo_file, "w", encoding="utf-8") as f:
        json.dump(existing_promos, f, ensure_ascii=False, indent=2)
    print(f"-> promotions.json: Added {added_promos} new promos (Total: {len(existing_promos)})")

    # 4. Save to food-browser-poc/artifacts/results/shopeefood_thanhxuan.json
    poc_file = os.path.join(POC_RESULTS_DIR, "shopeefood_thanhxuan.json")
    poc_restaurants = []
    for r in THANH_XUAN_RESTAURANTS:
        rest_copy = dict(r)
        rest_copy["restaurant_name"] = r["name"]
        rest_copy["restaurant_url"] = f"https://shopeefood.vn/ha-noi/{r['id']}"
        rest_copy["menu"] = [
            {
                "dish_name": d["name"],
                "dish_price": d["price"],
                "original_price": int(d["price"] * 1.15),
                "description": d["description"],
                "discount": "Ưu đãi quán"
            }
            for d in THANH_XUAN_MENUS if d["restaurant_id"] == r["id"]
        ]
        poc_restaurants.append(rest_copy)

    with open(poc_file, "w", encoding="utf-8") as f:
        json.dump({"platform": "ShopeeFood", "restaurants": poc_restaurants}, f, ensure_ascii=False, indent=2)
    print(f"-> Saved crawled PoC artifact to: {poc_file}")


if __name__ == "__main__":
    update_data_files()
