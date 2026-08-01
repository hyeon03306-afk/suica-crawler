import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import time
import re
from urllib.parse import urljoin

MINISTOP_URL = "https://www.ministop.co.jp/syohin/"

BLOCK_KEYWORDS = [
    "アルバイト", "パート", "募集", "採用", "求人", "店舗検索", "会社案内", "加盟店", 
    "お知らせ", "お問合せ", "サイトマップ", "アプリ", "SNS", "オーナー", "キャンペーン"
]

def is_spam(text):
    for word in BLOCK_KEYWORDS:
        if word in text: return True
    return False

def smart_translate(text, cache_dict, deepl_key):
    if not text: return ""
    if text in cache_dict: return cache_dict[text]
    if deepl_key:
        try:
            url = "https://api-free.deepl.com/v2/translate"
            headers = { "Authorization": f"DeepL-Auth-Key {deepl_key}", "Content-Type": "application/json" }
            data = {"text": [text], "target_lang": "KO"}
            res = requests.post(url, headers=headers, json=data)
            if res.status_code == 200:
                translated = res.json()['translations'][0]['text']
                cache_dict[text] = translated 
                return translated
        except Exception as e: print(f"DeepL 번역 에러: {e}")
    return text 

def crawl_ministop(db, deepl_key):
    headers = { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.ministop.co.jp/syohin/"
    }
    
    cache_ref = db.collection("system").document("translation_cache")
    cache_doc = cache_ref.get()
    trans_cache = cache_doc.to_dict() if cache_doc.exists else {}
    initial_cache_size = len(trans_cache)

    print(f"[미니스톱] 정면 돌파 크롤링 시작... (현재 번역 노트에 {initial_cache_size}개 기억 중)")
    ministop_data = []
    seen_titles = set()

    try:
        response = requests.get(MINISTOP_URL, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 🌟 페이지 전체에서 상품 이미지와 링크가 담긴 배너/카드 요소들을 전부 타격합니다!
            # 소스코드에 나왔던 productsBannerList 및 추천 영역의 링크들을 모두 수집합니다.
            targets = soup.select("#productsBannerList li a, #recommendArea a, .productList a")
            
            for target in targets:
                item_href = target.get('href', '')
                item_url = urljoin("https://www.ministop.co.jp", item_href) if item_href else ""
                
                # 이미지 alt 속성이나 텍스트에서 상품 이름을 추출합니다 (미니스톱은 alt에 상품명이 들어가 있습니다!)
                img_tag = target.select_one("img")
                raw_title = ""
                if img_tag and img_tag.get('alt'):
                    raw_title = img_tag.get('alt').strip()
                elif target.text:
                    raw_title = target.text.strip()
                
                raw_title = re.sub(r'\s+', ' ', raw_title)
                
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles: 
                    continue
                
                kr_title = smart_translate(raw_title, trans_cache, deepl_key)
                time.sleep(0.1)

                ministop_data.append({
                    "category": "🏪 편의점",
                    "brand": "미니스톱",
                    "title": kr_title,
                    "price": "", # 메인 배너에는 가격이 별도로 없어 빈값 처리
                    "date": "이번 주 신상품",
                    "region": "전국 (일부 점포 제외)",
                    "itemUrl": item_url,
                    "week": "이번주",
                    "imageUrl": ""
                })
                seen_titles.add(raw_title)
                print(f"  -> 수집됨: {kr_title}")
                    
        if len(trans_cache) > initial_cache_size:
            cache_ref.set(trans_cache)
            print(f"✅ 미니스톱: 번역 노트에 {len(trans_cache) - initial_cache_size}개 단어 추가!")
            
    except Exception as e:
        print(f"🚨 미니스톱 에러: {e}")
        
    return ministop_data

if __name__ == "__main__":
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    deepl_key = os.environ.get('DEEPL_KEY')
    
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps: firebase_admin.initialize_app(cred)
        db = firestore.client()
        ministop_items = crawl_ministop(db, deepl_key)
        if ministop_items:
            db.collection("crawled_events").document("미니스톱").set({"items": ministop_items})
            print(f"✅ 미니스톱 파이어베이스 업데이트 완료! (총 {len(ministop_items)}개)")
