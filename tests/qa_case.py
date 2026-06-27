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
    # wait until there's no spinner or 'running' class
    while True:
        running = await page.locator(".stApp[data-test-script-state='running']").count()
        if running == 0:
            break
        await page.wait_for_timeout(1000)

async def set_slider(page, label, target_val, min_val, step):
    # Find slider
    slider = page.locator(".stSlider").filter(has_text=label).locator("div[role='slider']")
    await slider.focus()
    await page.keyboard.press("Home") # go to min
    await wait_for_streamlit(page)
    
    steps = int(round((target_val - min_val) / step))
    for _ in range(steps):
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(100) # Give it a tiny bit to process
    await wait_for_streamlit(page)

async def run_case(case_idx):
    case = TEST_CASES[case_idx]
    print(f"Running Case {case_idx + 1}: {case['target']}")
    
    os.makedirs("outputs/ui_tests", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto("http://localhost:8501")
        await wait_for_streamlit(page)
        
        # Click Detective
        await page.locator("button", has_text="Detective").click()
        await wait_for_streamlit(page)
        
        # Set Target Search
        # Streamlit text input doesn't always have the label directly associated in a way playwright likes, 
        # but it has a placeholder
        target_input = page.locator("input[type='text']").first
        # We need to clear it and type
        await target_input.fill(case['target'])
        await target_input.press("Enter")
        await wait_for_streamlit(page)
        
        # Set Route
        route_select = page.locator("div[data-baseweb='select']").first
        await route_select.click()
        # Find the dropdown list item
        await page.locator("li[role='option']").filter(has_text=case['source']).first.click()
        await wait_for_streamlit(page)
        
        # Toggle Multi-Planet if depth > 1
        if case['depth'] > 1:
            toggle = page.locator("label").filter(has_text="Multi-Planet Search Deep-Dive")
            # click if not already checked
            is_checked = await toggle.locator("input").is_checked()
            if not is_checked:
                await toggle.click()
                await wait_for_streamlit(page)
            
            # Set sliders
            # Depth: min=1, step=1
            await set_slider(page, "Max Planetary Scan Depth", case['depth'], 1, 1)
            # SNR: min=3.0, step=0.1
            await set_slider(page, "Signal-to-Noise", case['snr'], 3.0, 0.1)
        else:
            # depth == 1, make sure multi-planet is off
            toggle = page.locator("label").filter(has_text="Multi-Planet Search Deep-Dive")
            if await toggle.count() > 0:
                is_checked = await toggle.locator("input").is_checked()
                if is_checked:
                    await toggle.click()
                    await wait_for_streamlit(page)
        
        # Click Fetch Target Metadata
        fetch_btn = page.locator("button", has_text="Fetch Target Metadata")
        await fetch_btn.click()
        
        # This might take a while, wait for the status to complete or "Target Discovery Confirmation" to appear
        await page.wait_for_timeout(5000)
        await wait_for_streamlit(page)
        
        # Click Analyze Telemetry
        analyze_btn = page.locator("button", has_text="Analyze Telemetry & Verify Harmonics")
        if await analyze_btn.count() > 0:
            await analyze_btn.click()
            await page.wait_for_timeout(5000)
            await wait_for_streamlit(page)
            # Wait for Core Telemetry or Error
            await page.wait_for_timeout(5000)
        else:
            print("Analyze button not found! Maybe fetch failed.")
        
        # Open expanders if any (e.g. "Candidate 1", etc.)
        expanders = await page.locator("div[data-testid='stExpander'] summary").all()
        for exp in expanders:
            await exp.click()
            await page.wait_for_timeout(500)
            
        await wait_for_streamlit(page)
        
        # Dump output
        out_prefix = f"case_{case_idx+1}_{case['target'].replace(' ', '_')}"
        await page.screenshot(path=f"outputs/ui_tests/{out_prefix}.png", full_page=True)
        dom = await page.locator("body").inner_text()
        with open(f"outputs/ui_tests/{out_prefix}_dom.txt", "w", encoding="utf-8") as f:
            f.write(dom)
            
        # Check for exceptions
        exceptions = await page.locator("div[data-testid='stException']").all_inner_texts()
        if exceptions:
            print(f"EXCEPTIONS FOUND in {case['target']}:")
            for e in exceptions:
                print(e[:200])
        else:
            print(f"Case {case_idx + 1} completed with no exceptions.")
            
        await browser.close()

if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    asyncio.run(run_case(idx))
