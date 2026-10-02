# 官方物理：动画缓冲读取主体与回退分支

日期：2026-10-03，接续[注册/复制/启停](../official-physics-registration-20261003/README.md)。新增 `Tools/official_physics_animator_buffer.py`，实现 ReadAnimatorBufferDataJob._Do 的**有限、成功单槽最终值与逻辑操作顺序**。不是实际Animator、NativeArray写入、完整物理或可见效果验收。剩余交付项见[进度与缺口](PROGRESS.md)。

## 从入口推进到实际主体

Execute369458/0x5a1dc78的31字节入口转发至 **_Do369459/0x5a1dc98，2509字节exact unwind范围**。本轮已读取主体、核对Job布局和Team stride464；不再停留在入口名推断。

Read job unboxed字段：flag@0、worldPosition@16、worldRotation@32、scale@48、localPosition@64、localRotation@80、matrix@96；三张map分别位于112、128、144，teamIdArray@160、teamDataArray@176。不能把这些偏移与manager类实例偏移混用。

### 门控顺序不同于普通Read

1. **先读teamIdArray[全局manager slot]**，然后检查TransformAccess首qword有效性。无效Transform不读flag/Team结构/maps，但前面的teamId读取已发生。
2. flag需enable mask0x10且read mask0x01。
3. 读取完整Team快照，调用IsCullingInvisible。入口的限定两返回路径只检查低32位中的0x800或0x80000。
4. 没有额外team0跳过，也**没有普通ReadTransform的bit61跳过条件**。不能直接调用普通Read API替代整个_Do。

IsCullingInvisible369625/0x5a3b5e8没有exact unwind入口。本轮只接受固定23字节、8条指令的字段load/test/direct-branch/两RET模式，精确核查分支目标和返回，不以相邻方法或padding推断整方法长度。

## 三层映射与两种来源

| 查找顺序 | 原字段名 | 实际调用点key | 找到的内容 |
| --- | --- | --- | --- |
| 1 | transformID2RWHandlerID | 当前全局manager slot，**不是自行构造的PPtr或InstanceID** | handler内的骨骼index |
| 2 | teamId2AnimatorInstanceId | signed Int16 Team编号 | Int32 Animator instance ID |
| 3 | animatorID2RWHandler | 第2步得到的ID，允许负数 | 原生动画读写record及其缓冲 |

任一TryGetValue失败就立即转到Transform getter路径，后面的map不查。找到record后访问非法handler索引/无效指针不是“map缺失”，不能用回退掩盖。离线接口传入稳定typed映射和已采样的数据；不模拟原生hash map或112字节record的实际指针/lifetime，更不声称已经生成真实游戏Animator map。

**映射成功：**从handler的Single世界位置/旋转和局部位置/旋转缓冲取值；调用WorldToLocal相对变换之前，先从native `TRS(worldPosition,worldRotation,Vector3.one)` 取得世界矩阵。这里的TRS构造尚未移植，接口明确要求调用者提供该native结果，不能拿任意getter矩阵或现成math构造冒充。

两条来源都会构造inverse(worldQuaternion)的零平移旋转矩阵，左乘原世界矩阵，再取有符号对角线。**映射成功分支随后再次写scale=(1,1,1)**；getter回退没有该覆盖。这两次scale写入是源行为，不是为了让结果好看而新增的补偿。参考保留中间scale和两次逻辑写入；测试中的不受约束矩阵仅用于验证分流算术，不证明它来自真实native TRS。

**回退：**依次取position、rotation、localToWorldMatrix、localPosition、localRotation。保留原getter世界矩阵及计算出的有符号scale。

普通模式的最终写入顺序：localPosition→localRotation→scale（映射时再写one）→worldPosition→worldRotation→matrix。矩阵仅在末尾写一次，**不是普通Read中原matrix先写、最终matrix再写的两次顺序**。

相对模式仍由Team.useRelativeTransform@156决定。使用caller已解析的逆TRS和Quaternion(matrix)：Single世界位置先相对变换再扩展Double3；逆矩阵四元数左乘worldRotation；逆矩阵左乘世界矩阵。局部值与已经计算/覆盖的scale保持原空间。init/last不由本函数更新。

## 回写及调度：不得宣称一起完成

- ReadAnimatorBufferData manager369406/0x5a1c92c、Write manager369405/0x5a1ce90的有界指令已核查。Job真实native调度、依赖句柄执行、custom Animator读写record和map生命周期未实现。
- WriteAnimatorBufferDataJob.Execute369460/0x5a2655c的2358字节主体已读取。其枚举循环中的culling、停用flag、bit61及非正权重分支会转到函数尾部，**不是统一continue**；map缺失等分支则转到迭代推进点。尚未移植，不把输入的单槽回退逻辑假称为输出规则。
- Team.UpdateTeamAnimatorData369500/0x5a2283c的3241字节指令已导出；map/record生成尚未逐分支完成语义核查。不能用导出成功称为完整Animator链闭合。
- 既有调度参考的cross+Animator委托路径仍未恢复；本轮不改变游戏实际mode未确认、stock Unity与定制scheduler不等价的边界。

## 验证与留存

按测试驱动技能观察缺模块RED后实现59项GREEN：三层map短路、全局slot与handler index区分、负Animator ID、mapped/getter两来源、二次one覆盖、相对读取、Single→Double、team0、bit61、teamId先读门控和adapter错误。新模块73语句/24分支全覆盖。

全套 **2065 passed /114 subtests /3历史skip /2历史Pillow告警**；22个参考模块1793语句/482分支branch-inclusive覆盖100%。Ruff/format/Pyright通过，临时工具pip-audit无已知漏洞。覆盖率是离线参考的测试覆盖，不是完整官方物理完成比例；没有新增native/Burst/Unity动态oracle。

GameAssembly/metadata封存哈希、主体/辅助路径和报告哈希见[verification.json](verification.json)。完整指令私有存于 `D:/EndfieldTechLib/notes/official-physics-animator-buffer-20261003-01/review-04/`，不公开原资产、完整native报告或第三方源码。11组164个saved点、7项runtime、主HEAD和9557项原index保持。没有运行Unity或游戏，现有舞台/渲染/湿身/阴影/MMD/预览物理未改。
