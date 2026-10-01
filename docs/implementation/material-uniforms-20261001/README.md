# 六个主体材质的原始常量 / GPU 上传审查（2026-10-01）

继承 Hair/Eye 原生输入增量（记录父提交 `576cef0`）。本轮从帧 6411 六个实际 PS 提取原始 UnityPerMaterial 字节，检查现有材质经过 Unity 上传后交给生产着色器的值。没有截图拟合、曝光补偿、重做材质文件或修改光照代数。

## 1. 查到并修复的错误

官方 `characternpr_hair.shader:60` 的 `_AnisotropyColor2` 是普通 **Color**，当前 CharacterLit 却错误加上 `[HDR]`。不是两个文件应该存同一个数值：普通 Color 的序列化 RGB 在 Linear 项目上传时转换到线性，HDR 则保留线性输入；alpha 不做这种转换。

实际 PS22257 的 `_51_m42` 位于 UPM byte 240（c15），在第二层高光表达式中被消费。b126:307/1061 提供相同位置的 `_AnisotropyColor2` 标签和 lobe 消费线索，不能套旧 b125 的资源语义表。

| RGB | 材质文件 / 错误 HDR 上传 | 捕获的实际 GPU 常量 |
|---|---|---|
| R | 0.301129431 | 0.0737994239 |
| G | 0.326204151 | 0.0868905336 |
| B | 0.635294139 | 0.361306876 |

先写官方 schema 声明门禁，再加入**实际生产 UPM 输出**，旧实现在 225 个分量中只有上述 3 项 FAIL，其余 222 项一致。随后只去掉错误 `[HDR]`，原材质文件中的颜色值不动；复跑 **225/225 PASS**，`2e-6` 门限不变。不得用手调颜色、材质 `.linear` 二次转换或全局增益来代替这个声明修复。

额外两组独立已知输入（8 分量）通过：普通 Color 的 RGB=(.002,.25,.73) 按标准 sRGB 分段函数上传；HDR 的 RGB=(.002,.25,4.3) 保持原值；两者 alpha=.37 不变。不是把捕获值倒推一个补偿系数。

## 2. 来源与标注边界

只离线重放已有 `C:/Users/Administrator/Downloads/正面.rdc`，未启动游戏或注入。复用 `capture_replay_inventory` 的打开/新输出契约以及现有 `extract_front_frame_constants.parse_hlsl` 的 packoffset 解析器，**不调用旧 variant 排名/union-name 标注**。

`Tools/capture_material_uniforms.py` 钉住重导 provenance hash、实际 PS 的 SPV/HLSL hash及六个明确 named candidate 的 hash。逐成员检查 `(offset,type,size,count,major)` 与完整 block size；从实际 set1/b0 descriptor 的原始 buffer range 读取 bytes，而不是依赖旧 JSON 中重建的成员 cursor。实际程序引用的匿名成员 token 判定 active；保留未命名字段为未批准，不填猜测标签。

| Draw | 部位 | PS | 原始 UPM 字节 | 本轮命名参考 |
|---|---|---|---|---|
| 776 | iris | 22259 | 400 | Eye b28 |
| 786 | body | 22250 | 368 | Skin b114 |
| 835 | cloth_01 | 22255 | 336 | Cloth b471 |
| 850 | cloth_02 | 37669 | 336 | Cloth b472 |
| 860 | face | 37671 | 384 | Skin b138 |
| 875 | hair | 22257 | 448 | Hair b126（不是 b125） |

共 2272 原始字节。布局一致只允许这份**显式字段标注**，不是全文算法/控制流/编译 variant 等价证明。collector 拒绝错 frame、程序 hash、缺失/重复 block、类型/布局变化、截断、非有限数据；successful Shutdown 后才写 complete，GUI exit=0 不作成功依据。最终代码再次导出，新 complete 与首次字节相同。

私有包：`Validation/Captures/material-uniforms-20261001-01`；固定 manifest SHA256 `943267aebf73d76b1aa0b8755c66bc5ba62af2f76085dba58c23bd6caee7909d`。原始 bytes/捕获/dump 不上传；公开的只是检查代码、数值报告和 hash。

## 3. 生产 GPU 审查与排除范围

`EndfieldMaterialUniformProbe.hlsl` 读取**CharacterLit 自己实际的 UnityPerMaterial 声明与上传**，不是新 shader 仿造声明，也不是 `Material.GetColor` 代替 GPU。只有显式 debug mode 100–120 输出诊断；正常 mode=0 不走此分支。`EndfieldMaterialUniformValidation.RunBatch` 在独立 D3D11 / Linear batch 初始化当前 URP，复制六个实际材质到临时对象，以浮点目标读取已知常量。

覆盖 **120 个实际 PS active 字段 + 六个 BaseMap_ST = 126 字段 / 225 分量**。BaseMap_ST 属于 VS 采样坐标契约，这里额外验证其上传值，不把它谎称 PS active。raw 每字段解码与 JSON float32 身份复验；生产材质全部在前后核对文件 hash，只改临时 quad 的 Cull，不改资产、场景、模型或管线设置。诊断 mode 在 finally 恢复。

**单独排除六个 `_DisableRainEffectOnMaterial` 字段**：现有 dry helper 未实现它们。捕获 selector=0 只用于记录受限输入，不代表“雨已关闭”，也不证明整个 weather 分支正确。所有天气行为、CP/global/light/shadow/post producer、描边 VS、其他 17 SMR variant、MPB 并发/最终场景生命周期仍不由本审查认证。

## 4. 验证与复跑

保留 `uniform-red.txt`（旧 HDR 实现 3 FAIL）和 `uniform-gpu-report.txt`（修复后 225 项 + 独立 8 分量 PASS）。五项相关 GPU 回归及 Eye 八态 policy 通过：native Hair/Eye、Hair split、Skin 28例、Official 17例、native Cloth。新 Python 模块 36 项测试、116/116 可执行行覆盖，Ruff/Pyright 通过；这是新导出模块覆盖率，不是 C#/HLSL/整个工程覆盖率。全套测试结果见 verification。

```powershell
$env:ENDFIELD_MATERIAL_UNIFORM_REPORT='D:/EndfieldTechLib/notes/your-new-run/uniforms.txt'
# 先新建 your-new-run；报告文件必须不存在。独立顺序 batch，不与当前 Editor 并发。
# Start-Process -FilePath 'A:/Unity/Editor/2022.3.30f1/Editor/Unity.exe' -WindowStyle Hidden -Wait
# 参数：-batchmode -force-d3d11 -projectPath "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner"
# -executeMethod EndfieldShaderPack.EndfieldMaterialUniformValidation.RunBatch -quit -logFile "新路径.log"
```

导出入口：在 official qrenderdoc 的 `--python` 中运行 `Tools/capture_material_uniforms.py`，设置 ENDFIELD_TOOLS_PATH、ENDFIELD_CAPTURE_PATH、ENDFIELD_CAPTURE_OUTPUT（新空目录）。任意新捕获/变体不能自动替换固定 manifest，必须重新审查。

主 HEAD / 9557-entry 暂存索引 / recovered 场景 / quality、graphics 设置保留。seal v1/v2 未重写，仍有 79/24 pending 和既有三处合计 drift；不是全量完整 PASS。

## 5. 下一正确接手点

材质常量主线已具备可复跑的真实 GPU 上传门禁，不需增加补偿层。下一步查 CP / directional-light / environment 参数选择和空间语义，再查 render-state、weather producer/消费者及正式场景绑定生命周期；按原表达式和作用域修复，不先调效果。解包动作/MMD 正式出片仍在这些主线工作之后，不因本轮数值通过就宣称全部完成。
