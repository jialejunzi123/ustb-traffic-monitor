# 校园网流量桌面小窗

Windows 桌面悬浮窗，自动登录北科大用户自服务系统，显示免费流量总量、已用量和剩余量。默认每 60 秒刷新，可拖动位置；右键可立即刷新或退出。

## 启动

1. 确认电脑已安装 Python 3.10 或更高版本（Windows 版，包含 Tkinter）和 Microsoft Edge。
2. 将 `config.example.ini` 复制为 `config.ini`，在其中填写校园网账号和密码。
3. 首次运行先双击 `install_dependencies.bat`，安装 Selenium。
4. 双击 `start_widget.bat`。
5. 如果无法连接自服务系统，请确认当前网络可以访问该网站；校外可能需要连接学校 VPN。

Selenium 使用本机 Edge 的无头模式自动完成登录和读取。首次启动会自动准备匹配的 Edge WebDriver；驱动缓存保存在程序目录的 `.selenium_cache` 中。

## 配置

`config.ini` 中可设置：

- `[account] username`：校园网账号
- `[account] password`：校园网密码
- `[widget] refresh_seconds`：刷新间隔，最短 15 秒
- `[widget] window_x` / `window_y`：初始窗口位置；拖动窗口后会自动更新

`config.ini` 中的密码以明文保存在本机。请勿把它发给他人或上传到网盘、代码仓库；该文件已由 `.gitignore` 排除。仓库只提供不含真实凭据的 `config.example.ini`。需要换账号时编辑本机的 `config.ini`。

## 限制

登录表单和流量字段按当前自服务系统页面结构自动识别。如果学校更新登录页或仪表板结构，小窗会保留并显示错误状态；届时需要更新解析规则。浏览器自动化依赖 Edge 和驱动可用；首次准备驱动需要网络访问 Selenium Manager 使用的 Edge 驱动服务。

## 许可证

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
