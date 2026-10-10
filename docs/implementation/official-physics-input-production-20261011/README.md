# 官方物理真实输入：有序对象身份与父级索引

2026-10-11。本单元把已核实的收集/查找规则应用到原始556个Transform、11个BoneCloth组件，生成**140个skin槽及11个追加render槽**的对象身份、父级和根骨索引。不是完整proxy、真实世界快照或Unity后端；舞台、渲染、湿身、阴影及现有预览物理均未修改。

## 实现与调用

- `Tools/official_physics_identity_inputs.py`：复用原collector，校验完整序列化forest，生成快照父级、排除最终render槽后的skin父级以及原序root索引。
- `Tools/export_official_physics_identity_inputs.py`：读取已经由bindings导出器核查的schema-v1文件，要求显式SHA256，拒绝覆盖输出，生成可重复使用的11组身份输入文件。
- 两份专项测试覆盖原序、重复render、根列表重复、忽略分支、跨文件同PathID、signed Int64边界、非法引用/循环、深链和CLI导出。

在仓库根执行，替换输出为一个尚不存在的路径：

```powershell
uv run --python 3.13 --no-project python -B Tools/export_official_physics_identity_inputs.py `
  --bindings "D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/official-physics-bindings-03.json" `
  --bindings-sha256 8dad33d1dcbeee882233bb8803b7141b3d2c3817aeed23a619f5c0eeb8fbe3c8 `
  --output "D:/EndfieldTechLib/notes/official-physics-input-production-20261011-01/eleven-identity-inputs-02.json"
```

这是身份编译，不是把prefab local TRS当世界快照。输入文档需先完成原始对象/组件/引用核查；本导出器不凭骨名或文件名认证组件类型，也不将哈希匹配冒充语义审计。

## 源规则与重要分流

1. **身份不降精度**：使用 `(serialized file, signed Int64 PathID)`，保留重复名称和跨文件同ID；这些不是Unity运行时Int32 instance ID，不能直接写入原runtime ID缓冲。
2. **IndexOf取第一次匹配**：GetTransformIndexFromId（370205/RVA0x5a51ef0）和GetParentTransformIndex（370206/RVA0x346ff20）使用原List.IndexOf。最终render会无条件追加；若它早已被收集，父级查找必须仍取早期槽，而非被字典覆盖成末槽。
3. **两个父级窗口**：snapshot父级覆盖全部槽；skin父级只覆盖skin。仅当查找结果等于最终renderTransformIndex时置-1，不能把任何同身份render都排除。未收集父级和root保持-1；不能按名字补齐或将其自动当Fixed属性。
4. **普通初始化中心**：Init的Component.get_transform→TransformRecord→clothTransformRecord，以及CreateBoneRenderSetupData读取record.transform并传给RenderSetupData的调用链经实际字节复核。此静态路径用布料组件自身Transform，不用舞台root/Armature包装代替；不据此宣称游戏实际采用了普通而非预建路径。
5. **Init的collisionBones为空**：BoneCloth=1分支RVA0x343ad33将第5个ABI参数槽置0，0x343ad4a调用CreateBoneRenderSetupData。metadata签名确认该槽对应collisionBones，而不是colliderList；callee再原样转交RenderSetupData。此导出器限定这条Init路径，保留None。它不意味着ColliderManager无碰撞体，也不证明其他runtime/prebuilt调用同样传空；不能把35条collider组件引用直接拿来替代此参数。
6. **校验是适配器政策**：双向父子边、单父级、循环/重复节点拒绝和迭代深链校验用于保护输入，不冒充官方异常/null/destroyed对象规则。

## 真实11组结果

| 组（省略MBC_Typhoea_） | skin | 含render的snapshot | 保存selection点 |
| --- | ---: | ---: | ---: |
| Hair_Front_Bangs_Short | 15 | 16 | 15 |
| Hair_Front_Side_Long | 10 | 11 | 10 |
| Hair_Back_Ponytail_Long | 14 | 15 | 38 |
| Hair_Back_Ponytail_Knot | 24 | 25 | 24 |
| Cloth_Coat | 12 | 13 | 12 |
| Cloth_Skirt | 37 | 38 | 37 |
| Cloth_Skirt_Rope | 6 | 7 | 6 |
| Cloth_Skirt_Bag | 6 | 7 | 6 |
| Acc_Back_Left_Bag | 4 | 5 | 4 |
| Acc_Back_Right_Lantern | 4 | 5 | 4 |
| Tail | 8 | 9 | 8 |
| 逐组合计，非跨组去重 | **140** | **151** | **164** |

生成的各组root索引和两种父级数组，与不调用生产函数的独立list/set收集及list.index复算完全一致。长马尾的38个选择点仍须走已核实的有效saved-selection复用和空间匹配；不进行14↔38逐槽复制，也不以userEdit=0强制重建。

## 验证与保存

按TDD先观察两次缺少模块的RED，再实现并复核。65项专项通过；两模块118语句/56分支的覆盖率98.85%（身份核心100%）。Ruff、Black检查、Pyright及compileall通过；完整回归**3871 passed、114 subtests、3历史skip、2历史Pillow弃用告警**。实际临时工具环境48个依赖经pip-audit检查无已知漏洞，不据此宣称整个Unity工程安全。

主代理静态重认证14个精确native span、22个指令锚点、8个字段锚点、collisionBones签名、BoneCloth枚举和实际IndexOf MethodSpec。没有本轮独立代理语义审查，也没有运行原DLL、原Job或Burst oracle。

本地证据目录：`D:/EndfieldTechLib/notes/official-physics-input-production-20261011-01/`：

- `eleven-identity-inputs-01.json`：真实11组输出，原对象完整身份仅本地保留。
- `certify_inputs.py`、`source-certificate-02.json`：只读原DLL/metadata及绑定哈希保护，精确字节/签名/字段验证和独立11组复算；01是增加签名/枚举锚点前的历史报告，未覆盖。
- `run_checks.py`、`checks-01.json`、`green-02.xml`、`coverage-02.json`、`full-suite-01.xml`、`pip-audit-01.json`：可复核检查记录。
- 原输入守护22/23位于collider-production证据目录：11组164个saved点、7个运行文件、主HEAD/index和舞台原样保留；提交后另做24复核。

公开库仅存适配代码、合成测试、说明与校验清单，不发布原始游戏对象、全文反汇编或资产。

## 接续顺序与未关闭门禁

本轮只关闭了第1门禁中的**有序身份/父级/root槽生产子项**，并把Init collision参数与ColliderManager组件列表分开；不把第1门禁整体标成PASS。

下一步沿这些槽接入候选实例的实际世界getter/矩阵快照，保留runtime Int32身份与PPtr的显式映射；按原有效saved分支做空间匹配生成属性，再接normal/bindpose、proxy拓扑、约束work-list、Team/native分配与输出生命周期。已有数学参考复用，不重新发明。完整输入/调度闭合后，才切换可回退Unity候选后端并验证MMD/解包动作、暂停/seek/reset和骨骼单writer。

原预建/async路线、实时null/destroyed语义及未实现活动分支仍是显式缺口。不能用默认零输入、no-op或调参近似宣布官方等价；本轮没有新的可见物理效果。
