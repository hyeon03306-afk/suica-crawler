import requests
import os
import json

MINISTOP_API_URL = "https://www.ministop.co.jp/syohin/json/s_syohin_thisweek.json"

print("🔍 [미니스톱 진단 봇] 실행 시작...")

headers = { 
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.ministop.co.jp/syohin/"
}

try:
    print(f"👉 1. 미니스톱 API 주소로 요청을 보냅니다: {MINISTOP_API_URL}")
    response = requests.get(MINISTOP_API_URL, headers=headers, timeout=15)
    
    print(f"👉 2. 미니스톱 서버 응답 코드: {response.status_code}")
    print(f"👉 3. 응답 내용 앞부분 (100글자): {response.text[:100]}")
    
    if response.status_code == 200:
        json_text = response.text.strip()
        if json_text.startswith('\ufeff'):
            json_text = json_text[1:]
            
        items = json.loads(json_text)
        print(f"👉 4. 성공! 총 {len(items)}개의 상품 데이터를 받아왔습니다!")
    else:
        print("👉 4. 🔴 서버가 정상 응답을 주지 않았습니다.")

except Exception as e:
    print(f"🚨 [치명적 에러 발생]: {str(e)}")

print("🔍 [미니스톱 진단 봇] 종료.")
