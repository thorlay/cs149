# Lecture 03：延迟、带宽与 ISPC

配套教材：[第三章](../../textbook/03-multicore-ispc.md)。本目录的程序是独立编写的教学实验，不是官方作业答案。

## 1. Python 手算模型

只需要 Python 3 标准库，从仓库根目录运行：

```bash
python3 labs/lecture03/models.py
```

验证 C=3、L=12 时 1/2/5/8 线程的算术忙碌率为 20%/40%/100%/100%；验证交错和连续分块对任意小规模的索引覆盖；复算带宽上限与洗衣完成时刻。最后应显示 `all_checks=pass`。

这是简化模型，没有模拟实际 CPU、Cache 或请求队列，也不产生硬件性能测量。

## 2. ISPC 三种分配与归约

需要 C++17 工具链及 [ISPC 官方编译器](https://github.com/ispc/ispc/releases)，先确认 `ispc --version` 可用。

Apple Silicon（ARM64），从仓库根目录运行：

```bash
mkdir -p /tmp/cs149-l03-build
ispc labs/lecture03/sine.ispc --target=neon-i32x4 --arch=aarch64 -O2 \
  -h /tmp/cs149-l03-build/sine_ispc.h -o /tmp/cs149-l03-build/sine.o
c++ -O2 -std=c++17 -I/tmp/cs149-l03-build labs/lecture03/main.cpp \
  /tmp/cs149-l03-build/sine.o -o /tmp/cs149-l03-build/sine
/tmp/cs149-l03-build/sine
```

支持 AVX2 的 x86-64 机器可将 ISPC 编译步骤替换为：

```bash
ispc labs/lecture03/sine.ispc --target=avx2-i32x8 --arch=x86-64 -O2 \
  -h /tmp/cs149-l03-build/sine_ispc.h -o /tmp/cs149-l03-build/sine.o
```

不要在不匹配的架构上执行产物。编译器的 Gather/Scatter 提示用于分析分块访问，不代表实测速度差异。

程序测试交错、分块、foreach 三种写法，在 12 种输入规模下对照 `std::sin`，误差要求小于等于 1e-6；同时检查尾部保护值与跨实例归约。输入在 [−1,1]，最大规模为 1024；分块乘法使用 32-bit 下标，不适用于可能溢出的大数组。

实际验证：macOS ARM64、ISPC 1.32.0、NEON `i32x4`，输出为：

```text
gang_size=4
sizes_checked=12 variants=3 tail_guard=pass reduction=pass
max_sin_error=5.96046e-08
correct=yes
```

x86 AVX2 命令本次未在目标硬件执行。实验不包含计时，不据此宣称任何加速比。比较真实性能时遵循教材中的预热、重复测量、固定数学任务与明确内存层级的要求。
