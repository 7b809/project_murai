from flask import Flask, request, jsonify
from flask_cors import CORS
import requests, time, re, traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# --------- FLASK SETUP ---------
app = Flask(__name__)
CORS(app)

# --------- GRAPHQL: AniList Fetch ---------
ANILIST_URL = "https://graphql.anilist.co"

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
        description(asHtml: false)
        episodes
        season
        seasonYear
        coverImage {
          extraLarge
          large
        }
        bannerImage
        genres
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
    """Initialize a headless Chrome WebDriver"""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service("chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# --------- VIDEO EXTRACTION ---------
def press_until_video_loaded(driver, max_presses=25):
    """Try pressing 'K' repeatedly until a video URL is found in the page HTML"""
    actions = ActionChains(driver)
    body = driver.find_element(By.TAG_NAME, "body")
    pattern_m3u8 = re.compile(r'https?://[^\s"]+\.m3u8')
    pattern_mp4 = re.compile(r'https?://[^\s"]+\.mp4')

    for i in range(max_presses):
        print(f"[ACTION] Pressing K ({i+1}/{max_presses})")
        actions.move_to_element(body).click().send_keys("k").perform()
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

# --------- ROUTES (API ONLY) ---------
@app.route("/")
def root():
    return jsonify({
        "status": "ok",
        "message": "Anime API Backend is running",
        "routes": ["/anime?id=<anime_id>", "/watch/<anime_id>/<episode>"]
    })

@app.route("/anime", methods=["GET"])
def get_anime():
    """Fetch anime details by ID and return as JSON."""
    anime_id = request.args.get("id")
    if not anime_id:
        return jsonify({"status": "error", "message": "Missing 'id' parameter"}), 400

    try:
        anime = fetch_anime_details(int(anime_id))
        if not anime:
            return jsonify({"status": "error", "message": "Anime not found"}), 404

        anime["episodesList"] = list(range(1, (anime.get("episodes", 0) or 12) + 1))
        return jsonify({"status": "ok", "anime": anime})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/watch/<int:anime_id>/<int:episode>", methods=["GET"])
def watch_episode(anime_id, episode):
    """Fetch streaming video URL for a specific anime episode."""
    target_url = f"https://www.miruro.to/watch?id={anime_id}&ep={episode}"
    print(f"[INFO] Fetching video for Anime {anime_id}, Episode {episode}")

    driver = initialize_driver()
    try:
        driver.get(target_url)
        time.sleep(5)
        result = press_until_video_loaded(driver)
        driver.quit()

        if result and (result.get("mp4") or result.get("m3u8")):
            video_url = result.get("mp4") or result.get("m3u8")
            print(f"[SUCCESS] Found video: {video_url}")
            return jsonify({"status": "ok", "anime_id": anime_id, "episode": episode, "video_url": video_url})
        else:
            print("[FAIL] No video found.")
            return jsonify({"status": "error", "message": "No video found."}), 404
    except Exception as e:
        traceback.print_exc()
        driver.quit()
        return jsonify({"status": "error", "message": str(e)}), 500

# --------- MAIN ---------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
