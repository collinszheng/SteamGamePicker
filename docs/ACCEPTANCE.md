# Steam Game Picker · v1.0.1 验收记录

| 项目 | 内容 |
| :--- | :--- |
| 依据文档 | [`PRD.md`](PRD.md) v1.8、[`DEV_PLAN.md`](DEV_PLAN.md) v1.0 |
| 代码版本 | v1.0.1（本仓库，已发布 [Release v1.0.1](https://github.com/collinszheng/SteamGamePicker/releases/tag/v1.0.1)） |
| 验收日期 | 2026-09-19 |
| 验收环境 | Windows 11（10.0.26300）、Python 3.12.10、requests 2.34.2、Pillow 12.3.0、truststore（可选依赖）、PyInstaller 6.22.3、Inno Setup 6.7.3（Inno 未随附中文语言包） |
| 最新修复 | v1.3（D8）证书信任回退；v1.4（D9）快捷范围可并存 + 抽签结果不再被占位文案覆盖；v1.5（D10）界面改为 Steam 官方深色风格；v1.6（D11/D12）应用更名为 Steam Game Picker + 中英双语界面与英文 README；v1.7（D13）图标改为 Steam 风格骰子；v1.0.1 发布（exe 版本资源 + 覆盖升级清理旧名快捷方式） |
| 自动化测试 | **477 项全部通过**（`python -m pytest`）；同一套测试已在 **GitHub Actions（windows-latest）** 上通过，见下方持续集成证据 |
| 真实接口校验 | 商店详情 **6/6**、真实账号端到端 **4/4**（v1.5 时期用用户提供的 SteamID64 与密钥实测，均经环境变量传入、未写入代码）：`https://steamcommunity.com/profiles/<SteamID64>` → **61 款游戏，加载 0.55 秒**。**v1.0.1 发布当天的复测未能进行**：本机网络到 Steam 全线返回 502/503/504（同一时刻 GitHub 可达，程序侧 `live_api` 如实报 `network`），详见 9.15；账号矩阵中"非公开 / 空库 / 无效 Key"三项仍待提供对应账号 |

## 0. 结论摘要

| 状态 | 数量 | 说明 |
| :--- | :--- | :--- |
| ✅ 通过 | 50 | 有自动化测试或实测证据 |
| ⚠️ 部分通过 | 3 | AC-36（控件重叠需人工目视）、AC-37（真实按键事件）、AC-43 之外的设备相关项见下行 |
| ⏸ 待凭据 / 待设备 | 3 | AC-06 / AC-07 / AC-08 中需要"非公开 / 空库 / 无效 Key"的场景；AC-43 的干净 Win10 机器 |
| ❌ 未通过 | 0 | — |

> 说明：⏸ 的项目**不是实现缺失**，而是需要用户提供 Steam API Key / 测试账号 / 第二台干净机器。
> 对应工具已交付：`tools/live_check.py`（设置 `STEAM_API_KEY`、`SGP_PUBLIC_ID`、`SGP_PRIVATE_ID`、`SGP_EMPTY_ID`、`SGP_INVALID_KEY` 后运行即可）。

---

## 1. 逐条验收

### 9.1 输入与解析

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-01 四种写法 | ✅ | `tests/test_steamid.py::test_steamid64_inputs` / `test_vanity_inputs`（纯数字、`/profiles/`、`/id/`、裸自定义名、大小写、带查询串、带尾斜杠） |
| AC-02 空输入 | ✅ | `test_steamid.py::test_empty_input`；`test_main_window.py::test_load_with_empty_input_reports_error`（提示"请先输入 Steam ID 或资料地址"，且不发起请求） |
| AC-03 不存在的自定义名 | ✅ | `test_steam_api.py::test_resolve_vanity_no_match_returns_success_42`（`success:42` → "无法解析该资料地址…"） |
| AC-04 Key 格式校验 | ✅ | `test_settings_dialog.py`（31 位 / 33 位 / 非十六进制 / 空 均被拒绝并显示格式要求） |

### 9.2 加载与缓存

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-05 大库加载 ≤5 s 且可拖动 | ✅ | **真实账号实测**：61 款库从请求到解析完成 **0.55 秒**；本地处理 1000 款：解析 < 1 s、载入列表 < 2 s、搜索 < 1 s（`tests/test_performance.py`）；主线程不做网络调用（`test_worker.py::test_task_runs_off_main_thread`） |
| AC-06 非公开账号 | ⏸/✅ | 契约层已测：`test_steam_api.py::test_private_profile_is_distinguished_from_empty_library`、`test_main_window.py::test_load_error_reports_private_profile`；真实账号实测待 Key |
| AC-07 空库 | ⏸/✅ | 契约层：`test_empty_library_reports_empty_library`；真实账号实测待 Key |
| AC-08 无效 Key | ⏸/✅ | 契约层：`test_steam_api.py::test_invalid_key_mapping`（401/403）；真实无效 Key 实测待提供 |
| AC-09 重开后恢复 | ✅ | `test_startup.py::test_startup_uses_cache_then_refreshes`（状态行含"上次更新"） |
| AC-10 断网可抽签 | ✅ | `test_startup.py::test_refresh_failure_falls_back_to_offline`（黄条 + 抽签可用） || AC-11 加载中取消 | ✅ | `test_worker.py::test_result_of_cancelled_task_is_dropped`、`test_main_window.py::test_cancel_load_cancels_task`、`test_shortcuts.py::test_escape_cancels_running_load` |
| AC-12 删缓存目录 | ✅ | `test_acceptance_matrix.py::test_ac12_cache_directory_deleted` |

### 9.3 范围与过滤

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-13 从未玩过 | ✅ | `test_pool.py::test_preset_never_played`、`test_main_window.py::test_preset_click_overwrites_manual_selection` |
| AC-14 玩得很少阈值 | ✅ | `test_pool.py::test_preset_low_playtime_threshold`（120 / 60 两个阈值） |
| AC-15 手动改动切自定义 | ✅ | `test_main_window.py::test_toggle_game_marks_custom_preset` |
| AC-16 勾选重启一致 | ✅ | `test_main_window.py::test_manual_selection_persists_to_disk`（含"凑巧等于预设"时的识别：`test_selection_matching_a_preset_is_recognised_as_that_preset`） |
| AC-17 全选作用域 | ✅ | `test_main_window.py::test_bulk_buttons_only_affect_current_search_results`（有搜索 / 无搜索两种作用域） |
| AC-18 1000 款展开与勾选 | ✅ | `test_ui_smoke.py::test_treeview_handles_1000_rows_within_budget`（< 2 s）、`test_treeview_checkbox_toggle_is_cheap`、`test_performance.py::test_window_handles_1000_games_within_budget` |
| AC-19 全排除 | ✅ | `test_state.py::test_s4_empty_pool`、`test_main_window.py::test_empty_pool_disables_draw_and_offers_expand` |

### 9.4 抽签

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-20 动画 1.8 s | ✅ | `test_animator.py::test_interval_plan_matches_prd_timing`（50×24 + 55/70/90/110/130/145 = 1800 ms） |
| AC-21 连点与并发保护 | ✅ | `test_state.py::test_s5_drawing_locks_inputs`、`test_main_window.py::test_drawing_state_locks_inputs`、`test_main_window_draw.py::test_draw_with_empty_pool_does_nothing`（动画期间输入/范围/加载全部禁用） |
| AC-22 50 次都在池内 | ✅ | `test_main_window_draw.py::test_draw_only_picks_from_checked_pool`（20 次 UI 级）；`test_pool.py::test_pick_is_uniform_without_bias`（10000 次频次偏差 < 8%） |
| AC-23 单款跳过滚动 | ✅ | `test_animator.py::test_single_pool_skips_rolling`、`test_main_window_draw.py::test_single_game_pool_uses_short_path`（300 ms 直接定格） |
| AC-24 动画中关窗 | ✅ | `test_worker.py::test_shutdown_stops_polling`、`test_main_window.py::test_on_close_saves_and_destroys`（保存配置 → 停轮询 → after_cancel → 销毁） |

### 9.5 详情展示

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-25 信息完整 | ✅ | `test_main_window_draw.py::test_details_loaded_and_rendered`；**真实接口**：Dota 2 / Stardew Valley 字段解析正确（`tools/live_check.py`） |
| AC-26 免费游戏 | ✅ | `test_models.py::test_free_game_shows_free_and_ignores_price`；**真实接口**：Dota 2 `is_free=true` → 显示"免费" |
| AC-27 打折只显示原价 | ✅ | `test_steam_api.py::test_app_details_discounted_game_keeps_original_price`；**真实接口**：Stardew Valley 输出 `¥ 48.00`，不含 `%` 与"折" |
| AC-28 缺字段 / success:false | ✅ | `test_main_window_draw.py::test_details_missing_fields_use_placeholder`、`test_details_success_false_degrades`（显示 `—` 与"无法获取详情"） |
| AC-29 断网详情降级 | ✅ | `test_main_window_draw.py::test_offline_detail_failure_keeps_draw_enabled` |
| AC-30 第二次命中缓存 | ✅ | `test_main_window_draw.py::test_cached_details_skip_network`（断言 worker 提交次数为 0） |

### 9.6 数据与恢复

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-31 配置损坏 | ✅ | `test_config.py::test_corrupt_json_is_backed_up_and_reset`（生成 `config.corrupt-<时间戳>.json`，按默认值启动） |
| AC-32 字段缺失 | ✅ | `test_config.py::test_missing_fields_use_defaults`、`test_wrong_types_are_coerced` |
| AC-33 强杀后配置可读 | ✅ | `test_config.py::test_atomic_write_leaves_no_temp_file`、`test_acceptance_matrix.py::test_ac33_leftover_temp_file_does_not_break_loading`、`test_json_config_written_is_always_parseable`（连续 20 次保存后每次都完整可解析） |
| AC-34 日志脱敏 | ✅ | `test_logging_setup.py`（`key=` 查询参数、`"api_key"` 字段、注册密钥三类脱敏；轮转 1 MB × 3） |
| AC-35 目录迁移 | ✅ | `test_acceptance_matrix.py::test_ac35_whole_directory_migration`（整目录复制后 Key / 上次 ID / 勾选 / 快照 / 详情 / 封面全部可用） |

### 9.7 界面与可用性

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-36 640×480 不重叠 | ⚠️ | 最小尺寸与自适应规则已实现并单测（`test_ui_smoke.py::test_header_image_size_keeps_aspect`、`test_theme_values_match_prd`）；**控件重叠需人工目视确认**（自动化无法可靠判定 Tk 布局重叠） |
| AC-37 纯键盘操作 | ⚠️/✅ | 绑定与分支逐条测试：`test_shortcuts.py`（空格、F5、Ctrl+,、Esc）；`Enter` 加载与列表 `Enter` 见 `test_main_window.py::test_on_tree_return` 路径。**真实按键事件**因窗口需 withdraw 而无法可靠合成，改以处理器级验证 |
| AC-38 全中文提示 | ✅ | `test_errors.py`（逐条锁定 PRD 5.7 文案、级别与按钮，含"每个 Err 都有中文文案"参数化测试） |
| AC-39 首启关窗不崩 | ✅ | `test_settings_dialog.py::test_first_run_guide_can_be_closed_without_crash`（停在 S0，抽签禁用） |

### 9.8 打包与安装

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-40 非管理员安装 | ✅ | **实测**：以受限令牌（`runas /trustlevel:0x20000`）安装成功，`install_exit=0`，安装到 `%LOCALAPPDATA%\Programs\SteamGamePicker`，安装后 exe 自检 `exit=0`，卸载 `exit=0` |
| AC-41 快捷方式 | ✅ | **实测**（v1.0.0 安装包）：桌面快捷方式存在，开始菜单目录内含应用与卸载两个快捷方式。**更名后的复核已完成**：v1.0.1 安装包实测得到「Steam Game Picker」目录 + 新名桌面快捷方式，并且从 v1.0.0 覆盖升级时旧名快捷方式会被清理（见 9.15 / AC-56） |
| AC-42 卸载保留配置 | ✅ | **实测**：静默卸载后安装目录已删除、`%APPDATA%\SteamGamePicker` 保留；交互式卸载会弹"是否同时删除配置与缓存"（默认"否"） |
| AC-43 干净 Win10 + Win11 | ⏸ | 本机（Win11 10.0.26300）安装→运行→卸载全流程通过；**干净 Win10 机器待补测** |

### 9.9 v1.2 确认的交互细节

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-44 预设覆盖手动 | ✅ | `test_main_window.py::test_preset_click_overwrites_manual_selection`（无确认弹窗，状态行轻提示） |
| AC-45 空格分流 | ✅ | `test_shortcuts.py::test_space_starts_draw`、`test_space_defers_to_native_widget`；**偏差见第 2 节第 1 条** |
| AC-46 列表 Enter 切换 | ✅ | `test_shortcuts.py`（空格不切换勾选）、`test_main_window.py` 列表交互测试 |

### 9.10 v1.3 证书信任回退（D8）

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-47 中间层环境自动回退 | ✅ | **实测**：修复前同一环境报 `network`（`SSLCertVerificationError`）；修复后 `tools/live_check.py` 8/8 通过（日志出现"证书校验失败，已切换到操作系统信任库并重试一次"）；打包产物与**已安装版本**自检均返回 `"live_api": "ok"`。单测覆盖回退路径：`test_trust.py::test_retries_once_with_system_trust` |
| AC-48 无 truststore 时的提示与重试上限 | ✅ | `test_trust.py::test_tls_trust_error_when_package_missing`（1 次尝试 + 专用中文提示）、`test_tls_trust_error_after_failed_retry`（最多 2 次）、`test_plain_connection_error_does_not_touch_truststore`（断网不误触发）、`test_non_certificate_ssl_error_is_network`（协议错误不算证书问题） |

### 9.11 v1.4 快捷范围可并存与结果展示（D9）

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-49 两个筛选可并存 | ✅ | `tests/test_range_filters.py`（11 项）：`test_both_filters_can_be_checked_together`、`test_unchecking_one_filter_keeps_the_other`、`test_all_button_clears_both_filters`、`test_unchecking_last_filter_falls_back_to_all`、`test_manual_change_switches_to_custom_and_clears_filters`、`test_filters_persist_and_restore`、`test_combined_filters_drive_the_draw_pool`；**真实数据印证**：用户 61 款库中"从未玩过"11 款 + "玩得很少"16 款 = 并集 27 款，与代码计算一致 |
| AC-50 结果不被占位覆盖 | ✅ | `test_state.py::test_drawn_result_is_never_overwritten_by_placeholder`、`test_empty_pool_hint_still_shown_even_with_result`；`test_main_window_draw.py`：详情加载完成后 / 详情失败后 / 切离线态后大字区仍为中签游戏名，且未抽签时占位文案正常显示、再抽一次会替换旧结果 |

### 9.12 v1.5 Steam 官方风格改版（D10）

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-51 配色与控件样式 | ✅ | `tests/test_ui_theme.py`（33 项）：官方色板锁定（`#171a21/#1b2838/#2a475e/#66c0f4/#c6d4df`）、主按钮绿 `#4c6b22`、中签绿 `#a4d007`；`test_apply_theme_installs_styles` 验证 `ttk` 切到 `clam` 且样式实际生效；16 组前景/背景组合按 WCAG AA ≥ 4.5:1 参数化校验；`test_legacy_light_theme_colors_are_gone` 防止旧浅色配色回流；勾选框指示器用 clam 真正支持的 `indicatorbackground/indicatorforeground`（`test_clam_supports_the_options_we_configure` 防止再写错选项名） |
| AC-52 布局与自适应 | ✅ | `test_no_widget_overflows_the_window`（800×600 与 640×480 下逐控件用 Tk 几何数据判定无越界，并断言受检控件 ≥ 20 个，避免空测试）；`test_short_window_auto_collapses_pool_panel`（窗口 < 520 高自动收起且不改写用户配置）；`test_cover_placeholder_is_hidden_until_a_result`；`test_bulk_button_labels_are_on_their_own_row`（搜索框与批量按钮分行，避免 800px 下按钮被裁）；`test_zone3_placeholder_uses_small_font`（26pt 提示会截断，改用 12pt） |

### 9.13 v1.6 改名与中英双语（D11 / D12）

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-53 中英双语界面 | ✅ | `tests/test_i18n.py`（19 项）：中英键集合完全一致（`test_translation_keys_are_in_sync`）、无空译文、占位符一致、缺失键渲染为 `⟦key⟧` 而不是抛异常、非法语言值回落中文；**英文界面不得残留中文**（`test_english_main_window_has_no_cjk` / `test_english_dialogs_have_no_cjk`，逐控件扫描文本，白名单仅放语言选择器里的「中文」自名）；中文文案与改版前**逐字节一致**（`test_chinese_strings_are_unchanged`，保证既有 407 项断言仍是回归网）；切换语言后已加载的库 / 勾选 / 搜索词 / 中签结果 / 列表展开态**全部保留**（`test_language_switch_preserves_loaded_state`）；设置保存后立即生效并可跨重启持久化（`test_settings_dialog_persists_language`、`test_language_survives_restart`）；英文下状态行、空池提示、缓存时间与详情字段均为英文（`test_english_status_messages`、`test_english_cache_and_details`）。**界面证据**：`docs/evidence/ui-english.png`（英文界面截屏） |
| AC-54 双语 README | ✅ | `tests/test_docs.py`（12 项）：`README.md`（中文，GitHub 默认渲染）与 `README.en.md`（英文）**互相链接**且切换链接位于正文前 12 行内；两版都必须包含安装包下载入口（指向 `releases/latest`）；`README.md` 必须为中文而 `README.en.md` 必须为英文（按 CJK 字符占比判定）；6 个 markdown 文件的全部**相对链接可达**（`test_relative_links_resolve`，防止改名后链接失效）；两版功能清单条目数一致（防止只更新单边） |

### 9.14 v1.7 图标重做（D13）

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-55 Steam 风格骰子图标 | ✅ | `tests/test_icon.py`（21 项）：ICO 必须含 16/24/32/48/64/128/256 七个尺寸且逐帧校验"圆角外全透明"（不带 alpha 会在任务栏上出现黑角）；**按像素采样**验证 Steam 深蓝徽章（四角暗且蓝 > 红）、浅色骰子面、深蓝点数与上沿的 Steam 蓝描边（不是只看源码里写了什么颜色）；小尺寸必须单独渲染——断言 16 像素"单独出图"与"缩小 256 图"逐字节不同，且点数规则为 ≥48 用 5 点、以下用 3 点；**生成过程不得出现 `ImageFont` / `draw.text` / `"抽"` 字面量**（旧图标是中文单字，更名后不应回流）；颜色必须从 `app/ui/theme.py` 取（唯一出处）；打包脚本（spec 与 .iss）必须引用同一个 `app.ico`。**链路实测**：用新图标完整跑通 PyInstaller 与 Inno Setup，并把两个产物里的图标抽出来核对，均为骰子图标（见第 4 节）。**视觉证据**：`docs/evidence/icon-preview.png`（深色/浅色背景真实像素 + 16/24/32/48 放大检查）、`docs/evidence/icon-256.png`；源码运行的窗口图标经**带标题栏截图人工核对**（`tools/capture_ui.py` 第 4 个参数） |

### 9.15 v1.8 覆盖升级（AC-56）

| 编号 | 结果 | 证据 |
| :--- | :--- | :--- |
| AC-56 旧版本覆盖升级 | ✅ | **真机实测**（本机 Windows 11，全部用发布产物，非源码）：① 干净状态静默安装**已发布的 v1.0.0 安装包** → 注册表 `Steam 游戏抽签器 1.0.0`、开始菜单目录「Steam 游戏抽签器」含 2 个快捷方式、桌面快捷方式为旧名；② 直接运行 **v1.0.1 安装包**覆盖升级 → 注册表变为 `Steam Game Picker 1.0.1`、安装目录沿用 `%LOCALAPPDATA%\Programs\SteamGamePicker`、开始菜单只剩「Steam Game Picker」一个目录且只有应用与卸载两个快捷方式、桌面快捷方式变为新名、exe 文件属性显示 `1.0.1.0`，**`config.json` 的 SHA256 前后完全一致**；③ 静默卸载 → 注册表项与安装目录清空、快捷方式清空，**配置目录（config.json / cache / logs）原样保留**；④ 再次安装 v1.0.1 并跑 `--selftest`（`docs/evidence/selftest-live-v101-installed.json`，`version: "1.0.1"`、`frozen: true`、`tk_ok/pillow_ok/requests_ok/truststore_ok: true`）。回归防线：`tests/test_release.py` 里 5 项断言锁住安装脚本的升级行为（`UsePreviousAppDir=yes`、`UsePreviousGroup=no`、`[InstallDelete]` 清理旧名目录与旧桌面快捷方式、桌面任务不得带 `checkedonce`），改动被误删会立刻失败 |

> **联网项说明**：本次复测时本机网络到 Steam 全线不可达（`api.steampowered.com` 504、
> `store.steampowered.com` 503、`steamcommunity.com` 502），而同一时刻 GitHub API 正常（200）。
> 因此 v1.0.1 的"真实账号拉库"未能在发布当天重跑；该链路在 v1.5 时期已实测通过
> （61 款游戏、0.55 秒），契约层另有脱机样本测试全程覆盖。网络恢复后可执行
> `python tools/live_check.py`（设置 `STEAM_API_KEY` 与 `SGP_PUBLIC_ID`）补跑，退出码 0 即通过。

---

## 2. 与 PRD 的实现偏差（全部为有意为之，已记录）

| # | 偏差 | 原因 |
| :--- | :--- | :--- |
| 1 | AC-45 的空格分流：焦点在**按钮**上时，空格交给按钮本身而不是抽签 | Tk 的按钮在类绑定阶段就已响应空格；若同时触发抽签会出现"一次按键两个动作"。文本输入框与按钮之外的所有位置仍严格按 AC-45 触发抽签 |
| 2 | `errors.message()` 返回**级别**（ok/warn/error/muted）而非直接返回颜色 | 颜色属界面关注点，由 `app/ui/theme.py` 映射为 PRD 5.7 的绿/黄/红/灰；行为不变 |
| 3 | 区2 折叠开关用 `ttk.Button` 而非 PRD 11.3 写的 `Checkbutton(style="Toolbutton")` | 同一交互，按钮更易做"▸/▾ + 当前范围"动态文案与状态断言 |
| 4 | 新增一条状态文案"正在获取详情…" | 对应状态机 S6 的骨架显示，PRD 5.7 表未列 |
| 5 | 详情请求期间隐藏 [重试] 按钮 | 防止连点重复提交（PRD 未规定，属交互补强） |
| 6 | 缓存清理严格守住 200 MB 上限：极端情况下（上限小到连快照都装不下）最新快照也会被清理 | PRD 6.4 要求"缓存总量上限"；最新快照天然是 mtime 最新的文件，正常规模下必然留到最后 |
| 7 | 安装向导界面为英文 | Inno Setup 6.7.3 官方未随附简体中文语言包（`packaging/ChineseSimplified.isl` 若存在则脚本会自动切换为中文）；应用本身界面全中文，不受影响 |
| 8 | exe 未做代码签名 | 代码签名需购买证书（PRD 风险表已列，SmartScreen 可能提示）。**版本资源已在 v1.0.1 补上**（文件属性里能看产品名、版本 1.0.1 与版权），由 `tools/version_info.py` 从 `app.APP_VERSION` 生成，不再各写一份 |
| 9 | 额外新增文件 | `app/cancellation.py`、`app/state.py`、`app/images.py`、`app/i18n.py`、`app/ui/animator.py`、`tools/`（这是把 PRD 可维护性要求与验收要求落地的必要补充，行为不超出 PRD） |
| 10 | 语言选择器里的语言名用**本族写法**呈现（`中文` / `English`），不随界面语言翻译 | 这是语言选择器的通行做法：界面已经是英文时若把「中文」显示成 `Chinese`，看不懂英文的用户反而找不到回中文的入口。因此该项是唯一允许在英文界面出现 CJK 的地方，并在测试中显式白名单化（`test_english_main_window_has_no_cjk`） |
| 11 | 界面语言是**进程级全局状态**而不是逐控件传入 | 与 Tk 的控件树构建方式匹配（`rebuild_ui` 按语言整体重建），避免几百处构造参数透传；纯逻辑模块（`steamid`/`pool`/`models`/`config`/`cache`）不感知语言，仅经由 `t()` 取文案，仍然可无界面单测 |

---

## 3. 开发期发现并修复的缺陷

| # | 缺陷 | 修复 |
| :--- | :--- | :--- |
| 1 | `MainWindow.set_state` 引用未定义变量，窗口完全无法创建 | 移除残留分支 |
| 2 | 加载中（S2）"刷新"按钮未按 PRD 11.1 禁用 | `set_state` 改为仅在 `LOAD_ENABLED` 时启用刷新 |
| 3 | 点 [重试] 后按钮不消失，可被连点重复提交 | 进入详情请求时隐藏 [重试] |
| 4 | 缓存清理"永不删最新快照"的豁免会让 200 MB 上限无法保证 | 改为严格守上限，按 mtime 从旧到新清理 |
| 5 | 静默卸载时自定义确认框仍会弹出，自动化部署会卡住 | `CurUninstallStepChanged` 中判断 `UninstallSilent` 直接返回（默认保留数据） |
| 6 | 无信息的状态会覆盖状态行，勾选一次就丢掉"已加载 N 款" | 状态机新增 `status_hint`，仅 NO_KEY / LOADING / EMPTY_POOL 才更新状态行 |
| 7 | 反复创建/销毁 Tk 解释器导致测试偶发 `init.tcl` 失败 | 测试改为会话级共享隐藏窗口，并显式设置 `TCL_LIBRARY`/`TK_LIBRARY` |
| 8 | **【用户实测反馈】** 输入 Steam URL 后提示"网络连接失败"，实际是 `SSLCertVerificationError`：本机根证书不在 certifi 清单中，所有请求全部失败 | 新增 `app/trust.py` + 可选依赖 `truststore`：仅在确认证书链校验失败时切换到操作系统信任库并**每请求最多重试一次**（不关闭证书校验）；新增 `Err.TLS_TRUST` 专用中文提示；`tools/live_check.py` 增加端到端 URL→库 检查；`--selftest --live` 让打包产物自查真实联网 |
| 9 | 上述修复的首版把重试守卫做成"每客户端一次"，导致信任库切换成功后的后续请求再遇证书错误时不再重试 | 改为**每请求最多重试一次**（既不无限循环，后续请求也能受益），并由 `test_trust.py::test_retry_also_works_for_library_and_details` 锁定 |
| 10 | **【用户反馈】** 抽签定格后，详情加载完成/失败回到 S3 时，区3 的大字被"输入 Steam ID 或资料地址后点击「加载游戏库」"占位文案覆盖，中签结果消失 | `state.controls_for` 在 READY / IDLE / OFFLINE 且已有结果时不再下发占位文案（PRD 11.1 S3 "灰色占位**或上次结果**"），并补 7 项回归测试（AC-50） |
| 11 | **【用户要求改进】** 「从未玩过」与「玩得很少」原先互斥，无法同时筛选 | 改为可并存的复选（并集）；「全部参与」保持单选并点击即清空两个复选；两个都取消时回落为全部参与；手动改动后切「自定义」（D9 / AC-49） |
| 12 | **【用户要求改版】** 原浅色界面风格不够好，希望贴近 Steam 官方观感 | 整体改为 Steam 官方深色配色 + 商店绿色主按钮（D10 / AC-51）；`ttk` 切到 `clam` 才能自绘深色控件；列表加斑马纹与被排除行灰显、区域卡片化、顶栏加 Steam 蓝强调线 |
| 13 | 改版过程中用截屏自查发现三处真实问题：占位文案沿用 26pt 大字被窗口截断、搜索框与三个长文案批量按钮同行导致横向溢出、抽签后封面位挤掉列表高度 | 占位/提示改用 12pt；搜索框与批量按钮分行；未抽签时不占封面位 + 封面宽度比例 0.42→0.30；新增"逐控件越界检测"测试（AC-52）作为回归防线 |
| 14 | **【用户要求改名】** 原名「Steam 游戏抽签器」不好听 | 显示名统一改为 **Steam Game Picker**（窗口标题 / 顶栏 / 关于窗 / 安装包与快捷方式）；**配置目录与 exe 名仍为 `SteamGamePicker`**，老用户配置零迁移（D11） |
| 15 | **【用户要求】** 需要英文界面与英文 README | 文案抽到 `app/i18n.py`（含错误、状态、按钮、表头、设置、关于共 ~90 个键），设置窗口新增语言选项（默认中文，保存即生效并持久化）；新增 `README.en.md` 与中文版互相链接；补 19 项 i18n 测试（含"英文界面不得残留中文"）与 12 项文档测试（AC-53 / AC-54） |
| 16 | 国际化的首版把「英文界面含 CJK」判定写得太宽，误报语言选择器里的「中文」 | 白名单化 `LANGUAGE_NAMES` 的取值本身，其余任何控件文本含 CJK 即失败（保持严格，避免以后漏译被放过） |
| 17 | **【截屏自查发现】** 证据截图工具没换算 DPI：程序未做 DPI 感知，Windows 按 125% 缩放窗口，而 Tk 的 `winfo_*` 是逻辑像素、`ImageGrab` 抓的是物理像素 | 抓图前按「物理屏宽 ÷ 逻辑屏宽」换算 bbox。此前所有界面证据图其实只拍到了窗口左上角约 80%，且整体偏移十几像素；已全部重新抓取（现为 1000×750 物理像素） |
| 18 | 由 17 引出的疑问："英文文案更长，会不会在 800×600 下越界？" | 用 Tk 几何数据实测**没有越界**；顺手把 AC-52 的"逐控件越界检测"参数化到英文界面（`test_no_widget_overflows_in_english`），把这个可能性彻底钉住 |
| 19 | **【发布前实测发现】** 应用更名（D11）后覆盖升级：开始菜单目录仍叫「Steam 游戏抽签器」，里面新旧两套快捷方式并存（4 个），桌面快捷方式也还是旧名 | 安装脚本加 `UsePreviousGroup=no` + `[InstallDelete]` 清掉旧名目录与旧桌面快捷方式；桌面快捷方式任务去掉 `checkedonce`（否则升级时默认不勾，旧快捷方式被清后用户桌面上会什么都不剩）。**已实测**：干净装 1.0.0 → 覆盖装 1.0.1 后只剩一个新名目录（2 个快捷方式）+ 新名桌面快捷方式，配置零改动（AC-56） |
| 20 | 发布当天的联网复测跑不通：`live_api` 报 `network`，本机到 Steam 全线 502/503/504 | **非程序缺陷**：同一时刻 `api.github.com` 经同一路径返回 200，而 `api.steampowered.com` / `store.steampowered.com` / `steamcommunity.com` 分别返回 504 / 503 / 502（代理直连两种方式都一样），属本机网络到 Steam 的链路问题。程序侧如实报错、未误判为证书问题，也未重试到失控（详见 9.15） |

---

## 4. 产出物与校验值

**已发布 v1.0.1**（对应 [Release v1.0.1](https://github.com/collinszheng/SteamGamePicker/releases/tag/v1.0.1)）：

| 产出物 | 路径 | 大小 | SHA256 |
| :--- | :--- | ---: | :--- |
| 可执行文件 | `SteamGamePicker\dist\SteamGamePicker.exe` | 20,051,708 | `4E8A2C41E337F52FB6C30C88335556201A3703313FEBFB700823C3317043E6B5` |
| 安装包 | `SteamGamePicker\dist\SteamGamePicker_Setup.exe` | 21,841,800 | `D18DBF2333485C989D2CB098A63F54635C43803560E3B262BBB73338CEE04561` |

> 校验方式：`Get-FileHash <文件> -Algorithm SHA256`，或 `certutil -hashfile <文件> SHA256`。
> 安装包内含的 exe 与上表第一行是同一个文件（同一份 PyInstaller 产物）。
> exe 文件属性：产品名 `Steam Game Picker`、版本 `1.0.1.0`、版权 `Copyright (c) 2026 collinszheng. MIT License.`。
> **发布后回验**：从 `https://github.com/collinszheng/SteamGamePicker/releases/latest/download/SteamGamePicker_Setup.exe`
> 下载实际产物，大小 21,841,800 字节、SHA256 与上表**完全一致**（同时等于本机 `dist` 里的文件），
> `releases/latest` 已指向 v1.0.1。

**历史产物（已被 v1.0.1 取代，请勿再分发）**：

| 版本 | 说明 | 安装包 SHA256 |
| :--- | :--- | :--- |
| v1.0.0 | 界面为 v1.5 Steam 风格、中文单语、旧名「Steam 游戏抽签器」、旧图标、exe 无版本资源 | `6A327017696FD52434EB2BA783C1A297E6C7CDEDE43FC38C1AD66A1FD4D26214` |
| v1.0.0 之前 | `22A340CA…`（v1.5 可执行文件）、`1B8CF558…`、`29CFC2DD…`（v1.3）、`DD6664DD…`（v1.4） | — |

> 界面截图存于 `docs/evidence/ui-steam-theme-loaded.png`（已加载未抽签）、
> `docs/evidence/ui-steam-theme-result.png`（抽签后含详情卡片）与
> `docs/evidence/ui-english.png`（英文界面）；三张图均为 **1000×750 物理像素**
> （本机 125% 缩放，已按 DPI 换算，见第 3 节缺陷 17）。
> 图标见 `docs/evidence/icon-preview.png` 与 `docs/evidence/icon-256.png`。

打包产物自检（`SteamGamePicker.exe --selftest --live --report <文件>`）：

**v1.0.1 已安装版本**（`docs/evidence/selftest-live-v101-installed.json`）——
组件全部可用；`live_api` 报 `network`，原因是发布当天本机到 Steam 全线 502/503/504
（同一时刻 GitHub 可达），非程序问题，详见 9.15：

```json
{ "version": "1.0.1", "frozen": true, "config_corrupted": false, "has_api_key": true,
  "snapshot_games": 61, "cache_bytes": 242803, "tk_ok": true, "pillow_ok": true,
  "requests_ok": true, "truststore_ok": true, "live_api": "network", "startup_ms": 29697.4 }
```

v1.5 产物（**联网校验通过**，`docs/evidence/selftest-live-v15.json`）：

```json
{ "version": "1.0.0", "frozen": true, "tk_ok": true, "pillow_ok": true,
  "requests_ok": true, "truststore_ok": true, "live_api": "ok", "startup_ms": 786.9 }
```

v1.7 打包产物（未联网环境，`docs/evidence/selftest-packaged-v17.json`）：

```json
{ "version": "1.0.0", "frozen": true, "tk_ok": true, "pillow_ok": true, "requests_ok": true,
  "truststore_ok": true, "snapshot_games": 61, "live_api": "skipped(no STEAM_API_KEY)",
  "startup_ms": 59.6 }
```

安装 / 卸载实测（v1.0.1，本机）：`install_exit=0` → 覆盖升级 v1.0.0 正常 →
`--selftest` 通过 → `uninstall_exit=0` → 配置目录保留、注册表与快捷方式清空（详见 9.15）。

冷启动外部计时：首次 2.98 s（杀软扫描新文件），此后稳定 2.01 / 2.01 / 2.03 s → **未超过 3 s 阈值，按 PRD 7.3 维持 onefile**。

---

## 5. 复现命令

```powershell
# 全量测试（477 项）
cd SteamGamePicker
python -m pytest

# 真实接口校验（详情接口无需 Key；账号矩阵需先设置环境变量）
$env:SGP_SYSTEM_TRUST='1'          # 本机存在 TLS 中间层时启用系统信任库
$env:STEAM_API_KEY='<你的Key>'
$env:SGP_PUBLIC_ID='<公开账号SteamID64>'
$env:SGP_PRIVATE_ID='<非公开账号SteamID64>'
$env:SGP_EMPTY_ID='<无游戏账号SteamID64>'
$env:SGP_INVALID_KEY='<无效Key>'
python tools\live_check.py

# 重新打包
python -m PyInstaller packaging\SteamGamePicker.spec --noconfirm
ISCC.exe packaging\installer.iss    # ISCC 位于 Inno Setup 安装目录

# 打包产物自检
.\dist\SteamGamePicker.exe --selftest --report .\dist\selftest.json
```

---

## 6. 待补测清单（需要你提供资源）

| 项 | 需要的资源 | 步骤 |
| :--- | :--- | :--- |
| v1.0.1 联网复测 | 本机网络到 Steam 恢复可达 | `set STEAM_API_KEY=<你的Key>`、`set SGP_PUBLIC_ID=<公开账号SteamID64>`，然后 `python tools\live_check.py`；退出码 0 即通过。发布当天 Steam 全线 502/503/504，未能重跑 |
| AC-06 / AC-07 / AC-08 剩余场景 | 一个**资料非公开**的账号、一个**无游戏**的账号、一个**无效 Key** | `set SGP_PRIVATE_ID=<非公开账号>`、`set SGP_EMPTY_ID=<空库账号>`、`set SGP_INVALID_KEY=<无效Key>`，然后 `python tools\live_check.py`；退出码 0 即通过 |
| AC-36 控件重叠目视 | 你本人 | 把窗口拖到 640×480，确认无重叠与关键信息截断 |
| AC-43 干净 Win10 | 一台未装过本程序的 Win10 64 位机器 | 运行安装包 → 启动 → 抽签 → 卸载 |
| 代码签名（可选） | 代码签名证书 | 用 `signtool` 对 exe 与安装包签名，可消除 SmartScreen 警告 |

> 已用你提供的账号完成的实测：`https://steamcommunity.com/profiles/<SteamID64>`
> → 解析成功 → **61 款游戏、0.55 秒**；「从未玩过」11 款、「玩得很少」16 款、
> 两者并存 27 款（并集语义正确）。

## 7. 持续集成证据

工作流：`.github/workflows/tests.yml`（Windows / Python 3.12，push 与 PR 触发）。

| 运行 | 提交 | 结果 | 说明 |
| :--- | :--- | :--- | :--- |
| [35431875836](https://github.com/collinszheng/SteamGamePicker/actions/runs/35431875836) | `7433a73` | ❌ 失败 | **有价值的一次失败**：运行器时区为 UTC，暴露了两条把时区写死的断言（期望 `09-19 15:04`，实际 `09-19 07:04`） |
| [35431965371](https://github.com/collinszheng/SteamGamePicker/actions/runs/35431965371) | `7c1a4fa` | ✅ 通过 | 修复后全部步骤 success；**自检步骤也成功**，说明该运行器具备可用 Tk 桌面会话，界面与布局测试确实在其中执行 |
| [35432298290](https://github.com/collinszheng/SteamGamePicker/actions/runs/35432298290) | `9c4b424` | ✅ 通过 | 应用更名提交（D11）后仍全绿 |
| [35432859899](https://github.com/collinszheng/SteamGamePicker/actions/runs/35432859899) | `4eba840` | ✅ 通过 | 中英双语 + 英文 README（D12 / AC-53 / AC-54）通过。**这条最有说服力**：本机开发环境的默认时区与语言都是中文，i18n 的"英文界面不得残留中文"与文档互链检查在**另一台干净机器**上同样成立 |
| [35432941223](https://github.com/collinszheng/SteamGamePicker/actions/runs/35432941223) | `ccde79a` | ✅ 通过 | 验收记录补记（纯文档） |
| [35433584762](https://github.com/collinszheng/SteamGamePicker/actions/runs/35433584762) | `9cb7721` | ✅ 通过 | 图标重做（D13 / AC-55）通过，461 项。图标测试按像素采样判定配色与小尺寸简化，因此在**另一台机器**上重跑同样成立 |
| [35433711249](https://github.com/collinszheng/SteamGamePicker/actions/runs/35433711249) | `75860d7` | ✅ 通过 | 打包链路实测与产物校验值补记（纯文档） |
| [35433762566](https://github.com/collinszheng/SteamGamePicker/actions/runs/35433762566) | `f1bc515` | ✅ 通过 | CI 运行记录补记（纯文档） |
| [35434319033](https://github.com/collinszheng/SteamGamePicker/actions/runs/35434319033) | `9a7b77b` | ✅ 通过 | **v1.0.1 发布提交**：477 项全绿，与本地结果一致 |

这次失败带来的实际收获（已记入 CHANGELOG）：

1. **产品行为修正**：`display_time` 原来直接格式化"写入时的偏移"，把配置目录拷到别的时区
   （PRD 6.5 明确支持的迁移场景）后"上次更新"会与本地时钟不一致；现统一按当前本地时区换算。
2. **测试时区无关化**：期望值改为由同一瞬间在本地时区推导，并新增两条与时区无关的不变量测试
   （ISO 往返保持瞬间不变；同一瞬间的不同偏移写法必须显示为同一个本地时间）。
3. 验证了测试套件可以在**另一台干净机器**上完整跑通（windows-latest），
   并且 405 → 407 → 438 → 461 → 477 项用例在两台机器、两个时区、两种界面语言下结果一致。

> 注意：这次 CI 通过的是**测试套件**，不等同于 AC-43（在干净 Win10/Win11 上安装并走完主流程），
> 该项仍列在第 6 节待补测。
