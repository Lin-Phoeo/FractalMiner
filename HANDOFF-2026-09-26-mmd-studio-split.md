# HANDOFF-2026-09-26-mmd-studio-split.md — MMD 独立化 + 交接文档

> 生成：2026-09-26 13:30（WorkBuddy 会话）
> 分支：`fix/typhoeus-render-explosion-20260917`（已 push 到 endfield-records）
> 给下一个 Agent 的完整状态。读这份之前先读 `.workbuddy/memory/MEMORY.md`（项目长期记忆）。

---

## 1. 本轮干了什么（按时间序）

| 提交 | 内容 |
|---|---|
| 891c6ac | 修复 26 个编译错误（Safe Mode 事件）：命名空间 using、MmdName 缺失类、VQuat/VVec3 转换助手、reader 可见性、Debug 二义性等 |
| b71e712 | 修复“只有个头在视频上方”三根因：① T-pose 校准单位坑（0.9 阈值是 MMD 单位，米制角色必失败）② 相机 basis 混入 M5 枢轴的 -90°X 俯仰 ③ 帧域混用（渲染 60fps vs VMD 采样固定 30fps，动作被拉慢 2 倍） |
| （待提交）| **MMD 独立化**：新建 `EndfieldMmdStudio.cs`（唯一 MMD 面板：编辑器内播放 + 出片一体），Anim Studio 剥离全部 MMD 代码回归纯 ACL 工具，批渲染器三个方法改 public 供复用 |

**尚未编译验证**：用户 Unity 一直开着占项目锁，桥接（EndfieldUnityBridge 计划任务）两轮被锁顶掉（exit=1073741845）。**接手第一件事：确认用户关 Unity → `schtasks //run //tn "EndfieldUnityBridge"` → 看 Logs/compile-check.log 零错误 → 若有错修掉再提交**。工作树包含未提交改动：EndfieldMmdStudio.cs（新）、EndfieldAnimStudio.cs、EndfieldVmdBatchRender.cs。

## 2. 现在的 MMD 工具格局（拆分后）

```
Endfield/Anim Studio      → ACL 官方动画专用（clip 播放/IK 探针/RootMotion），MMD 功能已全部移除
Endfield/MMD Studio       → MMD 唯一入口（新）：打开 VMD → 编辑器实时播放（Scene/Game 视图）
                             → 调镜头/位移比例 → 一键出片（PNG 序列 + ffmpeg MP4）
Endfield/VMD Batch Render → 保留（老批渲染入口，参数更全：分辨率/帧范围/音频），与 MMD Studio 共用
                             SaveFrame/Mux/FindFfmpeg（已改 public static）
```

**共享库 `Assets/EndfieldShaderPack/Editor/Mmd/`（6 个文件，勿轻易改）**：
- `VmdMotion.cs` — VMD 0002 解析 + 贝塞尔采样 + 表情/IK/镜头轨（cp932 Shift-JIS 名称）
- `MmdRig.cs` — 标准 MMD 半身 rig 定义（166 骨硬编码）+ MmdIk 两骨解析 IK + 数学助手
- `MmdRetarget.cs` — T-pose 校准（MmdCalibration.MakeTPose）+ 55-role 映射 + 逐帧 retarget + 足 IK
- `MmdNames.cs` — 名称归一（全角数字/I/K → 半角）
- `MmdPlayer.cs` — 播放核心（Load/Reset/ApplyFrame/Recalibrate）+ MmdCameraDriver（WorldBasis！）+ MmdFace 表情层
- 关键修正都在：MakeTPose 尺度归一（胸高×0.25）、WorldBasis（只取水平偏航）、30fps 帧域

**角色/场景**：`Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity`，角色根 `chr_0034_typhoea_rebuilt`，M5 枢轴 `Euler(0,45.5,0)*Euler(-90,0,0)` 挂在 Armature 父节点（EnsureScene 自动设）。

## 3. 播放为什么此前“只能渲染”——现在怎么解决的

旧结构里 VMD 驱动寄生在 Anim Studio 的 `SampleAndSolve`（依赖它的 `Tick` 播放循环和 `charRoot`），批渲染器又独立调用 MmdPlayer，两边 UI 状态不互通，用户在 Studio 里载入 VMD 后没有独立播放控制（按钮都在 ACL clip 域）。

新 `EndfieldMmdStudio`：
- 自带 `EditorApplication.update` 播放循环（Tick：时间推进 → ApplyAt(time) → SceneView.RepaintAll）
- ApplyAt = player.Reset → ApplyFrame(30fps 域) → 镜头驱动
- 播放/暂停/逐帧/进度条/循环全有；镜头 VMD 载入后 Scene/Game 视图即时可见
- 出片 = 同一个 ApplyAt 数学，`EditorApplication.update` 泵迭代器分帧渲染（编辑器不卡）
- 自动带出：载入动作 VMD 时若同目录有 Camera.vmd 自动挂镜头

## 4. 已知问题清单（交接必读）

1. **EndfieldMmdStudio.cs 未编译验证**（Unity 锁）——先跑桥接。写的时候修过 `camDriver.tar`/`/c/` 粘贴错误，但按经验必须全量重编才算数
2. **表情不动的根因**：提弗洛斯重建脸是 BakeMesh 烘焙网格，**没有 blendshape**——MmdFace 只能报“烘焙脸不支持形变”。要做表情得换有 blendshape 的脸网格（长线任务）
3. **眼神轨（両目）无人接收**：重建骨架没有眼球骨骼。要做眼神得挂眼球骨（长线）
4. **cam.vmd 只有 12 帧问题依旧**：Butt Dance 的镜头轨只覆盖动作前 19 秒（此后 SampleKey clamp 到末帧=静止机位）。不是 bug，是数据本身这么短；出片建议用自带完整镜头轨的动作（如 UNFORGIVEN）
5. **上一轮三根因修复（b71e712）也未经过渲染验收**：动作垮掉/头顶出画/时长错速修复后**没有重渲过一帧**——接手后需要：MMD Studio 试拍 5 帧 → PIL 数值门禁（前景 bbox 水平占比>25%、无 y=0 顶部裁切带）→ 不过再查 retarget
6. **Anim Studio 剥离后行为变化**：mmdMode 通路删除——如果用户之前靠 Anim Studio 播 VMD（现在走 MMD Studio），播放/暂停键布局变了。功能等价
7. **桥接批处理载荷**：当前 `_unity_bridge.bat` 是纯编译检查（`-quit`）。若要桥接跑批渲染/其他自动化，改写载荷后 `schtasks //run //tn "EndfieldUnityBridge"`；跑之前必须确认用户已关闭 Unity（`ps -W | grep Unity.exe`）

## 5. 验收门禁（用户硬要求，先写死阈值再看结果）

- 编译：桥接全量重编 `error CS` 计数 = 0
- 出片试拍（5 帧）：PIL 前景 bbox：水平占框 ≥25%（此前 7-17%）、顶部 y=0 无 ≥100px 宽连续前景带（头顶出画特征）
- 整段渲染：帧数 = VMD lastFrame+1（30fps 域）、MP4 时长 ≈ 音频时长（-shortest 截断前）
- 每步：截图/数值证据留档 Validation/；完成即隔离子提交 push；门禁不过不进下一步

## 6. 给下一个 Agent 的操作顺序

1. 读 `MEMORY.md`（长期记忆：桥接用法、git 隔离提交流程、四个已实测纠正的坑）
2. 确认用户关 Unity → 桥接编译 → 有错修错（重点看 EndfieldMmdStudio.cs）
3. 提交 MMD 独立化改动（隔离 index 流程见 MEMORY.md「Git 工作流」）
4. 让用户在 MMD Studio 里：打开动作 VMD → 播放（编辑器内直接看）→ 调镜头偏航/位移比例 → 试拍 5 帧 → 跑数值门禁 → 整段出 MP4
5. 若舞蹈形态仍怪：对照 `[4](#4-已知问题清单)` 逐条排除；retarget 数学源自 OedoSoldier/Endfield-Poser（AGPL-3.0），参数语义在 MmdRetarget.cs 注释里

## 7. 用户长期目标（别忘）

MMD 舞蹈视频（提弗洛斯跳 UNFORGIVEN）→ AI 视频素材。所以出片质量优先于一切复刻门禁；A 轨遗留（烘焙脸黑/身后多脸）只影响官方帧复刻，不影响视频。
