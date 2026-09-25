# HANDOFF 2026-09-25 — 3a 姿态应用闭环（姿态提取→Unity 渲染全链路完成）

> 前置文档：RESUME-2026-09-23-captured-pipeline.md、QODER-HANDOFF-2026-09-23.md。
> 本文档为最新权威状态。记录分支 fix/typhoeus-render-explosion-20260917。

## 0. 一句话状态

**3a 姿态链路全闭环**：捕获帧 6411 的 SSBO 骨骼姿态（268/481 骨映射）已成功驱动
Unity 重建设角色的蒙皮网格，渲染出与官方帧一致的"低头双手胸前持书"姿态，
三道骨骼门禁（世界系）全部通过。

证据：`Validation/pose-apply-01/pose-applied.png`（1280×720）+
`pose-apply-report.json`（pass=true）。

## 1. 今日（09-25）三层根因——姿态应用调试全记录

姿态应用脚本 `EndfieldPoseApplyValidation.RunPoseApply` 连续踩中三个互相掩盖的坑，
每一层都让上一层的现象具有迷惑性。**以后给该场景写任何骨骼操作代码，先读本节。**

### 坑 1：空壳 "Armature" 节点（已修）
场景里有个**没有子节点**的空 GameObject 叫 `Armature`（挂在角色根下）。
`FindDeep(root, "Armature")` 先命中它 → Collect 只得 1 个"骨骼" → applied=0。
真实骨架链：`chr_0034_typhoea_rebuilt > Root > Bip001 > Bip001_Pelvis > …`。

### 坑 2：停用 FBX prefab 里的第二套完整 Bip001 骨架（已修，最阴）
场景根列表（按序）：Main Camera / Directional Light /
**Typhoeus_SourceFBX（`Assets/Typhoeus/chr_0034_typhoea_uimodel.fbx` 的 PrefabInstance，
m_IsActive=0，内含自己完整的一套 Bip001 同名骨架）** /
chr_0034_typhoea_rebuilt（**可见**角色，17 个 SMR）/ CharacterLight。

`FindDeep` 不检查激活态、按根顺序先钻进 prefab → 我们把 268 骨姿态
**全部写进了停用 prefab 的骨架**：探针读回正常（停用物体的 transform 照样算）、
门禁"通过"（数值落在合理区间纯属巧合——A-pose 与持书姿态的手部范围有重叠）、
但渲染纹丝不动（可见 SMR 绑的是重建设那套）。

决定性证据（运行时探针，写代码必读手法）：
```csharp
ReferenceEquals(hairSmr.bones[headIdx], headTransformWeMoved) // false!
// hairSmr.bones[1] instanceID=31416（重建设） vs 我们移动的 head instanceID=-1934（prefab）
```
修复：锚定 `scene.GetRootGameObjects()` 中**名字为 chr_0034_typhoea_rebuilt** 的根，
再在其下 FindDeep("Bip001_Pelvis")。**教训：同名骨架×2 的场景里，
一切按名查找必须先锚可见角色根；探针数值合理≠作用在正确对象上（bbox 不可信教训的
Transform 版）；跨对象同一性用 ReferenceEquals/instanceID 判。**

### 坑 3：Root 节点 -90°X 的坐标系转换（已修）
锚对骨架后渲染出"脚底一坨面朝下的破布"。原因：姿态矩阵是捕获模型空间（Y-up），
而 `chr_0034_typhoea_rebuilt` 自带 -90°X（Root 局部系是 Z-up：bind 头在 z=+1.27）。
直接把 Y-up 姿态当 Root 相对世界写入 → 整体被 -90°X 拍倒。
修复：映射骨 `newWorld[t] = rootFix * pose`，其中
`rootFix = armature.localToWorldMatrix.inverse`（armature=Root 节点）。
同时**门禁探针从 Root 相对系改为世界系**（角色根在原点，rootFix 后世界==捕获模型系），
否则会重蹈"探针与渲染各说各话"。

## 2. 当前验证结果（run 09-25 09:39，exit=0）

| 探针（世界系） | 实测 | 门禁 |
|---|---|---|
| Bip001_Head | (−0.043, 1.258, −0.065) | y∈[1.15,1.40] ✅ |
| Bip001_L_Hand | (−0.167, 1.009, 0.070) | y∈[0.85,1.25], \|x\|∈[0.05,0.45] ✅ |
| Bip001_R_Hand | (−0.194, 1.128, 0.191) | 同上 ✅ |
| Bip001_Pelvis | (−0.033, 0.815, −0.053) | （参考） |

- pose file 268 骨全部 applied，145 骨 kept bind（重建设 Root 下共 413 transform；
  注：FBX prefab 那套是 428，别混淆）。
- bind（preApply，世界系）：Head (0, 1.269, −0.011)、L/R_Hand (±0.335, 0.873) 对称 A-pose
  → 姿态确实从 A-pose 变成了持书姿态。
- 渲染：角色直立、头微低、双手交叉于胸前（持书）、马尾随姿态摆动、尾巴在后。
  **书本体不可见**——书是独立 prop，不在本场景 17 个 SMR 内（后续若要整帧对照需单独处理）。

## 3. 关键文件

- `Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs` — 姿态应用+门禁+渲染。
  场景不保存（内存中应用姿态）。含详细注释记录上述三坑。
- 姿态数据：`Validation/Captures/tifuluosi-front-20260917/pose-full-01/pose_apply.txt`
  （268 行 `boneName\t16 floats`，行主序 M×v、平移在列 3，捕获模型空间 Y-up）。
- 产物：`Validation/pose-apply-01/pose-applied.png` + `pose-apply-report.json`。
- 工具链（53e9230 已入库）：Tools/export_pose_full.py、match_pose_slots.py、
  build_pose_apply.py（`bonePose = M_ssbo × inv(bindpose)`，delta 约定）。

## 4. 复现命令

```bash
# bat 必须 CRLF（sed -i 's/\r\?$/\r/' _unity_bridge.bat），载荷：
#   -executeMethod EndfieldShaderPack.EditorTools.EndfieldPoseApplyValidation.RunPoseApply
schtasks //run //tn "EndfieldUnityBridge"   # ~30-110s
cat Logs/bridge-marker.txt                  # exit=0 即门禁通过
cat Validation/pose-apply-01/pose-apply-report.json
```

## 5. 下一步（按优先级）

1. **与官方帧分区域对照**：pose-applied.png vs official-front-1280.png
   （PIL 区域均值/轮廓差分；注意书 prop 缺失、相机/FOV 是否已与捕获一致——
   相机在 (0,0.844,3.11)，旋转 (0,±1,−0.004,0) ≈ 180°Y）。
2. **多视角验收（B 轨收尾）**：转动相机/角色/灯光重跑 live 三关；
   新帧截取用 RenderDuck_v1.4（`C:\Users\Administrator\Downloads\RenderDuck_v1.4\`，
   官方 RenderDoc 会被 ACE 检测；旧 .rdc 仍可用官方 qrenderdoc 回放）。
3. 未映射 145 骨中的 corrective/twist 骨：目前保持 bind，远看无虞，
   近景对照时若关节处蒙皮对不上再回来补映射。
4. 长线：表情/镜头半身构图、局部覆盖层/透明/dither、cloth §10/§11、eye 折射、
   A 轨遗留（烘焙脸仍黑、身后多余脸）、MMD 重定向（481 骨姿态输入已具备）。

## 6. 运维备忘（沿用，勿再踩）

- bridge bat 必须 CRLF；printf 会吃 `\U`/`\E` 转义（用 Write 工具 + sed 补 \r）。
- 挂起 cmd 会阻塞计划任务（"已排队"）：`ps -W | grep -i unity`，taskkill //PID <第4列> //F。
- 编辑模式 `camera.Render()` 两次调用同帧第二次可能不刷新——渲染验证一次一进程。
- push 失败走 `env -u *_PROXY git -c http.proxy=http://127.0.0.1:7890 push`。
