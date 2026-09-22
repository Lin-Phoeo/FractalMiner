# -*- coding: utf-8 -*-
"""严格模拟 TyphoeusModelBuilder.cs 的骨骼摆放 + 蒙皮，找出角掉落地面的根因。

构建器关键逻辑（嫌疑点）：
  1. local = parentTheoryWorld^-1 * theoryWorld   (理论局部矩阵)
  2. Unity Transform 摆放: localRotation = local.rotation, localScale = (1,1,1)
     —— 矩阵分解丢 scale/镜像(det<0)，理论局部无法精确表达
  3. 蒙皮: skinned = Σ w_b * actualWorld_b * meshBindpose_b * v
     actualWorld 链累积分解误差 → 绑定姿势下顶点不再回到原位 → 部件掉落

输出：
  Phase1: 每根骨骼 理论世界 vs Unity实际世界 的位置/旋转偏差（>1cm 的算嫌疑）
  Phase2: 每 mesh 原始顶点范围（Z-up 原始空间，判断哪个是"角"）
  Phase3: 抽样蒙皮 → 每 mesh 绑定姿势下的顶点漂移（掉地上的=米级漂移）
"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

JSON_PATH = r"A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Assets\Typhoeus\_typhoea_model_data.json"

# ---------- 纯 Python 4x4 矩阵（row-major: M[r][c]）----------
def I4():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]

def mat_mul(A, B):
    return [[sum(A[r][k] * B[k][c] for k in range(4)) for c in range(4)] for r in range(4)]

def mat_vec(M, v):
    return [sum(M[r][k] * v[k] for k in range(4)) for r in range(4)]

def mat_inv(M):
    # 高斯消元求逆（增广矩阵）
    n = 4
    A = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            return None
        A[col], A[piv] = A[piv], A[col]
        pv = A[col][col]
        A[col] = [x / pv for x in A[col]]
        for r in range(n):
            if r != col and A[r][col] != 0.0:
                f = A[r][col]
                A[r] = [a - f * b for a, b in zip(A[r], A[col])]
    return [row[n:] for row in A]

def det3(M):
    # 上左 3x3 行列式
    return (M[0][0]*(M[1][1]*M[2][2]-M[1][2]*M[2][1])
          - M[0][1]*(M[1][0]*M[2][2]-M[1][2]*M[2][0])
          + M[0][2]*(M[1][0]*M[2][1]-M[1][1]*M[2][0]))

def col(M, c):
    return (M[0][c], M[1][c], M[2][c])

def norm3(v):
    return (v[0]*v[0]+v[1]*v[1]+v[2]*v[2]) ** 0.5

def sub3(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def read_matrix_unity(flat, index):
    """JSON 行主序 → Unity 列主序语义（TyphoeusModelBuilder.ReadMatrix 的转置读取）。
    返回 row-major 存储 M[r][c] = flat[o + c*4 + r]"""
    o = index * 16
    if flat is None or o + 15 >= len(flat):
        return I4()
    return [[flat[o + c*4 + r] for c in range(4)] for r in range(4)]

def decompose_unity(local):
    """模拟 Unity Transform 摆放：localRotation = local.rotation + localScale=(1,1,1)。
    即：取三列方向归一化（丢 scale），保留平移。镜像(det<0)矩阵会丢失反射。"""
    t = col(local, 3)
    out = I4()
    for c, fallback in ((0, (1,0,0)), (1, (0,1,0)), (2, (0,0,1))):
        v = col(local, c)
        n = norm3(v)
        if n < 1e-6:
            v = fallback; n = 1.0
        out[0][c], out[1][c], out[2][c] = v[0]/n, v[1]/n, v[2]/n
    out[0][3], out[1][3], out[2][3] = t
    return out

def scale_of(local):
    return (norm3(col(local,0)), norm3(col(local,1)), norm3(col(local,2)))

# ---------- 加载数据 ----------
with open(JSON_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)
bones = data['bones']
nb = len(bones)
meshes = data['meshes']
print(f"bones={nb} meshes={len(meshes)}")

# ---------- 全局 bindpose 合并（严格按构建器覆盖顺序） ----------
bindPoses = [I4() for _ in range(nb)]
hasBindPose = [False]*nb
for m in meshes:
    mb = m.get('bones') or []
    for b, gi in enumerate(mb):
        if 0 <= gi < nb:
            bindPoses[gi] = read_matrix_unity(m.get('bindPoses'), b)
            hasBindPose[gi] = True

# ---------- 理论世界矩阵（bindpose^-1） ----------
theoryWorld = [mat_inv(bindPoses[i]) if hasBindPose[i] else I4() for i in range(nb)]

# ---------- Unity 实际世界矩阵（含分解误差累积） ----------
actualWorld = [None]*nb
localInfo = [None]*nb   # (parent, det, scale)
for i, b in enumerate(bones):
    p = b['parent']
    world = theoryWorld[i]
    if 0 <= p < nb:
        pw = theoryWorld[p]      # 构建器用理论 parentWorld 求 local
        pw_inv = mat_inv(pw)
        if pw_inv is None:
            local = world
        else:
            local = mat_mul(pw_inv, world)
        actual = mat_mul(actualWorld[p], decompose_unity(local))
    else:
        local = world
        actual = decompose_unity(local)
    actualWorld[i] = actual
    localInfo[i] = (p, det3(local), scale_of(local))

# ---------- Phase 1: 骨骼偏差表 ----------
print("\n" + "="*96)
print("Phase 1: bones whose actual-world != theory-world  (posErr > 1cm or det<0)")
print("="*96)
suspects = []
for i in range(nb):
    tp, ap = col(theoryWorld[i], 3), col(actualWorld[i], 3)
    d = norm3(sub3(tp, ap))
    p, dt, sc = localInfo[i]
    mirrored = dt < -1e-6
    scaled = any(abs(s-1.0) > 1e-4 for s in sc)
    if d > 0.01 or mirrored or scaled:
        suspects.append((i, d, dt, sc))
        tag = []
        if mirrored: tag.append(f"MIRROR(det={dt:.3f})")
        if scaled: tag.append(f"SCALE={tuple(round(s,4) for s in sc)}")
        if d > 0.01: tag.append(f"posErr={d*100:.1f}cm")
        print(f"  [{i:>3}] {bones[i]['name']:<46} p={p:>3}  {' '.join(tag)}")
print(f"  -> suspect bones = {len(suspects)} / {nb}")

# ---------- Phase 2: 每 mesh 原始顶点范围（Z-up 原始空间） ----------
print("\n" + "="*96)
print("Phase 2: mesh vertex ranges in raw space (Z-up; head/角 ≈ z>1.4)")
print("="*96)
for m in meshes:
    vs = m['vertices']
    vc = len(vs)//3
    zs = [vs[i*3+2] for i in range(vc)]
    xs = [vs[i*3] for i in range(vc)]
    print(f"  {m['name']:<42} verts={vc:>6}  z=[{min(zs):+.3f},{max(zs):+.3f}]  x=[{min(xs):+.3f},{max(xs):+.3f}]")

# ---------- Phase 3: 抽样蒙皮 → 绑定姿势顶点漂移 ----------
print("\n" + "="*96)
print("Phase 3: per-mesh bind-pose skinning drift (sampled; 0 = perfect)")
print("="*96)
for m in meshes:
    mb = m.get('bones') or []
    bcount = len(mb)
    bws_i = m.get('boneWeightIndices') or []
    bws_v = m.get('boneWeightValues') or []
    vs = m['vertices']
    vc = len(vs)//3
    if vc == 0 or bcount == 0:
        continue
    meshBP = [read_matrix_unity(m.get('bindPoses'), b) for b in range(bcount)]
    stride = max(1, vc // 1500)
    maxdrift = 0.0; maxdrift_v = 0; sumdrift = 0.0; cnt = 0
    worst_bones = set()
    for i in range(0, vc, stride):
        v = (vs[i*3], vs[i*3+1], vs[i*3+2], 1.0)
        sx = sy = sz = 0.0
        for k in range(4):
            w = bws_v[i*4+k]
            if w <= 0: continue
            bi = bws_i[i*4+k]
            if bi < 0 or bi >= bcount: continue
            gi = mb[bi]
            if gi < 0 or gi >= nb: continue
            sk = mat_vec(mat_mul(actualWorld[gi], meshBP[bi]), v)
            sx += w*sk[0]; sy += w*sk[1]; sz += w*sk[2]
        drift = norm3((sx-v[0], sy-v[1], sz-v[2]))
        sumdrift += drift; cnt += 1
        if drift > maxdrift:
            maxdrift = drift; maxdrift_v = i
            for k in range(4):
                if bws_v[i*4+k] > 0 and 0 <= bws_i[i*4+k] < bcount:
                    worst_bones.add(bws_i[i*4+k])
    mean = sumdrift/cnt if cnt else 0
    flag = "  <<<< DROPPED PART" if maxdrift > 0.3 else ""
    print(f"  {m['name']:<42} drift max={maxdrift*100:>7.1f}cm mean={mean*100:>6.1f}cm  worstVert#{maxdrift_v}{flag}")
    if maxdrift > 0.05 and worst_bones:
        gnames = [f"slot{b}->[{mb[b]}]{bones[mb[b]]['name']}" for b in sorted(worst_bones) if 0 <= mb[b] < nb][:10]
        print(f"      worst vert bones: {gnames}")
