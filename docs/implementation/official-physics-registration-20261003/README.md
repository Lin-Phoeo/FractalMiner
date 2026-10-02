# 官方物理：初始姿态注册、槽位复制与启停

日期：2026-10-03，接续[骨骼读取与恢复](../official-physics-read-restore-20261003/README.md)。本轮新增 `Tools/official_physics_registration.py`，实现 **SetTransform成功槽位字段值、CopyTransform字段复制和EnableTransform单槽flag** 的离线有限参考。只返回值与操作顺序，不运行Unity，不改变舞台效果，不是完整物理后端或完整注册器。

## 已核实的关键规则

1. **init、current、last不是同一份姿态。** SetTransform依次调用11次getter：init局部位置/旋转，current世界位置/旋转，last世界位置/旋转，localScale，current局部位置/旋转，last局部位置/旋转。重复getter是再次调用，不能未经条件证明就复制current到last或init。接口分别接受11个采样结果；是否处于稳定层级由调用者保证。
2. **init不自动等于网格bindpose。** SetTransform用实际getter填init；重新Set会重新取值。Restore读取的正是这两个init缓冲，不能用ReadTransform更新的当前局部值或最新VMD帧替代。bulk Add的初始来源和上游注册时机还未全部闭合。
3. **注册scale与每帧读取scale不同。** Set取localScale；ReadTransform取inverse(worldRotation)乘世界矩阵后的有符号对角线。不能把这两种来源统一成lossyScale、绝对值或列长度。
4. **Set与Copy均不写localToWorldMatrixArray。** 目标矩阵原值保留，不能为了看起来完整而复制或重新构造TRS。单Transform Add另行从float4x4.identity字段初始化矩阵，不能把Add行为套到Set/Copy。
5. **无效Transform注销不清全部姿态。** Set的Unity null/destroyed分支先调用MarkAnimatorTransformDirty，再清flag、TransformAccess、teamId；init/current/last/scale/matrix全部保留。不能将该调用擅自命名为“解除所有关联”。
6. **Enable不恢复初始姿态，也不能复活flag0。** manager无效或负index直接跳过；flag为0保留0；非零flag仅设置/清除mask0x10，其余位不动。清除仅含0x10的flag后再次Enable仍为0。本轮只实现单槽重载，未拿它假代chunk Job。

## 字段与写入顺序

以下offset为manager类实例偏移；不是Job布局，也不是资产PPtr。

| manager字段 | offset | Set/Copy参考值 |
| --- | --- | --- |
| flagArray | 16 | Byte原值；Set不自动OR enable |
| initLocalPositionArray / initLocalRotationArray | 24 / 32 | 首次两次局部getter；与current/last分开 |
| positionArray / rotationArray | 40 / 56 | current世界采样；位置Single3扩展Double3 |
| lastpositionArray / lastrotationArray | 48 / 64 | 再次世界采样，不直接复制current |
| scaleArray | 72 | localScale采样，无绝对值/归一化 |
| localPositionArray / localRotationArray | 80 / 96 | current局部采样 |
| lastlocalPositionArray / lastlocalRotationArray | 88 / 104 | 再次局部采样 |
| localToWorldMatrixArray | 112 | Set/Copy不写，保留目标矩阵 |
| teamIdArray | 120 | Int32调用参数的低16位，存为signed Int16 |
| transformAccessArray | 128 | 调用者已解析的opaque访问引用 |

Set成功：flag → 上述11项姿态/缩放字段（按getter顺序）→ teamId → TransformAccess → AddAnimatorTransform调用描述。所有有限四元数保留大小，包括零；flag0也会采样。TeamManager调用保留原Int32参数，不拿截断后的Int16替代。

Set无效Transform：MarkAnimatorTransformDirty调用描述 → flag0 → TransformAccess null → teamId0。传给dirty调用的是输入null或destroyed引用，不擅自取旧slot引用。manager无效时接口返回None，其他参数不读取。

Copy：flag → init/current/last/scale字段 → TransformAccess → teamId。矩阵保留目标值；没有额外null/enable/team0筛选，也不调用TeamManager。它是已有typed槽位的原值复制，不重新Single舍入Double位置，不归一化、不重新采样。本参考不是共享数组内多writer时序或别名竞态的证明。

接口不模拟实际getter、NativeArray逐次写入及异常中途副作用，也不自动维护Animator集合；`AnimatorCall`只是被确认的方法名、参数和前后位置。有限性、bool、Int32/Byte范围、缺失采样拒绝是adapter政策，不作原生异常等价声明。Set/Copy由调用者先选出有效预分配槽位；没有实现native索引、free-list或TransformAccessArray分配。

## 审过但尚未移植的生命周期

检查了三个Add重载、Remove、Expand和chunk Enable的manager函数范围，但**审过入口不等于实现闭合**：

- Add369416的单Transform路径重复getter，并访问float4x4.identity。调用点0x5a1bb9d的metadata usage指向该类型，identity在static storage offset0。静态字段身份已确认，未读取运行时static storage或执行初始化器。底层ExNativeArray分配/复用返回的chunk与TransformAccessArray Add/Set关系待补，不假设永远尾部追加。
- Add369414从上游对象的数组导入flag/init，其余数组按count建立；Add369415是count预留路径，不能伪装成相同的live getter注册。底层分配默认值和上游init生成仍未完成。
- Remove369419依次调用14个数组的Remove，再逐slot清TransformAccess；**本函数内无TeamManager dirty调用**。flag/teamId调用显式传入0，但没有把未核查的通用Remove内部效果推断成“所有姿态清零”。释放/空洞复用/并发完成仍待审。
- Expand369422分别调用数组Expand；若chunk搬移则转移访问引用并清旧引用。它没有直接调用本轮Copy，不能以Copy未复制矩阵为由推断Expand遗漏矩阵。
- EnableTransformJob369463/0x5a1d2d4无exact RUNTIME_FUNCTION入口。本轮拒绝猜长度，未将单槽代码循环假称为官方Job。chunk入口369420的103字节仅证明分发链。

## 验证与边界

按测试驱动技能先观察缺模块RED，再实现73项GREEN，包含分离getter值、低16位截断、flag0、注销、matrix保留、完整Byte启停遍历、Single→Double、零/非单位四元数、再注册及 **注册→Read→Restore** 的合成接口回归。该回归证明接口不会混用init/current，不是实际Unity动画/物理唯一writer验收。

全套工具测试 **2006 passed /114 subtests /3历史skip /2历史Pillow告警**。21参考模块1720语句/458分支branch-inclusive覆盖100%；新模块82语句/16分支全覆盖。Ruff、格式、Pyright通过，临时工具pip-audit无已知漏洞。覆盖率不代表官方物理完成比例，没有新增游戏原生/Burst/Unity运行时oracle。

GameAssembly、metadata哈希沿用既有封存，方法及报告哈希见[verification.json](verification.json)。完整指令和私有审计在 `D:/EndfieldTechLib/notes/official-physics-registration-20261003-01/review-02/`；原资产、完整原生报告及第三方源码不公开。11组164个saved点仍为合法克隆；7项runtime、主HEAD和用户9557项原index保持。没有启动游戏/Unity或修改舞台、渲染、湿身、阴影、MMD与现有预览物理。

## 后续接入顺序

1. 补齐bulk初始数据来源、底层分配/释放与注册时机；追ReadAnimatorBufferDataJob真正主体。31字节Execute入口仅转发到0x5a1dc98，不能用普通Read替代。
2. 闭合相对TRS/逆矩阵与Quaternion(matrix)、真实11组proxy/Team发布、normalAxis下游、跨帧step/碰撞/惯性/reset；保证动画采样、restore/read和最终物理写入的依赖关系。
3. 候选完整后端具备真实输入后再做Unity可回退接入，验收MMD/解包动作、暂停恢复和跳帧，保留当前可见效果。**本轮没有新的可见物理效果可供预览，不宣称官方物理已完成。**
