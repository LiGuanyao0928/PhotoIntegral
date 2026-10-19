# PhotoIntegral：iPhone 相册整理工具

按日期、地点、类型、人物、事件自动分相簿，找出重复、相似照片和大文件，也支持自己写规则。
**只建相簿或复制文件，不会删除任何照片。**「待清理」里的照片由你自己确认后再删。

## 用什么办法操作 iPhone 相册？

| 办法 | 能做什么 | 缺点 | 结论 |
|---|---|---|---|
| **Mac 照片 App + iCloud 照片**（本工具默认） | 直接读 Mac 上的照片图库（含地名、人物、场景识别），在照片 App 里建相簿，**自动同步回 iPhone** | 需要 Mac，并开启 iCloud 照片 | ✅ 推荐 |
| **数据线导出到文件夹**（Windows / Linux / Mac 都行） | 用「照片」App、Windows 照片或 Image Capture 导出照片，本工具按方案归档到电脑文件夹 | 结果在电脑上，不会改回 iPhone 的相簿 | ✅ 适合备份归档、腾空间 |
| iPhone 镜像（iPhone Mirroring）+ 模拟点击 | 理论上什么都能点 | 很慢（几千张要点几个小时），界面一变就失效，点错可能误删，镜像时手机必须锁屏 | ❌ 不推荐 |
| 自己写 iOS App（PhotoKit） | 直接在手机上建相簿 | 要 Xcode、开发者账号，免费签名 7 天过期 | 以后可以做 |
| 快捷指令 | 能做简单的「把截图加到某相簿」 | 规则表达能力很弱，大图库很慢 | 只适合小需求 |

所以不需要 iPhone 镜像：照片本来就在 iCloud 里，在 Mac 上整理图库，iPhone 上的相簿会自动跟着变。

## 安装

```bash
pip install -e .              # 基础功能（文件夹模式）
pip install -e '.[macos]'     # Mac 照片图库模式（osxphotos + photoscript）
pip install -e '.[heic]'      # 文件夹模式下读取 HEIC 照片的 EXIF
```

Mac 首次运行时，系统会请求访问「照片」和控制「照片」App 的权限，请在
「系统设置 → 隐私与安全性」里允许你的终端。

## 快速开始

```bash
photointegral wizard          # 交互式向导：选来源、勾选方案、预览、执行
```

或者分步来（推荐，先看计划再执行）：

```bash
photointegral list                                  # 查看所有方案和选项

# Mac 图库：生成计划，只预览不改动
photointegral plan --preset basic -o plan.json
# 确认后执行：在照片 App 的「PhotoIntegral」文件夹下建相簿，会同步到 iPhone
photointegral apply plan.json

# 文件夹模式：导出的 iPhone 照片 → 按方案复制到新文件夹
photointegral run --source folder --path ~/Pictures/iPhone导出 \
    --preset cleanup --dest ~/Pictures/整理后 --mode copy
```

## 整理方案

预设（`--preset`）：

| 预设 | 内容 |
|---|---|
| `basic` | 按月份 + 按类型 |
| `timeline` | 按年 / 月 + 事件 |
| `travel` | 按地点 + 事件 |
| `cleanup` | 重复 + 相似 + 大文件 + 旧截图（只归类到「待清理」，不删除） |
| `full` | 日期、地点、类型、人物、设备、事件、重复、大文件 |

单个方案（`-s 名字:选项=值,...`，可以重复写多个，也能和预设叠加）：

| 方案 | 说明 | 常用选项 |
|---|---|---|
| `date` | 按年 / 月 / 日 / 季节 | `granularity=year\|month\|day\|season`，`nested=false` 平铺 |
| `location` | 按国家 / 城市（Mac 图库有地名；文件夹模式按 GPS 网格） | `level=country\|city`，`include_unknown=true` |
| `media_type` | 截图、视频、实况、自拍、连拍、人像、全景、收藏 | `types=screenshot\|video\|selfie` |
| `people` | 按人物（需要在照片 App 里给人物命名） | `min_count=3` |
| `events` | 时间连续的照片聚成一次活动 / 旅行 | `gap_hours=8`，`min_photos=15` |
| `camera` | 按拍摄设备，区分出微信 / 保存的图片 | `unknown_name=保存的图片` |
| `duplicates` | 完全相同的重复照片，每组保留最好的一张 | `include_kept=true` |
| `similar` | 相似照片（连拍、多次拍同一场景） | `threshold=6`，`window_minutes=10` |
| `large` | 大文件、长视频 | `min_mb=50`，`long_video_seconds=180` |
| `screenshots` | 旧截图 | `older_than_days=30` |

每个方案都可以用 `prefix=` 改顶层文件夹名，例如 `-s location:level=country,prefix=足迹`。

## 自定义规则

写一个 YAML 配置，参考 [`examples/custom.yaml`](examples/custom.yaml)：

```yaml
preset: basic
strategies:
  - {name: events, min_photos: 30}
rules:
  - album: "旅行/{year} {country}"
    when: {all: [{field: country, op: exists}, {field: country, op: ne, value: 中国}]}
  - album: "家人/{year}"
    when: {any: [{field: persons, op: contains, value: 妈妈}, {field: persons, op: contains, value: 爸爸}]}
```

```bash
photointegral plan -c my.yaml -o plan.json
```

## 安全性

- `plan` 只读，不做任何改动；`apply` / `run` 执行前会列出计划并要你确认（`-y` 跳过确认，`--dry-run` 只预演）。
- Mac 模式只新建相簿、往相簿里加照片。相簿只是引用，删掉相簿不会删照片；重复执行也不会重复添加。
- 文件夹模式默认 `copy`，原文件不动。`move` 会先把文件放进所有相簿，全部成功后才删除原文件。

## 开发

```bash
python -m unittest discover -s tests -t .
```

代码结构：`sources/`（读取照片）→ `strategies.py` / `rules.py`（分组方案）→ `plan.py`（计划）→ `sinks/`（执行）。
新增方案：在 `strategies.py` 里写一个 `Strategy` 子类并加上 `@register`。
