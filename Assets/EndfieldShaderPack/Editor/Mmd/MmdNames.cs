// MmdNames.cs — canonical MMD bone/morph name normalization shared by the rig
// definition and the VMD reader, so names written by MMD tools (full-width
// digits/I/K, Japanese kana) match the rig's hardcoded bone names.
// e.g. "左足ＩＫ" and "左足IK" fold to the same key.
using System;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    public static class MmdName
    {
        public static string Normalize(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return VmdName.Normalize(s);
        }
    }
}
