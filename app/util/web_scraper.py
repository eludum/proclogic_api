from playwright.sync_api import sync_playwright


def xml_from_procurement_site(publication_workspace_id: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(
            f"https://www.publicprocurement.be/publication-workspaces/{publication_workspace_id}/documents"
        )
        page.locator("tr:has-text('.xml')").get_by_role("button").nth(1).click()
        with page.expect_download() as download_info:
            page.get_by_role("button", name="Download latest version").click()

        download = download_info.value
        download_path = download.path()

        # Read the downloaded XML content
        with open(download_path, "r", encoding="utf-8") as f:
            xml_content = f.read()

        print(xml_content)

        context.close()
        browser.close()
