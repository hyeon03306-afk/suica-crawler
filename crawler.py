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
            
        # 🌟 얌전한 방식 폐기! 무식하지만 가장 확실한 '불도저' 추출기 도입
        img_url = ""
        raw_html = str(card) # 카드의 HTML 전체를 그냥 하나의 통글자로 변환
        
        # 1. src, data-src, srcset, url() 안에 있는 모든 텍스트 무지성 추출
        candidates = re.findall(r'(?:src|data-src|data-original|srcset)\s*=\s*[\'"]([^\'"]+)[\'"]', raw_html, re.IGNORECASE)
        candidates += re.findall(r'url\([\'"]?([^\'"\)]+)[\'"]?\)', raw_html, re.IGNORECASE)
        
        # 2. 태그 이름이 뭐든 상관없이 .jpg, .png, .webp 로 끝나는 주소가 있으면 무조건 쓸어담기 (핵심!)
        candidates += re.findall(r'[\'"]([^\'"]+\.(?:jpg|jpeg|png|webp|gif)[^\'"]*)[\'"]', raw_html, re.IGNORECASE)

        for candidate in candidates:
            # srcset처럼 쉼표로 여러 개가 엮여있으면 맨 앞 1개만 깔끔하게 자르기
            clean_url = candidate.split(',')[0].split(' ')[0].strip()
            
            # 쓸모없는 아이콘이나 빈 값은 패스
            if not clean_url or clean_url.startswith("data:") or clean_url.endswith(".svg"):
                continue
                
            img_url = clean_url
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = "https://www.mcdonalds.co.jp" + img_url
            break # 📸 진짜 사진 주소를 하나 찾았으면 그 즉시 탈출!

        # 날짜 핀셋 추출
        date_text = "진행 중인 이벤트"
        date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
        if date_match:
            date_text = date_match.group(1) + " 부터"
        else:
            date_tag = card.select_one(".campaign-list-item-date, .date, p")
            if date_tag and any(char.isdigit() for char in date_tag.text): 
                date_text = date_tag.text.strip()

        # 번역기 실행
        try:
            time.sleep(1.5)
            kr_title = translator.translate(title)
            kr_date = translator.translate(date_text)
            # 로그 창에서 사진을 성공적으로 찾았는지 바로 확인 가능하도록 수정!
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
