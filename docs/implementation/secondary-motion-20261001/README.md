# 长发 / 裙摆二次运动：第一版（2026-10-01）

后续增量：[尾链扩展记录](../secondary-extension-20261001/README.md)。当前Studio为长发10 + 裙摆14 + 尾链6，共30驱动关节；下面24关节与716检查是第一版的历史证据，不应当成最新范围。

这是**替代物理**，不是已经逆向闭合的官方物理算法。官方渲染/湿身公式、贴图、捕获光照、后处理没有为这个效果改写或调参；不使用官方截图逐像素拟合。

## 使用与实际产物

本工程 `Endfield / MMD Studio`：①初始化人物 → ②打开动作 VMD → 面板内播放。加载后“长发/裙摆物理（替代求解）”默认勾选，关掉可以对照。点击“正面全身镜头”查看，布料湿身可同时开启。不要开 Unity 顶栏 Play，不要保存临时预览舞台。

拖动时间、重置、循环、修改位移/幅度/IK/防穿地参数会重建必要的物理历史。倒拖从动作起点重放，长片可能等待；不是烘焙缓存已经实现。没有 VMD 时保持初始姿态，不自动播放虚构摆动。

实际渲染在 `Validation/secondary-motion-20261001-10/`：

- `01-mmd-no-physics.png` / `02-mmd-physics.png`：同一真实 VMD 2秒、关/开物理。
- `03-mmd-physics-wet.png`：物理 + 湿身。
- `04-studio-preview.png`：实际 MMD Studio 加载、参数操作后预览。
- `mmd-physics-wet-preview.mp4`：真实 Unity 输出61帧、960×600、30fps，2.033秒，无音频，不是AI生成。源PNG在 `frames/`。视频与关键图入库，中间61帧留本地。

动作署名：**Kimagure / @kimagure_video**，UNFORGIVEN CHALLENGE VMD。本轮只输出非商业MMD技术预览，不再分发Motion.vmd，不声称动作是本项目原创。进一步发布/商业用途须自行遵守素材readme许可；相邻预览目录附CREDITS.md。

## 方案 / 许可证 / 官方证据边界

先检查工程、`_EndfieldRefs`、`D:/EndfieldTechLib/02-anim-face-physics` 和上游。SPCRJointDynamics与ZMD里的MagicaCloth2存在，但未接入主工程。SPCR控制器取样/累积步长读取 `Time.deltaTime`，不能原样保证编辑器拖动与离线出片一致；MagicaCloth是商业组件，不把参考工程商业源码复制进公开仓库。这不表示这些库不能适配。

采用 [UniVRM v0.99.4 VRMSpringBoneLogic](https://github.com/vrm-c/UniVRM/blob/8d33850c433881a765ccd88c2839f1042d414094/Assets/VRM/Runtime/SpringBone/VRMSpringBone.cs) 的小型Verlet/旋转核心加薄适配。MIT许可保留在源码头部与本目录；没安装整套UniVRM/UniGLTF，也不声称旧版核心等于最新全套库。

核心：惯性阻尼 + 父系静息方向恢复 + 重力 → 固定长度 → 碰撞 → 静息轴旋转。适配差异：

1. 世界空间尾点历史、固定120Hz，动画先求值，再物理，最后SkinBasis/相机/渲染，无LateUpdate/墙钟步长。
2. 明确加权骨链，不接管整棵骨架，不给缺位置的末端虚构7cm骨头。
3. 单碰撞球用长度球与外部性的交界投影替代简单“推出再归一化”；可行时同时保长度和非穿透。整个骨段被包住时没有可行解；多球/摆角约束也可能冲突，不能由单球门禁推断全角色无穿模。
4. 长发每关节安全摆角≤36°、裙摆≤24°。弹性、阻尼、重力、球半径与摆角是**预览默认值**，不是解包官方配置，也不是截图拟合。
5. 关闭仅恢复拥有的次级局部旋转，不修改主骨、局部位置/缩放、资产、shader/天气全局。

## 骨链范围：33关节假设为何撤回

输入 `Assets/Typhoeus/_typhoea_model_data.json` SHA256：`008b95e54768515b621ce0775e96f8b133b7089b1ac33da7cf9c9e3ed121d860`。

长发R/L `base_a_01..06`有真实权重，`07`没有；七条 `skirt_base_{R_c,R_b,R_a,M_a,L_c,L_b,L_a}_01..03`有权重，`04`没有。当前绑定恢复对没有矩阵的骨有identity fallback，**不能把它当末端真实位置**。05运行被权重门禁拒绝，失败报告保留，没有删掉验证硬接。

实际 **24个驱动关节**：长发2×5、裙摆7×2。每个驱动骨及下一骨都有真实权重与直接parent关系。最后有权重的骨随父系移动，未再独立驱动旋转；蝴蝶结分支跟随不等于独立物理完成。

先恢复解包加权bind并写入MMD T-pose，再构造物理。构造对所需骨名歧义、缺失、坏parent/权重/长度、非单位缩放拒绝。同名mesh对象不参与骨名映射（04早期错误保留）。

## 接入点

- `Assets/EndfieldShaderPack/Editor/EndfieldSecondaryMotion.cs`：`Evaluate(t, animatedPose, enabled)`，固定tick求解与倒拖重放。
- `EndfieldMmdStudio.cs`：LoadMotion后建实例；ApplyAnimatedPose负责身体/表情/现有防穿地，ApplyAt统一物理/SkinBasis/相机。
- RunRender直接调用同一ApplyAt、开头清历史；身体输入变化清历史，重校准前还原次级locals。
- 关闭/重载时先Dispose物理，再释放湿身/贴图/管线会话。无持久物理组件，无场景/ProjectSettings写入。
- **独立EndfieldVmdBatchRender、旧AnimStudio、解包clip driver未接这一版物理**，不能外推认证。

## 验证 / 红测试留存

Unity2022.3.30f1 / URP14 / D3D11，最终10/report.txt **716 checks PASS**：

- 实际24加权边；2400子步有限/固定长度误差<2e-5m/安全摆角。
- direct seek、增量播放、30/60fps采样、同时间重复、倒拖、关/开恢复；角差门限<0.05°，没有随失败放宽。
- 合成单球保长度/外部性；非法时间与零长度拒绝。
- 真实VMD2秒BakeMesh：hair01最大位移约0.234m；cloth01/02/03约0.0213/0.0140/0.00335m；body/face/iris等不相关网格位移0。这是自有状态对照，不是官方像素拟合。
- UNFORGIVEN（52轨/4146关键帧/约37.7秒）全时间线120Hz求解，半秒采样及末帧有限/长度门禁；**不是任意VMD认证，也未检查全时刻碰撞**。
- 实际Studio加载/幅度与地面选项变化、导出迭代器出帧同状态、关闭恢复17mesh。

01/02为测试enum编译错误，日志在notes；03-red实现缺失运行失败；04错误把无关重复mesh名当骨名；05发现无权重末端；07-red零长度输入未拒绝。06/08/09是中间通过版本，10是最终；03/04/05/07报告留存。没有用早期PASS替代最终测试。

湿身回归 `Validation/wetness-physics-regression-20261001-01/report.txt` **513 checks PASS**。Python **474 passed / 3历史skipped / 80subtests**；新4项是ownership/集成guards，不是复制物理算法当oracle。Ruff/Pyright通过，临时Python工具环境pip-audit无已知漏洞。**C#/HLSL/整工程覆盖率未测**，716是检查数不是覆盖率。没有新增Node依赖；没有认证Unity全包安全性。

复跑：设 `ENDFIELD_PHYSICS_OUTPUT` 为全新目录、`ENDFIELD_MMD_TEST_MOTION` 为本机Motion.vmd路径，Unity batch执行 `EndfieldShaderPack.EndfieldSecondaryMotionValidation.RunBatch`。不能与用户编辑器同时锁同一工程。完整日志/原索引备份：`D:/EndfieldTechLib/notes/secondary-motion-20261001-01/`。

## 下一阶段

1. 回源找无权重末端的真实rest/原始物理配置，不以identity/猜长度冒充官方。
2. 袖口、外套、飘带、尾链分组，核实际权重与主动画写入范围，避免双重驱动。
3. 大幅度动作mesh穿模、裙摆面间约束、腿/手/头发接触；当前仅球代理+安全摆角。
4. 脚滑/鞋底接触、扭转校正骨与表情是独立MMD待办，不靠物理掩盖。
5. 物理cache/Generic clip烘焙、预热、其他导出入口、角色/相机泛化。

本轮不宣称官方渲染、官方物理或完美MMD已全部完成。原场景/设置/seal、主HEAD/用户暂存索引保留，独立记录分支提交。
