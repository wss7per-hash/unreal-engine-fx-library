# FX Library Manager (UE 5.4)

一个 UE5 编辑器插件 + Python 脚本的 MVP 骨架，用于管理 Niagara / Cascade 粒子特效库：
查看资产、导出引擎缩略图、把特效连同依赖打包成 `.fxpack`、再把 `.fxpack` 导入另一个项目。

> 这是**设计文档落地后的第一版可运行骨架**，按 UE 5.4 编写。架构遵循「Python 编排逻辑，C++ 做引擎敏感操作」。
> 如你项目实际使用 UE 5.1，需把代码中少量 5.4 API 回退到 5.1 版本（如 `ThumbnailTools::FindCachedThumbnail` 可能换成 `FThumbnailManager::Get().GetThumbnail`，`TArray64 GetCompressed` 可能换回 `TArray GetCompressed(out)`）。

---

## 1. 安装

1. 把整个 `FXLibraryPlugin` 文件夹复制到你的项目：
   ```
   E:\uecplusplusprojects\MyProjecttest1wb\Plugins\FXLibrary\
   ```
2. 确认已启用 **Python Script Plugin**：
   `编辑 → 插件 → 脚本 → Python Editor Script Plugin` 勾选（本插件 .uplugin 已声明依赖，正常会随引擎自动启用）。
3. 右键项目 `.uproject` → **Generate Visual Studio project files**（只是生成 .sln/.vcxproj），然后在 VS 里选择 **Development Editor** 配置并生成（Build），或命令行执行 `Build.bat` 的 `Development Editor` 目标。截图里显示的是 **Build（编译）** 阶段，不是 Generate。`MSB8030` 和 `SwordFormation` 那两条不是 FXLibrary 引起的。
4. 打开项目，弹窗提示启用 FXLibrary 插件 → 启用并重启编辑器。

---

## 2. 入口

- 编辑器顶部菜单栏会出现 **`FX Library`** 下拉菜单。
- 点 **`Open FX Library Window`** 打开浮动面板（4 个按钮）。
- 面板按钮与菜单项一一对应，都会启动 `Content/Python/FXLibrary/` 下的 Python 脚本。

| 按钮 / 菜单项 | 脚本 | 作用 |
|---|---|---|
| Export Selected → .fxpack | `fx_export.py` | 把 Content Browser 中选中的特效 + 递归依赖打包成 `.fxpack` |
| Import .fxpack | `fx_import.py` | 选一个 `.fxpack`，解包并按原 package 路径放回项目 |
| Generate Thumbnails (Selected) | `fx_thumbnail.py` | 导出选中资产的引擎缩略图为 PNG（Tier 1） |
| List All FX Assets | `fx_list.py` | 把所有 Niagara/Cascade 资产打印到 Output Log |

---

## 3. 典型流程

### 导出
1. 在 Content Browser 里**选中一个 Niagara System 或 Cascade Particle System**。
2. 点 `Export Selected → .fxpack`。
3. 产物：`项目/Saved/FXLibrary/<特效名>.fxpack`（一个 zip，内含 `assets/`、`preview/thumb.png`、`manifest.json`、`deps_graph.json`）。

### 导入
1. 在另一个项目的编辑器里点 `Import .fxpack`，选择上面的 `.fxpack`。
2. 资产会被放回**原始的 `/Game/...` package 路径**，内部交叉引用因此保持有效。
3. 已存在的同名资产会被跳过（不会覆盖）。

---

## 4. 缩略图说明（重要）

- Tier 1（本版默认）：直接导出的就是 UE 引擎已经渲染好的缩略图。
- **UE 5.4 的 Python 没有公开 API 读取缩略图字节**，所以这一步由 C++（`UFXLibraryBPLibrary::ExportAssetThumbnail`，用 `ThumbnailTools::FindCachedThumbnail` + `ImageWrapper`）完成，Python 只负责调用。
- **如果缩略图导出失败**：该资产可能还没生成过缩略图。**在 Content Browser 里双击打开它一次**（让它渲染出缩略图），关掉再重试即可。

---

## 5. 已知限制（本 MVP 骨架）

1. **仅支持 `/Game/` 下的资产**：磁盘路径映射假设 package 在 `Content/` 下；`/Game/Plugins/...` 或重定向资产需扩展 `package_to_content_file`。
2. **导入不做「整体挪到自定义文件夹」的重映射**：为保持引用有效，资产放回原 package 路径。把整包挪到 `/Game/ImportedFX/` 并改写所有内部引用（文档中的 Tier-2 重映射）是后续增强。
3. **跨大版本不保证**：从 UE 5.4 项目导出的 `.fxpack`，导入 5.1 或 5.5+ 项目可能因资产格式变化失败。务必在 UI 标注风险（已在文档中规划）。
4. **依赖提取靠 AssetRegistry**：极少数运行时/私有生成的依赖可能漏抓；导入后建议跑一次资产体检（模块 E，待实现）。
5. **依赖提取靠 AssetRegistry**：极少数运行时/私有生成的依赖可能漏抓；导入后建议跑一次资产体检（模块 E，待实现）。
6. **`Plugin 'SwordFormation' does not list plugin 'Niagara'...`** 这个警告来自你项目里已有的 SwordFormation 插件，不是 FXLibrary 引起的。建议给 SwordFormation 的 `.uplugin` 增加 `"Niagara"` 依赖，或恢复 SwordFormation 插件文件后重新启用它。

---

## 6. 文件结构

```
FXLibraryPlugin/
├── FXLibrary.uplugin
├── Source/FXLibrary/
│   ├── FXLibrary.Build.cs
│   ├── FXLibraryModule.h / .cpp      # 菜单 + 浮动面板 + 启动 Python
│   └── FXLibraryBPLibrary.h / .cpp   # C++ 缩略图导出（供 Python 调用）
├── Content/Python/FXLibrary/
│   ├── fx_config.py                  # 配置（引擎版本、输出目录、类名）
│   ├── fx_common.py                  # 依赖递归 / 引擎资产过滤 / 路径映射 / 版本兜底
│   ├── fx_list.py                    # 列举 FX 资产
│   ├── fx_thumbnail.py               # 导出选中缩略图
│   ├── fx_export.py                  # 打包 .fxpack
│   └── fx_import.py                  # 解包导入
└── README.md
```
