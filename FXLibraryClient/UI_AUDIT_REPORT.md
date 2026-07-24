# FXLibraryClient · UI 与产品自审报告（2026-07-22 刷新版）

> 审查视角：**资深前端工程师**（UI 实现 / 视觉一致性 / 性能 / 可访问性）+ **产品经理**（完整体验走查 / 流程断点 / 功能缺口 / 名实相符）。
> 审查对象：当前工作区代码（`app/ui/main_window.py` 2566 行、`asset_grid.py`、`style.py`、`i18n.py`、`settings_dialog.py`、`tag_manager_dialog.py`、`log_panel.py`），并对照 `prototype/fx_library_prototype.html` 与原 `UE5特效库管理软件_设计文档.md`。
> 方法：逐文件精读 + 对照原型/设计文档 + 实际运行 `tools/qa_audit.py`。

## 0. 结论前置（先说最要命的）

我**实际跑了一遍现有 QA 套件**：`python tools/qa_audit.py` → **EXIT 0，全部 PASS，零 FAIL**（回归断言含 `primary_solid_no_accent2`、`batchbtnprimary_solid_no_accent2`、`inspexp_tokenized`、`uncat_notag_reachable`、`card_chrome_no_inline` 等）。

也就是说，上一版 `UI_AUDIT_REPORT.md`（7/22 早些时候）里列出的 **P0 白字看不清、P0 设置改主题语言不生效、P1 未分类/未标签不可达** 等，**在代码层面都已修复**。那份报告已过时，不应再作为依据。

但作为产品 + 前端视角重新走查，**当前版本存在 3 个致命级的"功能名实不符 / 头牌功能缺失"问题**，以及一批一致性、性能、死代码问题。下面按严重度列出。

---

## 一、产品经理视角：功能 / 流程断点

### 🔴 P0-A — 「导出 .fxpack」在 UI 里完全不存在（头牌 MVP 变单向）

设计文档把"一键导出 .fxpack（递归依赖 + manifest + 缩略图）"列为 MVP 第 2 件事，且是整个产品的**核心价值主张**（跨项目不丢依赖迁移）。
代码现状：
- 能**导入** `.fxpack`：检查器 `导入 .fxpack` 按钮 → `_import` → `_import_from_fxpack`（解包 + 写库）。✅
- 能**复制** `.uasset` 到某个 Content 文件夹：工具栏/检查器"导出到 UE 工程" → `_export_selected` → `ue_export.export_to_ue_project`（纯文件 copy）。⚠️ 不是 .fxpack。
- **没有任何按钮 / 菜单 / 右键项能"把选中特效打包成 .fxpack"**。全代码 grep `export_to_ue_project` / `.fxpack` 写动作，只有"解包导入"和"复制到文件夹"，**没有"打包导出"**。

后果：用户只能**消费**别人给的包，永远**产不出**自己的包。产品的"库 / 复用 / 社区分享"飞轮从第一步就断了。这与设计文档 §8.2 MVP 第 2 条直接矛盾。

### 🔴 P0-B — 「资产健康扫描」完全未接入 UI（头牌模块 E 死了）

设计文档模块 E（缺失依赖 / 重复资产 / 超 GPU 预算 / 变粉检测）是被反复强调的"易出彩"卖点。
代码现状：
- 桥脚本 `bridge/fx_health.py` 存在；DB 有 `health` 字段（`database.py:32`）；`set_health()` 方法存在；`i18n.py` 有 `health_check`/`health_scan`/`health_ok`/`hp_ok` 等十几个字符串；`models.py` 有 `health` 字段。
- **但 `main_window.py` 里没有任何触发它的入口**：工具栏无"体检"按钮、菜单无该项、检查器无"健康"行（`_build_inspector` 只建了 类型/标签/评分/备注 四行，`_show_inspector` 也从不动 `health` 字段）。grep `set_health` 仅命中 `database.py` 定义，从无调用。
- 结果：`health` 数据永远停在默认 `"ok"`，用户**永远看不到任何健康信息**，模块 E 对终端用户等于不存在。

### 🔴 P0-C — "播放 / 真实渲染缩略图"名实不符 + UE 渲染路径是死代码

设计文档模块 B 的 Tier2「代表性格值帧（UE 离屏渲染）」是"更好看的缩略图"卖点；Tier1 是引擎缓存静态图。
代码现状（**已逐行验证**）：
- 右键"读取粒子缩略图 / Generate playing thumbnail" → `_gen_playing_thumb` → `_gen_embedded_thumb`：**只做纯 Python 读取 .uasset 内嵌的静态缩略图（tier 1）或生成占位图（tier 4）**。它**从不启动 UE**。
- 真正会拉起 UE 渲染的 `_auto_render_thumbs`（`main_window.py:1944`）**全代码只有定义、零调用**——grep 仅命中其定义行与 QA 里的 monkeypatch。换言之，Tier2"UE 渲染"这条路径**从 UI 永远不可达**。
- 但 i18n / 弹窗文本反复承诺"生成**播放**缩略图""**UE 渲染真实**缩略图""优先尝试真实**播放帧**；失败提示还写"UE 渲染失败，已生成本地占位"。用户点下去拿到的是一张静态内嵌图，体验与文案严重不符。

### 🟠 P1-D — 「导出到 UE 工程」名实不符

按钮 `insp_exp` 文案"⤓ 导出到 UE 工程"，但底层 `ue_export.export_to_ue_project` 只是把 `.uasset` 文件**复制**进用户选的 Content 文件夹。它不会把资产注册进实时 UE 工程。连 `ue_not_configured` 警告都自承"will NOT import into a live UE project"。
问题：文案暗示"导入进引擎"，实际是"拷文件到目录"。叠加 P0-A（根本产不出 .fxpack），整个"导出"叙事是自相矛盾的。

### 🟠 P1-E — 日志 Dock 标题自相矛盾

- `_build_ui`（`main_window.py:448`）建 dock 时标题 = `tr("ue_bridge_log")` → "UE 桥日志"。
- `_retranslate_ui`（`:1356`）里却写 `self.log_dock.setWindowTitle(tr("activity_log"))` → "活动日志"。
结果：**初次启动叫"UE 桥日志"，一旦切一次语言就叫"活动日志"**。同一面板两个名字。

### 🟠 P1-F — 检查器不显示 health（数据有、UI 没有行）

见 P0-B：`health` 字段在库里，但检查器四行（类型/标签/评分/备注）里**没有"健康"行**，用户无从看到。

### 🟠 P1-G — 两个"设置"入口行为分歧

- 库菜单 `_show_library_menu` → `_open_settings`（`:585`）：保存后只刷新 UE 状态 + 套用主题/语言，**不重开 DB**。
- 齿轮 `btn_settings` → `_settings`（`:2152`）：保存后若 `library_dir` 变了会 `_open_db()` 重开库。
后果：从库菜单改了"库文件夹"路径，**库不会切换**（DB 没重开），用户以为改了其实没生效。两处应合并为同一实现。

### 🟠 P1-H — 「收藏」视图里取消收藏 → 网格/检查器状态不同步

`_insp_toggle_fav`（`:1752`）切换 `favorite` 后调 `_apply_filters()`。若当前在 `fav` 视图，该资产会从网格被移除，但 `_current_asset` 仍指向它、检查器仍展示它。直到下次筛选才一致。属于"界面说一套、数据另一套"。

### 🟡 P2-I — 死 i18n 字符串（健康排序/筛选）

`i18n.py` 定义了 `f_health`("全部状态")、`s_health`("健康度")、`insp_health`("健康")，但：
- 排序 combobox（`_build_main_area`）只加了 name/type/date/size/rating/random，**没有"健康度"项**；
- 筛选 combobox 也没有健康筛选；
- `_apply_grid_filters` / `_apply_sort` 都不处理 health。
→ 这三个键是**永远用不到的死字符串**（且 `insp_health` 连检查器都没渲染，见 P1-F）。

---

## 二、资深前端视角：UI 实现 / 一致性 / 性能

### 🟠 P1-J — 侧栏上方约 200px 空白死区（旧报告 P2 仍在）

`_build_sidebar` 里上方 `splitter.setSizes([200, 320])`，但上部 scroll 里现在**只剩「未分类 / 未标签」两个短按钮 + `addStretch(1)`**（`main_window.py:516-518`）。结果侧栏上半区一大片空白、下面文件夹区被挤到 320px。视觉空洞、浪费纵向空间。建议：去掉这条垂直 splitter，把快捷筛选与文件夹树合并到一个自然流里，或把"未分类/未标签"做成更紧凑的入口。

### 🟠 P1-K — 搜索无防抖 + 每次输入全量重建卡片网格（规模性能隐患）

`_apply_filters` 每次搜索框 `textChanged` 都会 `grid.set_assets(...)` —— 而 `set_assets` 会 `deleteLater` 旧卡片、重新 `AssetGrid` 全部卡片（含重画缩略图占位）。库里上千个资产时，**每敲一个字符就整网格重建一次**，无虚拟化、无 debounce，输入会明显卡顿。QA 只测了 4 张卡片所以看不出。建议：加 150–250ms 输入防抖 + 只更新可见卡片 / 引入卡片复用或虚拟化。

### 🟡 P2-L — 资产不可重命名

资产名直接取自文件名，全 UI 无"重命名"入口（右键、检查器、菜单均无）。设计文档与旧审计都提过，至今缺失。对"整理素材库"是高频刚需。

### 🟡 P2-M — 两套菜单/弹窗仍用内联 QSS（与全局 token 化纪律不一致）

应用已在 Round 7/8 把侧栏、卡片、按钮全部收归 `style.py` 全局 token，但仍有散落内联：
- 右键菜单 `_on_asset_context`（`:2207`）、文件夹树右键 `_on_folder_tree_context`（`:694`）、库菜单 `_show_library_menu`（`:694`）都现场拼 `tok[...]` 内联 `setStyleSheet`；
- `LightboxDialog`（`:66`）遮罩硬编码 `rgba(10,37,64,.55)`，未按主题 token；
- `ThumbResultDialog` / `RenderProgressDialog` 的 `btn` 也内联写死 `accent` 底色。
这些不是 bug（菜单每次打开重建、能跟随当前主题），但与"单一 token 真源"的工程纪律不一致，主题扩展时易再次踩坑。

### 🟡 P2-N — content header 的 sel_hint 常驻显示

原型里 `.sel-hint{display:none}` 且 `body.select-mode` 才显示；实际 `sel_hint_lbl`（`:928`）**始终可见**，哪怕没在选。在窄窗下和标题/视图分段挤在同一行，浪费标题行空间。建议默认隐藏，进入选择态再显示。

### 🟡 P2-O — 回收站 / 空视图下 sel_hint 文案误导

`_on_selection_changed` 在回收站视图会强制显示 batchbar（为露出"清空回收站"）。此时 `sel_hint` 仍显示"选择模式：点击卡片批量选择"，与回收站语境不符。

### 🟡 P2-P — 两个 settings 打开器代码重复

`_settings` 与 `_open_settings` 大量重复逻辑，应合并为一个 `_open_settings(trigger_reopen_db=True)` 之类，避免再次分歧（见 P1-G）。

### 🟢 已验证"没问题"的点（避免重复劳动）

为防止旧报告误导，以下旧问题**已确认修复**，无需再报：
- 主按钮白字对比度（#primary / #batchbtnprimary / #inspexp 均已深靛 solid token，`qa_audit` 三个 `*_solid_no_accent2` 全 PASS）。
- 设置里改主题/语言即时生效（`_open_settings` 现在会 `_apply_theme` / `_set_language`）。
- 未分类 / 未标签 入口已恢复（`_nav_map` + `_set_view`）。
- 主题切换强制 re-polish（`_apply_theme` 的 `setStyleSheet("")` 往返 + 遍历 topLevelWidgets unpolish/polish）。
- 卡片 chrome、侧栏组件、tooltip 全局 token 化，无内联残留；focus ring 可见；type 渐变可区分。
- QA 套件 100% 通过。

---

## 三、对照原型 / 设计文档的范围偏差（PM 须知）

 shipped 产品与 `prototype/fx_library_prototype.html`、`设计文档.md` 相比，被**有意砍掉或尚未做**的部分，作为 PM 应心里有数：
- 原型侧栏有 **Tags 筛选区 + 智能文件夹(Smart Folders) + 管理区**，当前版本**全部移除**（只剩 库名 / 未分类 / 未标签 / 文件夹 / 回收站）。标签只能在点开资产后在检查器里增删，不能做"按标签筛选"。
- 原型 header 有 **项目 pill + 渲染源 pill**（毛玻璃质感），当前版本去掉了（与"无插件纯客户端"架构一致，但产品叙事要相应调整）。
- 设计文档的 **社区市场、版本时间线、性能档位标注、缩略图 AB 对比、跨版本兼容提示** 等增长特性均未在 UI 出现（属 roadmap，非回归，但"产品≠原型"要先对齐预期）。

---

## 四、优先级清单（修复顺序建议）

| 级 | 问题 | 位置 | 修复方向 |
|---|---|---|---|
| **P0** | 导出 .fxpack 完全缺失（只能导入不能产出） | 全 UI 无入口 | 工具栏/检查器加"导出为 .fxpack"（递归依赖+manifest+缩略图） |
| **P0** | 资产健康扫描未接入 UI（模块 E 死） | 无任何按钮/检查器行 | 工具栏加"体检"，结果用可点击报告 + 检查器加"健康"行 |
| **P0** | "播放/真实渲染缩略图"名实不符 + UE 渲染路径死代码 | `main_window.py:1944` `_auto_render_thumbs` 零调用 | 要么接上 UE 渲染入口，要么把文案改为"读取内嵌静态缩略图"并删死代码 |
| **P1** | "导出到 UE 工程"名实不符（实为复制文件） | `_export_selected` / `ue_export` | 改名"复制到 Content 文件夹"，或补真正 import 逻辑 |
| **P1** | 日志 Dock 标题自相矛盾 | `:448` vs `:1356` | 统一为一个 i18n 键 |
| **P1** | 检查器无 health 行 | `_build_inspector` | 加健康行（依赖 P0-B） |
| **P1** | 两个设置入口行为分歧（改库目录不重开 DB） | `:585` vs `:2152` | 合并为同一实现，保存后统一 `_open_db` |
| **P1** | 收藏视图取消收藏后 grid/inspector 不同步 | `:1752` | 切换后若 `_current_asset` 被过滤掉则清空检查器 |
| **P1** | 侧栏上方 ~200px 空白死区 | `:516-518, :551` | 合并快捷筛选与文件夹树 / 去掉垂直 splitter |
| **P1** | 搜索无防抖 + 整网格重建（规模卡顿） | `:1398` / `asset_grid.set_assets` | 输入防抖 + 卡片复用/虚拟化 |
| **P2** | 资产不可重命名 | 全 UI 无入口 | 检查器/右键加重命名 |
| **P2** | 死 i18n（health 排序/筛选/检查器键） | `i18n.py` | 接上功能或删键 |
| **P2** | 菜单/弹窗散落内联 QSS | `:2207,:694,:66` 等 | 收归 style.py token（与全局纪律一致） |
| **P2** | sel_hint 常驻/回收站下误导 | `:928` | 仅选择态显示；回收站换文案 |

---

## 五、一句话总结

代码工程质量很高（QA 100% 通过、主题/对比度/内联 QSS 旧债基本清干净），**纯视觉与基础交互已经过关**。但站在产品角度，**"能产出的核心闭环"有缺口**：头牌的"导出 .fxpack"和"健康扫描"都没接进 UI，缩略图功能文案承诺了 UE 真实渲染却只做了静态读取——这些会让用户觉得"东西看着漂亮，但关键事干不了 / 名不副实"。建议**优先把 P0-A/B/C 三条接上**，产品才算自洽。
