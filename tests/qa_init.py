import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    os.makedirs("outputs/ui_tests", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto("http://localhost:8501")
        await page.wait_for_selector(".stApp")
        await page.wait_for_timeout(3000)
        
        await page.screenshot(path="outputs/ui_tests/initial_screenshot.png", full_page=True)
        body_text = await page.locator("body").inner_text()
        with open("outputs/ui_tests/initial_dom.txt", "w", encoding="utf-8") as f:
            f.write(body_text)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
