// Generated from the official decompiled pass. Do not edit by hand.
// Source: _dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/
//         runtime/shaders/lighting/shadow/screenspaceshadowresolve.shader
// Declared once in that file, at lines 616 (_247) and 617 (_248), inside the
// ScreenSpaceShadowResolve_Character pass (lines 553-1143). The directional pass
// uses differently named tables, so there is no ambiguity about which copy applies.
// Values are round-tripped through float32 so each literal is exactly the constant
// the GPU sees. The dump is local-only and gitignored, hence this file is committed.

#ifndef ENDFIELD_CHARACTER_SHADOW_TABLES_INCLUDED
#define ENDFIELD_CHARACTER_SHADOW_TABLES_INCLUDED

// _247: 16 Poisson offsets used by the character shadow gather loop.
static const float2 ENDFIELD_SHADOW_POISSON[16] =
{
    float2(-0.9420162439346313, -0.3990621566772461),
    float2(0.945586085319519, -0.7689072489738464),
    float2(-0.09418410062789917, -0.929388701915741),
    float2(0.3449593782424927, 0.29387760162353516),
    float2(-0.9158858060836792, 0.457714319229126),
    float2(-0.8154423236846924, -0.879124641418457),
    float2(-0.3827754259109497, 0.27676844596862793),
    float2(0.9748439788818359, 0.756483793258667),
    float2(0.4432332515716553, -0.9751155376434326),
    float2(0.5374298095703125, -0.47373420000076294),
    float2(-0.2649691104888916, -0.4189302325248718),
    float2(0.7919751405715942, 0.19090187549591064),
    float2(-0.2418884038925171, 0.9970650672912598),
    float2(-0.8140995502471924, 0.914375901222229),
    float2(0.19984126091003418, 0.7864136695861816),
    float2(0.14383161067962646, -0.1410079002380371)
};

// _248: 16 rotation basis vectors indexed by (px%%4)*4 + (py%%4), giving each pixel
// a different rotation of the Poisson disk. Used as float2x2(v, float2(-v.y, v.x)).
static const float2 ENDFIELD_SHADOW_ROTATION[16] =
{
    float2(-0.39965590834617615, 0.9166651964187622),
    float2(0.12451229989528656, -0.9922180771827698),
    float2(0.8523542881011963, 0.5229647159576416),
    float2(-0.2293124943971634, 0.9733529090881348),
    float2(-0.7724061012268066, 0.6351289749145508),
    float2(0.7927525043487549, -0.6095436811447144),
    float2(-0.5780497193336487, 0.8160015940666199),
    float2(-0.8311296105384827, -0.5560787916183472),
    float2(0.8077948093414307, 0.5894637703895569),
    float2(0.4714154005050659, 0.8819112777709961),
    float2(-0.3139738142490387, -0.9494317173957825),
    float2(-0.9450067281723022, -0.3270510137081146),
    float2(-0.18503740429878235, -0.9827315211296082),
    float2(-0.9337558746337891, 0.35791051387786865),
    float2(-0.9976140856742859, 0.06903629750013351),
    float2(0.30612778663635254, 0.9519904255867004)
};

#endif
