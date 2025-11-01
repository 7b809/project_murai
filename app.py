from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import requests, re, time, traceback

ANILIST_URL = "https://graphql.anilist.co"
MIRURO_WATCH_BASE = "https://www.miruro.to/watch"


# --------- Fetch from AniList ---------
def fetch_anime_details(anime_id: int):
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title { romaji english native }
        episodes
      }
    }
    """
    response = requests.post(ANILIST_URL, json={"query": query, "variables": {"id": anime_id}})
    return response.json().get("data", {}).get("Media", None)


# --------- Selenium Setup ---------
def initialize_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(service=Service("chromedriver"), options=options)


# --------- Extract Video URL ---------
def press_until_video_loaded(driver, max_presses=25):
    actions = ActionChains(driver)
    body = driver.find_element(By.TAG_NAME, "body")
    pattern_m3u8 = re.compile(r'https?://[^\s"\'<>]+\.m3u8')
    pattern_mp4 = re.compile(r'https?://[^\s"\'<>]+\.mp4')

    for i in range(max_presses):
        try:
            actions.move_to_element(body).click().send_keys("k").perform()
        except Exception:
            pass
        time.sleep(1.2)
        html = driver.page_source

        m3u8_match = pattern_m3u8.search(html)
        mp4_match = pattern_mp4.search(html)
        if m3u8_match or mp4_match:
            return {
                "m3u8": m3u8_match.group(0) if m3u8_match else None,
                "mp4": mp4_match.group(0) if mp4_match else None
            }
    return None


# --------- Process a Single Episode ---------
def process_episode(anime_id, ep):
    watch_url = f"{MIRURO_WATCH_BASE}/{anime_id}/episode-{ep}"
    driver = None
    try:
        driver = initialize_driver()
        driver.get(watch_url)
        time.sleep(5)
        result = press_until_video_loaded(driver)
        if result:
            video_url = result.get("mp4") or result.get("m3u8")
            print(f"[DONE] Ep {ep:02d}: {video_url}")
            return {"episode": ep, "url": video_url}
        else:
            print(f"[WARN] No video URL found for Ep {ep}")
    except Exception as e:
        print(f"[ERROR] Ep {ep}: {e}")
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
    return None


# --------- MAIN ---------
def main():
    print("=== Miruro Episode Extractor (Threaded) ===")
    user_input = input("Enter anime ID or full URL: ").strip()

    anime_id = int(re.findall(r"/watch/(\d+)", user_input)[0]) if "miruro.to" in user_input else int(user_input)

    anime = fetch_anime_details(anime_id)
    if not anime:
        print("[ERROR] Could not fetch anime details from AniList.")
        return

    title = anime['title'].get('romaji') or anime['title'].get('english') or f"Anime {anime_id}"
    total_eps = min(anime.get('episodes') or 12, 25)

    print(f"[INFO] Title: {title}")
    print(f"[INFO] Episodes: {total_eps}")
    print("-" * 60)

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_episode, anime_id, ep): ep for ep in range(1, total_eps + 1)}

        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    # Sort results by episode number
    results.sort(key=lambda x: x["episode"])

    print("\n=== Extraction Completed ===")
    for r in results:
        print(f"Ep {r['episode']:02d}: {r['url']}")

    # Save results
    with open(f"miruro_{anime_id}_videos.txt", "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"Episode {r['episode']}: {r['url']}\n")

    print(f"\nSaved results to miruro_{anime_id}_videos.txt")


if __name__ == "__main__":
    main()
