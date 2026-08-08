import os
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("BROWSER_SMOKE_URL", "http://127.0.0.1:8000")
ARTIFACT_DIR = Path(os.environ.get("BROWSER_ARTIFACT_DIR", "artifacts"))


def assert_workspace_shell(page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    assert page.locator("#authOverlay").count() == 1
    assert page.locator("#workspaceModeSwitch").count() == 1
    assert page.locator("#modeChatButton").count() == 1
    assert page.locator("#modeAgentButton").count() == 1
    assert page.locator("#modelSelect").count() == 1
    assert page.locator("#composer").count() == 1
    assert page.locator("#messageInput").count() == 1
    assert page.locator("#sidebar").count() == 1


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        assert_workspace_shell(page)
        page.screenshot(
            path=str(ARTIFACT_DIR / "workspace-desktop.png"),
            full_page=True,
        )

        page.set_viewport_size({"width": 390, "height": 844})
        assert_workspace_shell(page)
        page.screenshot(
            path=str(ARTIFACT_DIR / "workspace-mobile.png"),
            full_page=True,
        )
        browser.close()


if __name__ == "__main__":
    main()
