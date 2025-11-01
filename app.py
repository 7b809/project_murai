from flask import Flask
import requests, time, re, traceback, platform
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------- CONSTANTS ---------
ANILIST_URL = "https://graphql.anilist.co"
MIRURO_WATCH_BASE = "https://www.miruro.to/watch"

# --------- FETCH FROM ANILIST ---------
def fetch_anime_details(anime_id: int):
    """Fetch anime details (title, desc, cover, etc.) from AniList GraphQL API"""
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title {
          romaji
          english
          native
        }
        episodes
        season
        seasonYear
        coverImage {
          extraLarge
        }
        averageScore
      }
    }
    """
    variables = {"id": anime_id}
    response = requests.post(ANILIST_URL, json={"query": query, "variables": variables})
    data = response.json()
    return data.get("data", {}).get("Media", None)

# --------- SELENIUM CHROME DRIVER SETUP ---------
def initialize_driver():
    """Initialize a headless Chrome WebDriver (works on Windows + Colab)"""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    system = platform.system().lower()
    if "linux" in system:
        # For Google Colab or Linux environment
        chrome_path = "/usr/bin/chromedriver"
        options.binary_location = "/usr/bin/chromium-browser"
    else:
        # For Windows (local run)
        chrome_path = "chromedriver.exe"

    service = Service(chrome_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# --------- VIDEO EXTRACTION ---------
def press_until_video_loaded(driver, max_presses=25):
    """Try pressing 'K' repeatedly until a video URL is found in the page HTML"""
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

# --------- PROCESS ONE EPISODE ---------
def process_episode(anime_id, ep):
    """Open episode page, extract video URL"""
    driver = None
    try:
        driver = initialize_driver()
        watch_url = f"{MIRURO_WATCH_BASE}/{anime_id}/episode-{ep}"
        driver.get(watch_url)
        time.sleep(5)
        result = press_until_video_loaded(driver)
        if result:
            video_url = result.get("mp4") or result.get("m3u8")
            print(f"[DONE] Ep {ep}: {video_url}")
            return {"episode": ep, "url": video_url}
        else:
            print(f"[WARN] No video found for Ep {ep}")
            return {"episode": ep, "url": None}
    except Exception as e:
        print(f"[ERROR] Episode {ep}: {e}")
        traceback.print_exc()
        return {"episode": ep, "url": None}
    finally:
        if driver:
            driver.quit()

# --------- MAIN LOGIC ---------
def main():
    print("=== Miruro Episode Extractor ===")
    user_input = input("Enter anime ID or full URL: ").strip()

    # Extract ID from input
    if "miruro.to" in user_input:
        anime_id = int(re.findall(r"/watch/(\d+)", user_input)[0])
    else:
        anime_id = int(user_input)

    print(f"[INFO] Fetching details for Anime ID {anime_id}...")
    anime = fetch_anime_details(anime_id)
    if not anime:
        print("[ERROR] Could not fetch anime details from AniList.")
        return

    title = anime['title'].get('romaji') or anime['title'].get('english') or f"Anime {anime_id}"
    total_eps = anime.get('episodes') or 12
    total_eps = min(total_eps, 25)  # limit to 25 episodes

    print(f"[INFO] Title: {title}")
    print(f"[INFO] Episodes: {total_eps}")
    print("-" * 60)

    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_episode, anime_id, ep) for ep in range(1, total_eps + 1)]

        for future in as_completed(futures):
            res = future.result()
            if res and res.get("url"):
                results.append(res)

    print("\n=== Extraction Completed ===")
    for r in sorted(results, key=lambda x: x['episode']):
        print(f"Ep {r['episode']:02d}: {r['url']}")

    # Optionally save results
    filename = f"miruro_{anime_id}_videos.txt"
    with open(filename, "w", encoding="utf-8") as f:
        for r in sorted(results, key=lambda x: x['episode']):
            f.write(f"Episode {r['episode']}: {r['url']}\n")

    print(f"\nSaved results to {filename}")

# --------- RUN ---------
if __name__ == "__main__":
    main()
