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

# 편의점별 이벤트 URL 정보
TARGET_SITES = {
    "세븐일레븐": "https://www.sej.co.jp/cmp/",
    "로손": "https://www.lawson.co.jp/recommend/campaign/",
    "패밀리마트": "https://www.family.co.jp/campaign.html",
    "미니스톱": "https://www.ministop.co.jp/corporate/campaign/",
    "뉴데이즈": "https://waters.jr-cross.co.jp/campaign/" # 또는 일반 캠페인 페이지
}

def crawl_convenience_stores():
    translator = GoogleTranslator(source='ja', target='ko')
    all_store_data = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for brand_name, url in TARGET_SITES.items():
        print(f"[{brand_name}] 크롤링 시작...")
        parsed_data = []
        seen_titles = set()

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"⚠️ {brand_name} 접속 실패 (코드: {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 각 편의점 사이트 공통 카드/리스트 요소 선택자 광범위 탐색
            cards = soup.select("article, .card, .item, .campaign-list li, .list li, li a, .box")
            if not cards:
                cards = soup.select("a") # 태그가 안 잡히면 링크형태로 탐색

            for card in cards:
                title = ""
                # 1. 텍스트 추출 시도
                title_tag = card.select_one("h2, h3, h4, .title, .name, p")
                if title_tag:
                    title = title_tag.text.strip()
                elif card.name == 'a' and len(card.text.strip()) > 5:
                    title = card.text.strip()

                # 너무 짧거나 중복된 제목 필터링
                if not title or len(title) < 4 or title in seen_titles:
                    continue

                # 날짜 핀셋 추출
                date_text = "진행 중인 이벤트"
                date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
                if date_match:
                    date_text = date_match.group(1) + " 부터"
                else:
                    date_tag = card.select_one(".date, time, .period")
                    if date_tag and any(char.isdigit() for char in date_tag.text):
                        date_text = date_tag.text.strip()

                # 번역 (구글 차단 방지 1초 대기)
                try:
                    time.sleep(1.0)
                    kr_title = translator.translate(title[:50]) # 너무 길면 자름
                    kr_date = translator.translate(date_text[:30])
                except:
                    kr_title = title
                    kr_date = date_text

                parsed_data.append({
                    "category": "🏪 편의점",
                    "brand": brand_name,
                    "title": kr_title,
                    "date": kr_date,
                    "imageUrl": ""
                })
                seen_titles.add(title)

                # 한 브랜드당 최대 15개까지만 깔끔하게 수집
                if len(parsed_data) >= 15:
                    break

            all_store_data[brand_name] = parsed_data
            print(f"✅ {brand_name}: {len(parsed_data)}개 수집 완료")

        except Exception as e:
            print(f"🚨 {brand_name} 크롤링 중 에러 발생: {e}")
            all_store_data[brand_name] = []

    return all_store_data

if __name__ == "__main__":
    print("편의점 통합 크롤링 및 번역 시작...")
    data_map = crawl_convenience_stores()

    firebase_key_str = os.environ.get('FIREBASE_KEY')
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()

        # 각 편의점별 문서(document)로 각각 저장
        for brand, items in data_map.items():
            if items:
                db.collection("crawled_events").document(brand).set({"items": items})
        
        print("모든 편의점 파이어베이스 업데이트 완벽 성공! 🚀")
    else:
        print("🚨 FIREBASE_KEY를 찾을 수 없습니다.")
