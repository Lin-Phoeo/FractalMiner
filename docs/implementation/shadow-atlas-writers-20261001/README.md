# 官方阴影 atlas writers：实际状态审计与裁切修复

本轮接续 `shadow-producers-20261001`。只认证 frame6411 的 **23 次实际 atlas 深度绘制、120 个 raw CB 范围、程序身份/输入绑定/显式状态**，以及生产 `EndfieldCharacterShadowAtlas` 的普通 cutout Alpha 表达式。不认证完整阴影、动态分配、最终画面或 MMD；不做逐像素拟合。

## 1. 实际官方绘制契约

`Tools/capture_shadow_atlas_writers.py` 先核旧 archive 的14个程序 raw SHA，再离线重放确认23个 actual pipeline、VS/PS、index count 和 atlas depth view；资源 usage 只是找事件的线索，不代替上述核验。原始结果来自 `Validation/Captures/shadow-atlas-writers-20261001-final-02/`，只有双 Shutdown 成功后的 `complete.json` 代表完成。

| 项目 | 23 次 draw 的实际值 |
| --- | --- |
| 目标 | 32538 / view32540，D16，4096×2048，1 mip / slice / sample，无颜色附件 |
| renderpass / framebuffer | 1560 / 32544，depth attachment0，renderArea=(0,0,4096,2048) |
| 深度 | test/write=true，GreaterEqual，bounds=false，stencil=false |
| 光栅 | CullNoCull，frontCCW=true，depthBiasEnable=true，constant=-8，slope=-0，clamp=0 |
| viewport | x=3072，y=0，width=height=1024，depth range0..1 |
| scissor | x=3073，y=1，width=height=1022，enabled=true：四边留一像素 |
| clear260 | 精确 APIEvent260→chunk24904 `vkCmdBeginRenderPass`，pClearValues[0].depthStencil.depth=0，stencil=0 |

clear 的结构树保存在 `captured-clear.json`；**VkClearValue 是 union，depth target 必须读 depthStencil，不能把未使用的 color 三/四分量解释为清色**。结构序列化按 SDBasic 选择正确 POD 字段，保留全部子项/union标记，不用所有 AsXXX 的混合猜值。API schema 查 [RenderDoc1.46 structured_data.h](https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/structured_data.h) 与 [Vulkan pipeline state](https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/vk_pipestate.h)。

所有23draw只写 `(3072,0)` 这个 cell，与先前 raw resolve slot0 rect `(0.75,0,0.25,0.5)` 对应。CB 中有7槽**不证明本帧7槽都绘制**，也不证明C++动态分配算法。不得从一种捕获硬编码通用七角色排布。

## 2. VS / PS 不可合成一个通用透明测试

| actual PS | events | 该程序的裁切逻辑 |
| --- | --- | --- |
| 9063/9061/9044/9046（raw identical） | 272/277/326/331/336/341/346/351/356/366 | 空 fragment；不采样 Alpha、不 discard |
| 9065 | 282/286/291/296/300/304/308/312/316/321/361 | SampleBias(base alpha) × material alpha − cutoff <0 才 discard |
| 9050 | 376 | sqrt(SampleBias(alpha) × material alpha) 对屏幕坐标噪声作有符号 dither |
| 65356 | 371 | base cutout + 额外空间/纹理裁切 + instance fade/dither + sqrt alpha dither；不能用9050代替 |

9065：base set1/t1，actual s11 set0 是 Linear min/mag、Point mip、Wrap U/V/W、sampler bias0；shader 额外 SampleBias 输入来自 set0/b14 c26 / byte416。material alpha 在 set1/b0 c6.w /108，cutoff c2.y /36；VS BaseST c10 /160，只应用一次。切勿把匿名 m9 直接用前向 UPM 的全块尺寸/索引标签套进去。

VS9064/9049 raw identical；VS9043/9045/9060/9062 raw identical；65355有不同varyings。VS位置尾链是先skin/instance，再 `mul(set0/b8 matrix, world)`，然后 `clip.y=-clip.y`；**没有 vertex normal bias 不等于没有 raster bias**。

所有23次 VS b8 raw相同：`1738af83c64c021f72d93b9cb59f76be27ecb42fdd63a2ff7d711cd2afc6aa6e`，64 bytes，resource864@703360，column_major。矩阵按列解释：b8 row0=2×resolve slot0 row0−(0,0,0,1)，row1=−2×unit row1+(0,0,0,1)，row2/3保持；之后VS仍有Y反号。此为本捕获公式/数值核查，**不是**Unity/D3D的RT朝向或实时Fit策略完整证明。

vertex buffers/index buffers/attribute binding、各stage CB offset和descriptor bytes全部留存。未导出全部vertex payload/重求skin，所以不能声称本轮验证了全部顶点或palette生产；statically unused资源没有绑定也不代表可以从其他动态变体删去。

## 3. 实际修复范围

生产 `EndfieldCharacterLit.shader` 的 `fragShadowAtlas`：source flags开启 + `_EnableAlphaTest` 时，改用 `float` SampleBias alpha × `_BaseColor.a` 后 clip；之前漏材质Alpha、漏 `_EndfieldCapturedGlobalMipBias`。source flags关闭的旧路径保持原行为；opaque不因Alpha=0消失。UV沿用VS既有BaseST一次。

**未顺带修改** D16/raster偏移、矩阵、光照、曝光、后处理、GBuffer、dither/dissolve、材质/场景。删除“caster必须无偏移”的错误说明，明确旧R16颜色图adapter未认证。下面旧 reversed-Z 适配说明只代表历史URP实验，不能用来覆盖本轮实际 Vulkan D16 状态。

## 4. 先失败，再修，回归

`EndfieldShadowAtlasCutoutValidation.RunBatch` 读取并核 actual PS9065 HLSL SHA，暖机后以实际生产 atlas pass index2绘制合成quad，不用另一份替代shader。固定16×16 R16读回，64×64显式mip链；GPU D3D11/Linear，绝对门限2e-4。

- 旧18个scale/cutoff组合 +4个bias +2个路径保护：24例，7 FAIL。原始报告留存。
- 修复后同24例全部通过；增加BaseST一次、source shading关闭保护，最终26/26。
- Alpha乘积与阈值相等时不discard；缩放=0但cutoff=0仍keep，符合实际 `<0`，不是 `<=0`。
- 新离线工具最初33例失败（工具不存在）；后因手算index总数错了一项测试：actual总数303756，不是304806。以archive实际23draw核实后修测试，未调生产阈值。最终36例 /116 Python语句 /100%**行**覆盖（不代表分支/Unity/全工程）。
- 六类fresh Unity batch回归：cutout26、lifecycle13、sampler3072、shadow consumer238、material upload225分量、light selection688，全部通过/exit0。
- 全套Python：461 passed /3个历史skipped /80 subtests passed /2个既有Pillow warnings。Ruff、Pyright通过；临时pip-audit+pytest/numpy/pillow环境无已知漏洞，不代表Unity全依赖已审计。

本地全过程：`D:/EndfieldTechLib/notes/shadow-atlas-writers-20261001-01/`；原/中间/final报告都保留。源actual HLSL来自 `Validation/shadow-atlas-writer-audit-20261001-01/`，SPIRV-Cross工具身份/args沿用前一增量。验证时只创建内存quad/material/texture和preview场景；全部销毁、还原globals/active RT，不保存资产。

## 5. 下一轮必须做什么

1. **D16 atlas生产**：本轮状态可以直接作为输入契约；先用两个不同深度的重叠quad、两个提交顺序，验证官方max-depth选择、clear0、bias的实际后端尺度与方向，以及一像素scissor边界。不要直接将Vulkan GreaterEqual字面粘到Unity旧R16颜色图，或把raster bias数值减在颜色输出上冒充D16。
2. **分区与caster可见性**：资源格式、实际矩阵Y尾链、texelSize/rect同步、每slot只画对应caster，以及阴影独立culling；现有camera cullResults可能漏掉画外投影物。单捕获的cell0对齐不是通用动态allocator。
3. **其他裁切与模板域**：9050/65356的原生纹理/instance参数、PreGBuffer/其他物体遮挡、744/748 stencil !=4/==4、源R producer；不能用“普通cutout已修”消掉这些。
4. 再推进地面/Overlay/天气/final生命周期，正式场景native输入常驻与动画更新，最后解包动作/MMD完整出片。

原封存研究、v1/v2 manifest不改；79/24 pending不抹掉；主HEAD/9557-entry index/原角色场景/Quality/Graphics字节保持。当前真实剩余工作见 [remaining-work.md](remaining-work.md)，不是把历史截图分数改名成完成率。
