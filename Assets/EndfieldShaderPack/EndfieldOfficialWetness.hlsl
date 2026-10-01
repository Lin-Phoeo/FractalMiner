#ifndef ENDFIELD_OFFICIAL_WETNESS_INCLUDED
#define ENDFIELD_OFFICIAL_WETNESS_INCLUDED
// Source: CharacterNPR b471 (actual frame6411 cloth01 candidate PS22255).
// Only rain/immersion branch; not b400 stockings, clearcoat or snow.
// The raw arithmetic block is retained for mechanical source-equivalence tests.
// Actual t44/t41 use set0 s4 Repeat, despite canonical sampler_LinearClamp name.
// Rest coordinates must be carried unskinned in UV2/3, NOT deformed POSITION.
struct EFWetSurface
{
    float3 specNormal;
    float roughness;
    float3 shadowAlbedo;
    float3 albedo;
    float coverage;
};
float EFWetTime()
{
    return _EndfieldWeatherTime.x > 0.5 ? _EndfieldWeatherTime.y : _Time.x;
}
float4 EFWetDecode(float globalSelector, float packedGlobal, float packedObject)
{
    uint bits = asuint(globalSelector > 0.5 ? packedGlobal : packedObject);
    return float4(bits & 255u, (bits >> 8u) & 255u,
        (bits >> 16u) & 255u, (bits >> 24u) & 255u) * 0.0039215688593685626983642578125f;
}
float4 EFWetInputs(float worldY)
{
    float4 bytes = EFWetDecode(_CharacterParams10.x, _CharacterParams10.y, _EndfieldObjectWeather.x);
    float localWet = smoothstep(-0.20000000298023223876953125f, 0.1500000059604644775390625f,
        lerp(_EndfieldObjectWeather.y, _CharacterParams10.w, _CharacterParams10.x) - worldY) * bytes.y;
    return float4(bytes.x, localWet, max(bytes.z, localWet), bytes.w);
}
EFWetSurface EFWetEvaluate471(float3 albedo, float3 shadowAlbedo, float3 mappedNormal,
    float metallic, float roughness, float3 restPosition, float3 restNormal, bool skinned, float worldY)
{
    float4 weather = EFWetInputs(worldY);
    float _589 = weather.x;
    float _601 = weather.y;
    float _602 = weather.z;
    float _481 = metallic;
    float _485 = roughness;
    float3 _476 = albedo;
    float3 _498 = shadowAlbedo;
    float3 _553 = mappedNormal;
    bool _451 = skinned;
    float3 _10 = restPosition;
    float3 _9 = restNormal;
    float _407 = 0.0; // source static zero (second component of unused package)
// SOURCE_BLOCK_BEGIN
    float3 _1828 = 0.0f.xxx;
    float _1829 = 0.0f;
    float _1830 = 0.0f;
    float _1831 = 0.0f;
    float _1832 = 0.0f;
    float3 _1833 = 0.0f.xxx;
    float3 _1834 = 0.0f.xxx;
    [branch]
    if ((clamp(_589 + _602, 0.0f, 1.0f) - _DisableRainEffectOnMaterial) > 0.00999999977648258209228515625f)
    {
        float _1136 = 1.0f - _481;
        float _1139 = smoothstep(0.3499999940395355224609375f, 0.100000001490116119384765625f, dot(_476 * _1136, float3(0.21267290413379669189453125f, 0.715152204036712646484375f, 0.072175003588199615478515625f)));
        bool3 _1142 = _451.xxx;
        float3 _1144 = _10.xzy * float3(1.0f, 1.0f, -1.0f);
        float3 _1148 = float3(_1142.x ? _1144.x : _10.x, _1142.y ? _1144.y : _10.y, _1142.z ? _1144.z : _10.z) * _CharacterParams10.z;
        float3 _1150 = float3(_1142.x ? _9.xzy.x : _9.x, _1142.y ? _9.xzy.y : _9.y, _1142.z ? _9.xzy.z : _9.z);
        float3 _1152 = abs(_1150) - 0.20000000298023223876953125f.xxx;
        float3 _1155 = max((_1152 * _1152) * _1152, 6.103515625e-05f.xxx);
        float3 _1158 = _1155 / dot(_1155, 1.0f.xxx).xxx;
        float2 _1166 = _1148.xy;
        float2 _1171 = _1148.zy;
        float4 _1181 = ((_CharacterRainEffectTex.SampleBias(sampler_BumpMap, _1148.xz, _EndfieldCapturedGlobalMipBias) * _1158.y) + (_CharacterRainEffectTex.SampleBias(sampler_BumpMap, _1166, _EndfieldCapturedGlobalMipBias) * _1158.z)) + (_CharacterRainEffectTex.SampleBias(sampler_BumpMap, _1171, _EndfieldCapturedGlobalMipBias) * _1158.x);
        float _1182 = _1181.w;
        float _1184 = 1.10000002384185791015625f - _1182;
        float _1193 = max(smoothstep(0.800000011920928955078125f - _1182, _1184, clamp((_589 * _1136) + (_553.y * 0.20000000298023223876953125f), 0.0f, 1.0f)), smoothstep(0.449999988079071044921875f - _1182, _1184, clamp(_601 * _1136, 0.0f, 1.0f)));
        float _1200 = smoothstep(0.5f, 0.75f, _481);
        float _1202 = smoothstep(0.800000011920928955078125f, 0.60000002384185791015625f, _485) * _1139;
        float _1205 = clamp(_1202 + _1200, 0.0f, 1.0f) * max(_589, _602);
        bool _1209 = !((step(_589, 0.00999999977648258209228515625f) * step(0.00999999977648258209228515625f, _602)) != 0.0f);
        bool2 _1210 = _1209.xx;
        float2 _1212 = (1.0f - _602).xx;
        float2 _1213 = float2(_1210.x ? float2(3.0f, 4.345600128173828125f).x : _1212.x, _1210.y ? float2(3.0f, 4.345600128173828125f).y : _1212.y);
        float _1214 = 1.0f - _1205;
        float _1217 = _1209 ? EFWetTime() : 1.0f;
        float _1219 = _1217 * _1213.x;
        float _1221 = _1217 * _1213.y;
        float3 _1222 = _1148 * 20.0f;
        float3 _1223 = _1148 * 34.345600128173828125f;
        float3 _1225 = pow(max(_1152, 0.0f.xxx), 10.0f.xxx);
        float3 _1229 = _1225 / max(dot(_1225, 1.0f.xxx), 6.103515625e-05f).xxx;
        float _1231 = _1229.y;
        float2 _1232 = _1222.xz * 1.0f;
        float2 _1233 = floor(_1232);
        float2 _1236 = frac(_1233 * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1240 = _1236 + dot(_1236, _1236 + 34.345001220703125f.xx).xx;
        float _1241 = _1240.x;
        float _1242 = _1240.y;
        float2 _1246 = frac(float2(_1241 * _1242, _1241 + _1242));
        float2 _1249 = frac((_1233 + 114.51399993896484375f.xx) * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1253 = _1249 + dot(_1249, _1249 + 34.345001220703125f.xx).xx;
        float _1254 = _1253.x;
        float _1255 = _1253.y;
        float2 _1259 = frac(float2(_1254 * _1255, _1254 + _1255));
        float _1265 = _1246.x;
        float _1267 = 0.25f * lerp(0.60000002384185791015625f, 1.0f, _1265);
        float2 _1268 = ((_1232 - _1233) + ((((_1259 * 2.0f) - 1.0f.xx) * 0.25f) * 1.0f)) - 0.5f.xx;
        float _1271 = _1268.y;
        float2 _1275 = float2(_1268.x * 1.25f, _1271 * ((_1271 < 0.0f) ? 1.25f : 0.75f));
        float _1278 = _1219 + _1265;
        float _1282 = _1209 ? frac(_1278) : lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(_1278, 0.0f, 1.0f));
        float _1294 = _1246.y;
        float _1297 = ((smoothstep(0.20000000298023223876953125f, 0.2199999988079071044921875f, _1282) * smoothstep(0.85000002384185791015625f, 0.550000011920928955078125f, _1282)) * step(0.001000000047497451305389404296875f, smoothstep(_1267, 0.0f, length(_1275)))) * step(_1214, _1294 - 0.100000001490116119384765625f);
        float _1300 = _1297 * _1231;
        float _1308 = _1229.z;
        float2 _1309 = _1222.xy * 1.0f;
        float2 _1310 = floor(_1309);
        float2 _1313 = frac(_1310 * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1317 = _1313 + dot(_1313, _1313 + 34.345001220703125f.xx).xx;
        float _1318 = _1317.x;
        float _1319 = _1317.y;
        float2 _1323 = frac(float2(_1318 * _1319, _1318 + _1319));
        float2 _1326 = frac((_1310 + 114.51399993896484375f.xx) * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1330 = _1326 + dot(_1326, _1326 + 34.345001220703125f.xx).xx;
        float _1331 = _1330.x;
        float _1332 = _1330.y;
        float2 _1336 = frac(float2(_1331 * _1332, _1331 + _1332));
        float _1342 = _1323.x;
        float _1344 = 0.25f * lerp(0.60000002384185791015625f, 1.0f, _1342);
        float2 _1345 = ((_1309 - _1310) + ((((_1336 * 2.0f) - 1.0f.xx) * 0.25f) * 1.0f)) - 0.5f.xx;
        float _1348 = _1345.y;
        float2 _1352 = float2(_1345.x * 1.25f, _1348 * ((_1348 < 0.0f) ? 1.25f : 0.75f));
        float _1355 = _1219 + _1342;
        float _1359 = _1209 ? frac(_1355) : lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(_1355, 0.0f, 1.0f));
        float _1371 = _1323.y;
        float _1374 = ((smoothstep(0.20000000298023223876953125f, 0.2199999988079071044921875f, _1359) * smoothstep(0.85000002384185791015625f, 0.550000011920928955078125f, _1359)) * step(0.001000000047497451305389404296875f, smoothstep(_1344, 0.0f, length(_1352)))) * step(_1214, _1371 - 0.100000001490116119384765625f);
        float _1377 = _1374 * _1308;
        float _1385 = _1229.x;
        float2 _1386 = _1222.zy * 1.0f;
        float2 _1387 = floor(_1386);
        float2 _1390 = frac(_1387 * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1394 = _1390 + dot(_1390, _1390 + 34.345001220703125f.xx).xx;
        float _1395 = _1394.x;
        float _1396 = _1394.y;
        float2 _1400 = frac(float2(_1395 * _1396, _1395 + _1396));
        float2 _1403 = frac((_1387 + 114.51399993896484375f.xx) * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1407 = _1403 + dot(_1403, _1403 + 34.345001220703125f.xx).xx;
        float _1408 = _1407.x;
        float _1409 = _1407.y;
        float2 _1413 = frac(float2(_1408 * _1409, _1408 + _1409));
        float _1419 = _1400.x;
        float _1421 = 0.25f * lerp(0.60000002384185791015625f, 1.0f, _1419);
        float2 _1422 = ((_1386 - _1387) + ((((_1413 * 2.0f) - 1.0f.xx) * 0.25f) * 1.0f)) - 0.5f.xx;
        float _1425 = _1422.y;
        float2 _1429 = float2(_1422.x * 1.25f, _1425 * ((_1425 < 0.0f) ? 1.25f : 0.75f));
        float _1432 = _1219 + _1419;
        float _1436 = _1209 ? frac(_1432) : lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(_1432, 0.0f, 1.0f));
        float _1448 = _1400.y;
        float _1451 = ((smoothstep(0.20000000298023223876953125f, 0.2199999988079071044921875f, _1436) * smoothstep(0.85000002384185791015625f, 0.550000011920928955078125f, _1436)) * step(0.001000000047497451305389404296875f, smoothstep(_1421, 0.0f, length(_1429)))) * step(_1214, _1448 - 0.100000001490116119384765625f);
        float _1454 = _1451 * _1385;
        float2 _1467 = (float4(((clamp(_1275 / _1267.xx, (-1.0f).xx, 1.0f.xx) * lerp(0.25f, 0.5f, _1259.x)) * _1297) * _1231, _1300, _1294).xy + float4(((clamp(_1352 / _1344.xx, (-1.0f).xx, 1.0f.xx) * lerp(0.25f, 0.5f, _1336.x)) * _1374) * _1308, _1377, _1371).xy) + float4(((clamp(_1429 / _1421.xx, (-1.0f).xx, 1.0f.xx) * lerp(0.25f, 0.5f, _1413.x)) * _1451) * _1385, _1454, _1448).xy;
        float _1469 = max(_1454, max(_1300, _1377));
        float4 _1472 = float4(_1467, _1469, 0.0f);
        float2 _1474 = _1223.xz * 1.0f;
        float2 _1475 = floor(_1474);
        float2 _1478 = frac(_1475 * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1482 = _1478 + dot(_1478, _1478 + 34.345001220703125f.xx).xx;
        float _1483 = _1482.x;
        float _1484 = _1482.y;
        float2 _1488 = frac(float2(_1483 * _1484, _1483 + _1484));
        float2 _1491 = frac((_1475 + 114.51399993896484375f.xx) * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1495 = _1491 + dot(_1491, _1491 + 34.345001220703125f.xx).xx;
        float _1496 = _1495.x;
        float _1497 = _1495.y;
        float2 _1501 = frac(float2(_1496 * _1497, _1496 + _1497));
        float _1507 = _1488.x;
        float _1509 = 0.25f * lerp(0.60000002384185791015625f, 1.0f, _1507);
        float2 _1510 = ((_1474 - _1475) + ((((_1501 * 2.0f) - 1.0f.xx) * 0.25f) * 1.0f)) - 0.5f.xx;
        float _1513 = _1510.y;
        float2 _1517 = float2(_1510.x * 1.25f, _1513 * ((_1513 < 0.0f) ? 1.25f : 0.75f));
        float _1520 = _1221 + _1507;
        float _1524 = _1209 ? frac(_1520) : lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(_1520, 0.0f, 1.0f));
        float _1536 = _1488.y;
        float _1539 = ((smoothstep(0.20000000298023223876953125f, 0.2199999988079071044921875f, _1524) * smoothstep(0.85000002384185791015625f, 0.550000011920928955078125f, _1524)) * step(0.001000000047497451305389404296875f, smoothstep(_1509, 0.0f, length(_1517)))) * step(_1214, _1536 - 0.100000001490116119384765625f);
        float _1542 = _1539 * _1231;
        float2 _1547 = _1223.xy * 1.0f;
        float2 _1548 = floor(_1547);
        float2 _1551 = frac(_1548 * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1555 = _1551 + dot(_1551, _1551 + 34.345001220703125f.xx).xx;
        float _1556 = _1555.x;
        float _1557 = _1555.y;
        float2 _1561 = frac(float2(_1556 * _1557, _1556 + _1557));
        float2 _1564 = frac((_1548 + 114.51399993896484375f.xx) * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1568 = _1564 + dot(_1564, _1564 + 34.345001220703125f.xx).xx;
        float _1569 = _1568.x;
        float _1570 = _1568.y;
        float2 _1574 = frac(float2(_1569 * _1570, _1569 + _1570));
        float _1580 = _1561.x;
        float _1582 = 0.25f * lerp(0.60000002384185791015625f, 1.0f, _1580);
        float2 _1583 = ((_1547 - _1548) + ((((_1574 * 2.0f) - 1.0f.xx) * 0.25f) * 1.0f)) - 0.5f.xx;
        float _1586 = _1583.y;
        float2 _1590 = float2(_1583.x * 1.25f, _1586 * ((_1586 < 0.0f) ? 1.25f : 0.75f));
        float _1593 = _1221 + _1580;
        float _1597 = _1209 ? frac(_1593) : lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(_1593, 0.0f, 1.0f));
        float _1609 = _1561.y;
        float _1612 = ((smoothstep(0.20000000298023223876953125f, 0.2199999988079071044921875f, _1597) * smoothstep(0.85000002384185791015625f, 0.550000011920928955078125f, _1597)) * step(0.001000000047497451305389404296875f, smoothstep(_1582, 0.0f, length(_1590)))) * step(_1214, _1609 - 0.100000001490116119384765625f);
        float _1615 = _1612 * _1308;
        float2 _1620 = _1223.zy * 1.0f;
        float2 _1621 = floor(_1620);
        float2 _1624 = frac(_1621 * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1628 = _1624 + dot(_1624, _1624 + 34.345001220703125f.xx).xx;
        float _1629 = _1628.x;
        float _1630 = _1628.y;
        float2 _1634 = frac(float2(_1629 * _1630, _1629 + _1630));
        float2 _1637 = frac((_1621 + 114.51399993896484375f.xx) * float2(123.339996337890625f, 456.209991455078125f));
        float2 _1641 = _1637 + dot(_1637, _1637 + 34.345001220703125f.xx).xx;
        float _1642 = _1641.x;
        float _1643 = _1641.y;
        float2 _1647 = frac(float2(_1642 * _1643, _1642 + _1643));
        float _1653 = _1634.x;
        float _1655 = 0.25f * lerp(0.60000002384185791015625f, 1.0f, _1653);
        float2 _1656 = ((_1620 - _1621) + ((((_1647 * 2.0f) - 1.0f.xx) * 0.25f) * 1.0f)) - 0.5f.xx;
        float _1659 = _1656.y;
        float2 _1663 = float2(_1656.x * 1.25f, _1659 * ((_1659 < 0.0f) ? 1.25f : 0.75f));
        float _1666 = _1221 + _1653;
        float _1670 = _1209 ? frac(_1666) : lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(_1666, 0.0f, 1.0f));
        float _1682 = _1634.y;
        float _1685 = ((smoothstep(0.20000000298023223876953125f, 0.2199999988079071044921875f, _1670) * smoothstep(0.85000002384185791015625f, 0.550000011920928955078125f, _1670)) * step(0.001000000047497451305389404296875f, smoothstep(_1655, 0.0f, length(_1663)))) * step(_1214, _1682 - 0.100000001490116119384765625f);
        float _1688 = _1685 * _1385;
        float2 _1696 = (float4(((clamp(_1517 / _1509.xx, (-1.0f).xx, 1.0f.xx) * lerp(0.25f, 0.5f, _1501.x)) * _1539) * _1231, _1542, _1536).xy + float4(((clamp(_1590 / _1582.xx, (-1.0f).xx, 1.0f.xx) * lerp(0.25f, 0.5f, _1574.x)) * _1612) * _1308, _1615, _1609).xy) + float4(((clamp(_1663 / _1655.xx, (-1.0f).xx, 1.0f.xx) * lerp(0.25f, 0.5f, _1647.x)) * _1685) * _1385, _1688, _1682).xy;
        float4 _1701 = float4(_1696, max(_1688, max(_1542, _1615)), 0.0f);
        float _1703 = step(max(float2(_1267 * _1297, _407) * _1231, max(float2(_1344 * _1374, _407) * _1308, float2(_1421 * _1451, _407) * _1385)).x, 0.00999999977648258209228515625f);
        float2 _1707 = _1472.xy + (_1701.xy * _1703);
        float3 _1716 = float3((_1181.xy * 2.0f) - 1.0f.xx, 0.0f) + float3(_1707.x, _1707.y, 0.0f.xxx.z);
        float2 _1720 = float2(0.0f, (EFWetTime() * _CharacterParams10.z) * 0.75f);
        float3 _1723 = float3(_1150.x, 0.0f, _1150.z);
        float3 _1729 = abs(_1723 * rsqrt(max(1.1754943508222875079687365372222e-38f, dot(_1723, _1723)))) - 0.20000000298023223876953125f.xxx;
        float3 _1732 = max((_1729 * _1729) * _1729, 6.103515625e-05f.xxx);
        float3 _1735 = _1732 / dot(_1732, 1.0f.xxx).xxx;
        float _1754 = _1735.z;
        float _1756 = _1735.x;
        float4 _1758 = (_CharacterRainStreakTex.SampleBias(sampler_BumpMap, _1166, _EndfieldCapturedGlobalMipBias) * _1754) + (_CharacterRainStreakTex.SampleBias(sampler_BumpMap, _1171, _EndfieldCapturedGlobalMipBias) * _1756);
        float2 _1770 = _1716.xy + ((((_1758.xy * 2.0f) - 1.0f.xx) * ((_CharacterRainStreakTex.SampleBias(sampler_BumpMap, _1166 + _1720, _EndfieldCapturedGlobalMipBias).w * _1754) + (_CharacterRainStreakTex.SampleBias(sampler_BumpMap, _1171 + _1720, _EndfieldCapturedGlobalMipBias).w * _1756))) * _1205);
        float3 _1771 = float3(_1770.x, _1770.y, _1716.z);
        float _1772 = _1758.z;
        float _1777 = max(max(max(_1472.zw * step(0.00999999977648258209228515625f, _1469), _1701.zw * _1703).x, step(1.0099999904632568359375f - _1205, _1181.z)), smoothstep(1.0f - _1772, 1.10000002384185791015625f - _1772, _1205) * _1205);
        float2 _1778 = _1770.xy;
        _1771.z = max(1.000000016862383526387164645044e-16f, sqrt(1.0f - clamp(dot(_1778, _1778), 0.0f, 1.0f)));
        float3 _1785 = normalize(_1771);
        float3 _1786 = cross(_553, float3(0.0f, 1.0f, 0.0f));
        bool3 _1789 = (dot(_1786, _1786) > 6.103515625e-05f).xxx;
        float3 _1790 = normalize(_1786);
        float3 _1791 = float3(_1789.x ? _1790.x : float3(1.0f, 0.0f, 0.0f).x, _1789.y ? _1790.y : float3(1.0f, 0.0f, 0.0f).y, _1789.z ? _1790.z : float3(1.0f, 0.0f, 0.0f).z);
        float _1802 = min(_485, 0.0500000007450580596923828125f);
        float _1803 = lerp(_485, _1802, _1777);
        float _1820 = lerp(1.0f, 0.5f, (_1193 * (1.0f - _1139)) * (1.0f - _1202));
        _1828 = normalize(lerp(_553, normalize(((_1791 * _1785.x) + (cross(_1791, _553) * _1785.y)) + (_553 * _1785.z)), _1777.xxx));
        _1829 = _1777;
        _1830 = _1802;
        _1831 = _1777;
        _1832 = max(_1803 - ((0.20000000298023223876953125f * _1139) * _1193), min(0.20000000298023223876953125f, _1803));
        _1833 = _498 * _1820;
        _1834 = lerp(_476, _476 * ((smoothstep(0.699999988079071044921875f, 0.300000011920928955078125f, dot(_476, float3(0.21267290413379669189453125f, 0.715152204036712646484375f, 0.072175003588199615478515625f))) * 0.5f) + 1.0f).xxx, (_1777 * _1200).xxx) * _1820;
    }
    else
    {
        _1828 = _553;
        _1829 = 0.0f;
        _1830 = 0.00999999977648258209228515625f;
        _1831 = 0.0f;
        _1832 = _485;
        _1833 = _498;
        _1834 = _476;
    }
// SOURCE_BLOCK_END
    EFWetSurface result;
    result.specNormal = _1828;
    result.roughness = _1832;
    result.shadowAlbedo = _1833;
    result.albedo = _1834;
    result.coverage = _1829;
    return result;
}
#endif
