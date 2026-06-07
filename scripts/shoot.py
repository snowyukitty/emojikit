"""Headless screenshots of the emojikit studio UI (landing -> upload -> animate)."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8000"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1180, "height": 920}, device_scale_factor=2)
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_timeout(700)
    pg.screenshot(path="shot_landing.png")
    print("landing shot")

    pg.set_input_files("#file", "assets/fox.png")
    pg.wait_for_selector(".dz-stage:not([hidden])", timeout=90000)
    pg.wait_for_timeout(1200)
    pg.screenshot(path="shot_uploaded.png")
    print("uploaded shot")

    pg.click('.preset[data-name="celebrate"]')
    pg.wait_for_selector("#previewStage:not([hidden])", timeout=120000)
    pg.wait_for_timeout(1800)
    pg.screenshot(path="shot_result.png", full_page=True)
    print("result shot")
    b.close()
