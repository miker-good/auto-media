"""
头条号登录脚本 — 手动登录一次，保存 Cookie 供后续自动发布使用。

用法：
    python login_toutiao.py

会在当前目录生成 toutiao_cookies.json
"""
import json
from DrissionPage import ChromiumPage

COOKIE_FILE = "toutiao_cookies.json"

def main():
    page = ChromiumPage()
    page.get("https://mp.toutiao.com")

    print("=" * 50)
    print("浏览器已打开头条号后台")
    print("请手动扫码/手机号登录")
    print("登录成功后，回到终端按 Enter 键继续...")
    print("=" * 50)
    input()

    # 保存所有 cookie
    cookies = page.cookies()
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)

    print(f"Cookie 已保存到 {COOKIE_FILE}")
    page.quit()

if __name__ == "__main__":
    main()
