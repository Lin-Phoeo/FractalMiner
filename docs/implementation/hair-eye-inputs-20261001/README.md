# Hair / Eye 原生输入与官方采样更正（2026-10-01）

认证帧 6411 的 Hair PS22257 / Eye PS22259 原生输入、受限生产消费及眼睛投影光更正。没有截图拟合、亮度补偿或曝光/后处理调参；不是全量渲染完成。保留最高细节模型与原始纹理 mip 链。

## 1. 重要撤回：眼睛投影光

**旧交接/CPU 参照中“世界空间投影光不可再次归一化”的结论错误，必须停用。** 实际 `Validation/draw-program-audit-20260930-01/event-776-fragment-22259.hlsl:674` 在 ramp 点积内明确执行 `_1233 * rsqrt(max(FLT_MIN,dot(_1233,_1233)))`。根空间归一化、清零 Y、回到世界空间不能替代这个消费点的归一化。旧 canonical b28 对应表达式第 678 行也有该步骤，不是变体差异。

实际 PS SHA256：`c372e6c7708333952f52e77a17bb3c2ba300d87543cd91cd1f944adeeaa2c2b3`。没有重写封存原文或 seal 隐藏更正；后续以本说明和实际表达式为准。

先据源程序修独立 CPU 参照，旧运行时 **4/17 FAIL，最大误差约 0.158491**；再补消费点 `EFEyeNormalize(rampLightWS)`，**17/17 PASS**，六个根旋转/光方向例最大误差 `9.02933e-6`。原 `.004` 门限不变。CPU 还纠正 Clamp texel-center 与真实相机 view 索引，加入负 Z 光，避免旧饱和区用例掩盖问题。是受限 reduction，不是所有 uniform 组合证明。

## 2. 实际绑定、颜色域与采样

只离线重放 `C:/Users/Administrator/Downloads/正面.rdc`，未启动游戏/注入。私有包 `Validation/Captures/native-hair-eye-inputs-20261001-01` 不上传；complete manifest SHA256 固定为 `879c9064fbabdaafed25d798928cc20f730e235ea709abe1f3d91d63c70a158b`。controller/capture 成功 Shutdown 才写 complete，不能拿 GUI exit=0 代替成功证据。

| Draw / binding | 资源 | 格式 / 尺寸 / mip | 官方采样 |
|---|---|---|---|
| Hair 875 b1 | HN（split normals） | BC7_UNORM / 2048² / 12 | s4 Repeat，bias -1 |
| Hair 875 b2 | SpecRamp | RGBA8_UNORM / 256² / 1 | s6 Clamp，LOD0 |
| Hair 875 b3 | P | BC7_UNORM / 2048² / 12 | s4 Repeat，bias -1 |
| Hair 875 b4 | Line | BC7_UNORM / 512² / 10 | s4 Repeat，implicit Sample，无全局 bias |
| Hair 875 b5 | DiffRamp | RGBA8_UNORM / 256×1 / 1 | s6 Clamp，LOD0 |
| Hair 875 b6 | Base | BC7_SRGB / 2048² / 12 | s4 Repeat，bias -1 |
| Eye 776 b1 | Matcap | BC7_SRGB / 256² / 9 | s6 Clamp，bias -1 |
| Eye 776 b2 | DiffRamp | RGBA8_UNORM / 256×1 / 1 | s6 Clamp，LOD0 |
| Eye 776 b3 | Base | BC7_SRGB / 512² / 10 | s4 Repeat，bias -1 |

旧 Hair b1–b5 语义标签 SpecRamp/P/Line/DiffRamp/Bump 错位。实际 s4/s6 都是 bilinear / mip-point，descriptor bias=0；-1 来自 shader 全局 bias，不给纹理二次 bias。sRGB RGB typed view 解码一次、alpha 线性，其余图线性。原始压缩 bytes/mip 保留，不转 PNG、不翻 UV。

## 3. 实现与生命周期

- `Tools/capture_hair_eye_materials.py` 复用严格导出器，固定实际事件/PS/资源语义并核验 sampler。
- Hair Diff/View/Spec ramp 从候选 Mirror 改为实际 Clamp。Base/P/HN 共用 VS Base ST 一次后的 `sourceUV`；Line 继续额外应用自己的 Line ST，保留 implicit Sample。Hair 光照代数不改；合法域内 Mirror/Clamp 可能相同，不据此声称视觉提升。
- Eye Base Repeat / Matcap Clamp 均 bias=-1，ramp Clamp LOD0。helper 去掉重复 Base ST；CharacterLit 传 `sourceUV`，解析 frac/disk/parallax 使用实际 VS22258:454 输出坐标。投影光在 ramp 消费点再归一化。未改材质参数资产/曝光/后处理。
- `EndfieldCapturedHairEyeMaterials.cs` 固定九张图 hash/format/mip/sampler，全部检查后才绑定；Editor `EndfieldCapturedHairEyeMaterialInputs.Load()` 读取固定 manifest。
- opt-in `ENDFIELD_HAIR_EYE_NATIVE_MATERIALS=1`，默认关闭；目标是已审查 `M_actor_typhoea_hair_01` / `M_actor_typhoea_iris_01` variant。
- 复用 Cloth 的纹理所有权 scope；普通退出恢复原 slot/根继承，外部替换 owned texture 时保留外部字段，释放前移除其余仍 owned 的纹理。它是**独占短期同步 scope**，不是长期异步 MPB 合并器；仅非纹理字段的后来写入可能被常规恢复覆盖。
- recovered 场景实际 Cloth 2 + Skin 2 + Hair/Eye 2 共六个审查 slot 同时绑定、恢复，dirty 不变；不是全部 17 SMR variant。没保存场景/材质/quality/graphics。完整 pose 未运行，最终场景/Player 包装与动画并发待验证。

## 4. 验证与复跑

9 bindings / 9 images / 68 mip / 340 typed-view 点值：SampleLevel maxError=0，Load `<2e-6`；18 项 null/corruption 拒绝。四个 native/decoded 生产 fixture 通过，ramp 保留 native。另 11 个独立期望：Eye Base bias 两例+Repeat 边界一例、Matcap bias/Clamp 三例、解析 UV 内/外两例、Hair Line 三例（bias -1/0 都 mip3，Line ST×2 才到 mip4）。默认五 pass 编译/SetPass；Eye 八个 family/outline policy 状态通过。

八项既有 GPU 回归通过：native Skin、Skin formula 28例、native Cloth materials、native BC5、cube、Cloth normal、Cloth emission、Hair split；最终新 Hair/Eye 再跑也通过。Python 全套 342 passed / 3 历史 skipped / 77 subtests，2 个既有 Pillow warning。导出 API/IO 线覆盖率 97.08%，本 wrapper 100%，不宣称 C#/HLSL/全工程覆盖率。Ruff/Pyright 通过；pip-audit 仅 uv 临时工具环境，无新增项目依赖。

复跑：新建报告目录，两个报告路径必须不存在，Unity 任务顺序执行，不能同项目并发：

```powershell
$env:ENDFIELD_HAIR_EYE_MATERIAL_REPORT='D:/EndfieldTechLib/notes/your-new-run/hair-eye.txt'
$env:ENDFIELD_OFFICIAL_NUMERICAL_REPORT='D:/EndfieldTechLib/notes/your-new-run/official.txt'
# Unity: A:/Unity/Editor/2022.3.30f1/Editor/Unity.exe
# 用 Start-Process -WindowStyle Hidden -Wait，参数：
# -batchmode -force-d3d11 -projectPath "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner"
# -executeMethod EndfieldShaderPack.EndfieldNativeHairEyeMaterialValidation.RunBatch -quit -logFile "新路径.log"
# 公式单独跑 EndfieldShaderPack.EndfieldOfficialShadingValidation.RunNumerical
# 不跑 RunAll（旧工具会恢复写入资产）。
```

数值见 `gpu-input-report.txt`、`official-numerical-report.txt`；运行/hash/保护证据见 `verification.json`。v1/v2 seal 不重写，分别仍 79/24 pending，v1 handover drift / v2 CharacterLit、OfficialHair drift，无其它新增源漂移；仍不是全量完整 PASS。

## 5. 下一步

四族本轮六个 draw 已有原生输入实现。继续审查 material uniform、空间/天气分支、render state、shadow/light/post producer 与正式场景生命周期；不得因输入测试通过就跳过剩余规格。正式绑定与并发策略完成后接解包动作/MMD 全流程，不用曝光拟合掩盖错误。原始纹理 mip 是官方采样，不是模型 LOD 降级。
