import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
from deep_translator import GoogleTranslator # 🌟 번역기 칩 장착!

def crawl_mcdonalds():
    url = "https://www.mcdonalds.co.jp/campaign/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 일한 번역기 준비
    translator = GoogleTranslator(source='ja', target='ko')
    
    cards = soup.select(".campaign-list .campaign-list-item, .container-card-link, article")
    parsed_data = []
    seen_titles = set()

    for card in cards:
        # 1. 제목 긁어오기
        title = card.get('data-name', '').strip()
        if not title:
            title_tag = card.select_one("h2, h3, .title, p")
            if title_tag:
                title = title_tag.text.strip()
        
        if not title or title in seen_titles:
            continue
            
        # 2. 이미지 긁어오기
        img_url = ""
        img_tag = card.select_one("img")
        if img_tag:
            img_url = img_tag.get("data-original", "")
            if not img_url or img_url.startswith("data:"):
                img_url = img_tag.get("data-src", "")
            if not img_url or img_url.startswith("data:"):
                img_url = img_tag.get("src", "")
                
        if not img_url or img_url.startswith("data:"):
            source_tag = card.select_one("picture source")
            if source_tag:
                img_url = source_tag.get("srcset", "").split(",")[0].split(" ")[0].strip()
                
        if img_url:
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = "https://www.mcdonalds.co.jp" + img_url

        # 🌟 3. 날짜(기간) 긁어오기
        date_text = "진행 중인 이벤트" # 기본값
        date_tag = card.select_one(".campaign-list-item-date, .date, p")
        if date_tag and any(char.isdigit() for char in date_tag.text): 
            date_text = date_tag.text.strip()

        # 🌟 4. 한국어로 번역하기 (실패 시 원본 일본어 유지 + 에러 원인 출력)
        try:
            kr_title = translator.translate(title)
            kr_date = translator.translate(date_text)
            print(f"✅ 번역 성공: {kr_title}") # 성공하면 로그에 띄움
        except Exception as e:
            print(f"⚠️ 번역 실패 (원인): {e}") # 실패하면 이유를 로그에 띄움
            kr_title = title
            kr_date = date_text
                
        parsed_data.append({
            "category": "🍱 음식점",
            "brand": "맥도날드",
            "title": kr_title,  # 번역된 제목 저장!
            "date": kr_date,    # 번역된 날짜 저장!
            "imageUrl": img_url
        })
        seen_titles.add(title)
        
    return parsed_data

if __name__ == "__main__":
    print("크롤링 및 번역 시작...")
    data = crawl_mcdonalds()
    print(f"{len(data)}개의 이벤트 데이터 수집 및 한국어 번역 완료.")
    
    if data:
        firebase_key_str = os.environ.get('FIREBASE_KEY')
        if firebase_key_str:
            firebase_key = json.loads(firebase_key_str)
            cred = credentials.Certificate(firebase_key)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            
            db.collection("crawled_events").document("mcdonalds").set({"items": data})
            print("한국어 패치 데이터 파이어베이스 업데이트 성공! 🚀")
        else:
            print("🚨 FIREBASE_KEY를 찾을 수 없습니다.")
