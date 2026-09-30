# 官方渲染证据基线 v1（2026-09-30）

## 1. 基线身份与边界

用户目标：按官方算法、输入、光照和管线逻辑还原提弗洛斯，随后接解包动作与MMD；不以截图逐像素拟合、改曝光凑颜色或轮廓分数作为正确性定义。

**v1封存的是可追溯证据与本轮资料修订，不是“全部官方规格已闭合”的证书。** 原资料确有数学、输入及调度错误，本轮已在原文修正。仍省略的公式、未定位的生产端及未覆盖的变体不得随之变成“已确认”。当前资料还不能独立保证全游戏、全天气、全视角完全等价。

组成：

- [plan.json](plan.json)：资料类别、14模块六维验收状态及待补项。
- `manifest.json`：资料、源码及捕获证据的相对路径、字节数、SHA256；HLSL还保留keyword头。只发布元数据，不上传游戏源码/RDC/纹理/网格。
- [详细索引](../../research/INDEX-shader-sources.md)及原文：继续复用，不另写一套含混的“还原公式”。
- [上一批天气与阴影审计](../../research/source-contract-audit-20260930.md)：保留通道、雨滴时间、粗糙度、IBL、反向Z等已核更正。
- `Tools/render_spec_baseline.py`：防来源漂移检查，**不是shader等价证明器**；`complete=false`时不能宣称全量规格验收。

原文及用户暂存索引备份：`D:/EndfieldTechLib/notes/render-spec-baseline-20260930-01/`。本轮不改运行时渲染、材质、场景、网格、原始解包数据或冻结后处理实现。

清单盘点：6467份解码shader/wrapper、223份离线捕获程序/状态文件、1份原RDC身份，以及研究、交接、学习、外部技术库资料、7份C6版本档与字节保留策略；去重共6771个文件。**盘点/哈希数量不是逐指令核查覆盖率。** 本轮在原文修正了四族、后处理、描边/角色阴影的12份仓库资料及外部C6各层；天气两篇沿用上批关键核查。社区C3和旧C6验收已经标明不能充当规范。

C6分析/逐行/交接共7篇已收入`external/reports/translations/`，按UTF-8 LF存档；原技术库逐字节hash独立保留，正文以换行归一化复核相同。不仅记录D盘路径，Git回退也能恢复关键译读。未把官方shader原文件或第三方代码库复制进仓库。

## 2. 什么是官方证据

| 层 | 可证明 | 不可证明 |
|---|---|---|
| 现有RDC的SPIR-V、descriptor/常量、event/state | 该捕获、该draw实际程序及GPU输入 | 所有姿态/天气及CPU/C++生产算法 |
| `_dump_1.5.3`解码GPU源码及wrapper | 该快照的表达式、接口、派发及ShaderLab状态 | 与当前安装版本必然相同；wrapper排列就是实际render graph |
| 回源修订译读 | 明确范围内解释源码 | 未展开段落或省略伪码是完整规格 |
| Unity实现、测试、阶段报告 | 我方实现及指定输入测试结果 | 官方做法、独立真值或未运行阶段已通过 |
| 社区项目/文章/书签 | 候选方法与检索线索 | 官方规范或可覆盖一级证据的结论 |

身份必须绑定`(捕获/源码哈希, shader, subshader, pass, stage, keyword组合, per-draw布局)`。编号相同不跨族套用；frame6411 event/resource ID不迁到213.rdc。源码快照名不等于安装版本；cloth/hair候选签名有歧义时保留候选，不擅定唯一匹配。

最小编号、catch-all都不等于全部keyword关闭。查wrapper完整条件及文件头；末尾else也可能引用含基础keyword的编译产物。

## 3. 逻辑闭合的六个条件

各模块至少检查以下六维；有pending或未答问题，就没有完整认证：

1. **formula**：完整数据流、常数、乘数、swizzle、分支、钳制及归一化下限；“同族/相似”不代替证明。
2. **variant**：实际编译组合；单开keyword的diff不证明组合路径可拼接。
3. **input**：顶点、palette、纹理/缓冲布局、精度、位模式、ST顺序、坐标、sampler、sRGB view与数值域。
4. **producer**：输入如何生成、何时更新、共享关系；读取用途不等于恢复CPU字段名。
5. **render_state**：附件格式/clear、反向Z、模板位、剔除、RGB/alpha分别混合、调度及生命周期。
6. **runtime_binding**：实际draw正确绑定，动作变化仍成立；不贴固定捕获纹理冒充动态生成。

验收采用独立数值算例、边界/位布局测试、资源/GPU状态检查及动态绑定回归。**不要求官方截图逐像素求差；但“结构像”不免除公式和输入错误。** 原源码短向量、NaN、反向smoothstep或无除零保护路径先忠实记录，平台适配另列，不偷偷加入近似后称原版。

## 4. 本轮确定更正

以`…/runtime/shaders/`为源根；F/V是同号Fragment/Vertex。完整公式仍回原文及对应源码，不把本表概要当可执行端口。

| 部分 | 正确契约 | 一级证据 |
|---|---|---|
| Skin插值器 | TEXCOORD7为float3 rest-position，不是float4切线；无“雪把切线当位置”的源码bug | `materials/characternpr/characternpr_skin/Sub0_Pass0_Vertex_b138.hlsl:283,299,464`、F:375 |
| Skin rim | `clamp((1-clamp(ndv*.85+.15))*(mask*scale),0,1)`；旧括号改变了遮罩作用域 | 同F:628–631 |
| Skin光/法线 | 伪光向按源下限归一，GGX epsilon≈1e-4；无雪不自动选雨法线；HighlightMap不能额外乘CP13.w | 同F:710,778–796 |
| Skin SDF | RG平均、B重建；A读入未用，不能叫有效遮罩。光y替换为6.103515625e-05后归一，不能交换；ramp背光项保留在abs内，G=1取普通法线 | 同F:737–757 |
| Cloth法线 | 先`sample.w*=sample.x`再`.wy`；不是两分量都取A的`.aw`；无雪时_1991选原始N，不选雨法线_1855 | `materials/characternpr/characternpr/Sub0_Pass0_Fragment_b401.hlsl:424–430,885` |
| Cloth clearcoat | `_2244=_2243²; _2246=(_2243*_2244)*_2244`是**5次幂**；保留条件除法、≈1e-4与第二层mask | 同F:949–959 |
| Cloth IBL | 有理拟合分别使用N·V与roughness幂；reflection/GGX法线不能换成雪法线；b401不是body | 同F:935–942,975–1007；捕获归属见原文 |
| Eye光向 | 根矩阵→safe normalize→清局部y→变回世界；该步不额外normalize；后续ramp保留源码自己的归一化 | `materials/characternpr/characternpr_eye/Sub0_Pass0_Fragment_b28.hlsl:665–678` |
| Eye alpha | 源码用alpha作散射/预乘/条件输出，没用它计算视差；不能称“瞳孔深度” | 同F:420–431及主色段 |
| Hair天气 | 非零雨字节不一定跨0.01门槛；时间冻结条件保留；雪coverage不直接吃SSM.g | hair F_b125:656–684,933,970 |
| 描边身份 | skin b273、hair b306、主CharacterNPR b1088各自派发，不是三族共用b273 | 各wrapper Pass1条件 |
| 平滑法线 | 此流是TS半球xy，z=`sqrt(1-clamp(dot(xy,xy),0,1))`，不是折叠八面体 | skin V_b273:435–437 |
| 描边投影 | VP3×3不是仅view旋转；保留有符号543，不擅自abs | 同V:447–459 |
| 蒙皮/前帧 | 80.x组供当前position/normal/tangent，80.y不是切线组；保留V431选择方向，零符号分支也不替成sign(0) | 同V:320,415–431 |
| Overlay | 部分投影项清零不等于正交；PreDepth的CPU调度不能由属性声明证明，眼影/发影不必同序 | overlayshadow V与frame6411状态 |
| 地面SH | 4×4迭代，AB-LUT UV保留×1/256；.95限制混合量，不保证最终至少5%亮度 | shadowreceiver F:546–592 |
| UberPost | b354：锐化→主色曝光→合成已曝光Bloom→暗角→LogC→LUT→OETF→抖动；不再次曝光整个合成色 | `postprocessing/uberpost/Sub0_Pass0_Fragment_b354.hlsl:234–257` |
| 暗角/抖动 | aspect内/外lerp权重分别Params2.w/Params1.w；抖动为`[-.175/255,+.175/255)` | 同F:244及输出末段 |
| LUT | NONE+ACES进b1，!NONE&&ACES才b2；高光混合2.0拉满；ACEScc上界对应65504 | lutbuilder wrapper:25/35、F_b2:185–187 |
| FinalPass | afterpost=`background*aft.a+aft.rgb`，alpha为背景保留系数，不自动换1-alpha | finalpass F_b11:178–181 |
| Bloom两条路径 | dump四raster pass不等于frame6411的17compute dispatch；compute prefilter为13tap，raster代表5tap | 捕获bloom-source-01及bloom-samplers-02 |
| Raster Bloom | ENABLE_ALPHA乘输入RGB、输出alpha仍1；CHARACTER_MASK有独立角色分支；已查三对LOW/HIGH同值 | bloom F_b4:177–180,206、F_b3:180–187、b2/b6、b11/b12、b13/b14 |
| 其它后处理 | DOF far不命中整个MRT1置零；最大device-depth非一定最远；lensflare界外计可见；Frosted单位1texel | 修订`official-postprocess-stack.md`源码定位 |

四族文档共同保留`dot(view,view)*rsqrt(max(dot,1e-8))`，短向量不等于length；PCF sampler名字不证明实际寻址模式。外部C6摘要及逐行层已同步，关键更正在本表供Git读者使用。天气RGBA通道、雨滴时间、粗糙度、多散射分母继续沿用上一批审计。

## 5. 跨模块依赖

下图是依赖关系，不是凭wrapper排列臆造的完整执行图；调度须查真实事件。

```text
原网格/材质/纹理 + 解包动作或MMD最终骨态
         │（动作/IK后更新palette和部件root）
         ▼
PreGBuffer分类/法线 + camera depth ─────────────┐
动态shadow atlas → resolve R/G ────────────────┼→ Forward/Outline
         └→ 地面receiver（独立，不是刘海）       │        │
逐draw模板/深度 ──────────────────────────────┴→ Overlay/透明
天气包/水线/遮挡/雨雪图 → 对应变体 ──────────────────────┤
                                                       ▼
HDR输入 → compute Bloom生产 → UberPost实际组合变体 ← LUT生产
                                       │
                                       ▼
                 afterpost/Final/UI（启用与顺序依真实事件）
```

逐资源标色彩域：存储/view的sRGB、着色linear、LogC LUT坐标、LUT采样输出、显示OETF数值、RT硬件编码不是同一回事。不能因文件叫LUT就开sRGB。frame6411主后处理输入19394是RGBAHalf、Bloom58923是R11G11B10_FLOAT、grading19397是1024×32 RGBAHalf、输出19599是RGBA8_UNORM；不推广到其它捕获。

Overlay已观测状态（Vulkan反向Z；不要与ShaderLab默认LEqual直接按名称比较）：

| event | stencil ref/read/compare | depth write | RGB blend | alpha blend |
|---|---|---|---|---|
| 968眼白叠影 | 4/20/Equal | Off | Zero/SrcColor | One/One |
| 971第二眼白叠影 | 20/20/Equal | Off | Zero/SrcColor | One/One |
| 993发影预深度 | 4/20/Equal | On | Zero/One | Zero/One |
| 997发影颜色 | 4/20/Equal | Off | Zero/SrcColor | One/One |

Skin写36、eye写52；与20按位与分别4/20，分类互斥。复用原叠影mesh，不造近似面片/把ReadMask改0称原版。DISABLE_DRAW_UNDER_HAIR开启省略GBuffer test，不能凭名字反转分支。BaseColor.a在叠影alpha中有二次作用，VFX路径按原式。

## 6. 当前未闭合项

完整清单在plan。不能凭文档字数、全文读取、编译过或历史分数消掉以下缺口：

- dump与每draw程序精确匹配，尤其cloth/hair同签名候选；body b114/b208还缺专门完整规格。
- 原顶点各流、smooth-normal、root/palette生产与更新，不让Unity重建数据自证。
- IV/SH、点光分箱/cookie/PCF/LTC、方向阴影、动态atlas分配、雾的尾链与生产；URP简化灯非官方。
- 天气RGBA8位包、水线、UV scale、纹理/VerticalOcclusion生产及湿天气真实绑定。
- Overlay投影/GBuffer/PreDepth生产，地面receiver的SH/AB-LUT与匿名bias/dither。
- LUT生成事件与曲线、完整后处理组合、Temporal历史、Final/afterpost真实调度。

优先闭合当前干燥角色的具体路径，之后单独扩天气/局部灯/动态视角；每次标支持集合，不将子集通过扩写为全部完成。

## 7. 下一阶段实现审查顺序

1. 建`source/pass/variant → 输入生产者 → 我方函数/feature → 测试`表，漏项/近似分别登记。
2. 核网格/部件root与各法线角色；动作/MMD最终骨态后更新，MPB合并不互相覆盖。
3. 核四族完整公式和实际资源。b401不是body，不凭衣服名字套b401，不加无据亮度增益。
4. 核PreGBuffer模板、atlas/resolve、Overlay附件与调度；通用不透明CharacterLit材质不能冒充Overlay。
5. 核天气。已发现`Editor/EndfieldClipDriver.cs:210`与`EndfieldAclIkDriver.cs:117`直接写普通`wetness` float并称官方：它不是RGBA8位包，CP10.z也不是雨速。登记确定接口错误，待生产契约闭合后修；本轮不改这两个文件。
6. 核compute Bloom/UberPost曝光域、格式、采样及编码；冻结实现若有错必须独立记录解封/修订和回归，不静默改。
7. 解包动作、VMD、镜头变化下做绑定/公式/状态回归；渲染正确不代表retarget/IK/表情/次级物理全正确。

旧“偏暗48%”“单一增益”“M5全闭合”“IoU”等仅历史报告，不继续当现时官方规格。学习资料及旧handoff的像素/删垃圾要求也不覆盖当前用户要求。

## 8. 写死封存与复核

采用**版本目录＋内容哈希＋Git不可变提交**，不是chmod用户文件或覆盖原证据。v1发布后保留原manifest；新证据建v2，记录旧digest、理由、回源证明与复核，禁止原地重生成清单掩盖变动。

manifest不包含自身，plan/foundation包含在清单中，无循环哈希。按字节封存，换行转换也报变动；`.gitattributes`仅对本批存档/修订文本设`-text`，禁Git自动LF/CRLF转换（当前core.autocrlf=true），不改变其它资源。跨机还须提供未上传的本地dump/离线证据并保留原字节，或记录迁移重新封存。GitHub仅有元数据，不把未上传原资料当“从未创建”。

```powershell
# 只读完整性检查：0=字节完整（仍需查看complete），1=漂移/缺失
uv run --python 3.13 --no-project python -B Tools/render_spec_baseline.py verify docs/render-baseline/v1/manifest.json

# 当前全量门禁明确应返回2，不能放宽变绿
uv run --python 3.13 --no-project python -B Tools/render_spec_baseline.py verify docs/render-baseline/v1/manifest.json --require-complete

# 防漂移/禁止覆盖/迁移/未闭合测试；不用Unity或游戏
uv run --python 3.13 --no-project --with pytest python -B -m pytest Tools/tests/test_render_spec_baseline.py -q -p no:cacheprovider
```

默认根为本工程、`D:/EndfieldTechLib`、`C:/Users/Administrator/Downloads`，可用`--project-root/--techlib-root/--capture-root`迁移。`digest`只是清单内部校验，不是数字签名，不能抵抗同时改清单与digest；可信身份是发布的完整Git commit。

主索引9557项保持原样；用独立GIT_INDEX_FILE记录本批明确文件，不checkout/reset/clean或全量add。当前声明仅为资料审查及证据封存，不宣称Unity新实现或全量等价通过。

## 9. 本轮复核结果

- 封存工具：21项测试通过，语句+分支综合覆盖90.83%；Ruff与Pyright通过（后者0错误、0警告）。
- 既有资料审计：41项来源哈希/公式锚点/捕获状态检查通过，不能扩为全部shader等价。
- Tools回归：209通过、3个需要独立Unity诊断输入的测试跳过；2个Pillow弃用提醒，不改无关代码。历史图像工具只跑合成输入的工具测试，没有做本轮官方截图拟合。
- 新清单固定18个源码表达式锚点；所有来源字节和keyword身份可复核。完整规格门禁仍不通过，这是预期的真实状态。
- pip-audit仅本次隔离工具环境无已知漏洞，不扩为Unity工程依赖安全认证。
- 未运行Unity；不能声称本轮GPU集成/编译、MMD或天气实现通过。
