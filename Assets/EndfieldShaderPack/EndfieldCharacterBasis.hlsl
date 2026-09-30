#ifndef ENDFIELD_CHARACTER_BASIS_INCLUDED
#define ENDFIELD_CHARACTER_BASIS_INCLUDED

// Official skinned fragment input: per-part root rows at SSBO base, NOT
// weighted vertex matrices at base+3, nor the mesh object's native transform.
// Unity adapter supplies these three rows per renderer after pose evaluation.
// Existing property names retain compatibility with the initial skin adapter.
float4x4 EndfieldCharacterRootToWorld()
{
    if (_EndfieldSkinBasisEnabled > 0.5)
        return float4x4(_EndfieldSkinBasisRow0, _EndfieldSkinBasisRow1,
                        _EndfieldSkinBasisRow2, float4(0, 0, 0, 1));
    return GetObjectToWorldMatrix();
}

#endif
