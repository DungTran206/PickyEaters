import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from agent.agent import FoodAgent
from services.search import search_with_radius_expansion, search_restaurants

print('=== 1. Checking restaurants in Thanh Xuân within 5km ===')
rests = search_restaurants(user_address='Thanh Xuân, Hà Nội', radius_km=5.0)
print(f'Found {len(rests)} restaurants in 5km')
for r in rests[:8]:
    print(f'  {r.id} | {r.name} | {r.rating}⭐ | {r.distance_km}km | {r.address}')

print('\n=== 2. Checking search_with_radius_expansion for keyword: xoi ===')
res1 = search_with_radius_expansion(user_address='Thanh Xuân, Hà Nội', keyword='xoi', initial_radius=5.0)
print('Dishes found:', len(res1['dishes']))
for d in res1['dishes'][:8]:
    print(f'  {d.name} ({d.price:,}đ) - Rest: {d.restaurant_id}')

print('\n=== 3. Running FoodAgent with query "tìm quán xôi" at Thanh Xuân ===')
agent = FoodAgent(user_id='user_01', force_mock=True)
agent_res = agent.run(user_input='tìm quán xôi ngon gần đây', user_name='Dũng', user_address='Thanh Xuân, Hà Nội')

print('\n--- AGENT RESPONSE ---')
print(agent_res['response'])

print('\n--- STRUCTURED CANDIDATES ---')
for idx, c in enumerate(agent_res['candidates'], 1):
    rest = c['restaurant']
    dish = c['dish']
    print(f'{idx}. {dish["name"]} | {rest["name"]} | Rating: {rest["rating"]}* | Dist: {rest["distance_km"]}km | Final Price: {c["pricing"]["final_price"]:,}d')

print('\n=== 4. Running FoodAgent for Pho Bo ===')
res_pho = agent.run(user_input='tìm phở bò', user_name='Dũng', user_address='Thanh Xuân, Hà Nội')
for idx, c in enumerate(res_pho['candidates'][:2], 1):
    print(f'  Pho {idx}: {c["dish"]["name"]} - {c["restaurant"]["name"]} ({c["restaurant"]["rating"]}*, {c["restaurant"]["distance_km"]}km)')

print('\n=== 5. Running FoodAgent for Bun Cha ===')
res_bc = agent.run(user_input='tìm bún chả', user_name='Dũng', user_address='Thanh Xuân, Hà Nội')
for idx, c in enumerate(res_bc['candidates'][:2], 1):
    print(f'  Bun Cha {idx}: {c["dish"]["name"]} - {c["restaurant"]["name"]} ({c["restaurant"]["rating"]}*, {c["restaurant"]["distance_km"]}km)')

