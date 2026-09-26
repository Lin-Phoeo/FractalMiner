# HANDOFF 2026-09-26 — 动画系统：RM 破译完成 / 躯干跟随待收尾

> 移交对象：Gemini（或任何后续会话）。本文档是动画管线的权威状态，接手前必读。
> 前置阅读：`HANDOFF-2026-09-25-m5-geometry-solved.md`（渲染 M5 已闭环，与本文档正交）。

---

## 0. 一句话现状

终末地 ACL 动画已全量解码（333/333 transform 轨 + 333/333 **RootMotion 破译**），
但 battle 类动画的**四肢/躯干主骨不在 transform 轨里**（官方运行时程序化驱动），
目前用"解析式两骨 IK + RM 根骨驱动"近似，**躯干能位移、四肢会动但姿态乱**
（"僵尸乱摆"）。社区无人真正解决过此问题（详见 §5）。

## 1. 用户目标与硬要求（长期有效）

- 目标：复刻提弗洛斯(chr_0034)官方渲染 + 动画 → 最终接 MMD .vmd 做视频
- 每步必须有截图/数值证据，"编译过了"不算完成
- 门禁阈值先写死再看结果，不许事后放宽
- 每完成一步：隔离 index 提交 fix 分支 → push endfield-records
- **协作模式**：用户在 Unity 编辑器亲手验证（Endfield/Anim Studio 窗口），
  不要走 batchmode 渲染验证（batch 与用户编辑器冲突会崩，
  且像素差分被动态自阴影污染不可信）

## 2. 已实锤的技术事实（勿重新推导/验证）

### 2.1 ACL 动画布局
- 标准 ACL 2.1.0（tag 0xAC11AC11），Endfield 包装：3B uint24 size + 'ROUF' + ACL blob
- Transform 轨 track_type=12 (qvvf)；**RootMotion 轨 track_type=0（float1f 标量轨！）**
  —— 用 transform 解码器解 RM 会 segfault，必须用 `default_scalar_decompression_settings`
  + `write_float1(scalarf_arg0 → rtm::scalar_cast)`
- FloatBufferData(151轨) 前 28 轨 = RM 超集；轨 149 ≈ NormalizeTime(0→0.2 线性)
- TransformSubTrackMasks：位图 2bit/输出轨（pos+rot），几乎全 1（仅轨 180-182 cloth cuff 缺）

### 2.2 RootMotion 布局（本轮核心破译，社区独一份）
- `RootTrackCount/7` = 驱动骨数（attack_01=4，gacha=3），bone-major 每骨 7 float
- **语义：chr 根局部空间（Unity Y-up），无需任何坐标换算**（Z-up 换算是错的，
  被用户实测否定：bone0 直写正确落脚下，走换算的全飞）
- attack_01 四骨实测：
  - bone0 = Root 节点：f300 pos=(0,0,2.26) → **整体前冲 2.26m**（用户实测球在脚下 ✓）
  - bone1 ≈ bone0 + 常量肩锚偏移 (-0.02,0.97,0)：f50=(-0.03,0.49,2.26)=半蹲+前冲
    quat 直读 euler=(-7.7,22.8,3.2)° 持械姿态 ✓
  - bone2/3 = 左右臂相关驱动（euler y≈-90 与臂骨绑定同构，f150 挥至 -142/-110），
    精确语义未定
- **决定性对照**：gacha（主骨齐全）RM 全恒定 identity；battle（主骨缺失）RM 大幅运动
  → RM 就是主骨动画的运行时数据源
- IK_Root/IK_Hand_* 的 transform 轨**恒零或模型空间值**：IK_Hand_Knee_Foot 轨是
  "相对 Root 的模型空间"目标（y 0.48..1.06 手高/0.10..0.47 脚，合理）

### 2.3 动画轨内容
- 362 轨 = 头发/表情/手指/武器/twist/corrective/IK 目标轨
- **四肢主骨（UpperArm/Forearm/Hand/Thigh/Calf/Foot/Clavicle/Spine/Spine1/Spine2/Pelvis）
  全部缺席**（gacha 等 UI/interact 类 clip 例外：主骨在轨里）
- animation rigging 包的 `RigLayer.Update()` 只同步参数不求解（PlayableGraph 管线，
  batch 编辑器不 evaluate）——离线必须解析 IK

## 3. 当前管线（EndfieldAnimStudio / EndfieldAclIkDriver v8）

每帧：
1. `clip.SampleAnimation`（播 362 轨：头发/表情/手指/武器/IK 目标）
2. RM 驱动：bone0→Root.local（位移），bone1 的 delta→Bip001_Pelvis（躯干跟随近似）
3. 解析式两骨 IK（余弦定理+极向量）：ArmR/L 钉 IK_Hand_*_001，LegR/L 钉
   IK_Foot_*_001（极向量 IK_Knee_*_001），tip 旋转=target×绑定偏移
4. 渲染（M5 捕获管线：atlas caster→GBuffer→16-tap resolve→CapturedPost）

**v8 是刚写的、未验证**。v7 状态（用户已测）：RM 生效、全身在动、
但"僵尸乱摆"——探针实测 ArmR/L err=1.06/0.89m（臂长仅 0.55m，目标超程 2 倍
→ 余弦解疯狂翻转）。

## 4. "僵尸乱摆"根因分析（下一步从这里开始）

**目标超程的机制**：IK 目标轨（IK_Hand）是"模型空间"值——含躯干前倾/位移的
贡献。但躯干主骨恒定=肩钉死在绑定位置。官方：RM bone1 驱动 Spine/Clavicle 链 →
肩跟着目标走 → 目标可达。我们缺"肩跟随"。

**v8 已实现的近似**：bone1 delta → Pelvis（位移+旋转）。这能让肩大致跟随，
但 Pelvis 旋转对肩位置的传导不精确（肩高 0.97 vs pelvis 0.82，杠杆不同）。

**建议下一步（按优先级）**：
1. **验证 v8**：Play 看探针 err 是否收敛（<0.2m 可接受），动作是否像样
2. 若 err 仍大 → **躯干链 IK**：把 RM bone1 位姿作为 Spine2 的目标（两骨
   IK：Pelvis→Spine1→Spine2，target=bone1 世界位），锁骨再单独跟随（Clavicle
   旋转 = 从 Spine2 指向 IK_Hand 目标的方位角）
3. **Clavicle 跟随**（低成本高收益）：每帧把 Clavicle.localRotation 朝
   IK_Hand 目标方向偏转，扩大臂可达域
4. 对比验证基准：gacha clip 主骨齐全可直接播（无需 IK），作为"正确姿态"
   的参考实现——**推荐先用 gacha/interact 类 clip 打通渲染，再回头攻 battle**
5. 武器：IK_Weapon_L/R 轨有异常值（y -4.62），接入前需清洗

## 5. 社区调研结论（07:19，已核实）

| 方案 | 状态 |
|---|---|
| UP主死夢めぐり(BV1Eu9BBuExe) | 只有 shader 开源；动画"挂 Unity 自带 IK 近似"（自认垃圾、
  不敢配布——律师函）；repo 无动画代码 |
| AnimeStudio(Escartem) | 终末地**仅模型/贴图**提取成功，动画未实现 |
| AnimeStudioUltimate(ZZZ fork) | ZZZ(HoYo系) ACL 全解码直接可用——**HoYo 架构没有
  终末地这种"主骨运行时驱动"**，方案不可移植 |
| EFMI Tools | 终末地 Blender mod 链，仅网格/贴图 |

→ **社区无人实现终末地 battle 动画在游戏外的正确播放**。我们的 RM 破译是独一份。
没有可抄的现成轮子，必须自己补全"官方 solver 的近似"（§4 路线）。

## 6. 关键文件地图

```
FractalMiner/
  Assets/EndfieldShaderPack/Editor/
    EndfieldAnimStudio.cs      # 交互验证窗口（v8，用户操作入口）
    EndfieldAclIkDriver.cs     # batch 渲染驱动（v2 解析IK，可后续同步 v8）
    EndfieldClipBindDiag.cs    # 绑定诊断
    EndfieldAclAnimImporter.cs # frames.json → .anim（333 个已导入 24GB）
  Assets/Typhoeus/
    AnimationsDecoded/*.anim   # 333 解码 clip（本地 24GB，不入库）
    rootmotion-<clip>.json     # 333 个 RM 数据（25.8MB，本次已入库）
  Validation/
    anim-ik-*/                 # batch 渲染输出+report
    anim-studio-diag.txt       # Studio 诊断输出
  _unity_bridge.bat            # schtasks 计划任务 EndfieldUnityBridge 载荷
                               # （当前=compile-check；协作模式别跑 batch 渲染）
EndfieldUnpacker/
  _acl_decode.cpp/_acl_decode.exe          # transform 轨解码器（qvvf）
  _acl_decode_rm.cpp/_acl_decode_rm.exe    # RM/Float 解码器（scalar）★新增
  _build_acl_decode_rm.bat                 # SDK 必须 22621、rtm 在 _acl_src/rtm-2.3.0
  _rm_blobs/*.rm.bin                       # 333 RM 原始 blob
  _batch_export_rm.py  （见提交记录；重导出 framesFlat 格式）
  _anim_decoded/*.frames.json              # 333 解码 transform 数据
  _anim_track_paths/*.paths.json           # 362 轨的路径映射
  _anim_json_all/AnimationClip/*.json      # 游戏原始 typetree JSON（含 m_AclCompressedBuffer）
```

## 7. 操作手册（用户侧）

- Unity 打开 FractalMiner 工程 → 菜单 **Endfield/Anim Studio**
- Load Scene → 选 clip（默认 attack_01）→ Play / 拖 Time / Frame+1
- 勾选 **Apply RootMotion** 开启 RM 驱动
- 探针区：每链 tgt(目标)/tip(末端)/err(距离)；RM 行显示 4 骨位置
- Scene 视图：黄色 IK 链 + 红球(IK目标) + 绿球(末端) + 白球(RM 骨)
- 判读：tgt 变+err 小 = 正常；tgt 变+err 大 = 肩不跟随（当前状态）；
  tgt 不变 = Sample 问题

## 8. Git 状态

- 分支 `fix/typhoeus-render-explosion-20260917`，本次移交提交见 git log
- remote `endfield-records`（LinXingjian365/FractalMiner），push 用
  `env -u HTTP_PROXY git -c http.proxy=http://127.0.0.1:7890 push endfield-records <branch>`
- 隔离 index 流程：GIT_INDEX_FILE 用 Windows 路径；hash-object 必须 -w；
  update-index --cacheinfo 加新文件必须 --add；沙箱内 update-ref 不可靠直接写 loose ref
- push 大文件 >数GB 会 408；25.8MB RM json 已验证可推

## 9. 已踩坑速查（全部实测）

1. JsonUtility 不支持 List<float[]> → 用扁平 framesFlat + stride
2. RM 用 transform 解码器解会 segfault（track_type=0 要 scalar 设置）
3. Z-up→Y-up 换算是错的：RM/ACL 数据已是 Unity 语义 local
4. Animation Rigging RigLayer.Update() batch 下不求解
5. batch Unity 与用户打开的编辑器冲突：ProjectAlreadyOpenInAnotherInstance 崩溃
   （exit=1073741845）→ 协作模式别跑 batch
6. 场景 Typhoeus_SourceFBX prefab 是停用参考骨架（m_IsActive:0），Hierarchy 里
   看到两套 Bip001 正常，不碍渲染
7. MSVC 编译 RM 解码器：SDK 用 10.0.22621.0（26100 缺 ucrt 头）、rtm 用
   _acl_src/rtm-2.3.0（acl external/ 目录里没有）
8. MSVC 编译含中文注释的 cpp 会报 C4819 警告 + 字符串字面量换行坑
   （python heredoc 写 \n 注意转义）

## 10. MMD 接入（⚠️ 2026-09-26 更新：出现游戏内现成路线，优先级重排）

### 路线 A（推荐先走）：终末地游戏内 MMD Mod —— 现成、官方渲染质量

**关键情报（2026-09-26 用户发现）**：
- B 站视频【终末地MMD Mod现已支持导入镜头】https://b23.tv/SXrIAL0
  （2026-09-26 发布）——社区已实现游戏内 MMD 动画+镜头导入
- GameBanana 已有舞蹈动画 mod 实例：
  https://gamebanana.com/mods/668041 （Yvonne 极乐净土，作者 ffll1）
  - 热键：Alt+> 播放 / Alt+< 暂停 / Alt+Ctrl+/ 面板
  - 面板支持：播放速度调节 + 进度条拖动
  - 已知限制：不含表情；LOD 阴影不跟随（大世界）；实验性
- 工具链背景：XXMI Launcher + EFMI（Endfield Model Importer，3dmigoto 系）
  - EFMI: https://github.com/SpectrumQT/EFMI-Package
  - EFMI Tools(Blender): https://github.com/SpectrumQT/EFMI-Tools
  - 另有 3dmigoto-arknights-endfield 独立启动器分支

**为什么 mod 能"完美"而离线重建难**：动画数据注入游戏运行时后，
游戏自己的 SkeletonConstrainData/IK/程序驱动层全部正常工作——
这从反面证实了我们的诊断（离线缺的就是运行时求解层）。

**给用户出视频的最短路径**：装 XXMI Launcher + EFMI → 用社区 MMD mod
工具链转换 VMD → 游戏内播放 + 镜头导入 → 官方渲染直接录屏。
Unity 离线管线（本仓库）转为研究/实验平台。

### 路线 B：Unity 离线管线（本仓库，研究向）

- 解码 .anim 已就绪：VMD→anim 用 MMD4Mecanim/VroidMMDTools，姿态源替换
  SampleAnimation 即可，解析 IK rig 不变
- MMD 动作是"全骨骼关键帧"（无运行时驱动概念）→ 不存在主骨缺失问题，
  接入难度低于官方 battle 动画
- **诊断工具已备**：Anim Studio"导出骨架快照"按钮（当前帧全骨骼
  世界/局部位姿 → Validation/skeleton-snapshot.json）——离线分析的
  权威数据源，凡是坐标语义疑问都从它取真值，不要手写四元数 FK 猜
- battle 官方动画的躯干跟随收尾（§4）继续作为研究课题：
  已确认 IK_Hand 轨=官方求解结果回写（gacha 0 误差），缺肩跟随；
  Clavicle 跟随（v9，默认关）+ 躯干链 IK 是方向；bone2/3 语义未定
