import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import time
from urllib.parse import urljoin

MINISTOP_URL = "https://www.ministop.co.jp/syohin/"

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
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    cache_ref = db.collection("system").document("translation_cache")
    cache_doc = cache_ref.get()
    trans_cache = cache_doc.to_dict() if cache_doc.exists else {}
    initial_cache_size = len(trans_cache)

    print(f"[미니스톱] 전용 크롤링 시작... (현재 번역 노트에 {initial_cache_size}개 기억 중)")
    ministop_data = []
    seen_titles = set()

    try:
        response = requests.get(MINISTOP_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 🌟 진짜 F12 구조 반영: div#recommendArea 이하의 li 태그들
            cards = soup.select("#recommendArea li, .productList li")
            
            for card in cards:
                a_tag = card.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin("https://www.ministop.co.jp", item_href) if item_href else ""
                
                # 🌟 진짜 F12 구조 반영: 클래스가 name, price인 것 찾기
                title_tag = card.select_one(".name, h3")
                raw_title = title_tag.text.strip() if title_tag else ""
                if not raw_title or raw_title in seen_titles: continue
                
                price_tag = card.select_one(".price")
                raw_price = price_tag.text.strip() if price_tag else ""
                raw_price = raw_price.replace("税込", "(税込").replace("円", "円)") 
                
                kr_title = smart_translate(raw_title, trans_cache, deepl_key)
                kr_price = smart_translate(raw_price, trans_cache, deepl_key) if raw_price else ""
                time.sleep(0.1)

                ministop_data.append({
                    "category": "🏪 편의점",
                    "brand": "미니스톱",
                    "title": kr_title,
                    "price": kr_price,
                    "date": "이번 주 신상품",
                    "region": "전국 (일부 점포 제외)",
                    "itemUrl": item_url,
                    "week": "",
                    "imageUrl": ""
                })
                seen_titles.add(raw_title)
                    
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
            print(f"✅ 미니스톱 업데이트 완료! (총 {len(ministop_items)}개)")
