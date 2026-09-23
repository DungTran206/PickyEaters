import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)
res = client.get('/api/health')
print('Health check:', res.json())

chat_res = client.post('/api/chat', json={
    'message': 'tìm xôi ngon',
    'user_id': 'user_01',
    'user_name': 'Dũng',
    'user_address': 'Thanh Xuân, Hà Nội'
})
print('Chat status code:', chat_res.status_code)
chat_data = chat_res.json()
print('Total candidates returned:', len(chat_data.get('candidates', [])))
for idx, c in enumerate(chat_data.get('candidates', []), 1):
    rest = c['restaurant']
    dish = c['dish']
    print(f"  {idx}. {dish['name']} | {rest['name']} | Rating: {rest['rating']}* | Dist: {rest['distance_km']}km | Price: {c['pricing']['final_price']:,}d")
