# 当前物理交付缺口：不以测试数量代替完成进度

初版 2026-10-03，当前状态更新至 2026-10-11。本表限定官方物理接入主线，不重新宣称渲染/MMD的历史验收状态。现有预览物理继续可用；**完整官方候选后端没有接入Unity，也没有动态通过验收**。因此不是只剩若干参数微调，无法给可靠的完工百分比或会话数量。

## 已有基础

原版本与参数证据、若干proxy/角度/骨骼输出数学、current/last发布、限定host调度、普通Read/Restore/Set字段规则已有离线参考。Animator读取主体的map分流与有限值参考已有；[EndSimulationStep步末有限值参考与Start受力片段](../official-physics-particle-step-20261003/README.md)后，又实现[Start姿态插值/已解析中心惯性消费/受力组合](../official-physics-start-step-20261003/README.md)，测试连续两步反馈。所有这些仍各有输入/分支前提；合成测试和代码覆盖率不能证明真实全链完成。

## 剩下三类工作、八个交付门禁

| 类别 | 必须完成的门禁 | 当前实际状态 |
| --- | --- | --- |
| 真实输入与生命周期 | 1. 11组proxy/Team/list/骨骼/碰撞体等完整原输入发布 | 164个saved点克隆已核查；140个skin+11个render身份槽及两种父级/root索引已从原始引用生成。隔离Unity参考树两状态的真实getter、快照、骨权重/bindpose导入已验证；恢复角色动态getter、完整proxy与Team发布未闭合 |
| 真实输入与生命周期 | 2. bulk init生成、分配/复用/释放、相对矩阵构造 | 单槽Set/Copy/Enable有参考；[Double TRS/full inverse数学](../official-physics-frame-anchor-20261009/README.md)已有有限值参考，但allocator、bulk构造及全部调用方接入未完成 |
| 真实输入与生命周期 | 3. 动画map/record、回写Job与唯一writer调度 | 动画读取有限值已实现；map生成、输出Job与cross+Animator委托链待补 |
| 动态求解 | 4. step积分、中心运动/惯性/风与各算子依赖 | 普通粒子Start→End、[子步中心](../official-physics-center-step-20261003/README.md)、[Team与风状态](../official-physics-team-tail-20261003/README.md)、[粒子风力](../official-physics-particle-wind-20261003/README.md)、[Spring](../official-physics-spring-20261003/README.md)、[帧移动归约](../official-physics-frame-motion-20261008/README.md)、[帧惯性](../official-physics-frame-inertia-20261009/README.md)、[瞬移/平滑](../official-physics-frame-prelude-20261009/README.md)、[锚点生产](../official-physics-frame-anchor-20261009/README.md)、[符号缩放映射/帧矩阵](../official-physics-scale-remap-20261009/README.md)、[fixed-point帧目标生产](../official-physics-frame-target-20261009/README.md)、[帧reset补全/权重/独立PostTeam历史推进](../official-physics-frame-history-20261009/README.md)、[frameLocalPosition/风区选择](../official-physics-wind-zones-20261009/README.md)、[粒子14缓冲reset/7历史变换](../official-physics-particle-reset-20261009/README.md)和[帧末显示预测/动画历史发布](../official-physics-display-20261009/README.md)已有离线参考。风区经swap-back替换后按原顺序接续子步时间与粒子风力；帧prelude保留旧历史，PostTeam在全部子步/回写后推进帧历史；显示链保持模拟、显示与动画proxy历史分离。真实WindData/proxy/Team输入发布、reset请求/暂停恢复及跨步依赖仍未闭合，不用舞台root或默认零值代替原输入 |
| 动态求解 | 5. 碰撞链、normalAxis下游及约束完整消费 | 尚未完成整个角色的原输入、迭代顺序与输出闭环 |
| 动态求解 | 6. reset、暂停恢复、跳帧及状态发布 | current/last复制与host顺序有参考；帧级component/frame/now/oldWorld reset、帧权重初始化、PostTeam历史/flags/clock/force片段、[粒子14缓冲reset/7历史负缩放与惯性变换](../official-physics-particle-reset-20261009/README.md)，以及[帧末显示位置、原动画proxy历史和负缩放rotation发布](../official-physics-display-20261009/README.md)已有有限值参考。暂停/seek请求产生reset标志、暂停恢复跨步、真实数组发布及定制完成机制仍待补；离线私有range结果不等于Unity已发布 |
| Unity交付 | 7. 可回退C#候选后端与角色实例接入 | 未开始替换当前舞台后端；不能将Python参考称为Unity已实现 |
| Unity交付 | 8. MMD/解包动作下的实际动态验收与可迁移接口 | 候选后端未具备，不能宣称已验收或可无误迁移其他角色 |

“三类”不是三次调用，“八门禁”不是八个小补丁。动态求解与真实输入仍有逆向工作，不能给“已经90%”或“再一两轮就完美”的保证。

## 推进优先级

2026-10-09接续审计纠正了fixed-point帧目标旋转的native ABI→Python API适配：旧代码/测试重复交换Y/Z，正符号identity fixture本应保持identity。修正实现、独立矩阵参照和旧说明；粒子reset与两子步组合采用修正后的目标。原字节SHA检查正确不等于旧语义结论正确。详情见粒子reset说明与frame-target纠错记录。

2026-10-09随后补齐CalcDisplayPosition的有限值参考：恢复realVelocity显示外推、未钳制clock比例、原1.3根半径、blendWeight、flag20原动画历史与flag20000负缩放rotation写回，并用reset→两次Start/End→显示→再reset组合测试确认三套历史没有串用。这仍不是原NativeArray/Job或Unity动态验收。

2026-10-09同批推进[约束调用链](../official-physics-constraint-chain-20261009/README.md)：Distance的work-list/稀疏chunk/packed邻居与顺序range消费、显式WorkData的mode1点碰撞，以及完整18段子步符号依赖已有参考。恢复碰撞前后两次Distance、Spring/普通碰撞velocity reference差异与摩擦→逆质量→End反馈，用Start→Distance→Collision→Distance→End→下一Start限定组合测试验证。其余算子没有暗中设为已实现no-op；SelfCollision四轮目前只有顺序描述，不是碰撞数学。ColliderManager生产、真实list/proxy/Team发布、wrapper空列表与实际调度仍未闭合。

2026-10-10补上[ColliderManager生产与Point整批消费](../official-physics-collider-production-20261010/README.md)：Pre managed的Double帧/三套历史、显式Single Start、独立Double Job Start/End/Post与Point managed串行range已有有限值参考；验证Pre→Double Start→End→Post→下一帧及WorkData→Point消费者。新证据确认Start/End/Post UnsafeDo传Raw Double buffer给Single内核，普通Job则独立Double实现，因此没有捏造数值转换或宣称所有路由等价。真实runtime开关/Burst未观测，普通Point Job数学也需单独复核。原组件class、allocator/bulk输入发布、其余约束和完整Job依赖仍未闭合。

2026-10-10继续恢复[独立普通Point Job](../official-physics-point-job-20261010/README.md)：确认其Sphere/Capsule的Double合并半径、Double胶囊方向旋转，以及三种形状用原Double法线投影、Single法线输出的独立边界，未直接套managed形状函数。同时查出并修复此前managed参考中Spring速度误用位置增益的问题：原两条body均让速度参考加未缩放平均修正，只有next位置乘法线长度增益；低于法线长度门禁时两者清零。用修正前RED、非共线接触和已生产Double WorkData组合验证。单槽参考不等于Job并发、实际Burst或Unity发布。

2026-10-10随后恢复[Tether约束](../official-physics-tether-20261010/README.md)：独立检查普通Job、注册managed与Invoke实际非Burst fallback，补齐Move-only门禁、signed Team、稀疏proxy/局部root索引、参数转换和managed串行range。参考长度取当前子步stepBasicPosition，恢复Single上下界与拓宽Single的0.3/0.7软修正/速度反馈，不改成硬限长；重复slot及先前修改root保持原串行消费。71项专项及Start→Tether→End→下一Start组合通过。本轮只有主代理人工复核和静态复放，没有独立代理语义审阅或Burst执行证明；真实输入生成、native数组发布及Unity动态仍未验收。

2026-10-10继续完成[Angle完整有限值消费](../official-physics-angle-pass-20261010/README.md)：补齐packed unsigned高16 Team/全局低16 baseline、独立particle/proxy窗口、缓存初始化、Move-only门禁及整条baseline三轮完成后再进入下一条的串行range。独立原字节审查发现普通Job确有两处managed不能替代的精度边界：limit后FromTo目标收窄Single；restoration的delta、旋转与三次pivot向量乘法为Single，而目标减当前值、摩擦、位置/速度反馈仍Double。保留默认managed并显式分流，不宣称两条路或实际Burst等价。164项专项与Start→Tether→Angle→End→下一Start组合通过；完整3585项回归通过，独立数学/索引审阅均通过。原native struct读取、真实列表生产、并行调度及Unity动态仍未验收。

2026-10-10继续完成[TriangleBending两阶段有限值参考](../official-physics-bending-20261010/README.md)：恢复high12 Team/low20全局pair、四顶点/四写槽打包、Volume与两种Dihedral选择、Double几何/Single stiffness与写缓冲边界，以及独立aggregate按原Single顺序平均后拓宽写回Double位置。静态复核实际non-Burst fallback与注册managed只剩初始化flag地址差异，并交叉检查本地MagicaCloth2 2.17.1高层公式；后者不是当前游戏源码，实际Burst/并发/列表生产不据此宣称。官方11组保存配置的bending stiffness均为1.0，但真实topology/work-list、Team/proxy/native发布及Unity动态仍未闭合。本轮没有新可见效果。

2026-10-11收尾[Motion活动范围/Backstop有限值参考](../official-physics-motion-20261010/README.md)：恢复当前global Kernel、实际non-Burst fallback、ordinary单槽交叉证据、signed Team/proxy/Move/IsMotion门禁、BoneSpring参数例外及串行range。初稿测试与实现共同错用Clamp epsilon/InvalidMotion bit，独立字节复核后先跑出4项RED，再改为Clamp拓宽1e-9f、Backstop拓宽1e-8f和bit8。保留原depth求radius、Single平方depth求Motion曲线、Single旋转与球心偏移后拓宽、Double几何/直接除法、未饱和stiffness与拓宽.95f速度反馈，并完成Start→Motion→End→下一Start组合。官方11组maxDistance均关，仅短刘海一组开Backstop；不以效果增强为由修改配置。74项专项与完整回归通过，仍未接入Unity候选后端。

2026-10-11随后核查并实现[SelfCollision路由与缓冲更新计划](../official-physics-selfcollision-routing-20261011/README.md)：原参数Convert、Self/Sync/PSync门禁、位32–49、signed chunk有效性、保留/分配/释放计划、全局计数Int32变迁和同步目标尾循环请求已有离线参考。两路独立原字节审计与实现审查交叉验证，68项专项与完整回归通过。11组保存模式均为0，在参数未覆盖、独立角色且无外部启用同步父组的明确前提下，可按原规则关闭该链，不必为当前角色先完成全部active SelfCollision数学。外部父组仍可激活mode0接收组；旧chunk/其他角色的全局计数不能默认为0。真实父组图/运行状态未观测，native allocator、active数学和Unity仍未接入。

后续集中补真实topology/work-list、list/proxy/Team与骨骼发布，第1–3项按独立11组候选链需求补齐，不继续扩张当前关闭的SelfCollision数学。接入时必须显式核查动态参数/外部同步前提；若启用未实现分支应阻止候选运行，不能静默no-op。候选链形成后再进入第7–8项做可见效果与动作测试。若忠实原实现某分支仍无证据，明确保留待核查，不将调参近似或stock替代方案标成官方等价。

2026-10-11随后开始[真实身份输入生产](../official-physics-input-production-20261011/README.md)：将已核查collector与List.IndexOf第一次匹配规则接成带显式SHA256封印的导出器，从原始556个Transform生成11组140个skin+11个render槽、snapshot/skin两个父级窗口及root原序索引。实际对象身份按文件+signed Int64保留，不缩成runtime Int32，也不按骨名合并。独立list/set复算与原字节/字段/签名认证通过；另确认Init BoneCloth调用的collisionBones参数为空，不把ColliderManager列表擅自代入。65项专项和3871项完整回归通过。这只关闭有序身份与索引子项，仍须接真实getter快照、有效saved选择匹配、完整proxy/Team/work-list及Unity候选后端；没有游戏build路线、原Job/Burst或Unity动态验收证明。

2026-10-11继续接通[真实Unity getter与骨骼导入](../official-physics-getter-production-20261011/README.md)：隔离Unity2022.3重建原始556个Transform，在静止及整体刚性移动两状态采样实际instance/parent ID、世界/局部getter和矩阵；各态11组140个skin/151个snapshot接入既有原数学参考，生成位置、方向、权重和bindpose。独立NumPy复算280个skin输出及整体移动的render-local稳定性通过；Unity实测封印/覆盖拒绝通过，45项专项与3916项完整回归通过。原字节/指令25span与两个主Job身份/边界重新认证。采样对象是序列化参考树，不是游戏或主舞台恢复角色；完整proxy/Team/native发布、后端调度与动态验收仍未闭合。下一步沿现有输入做有效saved选择空间匹配与proxy构造，不逐槽复制14个skin和38个长马尾保存点。

这轮没有新可见效果；当前效果保持。用户能看到的新物理必须以候选后端实际切换并运行过的结果为准，而不是测试数字。
