# Fall 2023 原始资料索引

使用 [manifest.json](./manifest.json) 中的每讲 Slides 与视频地址。2023 年有 **18 个主题课（对应 18 份 Slides）与 1 次 Midterm Review（录播第 14 段）**；因此播放列表的第 15–19 段对应官方课程 L14–L18。

## 数据可信度

- **Slides：** 18 份 PDF 均通过 Stanford Fall 2023 官方页面逐讲核对过下载地址。
- **视频：** 18 个主题讲次的 YouTube ID 已与 2023 课程资源索引对应；期中复习另列。
- **Transcript：** Lecture 1、Lecture 2 与 Lecture 3 已阅读用户提供的无时间戳英文自动转写，并与各自课程主题对照，但仍未逐句与原始音频核对；**没有在公开仓库上传第三方全文**。其他讲次尚未取得可靠的完整 Transcript。详见 [L01 来源核验](./lecture-01-audit.md)、[L02 来源核验](./lecture-02-audit.md) 与 [L03 来源核验](./lecture-03-audit.md)。
- **教材章节：** L01、L02、L03 已整合 Transcript 与 Slides 写成完整原创教材，仍未逐句校对原音；L07、L10 为自包含初稿。状态字段区分文字稿阅读、课件核查与音频核对。

## 本地字幕建议格式

```text
sources/raw/
  01.en.vtt
  02.en.vtt
  ...
  18.en.vtt
  review.en.vtt
```

`raw/` 与 `packets/` 已加入忽略规则，避免把完整第三方字幕、PDF 内容直接公开到 GitHub。字幕文件仅供合法个人学习和事实核对，教材正文采用原创表述并标注原始来源。

## 具体怎么做？

阅读 [tools/README.md](../tools/README.md)：从公开视频尝试下载字幕，与 Slides PDF 组合成带页码、带时间戳的本地检索材料。文字稿如果存在缺漏或自动字幕术语误识别，应回放视频核对，而不是假定它准确。

[Stanford Fall 2023 官方课程表](https://gfxcourses.stanford.edu/cs149/fall23/)。
