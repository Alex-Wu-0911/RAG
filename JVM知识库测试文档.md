# JVM 内存、垃圾回收与故障排查

适用范围：Java SE 21 的 JVM 基本概念及 HotSpot 常用诊断方式。具体垃圾收集器的行为依赖 JVM 实现和配置。

## 一、JVM 运行时内存区域

JVM 运行时数据区域包括程序计数器、Java 虚拟机栈、堆、方法区，以及实现可能提供的本地方法栈。

堆由线程共享，是类实例和数组分配存储空间的运行时区域，其自动内存管理由垃圾收集器完成。JVM 规范不要求使用某一种具体回收算法。

每个线程拥有自己的 Java 虚拟机栈。方法调用会创建栈帧，用于保存局部变量、操作数栈以及方法执行所需的信息。栈帧随方法调用创建，并在方法结束后销毁。

方法区由线程共享，保存运行时常量池、字段与方法信息以及方法代码等类级别结构。运行时常量池是方法区的一部分。方法区是规范中的逻辑概念，不能直接等同于某个 JVM 实现中的一块固定物理内存。

程序计数器属于线程私有区域，执行非 native 方法时记录当前 JVM 指令的位置；执行 native 方法时，其值未定义。

栈深度超过允许范围可能导致 StackOverflowError；无法满足堆空间分配要求时可能出现 OutOfMemoryError。它们并不是同一种内存问题。

参考：[JVM 规范：运行时数据区域](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5)。

## 二、G1 的 Region 与分代回收

G1 即 Garbage-First，是分代垃圾收集器。它把堆划分成大小相等的 Region，每个 Region 可以承担 Eden、Survivor 或老年代等角色。年轻代与老年代分别由不同的 Region 集合组成，不要求各自占用一段连续的地址空间。

年轻代回收主要处理年轻代 Region，并复制存活对象。并发标记识别存活对象，为后续回收提供依据。混合回收既处理年轻代，也处理部分老年代 Region。

G1 不是完全没有停顿的收集器。部分工作可以与应用线程并发执行，但仍有暂停应用线程的阶段。不能把“并发标记”理解为整个回收过程都不暂停应用。

`-XX:MaxGCPauseMillis` 表达期望的停顿时间目标，不是单次停顿的硬性上限。更低的目标可能影响吞吐量，应通过实际负载评估。

G1 中大小超过单个 Region 一半的对象属于 Humongous Object，通常占用一个或多个连续 Region。排查大对象分配时，需要同时关注对象大小、分配频率和 Region 的可用情况。

参考：[Java 21 G1 指南](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html)。

## 三、使用 jcmd 收集诊断证据

jcmd 可以向运行中的 JVM 发送诊断命令。先确认目标进程，再选择线程、堆或运行事件等证据。下面的 `<pid>` 需要替换成目标 Java 进程的实际进程号。

```text
jcmd <pid> help
jcmd <pid> VM.command_line
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump heapdump.hprof
```

`help` 查看目标 JVM 支持的命令；`VM.command_line` 查看启动信息；`GC.heap_info` 查看堆概要；`Thread.print` 输出线程栈；`GC.class_histogram` 统计各类对象的数量与占用；`GC.heap_dump` 导出堆转储，供后续分析引用关系。

线程栈和堆转储解决的问题不同。线程栈适合观察线程执行的方法、等待与阻塞情况；堆转储适合分析对象占用和引用关系。一次线程栈不能代替堆对象分析。

还可以使用 Java Flight Recorder 收集一段时间内的事件：

```text
jcmd <pid> JFR.start name=diagnosis settings=profile duration=60s filename=diagnosis.jfr
```

诊断操作的影响取决于命令与进程状况。生成堆转储可能带来明显停顿和磁盘开销，操作前应确认可用空间及可接受的影响。

参考：[Java 21 诊断工具](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)。

## 四、内存不足与内存泄漏的区别

OutOfMemoryError 不必然意味着内存泄漏。堆配置不足、正常业务数据量过大，或者本地内存分配失败，都可能导致内存不足，需要结合异常的详细信息判断。

内存泄漏的一种典型情况是：对象在业务上已经不再需要，却仍然被可达引用持有，因而不能被回收。长期运行后，这些对象可能持续占用越来越多的内存。

遇到 `Java heap space`，应检查堆配置和业务负载，再分析对象分布与保留关系。单个时刻堆占用较高，不能独立证明存在泄漏；观察增长趋势并分析堆转储，才能形成更可靠的判断。

以下参数可用于在发生 OutOfMemoryError 时尝试生成堆转储：

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=heapdump.hprof
```

通过堆转储分析哪些对象占用了大量内存、它们被哪些引用保留，再结合业务判断是正常存活数据，还是意外保留的数据。

参考：[Java 21 内存泄漏排查](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)。

## 五、内存故障排查练习流程

以下流程是结合上述知识整理的练习思路，不是所有故障都要机械执行的固定步骤。

1. 记录异常完整信息、故障时间和请求量，确认实际表现。
2. 查看 JVM 启动参数和堆概要，确认实际生效的配置。
3. 如果主要表现为阻塞或响应缓慢，收集线程栈及一段时间的运行记录。
4. 如果主要表现为堆空间不足，查看对象直方图，必要时获取堆转储。
5. 结合引用关系和业务代码，区分容量不足与意外对象保留，修改后使用相同负载验证。

本资料没有记录任何业务系统实际使用的堆大小、线上吞吐量或最佳 GC 参数。这些信息需要从目标系统的运行数据中获得，不能只根据通用知识推断。
