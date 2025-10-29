from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests, time, re, traceback, os, zipfile, subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# --------- FLASK SETUP ---------
app = Flask(__name__, template_folder="templates")
CORS(app)  # Enable Cross-Origin Resource Sharing

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
    """Initialize Selenium ChromeDriver, auto-download if not found."""
    driver_path = "./chromedriver"

    # If chromedriver not found, download and extract it automatically
    if not os.path.exists(driver_path):
        print("[INFO] chromedriver not found. Downloading...")
        url = "https://storage.googleapis.com/chrome-for-testing-public/129.0.6668.90/linux64/chromedriver-linux64.zip"
        zip_path = "chromedriver-linux64.zip"

        # Download ZIP file
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            raise Exception(f"Failed to download chromedriver: HTTP {r.status_code}")
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        # Extract the ZIP
        print("[INFO] Extracting chromedriver...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(".")

        # Move the executable and clean up
        extracted_driver = "chromedriver-linux64/chromedriver"
        if os.path.exists(extracted_driver):
            os.replace(extracted_driver, driver_path)
        os.chmod(driver_path, 0o755)

        subprocess.run(["rm", "-rf", "chromedriver-linux64"], check=False)
        os.remove(zip_path)
        print("[INFO] chromedriver downloaded and ready.")

    # Setup Chrome options
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


# --------- VIDEO EXTRACTION ---------
def press_until_video_loaded(driver, max_presses=25):
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


# --------- ROUTES ---------
@app.route("/", methods=["GET"])
def home():
    """Homepage: ask for anime ID to fetch details."""
    return render_template("index.html")


@app.route("/anime", methods=["POST"])
def get_anime():
    """Fetch anime data and show episodes as cards."""
    anime_id = request.form.get("anime_id")
    if not anime_id:
        return render_template("index.html", error="Please enter a valid Anime ID")

    anime = fetch_anime_details(int(anime_id))
    if not anime:
        return render_template("index.html", error="Anime not found")

    total_eps = anime.get("episodes", 0) or 12
    episodes = list(range(1, total_eps + 1))

    return render_template("index.html", anime=anime, episodes=episodes)


@app.route("/watch/<int:anime_id>/<int:episode>", methods=["GET"])
def watch_episode(anime_id, episode):
    """Fetch episode streaming link and return as JSON (used by frontend JS)."""
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
            return jsonify({"status": "ok", "watch_url": video_url})
        else:
            print("[FAIL] No video found.")
            return jsonify({"status": "error", "message": "No video found."})
    except Exception as e:
        traceback.print_exc()
        driver.quit()
        return jsonify({"status": "error", "message": str(e)})


# --------- MAIN ---------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
    
