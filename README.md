# Steam 游戏抽签器（Steam Game Picker）

> 输入 Steam ID 或资料 URL，读取你的游戏库，点一下按钮，随机抽出今晚要玩的那款。

面向 Windows 10/11 的桌面小工具，解决"库里有几百款游戏，却不知道玩什么"的选择困难。
纯 Tkinter 界面，不登录你的 Steam 账号，只通过 Steam 公开 Web API 读取公开数据。

## 功能特性

| 功能 | 说明 |
| :--- | :--- |
| 身份解析 | 支持 17 位 SteamID64、`/profiles/` URL、`/id/` 自定义名、裸自定义名四种写法 |
| 游戏库加载 | 后台线程拉取，界面不卡顿；显示总数与参与抽签数 |
| 本地缓存 | 库快照 + 详情缓存（默认 7 天）；**启动秒开、断网也能抽签** |
| 范围筛选 | 「全部参与」/「从未玩过」/「玩得很少」（后两者**可同时勾选**，取并集）；也可在列表中逐条勾选排除 |
| 抽签动画 | 1.8 秒滚动减速，定格变绿加粗；结果从当前勾选集合中均匀随机产生 |
| 结果展示 | 封面、简介、类型、发行日期、Metacritic 评分、售价（只显示未打折原价） |
| 错误提示 | 全中文，区分"资料非公开""Key 无效""库为空""请求过频"等场景 |
| 证书信任回退 | certifi 校验失败时自动切换到操作系统信任库重试，**不关闭证书校验** |

## 环境要求

- Windows 10 / 11（64 位）
- Python 3.10+（仅源码运行需要）
- 一个 Steam Web API Key：[申请地址](https://steamcommunity.com/dev/apikey)（免费，首次启动会有引导）

## 快速开始（源码运行）

```powershell
pip install -r requirements.txt
python main.py
```

首次启动会弹出引导窗口要求填入 API Key，保存后粘贴自己的 Steam 资料地址即可加载游戏库。
配置保存在 `%APPDATA%\SteamGamePicker\config.json`。

## 键盘快捷键

| 按键 | 行为 |
| :--- | :--- |
| `Enter`（输入框内） | 加载游戏库 |
| `空格` | 抽签 / 再抽一次（列表或按钮上保留其原生含义） |
| `Enter`（列表有焦点） | 切换当前行勾选 |
| `F5` | 刷新游戏库 |
| `Ctrl` + `,` | 打开设置 |
| `Esc` | 关闭设置窗口 / 取消正在进行的加载 |

## 运行测试

```powershell
python -m pytest        # 361 项
```

测试覆盖纯逻辑（ID 解析、预设计算、缓存 TTL）、网络层契约（脱机样本模拟 Steam 的
各类响应与错误码）、界面交互、性能预算、异常矩阵与证书回退路径，全部脱机运行。

## 打包安装包

```powershell
python -m PyInstaller packaging\SteamGamePicker.spec --noconfirm   # 生成 dist\SteamGamePicker.exe
ISCC.exe packaging\installer.iss                                   # 生成 dist\SteamGamePicker_Setup.exe（需 Inno Setup 6）
```

安装包特性：非管理员权限即可安装、桌面快捷方式可选、开始菜单项、安装完成后可选立即运行、
支持静默安装（`/VERYSILENT`）、卸载时询问是否保留配置（默认保留）。

打包产物自检：

```powershell
.\dist\SteamGamePicker.exe --selftest --live --report .\dist\selftest.json
```

> `dist/` 与 `build/` 已在 `.gitignore` 中排除，安装包不入库。

## 项目结构

```
SteamGamePicker/
├─ main.py                  入口（含 --selftest 打包自检）
├─ app/
│  ├─ steamid.py            身份输入解析（纯函数）
│  ├─ steam_api.py          Steam Web API 封装与错误分类
│  ├─ trust.py              证书信任回退（系统信任库）
│  ├─ pool.py               范围筛选、可抽池与均匀随机（纯函数）
│  ├─ cache.py              库快照 / 详情 / 封面缓存
│  ├─ config.py             配置读写（原子写、损坏恢复）
│  ├─ worker.py             后台线程 + 队列 + 取消令牌
│  ├─ state.py              状态机与控件启停映射
│  └─ ui/                   主窗口、动画、设置窗口、主题
├─ tests/                   361 项 pytest（含 Steam 响应样本 fixtures）
├─ packaging/               PyInstaller spec 与 Inno Setup 脚本
├─ tools/                   实测与图标生成脚本
└─ docs/                    PRD、开发计划、验收记录
```

## 文档

| 文档 | 内容 |
| :--- | :--- |
| [产品需求文档](docs/PRD.md) | 目标、页面结构、模块数据与操作、本地数据要求、必做与不做、验收标准 |
| [开发计划](docs/DEV_PLAN.md) | M0–M8 任务分解、接口契约、日程与执行结果 |
| [验收记录](docs/ACCEPTANCE.md) | AC-01 ~ AC-50 逐条结果与证据、实现偏差说明、待补测清单 |

## 隐私与安全

- 只访问 Steam 公开接口，**不需要登录 Steam 账号**，不涉及购买、下载、启动游戏
- API Key 仅保存在本机 `%APPDATA%\SteamGamePicker\config.json`，不上传、不硬编码、不随安装包分发
- 日志自动脱敏：写入的日志里不会出现完整 API Key
- 全程 HTTPS，且不会用"关闭证书校验"的方式绕过网络问题

## 许可

本仓库尚未声明开源许可证。如希望他人自由使用 / 修改 / 分发，请补充 `LICENSE` 文件
（例如 MIT）；在补充之前，默认保留所有权利。
