# 官方后处理 Bloom 源码抽取(HGRP/PostProcessing/Bloom)

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/postprocessing/bloom/bloom.shader`(187 行,全读)+ `bloom\bloom\Sub0_Pass*_Vertex/Fragment_b*.hlsl`(注意:变体在**嵌套** `bloom\bloom\` 目录)。
代表变体:Pass0 b2(catch-all)、Pass1 b11(LOW)/b12(HIGH)、Pass2 b13/b14、Pass3 b17(LOW)/b18(HIGH)。

**本文不含任何单元测试或参考实现**(独立 oracle 由验收方另写),仅忠实转写源码。

## 1. Pass 列表与链路

| PassIdx | Name | 状态 | 关键字 | 代表变体 |
|---|---|---|---|---|
| 0 | Bloom Prefilter | ZTest Always、ZWrite Off、Cull Off(bloom.shader:8-14) | LOW_QUALITY、CHARACTER_MASK、ENABLE_ALPHA、HIGH_QUALITY(:21-24) | b2(全关) |
| 1 | Bloom Blur Horizontal | 同上(:72-78) | LOW_QUALITY、HIGH_QUALITY(:85-86) | b11(LOW)/b12(HIGH) |
| 2 | Bloom Blur Vertical | 同上(:110-116) | 同 Pass1 | b13/b14 |
| 3 | Bloom Upsample | 同上(:148-154) | 同 Pass1 | b17(LOW)/b18(HIGH) |

链路:Prefilter(阈值提取,下采样)→ 多级(Blur H → Blur V)金字塔 → Upsample 逐级上采样合成(最终被 `uberpost` 的 `_BloomTexture` 消费,见 official-postprocess-uberpost.md §4.1)。

**无 _Property 块**(bloom.shader 无 Properties);参数由 C# 注入:`_TexelSize`、`_Params`(Upsample 混合 x)、`_BloomThreshold`、`_BloomCharacterThreshold`、`_BloomCharacterParams`(cb0 b2,space3,bloom\Sub0_Pass0_Fragment_b2.hlsl:148-156)。

## 2. Pass0 Bloom Prefilter(b2,catch-all:LOW/CHARACTER_MASK/ENABLE_ALPHA/HIGH 全关)

- **5-tap 十字采样**(偏移 `±(0.89999997615814208984375f, -0.4000000059604644775390625f)`、`±(0.4000000059604644775390625f, 0.89999997615814208984375f)` × `_ScreenSize.zw`,即 texel 单位)(f_b2:181/186/191/196)。
- **soft-knee 阈值提取**(每 tap 同式,f_b2:177-179):
```
bright = max3(c)
knee   = clamp(bright - _BloomThreshold.y, 0.0f, _BloomThreshold.z)
weight = max((_BloomThreshold.w × knee) × knee, bright - _BloomThreshold.x) / max(bright, 9.9999997473787516355514526367188e-05f)
tap    = c × weight × _ExposureWithMiscParams.x
```
- **亮度加权归一化**(f_b2:180/201):每 tap 权重 `1 / (luma(tap) + 1.0f)`,输出 = `Σ(tap×w_luma) / Σ(w_luma)`,a=1。这一步是"亮度守恒的加权平均"(亮 tap 权重低),非标准 URP 直接平均。

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
b12/b14(HIGH)行数与 LOW 相同(182/180)——差异为采样偏移/权重档位 ⚠待核(未逐行)。

## 4. Pass3 Upsample

- **LOW(b17:177)**:`out = lerp(_InputHighTexture.SampleBias(uv), _InputTexture.SampleLevel(uv), _Params.x)`,a=1 —— 低分辨率 bloom 层与上一层线性混合。
- **HIGH(b18:175-178)**:B-spline **4-tap tent 上采样**(URP 同款):
```
pos = uv × cb0_Stripped_32.xy + 0.5f; cell = floor(pos); f = frac(pos)
w0 = 0.16666667163372039794921875f + (f × (-0.5f + (f × (0.5f - f×0.16666667163372039794921875f))))   // 1/6 cubic
w1 = f × 0.5f; w2 = f × (-1 + f×0.5f) × f → +0.666666686534881591796875f
w3 = 0.16666667163372039794921875f + (f × (0.5f + (f × (0.5f - f×0.5f))))
… 组合为 4 个采样点(权重归一常数 0.333333313465118408203125f 等)
out = lerp(_InputHighTexture, 4-tap 加权和(采样点 min(uv, 1-texel)), _Params.x)
```

## 5. keyword 差异(补记)
- `CHARACTER_MASK`(b3/b5/b7/b9):角色掩码版(使用 `_BloomCharacterThreshold/_BloomCharacterParams`,未逐行 ⚠待核)——用于"角色发光与场景发光分离"。
- `ENABLE_ALPHA`(b4/b5/b8/b9):输出 alpha 通道(未逐行 ⚠待核)。
- `HIGH_QUALITY`(b6 等):Prefilter 同为 203 行,采样数差异 ⚠待核;Blur/Upsample 见 §3/§4。

## 6. ⚠待核汇总
1. CHARACTER_MASK/ENABLE_ALPHA 分支逐行公式。
2. HIGH_QUALITY Prefilter/Blur 与 LOW 的具体差异(行数相同,疑权重/偏移档位)。
3. `_Params.yzw` 与 `_BloomCharacterParams` 的 C# 侧赋值语义(源码不可见)。

---
*仅静态转写,行号指 bloom.shader 与 bloom\bloom\Sub0_Pass*.hlsl;无测试/参考实现。*
