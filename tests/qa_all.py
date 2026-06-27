import sys
import asyncio
import os
import json
from playwright.async_api import async_playwright

TEST_CASES = [
    {"target": "TRAPPIST-1", "source": "TESS (via Lightkurve)", "depth": 5, "snr": 5.0},
    {"target": "Kepler-11", "source": "Kepler (via Lightkurve)", "depth": 6, "snr": 6.0},
    {"target": "WASP-12 b", "source": "Kepler (via Lightkurve)", "depth": 1, "snr": 10.0},
    {"target": "K2-138", "source": "Kepler (via Lightkurve)", "depth": 5, "snr": 5.5},
    {"target": "Kepler-20", "source": "Kepler (via Lightkurve)", "depth": 5, "snr": 4.5},
    {"target": "AU Mic", "source": "TESS (via Lightkurve)", "depth": 2, "snr": 6.0},
    {"target": "HD 80606 b", "source": "TESS (via Lightkurve)", "depth": 1, "snr": 7.0},
    {"target": "TOI-700", "source": "TESS (via Lightkurve)", "depth": 3, "snr": 4.8},
    {"target": "Kepler-4 d", "source": "Kepler (via Lightkurve)", "depth": 1, "snr": 6.5},
    {"target": "Kepler-90", "source": "Kepler (via Lightkurve)", "depth": 7, "snr": 5.0},
]

async def wait_for_streamlit(page):
    await page.wait_for_timeout(2000)
    for _ in range(30):
        running = await page.locator(".stApp[data-test-script-state='running']").count()
        if running == 0:
            break
        await page.wait_for_timeout(1000)

async def set_slider(page, label, target_val, min_val, step):
    slider = page.locator(".stSlider").filter(has_text=label).locator("div[role='slider']")
    await slider.focus()
    await page.keyboard.press("Home")
    await wait_for_streamlit(page)
    steps = int(round((target_val - min_val) / step))
    for _ in range(steps):
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(50)
    await wait_for_streamlit(page)

async def run_all_cases():
    os.makedirs("outputs/ui_tests", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto("http://localhost:8501")
        await wait_for_streamlit(page)
        
        # Click Detective (only need to do this once if state persists, but better to refresh to be safe)
        for idx, case in enumerate(TEST_CASES):
            # Refresh page to start fresh
            await page.goto("http://localhost:8501")
            await wait_for_streamlit(page)
            
            await page.locator("button", has_text="Detective").click()
            await wait_for_streamlit(page)
            
            print(f"Running Case {idx + 1}: {case['target']}")
            
            target_input = page.locator("input[type='text']").first
            await target_input.fill(case['target'])
            await target_input.press("Enter")
            await wait_for_streamlit(page)
            
            route_select = page.locator("div[data-baseweb='select']").first
            await route_select.click()
            await page.locator("li[role='option']").filter(has_text=case['source']).first.click()
            await wait_for_streamlit(page)
            
            if case['depth'] > 1:
                toggle = page.locator("label").filter(has_text="Multi-Planet Search Deep-Dive")
                is_checked = await toggle.locator("input").is_checked()
                if not is_checked:
                    await toggle.click()
                    await wait_for_streamlit(page)
                
                await set_slider(page, "Max Planetary Scan Depth", case['depth'], 1, 1)
                await set_slider(page, "Signal-to-Noise", case['snr'], 3.0, 0.1)
            else:
                toggle = page.locator("label").filter(has_text="Multi-Planet Search Deep-Dive")
                if await toggle.count() > 0:
                    is_checked = await toggle.locator("input").is_checked()
                    if is_checked:
                        await toggle.click()
                        await wait_for_streamlit(page)
            
            fetch_btn = page.locator("button", has_text="Fetch Target Metadata")
            await fetch_btn.click()
            
            # Wait for data fetch
            await page.wait_for_timeout(15000)
            await wait_for_streamlit(page)
            
            analyze_btn = page.locator("button", has_text="Analyze Telemetry & Verify Harmonics")
            if await analyze_btn.count() > 0:
                await analyze_btn.click()
                await page.wait_for_timeout(10000)
                await wait_for_streamlit(page)
                await page.wait_for_timeout(5000) # Give extra time for plots
            else:
                print(f"Analyze button not found for {case['target']}")
            
            expanders = await page.locator("div[data-testid='stExpander'] summary").all()
            for exp in expanders:
                await exp.click()
                await page.wait_for_timeout(500)
                
            await wait_for_streamlit(page)
            
            out_prefix = f"case_{idx+1}_{case['target'].replace(' ', '_')}"
            await page.screenshot(path=f"outputs/ui_tests/{out_prefix}.png", full_page=True)
            dom = await page.locator("body").inner_text()
            with open(f"outputs/ui_tests/{out_prefix}_dom.txt", "w", encoding="utf-8") as f:
                f.write(dom)
                
            exceptions = await page.locator("div[data-testid='stException']").all_inner_texts()
            if exceptions:
                print(f"EXCEPTIONS FOUND in {case['target']}: {exceptions[0][:200]}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_all_cases())
