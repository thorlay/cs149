# Lecture 08 来源核验记录（公开版）

**教材：** [第八章：数据并行思维](../textbook/08-data-parallel-thinking.md)

**来源：** [官方课程页](https://gfxcourses.stanford.edu/cs149/fall23/lecture/dataparallel/) · [51 页课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/dataparallel/08_dataparallel.pdf) · [录像](https://www.youtube.com/watch?v=Ba3TqxSgnTk)

## 阅读范围

用户提供的英文自动文字稿从开场序列模型到 Thrust/Spark 总结，全文已阅读；无时间码，含术语误识别和听不清，未逐句核验原音。文字稿明确把直方图细节留作课后材料，教材将其标为课件补充。

PDF 共 51 页，全部文字结构已核对；视觉抽查第 11、15、16、17、20、23、32、46、49 页，未逐页视觉复核。

| 页码 | 主题 | 原创教材处理 |
| --- | --- | --- |
| 2–9 | 数据并行、序列、Map | 区分纯函数条件、数学抽象与语言容器/执行策略 |
| 10–11 | Fold 与并行摘要 | 给出单位元、种子只算一次、摘要兼容规则 |
| 12–17 | Scan 与两种算法 | 独立算例、树含义、非二次幂补齐、精确结合次数、左右次序 |
| 18–25 | CPU/SIMD/GPU 分层 | 真实 CPU 分块版本；历史 Warp 示例不当作现代正确代码 |
| 27–30 | Segmented Scan | 以结合的 (value,head) 运算构造可运行实现，解释空段缺失 |
| 31–32 | 稀疏矩阵乘向量 | 加入完整 CSR 末尾偏移与空行，修正 8x2/8x3 |
| 34–39 | Gather/Scatter、分组与筛选 | 唯一写者条件、稳定筛选、重复目标聚合与排序成本 |
| 40–46 | 粒子网格五种方案 | 半开坐标域、独立数值例子、空桶、排序 ID 与原 ID 区别 |
| 47–49 | 直方图补充 | run 长度计数，不强制 Segmented Sum；空桶与向后搜索成本 |
| 50–51 | 总结与系统联系 | 原语表达不保证整体速度或任意分布式集合的顺序契约 |

## 修正与限定

1. 课件第 4 页页脚 163860 与 80×64×32 不符，正确为 163840；不是所有 Kernel 的最低数据量门槛。
2. Map 参数能捕获共享副作用，函数签名本身不保证独立；普通 C++ transform 不保证自动并行。
3. 并行 Fold 不仅要多给 combiner，还要摘要与更新规则兼容；非单位元 seed 不能在每块重复。
4. 结合不要求交换；异或不能当作非结合反例。通用下扫采用 incoming-prefix 在左、left-total 在右。
5. Inclusive 减原数组只适用于相应可逆特例；一般用补单位元右移。
6. 倍增每轮读取旧快照；缺少读写隔离时不能靠单个轮末 Barrier 修复。
7. 第 17 页伪代码变量/幂次排版不可直接复制；程序明确空输入、单位元与非二次幂。
8. 第 20–23 页 Warp 内共享读写没有现代独立线程调度所需完整同步；复用摘要区也需要旧读取完成。未发布为可执行 CUDA。
9. 5/10/11 等算例为抽象阶段，不是 GPU 保证时钟；工作高效不自动最快。
10. SpMV 表达式末项应为 8x3 而非 8x2；给出 [6,0,4,12,54,0] 含空行数值验证。
11. 空行不能读取 end−1；heads 无法保存空段身份，需要 rowptr/偏移。
12. 分桶 start/end 预置空区间；结果区间指向排序后的 ID 表。
13. 普通直方图可用 run 长度；加权时才需要权重聚合。第 49 页向后查找总工作可摊销为 O(K)，但最长空隙增加 Span，不误报为必然 O(K²)。
14. 不把离散访问与 Page Fault 混为一谈，也不把比较排序当作线性免费步骤。

## 一手参考

- [Blelloch 原作者报告记录](https://www.cs.cmu.edu/afs/cs.cmu.edu/project/scandal/public/papers/CMU-CS-90-190.html)：Prefix Sums and Their Applications，CMU-CS-90-190，1990。
- [NVIDIA GPU Gems Scan 章节](https://developer.nvidia.com/gpugems/gpugems3/part-vi-gpu-computing/chapter-39-parallel-prefix-sum-scan-cuda)：历史教学参考，不复用图片或代码。
- [NVIDIA Volta 调优指南](https://docs.nvidia.com/cuda/volta-tuning-guide/index.html)：同步与独立线程调度边界。
- [CUB DeviceScan](https://nvidia.github.io/cccl/unstable/cub/api/structcub_1_1DeviceScan.html)：结合且可非交换的操作、实现及版本边界；链接为开发版，不将其写成所有已发布版本的保证。
- [Thrust API 索引](https://nvidia.github.io/cccl/unstable/thrust/api/index.html)：原语延伸入口，未运行。

## 实际核验

| 程序 | 测试 | 结果 |
| --- | --- | --- |
| primitives.py | 340 组整数/字符串 Scan、Reduce | 与顺序参考一致；操作计数/轮数通过 |
| primitives.py | 200 组固定种子应用流水线 | 三种 Compaction 谓词、分段、分桶与加权聚合通过 |
| primitives.py | 100 组随机 CSR SpMV 与固定空行示例 | 与稠密乘法一致，非法输入检查通过 |
| chunk_scan.cpp | macOS ARM64、Apple Clang 16、C++17 O2 | 220 组整数/字符串、非整除/空区间通过 |
| chunk_scan.cpp ThreadSanitizer | 同一 220 组 | 通过，无竞争报告 |

未运行 GPU Scan、Thrust/CUB、分布式系统或性能 Benchmark。Python 顺序模拟算法阶段，不能代替设备同步验证；C++ 只保证本次测试路径，不证明全部调度。原始字幕、官方 PDF、临时渲染与构建产物保留仓库外，只公开原创教材与代码及来源链接。
