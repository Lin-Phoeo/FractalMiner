// ============================================================
//  TyphoeusModelBuilder.cs
//  从 _typhoea_model_data.json 重建提弗洛斯模型：
//    481 骨骼层级 + 17 个 SkinnedMeshRenderer（含蒙皮权重/bind pose）。
//  数据源：EndfieldUnpacker 用 AnimeStudio 从官方 AssetBundle 提取，
//  骨骼名哈希已逆向为 CRC32(完整路径)，局部骨骼索引已映射到全局。
//  用法：菜单 Endfield/Rebuild Typhoeus Model
// ============================================================
using UnityEngine;
using UnityEditor;
using System;
using System.Collections.Generic;
using System.IO;

namespace Endfield
{
    [Serializable]
    public class TyphoeaBoneData
    {
        public string name;
        public int parent;
    }

    [Serializable]
    public class TyphoeaMeshData
    {
        public string name;
        public float[] vertices;
        public float[] normals;
        public float[] uvs;
        public int[] indices;
        public int[] subMeshIndexCounts;
        public int[] boneWeightIndices;
        public float[] boneWeightValues;
        public float[] bindPoses;
        public int[] bones;
    }

    [Serializable]
    public class TyphoeaModelData
    {
        public List<TyphoeaBoneData> bones;
        public List<TyphoeaMeshData> meshes;
    }

    public static class TyphoeusModelBuilder
    {
        const string DataPath = "Assets/Typhoeus/_typhoea_model_data.json";

        [MenuItem("Endfield/Rebuild Typhoeus Model")]
        public static void Rebuild()
        {
            string full = Path.Combine(Application.dataPath, "Typhoeus", "_typhoea_model_data.json");
            if (!File.Exists(full))
            {
                Debug.LogError("[Typhoeus] 找不到 " + full);
                return;
            }

            string json = File.ReadAllText(full);
            TyphoeaModelData data = JsonUtility.FromJson<TyphoeaModelData>(json);
            Debug.Log($"[Typhoeus] bones={data.bones.Count} meshes={data.meshes.Count}");

            // 1. 合并全局 bind pose（每个骨骼一个逆世界矩阵）
            Matrix4x4[] bindPoses = new Matrix4x4[data.bones.Count];
            bool[] hasBindPose = new bool[data.bones.Count];
            for (int i = 0; i < data.bones.Count; i++) bindPoses[i] = Matrix4x4.identity;

            foreach (var m in data.meshes)
            {
                for (int b = 0; b < m.bones.Length; b++)
                {
                    int gi = m.bones[b];
                    if (gi >= 0 && gi < data.bones.Count)
                    {
                        bindPoses[gi] = ReadMatrix(m.bindPoses, b);
                        hasBindPose[gi] = true;
                    }
                }
            }

            // 2. 构建骨骼层级
            Transform[] boneTransforms = new Transform[data.bones.Count];
            GameObject root = new GameObject("chr_0034_typhoea_rebuilt");
            root.transform.position = Vector3.zero;
            root.transform.rotation = Quaternion.identity;

            for (int i = 0; i < data.bones.Count; i++)
            {
                GameObject go = new GameObject(data.bones[i].name);
                int p = data.bones[i].parent;
                if (p >= 0 && p < data.bones.Count && boneTransforms[p] != null)
                    go.transform.SetParent(boneTransforms[p], false);
                else
                    go.transform.SetParent(root.transform, false);
                boneTransforms[i] = go.transform;

                // 世界矩阵 = bind pose 的逆；局部 = parentWorld^-1 * world
                Matrix4x4 world = hasBindPose[i] ? bindPoses[i].inverse : Matrix4x4.identity;
                if (p >= 0 && p < data.bones.Count)
                {
                    Matrix4x4 parentWorld = hasBindPose[p] ? bindPoses[p].inverse : Matrix4x4.identity;
                    Matrix4x4 local = parentWorld.inverse * world;
                    go.transform.localPosition = local.GetColumn(3);
                    go.transform.localRotation = local.rotation;
                    go.transform.localScale = Vector3.one;
                }
                else
                {
                    go.transform.localPosition = world.GetColumn(3);
                    go.transform.localRotation = world.rotation;
                    go.transform.localScale = Vector3.one;
                }
            }

            // 3. 构建每个 mesh + SkinnedMeshRenderer
            foreach (var m in data.meshes)
            {
                BuildMesh(m, root.transform, boneTransforms, data);
            }

            Debug.Log("[Typhoeus] 模型重建完成：" + root.name);
            Selection.activeGameObject = root;
        }

        static void BuildMesh(TyphoeaMeshData m, Transform root, Transform[] bones, TyphoeaModelData data)
        {
            GameObject go = new GameObject(m.name);
            go.transform.SetParent(root.transform, false);
            go.transform.localPosition = Vector3.zero;
            go.transform.localRotation = Quaternion.identity;

            int vcount = m.vertices.Length / 3;
            Vector3[] verts = new Vector3[vcount];
            Vector3[] norms = new Vector3[vcount];
            Vector2[] uvs = new Vector2[vcount];

            for (int i = 0; i < vcount; i++)
            {
                verts[i] = new Vector3(m.vertices[i * 3], m.vertices[i * 3 + 1], m.vertices[i * 3 + 2]);
                if (m.normals != null && m.normals.Length >= (i + 1) * 3)
                    norms[i] = new Vector3(m.normals[i * 3], m.normals[i * 3 + 1], m.normals[i * 3 + 2]);
                if (m.uvs != null && m.uvs.Length >= (i + 1) * 2)
                    uvs[i] = new Vector2(m.uvs[i * 2], m.uvs[i * 2 + 1]);
            }

            Mesh mesh = new Mesh();
            mesh.name = m.name;
            mesh.vertices = verts;
            mesh.normals = norms;
            mesh.uv = uvs;

            // submeshes
            int subCount = m.subMeshIndexCounts != null ? m.subMeshIndexCounts.Length : 1;
            if (subCount <= 0) subCount = 1;
            mesh.subMeshCount = subCount;
            int idxOff = 0;
            for (int s = 0; s < subCount; s++)
            {
                int ic = (m.subMeshIndexCounts != null && s < m.subMeshIndexCounts.Length)
                    ? m.subMeshIndexCounts[s] : (m.indices.Length - idxOff);
                int[] tris = new int[ic];
                Array.Copy(m.indices, idxOff, tris, 0, ic);
                mesh.SetTriangles(tris, s);
                idxOff += ic;
            }

            // bind poses
            int bcount = m.bones != null ? m.bones.Length : 0;
            Matrix4x4[] mBindPoses = new Matrix4x4[bcount];
            for (int b = 0; b < bcount; b++)
                mBindPoses[b] = ReadMatrix(m.bindPoses, b);
            mesh.bindposes = mBindPoses;

            // bone weights（4 组/顶点）
            BoneWeight[] bws = new BoneWeight[vcount];
            for (int i = 0; i < vcount; i++)
            {
                bws[i].boneIndex0 = m.boneWeightIndices[i * 4];
                bws[i].weight0 = m.boneWeightValues[i * 4];
                bws[i].boneIndex1 = m.boneWeightIndices[i * 4 + 1];
                bws[i].weight1 = m.boneWeightValues[i * 4 + 1];
                bws[i].boneIndex2 = m.boneWeightIndices[i * 4 + 2];
                bws[i].weight2 = m.boneWeightValues[i * 4 + 2];
                bws[i].boneIndex3 = m.boneWeightIndices[i * 4 + 3];
                bws[i].weight3 = m.boneWeightValues[i * 4 + 3];
            }
            mesh.boneWeights = bws;

            mesh.RecalculateBounds();

            // SkinnedMeshRenderer
            SkinnedMeshRenderer smr = go.AddComponent<SkinnedMeshRenderer>();
            smr.sharedMesh = mesh;

            Transform[] smrBones = new Transform[bcount];
            for (int b = 0; b < bcount; b++)
            {
                int gi = m.bones[b];
                smrBones[b] = (gi >= 0 && gi < bones.Length) ? bones[gi] : null;
            }
            smr.bones = smrBones;
            smr.rootBone = bones.Length > 1 ? bones[1] : bones[0];

            // 绑定材质
            Material[] mats = new Material[subCount];
            Material mat = ResolveMaterial(m.name);
            for (int s = 0; s < subCount; s++)
                mats[s] = mat;
            smr.sharedMaterials = mats;
        }

        static Material ResolveMaterial(string meshName)
        {
            // mesh 名 -> 材质名
            string matName = meshName;
            if (matName.EndsWith("_lod0")) matName = matName.Substring(0, matName.Length - 5);
            matName = matName.Replace("S_actor_", "M_actor_");

            // 特殊部件
            if (meshName.Contains("eyeshadow")) matName = "M_eyewhiteshadow_common_01";
            if (meshName.Contains("hairshadow")) matName = "M_hairshadow_common_04";
            if (meshName.Contains("vfxpart_01")) matName = "M_fx_typhoea_toppotential_01_1";
            if (meshName.Contains("vfxpart_02")) matName = "M_fx_typhoea_toppotential_01_2";
            if (meshName.Contains("vfxpart_03")) matName = "M_fx_typhoea_toppotential_01_4";

            string path = "Assets/Typhoeus/Materials/" + matName + ".mat";
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null)
            {
                // 尝试大小写（vfxpart 的 mesh 名是大写 Typhoea，材质是小写 typhoea）
                matName = matName.ToLower();
                path = "Assets/Typhoeus/Materials/" + matName + ".mat";
                mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            }
            if (mat == null)
                Debug.LogWarning("[Typhoeus] 找不到材质 " + path + "（mesh=" + meshName + "）");
            return mat;
        }

        static Matrix4x4 ReadMatrix(float[] flat, int index)
        {
            Matrix4x4 m = Matrix4x4.identity;
            if (flat == null || index * 16 + 15 >= flat.Length) return m;
            int o = index * 16;
            m.m00 = flat[o];   m.m01 = flat[o + 1];  m.m02 = flat[o + 2];  m.m03 = flat[o + 3];
            m.m10 = flat[o + 4]; m.m11 = flat[o + 5]; m.m12 = flat[o + 6]; m.m13 = flat[o + 7];
            m.m20 = flat[o + 8]; m.m21 = flat[o + 9]; m.m22 = flat[o + 10]; m.m23 = flat[o + 11];
            m.m30 = flat[o + 12]; m.m31 = flat[o + 13]; m.m32 = flat[o + 14]; m.m33 = flat[o + 15];
            return m;
        }
    }
}
