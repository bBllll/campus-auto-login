# 校园网自动连接 · Campus Auto Login 2.0.1

Windows 桌面校园网助手。界面由 HTML、CSS、JavaScript 编写，使用系统 WebView2 显示；Python 负责校园网认证、Windows 密码加密、开机后台任务和日志。

## 使用

1. 先按下文配置你自己的校园网登录地址。公开源码不内置任何学校内网地址。
2. 将 CampusAutoLogin.exe 放在固定文件夹，双击打开。
3. 先连接校园 Wi-Fi 或网线，填写校园网账号、密码，选择实际运营商。
4. 开启“开机自动连接”，点击“保存并连接”。以后在登录 Windows 后后台运行。
5. 已保存密码不会回传到网页；同一账号的密码框留空会保留原密码，输入新密码则替换。修改账号时需要填写对应密码。

公开版使用独立的通用应用目录，首次使用需要配置地址与账号；原本机专用版的配置不受影响。页面资源全部内置，不依赖外部网站、字体或脚本。界面有网络连接、偏好设置和运行记录三个页面，动效可单独关闭。

## 配置校园网地址

公开版没有默认校园网服务器。将下列示例替换为学校实际的登录页地址，从源码运行时执行：

```powershell
python campus_auto_login.py --set-portal "http://portal.example.com/"
python campus_auto_login.py
```

示例域名仅作格式说明，不能用于实际认证。打包后可使用 CampusAutoLogin.exe 的同名 --set-portal 参数配置。

地址只保存到当前用户的 `%LOCALAPPDATA%\CampusAutoLogin\portal.json`，不会提交到仓库。重新打开程序后生效；支持标准 HTTP 80 和 HTTPS 443 端口，不接受在 URL 中嵌入用户名密码。尚未配置地址时，连接操作会提示配置，不会填写或提交密码。

## 开机与网络

开机任务继续监测网络变化约 10 分钟，而非首次在线即退出。每次任务最多提交一次认证；手动与自动认证共用会话内的提交锁。检测到校园认证在线但外网探测未通过时，会分别显示状态，避免反复提交密码。此功能不提供全天候断线重连。

程序操作配置的学校原登录页面，填写账号时限制在该服务器主机内。出现验证码时需手动登录。已适配部分 Dr.COM 表单及运营商控件，不承诺兼容所有学校的定制页面。

## 隐私与本机配置

账号密码通过 Windows DPAPI 加密保存，绑定当前 Windows 用户；同一用户下的其他程序仍可能解密，不能抵御已控制该用户会话的软件。界面只接收账号、运营商及“密码已保存”状态，不接收原密码。

公开版数据目录是当前用户的 `%LOCALAPPDATA%\CampusAutoLogin\`，包含本地地址配置、加密账号、日志和界面偏好，均不随源码分享。运行记录不包含账号密码或原始网页内容。开机项属于当前用户，不需要管理员权限。

网页仅加载程序内置的文档，禁止导航到外部网页，不开放 HTTP 账号接口。真实校园认证在单独的临时浏览器中执行，不复用日常浏览器配置。

如移动了程序，在新位置打开，保持开机连接开启，再保存一次设置。清除本机配置会删除加密账号并关闭开机项。

## 环境与源码

需要 Windows 10/11、Microsoft Edge WebView2 Runtime 和 Edge/Chrome。当前电脑已有 WebView2；其他电脑如缺少，请从[微软官方下载](https://developer.microsoft.com/microsoft-edge/webview2/)安装。

从源码运行需要 Python 3.11–3.14：

```powershell
python -m pip install -r requirements.txt
python campus_auto_login.py
```

开机后台任务使用 --auto。从源码配置自启时，需保持解释器和源码路径不变。

## 测试与打包

```powershell
python -m unittest discover -s tests -v
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean packaging/CampusAutoLogin.spec
```

生成 dist/CampusAutoLogin.exe，无需在目标电脑额外安装 Python。测试使用虚构账号、临时文件和模拟网页，不提交真实校园网认证。

代码分工和迁移说明见 [WEB-UI.md](WEB-UI.md)，开机时序修复说明见 [STARTUP-FIX.md](STARTUP-FIX.md)。账号、密码、本机配置与运行日志不随源码分享。
