from playwright.async_api import async_playwright


async def scrape_xml_from_procurement_site(publication_workspace_id: str) -> str:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(
            f"https://www.publicprocurement.be/publication-workspaces/{publication_workspace_id}/documents"
        )
        await page.locator("tr:has-text('.xml')").get_by_role("button").nth(1).click()
        async with page.expect_download() as download_info:
            await page.get_by_role("button", name="Download latest version").click()

        download = await download_info.value
        download_path = await download.path()

        # Read the downloaded XML content
        with open(download_path, "r", encoding="utf-8") as f:
            xml_content = f.read()

        await context.close()
        await browser.close()

        return xml_content
