# MMD 动作接入调研记录（2026-09-26，部分完成）

> **后续状态（2026-09-27）**：本文件是 09-26 的历史快照；当时列出的三处格式错误已修复，P1 错误补丁已从本地 UMT 参照还原。两套代理 PMX 的全帧交叉校验及新的实施路线见仓库根目录 `HANDOFF-2026-09-27-mmd-research-closure.md`。以下“待批准”“未闭合”等字样只描述 09-26 时点，不代表当前状态。特别注意：现有 MMD C# 文件标明由 AGPL-3.0 项目派生，换用 MIT 来源求值器也不会自动解除其他派生文件的许可义务。

> **状态**：用户 20:24 叫停，本文件记录截至叫停时的有用发现。5 路调研里 4 路交付报告，管线全景那一路未完成。
> **证据来源**：受当前网关限制，subagent 的 WebSearch 返回 429、WebFetch 返回 400。证据主要来自 GitHub API / README、docs.unity3d.com（curl 抓取）和本地源码。Qiita / Zenn / NGA / 知乎 / B 站等社区站点**没有覆盖**。
> **原始转录**：`D:\MmdOracle\research-transcripts-2026-09-26\`（含第三方内容，不入库）。
> **标注**：【已核实】= 本会话亲自用数据或源码复核过；【报告】= subagent 的结论，未复核。

## 1. 已核实的缺陷（按优先级）

### 1.1 【已核实·致命】骨骼插值读错字节：P1 补丁是错的，A 阶段的"亚毫米一致"对插值无效

- **数据**：Motion.vmd 共 4146 个骨骼关键帧，插值块第 0 行的 [2]、[3] 字节**全部为 (0,0)**。第 1–3 行 100% 自洽，存的才是真实的 Z / 旋转 x1：多数为 20，也有 43–83 的缓动值。
- **原因**：MMD 在第 0 行 [2]、[3] 写的是逐帧物理开关，不是插值数据。babylon-mmd（`src/Loader/vmdLoader.ts` L183-224）和 mmd_tools（`importer.py` L498/L547）都从第 c 行读通道 c。
- **我方**：`VmdMotion.cs` 按 `{c, c+4, c+8, c+12}` 读，因此**所有关键帧的 Z 与旋转通道 x1 都被读成 0**。移植来源 Poser 的 `mmd_motion.h:208` 同样从第 0 行读，这个 bug 是移植时一起继承过来的（saba 也有同样问题）。
- **UMT 上游原本是对的**：它的 `GetBoneInterpolationChannelOffset` = `channel<2 ? channel : channel+15`，Z/R 从第 1 行读，恰好避开 [2]、[3]。我们的本地补丁 P1（`return channel;`）把 oracle 改成和我方一样错。handoff 里的"实锤"（右手首 f248 旋转差 36°），实际是正确的 UMT 与错误的我方之间的差。
- **修复方向**：
  1. 解析器改为按第 c 行读，即 `16c + {0,4,8,12}`，与 babylon-mmd / mmd_tools 一致；
  2. 还原 UMT 的 P1 补丁；
  3. 重导 oracle 和 ours，重新全帧对比；
  4. 引入独立的第二 oracle，避免再次出现循环论证。
- **不受影响**：腿部 IK 修复（`MmdRig` 改用 `SampleBone`）与此无关，仍然有效。

### 1.2 【已核实·致命】VMD 相机旋转：弧度被当成角度用

- **问题链路**：`VmdMotion.cs:247` 的 `k.rotation = r.Vec()` 读出的是弧度（`:97` 注释写明），`VmdCamera.SampleKey` 插值时没有转换，`VmdCamera.cs:95` 直接送进 `OrbitDeg`，而它内部用的是按角度计算的 `Quaternion.Euler`。
- **后果**：所有 VMD 相机几乎不转。Poser 的 `mmd_camera.h:38-42` 用的是弧度制的 AxisAngle。
- **修复**：`OrbitDeg(rot * Mathf.Rad2Deg)`。

### 1.3 【已核实·高】相机贝塞尔字节序：x2 和 y1 读反

- **正确顺序**：相机每个通道的字节顺序是 x1, x2, y1, y2。两处参照一致：
  - UMT `VMDReader.cs:435-437/444`：`ReadInterpolation(raw, x1=12, y1=14, x2=13, y2=15)`
  - Poser `mmd_motion.h:241`：`Curve{x1,y1,x2,y2} = {unit(0),unit(2),unit(1),unit(3)}`
- **我方**：`VmdMotion.cs:254` 写成 `x1=U(0), x2=U(2), y1=U(1), y2=U(3)`。上一行注释是对的，代码是错的。
- **后果**：默认线性曲线 [20,107,20,107] 被读成 (0.157, 0.843) 两次，结果在 25% 处相机已走完约 76%。
- **修复**：`x1=U(0), x2=U(1), y1=U(2), y2=U(3)`。

## 2. 审计报告的其他发现【报告，未复核】

| # | 位置 | 严重度 / 置信度 | 问题 |
|---|---|---|---|
| 4 | `MmdPlayer.cs:132`、`MmdRetarget.cs:611-613` | 高 / 85 | rootOffset 是在 charRoot 局部空间算的（Z 轴朝上，M5 枢轴为 Ry45.5·Rx-90），却不经旋转直接加到世界坐标。inPlace 把竖直分量清零，保留的一个水平分量被写到了世界 Y。Poser 的做法是 `rootPos + rootRot * rootOffset`（`mmd_player.h:1181`）。 |
| 5 | `MmdRig.cs:484` | 中 / 80 | builtin rig 没有 IK 轨时，C# 返回 true，Poser 返回 false（`mmd_rig.h:509-510`）。MMD 本身默认 IK 是开的，这里要先定下想要的行为。 |
| 6 | `VmdMotion.cs:299,326,330,331` | 中 / 75 | `List.Sort` 不稳定，morph / IK / 相机关键帧也不去重。Poser 用 stable_sort，同一帧后出现的键覆盖前面的。 |
| 7 | `MmdRig.cs:499-530` | 低 / 65 | 每个 IK 控制器求解前，没有重置其链接上的 ik 旋转（UMT `MMDTransformManager.cs:977-981` 会重置）。只影响多条 IK 链共享链接骨的 rig。 |
| 8 | `VmdCamera.cs:44-45` | 低 / 90 | 空相机的回退关键帧 perspective=false、curves=null。 |
| 9 | `MmdRig.cs:336,430` | 低 / 90 | `pose.localRot` 分配了但从未写入；目前没有代码读它。 |

**审计确认没问题的**：
- SampleBone 修复
- fixed-axis 不强制（与 MMD/UMT 一致）
- 记录尺寸与段顺序
- perspective 标志
- 负权重付与
- 付与顺序
- IK 控制器排序
- 相机 orbit 顺序

**注意**：审计把骨骼插值 `{c,c+4,c+8,c+12}` 判为正确，那是拿打过 P1 的 UMT 作对照，属于循环论证，已被 1.1 推翻。

## 3. 现成方案检索（不重复造轮子）

### 3.1 源端 MMD 求值（VMD 采样 + 付与 + IK）

| 方案 | 许可 | 活跃度 | Unity 6 | 要点 |
|---|---|---|---|---|
| **UnityMMDTools**（github.com/CandidumGames/UnityMMDTools） | MIT | 首次提交 2026-06；v0.5.1 发布于 2026-09-02，等于本地 db35d9c；25★ | Asset Store 标注支持 2022.3–6000.3（未实测） | Burst 求解；CCD + 限位、付与（旋转 / 平移 / local）、IK 开关、顶点与组 morph（无骨骼 morph）、相机、Bullet 2.75 物理烘焙；可输出 baked-FK 或 sparse clip；PMX 可生成 Humanoid Avatar。sparse 模式有弧度 bug（即 P2，上游未修、也没人报过），而且对欧拉分量逐个套贝塞尔，追求保真要用 IKBakedToFK。Asset Store 版受 EULA 约束，代码只取 GitHub 的 MIT 版。 |
| **yohawing/unity-mmd-loader + mmd-anim**（Rust 核心） | MIT | 几乎每天提交；mmd-anim v0.5.2 发布于 2026-09-20 | **只支持 6000.0 及以上** | IK、付与、全类型 morph、相机、灯光、Bullet（仅 Play Mode）；Timeline clip；可烘焙 Generic 或 Humanoid；README 称用真实 MMD 导出的数据测试过；C ABI 可以从 2022.3 用 P/Invoke 调用，当第二 oracle。尚未 1.0，只有 Win x64 二进制；v0.3.0 修过同类插值布局 bug。 |
| **babylon-mmd** | MIT | v1.3.0 发布于 2026-07；254★ | Web | 最成熟：Rust→WASM 的 IK / 付与 / morph，Bullet WASM，逐帧物理开关，插值布局正确。适合做参考实现或 oracle（Node 无头运行未验证）。 |
| MMD4Mecanim（stereoarts） | 专有，免费，禁止上传 GitHub | 最后版本 Beta_20200105 | 非官方支持 | PMX→FBX，运行时 IK / 付与 / morph / Bullet；闭源，无法嵌入；EIEM 在用。 |
| Blender mmd_tools | GPL-3.0 | 活跃，3263★ | —（Blender 插件） | 插值按第 c 行读，精确；但 IK 用的是 Blender IK 而非 MMD 的 CCD，四元数用 nlerp。 |
| saba | MIT | 2023-09 起停更 | — | 插值从第 0 行读，同我们的 bug。 |
| nanoem | core 为 MIT，app 为 MPL-2.0 | 活跃 | — | 完整的 MMD 兼容编辑器；解析器忽略物理标志字节。 |
| hobosore/UnityVMDPlayer | MIT | 2020 | 未验证 | Humanoid 运行时播放，不支持付与和 CCD。 |
| abarabone/AnimLite | MIT | 2025-08 | 未验证 | 通过 Playables / Burst 在 Humanoid 上播 VMD。 |
| mmd-for-unity / libmmd-for-unity | BSD-3 | 2018 年停更 | ✗ | 放弃。 |
| three.js MMD addons | MIT | 已在 r172 移除 | — | 放弃。 |
| MMDBridge | 自定义许可 | 2023-08 | 在 MMD 内部运行 | 最接近真值，可用来裁决有争议的情况（未验证）。 |
| MMDAgent-EX | Apache-2.0 | 2026-02 | — | C++ MMD 引擎（细节未验证）。 |
| OedoSoldier/Endfield-Poser | AGPL-3.0 | 2026-09-25 | 游戏内注入 | 我们的移植来源；插值从第 0 行读；无物理。 |
| Sasye/EIEM（终末地 MMD） | AGPL-3.0，46★ | 2026-09-11 | 游戏内 | 直接对 VMD 做 retarget，有 twist 分配，按 VMD 的 IK 标志逐腿选择 FK 或游戏自带的 FinalIK；烘焙路径用 Unity + MMD4Mecanim；它的实践说明 Humanoid 肌肉空间会掉精度。 |
| maoxig/UnityMMDConverter | 无许可证 | 2026-05 | ? | 是对 MMD4Mecanim 的包装；只能参考，不能抄代码。 |
| ShiinaRinne/MMD6UnityTool、MMD4UnityTools | MIT、WTFPL | 2024、2023 | — | 只把相机和 morph 转成 .anim。 |

### 3.2 retarget / 接触 / 比例 / 物理 / 表情

| 领域 | 首选现成方案 | 备注 |
|---|---|---|
| MMD→终末地 retarget 核心 | **没有现成库**（两路调研结论一致）。保留自研，做法与 Poser / EIEM 同类：静息姿态 A/T 对齐、世界旋转增量、经父系转局部、根位移按腿长比缩放。 | Mecanim Humanoid 有损：没有 twist 骨、肩部肌肉范围窄、手指只有 3 个关节、humanScale 归一化导致接触漂移、脚滑、A-pose 需要 Enforce T-Pose。只作 A/B 基线。HumanPoseHandler 和 GameObjectRecorder 在 Unity 6 文档里仍然存在。 |
| 接触 / 脚滑 | Animation Rigging 的 TwoBoneIK 加烘焙。最新版 1.3.0，2023-01 之后没有更新，处于维护状态；项目当前锁在 1.1.1，需要升级。 | Final IK（付费）的 VRIK / Grounder / Baker 可选，但离线烘焙场景下不必要。 |
| 比例适配 | miu200521358/vmd_sizing（MIT，日本社区的标准工具，vmd_sizing_t4 在 2026-01 仍活跃） | 需要一个目标比例的 PMX；适合手部接触多的舞蹈。 |
| 离线 DCC | Blender mmd_tools 配合 Rokoko（LGPL）、Expy Kit、Auto-Rig Pro（付费）或 Blender-Vmd-Retargeting（付费，只有 Daz / CC 预设） | FBX 来回转换成本高，数学上也不比引擎内做得好，不作主线。 |
| 二次运动（头发 / 裙摆） | MagicaCloth 2（付费，质量最好）或 SPCRJointDynamics（MIT，免费，2023-10 后无更新）；也可用 UnityChanSpringBone（MIT）或 UniVRM SpringBone（与 VRM 组件绑定） | 保证出片确定性：由 Recorder 设置 captureDeltaTime，固定步长加子步，从第 0 帧预热，最后烘焙进 clip。 |
| 表情 | 终末地脸部用 SMC（SkeletalMorphCore）的骨骼偏移 morph，不是 blendshape，所以自研映射有理由。参考 Poser `face_templates.h` 的别名表（约 38 个 MMD 表情名）。 | VRM 1.0 表情预设可以作中间层。 |
| 官方 PMX | 没找到 Hypergryph 官方的终末地 PMX（检索受限，未验证） | 原神、星铁等社区多是用官方 PMX 加 vmd_sizing。 |

### 3.3 两路调研的汇总结论（尚未经用户批准，只作为方案输入）

- **源端求值用现成库**：2022.3 上用 UMT 的 baked-FK；mmd-anim 当第二 oracle，也是 Unity 6 的路线；babylon-mmd 当参考实现。我们的 C# 求解器降级为测试夹具，或者保留但必须交叉验证。1.1 已经证明它需要独立验证。
- **retarget 核心保留自研**（两路一致）。接触层用 Animation Rigging，二次运动用 MagicaCloth 2 或 SPCR。输出统一为每个 VMD 一个 Generic AnimationClip（身体 + 物理 + 表情），用 Timeline 加 Recorder 出片，可以平移到 Unity 6。
- **自研只限 4 处**：Bip001 角色映射与标定、retarget 核心、腿部目标胶水、SMC 表情。
- **需要更正的调研说法**：有一路称"我方 IK 是 Poser 版（欧拉钳制、没有膝盖平面解）"。实际 CCD 已经按 UMT 逐行对齐（见 oracle-calibration handoff §2 第 4 条），这个说法过时了。
- **许可**：
  - 我方 C# 移植包含 AGPL 派生代码；把求值换成 MIT 库，就可以去掉 AGPL。
  - 不能抄 MMD4Mecanim，也不能抄无许可证的仓库。
  - 动作素材的许可另算：要求署名，禁止再配布、禁止售卖，只限 MMD 用途。

## 4. Unity 6 迁移要点【报告，依据 docs.unity3d.com 官方升级指南】

**兼容模式时间线**：
- 6.0 / 6.1：升级上来的项目会自动开启兼容模式，但官方不再维护这条路径；
- 6.2：仍可用；
- 6.3：已移除，`URP_COMPATIBILITY_MODE` define 只用于转换过渡；
- 6.4：完全移除。

**必须改的**：
- 三个还在用旧 API 的 renderer feature 要实现 `RecordRenderGraph`：
  - `EndfieldCapturedPostFeature.cs:78-126`
  - `EndfieldCharacterShadowFeature.cs:147-260`
  - `EndfieldShowcaseRef/.../SihouluetteMaskPass.cs:31-55`
- `ScriptableRenderContext.DrawRenderers` 已过时，改用 RendererList：
  - `EndfieldCharacterShadowFeature.cs:244,253`
  - `SihouluetteMaskPass.cs:49`
- `_FORWARD_PLUS` 在 6.1 改名为 `_CLUSTER_LIGHT_LOOP`，涉及：
  - `EndfieldLit.shader:206`
  - `EndfieldLighting.hlsl`
- 编辑器工具依赖 URP 私有内部：
  - `EndfieldAnimRenderValidation.cs:176-187` 依赖 `s_RTHandlePool` 被预热；
  - `EndfieldCapturedSceneBuilder.cs:51` 读取 `m_RendererDataList`。
- `FindObjectOfType` 27 处、`FindObjectsOfType` 4 处，分布在 18 个文件里。

**行为变化**：
- 光照探针亮度从 94% 变为 100%，像素级闸门需要重设基线；
- 不再自动生成光照，批处理建场景时必须显式设置环境光或烘焙；
- 6.4 起 Destroy 时 OnDisable 会覆盖整个层级，`EndfieldCharacterShadowCaster.cs:52-57` 里的补丁逻辑可能被重复执行。

**现在写代码就遵守的规则**：
1. pass 主体写成 static 函数，同时供 `Execute` 和 `#if UNITY_6000_0_OR_NEWER` 下的 `RecordRenderGraph` 调用；
2. 同一个 pass 不要既读又写相机颜色；
3. 用 RendererList 绘制；
4. 持久资源自己分配；
5. 不要用反射访问 URP 私有字段；
6. shader 只用公开 include，同时声明新旧两个关键字，并且不要重复声明 `_BlitTexture`；
7. 用 `FindObjectsByType` 系列；
8. 加 asmdef，用 versionDefines 按包版本做条件编译；
9. 批处理工具显式设置光照；
10. 项目里目前没有 Cinemachine 代码，今后也不要再写 CM2 的代码。

**MMD 与动画部分**：Quaternion / Matrix4x4 数学不需要改；动画代码目前只用到 `SetCurve`、`SampleAnimation`、`GetCurveBindings`。

**未验证的项**：
- Timeline 1.8、Rigging 1.3、Recorder 5 在 Unity 6 上的版本情况，以及 Recorder 能否在 batchmode 下工作；
- AnimationMode、HumanPoseHandler、Playables 有没有变化；
- VFX 17 和 glTFast 在 Unity 6 的情况；
- Burst、Mathematics 的对应版本；
- 开启 RenderGraph 后 `camera.Render()` 的行为；
- 各 toon shader 社区的迁移经验。

**官方依据**：
- 6000.0/6000.1 URP 升级指南（`.../6000.0/Documentation/Manual/urp/upgrade-guide-unity-6.html`、`.../6000.1/.../upgrade-guide-unity-6-1.html`）
- `UpgradeGuideUnity6/63/64/65`
- Cinemachine 3 升级页（`com.unity.cinemachine@3.1/manual/CinemachineUpgradeFrom2.html`）

## 5. 工程现状事实

**版本与包**：
- Unity 2022.3.30f1、URP 14.0.12、Timeline 1.7.7、Animation Rigging 1.1.1、Cinemachine 2.10.3、glTFast 6.14.1、VFX 14.0.12、unity-mcp v10.2.0。
- 没有 asmdef。
- Cinemachine、Timeline、Rigging、glTFast、ProBuilder、VFX 都装了，但代码里零引用；项目代码里也没有用到 Timeline、Recorder、PlayableGraph、AnimationMode。

**目标角色**：
- Typhoeus 的 FBX 是 Generic（animationType 2），没有 Avatar；场景里没有 Animator 或 PlayableDirector。
- 目标骨骼是 `Bip001_*`（3ds Max Biped），外加脸部关节。
- Poser 的 55 个角色编号与 HumanBodyBones 一致。

**Poser 的 retarget 方法**：
- **源端**：在完整的 MMD rig 上播放 VMD。有 PMX 就用 PMX，否则用内置的 Standard rig 或 Extracted T-pose 预设；能自动补全グルーブ、上半身2、肩P/C、捩、足IK親、D/EX 骨。
- **对齐**：先做整体基对齐，再逐骨对齐静息方向，以吸收 A/T 姿态差异。
- **每帧传递**：计算世界旋转增量，经目标骨骼的父系转成局部旋转。
- **根位移**：髋部位移按腿长比缩放（内置 rig 固定为 0.08）。
- **腿部**：腿部 IK 复制膝角和髋→踝方向，但不复制脚的世界位置；接地是可选项。
- **twist**：twist 被合进肘、腕的世界旋转，目标上的 twist 骨和校正骨不驱动。

**工具与环境**：
- **Unity 桥接**：schtasks 任务 `EndfieldUnityBridge`（InteractiveToken）运行 `_unity_bridge.bat`，每次 Unity batch 大约 25 秒；跑完要恢复为只编译的载荷。
- **调研环境限制**：当前网关下 subagent 的 WebSearch 返回 429、WebFetch 返回 400，只能靠 curl 或 GitHub API。

## 6. 下一步建议（待用户确认，尚未执行）

1. **修 1.1–1.3**：都是有数据或源码佐证的单点缺陷。修完还原 UMT 的 P1，重导 oracle，重新全帧对比，这次要加一个独立于 UMT 的第二 oracle（mmd-anim 或 babylon-mmd）。
2. 复核并处理审计的 #4–#9。
3. **架构决策**（继续 brainstorming 流程）：
   - 源端求值用 UMT / mmd-anim 还是继续自研；
   - retarget 保留自研，加 Animation Rigging 接触层；
   - 二次运动与表情方案；
   - Unity 6 兼容写法。
4. **补社区检索**（Qiita / Zenn / NGA / 知乎 / B 站），需要先找到一个可用的搜索通道。
