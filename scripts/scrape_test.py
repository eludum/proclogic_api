import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.publicprocurement.be/publication-workspaces/5f1ebaba-bc31-4fc2-bb72-7878b3cc4219/documents")
        page.locator("tr:has-text('.xml')").get_by_role("button").nth(1).click()
        with page.expect_download() as download_info:
            page.get_by_role("button", name="Download latest version").click()
        
        download = download_info.value
        download_path = download.path()
        
        # Read the downloaded XML content
        with open(download_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        print(xml_content)

        context.close()
        browser.close()

run()