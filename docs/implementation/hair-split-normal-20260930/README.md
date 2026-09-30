# Hair 双法线与采样接线：来源驱动的实现增量

本轮实现了实际 event875 / PS22257 的 RG 漫反射、BA 高光法线核心，并接入 CharacterLit 的官方 dry/flat 分支。不是逐像素调参，也不是“整套官方 Hair 已完美复原”的认证。v1/v2 封存资料不重写；实现验证记录在这里。

## 已修正的实际错配

旧官方分支的 early return 调用只传一套 AG 法线；后面的 legacy BA 代码并不进入该调用。现有提弗洛斯 hair 材质其实早已启用 `_UseSpecBumpMap=1`，HN 绑定正确，不能因旧 b125 文档便把实际 b126 认成单法线。

新核心 `Assets/EndfieldShaderPack/EndfieldOfficialHairNormals.hlsl` 对同一次 HN sample：

- RG → diffuse，BA → specular；先从未缩放 XY 求 `max(1e-16, sqrt(1-clamp(dot(xy,xy),0,1)))`，再分别乘 XY scale。
- TBN 使用原始插值 `T`、`cross(N,T)*handedness`、`N`；不调用会额外归一 T/B 的 CharTBN。
- diffuse 使用 FLT_MIN 下限 rsqrt，再乘背面因子；specular 使用普通 normalize，不乘背面因子。零 specular 向量属于源程序的退化域，不人工改成其他法线。
- NdotL、view ramp、环境梯度、非深度背光 rim 使用 diffuse；strand、object-space edge fade、primary/secondary/line 三条 tangent shift 使用 specular。
- Hair 的 base/albedo、split normal、view direction 送入 helper 前保留 float，避免先经过旧 half N/V。

采样同步修正：Base/P/HN 共用一次 BaseMap_ST 后的 source UV，全部 SampleBias。捕获 bias 为 −1，通过私有 `_EndfieldCapturedGlobalMipBias` 注入，不污染 URP 的 `_GlobalMipBias`。Line 在 source UV 上再套 LineMap_ST，普通 Sample 不加 bias；两种 ramp 使用构造坐标、LOD0，没有额外 ST。

`_UseSpecBumpMap=0` 仍明确走旧单法线适配，传 N/N；它不是本轮 b126 双法线认证对象。legacy 非官方分支、场景、材质、贴图 metadata、原始捕获均未修改。

## 来源核实，不用旧错签名表

实际来源是 `Validation/Captures/tifuluosi-front-20260917/replay-details-01/draw-details.json` 的 event875 → `ShaderStage.Pixel` → ResourceId::22257，以及重新导出的 `Validation/draw-program-audit-20260930-01/event-875-fragment-22257.hlsl`（SHA256 `e2394790fca96e29a67f4a8925f4a04bdc977a493847fe284d128bfbfeca37b9`）。核心在该文件 _499.._576；VS22256 输出 BaseMap_ST UV。set0/b16 `_child16`=-1，对应 HLSL `packoffset(c26)`，即 offset416。

| set1 binding | 实际用途 | 捕获 resource |
| --- | --- | --- |
| 1 | SplitNormalMap / HN | 44755 |
| 2 | SpecRampMap | 59387 |
| 3 | MetallicGlossMap / P | 37888 |
| 4 | LineMap | 38063 |
| 5 | DiffRampMap | 30467 |
| 6 | BaseMap / D | 37906 |

旧 `extracted-source-shading-reviewed-20260923/summary.md` 的槽名字由错用 b125 映射得到，不能据此绑定实际 PS22257。该历史材料仍留存，不当权威。HN 材质 GUID `17108308015ca514e88b228499270a49` 指向 HN.png，metadata 为 Default、sRGB0、无 normal 转码、mipmap 开启；这仅证明当前绑定/导入设置，不等于捕获资源的全部 mip 字节已经复原。

## 验证与复现

测试先失败：6 个新结构 guard 中 4 fail、1 missing-kernel error、1 既有绑定检查通过；实现后全部通过。进一步在 Unity 2022.3.30f1 / URP14 / D3D11 / RTX3060 Laptop 上执行同一个生产 normal include：9 组 × 2 法线=18 个 GPU 算例，独立 double CPU 公式核算，阈值 2e-5，最大分量差 `4.059186498039935e-8`。包括背面、非单位/非正交插值 TBN、盘外 XY、缩放顺序、零/负 scale 和 diffuse 零向量下限；未对源程序未定义的 spec 零向量造“通过”结果。

还实际绘制生产 CharacterLit 官方 Hair 分支：

- 关闭 spec 与 line modulation 后，只改 BA，diffuse 输出差=0。
- 只改 RG，diffuse 响应=0.108597。
- 启用 spec 后，只改 BA，输出响应=0.356039。

这些是合成纹理的分支隔离算例，不是官方画面逐像素对照，也不意味着亮度是调参目标。CharacterLit 默认关键词下的 5 个 pass SetPass/编译通过，不扩大为全部关键词组合。最初批处理尚未初始化 URP 时 DrawMesh 得到粉色 fallback，已修测试环境：在独立 preview scene 渲染一次初始化 URP，再执行生产 probe；这个失败尝试没有当成通过。首次 harness 的 C# namespace 错误也已修复，最终批处理零 C#/Shader 编译错误。

回归：275 passed、3 个历史缺独立 Unity 输入的 skip、3 subtests；2 个既有 Pillow 提醒。Ruff 通过，Pyright 零错误/警告。本轮隔离 Python 工具环境 pip-audit 无已知漏洞；不是全项目安全审计。HLSL 每条新核心运算均由这些 probe 执行，但没有安装 HLSL coverage 插桩，不声称全 Shader/管线达到 80% 机器覆盖率。

在 FractalMiner 根目录执行结构/既有回归：

```powershell
uv run --python 3.13 --no-project --with pytest --with pytest-subtests --with pillow --with numpy python -B -m pytest Tools/tests docs/render-baseline/v2/tools/tests -q -p no:cacheprovider
```

GPU harness 只允许独立 batch editor；先关闭该项目的编辑器以免争抢工程锁。`ENDFIELD_HAIR_PROBE_REPORT` 必须是**未存在**的输出文件；不要覆盖本轮报告。不要添加 `-nographics`。

```powershell
$env:ENDFIELD_HAIR_PROBE_REPORT='D:/EndfieldTechLib/notes/hair-probe-NEW.txt'
& 'A:/Unity/Editor/2022.3.30f1/Editor/Unity.exe' -batchmode -force-d3d11 `
  -projectPath 'A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner' `
  -executeMethod EndfieldShaderPack.EndfieldHairSplitValidation.RunBatch -quit `
  -logFile 'D:/EndfieldTechLib/notes/hair-probe-NEW.log'
```

PowerShell 启动 GUI exe 可能立即返回；以新报告是否存在并写出 RESULT PASS、日志的编译/异常记录为准，不把 shell 的即时 exit0 当作 Unity 测试成功。Harness 清理对象、关闭 preview scene，恢复生产 probe 显式保存的 global 列表；URP 初始化和 DrawMesh 的矩阵/其他状态仅在独立 batch 进程内，退出后丢弃，不声称完全恢复交互编辑器上下文。不载入/保存角色场景，也不修改材质资产。没有启动游戏或抓取新帧。

本轮最终本机报告：`D:/EndfieldTechLib/notes/hair-split-normal-20260930-01/gpu-probes-04.txt`，SHA256 `83eb85c10d9369c93fd3c6672d77ddcf344fa16e2e5b7e3327b7f7e20064ff34`；日志 `unity-batch-05.log` 仅本地留存，避免将许可证/设备信息提交公共仓库。摘要在 verification.json。

## 封存与回退边界

v1 原 verify：6771 文件、18 anchor，无错误，仍 evidence-only。v2 原 verify：149 文件、7 anchor，**完整快照 integrity=false**，只有两个预期实现变化：CharacterLit.shader 和 OfficialHair.hlsl。manifest digest、inventory、全部来源/其余审计快照/anchors 没变；“来源完整性通过”不改写成“完整旧快照通过”，不删 pending。

修改前精确备份在 `D:/EndfieldTechLib/notes/hair-split-normal-20260930-01/`，旧 shader/helper 字节 hash 分别为 `aed32e75dd8cde4c4208d2cb15e2bcf55cead5e461db121e44cbd3c9e6bcec96` / `794590e4362bcd9c031e7deaa3c260113a3e80ba8eb23c7020f97814d91a6eab`，与封存 v2 一致。

重要：工作目录原有 CharacterLit 的 debug/outline 修改尚不在记录分支 tip05cd5b2 中。本轮没有改/认证它们；先单独记录原有状态到 `d540f22af1f40413590ed87d363993c2604aa434`，本轮实现提交以它为 parent，这样回退 Hair 不会顺便丢掉用户原有 outline 工作。该留存提交不是“outline 官方等价”的证书。主 HEAD `fc9d4869803f439ffff83311986190e8a8b5ade3`、主索引9557项及条目内容不变，场景/Quality/Graphics 文件 hash 不变。

不要在含用户大量暂存文件的主索引上直接 git commit/revert/reset；沿记录分支与独立 index 操作，先核当前尖端。Git 换行过滤可能改变工作目录字节 hash，完整旧快照复核优先使用上述精确备份，不能把 Git 文本内容一致当作字节一致。

## 下一步与仍未闭合的项

当前只闭合双法线核心及消费/UV/bias 接线，不扩大为完整官方渲染：actual sampler 过滤/寻址状态未由 draw-details 导出；输入贴图 mip 字节、native GPU fetch/skinning/part-root、SSM producer/绑定、helper 旧 safe-XZ 与 lobe sqrt saturation 的退化域、天气湿身/点光/深度 rim/雾、完整 VFX/输出精度和全局后处理仍须各自审计。合成常量纹理没有 mip 链，本轮只验证 bias 值与采样代码，未数值认证真实 LOD 行为。

下一优先工作按 v2 §4 审实际 cloth_02 emission consumer：预乘选择、UV/bias、插入顺序，再按来源实现并编译。Hair 剩余整支公式/退化域/sampler 与动态 native producer 继续挂显式待办；不调亮补偿。官方解包动作和 MMD 后续依赖 native 输入/骨架生命周期闭合，不能借本轮 Hair 通过提前宣称接好了。
