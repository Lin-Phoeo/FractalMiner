# 官方物理输入链：新建BoneCloth属性与Transform标志

2026-10-11。接续[Line统计与有效保存点匹配](../official-physics-selection-production-20261011/README.md)，补齐**fresh、未优化、未减点、skin原序**条件下的初始属性、保存属性OR与Transform flags。不是完整BuildProxyMesh，不是游戏运行状态观测，也没有替换Unity舞台后端。渲染、湿身、阴影及现有预览物理保持不动。

## 实现与明确前提

- `Tools/official_physics_initial_buffers.py`：属性初值0、全部Transform槽初值Read=1、逐skin槽OR保存winner，再消费既有原flags规则；末尾render槽不写入/恢复。返回`skin_transform_indices=oldCount+i`，本API限定oldCount=0，不按对象ID合并槽。
- `Tools/export_official_physics_initial_buffers.py`：只消费前一单元封印的匹配产物，要求显式SHA256及`--fresh-ordinary-import`，拒绝覆盖文件。检查状态/组唯一性、跨状态身份/次序/数量和属性byte域；不修改输入。
- 两份测试覆盖256种属性字节、Move优先级、render槽、错误窗口/数量、非Boolean前提、schema/身份顺序、封印及CLI。

fresh empty普通BoneCloth及未改序是**重建参考的实验前提**，不是“已发现游戏必走这一条创建路线”。前一单元的空运行时覆盖前提继续原样保留，不升级为游戏字典为空的证明。重复对象身份也不合并槽；render即使与skin对象相同仍保留单独最后一槽。已有容量/复用/追加、BoneSpring、优化减点后映射不在本API范围，不用当前结果代替这些分支。

## 原字节依据

1. `VirtualMesh.ctor371567/0x3dd6710`创建attributes包装，显式将count/capacity清零并存入字段`+0x38`。`ImportBoneType371507/0x3471d40`随后对该数组调用`AddRange(vertexCount)`。
2. `AddRange/0x45b0960`进入`Expand/0x40ae5b0`的新数组分支，NativeArray构造参数为`NativeArrayOptions.ClearMemory=1`。`0x3dd98a0`检查该bit，向具名`UnsafeUtility::MemSet(System.Void*,System.Byte,System.Int64)`调用传入填充值0。枚举值由当前metadata确认；不是根据stock插件猜初值。这里只静态确认调用契约，没有运行原allocator/icall。
3. 原`ImportBoneType`在`0x347492f`比较类型2，`jne 0x3474a77`跳过BoneSpring的属性填充。普通BoneCloth=1不走DisableCollision/Invalid覆写段。类型/字段语义接续[原骨骼导入证据](../official-physics-bone-import-20261002/README.md)，并逐指令重新读取原完整12628字节body。
4. `TransformData.AddTransformRange370726/0x39d49b0`按`oldCount+i`填索引；flagArray的generic AddRange明确传入byte1。`0x44f26c0→0x45c31d0→0x42287c0→0x2ca5b20`恢复区间逐byte填充，两条setter路径均直接写传入的byte。没有把未初始化数组猜成Read。
5. `Proxy_BoneClothApplayTransformFlagJob371603/0x343c570`按相同顶点槽读属性/flag：Move bit2优先OR4，否则Fixed bit1 OR2；有效属性`attr&3`再OR8。末尾额外render槽不在skin顶点窗口内，因此保持Read=1。这里复用已有`apply_bone_transform_flags`，没有重写或改动该模块。

本轮35个RUNTIME_FUNCTION片段、3个metadata方法身份、21处选定锚点、完整骨骼导入body及独立78字节setter重新校验原SHA/指令；这不是完整所有CFG的独立重证明。generic flag AddRange的方法定义已解析，但一个generic constructor TypeInfo仍未解析；该缺口明确保留，不能据此宣称所有泛型布局或生命周期完整闭合。

## 两个参考状态的实际结果

复用隔离Unity参考树的`serialized-rest`、`rigid-reference-frame`getter匹配产物，本轮没有新启动Unity、游戏或采样恢复角色。

| 每个状态 | 数量/内容 |
| --- | --- |
| 组数/skin/render | 11 / 140 / 11 |
| 初始proxy属性 | 140个0 |
| 初始Transform flags | 151个Read=1 |
| OR后skin属性 | 51个Fixed=1，89个Move=2 |
| flags消费后 | 51个11（Read+FixedWrite+Restore），89个13（Read+MoveWrite+Restore） |
| 末尾render槽 | 各组1个，共11个，只读1 |

独立检查不用生产函数生成期望值，复核全部256种byte规则及两态280个skin属性、302个Transform flags和source-order映射。两态结果一致。这些是**优化前参考数组**；不是最终求解粒子分类、原NativeArray发布或原Job/Burst运行验证。

## 复现与封存

在FractalMiner根运行；输出使用尚不存在的新文件：

```powershell
uv run --python 3.13 --no-project python -B Tools/export_official_physics_initial_buffers.py `
  --matched-input "D:/EndfieldTechLib/notes/official-physics-selection-production-20261011-01/eleven-matches-01.json" `
  --matched-sha256 ec3189c6321559e3dc4b0ad71226240f1cf94fae78aa63b294f6046681bb3d19 `
  --fresh-ordinary-import `
  --output "D:/EndfieldTechLib/notes/official-physics-initial-buffers-20261011-01/eleven-buffers-02.json"
```

本地证据目录`D:/EndfieldTechLib/notes/official-physics-initial-buffers-20261011-01/`：

- `eleven-buffers-01.json`：实际两态11组导出，SHA256 `f6c2a654f254937496bc79a217e2a57748168d107dfe4d3fdaf0f6196f635b57`。
- `verify_buffers.py`、`independent-buffer-check-01.json`：独立byte与实际参考数组复算。
- `audit_initial.py`、`initial-source-04.json`、`certify_sources.py`、`source-certificate-03.json`：只读原版本静态证据；先前迭代也保留，不覆盖失败/较窄结论。
- `red-01.xml`：实现缺失的TDD RED；`checks-01.json`保留初次Ruff C408失败。只对四个新文件机械修正dict字面量后重跑，`checks-02.json`全部通过。
- `green-02.xml`、`coverage-02.json`：27项专项、83语句/28分支100%覆盖；`full-suite-01.xml`：3996 passed、114 subtests passed、3历史skip、2历史Pillow告警。Ruff/Black/Pyright/compileall通过，临时工具48依赖无已知漏洞，不是Unity项目整体安全结论。
- collider-production目录guard31/32及提交后33：保护164保存点、7个运行文件、舞台、主HEAD及主index。

公开只提交通用Python实现、合成fixture、说明和封印，不提交原资产、完整身份记录、DLL/metadata、反汇编或商业源码。主代理静态审查及独立字节公式复算；没有本轮新subagent、原运行时或Burst执行。

## 后续正确路线

1. 确认Optimize/reduction及normal-axis下游如何影响索引、方向和拓扑，连接上述优化前结果，不能直接称完整proxy。
2. 生成约束work-list、Team/骨骼/碰撞体输入及分配/复用/发布生命周期，形成所有实际启用消费者的候选链；未支持分支拒绝运行。
3. 接恢复角色的真实动态getter/身份映射，再做可回退C#后端及MMD/解包动作、reset/seek/暂停恢复、唯一writer验收。当前仍没有新的可见物理效果。
