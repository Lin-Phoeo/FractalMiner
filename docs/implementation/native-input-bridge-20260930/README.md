# 原生输入无损交接接口：2026-09-30

## 本轮完成与边界

已实现 **原始VS输入 → 独立数据包 → Python/C#只读消费者**，真实frame6411六draw验证通过。不是原生GPU draw、官方skinning CPU生产器或Unity网格适配完成；画面未改变。`rendering_certified=false`和`mesh_mapping_ready=false`仍为强制字段。

来源规范仍是[封存v2](../../render-baseline/v2/foundation.md)。本轮没有改写v1/v2、旧pose导出、现有shader/helper、mesh、scene或ProjectSettings。没有启动Unity/游戏，没有截图像素拟合。

本轮使用search-first复用封存检查器；TDD先跑失败用例再实现；verification-loop补真C#编译/执行、覆盖率、差异及依赖检查；codebase-documenter用于本交接。不能用文档或源码字符串检查替代真正读取测试。

## 为什么不直接改Mesh权重API

[Unity 2022.3 SetBoneWeights文档](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Mesh.SetBoneWeights.html)说明内部存储可能降低传入浮点精度、不能保证精确往返，最低精度为16-bit normalized，还要求权重排序、忽略零权重。换此API不是cloth_01原生f32无损保真的证据。现有`mesh.boneWeights` setter的具体内部行为没有在本轮实测，不将另一API的行为直接套给它。

[VertexAttributeDescriptor文档](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Rendering.VertexAttributeDescriptor.html)规定最多4个vertex streams；捕获绑定含slot4零步长常量。不能宣称把捕获五slot布局原样塞进Unity Mesh。后续适配必须另验。

## 代码与本地产物

| 入口 | 职责 |
|---|---|
| `Tools/native_draw_bundle.py` | build/verify/read_stream；复用封存v2的原始输入检查，不改其代码 |
| `Assets/EndfieldShaderPack/NativeCapturedDrawData.cs` | 无UnityEngine依赖的只读消费者，放在非Editor目录供未来editor/runtime适配层引用 |
| `Tools/NativeDrawBundleTests/` | 与实际消费者源文件直接链接的C#9 console harness，复用项目已有Newtonsoft DLL |
| `Tools/tests/test_native_draw_bundle*.py` | 20项Python测试、24项实际C#编译/执行测试；故障源和消费者缓存反例 |
| `Validation/native-draw-bundle-20260930-01/` | 实际六draw数据包，仅在本地；不上传官方原始字节 |
| [verification.json](verification.json) | 本轮结果、可信manifest pin与覆盖率报告身份，入Git留存 |

数据包保留原始manifest/contract的完整字节；每个属性保持location、匿名signature、原生format、resource/slot/stride/offset/first_byte；原始索引字节、index width、ib_min和draw offsets也保留。每个输入为**原导出的紧凑属性数组**，不是原GPU buffer完整交错span；零步长流已按原导出展开，但保留原stride=0来源记录。后续GPU适配不能误用来源stride来遍历紧凑数组。

`manifest.json`按location建立独立逻辑记录；即使0/5或2/6/7字节相同也不合并用途。不造缺失location、不量化f32、不截断u32 slots、不排序/归一权重、不正交化N/T、不变换坐标、不rebase原始index。packed R32载体按位交接，避免float/JSON改写NaN等位模式。

`complete.json`最后写入，包含整个新manifest的SHA。失败留下未完成目录，读者拒绝；工具不清理/复用它，重试应换全新目录。文件路径只允许直接子文件、拒绝路径逃逸/链接；读取验证所有文件大小/hash、来源pin、location/format、非负地址、零步长复制、index地址/count/span。来源index当初没有单独hash字段：本包新增SHA只固化导出时读取的索引，**不扩大为原游戏全部拓扑的独立认证**；封存v2仍包含对应原索引的文件hash。

## 复现与读取

在FractalMiner根目录运行；build输出目录必须未存在，而且位于原始导出目录之外。

```powershell
# 此名称已存在；复现时换成全新目录，不覆盖当前已验证包
uv run --python 3.13 --no-project python -B Tools/native_draw_bundle.py build `
  Validation/vertex-input-export-20260929-183059/manifest.json `
  docs/render-baseline/v2/native-input-contract.json Validation/native-draw-bundle-NEW

uv run --python 3.13 --no-project python -B Tools/native_draw_bundle.py verify `
  Validation/native-draw-bundle-20260930-01 `
  --manifest-sha256 3822497b8775fc18cdcebbf12a227b14aec8230a3ac886e990f037d6508e8db6 `
  --contract-sha256 ba28e78d991d7ee550ad59ccad18903dab89bc22c7cfcc0335e3e66a1e2f8793
```

```csharp
var data = EndfieldShaderPack.CapturedData.NativeCapturedDrawData.Load(
    "Validation/native-draw-bundle-20260930-01",
    "3822497b8775fc18cdcebbf12a227b14aec8230a3ac886e990f037d6508e8db6");
var cloth = data.GetDraw(835);
byte[] originalF32Weights = cloth.GetInput(8).CopyBytes();
uint originalSlot = cloth.GetInput(9).ReadUnsignedComponent(0, 0);
uint packedFrameBits = data.GetDraw(875).GetInput(2).ReadUInt32Bits(0, 0);
```

C# Load必须接受**来自可信交接记录**的manifest SHA，不能从待验证包本身计算后称其身份可信。hash是身份/完整性约束，不是加密签名。`CopyBytes`、`SourceBinding`、`SourceRecord`都返回复制，消费者不能改内部缓存。`ReadFloat32`仅为原f32载体；`ReadNormalizedComponent`返回double数学诊断值，不宣称复现GPU normalized-fetch的浮点舍入；GPU提交仍应取原字节。缺少输入时抛错，不回退到相似流。

## 验证记录

- 实际包：6 draw、52,820顶点、56路属性及6路索引；Python复核/C#实际读取通过。
- 新增44项测试通过；其中C#包含packed NaN/负零、slot300、原始index、alias独立、外部SHA、缓存防修改、原生坏地址/格式/NaN权重、UNORM8/16和index8/32反例。
- 合并回归269通过、3个历史缺独立Unity诊断输入的测试跳过、3 subtests通过、2个既有Pillow弃用提醒；本轮没有新增skip。
- Python工具：语句92.90%、分支82.81%、合并89.95%。C#消费者：行222/223=99.55%、分支139/162=85.80%；统计排除harness Program.cs，不包含Unity/GPU。
- Ruff通过；Pyright 0错误/警告；C#9在net10.0执行、netstandard2.1编译均零警告/错误。不等同Unity工程/Shader编译通过。
- pip-audit仅本轮隔离工具环境无已知漏洞；项目已有Newtonsoft复用，未新增Unity依赖；没有把工具环境结果扩为全项目安全认证。
- C#覆盖率使用Microsoft `dotnet-coverage`18.11.0，仅安装在本轮外部备份目录并作用于自有harness，未加项目或全局工具依赖；[官方收集说明](https://learn.microsoft.com/en-us/dotnet/core/additional-tools/dotnet-coverage)。

测试入口：`uv run --python 3.13 --no-project --with pytest python -B -m pytest Tools/tests/test_native_draw_bundle.py Tools/tests/test_native_draw_bundle_csharp.py -q -p no:cacheprovider`。需要本机dotnet10 SDK、当前Unity PackageCache的Newtonsoft DLL；缺依赖直接失败，不静默跳过。

## 下一步，不误判完成度

1. 输入的**存储与只读交接**闭合了，但palette、part-root、current/previous、归一化GPU fetch、VS解码及mesh重建生命周期仍未闭合。不能用本包当已实现的完整skinning算法。
2. 按v2 §3修Hair官方source helper：diffuse/spec分别使用RG/BA、精确TBN、背面符号和归一化下限；现有早return后的BA代码不能算已接入。先来源算例/分支/绑定门禁，再编译。
3. 按v2 §4补cloth_02 emission预乘选择项、UV/bias/插入顺序，另核两套cloth的part-root，不用调亮补偿。
4. 真实GPU适配建立独立层，不直接覆盖现有SMR或假定Unity原生权重存储保真。先验证vertex order和各location，保存旧mesh及入口的回退版本，确认重建不覆盖恢复流后再接动作/MMD。

本轮Git只提交新增接口/测试/文档/结果元数据；用户原9557项主索引、主HEAD、既有场景及渲染文件保持原状。封存证据仍为evidence-only，不改变其pending列表。
