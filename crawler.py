import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import re
import time
from deep_translator import GoogleTranslator

def crawl_mcdonalds():
    url = "https://www.mcdonalds.co.jp/campaign/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    translator = GoogleTranslator(source='ja', target='ko')
    
    # 🌟 핵심 수정: <a> 태그 대신, 사진까지 전부 품고 있는 더 큰 부모 박스(.container-card)를 통째로 잡습니다!
    cards = soup.select(".container-card, .campaign-list-item, article")
    parsed_data = []
    seen_titles = set()

    for card in cards:
        # 1. 제목(Title) 추출 (빈방 a 태그에서 데이터 빼오기)
        title = ""
        a_tag = card.select_one("a[data-name]")
        if a_tag:
            title = a_tag.get('data-name', '').strip()
        
        if not title:
            title_tag = card.select_one("h2, h3, .title, p")
            if title_tag:
                title = title_tag.text.strip()
        
        if not title or title in seen_titles:
            continue
            
        # 2. 이미지(Image) 추출 (이제 큰 박스 안을 뒤지므로 무조건 찾아냅니다!)
        img_url = ""
        
        source_tag = card.select_one("picture source")
        if source_tag and source_tag.get("srcset"):
            img_url = source_tag.get("srcset").split(",")[0].strip().split(" ")[0]
            
        if not img_url:
            img_tag = card.select_one("img")
            if img_tag:
                for attr in ["src", "data-src", "data-original"]:
                    temp_url = img_tag.get(attr, "")
                    if temp_url and not temp_url.startswith("data:"):
                        img_url = temp_url
                        break
                        
        if img_url:
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = "https://www.mcdonalds.co.jp" + img_url

        # 3. 날짜(Date) 추출
        date_text = "진행 중인 이벤트"
        date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
        if date_match:
            date_text = date_match.group(1) + " 부터"
        else:
            date_tag = card.select_one(".container-card-text, .date, p")
            if date_tag and any(char.isdigit() for char in date_tag.text): 
                date_text = date_tag.text.strip()

        # 4. 번역 및 결과 출력
        try:
            time.sleep(1.5)
            kr_title = translator.translate(title)
            kr_date = translator.translate(date_text)
            print(f"✅ 번역 완료: {kr_title} (📸 사진: {'성공!' if img_url else '실패 ㅠㅠ'})")
        except Exception as e:
            print(f"⚠️ 번역 실패: {e}")
            kr_title = title
            kr_date = date_text
                
        parsed_data.append({
            "category": "🍱 음식점",
            "brand": "맥도날드",
            "title": kr_title,  
            "date": kr_date,    
            "imageUrl": img_url
        })
        seen_titles.add(title)
        
    return parsed_data

if __name__ == "__main__":
    print("크롤링 및 번역 시작...")
    data = crawl_mcdonalds()
    print(f"{len(data)}개의 이벤트 수집 및 번역 완료.")
    
    if data:
        firebase_key_str = os.environ.get('FIREBASE_KEY')
        if firebase_key_str:
            firebase_key = json.loads(firebase_key_str)
            cred = credentials.Certificate(firebase_key)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            
            db.collection("crawled_events").document("mcdonalds").set({"items": data})
            print("파이어베이스 업데이트 완벽 성공! 🚀")
        else:
            print("🚨 FIREBASE_KEY를 찾을 수 없습니다.")
