# -*- coding: utf-8 -*-
"""精确解析场景 YAML，dump 每个 SMR 的骨骼引用(m_Bones)、rootBone、enabled，
并与 JSON 数据的 m.bones(全局索引) 逐槽位对比，验证场景保存的骨骼映射是否与数据一致。"""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCENE = r"A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Assets\Scenes\Typhoeus_Showcase.unity"
JSON_PATH = r"A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Assets\Typhoeus\_typhoea_model_data.json"

text = open(SCENE, 'r', encoding='utf-8').read()
doc_re = re.compile(r'^--- !u!(\d+) &(\d+)\s*$', re.M)
matches = list(doc_re.finditer(text))
docs = []
for i, m in enumerate(matches):
    start = m.end(); end = matches[i+1].start() if i+1 < len(matches) else len(text)
    body = text[start:end]
    typ = body.strip().split('\n', 1)[0].rstrip(':').strip()
    docs.append((int(m.group(1)), int(m.group(2)), typ, body))

# GameObject 名字表
gos = {}
for cls, fid, typ, body in docs:
    if typ.startswith('GameObject'):
        mm = re.search(r'm_Name:\s*(.+)', body)
        if mm: gos[fid] = mm.group(1).strip()

print(f"docs={len(docs)} gos={len(gos)}")

# JSON 数据
data = json.load(open(JSON_PATH, 'r', encoding='utf-8'))
bones = data['bones']
nb = len(bones)
mesh_by_name = {}
for m in data['meshes']:
    mesh_by_name[m['name']] = m

# Transform 名字表（用于把 m_Bones 的 fileID 解析成骨骼名）
trans_name = {}
for cls, fid, typ, body in docs:
    if typ.startswith('Transform'):
        go = re.search(r'm_GameObject:\s*\{fileID:\s*(\d+)\}', body)
        if go and int(go.group(1)) in gos:
            trans_name[fid] = gos[int(go.group(1))]

print("="*100)
print("SMR scene-vs-JSON bones mapping check")
print("="*100)
for cls, fid, typ, body in docs:
    if not typ.startswith('SkinnedMeshRenderer'):
        continue
    go = re.search(r'm_GameObject:\s*\{fileID:\s*(\d+)\}', body)
    if not go: continue
    gname = gos.get(int(go.group(1)), '?')
    # enabled
    en = re.search(r'm_Enabled:\s*(\d+)', body)
    enabled = en.group(1) == '1' if en else False
    # m_Bones 列表（YAML "- {fileID: N}"）
    mb = re.search(r'm_Bones:\s*\n((?:\s*-\s*\{fileID:\s*\d+\}\s*\n?)*)', body)
    scene_bones = []
    if mb:
        scene_bones = [int(x) for x in re.findall(r'\{fileID:\s*(\d+)\}', mb.group(1))]
    # rootBone
    rb = re.search(r'm_RootBone:\s*\{fileID:\s*(\d+)\}', body)
    root_name = trans_name.get(int(rb.group(1)), '?') if rb else '?'
    # JSON 对比
    md = mesh_by_name.get(gname)
    json_global = md['bones'] if md else None
    json_bcount = len(json_global) if json_global else 0
    scene_bnames = [trans_name.get(b, '?') for b in scene_bones]
    # 验证：scene_bones 的数量和 JSON bcount 是否一致，且每个 scene bone 的 transform 名字 == JSON 全局骨骼名
    match = (len(scene_bones) == json_bcount) if md else False
    if match:
        for s, gi in zip(scene_bones, json_global):
            if 0 <= gi < nb and trans_name.get(s) != bones[gi]['name']:
                match = False
    verdict = 'OK' if match else 'MISMATCH'
    print(f"{gname:<42} enabled={int(enabled)}  sceneBones={len(scene_bones):>3}  jsonBones={json_bcount:>3}  root={root_name:<20} {verdict}")
    if not match and md:
        print(f"    scene bone names: {scene_bnames}")
        print(f"    json  global idx : {json_global}")
        print(f"    json  bone names : {[bones[gi]['name'] for gi in json_global if 0<=gi<nb]}")
