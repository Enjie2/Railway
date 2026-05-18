import time
import os
import requests
import platform
from datetime import datetime
if "DISPLAY" not in os.environ:
    if platform.system().lower() == "linux":
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=False, size=(1920, 1080))
            display.start()
            os.environ["DISPLAY"] = display.new_display_var
        except:
            pass
from seleniumbase import SB

# ================= 配置区域 =================
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
ACCOUNTS = os.getenv("FG_ACCOUNTS", "")           # 邮箱-----密码 一行一个
SERVER_IDS = [s.strip() for s in os.getenv("SERVER_IDS", "").split(",") if s.strip()]

LOGIN_URL = "https://panel.freegamehost.xyz/auth/login"
PANEL_BASE = "https://panel.freegamehost.xyz"

def parse_accounts(raw: str):
    accounts = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "-----" not in line:
            continue
        parts = line.split("-----", 1)
        if len(parts) == 2:
            accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

class FreeGameHostRenewal:
    def __init__(self):
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.screenshot_dir = os.path.join(self.BASE_DIR, "artifacts")
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def mask_account(self, u):
        if "@" in u:
            local, domain = u.split("@", 1)
            return f"{local[:2]}***@{domain}"
        return u[:2] + "*" * (len(u) - 2) if len(u) > 2 else u

    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] [INFO] {msg}", flush=True)

    def shot(self, sb, name):
        path = os.path.join(self.screenshot_dir, name)
        sb.save_screenshot(path)
        return path

    def send_tg(self, icon, title, account_name, server_id, state_str, extra="", screenshot=None):
        if not TG_TOKEN or not TG_CHAT_ID:
            return
        msg = f"{icon} {title}\n\n账号: {account_name}\n服务器: {server_id}\n状态: {state_str}\n{extra}\n\nFreeGameHost Auto Renew"
        try:
            if screenshot and os.path.exists(screenshot):
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(screenshot, "rb") as f:
                    requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": msg}, files={"photo": f})
            else:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, data={"chat_id": TG_CHAT_ID, "text": msg})
        except Exception as e:
            self.log(f"TG发送失败: {e}")

    def close_popups(self, sb):
        self.log("🔍 关闭 Cookie/广告弹窗...")
        try:
            for _ in range(3):
                if sb.is_element_visible('button[aria-label*="close" i], button:has-text("×"), button:has-text("关闭")', timeout=8):
                    sb.click('button[aria-label*="close" i], button:has-text("×")')
                    self.log("✅ 已关闭弹窗")
                    time.sleep(3)
        except Exception as e:
            self.log(f"弹窗关闭异常: {e}")

    def run(self):
        self.log("🚀 开始执行 FreeGameHost 自动续期")
        accounts = parse_accounts(ACCOUNTS)
        if not accounts:
            self.log("❌ 未配置 FG_ACCOUNTS")
            return

        for idx, (email, password) in enumerate(accounts, 1):
            masked = self.mask_account(email)
            self.log(f"==== 账号 [{idx}] {masked} ====")

            with SB(uc=True, test=True, headed=False,
                    chromium_arg="--no-sandbox,--disable-dev-shm-usage,--disable-gpu") as sb:
                try:
                    # ==================== 登录 ====================
                    self.log("🌐 打开登录页面...")
                    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=12)
                    time.sleep(12)
                    self.shot(sb, f"login_{idx}_raw.png")

                    self.close_popups(sb)

                    self.log("⏳ 等待登录输入框...")
                    sb.wait_for_element_present('input', timeout=60)
                    self.shot(sb, f"login_{idx}_inputs.png")

                    self.log("✅ 填写邮箱和密码...")
                    sb.type('input:first-of-type', email)
                    time.sleep(2)
                    sb.wait_for_element_visible('input[type="password"]', timeout=30)
                    sb.type('input[type="password"]', password)

                    # ==================== 点击 LOGIN 按钮（最关键加强）===================
                    self.log("⏳ 等待 LOGIN 按钮出现...")
                    self.shot(sb, f"login_{idx}_before_click.png")   # 点击前截图

                    button_selectors = [
                        'button:has-text("LOGIN")',
                        'button[type="submit"]',
                        'button:has-text("Login")',
                        'button:has-text("Sign in")'
                    ]

                    clicked = False
                    for sel in button_selectors:
                        try:
                            if sb.is_element_visible(sel, timeout=25):
                                sb.click(sel)
                                self.log(f"✅ 已点击 LOGIN 按钮（使用 {sel}）")
                                clicked = True
                                break
                        except:
                            continue

                    if not clicked:
                        # JS 保底点击（最强兜底）
                        self.log("⚠️ 普通点击失败，尝试 JS 点击...")
                        sb.execute_script("document.querySelector('button').click();")
                        time.sleep(3)

                    time.sleep(12)

                    if "/auth/login" in sb.get_current_url():
                        self.log("❌ 登录失败（仍在登录页）")
                        self.send_tg("❌", "登录失败", masked, "N/A", "仍在登录页", screenshot=self.shot(sb, f"login_fail_{idx}.png"))
                        continue

                    self.log("✅ 登录成功")

                    # ==================== 续期服务器 ====================
                    success_count = 0
                    for server_id in SERVER_IDS:
                        try:
                            url = f"{PANEL_BASE}/server/{server_id}"
                            self.log(f"🌐 打开服务器页面: {server_id}")
                            sb.uc_open_with_reconnect(url, reconnect_time=8)
                            time.sleep(10)
                            self.close_popups(sb)
                            self.shot(sb, f"server_{server_id}_{idx}.png")

                            renew_clicked = False
                            for selector in [
                                'button:has-text("增加8小时")',
                                'button:has-text("8小时")',
                                'button:has-text("Renew")',
                                'button:has-text("+8")',
                                'button:has-text("RENEW SERVER")'
                            ]:
                                if sb.is_element_visible(selector, timeout=20):
                                    sb.click(selector)
                                    self.log(f"✅ 已点击续期按钮 → {server_id}")
                                    renew_clicked = True
                                    time.sleep(8)
                                    success_count += 1
                                    break

                            if not renew_clicked:
                                self.log(f"⚠️ 未找到续期按钮（可能 cooldown 中）→ {server_id}")
                                self.shot(sb, f"no_renew_btn_{server_id}_{idx}.png")

                        except Exception as e:
                            self.log(f"服务器 {server_id} 异常: {e}")
                            self.shot(sb, f"server_error_{server_id}_{idx}.png")

                    extra = f"成功续期 {success_count}/{len(SERVER_IDS)} 个服务器"
                    self.send_tg("✅", "续期完成", masked, ", ".join(SERVER_IDS), "已执行", extra, screenshot=self.shot(sb, f"final_{idx}.png"))

                except Exception as e:
                    self.log(f"❌ 账号处理异常: {e}")
                    self.send_tg("❌", "异常终止", masked, "N/A", "脚本异常", str(e)[:200], screenshot=self.shot(sb, f"error_{idx}.png"))

        self.log("✅ 所有账号处理完毕")

if __name__ == "__main__":
    FreeGameHostRenewal().run()
