# 布料湿身预览与 MMD 测试起点（2026-10-01）

本轮交付的是 **cloth01/02 的源码雨/浸湿响应 + 原生天气纹理接入 + 干净可见的 MMD 初始姿态**。不是“全角色湿身/原版整套天气/任意 MMD 动作全部完美”的完成证明。验收按源码、资源绑定、数值合约和运行生命周期进行，没有用官方截图逐像素拟合，也没有调亮度、曝光、LUT 或冻结后处理来冒充湿身。

## 1. 现在怎么打开看

工程：`A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner`，Unity **2022.3.30f1** / URP 14，D3D11、Linear。这是编辑器预览，尚非打包后的 Player 入口。

1. 等 Unity 编译完成，菜单 **Endfield → Wetness Studio**。
2. 按 **① 打开干燥/湿身测试舞台（不写原场景）**。会询问当前修改，再打开已有的 `Assets/Scenes/Typhoeus_MMD_Stage.unity`。只打开，不重建/保存舞台；原 `Typhoeus_OfficialFrame_Recovered.unity` 不改。
3. 切到 **Game** 标签。按 **正面全身镜头（仅预览相机）**，方便观察袖子、外套、靴子。
4. 勾选 **② 开启湿身（布料 b471）**，先用：雨量 R=1、直接浸湿 B=0、水线幅度 G=0。白色/黑色布料的粗糙度、雨滴法线、流痕和材质变化来自源码，不是全身统一变暗。
5. 为了暂停看清：勾 **冻结雨滴时间**，时间=12 秒。取消冻结即可用正常渲染时间；源码消费的是秒/20。
6. 想看浸湿：R=0，B 从0拖到1。想看按高度浸湿：B=0，G=1，调水线世界高度；不要把 G 当普通全身湿度。
7. **保存当前预览 PNG** 会新建 `Validation/wetness-user-日期时间/preview.png`，不覆盖已有结果。
8. 关闭面板会释放本会话纹理、网格副本和临时管线，并恢复会话前的骨态/相机/Animator/蒙皮刷新状态。预览期间不要保存舞台或切 Unity 顶栏 Play；MMD 播放使用面板内按钮。

若另一个 MMD/湿身窗口已占用角色会话，先关闭那个面板再打开，避免两个纹理/天气所有者互相覆盖。参数出现 NaN/无穷或非法范围时会停用湿身并显示错误，不把坏值送进 GPU。

实际 Unity 输出（不是生成图）：

- 干燥：`Validation/wetness-20261001-12/01-dry.png`
- 雨淋：`Validation/wetness-20261001-12/02-rain.png`
- 初始 T-pose：`Validation/wetness-20261001-12/03-mmd-initial-tpose.png`
- 现有 VMD 的5个采样：同目录 `04-mmd-{0.0,0.3,1.0,2.0,4.0}.png`
- 关闭开关回干燥：`02b-return-dry.png`

## 2. 接着怎么测试 MMD

1. 湿身面板按 **③ 湿身看完 → 打开 MMD Studio，初始化人物**；或关湿身面板，菜单 **Endfield → MMD Studio**。
2. 按 **① 初始化人物模型**。应看到真正写入可见骨架的 T-pose：双臂展开、双腿正常站立，不能只相信“校准成功”文字。
3. 可按 **正面全身镜头（测试构图）**。再按 **② 打开动作 VMD...** 选择你的动作。每次载入会重新恢复完整解包绑定骨架、应用 T-pose，再捕获播放器基准，不能拿上一动作的残留姿态当 rest。
4. 第一轮保持幅度=1、各部位幅度=1、IK=FollowMotion，先不开 VMD 镜头。检查载入信息：校准成功、未映射轨道；非标准源骨架需已有 PMX 导出的 source-rig JSON，不能用幅度滑块掩盖映射错误。
5. 用面板内 **播放/暂停/+1帧**，不要用 Unity 顶栏 Play。先观察腿/脚、手腕、转身、下蹲，再单独加入 Camera.vmd。
6. 可以 **渲当前帧/试拍5帧**。MMD Studio 的出帧改为与湿身预览相同的显式 URP 请求、原生贴图/光照/后处理作用域，并在每帧更新动态 SkinBasis；不再用旧的独立 Camera.Render 路径。输出目录保留现有 fresh-run 机制。整段 MP4 和其他独立 batch 菜单本轮没有全面认证。

已试跑本地 UNFORGIVEN 的 `Motion.vmd`：52轨、4146关键帧、37.7秒、未映射0、scale=.080，5个时刻的骨骼数值有限且实际姿势改变。**这不等于整段动作接触/防滑/布料物理或所有 VMD 已验收**。测试失败请保留动作路径、失败时间、面板信息和当前帧，不要先把幅度改小。

## 3. 官方依据与适配边界

### 布料消费

- 帧6411实际 event835/PS22255 是 cloth01，event850/PS37669 是 cloth02，程序/原 SPIR-V 身份沿用已复核的 draw-program audit。
- canonical b471 雨/浸湿块 `_1828.._1834` 被原样保留在 `EndfieldOfficialWetness.hlsl` 的 SOURCE_BLOCK 内，仅替换采样器名、全局 mip bias 绑定名和手动时间入口。测试删除空白后逐字符比较，不删常量、分支或 swizzle。
- b472 对应 `_1842.._1848`；新增测试证明它与 b471 **这个湿身块**仅临时变量重命名不同。不宣称两个完整 shader 文件/所有变体相等。
- 两个实际 draw 的 set0/t44 均为资源62782，t41 均为1015（已从既有 `replay-details-01/draw-details.json` 核查）。该旧 JSON 不证明 native typed view，native view/mip数据来自本轮重新离线导出。
- CP10.x 的字节选择为 `> .5`；CP10.y 是 **RGBA8 位重解释的 float**，不能上传普通湿度 float。R=雨、G=局部水线湿度、B=直接浸湿、A=雪。雪本轮不消费。
- 水线高度为 `lerp(objectHeight,CP10.w,CP10.x)`，相对当前 world Y 的 smoothstep(-.2,.15)；局部湿度乘 G，再与 B 取 max。CP10.z=2.25 是 UV 尺度，不是雨速。
- wet normal 供 GGX/IBL 使用；非雪路径的 ramp 漫反射/环境梯度仍用原 mapped normal，不能把所有光照法线都替换成湿法线。
- 只给本角色 cloth01/02 创建网格副本，UV2 携带**未蒙皮的原模型坐标**、UV3 携带原法线。源 skinned xzy/sign 转换只做一次。未提供 rest marker、无纹理、关闭开关时保留干燥路径。原 mesh asset 不改。
- 这是重建模型的原始顶点/法线适配；仍不是对原引擎全部 vertex-fetch/rest-stream 输入位级同一性的认证，也不是清漆/丝袜/皮肤/头发等其他天气变体的认证。

### 原生天气纹理（本地数据不上传 Git）

目录：`Validation/Captures/character-weather-20261001-02/`，运行要求保留此目录及既有 cloth/skin/hair/eye/environment native 输入包。

| 输入 | 原生规格 | SHA-256 |
| --- | --- | --- |
| complete.json | 帧6411、离线成功后才写 completion | `97a4ec882d4eaa27a459167bc3f254f3b57ae782dc2c84d3ab2164b983630b96` |
| 835-Rain.raw | BC7_UNORM linear，1024²，11 mip，1398128字节 | `72e3d00a34c5d8edf00b98444af9ae8fae92789bd4c90f15431408e9f04dd92a` |
| 835-Streak.raw | BC7_UNORM linear，256²，9 mip，87408字节 | `05f5a7d6ed00cdeeeff63cf6a0380d77421e8272b22f86d94c47a660770b316c` |

实际 s4 是 U/V/W Repeat、min/mag Linear、mip Point、无各向异性/bias；不能因 dump 的 `sampler_LinearClamp` 字面名字就绑定 Clamp。Unity 直接上传所有 BC7 mip，无 PNG 转码/重压缩/生成 mip/纹理导入修改。typed PickPixel 对所有20 mip的100个采样点/400分量与 Unity GPU Load 对照通过（2e-6）。这是**干燥捕获帧中绑定的天气资源**，不是新取得的雨天气帧，也没有证实 C++ 天气、遮挡、累积/干燥 producer。

### 本轮抓到的集成/初始姿态问题

1. URP14 `SingleCameraRequest` 直接调用 RenderSingleCameraInternal，不触发 begin/endCameraRendering。仅订阅事件会得到“开关勾了但实际湿身 gate=0”。普通相机回调和显式截图现在共用可嵌套、可恢复的 weather scope。
2. 同步批渲染可缓存上一次蒙皮矩阵。会话内启用 `forceMatrixRecalculationPerRender`，关闭后恢复，不再出现骨骼已经 T-pose、画面还是旧姿态的假通过。
3. 重新打开舞台不是干净 bind。现在按 `_typhoea_model_data.json` 的完整481骨层级/17 mesh绑定矩阵恢复，先验证父子层级、跨 mesh 一致性和有限值再写入。17 mesh 的 BakeMesh 顶点对原始 bind 顶点均通过2e-4米门禁。
4. MmdCalibration 旧 pelvis basis 的 x=R-L、z=cross(L-R,up) 构成 det<0 反射矩阵，却交给 Matrix.rotation 提取四元数，导致骨盆扭转。改为一致的右手基；新增髋部横轴与肩部横轴一致门禁先失败再通过。没有修改官方 shader 来补偿这个动画错误。

## 4. 验证及保护

主验收：`Validation/wetness-20261001-12/report.txt`，Unity退出0，**513条检查通过**。包含 packed-float GPU 位模式、native mip/view、材质排除、两种实际相机入口、嵌套/异常/非法输入恢复、干湿干恢复、完整绑定蒙皮、骨盆/四肢/T-pose、reset、VMD采样、会话关闭原 mesh/管线恢复。

相机诊断检查的是本实现 fragment 是否收到了输入，不是官方截图的像素拟合；干湿干检查只是开关可逆性。两种相机入口均覆盖83102个被标记的布料 fragment。既有 light 688、environment、atlas普通cutout 26、material uniform 225分量、shadow consumer 238、shadow lifecycle 13、MMD format/radian/root-space回归通过。

Python全套470 passed /3历史skipped /80 subtests，2个既有Pillow弃用提示；本轮导出器测试16 passed /24 subtests、两文件合计94%行/分支合并覆盖。Ruff/Pyright通过。没有测量 Unity C#/HLSL 整工程行覆盖，不以513条检查宣称80%整工程覆盖。

过程日志/旧失败报告保留在 `D:/EndfieldTechLib/notes/wetness-mmd-start-20261001-01/` 与 `Validation/wetness-20261001-{02..12}/`。早期450/468等“PASS”没有覆盖实际 wet gate 或骨盆手性，**不可当作交付依据**；最终以12目录和本说明为准。07目录保留新骨盆门禁的真实失败；不删除、不放宽。

主HEAD/9557项暂存条目、原官方场景、Graphics/QualitySettings、已有封存文档不纳入本轮提交。一次 git status 的索引 stat-only 刷新，在确认所有 staged entry 完全一致后恢复了进入本轮时的原始索引字节。记录仍采用独立 index/commit-tree 分支，不顺带提交历史9555个staged paths。

触及文件中原有的工作副本改进保留（例如 ClipDriver 先前的诊断入口与解包动作配置路径），不把记录分支相对 parent 的全部差异冒称本轮新写。源代码 diff-check 通过；Unity自动生成 `.meta` 空字段和原始失败日志的尾空格保留、不改取证日志。临时Python工具环境 pip-audit 无已知漏洞，不代表 Unity 全依赖审计。

## 5. 未完成项与下一步

- 当前湿身只覆盖 cloth01/02。先核实皮肤/头发/丝袜/清漆对应 actual PS 的天气块及原生输入，再逐类接入；不能把 b400 或 LiquidAg snow 块当作本角色全部天气实现。
- 源天气遮挡、水线 per-object producer、雨/雪累积和干燥没有还原；手动组件只提供正确输入布局。
- 更早的真实 D16 atlas/bias/scissor/分区、stencil域/R producer、Overlay等仍按 shadow-atlas-writers 清单待办，不因湿身预览通过而消失。封存基石的79/24 pending不改写成已完成。
- 请先实测 MMD 起始姿态与上述单个动作：完整时域、脚接触/防滑、源自定义 IK、表情骨映射、头发裙摆物理、相机、音轨、整段 MP4均应各自验证。当前窗口不是“任意源模型/任意动作一键完美”的结论。
- 所有 native 输入是可逆编辑器会话加载。正式常驻场景/打包资源和独立 batch 导出统一入口尚需后续设计；本轮不改 Unity6、LOD、性能适配或其他研究范围。
