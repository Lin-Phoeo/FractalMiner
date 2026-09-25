# 交接首条提示词（2026-09-25 v2）— 终末地提弗洛斯官方渲染完全还原

> 用法：把本文件全文作为第一条消息发给接手的智能体。

---

你是接手《明日方舟：终末地》提弗洛斯（chr_0034 / typhoea）渲染逆向还原项目的智能体。

## 0. 项目主线与你在这条线上的位置

**主线：在 Unity 里 100% 复刻官方游戏帧的角色渲染**（以本地捕获帧为 ground truth，
逐像素/分区域对得上才算完）。主线之后才是延伸目标：MMD .vmd 动画接入 → AI 视频。

主线里程碑与进度：

| # | 里程碑 | 状态 |
|---|---|---|
| M1 | 官方 shader 公式逆向（hair/skin/eye/cloth 四族 ForwardLit） | ✅ 已落地（A 轨，b401 核心） |
| M2 | 捕获后处理管线复刻（Bloom 逐字节一致、官方 G 通道自阴影算法完整解出） | ✅ 冻结模块 |
| M3 | 动态自阴影全链路（atlas→prepass→官方 16-tap resolve→消费） | ✅ live 三关全 PASS |
| M4 | 官方姿态还原（捕获帧 SSBO 骨骼流 → Unity 481 骨 → 蒙皮渲染） | ✅ 09-25 闭环 |
| M5 | **官方帧整帧对照验收（姿态/相机/光照/材质一体，分区域对像素）** | ⬅ **你在这里**：几何 09-25 下午已闭合（L1=0.00000），剩颜色/光照接入 |
| M6 | 细节补完（书 prop、表情、覆盖层/透明/dither、cloth §10/§11、eye 折射、A 轨遗留） | 未开始 |
| M7 | 多视角泛化验收（转相机/角色/灯光重跑全部门禁） | 未开始 |
| 延伸 | MMD 重定向（481 骨姿态输入已具备）→ AI 视频 | 未开始 |

**你的主要工作就是 M5 起把"完全还原官方渲染"收尾**：所有零部件（shader、后处理、
自阴影、姿态）都已验证可用，现在要把它们合到同一帧里与官方帧对齐验收。

## 1. 开工前必读（按序，别跳）

1. `A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\HANDOFF-2026-09-25-m5-geometry-solved.md` — **最新权威状态**：M5 几何闭环（R_y(+45.5) 角色枢轴，L1=0.00000）、相机 pitch 符号修正、帧 6411 真值基准、剩余工作清单、9 轮复核表。
2. `FractalMiner\RESUME-2026-09-23-captured-pipeline.md` — 捕获管线/自阴影/Bloom 权威记录（§5.2 官方 G 通道自阴影算法已完整解出，**不要重新推导**）。
3. `FractalMiner\QODER-HANDOFF-2026-09-23.md` — 架构、文件所有权、Git 硬约束。
4. ground truth shader：`FractalMiner\_dump_1.5.3\...\characternpr\`；翻译文档 `docs\research\official-forwardlit-*.md`，落地直接抄公式。

## 2. 工程与环境

- Unity 2022.3.30f1 + URP 14.0.11，工程根 `A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner`。
- 基线场景 `Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity`：**含两套同名 Bip001 骨架**——可见角色 `chr_0034_typhoea_rebuilt`（17 个 SMR）+ 停用的 `Typhoeus_SourceFBX` prefab。**一切按名查找必须先锚可见角色根**。
- 用户是鹰角实习生，个人学习用途，不公开发布。

## 3. 当前可工作的具体入口（M5 任务分解）

1. **姿态渲染 vs 官方帧分区域对照**：`Validation/pose-apply-01/pose-applied.png` vs 官方正面帧（official-front-1280.png）。
   - 已知差异源（先核对再改）：① 书本体缺失——书是独立 prop，不在场景 17 个 SMR 内，需决策是否补；② 场景相机 (0,0.844,3.11) ≈180°Y 与捕获帧相机/FOV 一致性（捕获 cam/VP 在 `Validation/Captures/tifuluosi-front-20260917/pose-full-01/manifest.json`）；③ 145 个未映射骨（corrective/twist 保持 bind），关节处蒙皮对不上再补映射。
   - 验收方法：PIL 区域均值/轮廓差分，阈值先写死。
2. **整帧合成对照**：把姿态正确的角色 + 捕获光照分支（CP1.y=1 平坦环境 + CP1.w=1 光方向覆盖 CP11.xyz）+ 冻结的捕获后处理链合成一帧，与官方帧整帧差分。
3. 之后再进 M6/M7。

## 4. Unity batchmode 自动化（唯一可用通道）

WorkBuddy 进程树直接 spawn Unity 会死锁。已建计划任务桥：

```bash
# 1) 改写 FractalMiner/_unity_bridge.bat 的 -executeMethod 载荷（必须 CRLF！）
#    用 Write 工具写完后：sed -i 's/\r\?$/\r/' _unity_bridge.bat
# 2) 触发：schtasks //run //tn "EndfieldUnityBridge"（无代码改动 ~30s，有重编译 ~55-115s）
# 3) 验收：cat Logs/bridge-marker.txt（看 exit=）+ 对应 Logs/*.log + 产物文件
```

- bat 必须 CRLF（LF 静默失效）；**禁用 printf 写路径**（`\U`/`\E` 转义会吃掉 `A:\Unity\Editor`）。
- 挂起 cmd 会阻塞后续触发（任务"已排队"）：`ps -W | grep -i unity` → `taskkill //PID <第4列WINPID> //F`。
- 强杀 Unity 会污染 Library；卡死先清 `Temp/UnityLockfile`。
- 编辑模式 `camera.Render()` 同帧第二次调用疑似不刷新——渲染对比实验一次一进程。

## 5. 用户硬要求（每步必守）

- 每步必须截图/数值证据（batchmode 渲染后 PIL 区域均值或逐像素对官方帧），"编译过了"不算完成。
- **门禁阈值先写死再看结果，不许事后放宽。**
- 每完成一步：隔离索引提交 fix 分支 → push（见 §6）。
- 已实测纠正的坑（别再犯）：角色索引 int() 截断；step 数遮挡 0=全亮；0/0 不出 NaN 禁加保护；`_CaptureFlipY` 实时必须传 0；atlas 必须 R16_UNORM；reversed-Z 自定义 RT 深度=1-clip.z 用 clear1+LEqual；`EndfieldCharacterLight.forward` 指向光源非旅行方向。
- **探针数值合理 ≠ 作用在正确对象上**：跨对象同一性用 ReferenceEquals/instanceID 判；蒙皮是否响应用 BakeMesh 前后对比判。

## 6. Git 工作流（严格遵守）

- 记录分支 `fix/typhoeus-render-explosion-20260917`，尖端 `3602e1a`（已 push；几何闭环代码在 `9bf3058`）。本地 HEAD 在 main（ee02bba），**不要动**。
- 隔离索引提交（工作树有大量无关改动，绝不可 `git add .`）：

```bash
cd FractalMiner
export GIT_INDEX_FILE="A:\\Hypergryph Launcher\\games\\Arknights Endfield\\FractalMiner\\.git\\_wb_idx_xxx"
git read-tree 3602e1a   # 始终先 git log 确认当前尖端，别硬编码旧 hash
git add <只加你的文件>   # 排除 Assets/Project 删除、ProjectSettings、UnityMCP 日志、__pycache__、Assets/Codex finishhalf-0923.unity（用户文件）
TREE=$(git write-tree)
COMMIT=$(git commit-tree "$TREE" -p 3602e1a -m "...")   # -p 也用当前尖端
printf '%s\n' "$COMMIT" > .git/refs/heads/fix/typhoeus-render-explosion-20260917   # 沙箱内 update-ref 不可靠
rm -f .git/_wb_idx_xxx    # rm 用 git-bash 相对路径，Windows 盘符路径会被沙箱拦
git push endfield-records fix/typhoeus-render-explosion-20260917
# push 502 时：env -u *_PROXY git -c http.proxy=http://127.0.0.1:7890 push ...
```

- **冻结模块**（除非新数值测试证明有错）：EndfieldCapturedBloom.cs、EndfieldCapturedPost.shader、EndfieldCapturedPostFeature.cs、Editor/EndfieldCapturePipelineValidation.cs。
- `Typhoeus_CapturedPipeline.unity` 是生成场景：只改 `EndfieldCapturedSceneBuilder.cs` 再生成，不许直接编辑保存。

## 7. 已完成状态明细（不要重做）

- **M1 官方 shader（A 轨）**：hair/skin/eye/cloth b401 核心已落地；珊瑚海岸静态重建基本完成（60b2599），遗留：烘焙脸仍黑、身后多余脸（归 M6）。
- **M2 捕获后处理**：动态 Bloom 逐字节一致；官方 G 通道自阴影 = 16-tap Poisson GatherRed + TBL247/248 + 非线性软化（screenspaceshadowresolve.shader L1077-1127）。
- **M3 动态自阴影**（e3d1156）：atlas caster（LEqual+clear1+Cull Off）→ GBuffer prepass（同深度态）→ CSResolveScreen → CharacterLit 消费 `_EndfieldCharacterShadowScreen`.g；数值：atlas 238267 texels、median signed 误差 +8.8e-5、shadowFraction 0.2057；视觉证据 Validation/live-shadow-diff-x6.png。
- **M4 姿态**（53e9230 破解 + 049b992 闭环）：真蒙皮模型=逐实例 palette 记录（**槽号=InstanceIndex 非骨骼槽**）+ SSBO(ResourceId::245) 骨骼流（骨 b = 3×float4 行 @ (base1+3b)*16）；375/375 槽↔骨映射（pose-full-01/slot_vote.json，顶点与 Unity 资产逐字节一致）；delta 约定 `bonePose = M_ssbo × inv(bindpose)`；268/481 骨姿态驱动蒙皮渲染出官方"低头胸前持书"姿态，世界系门禁全过（证据 `Validation/pose-apply-01/`）。姿态数据 `pose-full-01/pose_apply.txt`（行主序 M×v、平移列 3、捕获模型空间 Y-up）。Root 带 −90°X，应用时 `newWorld = inverse(armature.localToWorldMatrix) × pose`。
- **旧 pose-palette-01 结论作废**（把逐实例记录当骨骼调色板）。

## 8. 杂项环境

- 截新帧用 RenderDuck_v1.4（`C:\Users\Administrator\Downloads\RenderDuck_v1.4\`，官方 RenderDoc 会被 ACE 反作弊检测；旧 .rdc 仍可用官方 qrenderdoc 回放）。
- Bash 缺 head/wc/dirname：`export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"`；PowerShell 无输出换 Bash。
- Python 用 `EndfieldUnpacker/.venv`（PIL 无 numpy）。
- 大文件超 Read 限制：先 `grep ^#{1,3}` 拿结构再分段读。
- 工作区记忆 `.workbuddy\memory\`（项目根，非 FractalMiner）：每日日志 + MEMORY.md，完成实质工作后追加。
