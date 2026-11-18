# MJH-editor V2.5.4

梦江湖装备、武学与人物编辑器，适用于带 Microsoft Edge WebView2 的 64 位 Windows。

## 安装和升级

**[下载联网安装器](https://github.com/zeroXlight/MJH-editor-downloads/releases/download/online-setup/MJH-editor-OnlineSetup.exe)**

`MJH-editor-OnlineSetup.exe` 可以长期保留。每次运行时，它会从 GitHub 检查最新正式版、下载并校验对应安装包，再打开安装向导。

需要安装指定版本时，运行该版本发布页中的 `MJH-editor-Setup.exe`。两种入口都可以在安装向导选择目录，并按需安装手游模型与立绘、当前版本源码。

试装本地构建时，可将同版本的可选 ZIP 放在安装器旁边，勾选后由安装器校验并从本地解包。

编辑器顶部工具栏的「更新与资源」可以检查新版、选择提醒或自动更新，并下载当前版本源码。开启自动更新后，安装包在后台下载和校验，正常退出编辑器后才启动安装。补装可选组件时，重新运行当前版本安装器并沿用原安装目录。

下载会显示百分比和已下载大小。编辑器无法启动时，从 Windows 开始菜单打开「MJH-editor 更新与修复」，可以检查新版、下载并安装，或修复当前最新版。V2.5.1 和 V2.5.2 遇到启动故障时，可直接运行公开发布页的完整安装包。

从 V2.5.3 起，安装器会保留一份安装包作为差分基线。匹配发布清单中的基线时优先下载更小的差分包，再重建并验证完整安装包。基线缺失或差分失败时会下载完整安装包。

## 从源码构建

使用 Windows x64、Python 3.14、Node.js 和支持 ZIP 下载及解包的 Inno Setup 6.7.4。进入 `src`，运行 `python -m pip install -r requirements.txt`。如修改过界面，在 `src/desktop_ui` 运行 `npm ci` 和 `npm run build`，再回到 `src` 运行 `python desktop_app.py` 或 `python -m PyInstaller desktop.spec`。开发时可将解压后的 `mobile_assets` 放在项目根目录。

## 发布新版本

完整的源码提交、版本发布、差分包验证和个人分支流程见 [发布文档](RELEASING.md)。发布用的源码 ZIP 与目标分支的提交逐文件校验后，才会推送标签和上传附件。

更新 `src/edition.py` 中的版本号，并重建前端。使用项目已有的更新签名密钥运行 `build_release.py`，提供资源目录、`ISCC.exe` 和简体中文语言文件。密钥存放在开发工作环境的 `%LOCALAPPDATA%/MJH-editor-release/ed25519.key`，发布脚本也可通过 `--key` 指定安全存放的原密钥。

将 `release-assets` 中的 `MJH-editor-OnlineSetup.exe`、`MJH-editor-Setup.exe`、`MJH-editor-MobileAssets.zip`、`MJH-editor-Source.zip` 和 `update.json` 一同上传至对应版本 Release。先上传齐全，再发布为最新版。联网安装器和编辑器通过内置公钥验证更新清单。

为上一版生成差分包时，追加 `--previous-release <上一版的 release-assets 路径>`。参数可重复指定，以覆盖多个旧版。若脚本生成 `MJH-editor-From-*.bsdiff`，把它与这次生成的签名清单和完整安装包一同上传。
