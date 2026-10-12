# ExNativeArray外层增长：AddRange、typed Fill与Expand

2026-10-12，承接 `611f75d`。生产参考为 `Tools/official_physics_native_growth.py`。本单元将上一单元已恢复的free-list账本接到外层AddRange/Expand/Fill有限状态，覆盖逻辑capacity、detached cells、useCount和emptyChunks；**没有分配或释放原NativeArray，没有执行原Job、恢复allocator handle或接入Unity**，现有舞台与可见效果不变。

## 原路径与精度边界

| 方法 | 已恢复的成功路径 |
| --- | --- |
| `AddRange(Int32)` / method371296 | `requested==0`时只在数组未创建时构造零长数组并返回零chunk；正数先调用既有第一个fit复用。无fit时令`newCapacity = oldCapacity + max(requested, oldCapacity)`，构造ClearMemory数组、复制完整旧capacity、释放旧数组、返回`(oldCapacity, requested)`，并把未用新尾部追加到free-list；最后以返回chunk末端提高useCount |
| `AddRange(Int32,T)` / method371297 | 先走上述AddRange，再只对返回chunk执行typed Fill；不会填新capacity尾部，也不会先清理复用窗口外的旧单元 |
| `Fill(DataChunk,T)` / method371321 | 数组未创建或length非正时早退；正窗口进入FillInternal |
| `FillInternal` / method371322 | 从start起逐项调用setter，共写size次 |
| `Expand(DataChunk,Int32)` / method371307 | 旧length非正或新length不增长时返回原chunk；否则按完整新length AddRange，复制旧chunk前缀，再Remove旧chunk，返回新chunk |

增长后的新NativeArray由原构造路径使用ClearMemory，旧capacity全量复制后才Dispose。有限Python参考用显式`clear_value`表达调用方对零字节的类型解释：对于结构体或quaternion，不能擅自说“默认值就是Python整数0”。复用到的旧cell不自动清零；Expand只覆盖旧长度前缀，因此新chunk剩余cell可能保留复用区旧值，等待调用方后续Fill。

API输入是不可变 `ArenaBufferState(created, cells, arena)` 快照，`cells`只是脱离原生内存的逻辑单元。安全适配器会在变更前拒绝负请求、Int32溢出、useCount越界、free chunk越界及正窗口越界；这些检查不是原非法输入、异常部分写入、并发或native fault等价。`requested==0`、未创建Fill、非正Fill和非增长Expand保留原短路，不读取本来不会消费的无效窗口字段。

## 静态来源与独立参照

从当前method table、MethodSpecs和pointer slots认证11个exact family、6593字节、14个方法身份和48个指令锚点。七个代表性 `AddRange(Int32)` 实例为ExBitFlag8、Int16、Single、double3、float3、float4x4及quaternion；Int16另外覆盖typed AddRange、Expand、Fill、FillInternal，以及NativeArray ctor/Copy/Dispose身份。

关键根包括Int16 AddRange `0x343e010`、typed AddRange `0x41998b0`、Expand `0x758ff08`、Fill `0x343e2a0`、FillInternal `0x3fce7d0`，以及Int16 NativeArray ctor `0x31507b0`、Copy `0x3150b00`、Dispose `0x32be130`。其余实例用于确认外层控制形状，不把开放泛型零offset或相邻函数猜成具体布局。

私有 `verify_source.py` 不导入生产参考，重新读取封印DLL/metadata并依据上述family与锚点生成独立有限状态机，固定seed覆盖1000组AddRange、typed Fill及Expand合成fixture。`check_oracle.py`才导入生产模块比较，1000组全部一致。这个参照是**source-anchored独立状态机**，不是指令解释器、原native执行或Unity动态证明；原始证据和fixture保存在 `D:/EndfieldTechLib/notes/official-physics-native-growth-20261012-01/`，哈希见本目录 `verification.json`。

## 验证、限制与下一步

先观察缺模块collection RED，再实现通过25项新测试。与free-list账本合跑64项；新模块94语句、30分支、100%覆盖。全套4754项及114个subtests通过，保留3项历史skip与2项历史Pillow警告；生产/测试和私有脚本的Ruff、Black、Pyright、compileall及测试环境pip-audit门禁通过。本轮没有独立代理语义审阅。

11组/164保存点、7个runtime文件、9557项主index、主HEAD及受保护舞台文件保持。测试数和合成fixture不能折算成“官方物理完成率”。

仍未完成：`ExpandAndFill`、其他AddRange重载（数组/native/exarray/stride/type变更）、实际十四数组注册与复用、component arena、完整Team teardown、原native容器/allocator/Job/GCHandle生命周期、真实Animator record/TRS和可回退C# Unity候选。下一单元应优先把十四Transform/Team数组的实际注册调用接到本逻辑，补`ExpandAndFill`及所需重载，再进入component/Team完整释放；不能把detached cells称为已分配NativeArray。

全局状态和最终交付门禁以 [PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md) 为准。
