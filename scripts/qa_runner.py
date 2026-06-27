import asyncio
from playwright.async_api import async_playwright
import json
import time

targets = [
    {"name": "TRAPPIST-1", "source": "TESS (via Lightkurve)", "depth": 2, "snr": 5.0},
    {"name": "Kepler-11", "source": "Kepler (via Lightkurve)", "depth": 3, "snr": 6.0},
    {"name": "WASP-12 b", "source": "TESS (via Lightkurve)", "depth": 1, "snr": 10.0},
    {"name": "K2-138", "source": "Kepler (via Lightkurve)", "depth": 3, "snr": 5.5},
    {"name": "Kepler-20", "source": "Kepler (via Lightkurve)", "depth": 3, "snr": 4.5},
    {"name": "AU Mic", "source": "TESS (via Lightkurve)", "depth": 2, "snr": 6.0},
    {"name": "HD 80606 b", "source": "TESS (via Lightkurve)", "depth": 1, "snr": 7.0},
    {"name": "TOI-700", "source": "TESS (via Lightkurve)", "depth": 2, "snr": 4.8},
    {"name": "Kepler-4d", "source": "Kepler (via Lightkurve)", "depth": 1, "snr": 6.5},
    {"name": "Kepler-90", "source": "Kepler (via Lightkurve)", "depth": 3, "snr": 5.0}
]

async def set_slider(page, label_text, target_val, min_val, max_val, step=1):
    print(f"Setting slider {label_text} to {target_val}...")
    try:
        slider = page.locator(f"div:has-text('{label_text}')").locator("div[role='slider']").first
        await slider.focus()
        await page.keyboard.press("Home")
        await page.wait_for_timeout(200)
        
        steps = int(round((target_val - min_val) / step))
        for _ in range(steps):
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(50)
    except Exception as e:
        print(f"Error setting slider {label_text}: {e}")

async def run_target(p, target_info):
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1920, "height": 1080})
    
    t_name = target_info["name"]
    t_source = target_info["source"]
        
    print(f"\n--- Testing {t_name} ---")
    await page.goto("http://localhost:8501", timeout=30000)
    
    # Wait for hydration
    await page.wait_for_selector(".stApp", state="attached")
    await page.wait_for_timeout(3000)
    
    # Click Detective Tab in the Sidebar
    print("Waiting for Detective tab...")
    try:
        det_tab = page.locator("text=Detective").first
        await det_tab.wait_for(state="visible", timeout=30000)
        await det_tab.click()
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Could not click Detective tab: {e}")
    
    print("Finding search input...")
    # Streamlit text input might take a moment to appear after clicking the tab
    try:
        target_input = page.locator('div[data-testid="stTextInput"] input').first
        await target_input.wait_for(state="visible", timeout=30000)
        await target_input.fill("")
        await target_input.fill(t_name)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1000)
    except Exception as e:
        print(f"FAILED to find text input: {e}")
        await browser.close()
        return None
        
    # Select Data Route
    print("Selecting data route...")
    try:
        route_input = page.locator('div[data-baseweb="select"]').first
        await route_input.click()
        await page.wait_for_timeout(500)
        await page.locator(f"li:has-text('{t_source}')").first.click()
    except Exception as e:
        print(f"Failed to select data route: {e}")
    
    # Click Fetch
    print("Clicking Fetch...")
    try:
        fetch_btn = page.locator("button:has-text('Fetch Target Metadata')").first
        await fetch_btn.click()
    except Exception as e:
        print(f"Failed to click fetch: {e}")
    
    print("Waiting for Fetch to finish...")
    try:
        # Wait for the next button to appear
        analyze_btn = page.locator("button:has-text('Analyze Telemetry')").first
        await analyze_btn.wait_for(state="visible", timeout=600000)
    except Exception as e:
        print(f"FAILED to fetch {t_name} data (timeout waiting for Analyze button): {e}")
        try:
            await browser.close()
        except Exception:
            pass
        return None
        
    # Multi-planet toggle
    if target_info["depth"] > 1:
        print("Toggling multi-planet...")
        try:
            toggle = page.locator("text=Multi-Planet Search Deep-Dive").first
            await toggle.click()
            await page.wait_for_timeout(500)
            
            await set_slider(page, "Max Planetary Scan Depth", target_info["depth"], 1, 5, 1)
            await set_slider(page, "Signal-to-Noise (SNR) Floor Cutoff", target_info["snr"], 3.0, 12.0, 0.1)
        except Exception as e:
            print(f"Failed toggling multi-planet: {e}")
            
    print("Clicking Analyze...")
    try:
        await analyze_btn.click()
    except Exception as e:
        print(f"Failed to click analyze: {e}")
    
    print("Waiting for Analysis...")
    try:
        await page.wait_for_selector("text=Diagnostic Summary Matrix", timeout=600000)
    except Exception as e:
        print(f"FAILED Analysis for {t_name} (timeout waiting for matrix): {e}")
        try:
            await browser.close()
        except Exception:
            pass
        return None

    await page.wait_for_timeout(3000)

    # Click Stability if available
    try:
        stability_btn = page.locator("button:has-text('Analyze System Stability')").first
        if await stability_btn.is_visible():
            print("Clicking Stability...")
            await stability_btn.click()
            await page.wait_for_selector("text=Survival Time", timeout=30000)
    except:
        pass
        
    dom_text = await page.locator("body").inner_text()
    exceptions = await page.locator("div[data-testid='stException']").all_inner_texts()
    if exceptions:
        print(f"EXCEPTIONS FOUND FOR {t_name}!")
        
    try:
        await browser.close()
    except Exception:
        pass
    
    return {
        "dom": dom_text,
        "exceptions": exceptions
    }

async def main():
    results = {}
    async with async_playwright() as p:
        for t in targets:
            res = await run_target(p, t)
            results[t["name"]] = res
            
            with open("qa_results.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
