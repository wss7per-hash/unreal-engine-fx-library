# Unreal Engine FX Library

UE5 特效（Niagara / Cascade 粒子）资源管理与迁移工具集。把散落在多个 UE5 项目里的特效资产**集中浏览、预览、打标签、体检、打包迁移**，让素材库从「一个个打开项目翻」变成「一个库随时搜」。

> 日常使用**完全不依赖 UE 编辑器**：扫描、缩略图（纯 Python 读取 `.uasset` 内嵌图 + 占位图）、标签、检索、`.fxpack` 导入导出全在本地完成。
> UE 仅在「真实渲染播放帧缩略图」时作为**可选增强**（无头桥）。

## 仓库结构

```
unreal-engine-fx-library/
├── FXLibraryClient/              # 桌面端（Python + PySide6），本仓库主程序
│   ├── app/                     # 应用逻辑：scanner / models / workers / ui
│   ├── bridge/                  # 无头 UE 桥脚本（fx_export / fx_import / fx_health ...）
│   ├── app/resources/           # 图标、logo
│   ├── tools/                   # qa_audit.py 等质量校验
│   ├── main.py                  # 入口
│   ├── FXLibraryClient.spec     # PyInstaller 打包配置
│   ├── run.bat / build_exe.bat # 运行 / 打包
│   └── README.md
├── FXLibraryPlugin/             # UE5 编辑器插件（C++ + Python），可选增强
│   ├── Source/FXLibrary/        # C++：菜单 + 面板 + 缩略图导出
│   ├── Content/Python/FXLibrary/# Python：导出 / 导入 / 列举 / 缩略图
│   └── README.md
├── UE5特效库管理软件_设计文档.md   # 完整设计文档（PRD + 架构 + 数据模型）
└── FXLibraryClient_软件介绍与使用手册.html  # 图文并茂的软件介绍与使用手册
```

## 快速开始（桌面端）

**本机直接运行**：双击 `FXLibraryClient/run.bat`（使用已配置好 PySide6 的托管 Python）。

**任意机器（Python 3.11+）**：
```bash
cd FXLibraryClient
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py
```

**打包独立 exe**（无需 Python 环境）：
```bash
cd FXLibraryClient
build_exe.bat        # 产物：dist/FXLibraryClient/FXLibraryClient.exe
```

首次运行：打开 **设置**，把 **UnrealEditor.exe** 指向你的安装（例如
`C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe`），
并设置 **库文件夹** 用于存放导出的 `.fxpack` 与缩略图。然后 **打开项目 → 选择 .uproject → 刷新列表**。

## 核心功能

| 模块 | 说明 |
|---|---|
| 扫描索引 | 递归扫描 UE5 项目，列出全部 Niagara / Cascade 特效，建立本地 SQLite 索引 |
| 三档缩略图 | Tier1 内嵌图（读 `.uasset`）→ Tier2 占位图（Pillow 生成）→ Tier3 手动图；可选 Tier0 真实引擎渲染 |
| 三种视图 | 图标 / 列表 / 详细，支持小中大三档卡片尺寸 |
| 搜索与筛选 | 按名称搜索，按类型 / 来源 / 评分 / 标签筛选，多条件排序 |
| 标签·收藏·评分·备注 | 为资产打标签、加星收藏、打分、写备注，全部本地持久化 |
| 虚拟文件夹 | 在库内自由分组资产，不影响原项目文件 |
| 导出 / 导入 `.fxpack` | 把特效连同**递归依赖**打包成自包含 zip（含 manifest + 缩略图），导入时按原 package 路径放回，内部引用不失效 |
| 资产体检 | 扫描缺失依赖、重复资产、孤立资产，给出健康报告 |
| 回收站（数据安全） | 软删除 + **路径安全围栏**：引用模式下永不触碰原项目文件，可一键还原 |

> `.fxpack` 只是 `zip + manifest.json`，里面是 100% 标准的 `.uasset`。导入后引擎看到的就是原生 `.uasset`，没有引入任何新资产格式。

## 无头 UE 桥（可选）

需要真实渲染缩略图或做引擎敏感操作时，客户端会**无头启动 UnrealEditor**（`-ExecutePythonScript`）运行 `bridge/` 下的脚本，完成后退出。桥脚本通过 JSON 与客户端通信。详见 `FXLibraryClient/README.md` 与 `FXLibraryPlugin/README.md`。

## 系统要求

- Windows
- Unreal Engine 5.3+（仅真实渲染缩略图 / 引擎敏感操作需要；纯浏览检索不需要）
- Python 3.11+（仅源码运行 / 打包时需要）

## 文档

- `UE5特效库管理软件_设计文档.md` — 完整设计文档
- `FXLibraryClient_软件介绍与使用手册.html` — 图文并茂的软件介绍与使用手册（浏览器直接打开）
- `FXLibraryClient/README.md` / `FXLibraryPlugin/README.md` — 各子项目说明

## License

见各子项目文件。
