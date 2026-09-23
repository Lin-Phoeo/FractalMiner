# 2026-09-23 源码派生角色光照：实现与验收

接续 `development-sync-20260923.md`。用户已认可上一轮模型/UV 修复；本轮保留那些几何结果，替换干燥角色展示条件下的主颜色计算。不是“完整官方管线已经还原”的声明。

## 交付与使用

- `EndfieldCharacterLit.shader` 接入独立 Hair、Skin、Cloth、Eye HLSL；body 与 face 共用 Skin 的不同分支。
- 场景的 `EndfieldOfficialFrameGlobals.useSourceShading` 默认启用新路径，关闭可比较旧近似。仅在捕获 profile、平坦环境、不透明、非 debug 条件下启用；非眼睛视差材质仍走旧路径。
- `capturedEnvironment` 是可选的明确绑定。未恢复环境数据时关闭 IBL，避免 Unity 未绑定 cubemap 的默认内容造成虚假反射。
- 生成场景：`Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity`、`Assets/Scenes/CoralCoast_Repaired.unity`。
- 固定相机 A/B：`Validation/official-source-shading.png` / `official-legacy-shading.png`，以及 `coral-source-shading.png` / `coral-legacy-shading.png`。
- 这些场景、图片、原游戏/模组资源与 RDC 仍留在本地，不随源码上传。原始场景及上一轮模型修复保留。

## 根据一手证据纠正的匹配

一手资料为本地 `正面.rdc` 的 frame 6411 导出、反射/绑定表，以及 `_dump_1.5.3/.../characternpr/` 的反编译 HLSL。旧研究文档和自动命名结果都不是独立证明。

| 事件 | 材质 | 本轮使用的源码族 | 限制 |
|---|---|---|---|
| 776 | iris | eye b28 / b52 相同签名族 | 使用 b28 的干燥主颜色公式 |
| 786 | body | **skin b114 / b208** | 并非旧报告的 cloth b401 |
| 835 | cloth_01 | cloth b471 / b474 / b911 / b914 | 绑定语义吻合，不宣称唯一编译变体 |
| 850 | cloth_02 | emission + specRamp cloth 共同公式 | 自动匹配仍有两个不同签名；保留告警 |
| 860 | face | skin b138 / b232 | SDF 面部主颜色 |
| 875 | hair | hair b125 系列 | 自动匹配仍有两个不同签名，使用已核对材质参数的 b125 子集 |

Body 的 set1 t1 是 1024×32 BC7-sRGB LUT，t2 是 256×1 ramp，t3 是 BC5 法线，t4 是 base。b401 的 t1/t2 却是 packed P / clearcoat，明显不符。b114/b208 的纹理语义和常量偏移吻合；body 应使用 CP3 环境色和 CP4 主灯色。旧报告把 offset192 的 SkinRimOffScale 命名成 ClearCoatSmoothness、offset208 的 SDFRimColor 命名成 ClearCoatColor，也随之纠正。现有材质的 sRGB SDFRimColor 已与捕获 linear 值吻合，不再次手动线性化。

工具 `extract_front_frame_constants.py` 的两处系统错误已修正：

1. folder hint 不再限制搜索域；所有族按证据评分，同分时才优先 hint，保留全部同分歧义。
2. 比较纹理槽时排除 storage buffer 和 sampler，避免所有正确候选的 set0 匹配都被误判。

对 786/835 添加了本帧经过人工核验的纹理语义约束，约束的是槽名而非某个文件名，不抹掉 DITHER 等变体。最新报告另存于 `Validation/Captures/tifuluosi-front-20260917/extracted-source-shading-reviewed-20260923/`；旧 `extracted/` 保留用于追溯，**其中的 body/cloth 自动属性名不应继续当作权威数据使用**。新报告 786→b114，835→b471，匹配评分均为 5/5。

## 本轮实际实现

### 共用光照

恢复 ramp alpha、视角 ramp、遮挡 mask、环境法线渐变、独立 diffuse/specLight，以及 ramp 染色后的亮度归一化。旧版直接 `albedo * rampRGB * lightColor` 不能等价表达这些步骤；白色 RGB ramp 的 alpha 改变，必须改变结果。

### 皮肤与身体

- SDFMask.g=0 是 SDF，g=1 是普通 N·L；旧版权重用反。
- SDF 阈值随物体空间水平光向变化，保留 Repeat/LOD0 与越界 ramp 坐标行为。
- BaseMap alpha 是光照遮挡，不是不透明材质的透明度。
- LUT 用 rim 染色前的 albedo 建索引；直接 GGX 使用原始贴图法线，不能换成 SDF 重建法线。
- body 无 SDF 分支等价于 mask=(1,1,1,0)，不读取 SDF/面部高光贴图，不套用布料 IBL。

### 头发与布料

- 头发采用 b125 RGorAG 法线，不套旧 RG/BA 分离法线猜测；移植主/副各向异性高光、LineMap 和反向光照项。
- 布料使用源码的伪光半程向量、GGX/粗糙度二维 specRamp 坐标，不增加无依据的 N·L 高光乘数。
- GGX epsilon 为 1e-4。支持的 clearcoat 数学采用五次幂；环境 BRDF 的多项式输入是 N·V 和 roughness，不能把二者都替成 N·V。
- 保留 emission，在源饱和度处理后、VFX/曝光前加入。GPU 测试同时覆盖 ShaderLab Color 的 sRGB→linear 上传规则。

### 眼睛

- raw UV 用于解析球面与 matcap 法线；贴图 ST 只作用于采样，保持模组 Y 翻转顺序。
- b28 固定眼睛视差，不受旧布料 `_UseParallax` 开关控制。
- matcap 按 `texture.rgb * color.a + color.rgb * texture.a` 混合，再使用独立 specLight；保留 CP13 眼睛项。
- 各族只在末尾做一次输出曝光，不再次乘主灯色。

## 验证

采用测试先行和分层验证，而非把成功导入当成视觉验收。

| 检查 | 结果 |
|---|---|
| Unity 2022.3.30f1 / D3D11 编译与 GPU 执行 | 通过 |
| hair/cloth/eye 常量纹理、ramp alpha、matcap、自发光 | 11/11 GPU–CPU 对照通过 |
| skin SDF 权重、ramp 过界 Repeat、base alpha、无 SDF body | 21/21 通过，最大通道误差约 2.54e-6 |
| capture 工具 + 新匹配规则单测 | 35/35 通过 |
| 两个 Python capture/extract 工具的分支覆盖率 | 单测 + 本地导出集成运行，合计 94% |
| 原版/珊瑚海岸整模 | 重复导入、GUID、TBN、UV、场景重载、GPU 输出检查通过 |
| 组装人物虹膜开/关贡献 | 1389 像素可见变化 |
| Python 环境依赖审计 | pip-audit 未发现已知漏洞，无本轮新增项目依赖 |

回归探针：C3 53242 像素、平均 linear luminance .472840；C6 23955 像素、.383542；C0 36024 像素、.036097；三者 near-black fraction=0。数值仅表示这些诊断视角的输出，不是与官方画面的相似度分数。

首次 RED：旧光照面对 ramp alpha 0/.5/1 输出相同颜色，6/6 对照失败。新路径纠正后通过；布料测试还揭露了未绑定 cube 的默认亮度泄漏，现已显式屏蔽。匹配规则的新测试也先复现了错误 hint 屏蔽正确候选的问题。

一键本地验收入口：

```powershell
& 'A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe' -batchmode `
  -projectPath 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner' `
  -executeMethod EndfieldShaderPack.EndfieldOfficialShadingValidation.RunAll `
  -logFile 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Logs\official-shading-acceptance.log' -quit
```

运行前确保没有另一个编辑器打开同一工程。报告在 `Logs/official-shading-numerical.txt`、`official-skin-shading-numerical.txt`、`recovery-validation.txt`。

## 还没有实现的官方效果，以及下一步的明确输入

目前验证的是**选定干燥平坦环境子集的公式和 Unity 集成**，不是官方全帧逐像素一致。静态姿态、投影/裁剪、动画、专用覆盖层、dither、雾、局部灯光、天气/湿润、蒙皮矩阵细节仍需进一步核对；VFX 开关在本帧关闭，眼睛 VFX rim 的法线适配也未单独验收。

已经从捕获绑定查到、但本轮尚未导出/接入的资源：

| 目标 | 本地捕获证据 | 后续操作 |
|---|---|---|
| 布料环境反射 | ResourceId::14188，128² BC6_UFLOAT，6 面 8 mip；835/850 set0 b45 | 离线导出全部面和 mip，确认坐标/色彩空间后绑定 profile |
| 屏幕阴影 | ResourceId::58932，2560×1600 R8G8；角色 set0 b22，生产事件 744/748 | 先分析 R/G 与深度生成过程；不能把固定截图阴影贴到不同姿态上冒充动态阴影 |
| 官方后处理 | event1205 / PS36235；LUT19397，输入19394，bloom58923，输出19599 | 匹配 uberpost b354；还原 LogC→LUT→sRGB/dither，而不是随意换通用 ACES |

后处理捕获参数包括 Lut_Params=(1/1024,1/32,31,1)、BloomParams.x≈.36604023、Sharpen.x=.3。仅凭参数未接入完整处理链。最终视觉验收还需要把姿态、镜头、阴影、环境和这条后处理链一起锁定后再做官方帧差分。

## 保存与回退

本轮提交接在记录分支 `fix/typhoeus-render-explosion-20260917` 的 `55b95b8` 后。继续采用隔离索引，不切换当前 main，不纳入其他工程的删除、资源包或未关联的场景改动。旧光照开关可立即比较；Git 提交记录提供源码回退点。
