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
HEADLESS = True   # 本地测试可改 False

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

def close_ad_popup(page):
    print("🔍 尝试关闭广告弹窗...")
    selectors = ['button:has-text("Close")', 'button:has-text("×")', 'button:has-text("✕")', '[class*="close"] button']
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=4000):
                btn.click()
                print("✅ 已关闭广告弹窗")
                time.sleep(3)
                return True
        except:
            continue
    return False

def handle_cookie_consent(page):
    print("🔍 尝试点击 Cookie「同意」...")
    selectors = ['button:has-text("同意")', page.get_by_role("button", name=re.compile("同意", re.I))]
    for sel in selectors:
        try:
            btn = page.locator(sel).first if isinstance(sel, str) else sel
            if btn.is_visible(timeout=5000):
                btn.click()
                print("✅ 已点击「同意」")
                time.sleep(4)
                return True
        except:
            continue
    return False

def main():
    if not ACCOUNTS or not SERVER_IDS:
        send_telegram("❌ 未配置账号或服务器ID")
        return

    account_list = [line.strip() for line in ACCOUNTS.split("\n") if "-----" in line]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="zh-CN"
        )

        page = context.new_page()

        for account_line in account_list:
            email, password = account_line.split("-----", 1)
            email = email.strip()
            password = password.strip()

            print(f"🔑 正在处理账号: {email}")

            success = False
            for attempt in range(MAX_RETRIES):
                try:
                    print(f"   → 第 {attempt+1} 次尝试打开登录页...")
                    page.goto(f"{PANEL_URL}/auth/login", wait_until="domcontentloaded", timeout=120000)
                    time.sleep(6)

                    # 截图原始页面
                    page.screenshot(path=f"login_{email}_step1_raw.png")

                    # 处理弹窗
                    close_ad_popup(page)
                    handle_cookie_consent(page)

                    # 再等页面完全稳定
                    page.wait_for_load_state("networkidle", timeout=30000)
                    page.screenshot(path=f"login_{email}_step2_clean.png")

                    # 填充邮箱
                    email_selectors = ['input[type="email"]', 'input[name="email"]', 'input[placeholder*="Email" i]']
                    for sel in email_selectors:
                        try:
                            elem = page.locator(sel).first
                            if elem.is_visible(timeout=10000):
                                elem.fill(email)
                                break
                        except:
                            continue

                    # 填充密码 + 登录
                    page.fill('input[type="password"]', password)
                    page.click('button[type="submit"], button:has-text("Login"), button:has-text("Sign in"), button:has-text("登录")', timeout=20000)

                    page.wait_for_load_state("networkidle", timeout=60000)
                    time.sleep(random.uniform(5, 8))

                    print(f"✅ 账号 {email} 登录成功")
                    success = True
                    break

                except Exception as e:
                    print(f"   ⚠️ 第 {attempt+1} 次失败: {e}")
                    if attempt == MAX_RETRIES - 1:
                        raise
                    time.sleep(10)

            if not success:
                continue

            # ==================== 续期服务器 ====================
            success_count = 0
            screenshots = []

            for server_id in SERVER_IDS:
                for retry in range(MAX_RETRIES):
                    try:
                        page.goto(f"{PANEL_URL}/server/{server_id}", wait_until="domcontentloaded", timeout=60000)
                        time.sleep(6)

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
                                if btn.is_visible(timeout=8000):
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

        browser.close()

if __name__ == "__main__":
    main()
