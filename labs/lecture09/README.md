# Lecture 09｜Spark、Shuffle 与分区恢复实验

配套 [第 9 章自包含教材](../../textbook/09-distributed-computing-spark.md)。全部程序也完整嵌入教材，不需要打开外部课件才能理解。

## 1. 标准库成本模型

```bash
python3 labs/lecture09/shuffle_model.py
```

验证手工 Shuffle 的 8→6 条记录预聚合、200 组固定种子随机参考对照、热键、窄/宽依赖的恢复输入集合、扫描与故障算例。末行应为 `ALL MODEL CHECKS PASS`。这是顺序模型，不运行真正的网络通信或 Spark。

## 2. 真正的本地 PySpark

已验证 macOS ARM64、Python 3.12.14、PySpark 4.0.1、Amazon Corretto Java 17.0.10。先让 JAVA_HOME 指向 JDK 17 安装目录，准备 Python 3.12，然后在仓库根目录执行：

```bash
python3.12 -m venv /tmp/cs149-spark-venv
/tmp/cs149-spark-venv/bin/python -m pip install pyspark==4.0.1
java -version
/tmp/cs149-spark-venv/bin/python labs/lecture09/spark_lab.py
```

可用对应 Python 解释器的完整路径替代 python3.12。首次需下载数百 MB，固定版本用于复现。程序使用临时目录、回环地址、两个本地执行线程，结束时清理数据并停止 Spark。

| 检查 | 预期 |
| --- | --- |
| 日志解析、过滤、reduceByKey | 六条合法记录；手机 Chrome=2、Safari=2；空输入结果为空 |
| 延迟执行、缓存与释放后重算 | 无注入失败的受控段中 map 累计调用为 0,12,24,24,36,36,48 |
| partitionBy / mapValues | 八个整数键落入 key mod 3；mapValues 保留 Partitioner |
| 重复键内连接 | 2×2=4 条结果 |
| checkpoint | Action 前未物化，之后有检查点路径；释放缓存后 sum=55 |
| saveAsTextFile | part-* 文件内容与聚合小结果一致 |
| 任务重试 | 成功结果尝试号 [0,1,0,0]；总和 66 |

最后应输出 `ALL LOCAL SPARK CHECKS PASS` 并成功退出。故障测试故意让分区 1 首次尝试报 `CS149 intentional first-attempt failure`，出现对应错误栈属于预期行为；后续重试须成功，断言不满足则程序失败。

`local[2,2]` 配置本地线程数和任务失败尝试限制，不代表两台服务器。Accumulator 只用于前面无失败、可容纳缓存段的诊断，不能当作分布式重试下精确业务计数。unpersist 不是故障注入；临时目录里的 checkpoint 也不能证明跨机器耐久性。

没有验证多机网络、Executor/Driver 崩溃、HDFS、推测执行、对象存储提交或外部写入恰好一次；不报告性能加速比。
