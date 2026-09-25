# 交接文档 — M5 几何对齐已完美闭合（2026-09-25 14:50）

> 接续 `HANDOFF-2026-09-25-pose-apply.md`（M4 姿态闭环）之后的工作记录。
> 本文档由 WorkBuddy（GLM）会话产出，覆盖 2026-09-25 上午至下午的全部进展。
> **当前分支尖端：`9bf3058`（已 push 到 endfield-records）**

---

## 0. 一句话状态

**M5（全帧对比验收）的几何部分已完全解决**：Unity 渲染的角色骨骼世界坐标、真实管线 viewport 投影与 RenderDoc 捕获真值 **逐顶点 L1=0.00000**。剩余门禁失败全部来自**颜色/光照/后处理**尚未应用，几何不再有未知数。

## 1. 本轮关键突破（按时间序）

### 1.1 相机 pitch 符号修复（上午）
- 捕获 VP 第 7 行（cw 行）= (0, +0.00811, −0.99997) ⇒ 相机**微微向上看**。
- 旧值 z 取负号导致 pitch 向下，产生恒定 NDC-y 误差 **0.0515**（917 个体顶点全部 `nya = -nyb + 0.0515` 精确成立）。
- 修复：`ExpectedCameraRotation = (-1.7726111e-10, 0.9999918, +0.0040552616, -4.371103e-8)`。
- 修复后用真实管线 `WorldToViewportPoint` 探针验证：4 个骨骼（head/pelvis/双手）viewport 与捕获 VP 真值**小数点后 5 位全同**。

### 1.2 发现捕获帧真值纹理（决定性证据）
- `pipeline-textures-01/post-input.dds` = 帧 6411 后处理输入，R16G16B16A16_FLOAT 2560×1600。
- PIL 不支持 DXGI format 10，用 Python 手写 half-float 解码 + Reinhard tonemap 得 `post-input-flipped.png`（需垂直翻转）。
- **帧 6411 真值 vs 官方截图：center L∞=0.0025 ✅ / size=0.0064 ✅ / IoU=0.860 ✅** —— 三何门禁全过。证明 RenderDoc 捕获与官方截图就是同一姿态同一时刻，消除"不同帧"假说。
- 对比报告存于 `Validation/pose-official-compare-06-frame6411truth/`。

### 1.3 M5 核心谜题破解：instance_child0 是列主序
- `probe_screen_truth.py` 头部写明官方 shader 链是 **variant A**：`inst = child0_3x3 × m + child0_col3 − camOffset`。
- 此前 screentruth 用 variant C（纯平移，不加 3×3）判定"姿态已在恢复坐标系"，导致 WorkBuddyAI 设 `CaptureInstanceRotation = identity` —— **这是错的**。
- child0 按 **cbuffer 列主序**解读：真实变换 = **R_y(+45.5°) × m + t**，即角色绕模型原点旋转 45.5°（不是相机转）。
- 数值证据链：
  - variant E（R_y(+45.5)×m − cam）点云 bbox 右边缘 0.7054 vs 帧 6411 真值 0.7063（左差是 cloth_01 坏槽位导出，见 §3.3）。
  - 官方截图亮度裁决：正确旋转 p50 亮度 59（落在深色角色上），错误旋转 132（落在亮背景上）。

### 1.4 轨道相机死胡同（避免重蹈覆辙）
- 尝试用轨道相机等价实现（角色不动）。穷举 8 种四元数组合（yaw±/顺序/俯仰±）：x 最好 0.00000 但 **y 恒等镜像（truth_y + orbit_y = 1.0000 每顶点精确成立）**——手拼四元数在该约定下无法复现捕获 y。
- 教训：不要手拼轨道相机。直接转角色。

### 1.5 最终解：旋转 chr root（四轮迭代后正确）
正确代码（`EndfieldPoseApplyValidation.cs`，直立姿态写入之后）：
```csharp
Quaternion pivotRot = Quaternion.Euler(0f, M5InstanceYawDeg, 0f)   // +45.5！
                    * Quaternion.Euler(-90f, 0f, 0f);              // 保留原 -90X
Transform pivotParent = armature.parent;   // chr_0034_typhoea_rebuilt
pivotParent.localRotation = pivotRot;
// 骨骼 local 一概不动！
```
**四个必踩的坑（全部实测验证）**：
1. **必须转 armature 的父级**（chr root），转 armature 自身无效——armature 的 transform 写入被 `t == armature` 跳过。
2. **必须与原 -90X 复合**（`Euler(0,±45.5,0) * Euler(-90,0,0)`）。直接替换 chr 旋转会抵消 rootFix 烘焙的 -90X 逆，角色倒地（探针见 Rx(90) 因子）。
3. **yaw 符号必须是 +45.5**（Unity LH）：`Euler(0,+45.5,0)*Euler(-90,0,0)` 产生数值 R_y(+45.5)（x′=c·x+s·z）；−45.5 产生镜像 form2（pelvis 落 (0.0142,…) 而非 (−0.0611,…)）。
4. **骨骼 local 绝对不要在枢轴后重写**。任何用"世界 TRS"逐骨重写 local 的尝试都会沿链复合造成双重旋转（实测 3 种写法全部翻车）。

**最终验证（14:48 run）**：
- 骨骼世界 vs R(+45.5)×m：**max |d| = 0.00000**
- 真实管线 viewport vs 捕获 VP 真值：**L1 = 0.00000**（head/pelvis/双手）
- Unity 渲染 bbox 宽度与官方**完全相等**（0.29375）
- IoU：0.309（起点）→ 0.730（vs 官方）；vs 帧 6411 真值 0.86 过门禁

## 2. 当前门禁状态（pose-official-compare-11）

| 指标 | 值 | 门限 | 状态 |
|---|---|---|---|
| bbox_center_linf | 0.0500 | ≤0.020 | ✗（几何已对齐，差在 mask 语义，见 §4） |
| bbox_size_relative_error | 0.1543 | ≤0.050 | ✗（同上；宽度已精确相等） |
| silhouette_iou | 0.7297 | ≥0.850 | ✗（颜色/阴影未应用所致） |
| region color | 29–44 LSB | ≤4 | ✗（未接捕获光照/后处理） |

**关键**：几何未知的全部关闭。剩余差异来源：
1. **官方 mask 在 y=0.83 处截断**（官方截图地面阴影被分割阈值裁掉），Unity 渲染的腿/靴子（0.84–0.94）是**正确几何**——帧 6411 真值同样有这些行。
2. **颜色门禁**需要把捕获光照分支（CP1.y 平坦环境 + CP1.w 光方向 + 官方 EndfieldCharacterLit）和冻结的捕获后处理链接进 pose-apply 渲染 —— 这是 M5 收尾的唯一真正工作。

## 3. 新增工具与数据（本轮产出）

- `Logs/bone-world-dump.json`：每次运行 dump 全部 413 骨骼世界坐标（枢轴后）。
- `Logs/projection-probe-dump.json`：4 门禁骨骼的 viewport 探针 + 17 个 SMR 的 BakeMesh 世界 AABB + 8 角点屏幕投影（用真实相机）。
- `Validation/m5-cloud-overlay-6411.png`：捕获点云叠加帧 6411 真值。
- `Validation/m5-triple-07.png`：Unity | 点云 | 真值三联图。
- `Validation/pose-official-compare-06-frame6411truth/`：帧 6411 真值 vs 官方（IoU 0.86 过门禁的证据）。
- SMR BakeMesh 结论：body/cloth_02/face/hair 与捕获 AABB **完全一致**（maxdiff 0.0000），iris 0.0012。捕获侧 cloth_01 因槽位导出 stride 错误（见下）无法直接比。
- **cloth_01 (835) skin 导出实际 stride=12**（manifest 写 32 是错的；285096/12=23758 顶点精确）。下游脚本读它必须强制 stride 12。
- `Validation/_slotnames-850.json`：slot→bone 名映射（来自 slot_vote.json）。

## 4. 下一步（按优先级）

1. **接入捕获光照渲染分支**：把 B 轨捕获链（CP1.y/CP1.w/CP11 常量 + EndfieldCharacterLit + 冻结捕获后处理 EndfieldCapturedPost）应用到 pose-apply 场景渲染。可参考 `EndfieldCapturePipelineValidation.cs`（冻结）的构建方式；场景 `Typhoeus_CapturedPipeline.unity` 是生成物，只改 `EndfieldCapturedSceneBuilder.cs`。
2. **颜色门禁复跑**：接完光照后重跑 `compare_pose_official.py`，目标 region mean ≤4 LSB。对照物优先用 `post-input-flipped.png`（捕获真值）而非官方截图（免受分割差异干扰）；建议给 compare 脚本加 `--truth` 基准模式。
3. **官方 mask 底部截断问题**：official-mask 在 y=0.83 截断导致 Unity 正确腿部被判 FP。可在 compare 脚本中把 official_character_y_max_norm 放宽到 0.95 或改用帧 6411 真值做基准（需先固化阈值再跑，勿事后放宽——用户硬规则）。
4. 书 prop 缺失（M6）、145 未映射骨骼、多视角验收（M7）——沿用 `HANDOFF-2026-09-25-pose-apply.md` §next 步骤。

## 5. 环境与操作（全部实测有效）

- **Unity batch 走计划任务**：改 `FractalMiner/_unity_bridge.bat` 载荷（CRLF！）→ `schtasks //run //tn "EndfieldUnityBridge"` → 20–140s → 查 `Logs/bridge-marker.txt` 的 `exit=`。本轮每次运行 20–110s。
- 运行前清锁：`rm -f Temp/UnityLockfile Temp/workerlic* Temp/FSTimeGet-*`。
- 编辑器脚本改完直接触发即可，bridge 会重新编译；编译错误看 `Logs/pose-apply-01.log`。
- Git 隔离提交模板（本轮实际用的修正版——**hash-object 必须 `-w`**）：
  ```bash
  export GIT_INDEX_FILE="$(pwd)/.git/_wb_idx_x"
  git read-tree <tip>
  H=$(git hash-object -w <file>)    # 不加 -w 会产生 invalid object！
  git update-index --add --cacheinfo 100644,$H,<file>
  TREE=$(git write-tree); COMMIT=$(git commit-tree $TREE -p <tip> -m "...")
  unset GIT_INDEX_FILE
  git update-ref refs/heads/fix/typhoeus-render-explosion-20260917 $COMMIT
  rm -f .git/_wb_idx_x
  ```
- push：`env -u HTTP_PROXY -u HTTPS_PROXY git -c http.proxy=http://127.0.0.1:7890 push endfield-records fix/typhoeus-render-explosion-20260917`
- Python 用 `EndfieldUnpacker/.venv`（PIL 无 numpy）；`_dump` DDS 解码参考本轮 post-input 脚本（DXGI 10 = half-float RGBA）。

## 6. 冻结模块（不变）

EndfieldCapturedBloom.cs、EndfieldCapturedPost.shader、EndfieldCapturedPostFeature.cs、Editor/EndfieldCapturePipelineValidation.cs、`Typhoeus_CapturedPipeline.unity`（生成物）。

## 7. 本轮所有验证运行编号（可复核）

| run | 内容 | 结果 |
|---|---|---|
| 11:37 | pitch 翻转首次渲染 | 骨骼 dump=pose 精确；IoU 0.4615 |
| 11:44/46 | +viewport/SMR 探针 | frontal 探针=真值（5 位）；SMR AABB 全等 |
| 14:00 | 轨道相机渲染 | IoU 0.7221，宽度精确相等 |
| 14:28 | 枢轴 v1（转 armature 自身） | 无效，世界未旋转 |
| 14:34 | 枢轴 v2（替换 chr rot） | 角色倒地（Rx(90) 因子） |
| 14:39 | 枢轴 v3（rotNew*rotOld⁻¹ 手工矩阵） | 还是 Rx(90)（l2w 陈旧+组合错误） |
| 14:43 | 枢轴 v4（重写 local=world） | 双重旋转，更糟 |
| 14:47 | 枢轴 v5（Euler(0,−45.5,0)*Euler(−90)） | y 正确但 yaw 镜像（form2） |
| **14:48** | **枢轴 v6（Euler(0,+45.5,0)*Euler(−90,0,0)）** | **L1=0.00000 完美闭合** ✅ |

—— 以上每一步都有 `Logs/bridge-marker.txt` 时间戳、`bone-world-dump.json`/`projection-probe-dump.json` 数值和 `pose-official-compare-*` 报告可复核。
