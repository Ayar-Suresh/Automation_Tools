# scrape_9anime.py
import json
import time
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementClickInterceptedException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


# ---------- CONFIG ----------
START_URL = "https://9anime.org.lv/"
HEADLESS = True          # set False to watch the browser
PAGE_LOAD_TIMEOUT = 20
IMPLICIT_WAIT = 5
SERVER_CLICK_WAIT = 4    # wait after clicking server button for iframe to update
DOWNLOAD_AJAX_TIMEOUT = 8
OUTPUT_FILE = "results.json"
# ----------------------------


def create_driver(headless: bool = True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1200,1000")
    # Avoid detection-ish flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(IMPLICIT_WAIT)
    return driver


def parse_homepage_cards(html: str) -> List[Dict]:
    """Uses BeautifulSoup to parse article cards from homepage HTML (fallback)."""
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.find_all("article", class_="bs")
    results = []
    for a in articles:
        try:
            a_tag = a.find("a", href=True)
            page_url = a_tag["href"].strip() if a_tag else None

            title = None
            h2 = a.find("h2", itemprop="headline")
            if h2:
                title = h2.get_text(strip=True)

            # sometimes the visible title sits in .tt as text
            tt = a.find("div", class_="tt")
            if tt and not title:
                title = tt.get_text(strip=True)

            epx = a.find("span", class_="epx")
            episode_text = epx.get_text(strip=True) if epx else None

            sb = a.find("span", class_="sb")
            type_text = sb.get_text(strip=True) if sb else None

            img = a.find("img")
            img_url = img.get("src") if img else None

            results.append({
                "page_url": page_url,
                "title": title,
                "episode_text": episode_text,
                "type": type_text,
                "image": img_url
            })
        except Exception:
            continue
    return results


def safe_text(el) -> Optional[str]:
    try:
        return el.text.strip()
    except Exception:
        return None


def click_and_get_iframe(driver, server_button) -> Optional[str]:
    """
    Click the server button (a <button> or option) and wait for iframe to update.
    Returns iframe src or None.
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", server_button)
        try:
            server_button.click()
        except ElementClickInterceptedException:
            # fallback: use JS click
            driver.execute_script("arguments[0].click();", server_button)
        # wait a bit for iframe to change/load
        time.sleep(SERVER_CLICK_WAIT)
        # look for iframe inside .player-embed or #embed_holder
        iframe = None
        try:
            iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".player-embed iframe, #embed_holder iframe"))
            )
        except TimeoutException:
            # try a looser search
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            iframe = frames[-1] if frames else None

        if iframe:
            src = iframe.get_attribute("src")
            return src
    except Exception:
        return None
    return None


def fetch_download_links_via_click(driver) -> List[str]:
    """
    Click #download-btn if present and wait for #download-links content.
    Return list of hrefs found inside #download-links.
    """
    links = []
    try:
        download_btn = driver.find_element(By.CSS_SELECTOR, "#download-btn")
    except NoSuchElementException:
        return links

    try:
        # click to trigger AJAX
        try:
            download_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", download_btn)

        # wait for #download-links to be populated or a modal to show
        try:
            WebDriverWait(driver, DOWNLOAD_AJAX_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#download-links a"))
            )
        except TimeoutException:
            # maybe the server returned no links or 500 message; still try to read innerHTML
            pass

        # collect links inside #download-links (links and buttons)
        try:
            container = driver.find_element(By.CSS_SELECTOR, "#download-links")
            anchor_elems = container.find_elements(By.TAG_NAME, "a")
            for a in anchor_elems:
                href = a.get_attribute("href")
                if href:
                    links.append(href)
            # sometimes links are in buttons with data-href etc
            btns = container.find_elements(By.TAG_NAME, "button")
            for b in btns:
                if b.get_attribute("data-href"):
                    links.append(b.get_attribute("data-href"))
        except NoSuchElementException:
            pass
    except Exception:
        pass

    return links


def scrape_anime_page(driver, page_url: str) -> Dict:
    """
    Open anime page and extract:
      - episode title/number/type/image/release date
      - video servers and iframe URLs
      - download links
    """
    result = {
        "page_url": page_url,
        "title": None,
        "episode": None,
        "type": None,
        "image": None,
        "released_on": None,
        "series": None,
        "video_servers": [],
        "download_links": []
    }

    try:
        driver.get(page_url)
    except Exception as e:
        print("Page load failed:", page_url, e)
        return result

    # Wait for main content to appear
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article, .megavid, #embed_holder"))
        )
    except TimeoutException:
        # continue anyway
        pass

    # parse some metadata
    try:
        # title
        try:
            title_el = driver.find_element(By.CSS_SELECTOR, "h1.entry-title, h1[itemprop='name']")
            result["title"] = safe_text(title_el)
        except NoSuchElementException:
            pass

        # episode number
        try:
            ep_meta = driver.find_element(By.CSS_SELECTOR, "meta[itemprop='episodeNumber']")
            result["episode"] = ep_meta.get_attribute("content")
        except NoSuchElementException:
            # fallback to .epx text
            try:
                epx = driver.find_element(By.CSS_SELECTOR, ".epx")
                result["episode"] = safe_text(epx)
            except NoSuchElementException:
                pass

        # type (Sub/Dub)
        try:
            typ = driver.find_element(By.CSS_SELECTOR, ".status, .sb")
            result["type"] = safe_text(typ)
        except NoSuchElementException:
            pass

        # released date
        try:
            rel = driver.find_element(By.CSS_SELECTOR, "span.updated, meta[itemprop='datePublished']")
            if rel.tag_name == "meta":
                result["released_on"] = rel.get_attribute("content")
            else:
                result["released_on"] = safe_text(rel)
        except NoSuchElementException:
            pass

        # series link/name
        try:
            series_a = driver.find_element(By.CSS_SELECTOR, "a[href*='/anime/']")
            result["series"] = series_a.get_attribute("href")
        except NoSuchElementException:
            pass

        # thumbnail image
        try:
            img = driver.find_element(By.CSS_SELECTOR, ".tb img, .mvelement img, meta[itemprop='image']")
            if img.tag_name == "meta":
                result["image"] = img.get_attribute("content")
            else:
                result["image"] = img.get_attribute("src")
        except NoSuchElementException:
            pass
    except Exception:
        pass

    # Collect server buttons (common patterns: #buttonContainer button, .mirror select options, .ps__-title buttons)
    server_buttons = []
    try:
        # prefer visible button container
        button_elems = driver.find_elements(By.CSS_SELECTOR, "#buttonContainer button, .player-servers button, .ps__-title button")
        for b in button_elems:
            # ensure it is clickable and has text
            name = b.text.strip() or b.get_attribute("data-option-id") or b.get_attribute("value")
            server_buttons.append((b, name))
    except Exception:
        pass

    # If no button elements, check for select .mirror options; we'll emulate selecting each option
    select_elem = None
    select_options = []
    try:
        select_elem = driver.find_element(By.CSS_SELECTOR, "select.mirror")
        opts = select_elem.find_elements(By.TAG_NAME, "option")
        for opt in opts:
            val = opt.get_attribute("value")
            txt = opt.text.strip()
            if val:
                select_options.append((opt, txt))
    except NoSuchElementException:
        select_elem = None

    # If we have button elements, click each
    if server_buttons:
        seen_iframes = set()
        for b, name in server_buttons:
            try:
                src = click_and_get_iframe(driver, b)
                if src and src not in seen_iframes:
                    result["video_servers"].append({"server_name": name or "unknown", "iframe_url": src})
                    seen_iframes.add(src)
            except Exception:
                continue
    elif select_elem and select_options:
        # iterate through options and trigger change
        seen_iframes = set()
        for opt, txt in select_options:
            try:
                # select via javascript to ensure change event fires
                driver.execute_script("arguments[0].selected = true; arguments[0].parentNode.dispatchEvent(new Event('change'))", opt)
                time.sleep(SERVER_CLICK_WAIT)
                # find iframe
                try:
                    iframe = driver.find_element(By.CSS_SELECTOR, ".player-embed iframe, #embed_holder iframe")
                    src = iframe.get_attribute("src")
                    if src and src not in seen_iframes:
                        result["video_servers"].append({"server_name": txt or "option", "iframe_url": src})
                        seen_iframes.add(src)
                except NoSuchElementException:
                    # fallback: collect all iframes
                    frames = driver.find_elements(By.TAG_NAME, "iframe")
                    if frames:
                        src = frames[-1].get_attribute("src")
                        if src and src not in seen_iframes:
                            result["video_servers"].append({"server_name": txt or "option", "iframe_url": src})
                            seen_iframes.add(src)
            except Exception:
                continue
    else:
        # fallback: collect any iframes present on page
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        seen = set()
        for f in frames:
            s = f.get_attribute("src")
            if s and s not in seen:
                result["video_servers"].append({"server_name": "iframe", "iframe_url": s})
                seen.add(s)

    # Try to fetch download links via clicking the download button
    result["download_links"] = fetch_download_links_via_click(driver)

    return result


def main():
    driver = create_driver(headless=HEADLESS)
    results = []
    try:
        print("Loading homepage:", START_URL)
        driver.get(START_URL)
        time.sleep(2)  # allow some JS to run

        # Prefer to find article cards via selenium first
        article_elems = driver.find_elements(By.CSS_SELECTOR, "article.bs")
        cards = []

        if article_elems:
            for art in article_elems:
                try:
                    a_tag = art.find_element(By.CSS_SELECTOR, "a[itemprop='url'], a[href]")
                    page_url = a_tag.get_attribute("href")
                except NoSuchElementException:
                    page_url = None

                # title
                title = None
                try:
                    h2 = art.find_element(By.CSS_SELECTOR, "h2[itemprop='headline']")
                    title = h2.text.strip()
                except NoSuchElementException:
                    try:
                        tt = art.find_element(By.CSS_SELECTOR, ".tt")
                        title = tt.text.strip()
                    except NoSuchElementException:
                        title = None

                # episode
                ep_text = None
                try:
                    ep = art.find_element(By.CSS_SELECTOR, ".epx")
                    ep_text = ep.text.strip()
                except NoSuchElementException:
                    pass

                # sub/dub
                type_text = None
                try:
                    sb = art.find_element(By.CSS_SELECTOR, ".sb")
                    type_text = sb.text.strip()
                except NoSuchElementException:
                    pass

                # image
                img_url = None
                try:
                    img = art.find_element(By.CSS_SELECTOR, "img")
                    img_url = img.get_attribute("src")
                except NoSuchElementException:
                    pass

                if page_url:
                    cards.append({
                        "page_url": page_url,
                        "title": title,
                        "episode_text": ep_text,
                        "type": type_text,
                        "image": img_url
                    })
        else:
            # fallback: parse page source with BeautifulSoup
            print("No article elements found with Selenium; trying BeautifulSoup fallback.")
            html = driver.page_source
            cards = parse_homepage_cards(html)

        print(f"Found {len(cards)} anime cards on homepage.")

        # iterate through cards and scrape each page
        for idx, card in enumerate(cards, 1):
            page = card.get("page_url")
            if not page:
                continue
            print(f"[{idx}/{len(cards)}] Scraping: {page}")
            scraped = scrape_anime_page(driver, page)
            # merge basic card data
            for k in ("title", "episode_text", "type", "image"):
                if card.get(k) and not scraped.get(k if k != "episode_text" else "episode"):
                    if k == "episode_text":
                        scraped["episode"] = card[k]
                    else:
                        scraped[k] = card[k]
            results.append(scraped)

    except Exception as e:
        print("An error occurred:", e)
    finally:
        driver.quit()

    # Save results
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Scraping finished. Saved {len(results)} items to {OUTPUT_FILE}.")


if __name__ == "__main__":
    main()
