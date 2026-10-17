# 2.0.1：网页界面公开版

应用界面改为 HTML、CSS、JavaScript，由 pywebview 和 Windows WebView2 显示在独立桌面窗口中。Python 继续处理校园认证、DPAPI 加密、开机任务及浏览器清理。

- `webui/index.html`：页面结构、登录表单、连接状态、设置和运行记录。
- `webui/style.css`：布局、控件样式和窄窗口适配。
- `webui/motion.css`：DeepSeek Harness 提供的独立动效组件，由 Codex 集成。
- `webui/app.js`：页面交互、输入检查、状态刷新和调用本机桥接。
- `web_ui.py`：页面资源装配、状态管理、有限的本机功能桥接。

页面全部使用随程序附带的资源，无需外部字体、脚本或网站。未登录校园网时仍能打开。公开版不内置校园网服务器，通过 --set-portal 参数保存到本机 portal.json，具体步骤见 README。公开版使用独立的通用数据目录，不改动原本机专用版配置。密码不会回传到网页；密码框留空会保留同一账号原密码，输入新密码则替换。

需要 Windows 10/11 和 Microsoft Edge WebView2 Runtime。本机已有此运行时；其他电脑如未安装，应从微软官方下载。日常使用仍运行 `CampusAutoLogin.exe`，无需额外安装 Python。

开机任务继续在后台工作，约 10 分钟的开机网络监测逻辑保持。账号、密码及本机配置不随源码分享。
