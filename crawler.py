import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import re        # 🌟 날짜 뽑아내는 돋보기 부품
import time      # 🌟 1초 쉬게 만드는 타이머 부품
from deep_translator import GoogleTranslator

def crawl_mcdonalds():
    url = "https://www.mcdonalds.co.jp/campaign/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    translator = GoogleTranslator(source='ja', target='ko')
    
    cards = soup.select(".campaign-list .campaign-list-item, .container-card-link, article")
    parsed_data = []
    seen_titles = set()

    for card in cards:
        title = card.get('data-name', '').strip()
        if not title:
            title_tag = card.select_one("h2, h3, .title, p")
            if title_tag:
                title = title_tag.text.strip()
        
        if not title or title in seen_titles:
            continue
            
        # 🌟 강력한 이미지 핀셋 업그레이드 (숨겨진 이미지까지 싹 다 찾기)
        img_url = ""
        
        # 1. 일반 img 태그 싹 뒤지기
        img_tag = card.select_one("img")
        if img_tag:
            for attr in ["data-original", "data-src", "src"]:
                temp_url = img_tag.get(attr, "")
                if temp_url and not temp_url.startswith("data:"):
                    img_url = temp_url
                    break
                    
        # 2. picture source 태그 뒤지기
        if not img_url:
            source_tag = card.select_one("source")
            if source_tag:
                temp_url = source_tag.get("srcset", "")
                if temp_url and not temp_url.startswith("data:"):
                    img_url = temp_url.split(",")[0].split(" ")[0].strip()

        # 3. 만약 배경 이미지(background-image)로 숨겨둔 경우
        if not img_url:
            bg_tags = card.select("[style*='background']")
            for bg in bg_tags:
                style = bg.get("style", "")
                match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
                if match:
                    temp_url = match.group(1)
                    if not temp_url.startswith("data:"):
                        img_url = temp_url
                        break
                        
        if img_url:
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = "https://www.mcdonalds.co.jp" + img_url

        # 🌟 날짜 핀셋 추출 (정규표현식 사용)
        date_text = "진행 중인 이벤트"
        date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
        if date_match:
            date_text = date_match.group(1) + " 부터" # 예: 7/22(水) 부터
        else:
            date_tag = card.select_one(".campaign-list-item-date, .date, p")
            if date_tag and any(char.isdigit() for char in date_tag.text): 
                date_text = date_tag.text.strip()

        # 🌟 구글 차단 방지용 1초 대기 후 번역
        try:
            time.sleep(1.5) # 사람이 하는 것처럼 1.5초 쉬었다가 번역 (핵심!)
            kr_title = translator.translate(title)
            kr_date = translator.translate(date_text)
            print(f"✅ 번역 완료: {kr_title}")
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
