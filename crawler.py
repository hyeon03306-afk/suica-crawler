import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json

def crawl_mcdonalds():
    url = "https://www.mcdonalds.co.jp/campaign/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    cards = soup.select(".campaign-list .campaign-list-item, .container-card-link, article")
    parsed_data = []
    seen_titles = set()

    for card in cards:
        title = card.get('data-name', '').strip()
        if not title:
            # 🌟 [수정 완료] 파이썬 문법인 select_one으로 변경했습니다!
            title_tag = card.select_one("h2, h3, .title, p")
            if title_tag:
                title = title_tag.text.strip()
        
        if not title or title in seen_titles:
            continue
            
        img_url = ""
        # 🌟 [수정 완료] 파이썬 문법인 select_one으로 변경했습니다!
        img_tag = card.select_one("img")
        if img_tag:
            img_url = img_tag.get("data-original", "")
            if not img_url or img_url.startswith("data:"):
                img_url = img_tag.get("data-src", "")
            if not img_url or img_url.startswith("data:"):
                img_url = img_tag.get("src", "")
                
        if not img_url or img_url.startswith("data:"):
            # 🌟 [수정 완료] 파이썬 문법인 select_one으로 변경했습니다!
            source_tag = card.select_one("picture source")
            if source_tag:
                img_url = source_tag.get("srcset", "").split(",")[0].split(" ")[0].strip()
                
        if img_url:
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = "https://www.mcdonalds.co.jp" + img_url
                
        parsed_data.append({
            "category": "🍱 음식점",
            "brand": "맥도날드",
            "title": title,
            "imageUrl": img_url
        })
        seen_titles.add(title)
        
    return parsed_data

if __name__ == "__main__":
    print("크롤링 시작...")
    data = crawl_mcdonalds()
    print(f"{len(data)}개의 이벤트 데이터 수집 완료.")
    
    if data:
        # 깃허브 비밀금고에서 마스터키 꺼내오기
        firebase_key_str = os.environ.get('FIREBASE_KEY')
        if firebase_key_str:
            firebase_key = json.loads(firebase_key_str)
            cred = credentials.Certificate(firebase_key)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            
            # 파이어베이스 창고에 밀어넣기
            db.collection("crawled_events").document("mcdonalds").set({"items": data})
            print("파이어베이스 업데이트 완벽 성공! 🚀")
        else:
            print("🚨 FIREBASE_KEY를 찾을 수 없습니다.")
