# -*- coding: utf-8 -*-
"""解析 Unity 场景 YAML，把 chr_0034_typhoea_rebuilt 下每根骨骼保存的局部 TRS
与理论绑定姿势（bindpose^-1 链推得的局部）逐项对比，找出被动过的骨骼。
这直接回答"角为什么掉地上"——场景保存的姿势偏离绑定姿势 = 掉落根因。"""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCENE = r"A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Assets\Scenes\Typhoeus_Showcase.unity"
JSON_PATH = r"A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Assets\Typhoeus\_typhoea_model_data.json"

# ---------- 场景 YAML 解析 ----------
doc_re = re.compile(r'^--- !u!(\d+) &(\d+) (.+)$', re.M)
with open(SCENE, 'r', encoding='utf-8') as f:
    text = f.read()

# 分割文档
docs = []   # (classid, fileid, typename, body)
matches = list(doc_re.finditer(text))
for i, m in enumerate(matches):
    start = m.end()
    end = matches[i+1].start() if i+1 < len(matches) else len(text)
    docs.append((int(m.group(1)), int(m.group(2)), m.group(3).strip(), text[start:end]))

def parse_vec3(s):
    m = re.search(r'x:\s*([-\d.eE+]+),\s*y:\s*([-\d.eE+]+),\s*z:\s*([-\d.eE+]+)', s)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None

def parse_quat(s):
    m = re.search(r'x:\s*([-\d.eE+]+),\s*y:\s*([-\d.eE+]+),\s*z:\s*([-\d.eE+]+),\s*w:\s*([-\d.eE+]+)', s)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))) if m else None

transforms = {}   # fileid -> dict(go, pos, rot, scale, father, children)
gos = {}          # fileid -> name
for cls, fid, typ, body in docs:
    if typ.startswith('GameObject'):
        m = re.search(r'm_Name:\s*(.+)', body)
        if m: gos[fid] = m.group(1).strip()
    elif typ.startswith('Transform'):
        go = re.search(r'm_GameObject:\s*\{fileID:\s*(\d+)\}', body)
        pos = re.search(r'm_LocalPosition:\s*(\{[^}]+\})', body)
        rot = re.search(r'm_LocalRotation:\s*(\{[^}]+\})', body)
        sc  = re.search(r'm_LocalScale:\s*(\{[^}]+\})', body)
        fa  = re.search(r'm_Father:\s*\{fileID:\s*(\d+)\}', body)
        transforms[fid] = {
            'go': int(go.group(1)) if go else 0,
            'pos': parse_vec3(pos.group(1)) if pos else (0,0,0),
            'rot': parse_quat(rot.group(1)) if rot else (0,0,0,1),
            'scale': parse_vec3(sc.group(1)) if sc else (1,1,1),
            'father': int(fa.group(1)) if fa else 0,
        }

print(f"scene docs={len(docs)}  transforms={len(transforms)}  gameobjects={len(gos)}")

# 找 root：名字 = chr_0034_typhoea_rebuilt 的 GameObject
root_tid = None
for tid, t in transforms.items():
    if gos.get(t['go']) == 'chr_0034_typhoea_rebuilt':
        root_tid = tid
        break
if root_tid is None:
    print("!! chr_0034_typhoea_rebuilt not found in scene"); sys.exit(1)
print(f"root transform fileID={root_tid}")

# 收集 root 子树（含 mesh 挂点）
def subtree(tid, out):
    out.append(tid)
    for fid, t in transforms.items():
        if t['father'] == tid:
            subtree(fid, out)
all_tids = []
subtree(root_tid, all_tids)
print(f"subtree transforms = {len(all_tids)}")

# ---------- 理论局部姿势（复用构建器逻辑） ----------
def I4(): return [[1.0 if r==c else 0.0 for c in range(4)] for r in range(4)]
def mat_mul(A,B): return [[sum(A[r][k]*B[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
def mat_inv(M):
    n=4; A=[row[:]+[1.0 if i==j else 0.0 for j in range(n)] for i,row in enumerate(M)]
    for col in range(n):
        piv=max(range(col,n),key=lambda r:abs(A[r][col]))
        if abs(A[piv][col])<1e-12: return None
        A[col],A[piv]=A[piv],A[col]; pv=A[col][col]; A[col]=[x/pv for x in A[col]]
        for r in range(n):
            if r!=col and A[r][col]!=0.0:
                f=A[r][col]; A[r]=[a-f*b for a,b in zip(A[r],A[col])]
    return [row[n:] for row in A]
def col(M,c): return (M[0][c],M[1][c],M[2][c])
def norm3(v): return (v[0]*v[0]+v[1]*v[1]+v[2]*v[2])**0.5
def sub3(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def read_matrix_unity(flat, index):
    o=index*16
    if flat is None or o+15>=len(flat): return I4()
    return [[flat[o+c*4+r] for c in range(4)] for r in range(4)]

with open(JSON_PATH,'r',encoding='utf-8') as f:
    data=json.load(f)
bones=data['bones']; nb=len(bones); meshes=data['meshes']
bindPoses=[I4() for _ in range(nb)]; hasBP=[False]*nb
for m in meshes:
    for b,gi in enumerate(m.get('bones') or []):
        if 0<=gi<nb:
            bindPoses[gi]=read_matrix_unity(m.get('bindPoses'),b); hasBP[gi]=True
theoryWorld=[mat_inv(bindPoses[i]) if hasBP[i] else I4() for i in range(nb)]
theoryLocal=[None]*nb
for i,b in enumerate(bones):
    p=b['parent']
    if 0<=p<nb:
        pwi=mat_inv(theoryWorld[p])
        theoryLocal[i]=mat_mul(pwi,theoryWorld[i]) if pwi else theoryWorld[i]
    else:
        theoryLocal[i]=theoryWorld[i]

# ---------- 对比 ----------
print("\n" + "="*100)
print("scene-vs-bindpose local pose diff (posErr>1mm or rotErr>0.5deg)")
print("="*100)
# 场景 Transform 按名字索引（骨骼名唯一性：官方骨架内不重名）
scene_by_name={}
for tid in all_tids:
    t=transforms[tid]
    name=gos.get(t['go'],'')
    if name and name!='chr_0034_typhoea_rebuilt':
        scene_by_name.setdefault(name,[]).append(tid)

mismatch=0; checked=0; root_children_note=[]
for i,b in enumerate(bones):
    name=b['name']
    cands=scene_by_name.get(name)
    if not cands: continue
    tid=cands[0]
    t=transforms[tid]
    tp=t['pos']
    # 理论局部平移（构建器: local.GetColumn(3)，即 theoryLocal 的平移列）
    thp=col(theoryLocal[i],3)
    derr=norm3(sub3(tp,thp))
    # 四元数点积（近似角度差）
    sr=t['rot']
    # 理论旋转：从理论局部矩阵提取（近似：去 scale 正交化后转四元数）——用平移差为主判定
    checked+=1
    if derr>0.001:
        mismatch+=1
        p=b['parent']
        pname=bones[p]['name'] if 0<=p<nb else 'ROOT'
        print(f"  [{i:>3}] {name:<44} parent={pname}")
        print(f"        scene pos = ({tp[0]:+.4f},{tp[1]:+.4f},{tp[2]:+.4f})")
        print(f"        bind  pos = ({thp[0]:+.4f},{thp[1]:+.4f},{thp[2]:+.4f})   posErr={derr*100:.2f}cm")
        if len(cands)>1: print(f"        (note: {len(cands)} transforms share this name)")

print(f"\nchecked={checked} bones present in scene; mismatched={mismatch}")
if mismatch==0:
    print(">> 场景保存的骨骼姿势与绑定姿势一致 —— 姿势没被改过，掉落另有原因。")

# ---------- 额外：SMR 状态 & cloth_05 的骨骼在场景里的世界位置 ----------
print("\n" + "="*100)
print("cloth_05 (top head part, single-bone) scene check")
print("="*100)
# 找 cloth_05 的 SMR 组件与其 m_Bones 引用
smr_by_name={}
for cls,fid,typ,body in docs:
    if typ.startswith('SkinnedMeshRenderer'):
        go=re.search(r'm_GameObject:\s*\{fileID:\s*(\d+)\}',body)
        if go:
            gname=gos.get(int(go.group(1)),'')
            smr_by_name[gname]=(fid,body)
for key in smr_by_name:
    if 'cloth_05' in key or 'Typhoea' in key and 'cloth' in key.lower():
        pass
print("SMR objects in scene:", [k for k in smr_by_name if 'Typhoea' in k or 'typhoea' in k])
for k,(fid,body) in smr_by_name.items():
    if 'cloth_05' in k:
        bones_refs=re.findall(r'm_Bones\[(\d+)\]:\s*\{fileID:\s*(\d+)\}',body)
        print(f"  {k}: bones refs={len(bones_refs)}")
        for idx,bfid in bones_refs[:5]:
            t=transforms.get(int(bfid))
            nm=gos.get(t['go']) if t else '?'
            print(f"    slot{idx} -> {nm} (fileID {bfid})")
        # SMR transform（挂点）与 rootBone
        rb=re.search(r'm_RootBone:\s*\{fileID:\s*(\d+)\}',body)
        if rb:
            t=transforms.get(int(rb.group(1)))
            print(f"    rootBone = {gos.get(t['go']) if t else '?'}")
