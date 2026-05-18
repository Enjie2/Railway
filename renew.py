import os
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ====================== 配置 ======================
ACCOUNTS = os.getenv("FG_ACCOUNTS", "").strip()          # 格式：邮箱-----密码\n邮箱2-----密码2
SERVER_IDS = [s.strip() for s in os.getenv("SERVER_IDS", "").split(",") if s.strip()]
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

PANEL_URL = "https://panel.freegamehost.xyz"
MAX_RETRIES = 3
HEADLESS = True

def send_telegram(message: str, screenshot_paths: list = None):
    if not (TG_BOT_TOKEN and TG_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        import requests
        requests.post(url, data=data, timeout=10)
        if screenshot_paths:
            for path in screenshot_paths:
                if Path(path).exists():
                    files = {"photo": open(path, "rb")}
                    requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data=data, files=files, timeout=10)
    except:
        pass

def main():
    if not ACCOUNTS or not SERVER_IDS:
        print("❌ 未配置 FG_ACCOUNTS 或 SERVER_IDS")
        send_telegram("❌ FreeGameHost 续期失败：未配置账号或服务器ID")
        return

    account_list = [line.strip() for line in ACCOUNTS.split("\n") if "-----" in line]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        for account_line in account_list:
            try:
                email, password = account_line.split("-----", 1)
                email = email.strip()
                password = password.strip()

                print(f"🔑 正在处理账号: {email}")

                # 登录
                page.goto(PANEL_URL + "/auth/login", wait_until="networkidle", timeout=60000)
                page.fill('input[type="email"]', email)
                page.fill('input[type="password"]', password)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle", timeout=30000)

                # 可能有 Cloudflare / Turnstile，等待一下
                time.sleep(5)

                success_count = 0
                screenshots = []

                for server_id in SERVER_IDS:
                    for retry in range(MAX_RETRIES):
                        try:
                            page.goto(f"{PANEL_URL}/server/{server_id}", wait_until="networkidle", timeout=60000)
                            time.sleep(4)

                            # 多 selector 适配 oyz8 风格，保证能点到“增加8小时”按钮
                            button_selectors = [
                                'button:has-text("增加8小时")',
                                'button:has-text("8小时")',
                                'button:has-text("Renew")',
                                'button:has-text("+8")',
                                'button:has-text("增加八小时")',
                                '[data-action="renew"]',
                                'button[title*="8小时"]'
                            ]

                            clicked = False
                            for selector in button_selectors:
                                if page.locator(selector).count() > 0:
                                    btn = page.locator(selector).first
                                    if btn.is_visible():
                                        btn.click()
                                        print(f"✅ 点击续期按钮成功: {server_id}")
                                        clicked = True
                                        break

                            if not clicked:
                                # 备用方案：任意包含“8小时”或“Renew”的按钮
                                page.get_by_text(re.compile(r"8小时|Renew|increase", re.I)).first.click()

                            time.sleep(3)
                            success_count += 1

                            # 截图
                            screenshot_path = f"screenshot_{server_id}.png"
                            page.screenshot(path=screenshot_path)
                            screenshots.append(screenshot_path)
                            break

                        except Exception as e:
                            print(f"⚠️ 第 {retry+1} 次尝试失败: {e}")
                            if retry == MAX_RETRIES - 1:
                                raise
                            time.sleep(5)

                # 通知
                msg = f"""✅ FreeGameHost 续期完成
账号: {email}
服务器: {", ".join(SERVER_IDS)}
成功: {success_count}/{len(SERVER_IDS)}
时间: {time.strftime("%Y-%m-%d %H:%M:%S")}"""
                send_telegram(msg, screenshots)

            except Exception as e:
                print(f"❌ 账号 {email} 处理失败: {e}")
                send_telegram(f"❌ FreeGameHost 账号 {email} 续期失败\n错误: {str(e)[:200]}")

        browser.close()

if __name__ == "__main__":
    main()