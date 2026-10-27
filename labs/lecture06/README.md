# Lecture 06：局部性、通信与竞争实验

配套教材：[第六章](../../textbook/06-locality-communication-contention.md)。只需 Python 3 标准库与 C++17 编译器，无须 GPU 或集群。

## Python 确定性模型

从仓库根目录运行：

```bash
python3 labs/lecture06/models.py
```

覆盖 8 个发送优先死锁与 8 个奇偶会合协议、54 组逐颜色 Halo 校验、条带/二维块总载荷、输入专用 LRU 模型、融合逻辑流量和 Roofline 算术。

固定结果包括：

```text
halo: cases=54 every_color=pass boundaries=pass payload=pass
partition N=1024 P=16: strip=30720 tile=12288 values/exchange
LRU input-only N=30: row=720 strip_width4=480 misses
fusion: 36 -> 20 logical bytes/element; ideal bandwidth-only speedup=1.8
all_checks=pass
```

完整输出见教材。Halo 采用独立私有列表与显式快照复制，每个颜色阶段与串行红黑参考解逐项比较；N=1/2/3/5/8/11、P=1…min(N,4)、轮数 1/2/7，覆盖非整除分区。P>N 不在定义范围。

LRU 模型仅统计双缓冲五点模板输入，6 个全相联缓存行、每行 4 项、N=30、物理行宽 32，输出假定独立缓存。这是教学模型，不是硬件实测或对课件图中计数的精确模拟。

程序没有创建真实进程、运行 MPI、实现异步网络或停止归约协议；检测会合死锁不会真的挂住程序。

## C++17 正确性与可选计时

```bash
mkdir -p /tmp/cs149-l06-build
c++ -O2 -ffp-contract=off -std=c++17 -Wall -Wextra -pedantic \
  labs/lecture06/locality.cpp -o /tmp/cs149-l06-build/locality
/tmp/cs149-l06-build/locality
```

固定输出：

```text
fusion_cases=9 stencil_cases=90 boundaries=pass correct=yes
```

融合覆盖空数组及 8 种非空长度，并与独立 double 算术比较；分块是双缓冲 Jacobi，N=1/2/3/7/16/31、Tile=1/2/3/8/64、轮数=1/2/7，逐轮比较参考输出与边界。它不同于 Python 中的红黑算法，不把两个算法互相比时间。

本次在 macOS ARM64、Apple Clang 16 实际编译运行。地址与未定义行为检测也已运行，无报告：

```bash
c++ -O1 -g -ffp-contract=off -std=c++17 -fsanitize=address,undefined \
  labs/lecture06/locality.cpp -o /tmp/cs149-l06-build/locality-sanitize
/tmp/cs149-l06-build/locality-sanitize
```

可选融合计时：

```bash
/tmp/cs149-l06-build/locality --bench 4194304
```

8 个 float 数组共约 128 MiB；先预热，各版本各 7 次，交替顺序，报告中位数；每次计时后读取完整输出校验和。分配、初始化和校验不计时。默认元素数也是 4194304，可指定 1…16777216。

一次本机观察：三次扫描 1.547 ms，融合 0.788 ms，约 1.96 倍；不规定其他运行必须达到此结果。程序中的 `logical_GB_per_s` 来自 36N/t 与 20N/t，**不是实测 DRAM 带宽**，也未证明输入来自 DRAM。理论流量比 1.8 需要相同有效带宽等前提，不能用它要求实测必须一致。

没有测空间分块的速度、实际 Cache Miss、NUMA 或多机通信；不提供 GPU、MPI 或异步通信的性能结论。所有源代码完整收录于教材，构建产物放在仓库外。
