"""Small always-on-top monitor for the USTB campus network allowance."""

from __future__ import annotations

import configparser
import os
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.ini"
DASHBOARD_URL = "https://zifuwu.ustb.edu.cn/Self/dashboard"


def read_config() -> tuple[str, str, int, int, int]:
    if not CONFIG_PATH.exists():
        raise RuntimeError("找不到 config.ini，请确认配置文件与程序放在同一目录。")
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_PATH, encoding="utf-8")
        username = config.get("account", "username").strip()
        password = config.get("account", "password").strip()
        interval = config.getint("widget", "refresh_seconds", fallback=60)
        x = config.getint("widget", "window_x", fallback=80)
        y = config.getint("widget", "window_y", fallback=80)
    except (configparser.Error, ValueError) as exc:
        raise RuntimeError(f"config.ini 配置格式有误：{exc}") from exc
    if not username or not password:
        raise RuntimeError("请在 config.ini 的 [account] 中填写 username 和 password。")
    if interval < 15:
        interval = 15
    return username, password, interval, x, y


class BrowserClient:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        try:
            from selenium import webdriver
            from selenium.common.exceptions import TimeoutException, WebDriverException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.edge.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise RuntimeError("缺少 Selenium 依赖，请先运行 install_dependencies.bat。") from exc

        # Keep driver downloads/caches beside the app, and disable Selenium Manager telemetry.
        os.environ["SE_CACHE_PATH"] = str(ROOT_DIR / ".selenium_cache")
        os.environ["SE_AVOID_STATS"] = "true"
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1400,1000")
        options.add_argument("--no-first-run")
        try:
            self.driver = webdriver.Edge(options=options)
            self.driver.set_page_load_timeout(30)
        except WebDriverException as exc:
            raise RuntimeError(
                "无法启动 Edge 自动化。请确认已安装 Microsoft Edge，且首次运行时可以下载匹配的驱动。\n"
                f"详情：{str(exc).splitlines()[0]}"
            ) from exc
        self.wait = WebDriverWait(self.driver, 20)
        self.By = By
        self.TimeoutException = TimeoutException

    @staticmethod
    def _is_login_page(driver) -> bool:
        return "/self/login" in driver.current_url.lower()

    def _visible_enabled(self, by, selector: str, description: str):
        def find_visible(driver):
            for element in driver.find_elements(by, selector):
                try:
                    if element.is_displayed() and element.is_enabled():
                        return element
                except Exception:
                    continue
            return False

        try:
            return self.wait.until(find_visible)
        except self.TimeoutException as exc:
            raise RuntimeError(f"登录页没有可操作的{description}。") from exc

    def _account_input(self):
        """Prefer the visible account field; login pages sometimes contain hidden duplicates."""
        def find_account(driver):
            candidates = driver.find_elements(
                self.By.CSS_SELECTOR,
                "input:not([type]), input[type='text'], input[type='email'], input[type='tel']",
            )
            usable = []
            for element in candidates:
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    if element.get_attribute("readonly") is not None:
                        continue
                    rect = element.rect
                    if rect.get("width", 0) < 2 or rect.get("height", 0) < 2:
                        continue
                    hints = " ".join(
                        (element.get_attribute(name) or "")
                        for name in ("id", "name", "placeholder", "autocomplete")
                    ).lower()
                    score = 2 if any(word in hints for word in ("account", "user", "login", "账号")) else 0
                    usable.append((score, element))
                except Exception:
                    continue
            if usable:
                usable.sort(key=lambda item: item[0], reverse=True)
                return usable[0][1]
            return False

        try:
            return self.wait.until(find_account)
        except self.TimeoutException as exc:
            raise RuntimeError("登录页没有可操作的账号输入框（已检查当前页可见输入控件）。") from exc

    def _masked_page_text(self) -> str:
        try:
            text = self.driver.find_element(self.By.TAG_NAME, "body").text
        except Exception:
            return ""
        text = " ".join(text.split())
        return text.replace(self.username, "[账号已隐藏]").replace(self.password, "[密码已隐藏]")[:240]

    def _login(self) -> None:
        account = self._account_input()
        password = self._visible_enabled(
            self.By.CSS_SELECTOR, "input[type='password']", "密码输入框"
        )
        for description, element, value in (
            ("账号", account, self.username),
            ("密码", password, self.password),
        ):
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", element
                )
                element.clear()
                element.send_keys(value)
                if element.get_attribute("value") != value:
                    raise RuntimeError("输入框没有保留填写内容。")
            except Exception as exc:
                raise RuntimeError(
                    f"填写{description}输入框时失败（{type(exc).__name__}）。"
                ) from exc

        button = None
        candidates = self.driver.find_elements(
            self.By.CSS_SELECTOR, "button, input[type='submit'], input[type='button']"
        )
        for candidate in candidates:
            try:
                if candidate.is_displayed() and candidate.is_enabled():
                    label = " ".join((candidate.text or candidate.get_attribute("value") or "").split())
                    if "登" in label:
                        button = candidate
                        break
            except Exception:
                continue
        if button is None:
            raise RuntimeError("登录页没有可操作的“登录”按钮。")
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
            button.click()
        except Exception as exc:
            raise RuntimeError(f"点击登录按钮时失败（{type(exc).__name__}）。") from exc

        try:
            self.wait.until(
                lambda driver: not self._is_login_page(driver)
                or "免费流量使用情况"
                in driver.find_element(self.By.TAG_NAME, "body").text
            )
        except self.TimeoutException as exc:
            feedback = self._masked_page_text() or "页面没有显示可读提示。"
            raise RuntimeError(f"浏览器自动登录后仍停留在登录页。页面提示：{feedback}") from exc

    def get_allowance(self) -> dict[str, float]:
        self.driver.get(DASHBOARD_URL)
        if self._is_login_page(self.driver):
            self._login()
            self.driver.get(DASHBOARD_URL)
        if self._is_login_page(self.driver):
            feedback = self._masked_page_text() or "网站未显示可读提示。"
            raise RuntimeError(f"登录未成功，仪表板仍跳回登录页。页面提示：{feedback}")

        try:
            text = self.driver.find_element(self.By.TAG_NAME, "body").text
        except Exception as exc:
            raise RuntimeError("已打开仪表板，但无法读取页面内容。") from exc
        text = re.sub(r"\s+", " ", text)
        if "免费流量使用情况" not in text:
            raise RuntimeError("已打开仪表板，但没有找到流量余额区域。页面结构可能已更新。")

        values: dict[str, float] = {}
        for key, label in (("total", "总量"), ("used", "已用"), ("remaining", "剩余")):
            match = re.search(rf"{label}\s*[:：]?\s*([\d,]+(?:\.\d+)?)\s*M?", text, re.I)
            if not match:
                raise RuntimeError(f"仪表板中暂时找不到“{label}”数值。")
            values[key] = float(match.group(1).replace(",", ""))
        if values["total"] <= 0:
            raise RuntimeError("仪表板返回了无效的流量总量。")
        return values

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass


def format_mb(value: float) -> str:
    return f"{int(value)}" if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


class TrafficWidget:
    def __init__(self, username: str, password: str, interval: int, x: int, y: int) -> None:
        self.interval = interval
        self.username = username
        self.password = password
        self.client: BrowserClient | None = None
        self.messages: queue.Queue = queue.Queue()
        self.refresh_event = threading.Event()
        self.stop_event = threading.Event()
        self.fetching = False
        self.last_error: str | None = None

        self.root = tk.Tk()
        self.root.title("校园网流量")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"430x158+{x}+{y}")
        self.root.configure(bg="#f7f8fa")
        try:
            self.root.attributes("-alpha", 0.98)
        except tk.TclError:
            pass

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.bind("<Button-3>", self._show_menu)
        self.root.after(150, self._drain_messages)
        self.root.after(500, self.refresh)
        threading.Thread(target=self._worker, daemon=True).start()

    def _build_ui(self) -> None:
        self.card = tk.Frame(self.root, bg="white", highlightbackground="#d9dde3", highlightthickness=1)
        self.card.pack(fill="both", expand=True, padx=1, pady=1)

        header = tk.Frame(self.card, bg="white")
        header.pack(fill="x", padx=16, pady=(10, 2))
        self.title_label = tk.Label(header, text="免费流量使用情况", bg="white", fg="#202b3b", anchor="w", font=("Microsoft YaHei UI", 10))
        self.title_label.pack(side="left")
        self.status = tk.Label(header, text="正在连接…", bg="white", fg="#8a93a0", anchor="e", font=("Microsoft YaHei UI", 8))
        self.status.pack(side="right")

        self.progress = tk.Canvas(self.card, height=30, bg="white", highlightthickness=0)
        self.progress.pack(fill="x", padx=15, pady=(4, 5))
        self.progress.bind("<Configure>", lambda _event: self._draw_progress())

        row = tk.Frame(self.card, bg="white")
        row.pack(fill="x", padx=17, pady=(0, 5))
        self.total_label = tk.Label(row, text="总量：-- M", bg="white", fg="#3981cf", anchor="w", font=("Microsoft YaHei UI", 9))
        self.total_label.pack(side="left")
        self.used_label = tk.Label(row, text="已用：-- M", bg="white", fg="#f5a33c", anchor="center", font=("Microsoft YaHei UI", 9))
        self.used_label.pack(side="left", expand=True)
        self.remaining_label = tk.Label(row, text="剩余：-- M", bg="white", fg="#4bae58", anchor="e", font=("Microsoft YaHei UI", 9))
        self.remaining_label.pack(side="right")

        footer = tk.Frame(self.card, bg="white")
        footer.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(footer, text="右键菜单可刷新或退出 · 拖动窗口可调整位置", bg="white", fg="#9aa2ad", anchor="w", font=("Microsoft YaHei UI", 8)).pack(side="left")
        self._drag_start = None
        self._drag_moved = False
        for widget in (self.card, header, self.title_label, self.status, self.progress, row, self.total_label, self.used_label, self.remaining_label, footer):
            widget.bind("<ButtonPress-1>", self._drag_begin)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)
            widget.bind("<Button-3>", self._show_menu)
        self._values: dict[str, float] | None = None

    def _drag_begin(self, event) -> None:
        self._drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        self._drag_moved = False

    def _drag_move(self, event) -> None:
        if self._drag_start:
            x = event.x_root - self._drag_start[0]
            y = event.y_root - self._drag_start[1]
            self.root.geometry(f"+{x}+{y}")
            self._drag_moved = True

    def _drag_end(self, _event) -> None:
        self._drag_start = None
        if not self._drag_moved:
            return
        self._drag_moved = False
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH, encoding="utf-8")
        if not config.has_section("widget"):
            config.add_section("widget")
        config.set("widget", "window_x", str(self.root.winfo_x()))
        config.set("widget", "window_y", str(self.root.winfo_y()))
        with CONFIG_PATH.open("w", encoding="utf-8") as stream:
            config.write(stream)

    def _show_menu(self, event) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="立即刷新", command=self.refresh)
        menu.add_command(label="查看最近错误", command=self.show_error)
        menu.add_command(label="退出", command=self.close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_error(self) -> None:
        if self.last_error:
            messagebox.showerror("校园网流量更新失败", self.last_error, parent=self.root)
        else:
            messagebox.showinfo("校园网流量小窗", "目前没有记录到错误。", parent=self.root)

    def refresh(self) -> None:
        if self.fetching:
            return
        self.fetching = True
        self.status.configure(text="正在刷新…", fg="#8a93a0")
        self.refresh_event.set()

    def _worker(self) -> None:
        try:
            while not self.stop_event.is_set():
                self.refresh_event.wait()
                self.refresh_event.clear()
                if self.stop_event.is_set():
                    break
                try:
                    if self.client is None:
                        self.client = BrowserClient(self.username, self.password)
                    values = self.client.get_allowance()
                    self.messages.put(("ok", values))
                except Exception as exc:  # Keep the window alive and show a concise error.
                    self.messages.put(("error", f"{type(exc).__name__}: {exc}"))
                self.stop_event.wait(self.interval)
                if not self.stop_event.is_set():
                    self.refresh_event.set()
        finally:
            if self.client is not None:
                self.client.close()

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                self.fetching = False
                if kind == "ok":
                    self._values = payload
                    self.total_label.configure(text=f"总量：{format_mb(payload['total'])} M")
                    self.used_label.configure(text=f"已用：{format_mb(payload['used'])} M")
                    self.remaining_label.configure(text=f"剩余：{format_mb(payload['remaining'])} M")
                    self.status.configure(text="已更新", fg="#4b9b59")
                    self.last_error = None
                    self._draw_progress()
                else:
                    self.last_error = payload
                    self.status.configure(text="更新失败（右键查看）", fg="#d36b55")
        except queue.Empty:
            pass
        if not self.stop_event.is_set():
            self.root.after(200, self._drain_messages)

    def _draw_progress(self) -> None:
        canvas = self.progress
        canvas.delete("all")
        width = max(1, canvas.winfo_width() - 2)
        height = max(1, canvas.winfo_height() - 2)
        radius = 5
        if not self._values:
            canvas.create_rectangle(1, 1, width, height, fill="#e9edf2", outline="", width=0)
            return
        ratio = max(0.0, min(1.0, self._values["used"] / self._values["total"]))
        split = max(radius, min(width - radius, int(width * ratio)))
        canvas.create_rectangle(1, 1, split, height, fill="#f2aa4b", outline="", width=0)
        canvas.create_rectangle(split, 1, width, height, fill="#5bb45e", outline="", width=0)

    def close(self) -> None:
        self.stop_event.set()
        self.refresh_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    try:
        username, password, interval, x, y = read_config()
        TrafficWidget(username, password, interval, x, y).run()
    except Exception as exc:
        # A native dialog is preferable to silently closing when configuration is invalid.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("校园网流量小窗", str(exc))
        root.destroy()


if __name__ == "__main__":
    main()
