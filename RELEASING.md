# MJH-editor 发布文档

本文适用于 Windows PowerShell、人工操作和 AI 代理。官方公开源码与下载统一放在 zeroXlight/MJH-editor-downloads，正式源码分支为 main。

## 1. 一次完整发布的结果

| 位置 | 内容 |
| --- | --- |
| main 或个人指定分支 | 完整 src、前端 dist、构建/发布脚本、安装器脚本、README 和本文 |
| vX.Y.Z 标签 | 对应这次源码提交 |
| 正式版 Release | 正文顶部的联网下载链接、同版本离线安装器、手游资源 ZIP、源码 ZIP、签名更新清单，以及清单中列出的差分包 |
| online-setup 下载入口 | 独立的联网安装器 EXE，只在首次发布或联网安装器本身有改动时上传 |

源码 ZIP 要与版本标签的文件清单和内容一致。每次发布先完整准备附件，再发布为正式 Latest。

## 2. 环境与签名密钥

使用 Windows x64、Python 3.14、Node.js、Git、GitHub CLI，以及 Inno Setup 6.7.4 和对应的简体中文语言文件。建立开发环境。

~~~powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r '.\src\requirements.txt'
gh auth login
gh auth setup-git
~~~

按终端提示完成 GitHub 登录，授权给准备发布的目标仓库。浏览器登录和 GitHub 插件连接可用于 AI 的网页/连接器操作，Git 与 gh 命令另用本机的 CLI 凭据。

官方更新沿用原 Ed25519 私钥，默认位于 %LOCALAPPDATA%/MJH-editor-release/ed25519.key。公开公钥在 src/update_public_key.py。私钥在本地构建时读取，保存在仓库和公开附件之外。普通下载者创建自己的渠道时，使用自己的密钥，步骤见第 9 节。

本机已存在的便利路径如下，新机器按实际安装位置配置。

~~~text
Python
D:\桌面\工作区域\软件\编辑器\MJH-editor-V2.5.1\.venv\Scripts\python.exe
Inno 编译器
D:\桌面\工作区域\软件\编辑器\MJH-editor-V2.5.1\.tools\Inno Setup\ISCC.exe
中文语言文件
D:\桌面\工作区域\软件\编辑器\MJH-editor-V2.5.1\.tools\ChineseSimplified.isl
~~~

## 3. 获取源码和准备分支

官方维护者在公开仓库的 main 工作。开发者可以先建个人分支，再通过 PR 合入 main。

~~~powershell
git clone https://github.com/zeroXlight/MJH-editor-downloads.git
Set-Location -LiteralPath '.\MJH-editor-downloads'
git switch main
git pull --ff-only origin main
~~~

其他人独立发布时，先 Fork 到自己的账号，克隆自己的仓库，再建立自己的分支。发布脚本接受显式仓库和分支参数。

## 4. 修改版本和提交

修改 src/edition.py 中的 VERSION，例如改成 'V2.5.4'，同步当前版本描述和升级说明。先完成代码修改和功能验证。

前端有改动时，构建并提交生成的 dist。

~~~powershell
Push-Location -LiteralPath '.\src\desktop_ui'
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
Pop-Location

git add -- .gitignore README.md RELEASING.md build_release.py publish_release.py installer.iss '升级使用说明.txt' src
git diff --cached --stat
git commit -m "Prepare MJH-editor V2.5.4"
git status --short --branch
~~~

提交后工作区应干净。增加顶层源文件时，同步 build_release.py 的 top 打包清单。发布脚本会逐文件比较源码 ZIP 与 Git 跟踪内容。

## 5. 构建安装器和附件

准备完整 mobile_assets 目录。可以解压上一版的 MJH-editor-MobileAssets.zip，得到 mobile_assets。设置本机路径并运行。

~~~powershell
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
$mobile = Join-Path (Get-Location) 'mobile_assets'
$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
$chinese = 'C:\Program Files (x86)\Inno Setup 6\Languages\ChineseSimplified.isl'

& $python '.\build_release.py' --mobile-assets $mobile --iscc $iscc --chinese-language $chinese
if ($LASTEXITCODE -ne 0) { throw '发布构建失败' }
~~~

若中文文件是单独下载的，将 $chinese 改成它的实际路径。建议每个正式版本从新的干净工作目录构建，保存上一版的原始附件。修改资源时使用新的输出目录，脚本会拒绝复用内容标识不同的资源 ZIP。

release-assets 中必须有下面四个文件，文件名保持一致。

~~~text
MJH-editor-Setup.exe
MJH-editor-MobileAssets.zip
MJH-editor-Source.zip
update.json
~~~

脚本会编译编辑器和独立修复工具，打包资源 ZIP、源码 ZIP 与固定版本安装器。update.json 的签名覆盖版本、安装器大小、SHA-256 及可用差分信息。联网安装器在运行时读取最新正式版的 update.json，再校验并启动该版本的完整安装器。

### 维护联网安装入口

首次发布联网安装器或修改联网安装器时，在原构建命令追加 `--build-online-setup`，生成 `release-assets/MJH-editor-OnlineSetup.exe`。在 GitHub 创建标签为 `online-setup` 的独立 Release 并上传此 EXE，按 GitHub 的 Pre-release 类型发布。GitHub 的 Latest 继续用于带签名清单的正式版本。

固定下载地址是 `https://github.com/OWNER/REPOSITORY/releases/download/online-setup/MJH-editor-OnlineSetup.exe`。维护此入口时保留标签和文件名。以后只发布编辑器版本时，沿用原 EXE 和固定地址。仓库首页和每个新正式版正文顶部都提供这一下载入口。

### 生成差分

将上一版正式发布的原始 MJH-editor-Setup.exe 和 update.json 放在同一个目录，追加下面参数。

~~~powershell
& $python '.\build_release.py' --mobile-assets $mobile --iscc $iscc --chinese-language $chinese --previous-release 'D:\ReleaseHistory\v2.5.3'
~~~

--previous-release 可重复指定多个版本。脚本验证基线，生成小于完整包 80% 的差分才会纳入发布。清单列出的 MJH-editor-From-*.bsdiff 全部随本版上传。

V2.5.3 开始缓存安装基线，V2.5.1/V2.5.2 首次迁移仍下载完整包。后续有匹配基线时优先差分，失败可回退完整包。

## 6. 本地验证和发布说明

在独立目录验证自选安装目录、默认可选组件、补装、更新进度、开始菜单的更新修复工具、正常退出后安装，以及重新打开的版本号。

运行联网安装器，确认它下载的是当前公开 Latest，下载结束后打开对应版本的安装向导。发布前从本地构建运行时，它会获取 GitHub 上已发布的正式版。发布后可再用早期保存的联网安装器验证它是否能找到新版。

模拟编辑器 EXE 缺失时，修复工具应能独立打开。编辑器卡住时，先通过任务管理器结束该编辑器进程，再运行修复工具。差分重建的安装包应与正式完整包逐字节或 SHA-256 一致。

发布说明放在忽略提交的 release-assets 内，保持真实换行。

~~~powershell
@'
本版变更
- 填入真实变更。
- 填入升级注意事项。
'@ | Set-Content -LiteralPath '.\release-assets\notes.md' -Encoding utf8

& $python '.\publish_release.py' --repository zeroXlight/MJH-editor-downloads --branch main --notes-file '.\release-assets\notes.md' --check-only
if ($LASTEXITCODE -ne 0) { throw '发布校验失败' }
~~~

校验失败时修正原因。源码、文档或安装器脚本变化后，重新提交和构建。

## 7. 同步 main 并发布

~~~powershell
& $python '.\publish_release.py' --repository zeroXlight/MJH-editor-downloads --branch main --notes-file '.\release-assets\notes.md'
if ($LASTEXITCODE -ne 0) { throw '发布中断，请检查输出和 GitHub 状态' }
~~~

脚本确认 origin、当前分支、干净工作区和源码 ZIP 一致后，普通快进推送目标分支，并创建对应提交的版本标签。接着创建草稿、上传全部附件、核对 GitHub 的大小和 SHA-256，最后发布为正式 Latest。

如果网络中断，读取 GitHub 真实状态后处理。相同版本仍为草稿时，可用原提交和附件重试。已发布版本的修正使用新版本号。并发提交导致推送被拒绝时，先读取并合并远端改动，再重新构建。

通过网页或连接器发布时也遵循相同顺序。先同步完整源码到目标分支，再用该确切提交建立 vX.Y.Z 标签。将联网安装器固定下载地址放在发布说明首段，草稿收齐并核对四个固定附件及差分文件后设为正式 Latest。使用 `publish_release.py` 时会自动添加下载链接。

## 8. 发布后核验与故障修复

~~~powershell
$repository = 'zeroXlight/MJH-editor-downloads'
$tag = 'v2.5.4'
gh api "repos/$repository/releases/tags/$tag" --jq '{tag: .tag_name, draft: .draft, prerelease: .prerelease, assets: [.assets[] | {name, size, digest}]}'
gh api "repos/$repository/releases/latest" --jq '.tag_name'
git ls-remote origin "refs/heads/main" "refs/tags/$tag"
~~~

确认 Latest、标签提交、源码 ZIP 和 Git 源码一致。使用已安装旧版检查新版，验证签名、下载和退出安装。保留旧版安装器和验证记录。有故障时从保存的源码修正后提升版本发布，客户端只按版本号递增更新。

## 9. 在自己的仓库和分支独立发布

先在 GitHub Fork 公开仓库，替换下面 YOUR_NAME 并克隆自己的 Fork。

~~~powershell
git clone https://github.com/YOUR_NAME/MJH-editor-downloads.git
Set-Location -LiteralPath '.\MJH-editor-downloads'
git switch -c release/2.5.4
git remote -v
~~~

只贡献修改时，在自己的分支提交并发 PR。独立分发给自己的用户时，需要配置自己的更新渠道。

1. 将 src/editor_update.py 的 RELEASES 改为自己的公开仓库，例如 https://github.com/YOUR_NAME/MJH-editor-downloads/releases。
2. 仅在自己的开发副本中，将 src/update_public_key.py 移出仓库备份，然后选择一个全新的、位于仓库之外的私钥路径。
3. 为自己的新渠道生成公钥和私钥。

~~~powershell
$key = Join-Path $env:LOCALAPPDATA 'MJH-editor-MY-FORK-release\ed25519.key'
& $python '.\build_release.py' --init-key --key $key
~~~

以后每次 build_release.py 都追加 --key $key。提交自己的公钥和渠道设置。自己的用户首次完整安装这个渠道版本后，就会信任自己的签名和更新地址。作者版继续沿用作者的公钥和渠道。

4. 独立分发时统一修改 installer.iss 的 AppId、DefaultDirName、DefaultGroupName、AppMutex，以及 src/editor_update.py 的 APP_MUTEX。同时安装多个渠道时，为自己的更新设置和缓存选择独立的用户配置目录。
5. 按前述步骤修改、提交、构建和校验，发布参数使用自己的仓库和分支。首次发布时同时创建自己的 `online-setup` 下载入口，将 README 的联网安装器下载地址改成自己的仓库。

~~~powershell
& $python '.\publish_release.py' --repository YOUR_NAME/MJH-editor-downloads --branch release/2.5.4 --notes-file '.\release-assets\notes.md'
~~~

## 10. 可直接交给 AI 的任务模板

填好仓库、分支、版本和本机路径后使用。

~~~text
先阅读根目录 RELEASING.md，完成 MJH-editor 的修改、构建、验证与发布。
授权目标仓库为 OWNER/REPOSITORY，目标源码分支为 BRANCH，版本为 VX.Y.Z。
将完整源码、前端 dist、构建/发布脚本、安装器脚本和文档同步到上述分支。
原私有仓库 zeroXlight/MJH-editor 保持原样。
个人发布以我自己的 Fork 为 origin，先配置我的更新渠道、公钥和安装标识。
沿用指定本地私钥完成签名，私钥保存在源码和公开附件之外。
先完成前端构建、代码验证和提交，再运行 build_release.py。
需要差分时用上一版正式发布的原始附件作基线。
运行 publish_release.py --check-only，核对源码 ZIP 与提交逐文件一致。
发布时同步目标分支、标签、四个固定附件和签名清单列出的差分文件。
在正式版说明开头添加固定联网入口链接。联网安装器有改动时才重新构建并更新独立入口。
核对云端哈希后发布为 Latest，再检查旧版检测新版。
最后返回源码提交、版本发布、发布文档的链接，以及真实验证结果。
~~~
