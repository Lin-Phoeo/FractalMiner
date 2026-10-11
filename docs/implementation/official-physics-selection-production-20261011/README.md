# 官方物理输入链：Line统计与有效保存点空间匹配

2026-10-11。接续[隔离Unity参考树getter与骨骼导入](../official-physics-getter-production-20261011/README.md)，将其两种实际采样状态接到Line边、搜索距离与有效saved-selection匹配。**本单元产出匹配到的保存属性字节，不是最终proxy属性、TransformData flags或Unity求解器。**当前舞台渲染、湿身、阴影和预览物理未改动，没有新的可见物理效果。

## 本轮实现

- `Tools/official_physics_line_inputs.py`：从已解析skin父级窗口按原child槽顺序生成Line边；计算原采样均方根/最大距离；克隆有效保存点并应用显式覆盖；组合既有原网格与最近邻参考，输出候选序列和匹配字节。
- `Tools/export_official_physics_line_inputs.py`：将bindings、配置及getter采样关联，要求三个显式SHA256封印并拒绝覆盖输出。限定BoneCloth=1、Line=0、simple/shape reduction均为0、skin顺序不变；非支持分支拒绝，不降级为猜测。
- 两份合成测试覆盖统计/顺序/同距/Invalid、不同保存点数量、userEdit=false、非有限值/错误索引、配置路由、字段解码、封印与CLI。

保存配置的`userEdit`在SceneProbe JSON中为Int32 0/1，属性为`{"Value":byte}`；边界显式解码这两种形态，也支持合成fixture的Boolean/byte。字符串、浮点Boolean、非二进制整数、额外包装字段及非法byte均拒绝，不用任意truthiness绕过核查。

## 官方分支与运算依据

1. `ImportBoneType371507/0x3471d40`读取Line连接模式，按child槽迭代，调用`GetParentTransformIndex(..., excludeRender=true)`。无skin父级则跳过。`PackInt2/0x346fef0`把两个端点排序为min/max，保留边的生成顺序；不自行去重。父级身份由上一单元生成，不按骨名或距离猜测。
2. `ImportFrom371504/0x39d2f80`在导入骨骼后调用`CalcAverageAndMaxVertexDistanceRun371548/0x3dd9fb0`。普通Line统计的调用方先清零平方距离和/最大值；`Work_AverageLineDistanceJob371625/0x42b8e10`使用stride=max(floor(lineCount/100),1)。不是截取前100条，也不是所有情况下都逐边采样。
3. 减法与乘加为Single：delta分量分别收窄，平方和顺序为`(y*y+x*x)+z*z`，各条平方距离串行Single累加。调用方除以收窄Single的采样数，再Single平方根；最大平方距离同样开方。因此`averageVertexDistance`是采样边长的**均方根**，不是平均长度或最大父子长度。这里排除triangle累加和非有限值域。
4. [有效saved分支](../official-physics-saved-selection-20261002/README.md)判断IsValid，不是userEdit。保存数组即使数量与skin不相等也原样Single克隆。运行时`boneAttributeDict`覆盖会在选择后应用；本API强制显式传入已解析覆盖，不能暗中猜成空。
5. `ApplySelectionAttribute371531/0x41b6e80`使用保存位置数组的**不变换重载**。两套输入必须已处于原render-local空间，不新增转置、缩放或“对齐”变换。搜索radius=max(proxy RMS, saved maxConnectionDistance, 1e-5f)，gridSize=radius*1.5f。
6. [fresh serial网格](../official-physics-grid-20261002/README.md)按x最快、再y、再z枚举；同cell按反向插入顺序消费。最近邻的包含半径和后枚举同距替换规则保留，Invalid也可以成为最终winner。本单元仅输出winner；原后续`oldProxyByte | winner`及Transform flags需要初始缓冲，尚未在这条生产链生成，不能拿默认零替代。

统计函数的2032字节RUNTIME_FUNCTION边界包含1973字节代码、3字节padding及两个28字节跳转表。本轮分别认证代码和table，验证14个表项指向代码指令边界及两个加载站点；没有把table线性解码结果当代码证据。并复核5个metadata方法身份、Line Job七个unboxed字段偏移、17处语义锚点和两个直达ret的Single向量helper。

## 实际参考输入结果

当前11组保存配置确实全部为BoneCloth/Line、两类减点距离为0。本轮消费上一单元隔离Unity2022.3的`serialized-rest`、`rigid-reference-frame`采样，**没有重新启动Unity或游戏，也没有采样主舞台恢复角色**。

CLI使用显式`--no-runtime-overrides`：只声明“重建参考树无额外覆盖”的实验前提，**不证明实际游戏运行时字典为空**。结果保留`runtime_overrides_observed=false`及这段前提；缺少它拒绝导出。

| 组 | skin槽 | 保存点 | Line边 | winner=Fixed字节 | winner=Move字节 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 短刘海 | 15 | 15 | 10 | 10 | 5 |
| 长侧发 | 10 | 10 | 8 | 4 | 6 |
| 长马尾 | 14 | 38 | 12 | 2 | 12 |
| 马尾结 | 24 | 24 | 22 | 12 | 12 |
| 外套 | 12 | 12 | 6 | 6 | 6 |
| 裙摆 | 37 | 37 | 30 | 7 | 30 |
| 裙绳 | 6 | 6 | 4 | 2 | 4 |
| 裙袋 | 6 | 6 | 4 | 2 | 4 |
| 背左袋 | 4 | 4 | 3 | 3 | 1 |
| 灯饰 | 4 | 4 | 3 | 2 | 2 |
| 尾部 | 8 | 8 | 7 | 1 | 7 |
| 每态合计 | 140 | 164 | 109 | 51 | 89 |

两态全部140个skin槽均找到保存点，winner字节一致；7组userEdit=true、4组false的数据都保留。特别是长马尾从38个保存点按位置匹配14个skin，而不是截取或逐槽复制。**表中51/89是winner字节分布，不是最终求解粒子的固定/运动分类**；仍须消费old属性与flags。

独立NumPy计算不用生产函数生成期待匹配：复算Line顺序、Single指标、cell候选顺序及280个winner，再对全部保存点穷举检查最近距离。480组随机距离统计（含199/200、299/300与301边界）原始Single位模式全部一致。这是输入/有限值数学复核，不是原native/Burst运行一致性或逐像素画面校准。

## 复现与证据

在FractalMiner根运行，输出须使用未存在的新文件：

```powershell
uv run --python 3.13 --no-project python -B Tools/export_official_physics_line_inputs.py `
  --bindings "D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/official-physics-bindings-03.json" `
  --bindings-sha256 8dad33d1dcbeee882233bb8803b7141b3d2c3817aeed23a619f5c0eeb8fbe3c8 `
  --config "D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/official-cloth-config-04.json" `
  --config-sha256 ce377a025cc16e68a0382e92d73b0b47c82641550f79f58846dcc68af4ad9b3d `
  --getter-capture "D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/unity-getters-03.json" `
  --getter-sha256 0d99b53ebf1c7180e007705629eb9c27a66a853156de443b4f3a4ca4837be783 `
  --no-runtime-overrides `
  --output "D:/EndfieldTechLib/notes/official-physics-selection-production-20261011-01/eleven-matches-02.json"
```

本地目录`D:/EndfieldTechLib/notes/official-physics-selection-production-20261011-01/`：

- `eleven-matches-01.json`：两个参考状态的实际导出。
- `verify_matches.py`、`independent-match-check-01.json`：480组位模式和280槽独立复核。
- `audit_inputs.py`、`native-inputs-02.json`、`certify_sources.py`、`source-certificate-02.json`：原字节/字段/分支证据，47个既有span重认证及5份CFG选定指令报告逐指令重新读取。完整反汇编只在本地。
- `red-01/02.xml`：缺少模块的TDD RED；`red-03/04.xml`：实际序列化字段形态暴露的RED，修正后重跑，不覆盖历史。
- `run_checks.py`、`checks-01.json`、`green-04.xml`、`coverage-03.json`、`full-suite-01.xml`、`pip-audit-01.json`：53项专项、155语句/54分支100%覆盖；3969 passed、114 subtests passed、3历史skip、2历史Pillow告警；Ruff/Black/Pyright/compileall通过。临时工具48依赖无已知漏洞，不等于Unity项目整体安全审计。
- collider-production目录guard28/29及提交后30：核对原164点、7个运行保护文件、舞台、主HEAD和index未变。

公开库仅提交通用Python实现、合成fixture、说明及哈希；不提交完整原始资产/身份记录、DLL/metadata、反汇编或商业插件源码。主代理人工审查与独立NumPy复算，没有本轮新subagent或原运行时执行。

## 下一步的最小正确链路

1. 源证据补齐初始proxy属性、TransformData flags及其映射/normal-axis默认填充，再与当前winner做原OR和flags消费。明确Optimize/reduction是否及如何改序；本单元只适配未减点且skin顺序未变的输入，不能当最终BuildProxyMesh。
2. 形成完整proxy拓扑/约束work-list、Team/骨骼/碰撞体真实发布和生命周期；所有启用消费者齐备后才能建立候选调度，未支持分支拒绝运行。
3. 关闭恢复角色实例身份映射，采样其动画getter；参考树实验前提不能冒充角色运行时状态。
4. 最后接可回退C#后端并跑MMD/解包动作、reset/seek/暂停恢复及唯一writer动态验收。八个总体门禁仍未整体闭合。
