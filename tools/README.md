# 课程资料准备工具（本地执行）

目标：把一讲的 **Stanford Slides PDF** 和 **已合法获取的 YouTube VTT 字幕** 处理成带页码、带时间戳的本地参考包。**工具只整理来源，不自动创作中文教材；教材仍需结合准确材料进行原创编写与事实校对。**

## 1. 获取资料

### Slides

从 [官方课表](https://gfxcourses.stanford.edu/cs149/fall23/) 选择 Lecture，点击 Download slides as PDF，保存为 `sources/raw/01.pdf` 等。

### Transcript

YouTube 可点击视频简介中的 Show transcript 阅读（以视频实际可用性为准）。若本地装有 `yt-dlp`，可以尝试导出自动英文字幕（不下载视频）：

```bash
yt-dlp --skip-download --write-auto-subs --write-subs \
  --sub-langs 'en.*' --sub-format vtt \
  -o 'lecture01.%(ext)s' 'https://www.youtube.com/watch?v=V1tINV2-9p4'
```

根据导出的文件名，将得到的 `.vtt` 放在 `sources/raw/01.en.vtt`。自动字幕可能不存在，或因平台限制无法下载；遇到此情况不要伪造 Transcript。

**请勿将整份字幕和 Slides PDF 直接推送到公开 GitHub 仓库。**

## 2. 把两种资料整理成带来源的本地 Markdown

依赖 Python 3.10+；解析 PDF 还需要 `pip install pymupdf`。

```bash
cd cs149
python tools/prepare_materials.py \
  --pdf sources/raw/01.pdf \
  --vtt sources/raw/01.en.vtt \
  --output sources/packets/01-materials.md
```

也可以只提供 `--pdf` 或 `--vtt`，工具会明确标记缺失的来源。它不会联网、不会偷偷拉取资料。

## 3. 编写与检查

1. 先阅读 PDF 的目录、关键图页、推导；自动抽取文字不可靠时查看原始图片；
2. 对照 Transcript 的时间码核查教授讲的额外例子、修正和限定条件；
3. 写原创教材，不复刻 Slides 的全部文字或字幕；
4. 给重点段落注明 PDF 页码、视频时间点；
5. 说明哪些内容是课程原意、哪些是作者加入的现代工程延伸；
6. 用独立代码与小题目验证计算结论，再发布到 `textbook/`；
7. 更新 `sources/manifest.json` 的来源核验状态（只有**确实逐段核对完整字幕**才能设为 true）。

## 版权与质量

- 公开项目仅发布原创教材、来源链接、必要的少量引述；原 Slides、录像、字幕的版权归各版权方。
- 不要把字幕自动转写的 `silk` 误当成 Cilk，也不要把 `SIMD`、`SIMT`、`ILP` 混为一谈。
- 对无法验证的细节，写“未核实”，不要填入臆测时间戳。
