# 官方物理：保存选择与代理属性应用

日期：2026-10-02。接续[代理绑定方向](../official-physics-proxy-frames-20261002/README.md)。新增 `Tools/official_physics_saved_selection.py`，实现普通骨骼构建分支的有限输入参考，以及保存选择→代理属性→transform flags 的接线。**没有更换Unity舞台物理，不是完整RuntimeBuildAsync、原版实时求解器或新视觉效果。**

## 本轮纠正的路径区别

1. `SelectionData.IsValid` 只检查positions/attributes非空、非零长度、长度相同；**不检查userEdit**。普通bone worker在ImportFrom后以有效性决定是否新建。有效保存选择即使userEdit=false也不在此处分支重建，点数也不必等于当前收集骨数。
2. 无效保存选择经`SelectionData(proxy, float4x4.identity)`构造，位置仍走原Single矩阵运算；最大距离取proxy的`maxVertexDistance`，默认userEdit=false，然后Fill Move、显式根设Fixed。它**不是**`GenerateBoneClothSelection`的userEdit=true/parent-edge最大距离路径，不能用先前新生成API替代。
3. `boneAttributeDict`在有效/新建两条路径汇合后应用，按RenderSetupData的原始ID查找。缺失ID（返回-1）跳过，命中对selection的对应索引进行**整字节替换**；不按名称猜骨，不重新排序。
4. 代理应用的radius为`max(proxy.averageVertexDistance, selection.maxConnectionDistance, Single(1e-5))`，**gridSize=radius×1.5**。原始RIP常量是`acc52737`与`0000c03f`。另一个`ConvertFrom`路径的AABB×0.2、radius×0.5不能移用。
5. `Proxy_ApplySelectionJob`最近邻判定半径/最小距离均包含等号，同距由**后枚举候选**覆盖，Invalid也可成为winner；最终为**oldAttribute OR winner**，未命中保留旧属性。不是ConvertSelectionJob的整字节赋值，也不能先清空旧位。

最终bone transform flags复用上一阶段原Job：Move优先OR4，否则Fixed OR2，任一有效OR8，旧flags保留。因此原Move位遇到Fixed winner可得到attribute=3，flags仍选择Move；不能强制Fixed优先。

## API与适用边界

- `SavedSelection`、`selection_is_valid`：保存数据及原始有效性判断。允许空/缺失数组表示无效记录；不是允许null SelectionData对象绕过上游异常。
- `choose_bone_build_selection`：ImportFrom之后、reduction/optimization之前的普通bone选择参考。有效数组深拷贝为有限Single，保存userEdit及最大距离；无效才新建。根索引与字典索引必须由原ID查找产生，字典枚举顺序由调用者供给。
- `proxy_selection_search_parameters`：代理应用专用半径/网格参数，不依据bbox重新估计。
- `apply_proxy_selection_attributes`：明确给定原候选序列的nearest+OR内核。
- `apply_bone_proxy_selection`：fresh/serial/no-resize网格、候选枚举、属性OR、bone transform flags组合。支持保存点数与目标proxy数不同；目标位置/旧属性/flags必须属于**实际目标proxy同一顺序**。

ApplySelectionAttribute调用的是GetPositionNativeArray的**无矩阵变换重载**，本参考也不追加world/local猜测转换。输入必须已处于原共享匹配空间。有效/有限输入参考不等于完整克隆、错误处理、泛型调度或Native allocator；有限值、字节/索引/数量拒绝是adapter政策。原应用遇无效选择设置error0x50de，adapter采用ValueError，不把它变成ConvertFrom式空输入保留。

没有移植：MoveNext全部状态机、上游manual/paint模式决策、prebuild路径、mesh路径、减点重排/合并、原世界getter实际值、完整proxy/normalAxis消费、Team/step、碰撞、惯性/reset、Unity骨骼回写。不能宣称普通bone规则就是游戏当前实际走过的分支。

## 原始证据

仅静态读取封存DLL/metadata，SHA及私有证据哈希见verification.json；未执行、启动、注入或附加游戏。完整指令、原资产及第三方源码不入库。

| 对象 | method / RVA | 认证范围 |
| --- | --- | --- |
| SelectionData.IsValid / IsUserEdit | 369315 / 0x4564da0；369316 / 0x4a46790 | 无unwind叶函数：有界可达分支逐指令至RET |
| SelectionData.Clone | 369317 / 0x38e2f20 | 289字节unwind family；数组clone及字段复制 |
| SelectionData(proxy,matrix) | 369313 / 0x5a1fcac | 659字节；maxVertexDistance@0x168，与average@0x158不同 |
| bone worker | 368612 / 0x3ddcec0 | 11269字节代码 + 3字节对齐 + 7项RVA表 |
| RuntimeBuildAsync.MoveNext | 368613 / 0x38e31c0 | 18520字节代码 + 26张各7项RVA表；上游克隆片段核查 |
| ApplySelectionAttribute | 371531 / 0x41b6e80 | 2404字节代码 + 7项RVA表 |
| Proxy_ApplySelectionJob.Execute | 371602 / 0x2ef3e40 | 2588字节；尾部OR旧attribute已核查 |

先前线性解码拒绝的三处函数，原因是尾部RVA跳表被当成代码。本轮按精确unwind范围分开代码/对齐/表，每表有实际加载site且所有target落在真实指令边界；不以连续反汇编到失败点冒充全体。**这些完整字节分类不等于全控制流、每条调用运行时行为或整函数移植已证明。**

worker矩阵RIP 0x3ddd522解码为Unity.Mathematics.float4x4，静态首槽metadata字段为identity@0，zero@64，四列传入构造器；没有把任意未解析常量当identity。保存选择克隆复制positions、attributes、最大距离和userEdit；本参考保持Single位，不比较JSON十进制Python Double数值来判断是否克隆改变。

## 实际配置与验证

封存11组配置全部保存选择有效，合计164点；7组userEdit=true，4组false。私有脚本验证11组有限Single克隆位保持（未施加未知字典覆盖、未尝试假造proxy匹配）。**4组false不等于应丢弃保存选择**；38保存点/14收集骨等情况依然必须走实际位置映射。此检查只证明序列化数据与有限分支参考，不证明当前游戏运行状态或11组完整proxy已生成。

TDD缺模块RED后新增55项通过：有效/无效与userEdit独立、不同点数、根/字典覆盖顺序、缺失ID、空目标、Single十进制表示、inclusive半径/同距/Invalid、网格逆序插入、全65536属性字节组合、旧flags和Move优先、显式拒绝不合法输入。全套1626 passed /114 subtests /3历史skip /2历史Pillow告警；15参考模块1139语句/292分支100%覆盖。Ruff/format、Pyright、临时工具pip-audit通过。**覆盖率不是原版行为oracle，也不是项目完成百分比。**

七项runtime文件、主HEAD/index保持；未重跑Unity。私有目录：`D:/EndfieldTechLib/notes/official-physics-saved-selection-20261002-01/`，最终静态审计review-06、实际配置检查input-check-02、全套coverage-full-02。

## 后续主线

下一步是原世界快照/实际分支条件/normalAxis与proxy构建接齐，产出11组真实完整输入；随后恢复碰撞、Team/step、剩余求解/惯性/reset及唯一Unity骨骼写入。已有新选择快照→frame捷径仍保留，但不能冒充本模块的实际保存选择路径，也不把现有预览物理静默换成尚未完成的官方后端。

接续记录：[世界与局部骨骼缓冲回写](../official-physics-writeback-20261002/README.md)已恢复有限输入的两项回写计算。真实proxy、normalAxis全部消费、双缓冲发布与Unity setter仍未闭合；本页上述历史验证范围不因此扩展。
