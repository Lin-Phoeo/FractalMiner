# 官方后处理 Bloom 源码抽取(HGRP/PostProcessing/Bloom)

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/postprocessing/bloom/bloom.shader`(187 行,全读)+ `bloom\bloom\Sub0_Pass*_Vertex/Fragment_b*.hlsl`(注意:变体在**嵌套** `bloom\bloom\` 目录)。
代表变体:Pass0 b2(catch-all)、Pass1 b11(LOW)/b12(HIGH)、Pass2 b13/b14、Pass3 b17(LOW)/b18(HIGH)。

**本文不含任何单元测试或参考实现**(独立 oracle 由验收方另写),仅忠实转写源码。

> **范围校正（2026-09-30）**：本篇是dump中**raster Bloom四pass家族**的导读，不是帧6411实际Bloom生成链。现有捕获在events1121…1153产生9层、1157…1185产生8层，均为compute dispatch；三个捕获HLSL位于`Validation/Captures/tifuluosi-front-20260917/bloom-source-01/shader-{20453,20455,20463}.hlsl`。其中20453是13tap加权prefilter（不是本文5tap）。应独立封存compute source/17dispatch资源依赖与`bloom-samplers-02`证据，不能用四passraster结构替代。最终BloomResource58923为1280×800、R11G11B10_FLOAT；生产端阶段的有限精度也属于契约。

## 1. Pass 列表与链路

| PassIdx | Name | 状态 | 关键字 | 代表变体 |
|---|---|---|---|---|
| 0 | Bloom Prefilter | ZTest Always、ZWrite Off、Cull Off(bloom.shader:8-14) | LOW_QUALITY、CHARACTER_MASK、ENABLE_ALPHA、HIGH_QUALITY(:21-24) | b2(全关) |
| 1 | Bloom Blur Horizontal | 同上(:72-78) | LOW_QUALITY、HIGH_QUALITY(:85-86) | b11(LOW)/b12(HIGH) |
| 2 | Bloom Blur Vertical | 同上(:110-116) | 同 Pass1 | b13/b14 |
| 3 | Bloom Upsample | 同上(:148-154) | 同 Pass1 | b17(LOW)/b18(HIGH) |

从pass职责推导的候选raster链：Prefilter→多级Blur H/V→Upsample；wrapper本身只列pass，不证明运行时重复次数、层级尺寸/格式或dispatch顺序。其结果可由UberPost消费，但帧6411实际生产端是上框中的compute链。

**无Properties块**；确认cbuffer参数布局，不据此推断由C#而不是自研C++生产。参数包括`_TexelSize`、`_Params`、两组threshold和`_BloomCharacterParams`。

## 2. Pass0 Bloom Prefilter(b2,catch-all:LOW/CHARACTER_MASK/ENABLE_ALPHA/HIGH 全关)

- **5-tap 十字采样**(偏移 `±(0.89999997615814208984375f, -0.4000000059604644775390625f)`、`±(0.4000000059604644775390625f, 0.89999997615814208984375f)` × `_ScreenSize.zw`,即 texel 单位)(f_b2:181/186/191/196)。
- **soft-knee 阈值提取**(每 tap 同式,f_b2:177-179):
```
bright = max3(c)
knee   = clamp(bright - _BloomThreshold.y, 0.0f, _BloomThreshold.z)
weight = max((_BloomThreshold.w × knee) × knee, bright - _BloomThreshold.x) / max(bright, 9.9999997473787516355514526367188e-05f)
tap    = c × weight × _ExposureWithMiscParams.x
```
- **亮度加权归一化**(f_b2:180/201):每tap权重`1/(luma(tap)+1)`，输出加权均值、a=1。亮tap权重低，不能称“亮度守恒”：例如灰度tap=0与2，均值为0.5而算术均值为1。精确luma使用源码Rec709常量。

## 3. Pass1/Pass2 分离高斯(b11/b13;HIGH b12/b14)

**Pass1 Horizontal(b11,LOW)为 9-tap**,采样中心对称,间距 `_TexelSize.z × {2, 4, 6, 8}`(f_b11:176-180):
```
权重:0.01621622033417224884033203125f、0.0540540516376495361328125f、0.12162162363529205322265625f、0.1945945918560028076171875f、中心 0.2270270287990570068359375f(左右对称)
out = Σ SampleBias(LinearClamp, uv ± offset) × 权重;a = 1
```

**Pass2 Vertical(b13,LOW)为 5-tap**(f_b13:175-177)——与 Pass1 **不同**(非镜像):
```
间距:_TexelSize.w × {3.23076915740966796875f, 1.384615421295166015625f}(纵向)
权重:0.0702702701091766357421875f、0.3162162303924560546875f、中心 0.2270270287990570068359375f(左右对称)
out = Σ SampleBias(LinearClamp, uv ± offset) × 权重;a = 1
```
b11/b12及b13/b14回源公式相同（本轮核对函数体），HIGH标签不改变这里的偏移或权重；不得凭keyword名称虚构不同档位。HIGH上采样才有不同采样公式。

## 4. Pass3 Upsample

- **LOW(b17:177)**:`out = lerp(_InputHighTexture.SampleBias(uv), _InputTexture.SampleLevel(uv), _Params.x)`,a=1 —— 低分辨率 bloom 层与上一层线性混合。
- **HIGH(b18:175-178)**:cubic B-spline的双线性采样重组（4次读取），不是简单4tap tent；精确组合权重/采样位置以该源码为准，不可用“URP同款”替代：
```
pos = uv × cb0_Stripped_32.xy + 0.5f; cell = floor(pos); f = frac(pos)
w0 = 0.16666667163372039794921875f + (f × (-0.5f + (f × (0.5f - f×0.16666667163372039794921875f))))   // 1/6 cubic
w1 = f × 0.5f; w2 = f × (-1 + f×0.5f) × f → +0.666666686534881591796875f
w3 = 0.16666667163372039794921875f + (f × (0.5f + (f × (0.5f - f×0.5f))))
… 组合为 4 个采样点(权重归一常数 0.333333313465118408203125f 等)
out = lerp(_InputHighTexture, 4-tap 加权和(采样点 min(uv, 1-texel)), _Params.x)
```

## 5. keyword 差异(补记)
- `CHARACTER_MASK`代表b3:180–187：每tap读取MotionVector.w，`charMask=abs(w-.3000000119)<.1000000015`，插值角色/场景threshold；角色命中最终选择`max(rgb-characterThreshold.x,0)*BloomCharacterParams.x`，再乘Exposure.x，随后同式luma加权。不能只替换threshold而漏掉角色分支。
- `ENABLE_ALPHA`代表b4:177–180：**输入rgb先乘输入alpha再提取阈值**，不是输出alpha；最终`SV_Target0.a=1`（:206）。组合分支仍须逐式复核。
- `HIGH_QUALITY`b6的prefilter函数与b2同形同值；没有采样数差异。这里仍是5tap；捕获compute20453的13tap是另一管线。

## 6. ⚠待核汇总
1. CHARACTER_MASK与ENABLE_ALPHA组合的完整公式、输入MotionVector分类生产者、其格式/过滤仍待核；本轮只检查代表b3/b4。
2. b18的完整cubic重组式不能由本文省略伪码直接实施；raster全部变体还不是全覆盖认证。
3. 参数生产语义、raster启用条件/层级尺寸和格式待核；当前帧compute资源有独立证据，不允许混写。
4. frame6411compute20453:182使用threshold后乘全局`_5_m20.x`曝光；UberPost先对主色曝光再合成已经曝光的Bloom，两处曝光分别作用各自输入，不能合并成对整个颜色再次曝光。

---
*仅静态转写,行号指 bloom.shader 与 bloom\bloom\Sub0_Pass*.hlsl;无测试/参考实现。*
