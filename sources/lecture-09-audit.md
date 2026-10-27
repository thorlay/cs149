# Lecture 09｜来源与核验记录

核验日期：2026-10-26。配套 [第 9 章](../textbook/09-distributed-computing-spark.md) 与 [实验](../labs/lecture09/README.md)。

## 材料与覆盖范围

- [官方讲次页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/spark/)：Distributed Data-Parallel Computing Using Spark。
- [官方 PDF](https://gfxcourses.stanford.edu/cs149/fall23content/media/spark/09_spark.pdf)：57 页，全文文本已阅读；图像抽查第 7、12、29、45、47、48、50、53 页，不声称逐页图像审校。
- [公开视频](https://www.youtube.com/watch?v=jaMWmLq422U)：只作回查入口，未逐句听音频。
- 用户提供的英文无时间戳自动文字稿已完整阅读，起于 Spark/集群动机，止于窄依赖与宽依赖初步介绍。文字稿结束后的 Join/PartitionBy、完整 Lineage 恢复、COST 和生态部分在教材标为课件补充。

| 课件范围 | 教材内容 | 核验/补充 |
| --- | --- | --- |
| 1–7 | 集群动机、容量/带宽模型、消息传递 | 算例复算；区分通信协议与完整程序同步 |
| 8–14 | DFS、HDFS 与日志问题 | 数据/元数据路径、副本与故障域，非随机共享数组 |
| 15–25 | MapReduce、分组、调度、失败与慢节点 | 原创键值算例、预聚合、重复副作用边界 |
| 26–32 | 迭代与复用的动机 | 原创成本模型，不复用课件性能数字作当前结论 |
| 33–46 | RDD、延迟执行、持久化、融合与依赖 | 对照版本 API，修正有序/默认物化等误读 |
| 47–51 | Join、分区、恢复 | 课件补充；区分逻辑分区与物理位置 |
| 52–57 | 性能、COST、生态 | 课件补充；历史结果不推断当前产品排名 |

## 重点修正

1. 文字稿的单机平均 25 年、千台机器与每小时故障不相符。独立指数模型按每年 365 天计算为 219 小时；不等于数据永久丢失间隔。
2. 单机 50 MB/s、100 TB 扫描为教学数值，十进制单位；理想千机 33.333 分钟受共享出口和其他开销限制。
3. 课件网络、机架功率、历史工作集数据不称为当前硬件规格，也未复写历史价格建议。
4. HDFS 块与副本数可配置；NameNode 返回元数据，DataNode 提供数据；管线复制不等于客户端独立传每份副本。
5. 通用每键 Reducer 不必是结合的二元运算；可重排局部聚合与 Spark reduceByKey 则需要对应的结合/交换条件。
6. 分区号不是机器号；Shuffle 拉取可以与 Map 重叠，不把阶段示意图误写成完全无重叠的网络屏障。
7. 经典 Hadoop Map 中间输出通常是本地 Shuffle 文件，不能说所有中间输出均直接写 HDFS。
8. 推测执行可以有多个尝试，不杀整机；重试不能自动使外部写入恰好一次。
9. RDD 不提供通用全局顺序；逻辑不可变不自动保证用户函数纯净或外部输入稳定。
10. map/filter 可迭代器流水处理，无需每个 RDD 物化成完整数组。未 persist 不代表默认写 HDFS；persist 本身不触发全量求值。
11. 窄依赖定义从每个父分区被至多一个子分区使用来判断，不能简化成一个子分区只能有一个父来源。
12. Join 成本取决于兼容 Partitioner、实际布局和复用，partitionBy 自己可能需要 Shuffle，窄依赖不保证物理完全无通信。
13. 课件 persist(RELIABLE) 不作为可直接执行的 PySpark 接口；实际使用 setCheckpointDir/checkpoint，区分缓存、本地检查点和可靠检查点。
14. 重算范围由依赖与现存输出共同决定；Driver 崩溃不属于本章局部分区恢复保证。

## 一手补充参考

- [RDD 原始论文，NSDI 2012](https://www.usenix.org/system/files/conference/nsdi12/nsdi12-final138.pdf)：Lineage、粗粒度确定性变换与中间结果复用；未复现原论文性能实验。
- [HDFS 3.3.5 架构](https://hadoop.apache.org/docs/r3.3.5/hadoop-project-dist/hadoop-hdfs/HdfsDesign.html)：块、副本、元数据、流式访问与复制管线。
- [Spark 4.0.1 RDD 指南](https://spark.apache.org/docs/4.0.1/rdd-programming-guide.html)、[reduceByKey](https://spark.apache.org/docs/4.0.1/api/python/reference/api/pyspark.RDD.reduceByKey.html)、[checkpoint](https://spark.apache.org/docs/4.0.1/api/python/reference/api/pyspark.RDD.checkpoint.html)：版本契约及边界；另对照已安装 PySpark 4.0.1 实际执行。
- [PySpark 安装说明](https://spark.apache.org/docs/4.0.1/api/python/getting_started/install.html)：依赖核查。本文固定 4.0.1，不声明最新。
- [McSherry、Isard、Murray：Scalability! But at what COST?，HotOS 2015](https://www.usenix.org/conference/hotos15/workshop-program/presentation/mcsherry)：合理单线程基线与绝对性能。

## 实际核验

| 程序 | 环境/测试 | 结果 |
| --- | --- | --- |
| shuffle_model.py | Python 标准库；手工例、200 组固定种子随机 Shuffle | 与顺序参考一致；零和键、负贡献、空输入及预聚合记录数通过 |
| shuffle_model.py | 热键、窄/宽依赖及现存输出、扫描/故障算式 | 通过 |
| spark_lab.py | macOS ARM64、Python 3.12.14、PySpark 4.0.1、Corretto Java 17.0.10 | 全部本地检查通过，成功退出 |
| spark_lab.py | textFile/flatMap/filter/reduceByKey、空输入 | Chrome=2，Safari=2；空聚合为空 |
| spark_lab.py | lazy/persist/unpersist 受控无失败段 | 调用次数 0,12,24,24,36,36,48 |
| spark_lab.py | partitionBy、mapValues、重复键 Join | 分区放置、元数据保留、四条 Join 结果通过 |
| spark_lab.py | checkpoint、saveAsTextFile | 检查点物化与重读、输出文件内容通过 |
| spark_lab.py | local[2,2] 下任务异常注入 | 分区 1 首次失败、第二次成功，成功尝试号 [0,1,0,0]，和为 66 |

Accumulator 仅诊断受控缓存段，不承诺重试下精确业务计数。任务异常重试不是机器故障测试；本机检查点不是跨机持久性证明；没有运行多机、HDFS 高可用、Driver 崩溃、推测执行、网络性能或外部恰好一次写入实验。

原始字幕、PDF、渲染和安装环境均在公开仓库外，仅公开原创教材、实验与来源链接。状态为 self-contained draft；音频仍未逐句核验。
