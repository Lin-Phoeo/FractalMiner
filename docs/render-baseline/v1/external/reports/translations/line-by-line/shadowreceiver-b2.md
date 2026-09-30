# 逐行译读:HGRP/CharacterNPR_ShadowReceiver(变体 b2)

源文件(相对 `...\materials\characternpr\`):`characternpr_shadowreceiver\Sub0_Pass0_Vertex_b2.hlsl`(231 行)、`Sub0_Pass0_Fragment_b2.hlsl`(606 行，均含 main)。b3(+SRP_INSTANCING_ON)差异仅实例化。分析层见 `..\official-shadowreceiver.md`。

---

## A. 顶点 Sub0_Pass0_Vertex_b2.hlsl

### A.0 声明区

- L1-3:头注释。Blob 2,ParamBlob 0,关键字 none(catch-all)。
- L5-31:TransformVariables b12(与描边顶点同,NonJitteredViewNoTransProjMatrix 在 c32)。
- L33-174:ShaderVariablesGlobal b16(体使用:_ScreenSize 未用、_TaaJitterStrength、_CloudShadowParams 未用)。
- L176-188:**`UnityPerDraw` b0,space2(非实例化版,具名!)** —— `_unity_ObjectToWorld`(c0)、Stripped_64(c4)、`_unity_WorldTransformParams`(c5)、Stripped_96(c6)、Stripped_160..240(c10-c15)。
- L189-206:静态/IO —— 输入 POSITION0=_3(float4)、NORMAL0=_4;输出 TEXCOORD0=_5(WS 位置)、TEXCOORD1=_6(WS 法线)、SV_Position。

### A.1 vert_main(L208-219)逐行

- `L210` `_71 = mul(O2W 3×3, (1/dot(行0,行0), 1/dot(行1,行1), 1/dot(行2,行2)) × _4)` —— **法线变换**(每轴除以行向量长度平方,处理非均匀缩放)。
- `L211` `_81 = mul(_unity_ObjectToWorld, (_3.xyz, 1)).xyz` —— 物体空间位置 → 世界(POSITION0 为 float4,w 忽略)。
- `L212` `_92 = mul(NonJitteredViewNoTransProjMatrix, (_81 - camPos, 1))` —— 裁剪。
- `L213` `_100 = _92.xy - _TaaJitterStrength.zw×(2,-2)×_92.w` —— 去 TAA 抖动。
- `L214` `_101 = (_100, _92.z, _92.w)`。
- `L215` `_5 = _81`(输出 WS 位置)。
- `L216` `_6 = _71 × rsqrt(max(1e-38, dot(_71,_71)))`(输出归一化 WS 法线)。
- `L217-218` `_101.y = -_100.y; gl_Position = _101`(y 翻转)。
- L221-231:main() 装载与输出。

---

## B. 片元 Sub0_Pass0_Fragment_b2.hlsl

### B.0 声明区

- L1-3:头注释(catch-all)。
- L5:`static float _167 = 0.0f` —— 被拼进采样坐标 float3 又取 `.xy` 的填充值,**非比较偏置**。
- L7-31:TransformVariables b12。
- L33-174:ShaderVariablesGlobal b16(体使用:_ScreenSize、_CloudShadowParams0-3、_VFXParams0)。
- L176-188:`UnityPerDraw` b0,space2(非实例化,同顶点)。
- L190-199:LightDataBuffer b14(只用 `_DirectionalLightDirection`)。
- L201-231:ShadowData b15 —— `_CSMWorldToShadow[5]`、`_CSMShadowSplitSpheres[4]`、`_CSMShadowAtlasParams[4]`、`_CSMShadowTexelSize`、`_DirectionalShadowParams`(c34)、`_DirectionalShadowParams2`(c35)、`_CSMRhodesParams`(c36)、**`_CharacterWorldToShadow[15]`(c448)、`_CharacterShadowBiases[15]`(c508)、`_CharacterShadowLightDir[15]`(c523)、`_CharacterShadowAtlasParams[15]`(c538)、`_CharacterShadowTexelSize`(c553)、`_CharacterShadowParams`(c554)**、`_ASMWorldToShadowBaseMat`(c576)、`_ASMIndirectWorldToShadow`(c580)、`_ASMParams/_ASMParams2/_ASMShadowTexelSize`(c584-586)、`_ASMIndirectParams[128]`(c587)。
- L233-243:VisibilitySHConstData b48(`_ABParams` c2、`_FHatParams` c3)。
- L245-257:**UnityPerMaterial b0,space1(具名)** —— c0 = `_CircleFade/_CircleFadeDistance/_CircleFadeSmoothness/_DisableCharacterSelfShadow`;c1 = `_DisableSceneShadow` + 3 个 Stripped;c2 = `_ShadowColor`;c3 = `_CapsuleAoColor`。
- L259-267:采样器(s6 LinearRepeat、s4 LinearClamp、s7 LinearMirror 比较)+ 纹理:t9 `_CSMShadowmapTex`、t39 `_CharacterShadowmapTex`、t8 `_CloudShadowTex`、t11 `_ASMShadowmapTex`、t46 `_ABLutTex`、t21 `_VisibilitySHRT`。
- L269-284:IO(输入 _3=WS 位置、_4=WS 法线、SV_Position;输出仅 SV_Target0)。
- L286-295:half 打包辅助。

### B.1 frag_main(L297-594)逐行

#### B.1.1 角色自阴影 atlas(L299-364)

- `L299` `_180 = asuint(_unity_WorldTransformParams.z)` —— 逐对象位掩码(选择生效的 atlas tile)。
- `L300-302` `_182 = 1.0f`(累进值);`_183 = 0`。
- `L303` `for (_185 = 0; _185 < min(_CharacterShadowParams.z, 15); …)` —— 最多 15 张 tile。
- `L306` `if ((_180 & asuint(_CharacterShadowBiases[_185].w)) != 0)` —— 本 tile 是否作用于此物体(bit 掩码)。
- `L308` `_206 = 1 - clamp(dot(_4, _CharacterShadowLightDir[_185].xyz), 0, 0.9)` —— 接收偏移强度(1-N·L,封顶 0.9)。
- `L309` `_223 = mul(_CharacterWorldToShadow[_185], (pos - LightDir×(_206×Biases.x) + N×(_206×Biases.y), 1))` —— **receiver bias 全在几何侧**(沿光推 + 沿法线抬)。
- `L310-312` `_225 = max(_223.z, 0.01)`(比较深度)。
- `L313-319` UV 出界/NaN → 保持 `_182` 继续。
- `L320` `_251 = (AtlasParams.xy + uv×AtlasParams.zw) × TexelSize.zw` —— atlas 区块 → 纹素坐标。
- `L321-355` **3×3 tent 权重展开**(与描边片元点光 PCF 同一套:0.16/0.08 常数,L321-342 计算行列偏移)。
- `L356` `_406 = 前 7 tap 加权和`(逐项 `_CharacterShadowmapTex.SampleCmpLevelZero(sampler_LinearMirror, uv, _225)`)。
- `L357` `_424 = min(_182, _406 + 第 8/9 tap)` —— **结果与之前 tile 取 min(取最暗)**。
- `L358-364` else(掩码不匹配):`_424 = _182`;`_183 = _424` 进位。

#### B.1.2 场景阴影:CSM + ASM + 云影(L365-545)

- `L365-372` `do {` 块;`if (_DirectionalShadowParams2.w >= 0.99)` → `_908 = (DirShadowParams2.z, 1)` 直达(DEBUG/覆盖通道)。
- `L373-376` CSM 距离淡出:`_437 = int(DirShadowParams2.x)`;`_447 = pos - (cascIdx==2 ? SplitSpheres[0].xyz : camPos)`;`_458 = max(clamp((DirShadowParams.w - dot(_447,_447))×DirShadowParams.z, 0, 1), _CSMRhodesParams.x)`。
- `L377-393` `if (_458 > 0)`:`_465.._493` 四球距离比较求层;`_497 = clamp(层间过渡)`;`_504 = max(clamp(4 - 加权和, 0, 3), DirShadowParams.y)` —— cascade 选择(带混合)。
- `L394-402` `_512 = mul(_CSMWorldToShadow[_504], pos)`;`_515 = z;_516/_517`;出界判定 `_525`;`_543 = atlas UV × TexelSize.zw`。
- `L403-431` **4-tap bilinear PCF**(`_547.._610` 权重,0.44444 系数;`_645 = _525 ? 1 : 4 tap 和`)。
- `L432-441` `_646 = _525`;else(近距离不分层)`_645 = 1`。
- `L448-453` `if ((_458 < 1) || (_CSMRhodesParams.x > 0.5))` —— 算 ASM(间接/环境阴影):`_659 = 1 - clamp(dot(_4, DirLightDir), 0, 0.9)`;`_676 = 接收点(同 atlas 的双向 bias,_ASMParams.x/y)`;`_677 = mul(_ASMIndirectWorldToShadow, _676)`。
- `L457-459` `_678` 在 (0,1)² 内 → `_697 = clamp(uint((floor(_677.y×_ASMParams2.z) + _677.x) × _ASMParams2.y), 0, 127)` —— **间接 tile 表索引**。
- `L460-464` `_701 = _ASMIndirectParams[_697].x`(half2 打包:tile 内偏移 + 有效标志 `_703`)。
- `L466-476` `_703 >= 0`:`_712 = _ASMWorldToShadowBaseMat`(w 列换成 `_ASMIndirectParams` 的 y/z/w);`_719 = mul(_712, _676)`;`_743 = (uv×_ASMParams.zw + tileOffset) × _ASMShadowTexelSize.zw`。
- `L477-504` **4-tap bilinear PCF**(`_745.._804`,同 CSM 套路)→ `_844`。
- `L505-523` 各级出界 → 1;`_848 = _648 ? _846 : _647`、`_849 = _846`。
- `L525-530` else:`_848 = _647; _849 = 1`;`_852 = lerp(lerp(_849, _848, _458), min(_849,_848), _CSMRhodesParams.x)` —— **CSM/ASM 混合**。
- `L531-542` 云影:`_852 > 0.001` 时 `_859/_869 = 世界xz 投影(_CloudShadowParams0/1/3)`;`_878 = _CloudShadowParams2.xy × _VFXParams0.w`(偏移);`_903 = _852 × lerp(1, lerp(近层, 远层, smoothstep(P1.x,P1.y,|xz|)), P2.z)`(两层 `_CloudShadowTex` 按距离混合)。
- `L543` `_908 = (lerp(_903, DirShadowParams2.z, DirShadowParams2.w), _903)` —— 场景阴影输出。

#### B.1.3 合成与输出(L546-594)

- `L546` `_926 = clamp(0.95 - min( lerp(lerp(1,_182,DirShadowParams.x), 1, _DisableCharacterSelfShadow), lerp(lerp(1,_908.x,DirShadowParams.x), 1, _DisableSceneShadow) ), 0, 1) × _ShadowColor.w` —— 两个开关分别淡出自阴影/场景阴影；0.95限制混合amount，不保证最终RGB至少5%；最后还消费ShadowColor.rgb及CapsuleAO。
- `L547-555` `if (_CircleFade > 0.5)`:`_946 = _926 × smoothstep(_CircleFadeDistance+_CircleFadeSmoothness, _CircleFadeDistance, distance(_3, O2W 平移))` —— **圆形淡出(圆心=物体原点)**;else `_946 = _926`。
- `L556` `_959 = _VisibilitySHRT.SampleLevel(LinearRepeat, fragCoord.xy×_ScreenSize.zw, 0)` —— 屏幕空间可见性 SH。
- `L557-560` `if (任一分量 |·| > 1e-4)`。
- `L561-586` SH 解码：`_966=length(_959.yzw)`；>4.599999904632568359375反复折半并计数_968，_977=_959*_971，_982=(0,_977.yzw)。F576的`_ABLutTex`UV为`float2(((((length(_982)*_FHatParams.x)+_FHatParams.y)*255)+0.5)*0.00390625,0.5)`，Level0/LinearRepeat，采样xy再乘_ABParams.xy加_ABParams.zw。`_1018=float4(_1004.x*3.5449078083038330078125,_982.yzw*_1004.y)*exp(_977.x*0.282094776630401611328125)`。F581按_968次迭代`mul(float4x4(_1018,float4(_1018.yx,0,0),float4(_1018.z,0,_1018.x,0),float4(_1018.w,0,0,_1018.x))*0.282094776630401611328125,_1018)`；F585构造同样4×4再乘`float4(1.1283791065216064453125,-0,0,-0)`；不是2×2旋转。F586保留各分量系数/符号及yzwx重排，不以近似旋转替代。
- `L588-590` else:`_1055 = (0,0,0,1)`。
- `L592` `_1067 = lerp(lerp(1, _ShadowColor.rgb, _946), _CapsuleAoColor.rgb, 1 - clamp(luma(max(0, dot(_1055, (0,1,0,1)))), 0, 1))` —— **最终色**:阴影色路径 与 CapsuleAo 路径按"上方可见度"混合。
- `L593` `_6 = (_1067, 1)` —— 输出(配合 `Blend Zero SrcColor` = dst×src 乘法压暗)。
- L596-606:main() 装载(SV_Position 同样 `1/w` 反演,L599)、输出。

---

*说明:机械逐行层;语义结论(帧内作用、属性映射、实现含义)以 `..\official-shadowreceiver.md` 为准。*
