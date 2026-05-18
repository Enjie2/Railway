import os
import time
import re
import random
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ====================== 配置 ======================
ACCOUNTS = os.getenv("FG_ACCOUNTS", "").strip()          # 邮箱-----密码   一行一个
SERVER_IDS = [s.strip() for s in os.getenv("SERVER_IDS", "").split(",") if s.strip()]
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

PANEL_URL = "https://panel.freegamehost.xyz"
MAX_RETRIES = 3
HEADLESS = True   # 本地测试时可改成 False

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
        send_telegram("❌ FreeGameHost 续期失败：未配置账号或服务器ID")
        return

    account_list = [line.strip() for line in ACCOUNTS.split("\n") if "-----" in line]

    with sync_playwright() as p:
        # 加强版隐身参数（取代 playwright-stealth）
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-client-side-phishing-detection",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            }
        )

        page = context.new_page()

        for account_line in account_list:
            try:
                email, password = account_line.split("-----", 1)
                email = email.strip()
                password = password.strip()

                print(f"🔑 正在处理账号: {email}")

                # ==================== 登录 ====================
                page.goto(f"{PANEL_URL}/auth/login", wait_until="networkidle", timeout=90000)
                time.sleep(8)

                # 处理 Ad Blocker 页面
                if any(text in page.content().lower() for text in ["ad blocker", "adblocker", "ad-block"]):
                    print("⚠️ 检测到 Ad Blocker 页面，尝试点击 Reload Page...")
                    page.get_by_text("Reload Page", timeout=10000).click()
                    page.wait_for_load_state("networkidle", timeout=60000)
                    time.sleep(10)

                # 截图登录页（调试用）
                page.screenshot(path=f"login_{email}.png")

                # 填充邮箱（多 selector）
                email_selectors = [
                    'input[type="email"]', 'input[name="email"]',
                    'input[placeholder*="Email" i]', 'input[placeholder*="邮箱" i]'
                ]
                for sel in email_selectors:
                    try:
                        elem = page.locator(sel).first
                        if elem.is_visible(timeout=8000):
                            elem.fill(email)
                            break
                    except:
                        continue

                # 密码
                page.fill('input[type="password"]', password)

                # 点击登录
                page.click('button[type="submit"], button:has-text("Login"), button:has-text("Sign in"), button:has-text("登录")', timeout=15000)
                page.wait_for_load_state("networkidle", timeout=60000)
                time.sleep(random.uniform(4, 7))

                print(f"✅ 账号 {email} 登录成功")

                # ==================== 续期服务器 ====================
                success_count = 0
                screenshots = []

                for server_id in SERVER_IDS:
                    for retry in range(MAX_RETRIES):
                        try:
                            page.goto(f"{PANEL_URL}/server/{server_id}", wait_until="networkidle", timeout=60000)
                            time.sleep(6)

                            # 增加8小时按钮（多 selector）
                            button_selectors = [
                                'button:has-text("增加8小时")',
                                'button:has-text("8小时")',
                                'button:has-text("Renew")',
                                'button:has-text("+8")',
                                page.get_by_text(re.compile(r"8小时|Renew|increase", re.I)).first
                            ]

                            clicked = False
                            for sel in button_selectors:
                                try:
                                    btn = page.locator(sel).first if isinstance(sel, str) else sel
                                    if btn.is_visible(timeout=5000):
                                        btn.click()
                                        print(f"✅ 已点击续期: {server_id}")
                                        clicked = True
                                        break
                                except:
                                    continue

                            if not clicked:
                                raise Exception("未找到续期按钮")

                            time.sleep(5)
                            success_count += 1

                            shot = f"screenshot_{server_id}.png"
                            page.screenshot(path=shot)
                            screenshots.append(shot)
                            break

                        except Exception as e:
                            print(f"⚠️ 服务器 {server_id} 第 {retry+1} 次失败: {e}")
                            if retry == MAX_RETRIES - 1:
                                raise
                            time.sleep(10)

                msg = f"""✅ FreeGameHost 续期完成
账号: {email}
服务器: {", ".join(SERVER_IDS)}
成功: {success_count}/{len(SERVER_IDS)}
时间: {time.strftime("%Y-%m-%d %H:%M:%S")}"""
                send_telegram(msg, screenshots)

            except Exception as e:
                print(f"❌ 账号 {email} 处理失败: {e}")
                send_telegram(f"❌ FreeGameHost 账号 {email} 续期失败\n错误: {str(e)[:300]}")
                if Path(f"login_{email}.png").exists():
                    send_telegram(f"📸 账号 {email} 登录页面截图", [f"login_{email}.png"])

        browser.close()

if __name__ == "__main__":
    main()
