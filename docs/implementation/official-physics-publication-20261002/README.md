# 官方物理：当前/last缓冲复制与写入入口选择

日期：2026-10-02。接续[骨骼缓冲回写](../official-physics-writeback-20261002/README.md)。新增`Tools/official_physics_publication.py`。恢复的是**有限输入的已完成复制与入口供给数据选择**，不是Unity Job调度、实际骨骼setter或完整物理后端；没有改动现有舞台效果。

## 修正上一阶段的概括

上一阶段写“实际Unity setter读取last buffers”，仅按Job字段名判断，不够准确。源`WriteTransformJob`确实把四个输入字段命名为last，但两个manager入口向这些字段传入的数组不同：

| manager入口 | position/rotation/localPosition/localRotation源 | manager对象偏移 |
| --- | --- | --- |
| WriteTransform | 当前四数组 | 0x28 / 0x38 / 0x50 / 0x60 |
| WriteDoubleBufferTransform | last四数组 | 0x30 / 0x40 / 0x58 / 0x68 |

两者都传当前flagArray、teamIdArray、TeamData与同一个transformAccessArray，并调度同一个`WriteTransformJob`。调度泛型metadata usage在0x32ad3be与0x5a1d17d均为spec515136 / method360313 / methodInst28911；registration中该实例的唯一参数指针与原`WriteTransformJob`canonical byval指针精确相同，已静态核查。字段名不能证明数据年龄。

`select_transform_write_buffers(current,last,cross_frame=...)`明确映射这两个入口。bool必须由上游独立确认的模式提供，不用Job字段名、帧数或“当前动画已更新”自动推断。它返回有限值快照，不冒充NativeArray引用别名或完整模式决策。

## 复制规则

`CopyDoubleBufferJob.Execute`依次调用四次`NativeArray.Copy`：world position、world rotation、local position、local rotation；方向为**当前→对应last**。不交换指针，不旋转/归一化/插值，不按team、Move/Fixed或enable过滤。原copy Job中没有这些门禁输入。

每次Copy使用该**源数组自己的Length**，不是共用骨数、活跃数或两数组较小长度。世界position复制24字节/元素，rotation16，local position12，local rotation16。目标比源长时尾部未被该复制覆盖；adapter保留它，不清零、不resize。

调用链已静态追至源长度与source/destination指针计算：

| 数据 | wrapper → source-length重载 → offset重载 → 字节复制计算 |
| --- | --- |
| Double3世界位置 | 0x3b60d4 → 0x8031854 → 0x3173f4 → 0x4181ac0 |
| Single四元数（两处） | 0x3b607c → 0x8031750 → 0x30af10 → 0x343f790 |
| Single3局部位置 | 0x3b60a8 → 0x80317a8 → 0x30a2dc → 0x314ec10 |

最终跳转0x2d73b10的icall字符串为`Unity.Collections.LowLevel.Unsafe.UnsafeUtility::MemCpy(System.Void*,System.Void*,System.Int64)`。目标RCX、源RDX、字节数R8的计算方向与上述复制一致。这里只核查文件初始化与静态调用，**没有解析活跃运行时函数指针或执行游戏**。

`copy_double_buffer(current,last)`使用四组不可变tuple快照表示一次完成的复制。有限/分量/最多65536项/目标容量拒绝是adapter政策；目标太短拒绝，不截断。验证在返回前完成，失败不部分写入，这是纯函数adapter行为，不宣称原native异常或原部分写入行为相同。NaN/Inf输入及目标尾部拒绝，不处理原raw内存别名、重叠复制和allocator生命周期。

## 已验证与未验证

源绑定：manager CopyDoubleBuffer method369407 /0x32ac880，922字节unwind family；WriteDoubleBufferTransform 369408 /0x32ad2b0，562字节family；WriteTransform 369425 /0x5a1d0ec，485字节；CopyDoubleBufferJob.Execute 369462 /0x5a1a730，230字节。manager包装函数与调度sites已检查，**只移植上述数组供给与复制语义，不宣称整个包装函数、CrossFrameJobUtils或游戏循环已恢复**。

TDD缺模块RED后新增48项通过：复制方向、四数组独立长度、目标尾部、短目标拒绝、大Double/最终Single、signed-zero/subnormal保留、非单位四元数、显式模式、非选缓冲不读取、跨两次合成帧的显式发布，以及上一阶段世界/局部回写→复制→选择组合。组合是合成fixture，不是实际11组proxy或游戏运动轨迹。

全套1720 passed /114 subtests /3历史skip /2历史Pillow告警。17参考模块1291语句/332分支，branch-inclusive覆盖100%。Ruff/format与Pyright通过，临时工具pip-audit无已知漏洞。**覆盖率不是还原完成比例，本轮没有新增游戏运行oracle。**

七项runtime文件、主HEAD与用户原index均保持。没有重跑Unity，没有切换官方物理后端，没有新增可见效果。原资产/DLL/完整指令/第三方库保留在私有目录，不入库。证据哈希见[verification.json](verification.json)，完整报告位于`D:/EndfieldTechLib/notes/official-physics-publication-20261002-01/review-11/`。

## 下一步

已补齐：缓冲回写算术、当前→last的有限复制、两条入口的明确供给区别。

仍缺：实际11组proxy与normalAxis消费；Team/list发布、step/剩余求解、碰撞、惯性/reset；原cross-frame开关、JobHandle完成依赖、何时复制/何时消费、容量扩展及生命周期；实际setter的blend/culling/world-local/relative-sync分支；动画与物理唯一writer的Unity运行回归。

下一阶段优先查调度依赖与模式调用者，明确复制的是哪次完成结果。不要在每次渲染前自动copy，否则last输入会变成current，掩盖跨帧错误。完整运行链未闭合前，继续保留当前预览后端。

2026-10-03后续：[帧钩子与跨帧调度参考](../official-physics-scheduling-20261003/README.md)已静态恢复稳定模式、mapping为空的Transform路径顺序及符号依赖。确认旧master完成→last消费并普通完成→新求解→当前复制至last；原跨帧完成使用独立定制icall。仅调度计划，不执行native Job；Animator委托、mesh mapping、实际setter与完整solver仍未移植，旧门禁为当时状态快照，不改写历史验收。
