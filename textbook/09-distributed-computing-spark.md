# 第 9 章｜Spark：把数据并行扩展到会失败的机器集群

**先修知识：** 能阅读 Python 的列表、字典、函数与循环；知道文件保存在磁盘、运行中的数据保存在内存。本文会重新解释 Map、Reduce、分区、网络通信和任务调度，不要求先学 Hadoop、MPI 或数据库。

**本章目标：** 独立推演一次跨机器按键聚合；解释为什么程序能在部分任务失败后继续；区分 RDD、缓存和检查点；根据依赖与分区判断通信和重算成本；运行无需集群的纸笔模型及真正的本地 Spark 实验。

**来源状态：** 结合用户提供的第 9 讲无时间戳英文自动文字稿，以及 Fall 2023 官方 Spark 课件 57 页原创编写。文字稿在窄/宽依赖的初步讨论后结束；后面的分区 Join、完整恢复过程、COST 与生态内容依据课件补充，正文单独标明。未逐句核对视频音频。课件有历史数据、教学伪代码和接口简写，本文不把它们作为现代 API 契约。实验固定使用 PySpark 4.0.1、Python 3.12.14、Java 17，验证范围见文末。

## 9.1 从一颗芯片走到一千台机器

在一台多核计算机上，几个线程可以访问同一个数组；在独立服务器之间，一个进程的内存地址并不能指向另一台机器的数据。每台服务器有自己的操作系统、内存和存储，交换数据需要网络。把 CPU 数量增加一千倍，只解决了“有多少计算资源”，没有解决数据在哪里、谁来通信、任务怎样分配以及机器中途退出怎么办。

考虑扫描一份日志。设数据量为 D 字节，单机持续读取带宽为 B 字节/秒，机器数为 P。忽略计算与调度开销，数据恰好均匀分布，而且每台机器都能独立达到 B，理想时间为：

$$
T_1 = \frac{D}{B}, \qquad T_P = \frac{D}{PB}
$$

沿用课堂教学数值，采用十进制 TB、MB：D = 100×10¹² 字节，B = 50×10⁶ 字节/秒。单机需要 2,000,000 秒，即约 23.148 天；1,000 台机器理想情况下需要 2,000 秒，即约 33.333 分钟。这不是今天 SSD 的性能测量，也没有计入数据搬运。

如果所有机器共享的存储出口总共只有 S 字节/秒，那么读数据至少需要 D/S 秒。单机瓶颈和共享瓶颈合起来给出：

$$
T_P \geq \max\left(\frac{D}{PB},\frac{D}{S}\right)
$$

例如 S = 10 GB/s，100 TB 仍需至少 10,000 秒，约 166.7 分钟。继续增加服务器不能突破这个出口。分布式程序还要承担序列化、网络传输、调度和最慢任务等待；理想除以 P 只是一个起点。

### 故障为什么会成为日常事件？

设每台机器故障间隔服从独立指数分布，平均间隔为 M 小时。那么每台故障率为 1/M，P 台的总故障率为 P/M，下次任意一台发生故障的平均等待时间为 M/P。

课堂文字稿将“单台平均 25 年、1,000 台机器”与“每小时故障”联系起来，这组数值不相符。按每年 365 天计算：

$$
\frac{25\times365\times24}{1000}=219\ \text{小时}=9.125\ \text{天}
$$

100,000 台才降到约 2.19 小时。机架断电、网络设备故障等还可能同时影响多台机器，独立模型不能描述这些相关事件。这里算的是“有机器出故障”，不是“数据永久丢失”；后者还取决于副本布局、修复速度及共同故障范围。

结论是：随着规模增大，程序应该把局部故障当成需要处理的执行情况，而不是每遇到一次就从整个作业的开头重来。

## 9.2 三个层次：保存数据、组织计算、执行任务

可以把本章的系统拆成三个职责，它们可以部署在同一批服务器上，也可以分开：

| 层次 | 负责回答的问题 | 本章示例 |
| --- | --- | --- |
| 存储 | 文件由哪些块组成？块的副本在哪里？ | HDFS |
| 编程模型 | 程序对哪些集合做什么变换？ | MapReduce、Spark RDD |
| 执行与调度 | 哪个进程运行哪个分区？失败后重试什么？ | Driver、Executor、任务调度器 |

“Spark 会容错”不等于“原始文件可以随便丢”。计算引擎需要某些仍可用的输入，才能重新执行变换；存储系统则负责让输入不随一台机器的消失而消失。

### 分布式内存与消息传递

假设机器 A 上有整数 x，机器 B 上需要用它。A 将 x 编码成字节，通过网络发送；B 接收并还原到自己的变量 y。传输的内容是数据，不能简单把 A 的指针数值交给 B 后直接解引用。

发送和接收本身具有协议规定的先后关系，但并不自动解决程序的全部同步问题。需要匹配消息来源、标签、大小和缓冲区生命周期；如果双方都等待对方先发送，还可能死锁。MPI 提供消息传递接口，而 MapReduce/Spark 进一步表达“整批数据的处理关系”，由运行时安排大量通信。这里比较的是抽象层次，不是声称所有 MPI 系统都没有容错能力。

### HDFS 如何提供一个大文件？

用教学配置举例：文件按 256 MB 大小切块，每块保存 3 个副本。块大小和副本数都可配置；课件的 64–256 MB 是示例范围，不能当成所有部署的默认值。最后一个块可以小于指定块大小。

```text
逻辑文件 events.log
    ├── block 0 ── 副本：DataNode A、C、E
    ├── block 1 ── 副本：DataNode B、D、F
    └── block 2 ── 副本：DataNode A、D、F

客户端 ── 查询块位置 ──> NameNode（命名空间、元数据）
客户端 <── 读取数据 ───> DataNode（实际块内容）
```

NameNode 回答“到哪里读”，大文件的数据一般不经过它中转。写入可以经 DataNode 管线依次复制，不能从这个示意图推断客户端必须分别向每个副本传完整文件。

若物理总容量为 C、副本数为 r，忽略元数据、预留空间和其他开销，逻辑容量约为 C/r。例如 12 TB 原始容量做三副本，约保存 4 TB 逻辑数据。副本跨机架放置能降低一个机架故障造成全部副本一起消失的风险，但不保证抵抗所有相关故障或误删。

HDFS 面向大文件和流式读写，有写入租约等约束，不是一个支持任意位置并发修改的远程共享数组。元数据服务同样需要高可用与恢复设计；“管理节点只有一台，所以不用考虑它失败”不是正确推论。本章实验只使用本机临时文件，没有部署或验证 HDFS。

## 9.3 MapReduce 到底把什么工作交给运行时？

需求是：在网站访问日志中，按浏览器统计手机访问次数。先明确数据含义：一次日志记录算一次访问；同一用户多次访问不会自动去重；本例只把 device 恰好为 mobile 的记录算作手机，tablet 不算。真实 User-Agent 解析复杂，不能仅看到 Safari 字符串就判定手机。

用三个输入分区手工推演。为缩短表格，将浏览器 A、B、C 编码为整数 0、1、2；每条符合条件的记录产生一个键值对 `(浏览器, 1)`：

| 输入分区 | Mapper 输出 |
| --- | --- |
| P0 | (0,1), (0,1), (1,1) |
| P1 | (0,1), (2,1), (2,1) |
| P2 | (1,1), (2,1) |

Mapper 不是只能一条输入产生一条输出：过滤掉的记录产生零条，一条文本做词频统计则可能产生多个 `(单词,1)`。普通 Map 是一对一，MapReduce 的 Mapper 具有更一般的发射语义，在 Spark 中常用 flatMap 表达零到多条输出。

接下来不能直接在每台机器独立得出最终浏览器次数，因为键 0 分散在 P0 和 P1，键 1 分散在 P0 和 P2。运行时需要把同一个键的全部贡献送到一个逻辑聚合位置，这一步通常叫 **Shuffle**。

若有 R = 2 个目标分区，使用本例明确约定的规则 h(k) = k mod 2：

```text
P0: 0,0,1 ──┬──> Q0: (0,1),(0,1),(0,1),(2,1),(2,1),(2,1)
P1: 0,2,2 ──┤        分组：0 -> [1,1,1]，2 -> [1,1,1]
P2: 1,2   ──┴──> Q1: (1,1),(1,1)
                     分组：1 -> [1,1]

Reducer 对每个键求和：0 -> 3，1 -> 2，2 -> 3
```

Q0/Q1 是分区身份，不是永久绑定的机器编号。调度器可以把 Q0 的任务放到当前可用的 Executor 上；重试时还可能换位置。Hash 相同目标只说明键的归属，并不自动执行网络通信。

完整的数据流是：**读输入 → 运行 Mapper → 分区与 Shuffle → 按键分组 → 调用 Reducer → 提交输出**。有些实现还会排序以方便分组，但组内 value 的顺序通常不构成用户可依赖的契约。

### Reducer 必须满足结合律吗？

要分清两件事。通用 MapReduce 框架可以把某个键的整个 value 集合交给用户函数；该函数可以做任意每键计算，不要求所有这类用户函数本身都是一个可结合的二元运算。

但如果希望在不同机器上先计算部分摘要，然后以任意分组、任意顺序合并摘要，合并操作必须满足相应代数条件。Spark 的 reduceByKey 要求结合且交换的合并函数。整数加法满足它；减法不满足：`(8-3)-1=4`，而 `8-(3-1)=6`。浮点加法在有限精度下不严格结合，分区变化可能带来末位差异，不能要求所有运行逐位相同。

## 9.4 Shuffle 的代价与本地预聚合

直接传输上表需要发送 8 条键值记录。若每个 Mapper 先对本地相同键求和：

| 输入分区 | 本地摘要 |
| --- | --- |
| P0 | (0,2), (1,1) |
| P1 | (0,1), (2,2) |
| P2 | (1,1), (2,1) |

只需发送 6 条记录，目标端再合并得到相同结果。这个优化叫 **Map-side Combine**。假设有 M 个输入分区、K 个不同键，每个键每个分区最多发一个固定大小摘要，发出的摘要数最多为 M×K，实际还受原始记录数限制。

并不是每个聚合都能只保留一个整数。计算平均值时，应传 `(sum,count)`，最终算总 sum / 总 count。若分区 0 有 `[0,10]`、分区 1 有 `[100]`，直接平均两个局部均值会得到 `(5+100)/2=52.5`，正确全局均值是 `110/3≈36.667`。错误的摘要不能靠更多机器修复。

Shuffle 的成本也不只有网络字节：还包括对象编码、缓冲、分区、排序或哈希、磁盘 Spill、远程读取与下游等待。本地模式仍会执行 Shuffle 的组织逻辑，只是没有跨物理机器网络。

用 b 表示单条编码后记录的字节数，N 表示记录数，传输载荷可粗估为 N×b。8 亿条、每条 24 字节就是 19.2 GB，尚未计协议开销。若一次预聚合减少为 8,000 万条，载荷变为 1.92 GB；这是记录数模型，不是本章测出的真实吞吐。

### 数据倾斜：平均工作量会掩盖最慢分区

假设四个输入分区各有 100 个键 0，再各有一个不同的冷键。直接 Shuffle 后，400 个热键记录必然进入同一个目标分区。即使设置 8 个目标分区，也不会把这一个键自动拆给八个 Reducer。

如果要的是求和，预聚合可以将 400 条热记录先缩成 4 条贡献。若要返回全部原始值，输出体积本身就无法省掉。拆分热键、加盐后两级聚合等方法需要问题允许合并，并正确处理键和结果；盲目加分区数通常不能消除单键瓶颈。

## 9.5 调度：局部性、负载平衡和长尾一起考虑

调度器需要跟踪未运行、运行中与已完成的任务，并知道输入和中间输出在哪里。通常任务数多于可同时运行的核数，这样空闲槽位可以继续领取工作，不必把一整台机器的命运绑定给一个巨大任务。

如果输入块就在某台空闲机器，尽量在附近运行任务，能避免远程传输入。可如果那台机器很忙，等待本地槽位的时间可能超过远程读取的代价。局部性是带有等待成本的优化，不是“永不跨机器读数据”的正确性规则。对象存储与独立存储层也会改变这一权衡。

对于 Shuffle，已经完成的 Map 输出可以被提前拉取，网络复制能与其他 Map 任务重叠。下游某个键的完整聚合仍需收齐所需贡献；不要把教学阶段图理解为所有传输都必须等全体 Mapper 结束后才开始。

### 失败时重试哪一部分？

- 某个任务尚未完成便退出：重新调度该任务，使用仍可访问的输入。
- Map 任务完成后所在机器丢失，本地 Shuffle 文件也丢失：依赖它的下游可能触发 Map 输出重算，不能仅凭“任务曾完成”就永久跳过。
- 最终结果已经按存储协议可靠提交：结果是否仍可用取决于存储系统，而不是原 Executor 是否还活着。

不能概括为“MapReduce 每一步都把所有结果写 HDFS”。经典 Hadoop MapReduce 的 Map 中间输出通常在本地磁盘；完整作业输出才走指定输出文件系统与提交协议。多作业迭代反复读取/写入完整数据集，才是课件强调的成本来源之一。

### 慢任务与推测执行

一个任务异常缓慢时，可以在另一处运行同一任务的备用尝试，接受合适的成功结果，再取消多余尝试。这样有机会缩短最后几个拖尾任务的等待。它不是杀掉原机器，也不能保证一定更快；两个尝试可能争同一个瓶颈，而数据倾斜造成的巨量工作也会在副本上重现。

更重要的是，一个逻辑任务可以实际执行多次。如果函数给外部服务“余额加 1”或“发送一封邮件”，重试和备用尝试可能重复产生副作用。需要由业务端提供幂等键、事务或适当的提交协议。计算结果可重建，与外部操作恰好执行一次，是两种不同的保证。

## 9.6 为什么迭代算法需要比单个 MapReduce 更灵活的模型？

假设图算法执行 K 轮，每轮读取上轮状态、生成贡献并按顶点聚合。用独立作业串联，常需要把上一轮结果写入持久存储，再让下一轮读回。图结构、解析后的记录等不变信息还可能重复加载。

设一次加载与解析成本为 L，每轮真正的更新成本为 U，每轮边界的持久化额外成本为 W。一个简化模型是：

$$
T_{\mathrm{jobs}}\approx K(L+U+W)
$$

如果能保留适合复用的中间数据，加载成本可以主要支付一次：

$$
T_{\mathrm{reuse}}\approx L+KU+C_{\mathrm{cache}}+C_{\mathrm{recovery}}
$$

这里 C_cache 是缓存管理开销，C_recovery 是故障后重算等额外开销。这个式子不意味着网络 Shuffle 和每轮状态更新消失，也不意味着持久化永远不需要。它说明：把每个中间变量都表达成磁盘文件，会限制运行时优化跨步骤的数据复用。

例如教学假设 K=10，L=4 秒、U=2 秒、W=3 秒，第一种为 90 秒；若缓存及恢复额外成本合计 6 秒，第二种为 30 秒。三倍来自避免重复成本，不是每次算术突然快了三倍。若缓存溢出、数据根本不复用，收益也可能消失。

Spark RDD 的核心取舍是：把中间集合、产生它们的变换和分区依赖交给运行时，使数据可以留在合适的介质中；丢失时沿来源关系重建，而非要求每个中间集合始终有完整可靠副本。

## 9.7 RDD：集合的定义，与集合当前在哪里，是两件事

**RDD（Resilient Distributed Dataset）** 可以理解为分区组织的、逻辑上不可变的数据集合。对 RDD 做变换会定义一个新 RDD，而不是就地改写原集合。RDD 对象同时带有如何得到其分区的依赖信息。

不要因此假定它具有通用的全局顺序。特别是 Shuffle 后，分区内记录顺序不能随便依赖。需要排序时必须显式定义排序需求；本章小结果在 Driver 上 sorted 后比较，只是为了展示与测试稳定。

RDD 的逻辑不可变也不是对任意 Python 对象及用户代码的自动纯函数检查。函数可以错误地修改外部状态、读取变化的网页或使用无固定种子的随机数。重算要得到相同内容，需要稳定输入与可重现的变换。

| 概念 | 例子 | 含义 |
| --- | --- | --- |
| Transformation | map、filter、flatMap、reduceByKey | 定义新的 RDD 及其依赖 |
| Action | count、collect、take、saveAsTextFile | 请求结果，驱动相关计算 |
| Persistence | persist、cache | 请求保留求值后的分区以便复用 |
| Lineage | 输入 → 解析 → 过滤 → 按键聚合 | 重建分区所需的来源与变换关系 |

注意 reduceByKey 虽然含 reduce，仍是返回 RDD 的变换；count 返回整数，collect 返回 Driver 内的本地列表。saveAsTextFile 是动作，但主要结果写到存储，而不是返回全部数据。

### 延迟执行如何工作？

设程序定义 `lines → parsed → mobile → counts`。仅建立这些变换一般不会立即扫描全部输入。Action 要求某个输出时，运行时分析依赖并安排所需任务；少量元数据查询不等于全量数据已经计算。

```text
Driver：描述“要什么”
  原始文件 → flatMap(parse) → filter(mobile) → map(browser,1)
                                                 │
                                              Shuffle
                                                 │
                                           reduceByKey(add)
                                                 │
                                             collect()
                                                 ↓
                                      Driver 上的小结果列表
```

Driver 运行用户主程序并组织作业；Executor 运行分区任务并保存部分缓存或 Shuffle 数据。Driver 普通 Python 变量不是集群共享内存，函数闭包中的对象会随任务分发，不能让任务修改一个普通计数器就期待 Driver 自动收到累计值。

collect 会把全部结果拉到 Driver。只有确认聚合后结果足够小时才合适；大结果应写到分布式输出，或用有界抽样/聚合。take 能限制返回记录数，但若前面的 Shuffle 或过滤很昂贵，并不保证只计算极少数据。

## 9.8 缓存不是每个 RDD 自带的一份完整数组

一次 `map → filter → count` 中，Executor 可以从输入迭代器取一条，变换一条，检查一条，只累计一个局部计数，不必先建立三份完整数组。

```text
输入迭代器 ── 一条记录 ──> 解析/变换 ──> 谓词 ──> 局部计数
                                             不保留所有通过记录
```

这相当于利用生产者与消费者的局部性：前一个操作刚产生的数据，紧接着被后一个使用，减少中间内存流量。持久化边界、Shuffle 和需要看见许多记录的算子会改变执行方式，不能把所有算子都无条件合并。

用单机的 `E = D + (A+B)×C` 做一个独立算例。每个元素有三次算术运算，采用 4 字节浮点，假设每个中间数组都真正经过所计算的内存层级，忽略缓存、写分配等额外影响：

- 分三遍：每遍读两个数、写一个数，合计 9 个数，即 36 字节；算术强度为 3/36 = 1/12 FLOP/字节。
- 融为一遍：读 A、B、C、D 四个数，写 E 一个数，合计 20 字节；算术强度为 3/20 FLOP/字节。

数据流量从 36 降到 20 字节，相应强度提高 1.8 倍。若系统完全受该流量限制且其他条件不变，这是潜在收益；不是所有运行都必然加速 1.8 倍。RDD 窄依赖流水线体现同样的思想，但 PySpark 还包含 Python/JVM 边界与对象处理，不能直接套用这五个浮点数的字节数。

### persist 什么时候真正发生？

调用 persist 主要登记保留策略，不会仅因为调用它就把数据算出来。后续 Action 首次触及某分区时，才尝试计算并保留该分区；take 等动作可能只触及部分分区。

默认不持久化一个 RDD，重复动作可能重走其变换链；不能理解成 Spark 自动把每个中间 RDD 写入 HDFS。可选策略包括只放内存、内存不足则放本地磁盘，以及附加副本等。不同语言/API 的默认存储级别可能不同，示例显式指定 StorageLevel。

若多个查询共享昂贵的 mobile 过滤结果，可以在 mobile 处持久化，而不是给每个中间 RDD 都加缓存。对于内存级缓存，保不住或被逐出的分区可能需要重算；unpersist 释放保留的数据，但保留 RDD 的计算定义。后续仍能沿依赖求值。

设共有 Q 次查询，重复预处理成本为 F，每次查询分支成本为 G，建立/管理缓存额外成本为 C。在数据保得住且读缓存成本暂并入 G 的模型下，不缓存约 Q(F+G)，缓存约 F+QG+C。当 `(Q−1)F>C` 才有机会净获益。现实中还要计缓存读取、序列化、GC 与挤掉其他数据的机会成本。

## 9.9 窄依赖、宽依赖与任务边界

从一个父 RDD 到一个子 RDD 的依赖看，**窄依赖**指每个父分区至多被一个子分区使用。map、filter 的典型情况是一条分区链；一个子分区也可能依赖多个父来源，所以“每个子分区只依赖一个父分区”不是一般定义。

```text
窄依赖：                      需要重分区的宽依赖：
A0 → B0 → C0                  A0 ──┬──> B0
A1 → B1 → C1                  A1 ──┼──> B1
A2 → B2 → C2                  A2 ──┴──> B2
                              每个 A 的不同键可能去不同 B
```

宽依赖中，一个父分区可能向多个子分区提供数据。按键分组常见的情形就是每个 Map 分区都可能贡献给每个目标分区，需要 Shuffle。这里说的是分区间的依赖分布，不是某个 RDD 对象有几个父 RDD。

窄依赖常能在同一个任务里沿迭代器流水处理；Shuffle 则形成阶段边界。Spark 把一个作业中的计算切为 Stage，Stage 内运行许多处理分区的 Task。一个 Task 可以经过多个窄依赖 RDD，而不是每个 RDD 必须各启动一批独立任务。

例如有 4 个输入分区，经过 map/filter 后按键聚合成 3 个目标分区，再 collect：教学上可分成上游 4 个分区任务和下游 3 个分区任务，Shuffle 分隔阶段。真实作业还受缓存、复用和 API 实现影响；一个 Action 不等于一个 Stage，也不宜把这个例子的任务数当作所有程序的固定规律。

**文字稿范围到这里：** 用户提供的转写在介绍这两种依赖后结束。下面三节将课件余下内容补齐，并结合版本文档修正接口用法，不表示讲者已在这段文字稿中讲完。

## 9.10 课件补充：同一个 Join，分区不同，成本就不同

两个键值集合做内连接：左侧 `(k,v)` 与右侧 `(k,w)` 产生 `(k,(v,w))`。只保留两边都出现的键；如果同一键左边有 m 条、右边有 n 条，结果是 m×n 条，不会自动去重。

例如左边 `[(a,1),(a,2),(b,3)]`，右边 `[(a,x),(a,y),(c,z)]`，结果只有键 a 的四个组合：`(1,x)、(1,y)、(2,x)、(2,y)`。这也解释了为什么一个很小的键集合仍可能产生很大的 Join 输出。

若两侧使用运行时能识别的兼容分区方式，相同键已在对应分区，则可以在对应分区之间执行连接，避免为这个连接重新分配键。若分区不兼容，通常需要重新分区。关键既包括记录实际在哪里，也包括运行时是否保有正确的 Partitioner 元数据；“我人工看过键好像聚在一起”不等于引擎可以证明。

partitionBy 会按规则重新分配键值对，必要时本身就要付 Shuffle 成本。若后面只 Join 一次，把 Shuffle 从 Join 前移未必节约总成本；如果相同分区被多轮计算复用，才可能摊薄这笔投入。即使逻辑依赖是窄的，两侧分区也不保证物理同机，不能直接声称完全没有跨机通信。

对于已经分好的键值 RDD，mapValues 只改 value，能够保留 Partitioner；普通 map 可能改变键，通常不能自动保留同样的分区承诺。实验检查整数键的放置和 mapValues 的元数据保留；未将“所有 Join 都自动无 Shuffle”作为测试结论。

## 9.11 课件补充：Lineage 如何恢复丢失的分区？

假设四个输入分区 A0…A3，分别经过确定性的过滤与映射得到 C0…C3。Executor 丢失了 C2，只要 A2 仍能从可靠输入或存活副本读取，就能重新执行对应变换，生成 C2；其他 C 分区不必仅因此全部重算。

```text
可靠输入 A2 ──> 解析 B2 ──> 过滤 C2 ──> 后续消费者
                    原缓存丢失        ↑
                          在可用资源上重新求值
```

Lineage 记录的是批量变换与分区关系，不是每次“某字节写成什么”的细粒度日志。一个 map 可以描述几亿条记录的相同变换，描述本身不随每条记录增长。因此粗粒度、可重放的集合运算为低成本记录来源创造了条件。真实实现仍需维护任务状态、Shuffle 位置等，并非只保存几行用户代码就能解决所有故障。

对于宽依赖，丢失一个结果分区可能需要多个上游分区的贡献。若所需 Shuffle 输出仍存在，可以复用；若相关中间文件也丢失，才沿依赖补算相应上游。恢复范围由**依赖关系与现存数据**共同决定，既不是永远只重算一个分区，也不是每次必然重启全作业。

用纸笔比较：四个父分区均未保留可用中间输出，丢失子分区 2。窄依赖只需父分区 2；全连接式宽依赖可能需父分区 0、1、2、3。若宽依赖所需父输出中 0、1、3 还在，则需要重建的父分区仍只有 2。这是后面恢复模型的含义，模型不模拟网络和 Spark 的真实调度器。

### 什么条件会破坏“重算得到相同数据”？

输入文件被覆盖、读取实时变化的远程服务、使用当前时间生成内容，或者从外部计数器消费一次性数据，都可能使重算产生不同结果。随机化算法应明确种子及分区/记录到随机流的映射；仅给 Driver 随便设置一次随机种子并不自动保证所有重试可重现。

Executor 丢失也不同于 Driver 丢失。RDD Lineage 的常见恢复描述假设当前应用的协调与调度状态仍在；Driver 整体崩溃如何恢复、应用如何重启及输出怎样提交，需要部署与应用级机制，不能从 RDD 的名称直接推出。

### 缓存、可靠检查点与本地检查点

| 机制 | 保存什么 | 丢失后依赖什么 | 主要用途 |
| --- | --- | --- | --- |
| 普通 persist/cache | 已求值的分区，可在内存或 Executor 本地磁盘等 | 通常仍保留 Lineage，可重算 | 避免重复计算 |
| 可靠 checkpoint | 在指定检查点文件系统保存物化结果 | 依赖检查点存储的可靠性 | 截断过长 Lineage，减少恢复链 |
| localCheckpoint | 利用本地缓存等保存检查点数据 | 本地数据丢失可能无法恢复 | 用可靠性换开销；不能当作跨节点耐久副本 |

可靠 checkpoint 也不是一调用就立即完成所有 I/O。先配置检查点目录，在该 RDD 首次执行作业前标记 checkpoint，再由 Action 驱动物化；完成后可移除对原父 RDD 的依赖。通常先 persist 能避免保存检查点时再次计算。集群场景应选择所有任务可访问、可靠性符合要求的文件系统。

课件第 48、56 页写的 `persist(RELIABLE)` 是教学简写，不是本章 PySpark 4.0.1 实验使用的接口。这里实际调用的是 `SparkContext.setCheckpointDir` 和 `RDD.checkpoint`。实验写本机临时目录，只验证 API 状态和重新读取结果，不能证明机器损坏后检查点仍在。

## 9.12 课件补充：规模扩展不能替代单机效率

假设一个系统在 1 核上需要 1,000 秒，在 100 核上需要 20 秒。它相对自己的基线加速 50 倍，扩展效率 50%。但如果合理优化的单线程程序只需 8 秒，100 核系统仍更慢。

课件引用的 COST（Configuration that Outperforms a Single Thread）衡量一个系统需要多大硬件配置才能超过有竞争力的单线程实现。这里关注的是绝对完成时间及资源，而不仅是相对系统自己的低效基线扩展了几倍。不同年代的数据和软件版本不能直接当成当前 Spark 的性能排名。

对象布局、重复解析、内存复制、解释器调用、序列化以及每个小任务的固定开销，都会影响实际效率。内存里存着数据，并不意味着没有解析、反序列化或对象访问成本。缓存文本和缓存已经解析好的记录也不是同样的工作。

现代 Spark 还有 SQL、DataFrame 等结构化接口。当系统知道列类型与操作语义，便可以进一步优化数据布局、查询计划和执行。本文选择 RDD 是为了看清分区、依赖与恢复，不意味着所有结构化数据分析都应手写 Python RDD。也不能把 Spark 的所有计算路径描述成逐元素执行 Python 对象函数。

面向 AI Infrastructure，可将本章思想用于理解离线语料清洗、按文档键聚合、数据分片、重试和输出幂等。大模型同步训练中的梯度 AllReduce、参数分片、通信重叠有自己的同步和恢复条件；不能把 RDD 的局部分区重算直接套到任意训练状态。

## 9.13 无需 Spark 的完整实验：Shuffle 与恢复成本模型

以下程序只依赖 Python 3 标准库，是顺序执行的教学模型。它显式构造目标桶，并不模拟真实并发、磁盘提交或网络。固定随机种子的 200 组测试将预聚合和不预聚合的结果与顺序计数参考比较，覆盖空输入、负贡献及和为零但仍存在的键。

程序还计算扫描时间与独立故障模型，并比较现存中间输出对恢复集合的影响。文件位于 [shuffle_model.py](../labs/lecture09/shuffle_model.py)，完整内容如下，可直接保存运行：

```python
#!/usr/bin/env python3
"""Paper-scale model: deterministic shuffle, combining, skew, recovery costs."""
from collections import Counter
from fractions import Fraction
import random


def shuffle(parts, reducers, combine):
    if reducers <= 0:
        raise ValueError("reducers must be positive")
    buckets = [[] for _ in range(reducers)]
    sent = 0
    for part in parts:
        items = Counter()
        if combine:
            for key, value in part:
                items[key] += value
            records = list(items.items())
        else:
            records = part
        for key, value in records:
            # Integer keys make partition placement reproducible across processes.
            buckets[key % reducers].append((key, value))
            sent += 1
    totals = {}
    for bucket in buckets:
        local = Counter()
        for key, value in bucket:
            local[key] += value
        totals.update(local)
    return totals, sent, [len(b) for b in buckets]


def recovery_inputs(lost_children, dependencies, available_parents):
    """Parents that must be regenerated, not a real Spark scheduler."""
    needed = set()
    for child in lost_children:
        needed.update(dependencies[child])
    return needed - set(available_parents)


def main():
    parts = [[(0, 1), (0, 1), (1, 1)],
             [(0, 1), (2, 1), (2, 1)], [(1, 1), (2, 1)]]
    raw, raw_sent, raw_load = shuffle(parts, 2, False)
    combined, combined_sent, combined_load = shuffle(parts, 2, True)
    assert raw == combined == {0: 3, 1: 2, 2: 3}
    assert (raw_sent, combined_sent) == (8, 6)
    assert raw_load == [6, 2] and combined_load == [4, 2]
    print(f"shuffle: raw={raw_sent}, combined={combined_sent}, totals={raw}")

    rng = random.Random(149)
    for _ in range(200):
        records = [(rng.randrange(8), rng.randrange(-5, 6))
                   for _ in range(rng.randrange(101))]
        count = rng.randrange(1, 9)
        parts = [records[i::count] for i in range(count)]
        reference = Counter()
        for key, value in records:
            reference[key] += value
        reducers = rng.randrange(1, 10)
        direct, n1, _ = shuffle(parts, reducers, False)
        merged, n2, _ = shuffle(parts, reducers, True)
        # Keep zero totals: a present key whose sum is zero still exists.
        assert dict(reference) == direct == merged
        assert n2 <= n1
        assert sum(merged.values()) == sum(v for _, v in records)
    print("random shuffle: 200 cases PASS")

    parts = [[(0, 1)] * 100 + [(i + 1, 1)] for i in range(4)]
    _, sent, load = shuffle(parts, 8, False)
    assert sent == 404 and max(load) == 400
    _, sent_combined, _ = shuffle(parts, 8, True)
    assert sent_combined == 8
    print("skew: 400 hot-key records share one reducer; combining sends 8 records")

    narrow = {i: {i} for i in range(4)}
    wide = {i: set(range(4)) for i in range(4)}
    assert recovery_inputs({2}, narrow, set()) == {2}
    assert recovery_inputs({2}, wide, set()) == {0, 1, 2, 3}
    assert recovery_inputs({2}, wide, {0, 1, 3}) == {2}
    print("recovery model: narrow=1 parent, wide<=4 parents; reuse survives")

    serial_seconds = Fraction(100 * 10**12, 50 * 10**6)
    parallel_minutes = serial_seconds / 1000 / 60
    hours = Fraction(25 * 365 * 24, 1000)
    assert serial_seconds == 2_000_000 and hours == 219
    print(f"scan: {float(serial_seconds / 86400):.3f} days, "
          f"{float(parallel_minutes):.3f} minutes on 1000 ideal nodes")
    print(f"failure model: 25-year mean / 1000 nodes = {float(hours):.0f} hours")
    print("ALL MODEL CHECKS PASS")


if __name__ == "__main__":
    main()
```

在仓库根目录运行：

```bash
python3 labs/lecture09/shuffle_model.py
```

关键输出为 `raw=8, combined=6`、`200 cases PASS`、`25-year mean / 1000 nodes = 219 hours`，最后为 `ALL MODEL CHECKS PASS`。字典显示顺序不影响答案。模型把单条摘要与单条原始记录视为相同大小，仅统计记录数；不能用这个输出宣称实际网络流量或性能按同一比例下降。

## 9.14 真正的本地 PySpark 实验

本实验运行真实 Spark 的任务、Shuffle、缓存与检查点代码，使用本机两个线程，不需要 GPU、HDFS 或云账号。依赖安装包较大，首次安装需要下载数百 MB。下面固定 PySpark 4.0.1 以便复现，没有将其称为最新版本。

已验证环境为 macOS ARM64、Python 3.12.14、Amazon Corretto Java 17.0.10。准备好 Python 3.12 和 JDK 17，让 JAVA_HOME 指向你的 JDK 安装目录，再从仓库根目录运行：

```bash
python3.12 -m venv /tmp/cs149-spark-venv
/tmp/cs149-spark-venv/bin/python -m pip install pyspark==4.0.1
java -version
/tmp/cs149-spark-venv/bin/python labs/lecture09/spark_lab.py
```

若 Python 3.12 的程序名或位置不同，使用对应解释器的完整路径。Driver 和 Python Worker 需使用兼容解释器；程序默认将 PYSPARK_PYTHON 设为当前解释器，已有环境变量则尊重它。实验只绑定本机回环地址，将输入、输出、缓存暂存和检查点放在自动清理的临时目录。

程序检验七件事：日志过滤与聚合、延迟执行及缓存、按键分区、重复键 Join、检查点、分区输出文件、失败任务重试。完整代码也在 [spark_lab.py](../labs/lecture09/spark_lab.py)：

```python
#!/usr/bin/env python3
"""Real PySpark local RDD checks, including one deliberately retried task."""
import os
from pathlib import Path
import sys
import tempfile
from operator import add

from pyspark import SparkConf, SparkContext, StorageLevel, TaskContext


# Synthetic TSV: event ID, device, browser. Repeated IDs remain separate events.
LINES = ["1\tmobile\tsafari", "2\tdesktop\tchrome",
         "3\tmobile\tchrome", "4\tmobile\tsafari",
         "5\ttablet\tchrome", "6\tmobile\tchrome", "broken"]


def parse(line):
    fields = line.split("\t")
    if (len(fields) != 3 or not fields[0].isdigit()
            or fields[1] not in {"mobile", "desktop", "tablet"}
            or fields[2] not in {"safari", "chrome"}):
        return []
    return [(int(fields[0]), fields[1], fields[2])]


def retry_partition(index, rows):
    context = TaskContext.get()
    attempt = context.attemptNumber()
    if index == 1 and attempt == 0:
        raise RuntimeError("CS149 intentional first-attempt failure")
    # Attempt number is diagnostic metadata; the numeric subtotal is deterministic.
    yield (index, attempt, sum(rows))


def main():
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    with tempfile.TemporaryDirectory(prefix="cs149-spark-") as directory:
        root = Path(directory)
        input_file = root / "events.tsv"
        input_file.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        conf = (SparkConf().setMaster("local[2,2]")
                .setAppName("CS149 lecture09")
                .set("spark.ui.enabled", "false")
                .set("spark.ui.showConsoleProgress", "false")
                .set("spark.driver.host", "127.0.0.1")
                .set("spark.driver.bindAddress", "127.0.0.1")
                .set("spark.local.dir", str(root / "scratch")))
        sc = SparkContext(conf=conf)
        sc.setLogLevel("ERROR")
        try:
            print(f"Spark {sc.version}, Python {sys.version.split()[0]}")
            rows = sc.textFile(input_file.as_uri(), minPartitions=3).flatMap(parse)
            mobile = rows.filter(lambda row: row[1] == "mobile")
            counts = mobile.map(lambda row: (row[2], 1)).reduceByKey(add, 3)
            assert rows.count() == 6 and mobile.count() == 4
            actual = sorted(counts.collect())
            assert actual == [("chrome", 2), ("safari", 2)]
            assert sc.parallelize([], 3).map(lambda x: (x, 1)).reduceByKey(add).collect() == []
            print(f"mobile browser counts: {actual}; malformed=1; empty input PASS")

            # Diagnostic only. Transformation accumulators may overcount on retries.
            calls = sc.accumulator(0)

            def observe(value):
                calls.add(1)
                return value * 2

            doubled = sc.parallelize(range(12), 4).map(observe)
            assert calls.value == 0
            assert doubled.count() == 12 and calls.value == 12
            assert doubled.count() == 12 and calls.value == 24
            doubled.persist(StorageLevel.MEMORY_ONLY)
            assert calls.value == 24  # persist itself runs no tasks.
            assert doubled.count() == 12 and calls.value == 36
            assert doubled.count() == 12 and calls.value == 36
            doubled.unpersist(blocking=True)
            assert doubled.count() == 12 and calls.value == 48
            print("lazy/cache/recompute: observed map calls 0,12,24,24,36,36,48")

            keyed = sc.parallelize([(i, i * 10) for i in range(8)], 4).partitionBy(3)
            placement = keyed.mapPartitionsWithIndex(
                lambda index, it: [(index, key) for key, _ in it]).collect()
            assert len(placement) == 8
            assert all(index == key % 3 for index, key in placement)
            assert keyed.partitioner is not None
            assert keyed.mapValues(lambda value: value + 1).partitioner == keyed.partitioner
            print("partitionBy: 8 integer keys correctly assigned to 3 partitions")

            left = sc.parallelize([("a", 1), ("a", 2), ("b", 3)], 2)
            right = sc.parallelize([("a", "x"), ("a", "y"), ("c", "z")], 2)
            joined = sorted(left.join(right, 3).collect())
            assert joined == [("a", (1, "x")), ("a", (1, "y")),
                              ("a", (2, "x")), ("a", (2, "y"))]
            print("inner join: duplicate key produces 2 x 2 = 4 records")

            sc.setCheckpointDir((root / "checkpoint").as_uri())
            checkpointed = sc.parallelize(range(10), 3).map(lambda x: x + 1)
            checkpointed.persist(StorageLevel.MEMORY_AND_DISK)
            checkpointed.checkpoint()
            assert not checkpointed.isCheckpointed()
            assert checkpointed.count() == 10
            assert checkpointed.isCheckpointed() and checkpointed.getCheckpointFile()
            checkpointed.unpersist(blocking=True)
            assert checkpointed.sum() == 55
            print("checkpoint: materialized locally; sum remains 55 after unpersist")

            output_dir = root / "result"
            counts.saveAsTextFile(output_dir.as_uri())
            saved = sorted(line for file in output_dir.glob("part-*")
                           for line in file.read_text(encoding="utf-8").splitlines())
            assert saved == sorted(repr(pair) for pair in actual)
            print("saveAsTextFile: partition files verified in temporary directory")

            # local[2,2]: two threads; allow two attempts per task before aborting.
            recovered = sorted(sc.parallelize(range(12), 4)
                               .mapPartitionsWithIndex(retry_partition).collect())
            assert [index for index, _, _ in recovered] == list(range(4))
            assert [attempt for _, attempt, _ in recovered] == [0, 1, 0, 0]
            assert sum(subtotal for _, _, subtotal in recovered) == sum(range(12)) == 66
            print("retry: attempts [0,1,0,0], recovered sum=66")
            print("ALL LOCAL SPARK CHECKS PASS")
        finally:
            sc.stop()


if __name__ == "__main__":
    main()
```

### 怎样读实验结果？

本次真实运行得到以下关键输出，版本行之外不依赖路径、任务 ID 或文件名：

```text
mobile browser counts: [('chrome', 2), ('safari', 2)]; malformed=1; empty input PASS
lazy/cache/recompute: observed map calls 0,12,24,24,36,36,48
partitionBy: 8 integer keys correctly assigned to 3 partitions
inner join: duplicate key produces 2 x 2 = 4 records
checkpoint: materialized locally; sum remains 55 after unpersist
saveAsTextFile: partition files verified in temporary directory
retry: attempts [0,1,0,0], recovered sum=66
ALL LOCAL SPARK CHECKS PASS
```

其中 malformed=1 来自已知七行输入和六条成功解析记录的校验，不是解析器向某个共享 Python 列表写错误日志。手机 Chrome、Safari 各两次；Desktop、Tablet 与坏行均未进入手机计数。

观察 map 调用次数使用了 Accumulator。这是受控实验中的诊断：前面的缓存测试没有注入失败，数据极小且缓存可容纳。第一次 Action 从 0 增至 12，未缓存的第二次增至 24；调用 persist 仍是 24；首次缓存求值变 36，复用不增加，unpersist 后再算变 48。**不能把变换里的 Accumulator 当成在任意失败、推测执行和重算下都精确的业务计数**。正确聚合结果应像浏览器次数那样通过 RDD 数据流返回。

`local[2,2]` 中第一个 2 是本地执行线程数，第二个 2 是任务允许失败尝试的限制。故障函数只让分区 1 的第零次尝试抛异常，下一次尝试成功；日志会出现带 `CS149 intentional first-attempt failure` 的错误栈，这是预期的故障注入。最终四个成功结果的尝试编号为 `[0,1,0,0]`，数据和仍是 0…11 的和 66。编号只用作诊断，数据计算本身保持确定。

unpersist 测试的是主动释放缓存后的重算，不能称为 Executor 故障测试。重试实验测的是任务抛异常后的重试，没有杀掉独立服务器。检查点实验只证明在当前本机文件系统仍可访问时可读回结果。输出保存后检查各 `part-*` 文件，说明结果分片写出；没有测试对象存储提交、推测执行下外部数据库恰好一次写入或 Driver 崩溃恢复。

## 9.15 从源码走到工程判断

拿到一个 Spark 程序，可以沿数据路径问以下问题，而不只数调用了多少个 API：

1. **输入与定义：** 每条记录是什么？坏记录、重复记录、空分区如何处理？输入重读时是否稳定？
2. **分区与流量：** 哪个算子改变键的归属？有多少记录、多少字节跨过 Shuffle？预聚合是否保持正确语义？
3. **关键路径：** 是否有热键或过大的分区？最慢任务是数据量问题、资源竞争，还是异常机器？
4. **复用与边界：** 哪个中间结果被多次使用？缓存是否真的被 Action 物化？它挤掉了什么？
5. **失败与提交：** 哪些输入仍可靠可读？丢失的数据能重建到哪一层？任务重试会不会重复写外部系统？
6. **测量：** 与合理的单机实现相比是否更快？启动、解析和第一次缓存的成本是否与后续查询分开记录？

这些问题没有统一的“多开机器”答案。数据量小、计算简单时，本机流式程序可能已经足够；数据和工作集确实超过一台机器，或者需要共享集群资源及恢复机制时，分布式系统的组织能力才成为重要收益。

## 9.16 练习与参考答案

### 练习

1. 100 TB 数据、单节点 50 MB/s，500 台理想节点扫描需要多少分钟？若共享出口为 10 GB/s，能达到这个时间吗？
2. 独立指数故障假设下，单机平均 25 年、10,000 台机器，下次任一节点故障的平均间隔是多少小时？这是否等于数据丢失间隔？
3. 30 TB 原始空间采用三副本，忽略其他开销可保存多少逻辑数据？三个副本都在一个机架的弱点是什么？
4. 本章三个输入分区使用 `key mod 2`，为什么 Q0 接收六条、Q1 接收两条？目标分区数增至 4 后，键 0 会被拆散吗？
5. 为什么求和可本地预聚合，求平均不能直接合并“局部平均”？给出正确摘要。
6. 对输入 `[8,3,1]` 使用减法做任意树形聚合，列出两个不同结果。为什么不能用于 reduceByKey？
7. 同一个键在 Join 左边出现 3 次，右边出现 4 次，内连接产生几条？若右边没有该键呢？
8. 定义 map/filter、调用 persist 后，没有 Action，能否断定所有分区已经驻留内存？
9. 一个 RDD 上运行两次 count，第二次一定从缓存读取吗？
10. “窄依赖就是每个子分区恰好只依赖一个父分区”错在哪里？兼容分区的两路 Join 能说明什么？
11. 四个父分区都能向每个子分区贡献记录，子分区 2 丢失。若父输出 0、1、3 仍在，需要重建哪些父输出？
12. 把缓存设为 MEMORY_AND_DISK，是否自动获得跨机器可靠检查点？
13. 每个任务把外部账户余额加 1，失败重试后余额可能怎样？如何让重复请求不重复计费？
14. 十亿条输入按键聚合后仍有两亿个键，collect 为什么危险？输出可以放在哪里？
15. 四个输入分区、三个 Shuffle 目标分区，map/filter/reduceByKey/collect 的简化两阶段图有多少分区任务？为什么不是每个 RDD 独立一阶段？
16. 系统 1 核 800 秒，80 核 20 秒；优化单线程基线为 12 秒。相对自身加速比和效率是多少？超过好基线了吗？
17. 本地实验的错误日志出现一次，最终 ALL LOCAL SPARK CHECKS PASS。如何判断是预期注入而不是忽略了错误？
18. 如果 map 中读取“当前时间”，一周后丢失缓存重算，RDD 不可变能保证记录内容一样吗？
19. 修改实验的 mobile 判定使 tablet 也算移动设备，应怎样改变期望结果？从纸笔算例先给出答案，再修改并运行代码。
20. 两次查询共享的预处理 F=7 秒，查询分支各 G=2 秒，缓存额外成本 C=9 秒。简化模型下值得缓存吗？三次查询呢？

### 参考答案

1. 2,000,000/500/60≈66.667 分钟。10 GB/s 共享出口仍需约 166.667 分钟，无法达到前者。
2. 25×365×24/10,000=21.9 小时。不是数据丢失频率；副本、相关故障和修复过程都会改变丢失风险。
3. 约 10 TB。一个机架级故障可能同时让三个副本不可用。
4. 键 0、2 都进 Q0，总计 3+3=6；键 1 的两条进 Q1。增加目标分区不会把同一个键拆散。
5. 求和的部分和可再求和；平均需 `(sum,count)` 并分别相加，最后做一次除法。
6. `(8−3)−1=4`，`8−(3−1)=6`。减法不结合，也不交换，不符合接口要求。
7. 12 条；右边没有则 0 条。它不是按唯一键自动选一个值。
8. 不能。persist 只登记策略，Action 才触发相关分区求值，而且不一定触及所有分区。
9. 不一定。没有持久化、缓存被逐出或丢失等情况均可能重算。
10. 应从父分区被哪些子分区使用来定义，至多一个子分区是窄依赖条件。两路 Join 的子分区可以各读取两侧对应父分区，因此多个父来源不自动等于宽依赖。
11. 需要重建父输出 2，再与现存 0、1、3 的所需贡献合并；不是无条件重建全部父分区。
12. 不会。本地磁盘仍可能随 Executor 所在机器丢失；可靠检查点要使用独立接口和合适的持久存储。
13. 一个逻辑操作可能多次加钱。业务端可按唯一请求键在事务中去重，或用业务适用的幂等写入与提交机制。
14. 聚合结果仍巨大，传输及 Driver 内存都可能承受不了。可用分布式文件输出或数据库写入流程，并考虑提交语义。
15. 简化为上游 4 个、下游 3 个，共 7 个分区任务。map/filter 等窄链能融合在同一任务中；实际执行还受 API 和缓存等影响。
16. 自身加速比 40，效率 40/80=50%。20 秒仍慢于 12 秒，没有超过该单线程基线。
17. 检查异常为指定的故障注入文本，成功结果中分区 1 尝试号为 1，其余为 0，总和为 66，且程序退出成功；只看到错误栈或只看到一句成功文字都不足以单独解释恢复过程。
18. 不能。逻辑不可变不阻止用户代码依赖变化的外部状态，重放结果取决于输入和变换能否复现。
19. Tablet 的一条 Chrome 加入，Chrome=3、Safari=2，总数=5；六条解析成功记录的总数不变。还需同步更新测试的 mobile.count() 与预期聚合结果。
20. 两次不缓存为 18 秒，缓存为 7+4+9=20 秒，不合算；三次不缓存为 27 秒，缓存为 7+6+9=22 秒。这里只比较给定模型，不包含其他内存和读取成本。

## 9.17 来源、版本与验证边界

- [Stanford 第 9 讲页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/spark/)及 [57 页官方课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/spark/09_spark.pdf)：本章主线，包括集群、MapReduce、RDD、依赖、恢复与 COST；历史硬件与性能数据不作为当前基准。用户自动文字稿已完整阅读，没有与音频逐句核验。
- [RDD 原始论文，NSDI 2012](https://www.usenix.org/system/files/conference/nsdi12/nsdi12-final138.pdf)：粗粒度变换、Lineage、复用与容错的研究来源；未复现论文基准。
- [HDFS 3.3.5 架构文档](https://hadoop.apache.org/docs/r3.3.5/hadoop-project-dist/hadoop-hdfs/HdfsDesign.html)：命名空间、块、副本与读写路径。本文不把其版本默认值推广至所有系统。
- [Spark 4.0.1 RDD 编程指南](https://spark.apache.org/docs/4.0.1/rdd-programming-guide.html)：版本核查入口；API 具体行为以对应方法文档与本次运行共同核验。
- [reduceByKey 方法](https://spark.apache.org/docs/4.0.1/api/python/reference/api/pyspark.RDD.reduceByKey.html)：结合/交换约束、本地合并与分区。
- [checkpoint 方法](https://spark.apache.org/docs/4.0.1/api/python/reference/api/pyspark.RDD.checkpoint.html)：调用时机、持久存储目录、父依赖与建议先持久化。
- [PySpark 4.0.1 安装说明](https://spark.apache.org/docs/4.0.1/api/python/getting_started/install.html)：依赖入口；本次实际选择 Python 3.12 与 JDK 17，不声称测试了全部受支持组合。
- [Scalability! But at what COST?，HotOS 2015](https://www.usenix.org/conference/hotos15/workshop-program/presentation/mcsherry)：绝对性能与合理单线程基线的比较标准；未把旧图表转载为现代性能结论。
- [本讲来源核验记录](../sources/lecture-09-audit.md)记录课件范围、修正和实测结果；[实验目录](../labs/lecture09/README.md)提供复现入口。

本文的数值模型、原创例子与实验是独立编写的教学内容。200 组 Shuffle 模型和全部本地 Spark 检查已通过；未测多机 Executor 丢失、机架故障、HDFS 高可用、网络性能、推测执行、对象存储输出提交、Driver 重启恢复或生产级恰好一次外部写入。教材状态为 self-contained draft，音频核验是独立的未完成项。
