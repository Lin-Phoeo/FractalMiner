# 官方物理：根节点、长度深度与角色对齐分支

日期：2026-10-02。接续[proxy输入/局部姿态链](../official-physics-proxy-chain-20261002/README.md)。新增 `Tools/official_physics_root_depth.py`，实现已认证原始 Job 的有限输入域离线参考；同时核查提弗洛斯11组法线对齐实际配置。**不是完整实时物理后端**，未改 Unity 代码、模型、舞台、材质、湿身、阴影或当前预览物理。

## 本轮实际完成

`evaluate_vertex_root_depth(parents, attributes, positions, initial_depths)` 返回原始规则对应的根索引、累计长度、深度及全局最大长度：

- 对全部代理顶点求值，不按 baselineData 或可见/加权骨列表筛选。
- 当前顶点含 Move 位2且 parent>=0 才沿父链走。每一步**先加上到父节点的距离**并记录父索引，再检查父节点是否继续 Move；非Move父节点也贡献最后一条边。
- 根输出初始-1，最后成为“最后走到的父节点”。非Move顶点、自身无父的Move顶点都保持-1；不把它们擅自写成自身索引或全局骨架根。
- 累计位置为 float3 Single，顺序是**由当前子节点向上累加**，不是从根向下复用父缓存。输入先舍入Single再相减；dot保持 `(y*y+x*x)+z*z`；sqrt和累加分别舍入Single。
- 使用整个代理顶点域的一个最大累计长度，**不是按发链/分组分别归一化**，也不是骨骼层数。
- maximum严格大于 float32(1e-8) 才对所有槽执行 clamp(length/maximum,0,1)。否则保留调用者原 depth buffer；不凭猜测初始化为零。长度和根输出始终重写。

与已封存baseline生成器的接线测试确认：即使某个可动子树没有被本次baseline根列表包含，它仍参与这个Job的全局最大值。不能把baseline作用域和全部proxy顶点域混为一谈。

完整森林/索引/Int32/Byte/UInt16域上限、有限Single输入/中间量检查是adapter安全契约，不冒称原始异常行为。原始Job的vcnt为Int32，当前参考器沿用已恢复proxy适配器的最多65536顶点边界。Python sqrt及显式Single舍入尚非游戏CRT/Burst逐位运行oracle；暂不实现非有限原生异常值路径。

## 身份与原始证据

原GameAssembly/metadata SHA256沿用前一阶段封存值，见verification.json。原始文件和完整指令报告仅保留本地，未执行原DLL、启动游戏、附加或注入进程。

认证 `VirtualMesh+BaseLine_CalcMaxBaseLineLengthJob.Execute` method371609/RVA0x313fed0，真实CHAININFO四片段47/500/101/98，共746字节；逐段完整解码，不按相邻方法距离猜函数尺寸。unboxed字段：vcnt@0、attributes@8、localPositions@24、vertexParentIndices@40、vertexDepths@56、vertexRootIndices@72、rootLengthArray@88。

关键控制流：0x313ff86 Move位2；0x313ff9a父符号；0x313ffed位置相减；0x3140028 sqrtss；0x3140033 addss；0x314003b更新根；0x3140070复查父属性；0x3140087–0x3140096写root/length；0x31400ba–0x31400f1阈值；0x3140119 divss及0x314011d clamp。阈值常量RVA0xa8c30e4原bytes77cc2b32，值9.99999993922529e-9；上界RVA0xa8c2ce8原bytes0000803f，值1。

减法helper0x2ef3960/49字节与dot0x4a4bd00/37字节采用严格直线指令白名单到RET认证。clamp helper0x2cd23e0无unwind条目，单独人工复核40字节：所有本地分支目标在指令边界、2处RET及上下界/原值选择路径、尾jmp回已审查块、后8字节INT3；没有误称其为直线leaf或完整unwind证明。原clamp会处理NaN，但本参考adapter明确拒绝非有限输入/中间值。

`CreateVertexRootAndDepth` method371536/RVA0x374b590 的参数装配顺序与上述字段结构相合（vcnt及六buffer），但实际经运行时函数指针调度。**没有将名字/字段匹配冒称已恢复泛型Job反射、原生动态调用链或Team分配/发布**。

## 当前角色可以排除的一条分支

重新读取封存原始配置 `official-cloth-config-04.json`（SHA256 ce377a025cc16e68a0382e92d73b0b47c82641550f79f58846dcc68af4ad9b3d），11组均 `normalAlignmentSetting.alignmentMode=0`、normalAxis=1、adjustmentTransform为空PPtr。

不是把名字猜成模式：原metadata认证 `ClothSerializeData.normalAlignmentSetting` 对象offset128、实际类型NormalAlignmentSettings；该类型alignmentMode@16。原 `ProxyNormalAdjustment` method371527/RVA0x43f6b10 的两个真实片段共888字节，0x43f6c0b读取配置+0x80，0x43f6c1b读取setting+0x10，0x43f6c20模式0直达返回；mode1/2另走对齐处理。

所以**当前提弗洛斯无需执行额外放射normal alignment Job**，但这不等于所有proxy normal/方向前处理均可省略。方法仍先分配normalAdjustmentRotations并调用填充链，本轮尚未认证其默认值和填充Job；导入normalAxis、骨姿态旋转/位置来源及后续方向任务也尚未完成。其他角色或mode1/2不能套用“总是不对齐”。

## 验证与下一步

TDD先缺模块RED再实现；49个新增测试包括多根全局尺度、Move位组合、停止位置、负父索引、非拓扑顺序、长度0、阈值上下、非Move深度保留、单精度输入舍入、由子向上累计不可换序、旧baseline接线、非法缓冲/索引/环/非有限输入。

全套 **1340 passed、114 subtests、3历史skip、2历史Pillow告警**；七参考模块654语句/184分支，覆盖率100%；Ruff/format、Pyright 0 errors、临时环境pip-audit和新增代码密钥模式检查通过。现有运行资产及主HEAD/主index保持。Unity未运行，本轮不提供新的动态物理效果验收。

下一批聚焦真实bone proxy输入（导入顺序、属性、方向、默认调整旋转及分配初始化）与Team/step接口；随后串积分/惯性、碰撞/reset、骨骼单写入者输出，最终接入可切换Unity后端。本模块和已经验证的角度/分组/局部姿态参考不反复重做。
