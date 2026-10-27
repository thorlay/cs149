# Lecture 04：并行编程基础实验

配套教材：[第四章](../../textbook/04-parallel-programming-basics.md)。程序为独立教学示例，不是通用数值求解库。

## Python 语义模型

只依赖 Python 3 标准库，从仓库根目录运行：

```bash
python3 labs/lecture04/models.py
```

输出包括 Amdahl 数字、2×2 网格的按行扫描/Jacobi/红黑一轮结果、部分和 55，以及 `all_checks=pass`。这验证算法语义和算术，不测线程性能。

## C++17 完整红黑求解器

```bash
mkdir -p /tmp/cs149-l04-build
c++ -O2 -std=c++17 -pthread labs/lecture04/redblack.cpp \
  -o /tmp/cs149-l04-build/redblack
/tmp/cs149-l04-build/redblack
```

已在 macOS ARM64、Apple Clang 16 实测：

```text
cases=100 fixed_sweeps=pass convergence=pass boundaries=pass
worst_residual=8.65416e-09
correct=yes
```

N=1/2/3/5/8，Worker=1/2/4/8，每组测试 1/2/7/31 次固定红黑扫描及一次阈值停止，共 100 组。内部 N×N、固定外圈、上边界为 1，其余边界（除上边角）为 0；更新是自身旧值加四邻居后乘 0.2。N=0 不属于这个求解器的定义范围。

完整算法每轮包含红阶段、黑阶段和停止决定发布。三次 Barrier 分别用于这些依赖，不是直接复制课件只展示红阶段的三次 Barrier。

使用 C++17 mutex/condition_variable/generation 构造可复用 Barrier；无须安装 C++20 Barrier。线程数大于行数时，空区间线程仍必须参加屏障。

可选 ThreadSanitizer：

```bash
c++ -O1 -g -std=c++17 -pthread -fsanitize=thread labs/lecture04/redblack.cpp \
  -o /tmp/cs149-l04-build/redblack-tsan
/tmp/cs149-l04-build/redblack-tsan
```

本次同样通过且无竞争报告；这不替代所有调度的形式化证明。小网格用于正确性检查，不据此宣称加速比。

## 可选 ISPC Gang 与归约

先准备 [官方 ISPC 编译器](https://github.com/ispc/ispc/releases)，以下假定 `ispc` 已在 PATH。Apple Silicon：

```bash
mkdir -p /tmp/cs149-l04-build
ispc labs/lecture04/basics.ispc --arch=aarch64 --target=neon-i32x4 -O2 \
  -h /tmp/cs149-l04-build/basics_ispc.h -o /tmp/cs149-l04-build/basics.o
c++ -O2 -std=c++17 -I/tmp/cs149-l04-build labs/lecture04/ispc_main.cpp \
  /tmp/cs149-l04-build/basics.o -o /tmp/cs149-l04-build/ispc_basics
/tmp/cs149-l04-build/ispc_basics
```

输出：

```text
gang_size=4 sizes_checked=9 absolute_repeat=pass reduction=pass tail=pass
```

将目标换为 `neon-i32x8` 后重新编译并链接，gang_size=8，其他检查同样通过。本次两个目标均用 ISPC 1.32.0 在 macOS ARM64 运行；不提供未验证的 x86 运行结论。

绝对值复制程序需要 2n 个输出位置；主机程序另加尾部哨兵检查。归约输入为小规模的 1/4 倍数，求和可以精确比较。Scatter 提示反映输出跨步访问，不代表结果不正确。
