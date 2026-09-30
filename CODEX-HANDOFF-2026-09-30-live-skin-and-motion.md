# 接管增量：官方皮肤根输入与动作链路（2026-09-30）

## 当前最高优先级：用户已明确改变验收方向

**不做逐像素对照，不以颜色 LSB、轮廓 IoU、截图配准或增益拟合为主线。**
按实际官方 shader / 资源格式 / pass 的结构、逻辑、方法核对实现；确认输入、坐标空间、光照、阴影、后处理和动作时序。画面可用于观察异常，不作为逐像素优化目标。然后接通解包动作与 MMD。旧交接里要求颜色门禁的段落不再是当前任务。

URP 是官方自研 SRP 的适配宿主，不应声称整个引擎、所有变体已经完全相同。已转写分支、适配部分、暂缺部分必须分开说明。

## 本轮已完成

### 1. 真正的 fragment 皮肤根输入

离线重放用户已有 `正面.rdc`，核对实际 shader37671 的 SPIR-V 并生成 HLSL：`Validation/face-input-audit-20260930-01/fragment-37671.hlsl`。
407–418 行的 per-draw flags bit16 决定从 SSBO 加载 root 三行，地址为 base×16。顶点骨骼 palette 则从 base+3 开始，两者不可混用。457 行之后的 SDF 光方向、相机轴、高光 UV 使用这个部件根坐标系，不是 SMR 的 ObjectToWorld。

新工具 `Tools/capture_skin_basis.py` 输出 `Validation/face-input-capture-20260930-01/basis.json`，包括六个部件的 flags/root rows/来源和八张 face mip0 贴图的资源、格式、hash。严格限定已审 frame6411；只重放本地捕获，不启动或注入游戏。
贴图预览与工作资产有垂直行序差，内容一致；这是导出/上传行序契约，**不要因此盲目翻贴图**。Color 属性 Inspector 值与 GPU 线性值不同也不能直接判为错误。

`EndfieldOfficialSkin.hlsl` + CharacterLit 增加显式 per-renderer 根三行，默认开关0兼容原有入口。`EndfieldCapturedSkinBasis.cs` 的捕获行覆盖仅供诊断、不会写入场景/材质，不用于动画。
合成 GPU/CPU 公式测试增加四个根 yaw 输入，先出现预期失败，再通过25例。它是公式单测，不是官方截图颜色验收。

### 2. 当前 pose 验证器漏掉实例旋转

旧代码先 inverse(已带45.5° yaw的scene armature)，最后又给chr root设置同一yaw：两者抵消，实际只剩model-space姿态。
修正：临时诊断场景先恢复 native -90°X，再求inverse、写捕获 model-space 骨态，最后施加官方实例 yaw。不保存基线场景。

`Tools/compare_skin_world.py` 独立验证 raw positions + UNORM16 weights + byte slots + 官方3×4 palette -> 列主序 instance。这是坐标链路测试，不是截图优化目标。旧“L1=0.00000证明所有变换闭合”的说法不能作为本轮基线的证据。
修前 body/face 最大世界位置差约0.213/0.124米；修后约1.42/1.83微米。仅验证这两个部件的位置，不代表其他部件、光照、MMD全部通过。
证据 `Validation/face-world-contract-before-20260930-01.json` / `...after-...json`。

### 3. 随动作更新的皮肤根适配

新 runtime `Assets/EndfieldShaderPack/EndfieldSkinBasisDriver.cs`：

- body 使用 `Bip001_Spine2.localToWorldMatrix`。
- face 使用 `Bip001_Head.localToWorldMatrix`，native 到官方部件轴转换为列 `[-Z,-X,+Y]`；保留位移和尺度，不求inverse、不拟合增益。
- 明确限定 Typhoeus face/body，不把 builder 的 `SMR.rootBone=bones[1]` 当语义来源，不推广到其他角色。
- 源骨映射与轴排列已由frame6411实际root行交叉核实；三个人工动态姿态验证实现，**未声称所有角色/所有捕获的语义都独立验证**。
- 每个 material slot 保留已有 MPB，先检查骨骼/有限值再写；不保存资产、场景，不加新插件。

已接入口：

| 入口 | 更新时序 |
| --- | --- |
| `Editor/EndfieldAnimStudio.cs`（Endfield/Anim Studio） | 解包 clip -> root motion/肩膀/IK -> skin basis -> 预览 |
| `Editor/EndfieldMmdStudio.cs`（MMD Studio） | Reset -> VMD/retarget -> foot correction -> skin basis -> camera |
| `Editor/EndfieldVmdBatchRender.cs`（Endfield/VMD Batch Render） | 同步每帧 ApplyFrame -> foot correction -> skin basis -> camera -> Camera.Render |

不要指望编辑器 Update/LateUpdate 自动发生在同步 Camera.Render 前。当前三处显式更新保证这个输入时序；以后新增 Animator/Timeline 等入口也要在最终骨态之后调用它。

`EndfieldSkinBasisValidation.Run`：三个动态姿态的轴排列、平移、MPB保留、缺骨拒绝 PASS。
`RunAnimationInputs`：实际加载 `A_actor_typhoea_battle_attack_01.anim` 与用户 UNFORGIVEN Motion.vmd，在新载舞台的各三个时刻采样，两条输入的 skin slots 都接通。报告 `Validation/live-basis-animation-inputs-20260930-01.json`。
此烟测只证明 **loader -> pose -> live skin basis**；不证明原生root-motion/IK精度、MMD源oracle一致、目标端防滑、表情/物理或整片出片已完成。没有修改MMD parser/retarget算法。

## 可看产物与代码入口

最新动态根诊断图：`Validation/face-live-after-20260930-01/pose-applied-lit-post.png`。
对应 HDR/根输入/骨矩阵：`Validation/face-live-inputs-after-20260930-01/`。
图仍有眼周噪点、白色附属物等问题，不能标注“原版完全完成”。6411是诊断输入，不是要复刻的唯一姿态。
正式预览仍用现有 MMD Studio / Anim Studio，出片用 VMD Batch Render；舞台仍 `Assets/Scenes/Typhoeus_MMD_Stage.unity`。

## 下一步：按官方结构继续，不回到像素拟合

1. 整理各族官方源码到实现的契约：UV/通道/sRGB、N/T/handedness、对象/骨骼/世界空间、sampler/LOD、材质常量、光方向与强度、pass顺序。皮肤当前是 dry/opaque/flat-environment 的有限分支，不把雨淋/点光等尚未移植的变体当已完成。
2. 优先审眼睛、头发、衣服实际分支和透明/覆盖层；噪点先排输入/索引/法线/采样语义，白色 prop 按独立 renderer/材质来源处理，不调全局曝光遮掩。
3. 检查角色灯统一来源：当前 CP1.w=1 时 shader 由 CP11 覆盖方向，转 CharacterLight 不等于改变最终受光。阴影投影与着色必须遵循官方各自的方向语义，而非凭控件名猜。
4. 按时序核对 shadow atlas -> index/normal -> screen resolve -> forward；HDR scene color -> dynamic Bloom -> captured LUT/post -> 最终编码。捕获输入不可贴在动画上，避免双曝光/双gamma/双后处理。本轮没有改冻结 Bloom/Post/管线验证文件，没有重新证明其全部历史结论。
5. 动作接入已存在，不重复写VMD loader：先确认解包clip、root motion、IK与骨架语义，再确认MMD源求值与target rest-basis/root-space。足底接触、脸骨表情、fixed-step物理仍需实现/审查。KeepFeetAboveBindFloor不是防滑器，五帧烟测不是全片正确。

## 回归、保护和提交边界

- Python：182 passed / 3 skipped / 两条旧Pillow警告；3 skip未伪造为通过。
- Unity实际执行动态单测、六帧输入烟测、live根诊断渲染均return code0；synthetic公式25例通过。
- 本轮测试依赖环境 pip-audit：No known vulnerabilities found，非全技术库安全背书。
- 不改原有9557项 staged，不保存基线场景，不删除用户/第三方资源。
- CharacterLit 工作副本包含他人旧描边改动；本轮记录仅纳入自己的6行属性/CB，其他已有修改不混入。
- 只记录明确源文件，不提交RDC、贴图/模型或本地诊断大文件。诊断依赖本地捕获与资产，记录分支不是完整可运行资产快照。
- 本轮改动前备份 `D:/EndfieldTechLib/notes/face-basis-20260930-01/`；原index/场景保护仍见前一份audit。

复现：Unity batch `-executeMethod EndfieldShaderPack.EditorTools.EndfieldSkinBasisValidation.Run`。
六帧烟测入口同类 `RunAnimationInputs`，设置 `ENDFIELD_BASIS_TEST_VMD` 为已有motion路径、`ENDFIELD_BASIS_TEST_REPORT` 为新JSON路径，`ENDFIELD_BASIS_TEST_RIG` 可指定真实源PMX转换的rig JSON；不指定时明确使用StandardMmd，不当真实源PMX一致性证明。
live诊断入口仍 `EndfieldSkinInputDiagnostics.Run`，设置新 `ENDFIELD_POSE_OUTPUT` / `ENDFIELD_SKIN_DIAGNOSTICS`，再设 `ENDFIELD_LIVE_SKIN_BASIS=1`。不要同时设 `ENDFIELD_CAPTURED_SKIN_BASIS`。
