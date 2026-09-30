# 官方渲染证据 v2：实捕获程序与原始输入

## 1. 范围与继承

这是v1的**追加、更正基线**，不改变v1文件或其声明。父版本提交为`b26d86efece511b728e29e586d3510c88c001e9b`；父manifest digest见本版plan。若历史handoff仍指v1，先读[版本入口](../README.md)。本版仍不认证全部官方渲染、全天气或MMD已经完成。

本轮实际工作：从已有frame6411 SPIR-V离线重导6个主体draw的VS/PS，保留descriptor space；回源核查Hair双法线、cloth_02 emission、body/rest流；新增原始输入检查工具。**未启动游戏或Unity，未改shader/材质/scene/mesh/runtime，也未做截图像素拟合。**

## 2. 程序身份不能由布局评分替代

原始来源：`Validation/Captures/tifuluosi-front-20260917/replay-details-01/draw-details.json`。其中`draws_and_dispatches[].stages[stage].shader`指向`shaders[id]`，后者才保存SPV文件、stage、bytes与sha256。不是stage对象本身有sha256。本轮12份磁盘SPV均与该原始记录hash一致。

重导目录：`Validation/draw-program-audit-20260930-01/`。每文件为`event-{event}-{vertex|fragment}-{shaderID}.hlsl`；`export-provenance.json`保存工具hash、精确参数、原SPV与新HLSL各自hash及来源JSON hash。HLSL由原SPV自动生成，原始指令才是权威；生成器/后端可能改变表达形式，不能反过来改原SPV以凑一致。

使用RenderDoc1.46 bundled `spirv-cross.exe`，SHA256=`e5b4db9356bb0de3f6b66ccfa2370750e29d8a66b9d4527880c77d2e0325022d`，参数`{spv} --hlsl --shader-model 51 --output {hlsl}`，无额外转换/优化参数。旧SM50导出没有space，不能把其`register(b0)`直接当set0。新导出明确`register(b0,space1)`与`register(b0,space2)`。

| draw / 部位 | VS / PS身份 | dump解释候选与边界 |
|---|---|---|
| 776 iris | 22258 / 22259 | Eye b28核心参考；b52有DITHER差异，不因layout同签名就认证同程序 |
| 786 body | 22249 / 22250 | Skin b114核心候选；b208不能因signature相同就并为同程序；不是Cloth b401 |
| 835 cloth_01 | 22254 / 22255 | b471/b474非注释正文相同；b911/b914仍有DITHER差异 |
| 850 cloth_02 | 37668 / 37669 | 实捕获t3的emission计算支持b472/b475核心；旧b1011纹理语义不能沿用 |
| 860 face | 37670 / 37671 | Skin b138核心参考；b232不能因layout同签名就认证同程序 |
| 875 hair | 22256 / 22257 | 实捕获双法线支持b126/b129核心；**不是b125单法线算法**；b242/b245另核 |

这不是“唯一dump文件全体等价”表。b471/b474、b472/b475、b126/b129经去`//`注释后的**整个文件正文逐字符比较相同**；只说明该Fragment导出正文等价类，不能推断Vertex、keyword provenance、ALPHATEST控制或整个管线也相同。该比较不删除常量、分支、初始化、swizzle或Load。

旧`Tools/extract_front_frame_constants.py:286–289,395–403`的`signature`只包含UPM offset/name/type及set1 binding/name；`ambiguous=False`表示只有一个此类signature，**不是只有一个编译变体**。文件还只展示`best[:12]`，全搜索不能以展示切片为全集（当前六draw最多8个best，未在此帧截掉候选）。布局5/5是候选筛选，不是算法证明。

资源声明排序相同仅为同源线索；排序不同也不能判接口不兼容。若将匿名变量映射到dump名，必须保留完整`(kind,set,binding)`与cbuffer`packoffset/type/count/major`、结构字段类型与次序。dump增加零初始化、typed `Load<float4>`与捕获`asfloat(Load4)`的差异尚未做全控制流/位读取证明；禁止删掉差异后宣称全文完全等价。

## 3. Hair：两套法线及各自用途已直接确认

权威为`event-875-fragment-22257.hlsl`，不是依文件名或HN贴图命名猜测：

- t1/space1纹理`_58`在444行单次SampleBias（sampler `_27`=s4/space0，bias `_20_m16`）得到`_499`。
- 445–461：RG→`xy*2-1`；z=`max(1e-16,sqrt(1-clamp(dot(xy,xy),0,1)))`；xy乘UPM c0.w（b126名`_BumpScale`）；用原几何TBN转换，再按float-min下限归一，最后乘背面符号，成为diffuse法线`_557`。
- 463–468：BA执行自己的z重建，xy乘UPM c12.y（b126名`_SpecBumpScale`）；经同几何TBN后普通normalize，成为spec法线`_576`。**此步不乘diffuse背面符号，不能合并为一套N。**
- 471：spec法线参与strand构造；473：spec法线参与XZ edge-fade；1046：spec法线参与高光轴；1033：diffuse法线参与主体环境照明。正反面、两种归一化、原TBN及UV/bias都须保留。

命名候选`characternpr_hair/Sub0_Pass0_Fragment_b126.hlsl:296,362,448–477`提供字段及纹理名映射。旧b125:448–465是先`sample.w*=sample.x`再AG的一套_BumpMap，不能照其文档端口来认证上述实捕获双法线。

**已有实现检查（只登记，不修改）**：`EndfieldCharacterLit.shader:585`的RG split分支被`!sourceShading`挡住；614–670的official source分支会提前return，后面的821 BA支路不可达。`EndfieldOfficialHair.hlsl:123`仅接收一套N，后续strand、edge-fade、主次lobe复用这套N。所以“工程已有BA代码”不代表当前official source路径已接好捕获算法。应先补helper的diffuse/spec独立输入及实际绑定，再对照公式；不通过调亮弥补。

## 4. Cloth_02：Emission消费链已确认，别漏预乘因子

`event-850-fragment-37669.hlsl:424`从t3/space1 `_57` SampleBias（s4/space0、`_GlobalMipBias`对应匿名槽）得到`_528`。965行实际添加：

```text
((_528.rgb * UPM.c7.rgb) * UPM.c1.w) * _2265
_2265 = (1 - UPM.c1.z) + (baseAlpha * UPM.c1.z)
```

对应dump b472:271,289,339,428,941,969，名字分别`_EmissionBrightness`、`_EmissionColor`、`_EmissionMap`、`_AlphaPremultiply`。不是仅`map*color*brightness`；它还乘alpha预乘选择项。`baseAlpha`须追实际`_491`，不能把材质alpha或输出alpha随便代替。

旧b1011的t2=ShadowLUT/t3=MetallicGlossMap只是同布局候选，不能作为cloth_02的实际纹理语义。实际program已证明t3 RGB用于emission，但纹理如何生产、sRGB view及具体绑定仍另查。

**已有实现检查**：source分支`EndfieldCharacterLit.shader:655–658`已有emission，并非全缺；但缺上述`_2265`选择项。还须查UV ST、bias、加入点光/IBL/饱和度的位置；当前捕获材质若AlphaPremultiply=0，只能证明该项退化为1，不保证其它材质路径。没有据此更改实现或宣称视觉改善。

## 5. 六draw原始输入：现在有可机械复核的契约

权威输入：`Validation/vertex-input-export-20260929-183059/manifest.json`（schema=`renderdoc-vsin-raw-v1`, import_ready=false）。该字段不可强改为导入完成；它是按shader输入location保存的原始数据，不是Unity属性表。contract固化此manifest的SHA、六draw身份/计数和实际format，工具通过signature查location，忽略InstanceIndex builtin，不按匿名名字或buffer slot猜用途。

| draw / 顶点数 | location2/3 N-T储存 | location8 weights / location9 slots | 独立静止流 |
|---|---|---|---|
| 776 / 162 | packed R32_FLOAT + 常量R8 UNORM fallback | 常量R8 UNORM×4 / R8 UINT×4；flags49单影响 | 5 restPos，6 restN |
| 786 / 917 | packed R32_FLOAT + R8 UNORM fallback | u16 UNORM×4 / u8 UINT×4 | 5 restPos，6 restN，7 restT |
| 835 / 23758 | f32×3 N + f32×4 T | **f32×4 / u32×4**，不重编码 | 5 restPos，6 restN；无独立location7 |
| 850 / 10568 | packed R32_FLOAT + R8 UNORM fallback | u16 UNORM×4 / u8 UINT×4 | 5 restPos，6 restN |
| 860 / 2109 | packed R32_FLOAT + R8 UNORM fallback | u16 UNORM×4 / u8 UINT×4 | 5 restPos，6 restN |
| 875 / 15306 | packed R32_FLOAT + R8 UNORM fallback | u16 UNORM×4 / u8 UINT×4 | 5 restPos，6 restN，7 restT |

完整location4格式等见`native-input-contract.json`；未解释成UV/color。packed float必须按位读取，不能先按普通float数值判断finite或当XYZ三分量。位30压缩标记、位31tangent.w、signed10×2折叠八面体N与signed10切线角见本轮VS；这又不同于描边smooth-normal的TS半球xy流。

新`tools/raw_draw_inputs.py`对56个属性文件全体复算hash/字节数/地址、查signature/格式、校验6个index span；本轮6部位52,820顶点全通过。position与restPos六组字节相同，这是静止输入流别名，不取消它们不同的**输出语义**。

现有`verification.json`的位置/UV/index与原解包JSON相符，只覆盖这些分量；不扩为全部骨矩阵/normal/tangent/着色正确。原始cloth_01 N/T可非正交，禁止自行正交化再称原始还原。

### pose-full不能再当全原始oracle

`Tools/export_pose_full.py:94–98`把cloth_01四个f32权重改成`round(w*65535)`，把u32 slots用min255保存。新版机械检查证明95,032个权重分量中70,373个会改变，最大新增变化`7.628500484302414e-6`。原f32权重和范围`0.9999998584389687…1.0000001303851604`，不应再主动归一/量化。

本帧cloth_01 max slot=119，min255在此帧没有造成截断；测试另外保留slot300防止泛化工具吞掉真实u32。body/face/hair/cloth_02本来就是u16，不受此新增量化影响。iris高三个slot byte为0只是本帧事实，不能据此把R8×4输入普遍按单u32骨slot读。

旧pose-full可保留为历史姿态副本，但其“VERIFIED全链”和“instance仅平移”注释不再作为全输入真值。v1原文不改；本版明确撤回此泛称。

## 6. 输入生产与现有实现仍待闭合

- **rest/previous**：实际body VS输出TEXCOORD6 restN、7 restT、8 restPos、9 instance（新导出296–299,480–482）；face b138只有restN/restPos，不能混表。当前`EndfieldCharacterLit.shader:373–391`没有这些独立流与previous palette输出，故雨雪框架/MV/TAA不认证。
- **重建覆盖**：`TyphoeusModelBuilder.cs:191,204`重算tangent并CopySerialized覆盖mesh；V2 importer另行恢复N/T。需把“重建→恢复真实属性→动作/IK→part-root→渲染”作为完整生命周期，不以一次导入的通过代替重建后仍正确。
- **part root**：实际fragment bit16读base+0/1/2，bone palette从base+3开始，两者不同。捕获数据支持body Spine2、iris/face/hair Head列置换`[-Z,-X,+Y]`的四部位适配；当前`EndfieldSkinBasisDriver.cs:20–24`不处理两套cloth。只认证该捕获适配证据，cloth对应骨及动态输入仍待证明。
- **描边smooth-normal**：当前`SmoothNormals.cs`自生成UV7，不能凭N/T恢复即宣称原描边流已还原；必须另取outline draw的实际输入、跟踪解码与生产，不用forward流自证。

上述是逻辑/数据层未闭合，不要求逐像素截图对照。动作/MMD后必须仍正确保留原始流、权重、root/previous、资源绑定与pass调度。

## 7. 下一实现顺序与门禁

1. 先给原始输入生产建新的无损接口：保留cloth_01 f32权重/u32 slots，独立rest各流；不以pose-full统一u16作为源。验证所有输入及重建生命周期，不提前改scene。
2. 官方source Hair改成diffuse/spec两个法线及精确几何TBN/背面/归一下限，查实际texture/bias绑定；现有b125 helper只能保留为显式单法线变体，不覆盖捕获双法线。
3. cloth_02按实程序核emission全部乘数和顺序，推导cloth part-root；不同部位不套同一family默认。
4. 独立追outline smooth流、current/previous palette；然后扩湿天气、方向/局部灯/IV/雾生产和管线。
5. 每一实现修改先有独立来源算例/位布局/状态或绑定门禁，再跑Unity；若未跑不能说编译/GPU通过。冻结Bloom/post仍不静默改。

本轮工具16项通过，语句+分支覆盖87.83%，Ruff/Pyright通过；合并Tools回归225通过、3个缺独立Unity诊断输入的测试跳过，既有Pillow弃用提醒2项。pip-audit仅本轮隔离工具环境无已知漏洞，不认证Unity依赖。工具仅证明写明范围，不恢复完整CPU/C++生产端；完整规格门禁仍失败是预期状态。

## 8. 复核与封存

v2只追加、以plan中的父digest连接v1。`manifest.json`不包含自身；v2目录与版本入口有局部`-text`规则，防止检出改变字节，不改v1的字节策略。Git不上传本轮官方HLSL/SPV/原始顶点文件，仅上传版本文本、工具、contract、结果与身份元数据。

```powershell
# 原始输入：只读；--output如指定必须是新文件，不能覆盖既有证据
uv run --python 3.13 --no-project python -B docs/render-baseline/v2/tools/raw_draw_inputs.py Validation/vertex-input-export-20260929-183059/manifest.json docs/render-baseline/v2/native-input-contract.json

# 同时验证父基线与追加基线；哈希通过不等于全部规格通过
uv run --python 3.13 --no-project python -B Tools/render_spec_baseline.py verify docs/render-baseline/v1/manifest.json
uv run --python 3.13 --no-project python -B Tools/render_spec_baseline.py verify docs/render-baseline/v2/manifest.json

uv run --python 3.13 --no-project --with pytest python -B -m pytest docs/render-baseline/v2/tools/tests -q -p no:cacheprovider
```

保留主索引9557项及原HEAD，独立index提交明确成果。不能把本轮找出的真实缺口倒写为“修复渲染已经通过”。
