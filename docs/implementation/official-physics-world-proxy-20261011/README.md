# 世界空间 proxy 蒙皮 → 首次 reset

2026-10-11，接续[注册与首次初始化](../official-physics-particle-registration-20261011/README.md)。本轮把真正的 PreProxy 蒙皮生产器补为有限输入参考，再接入已验证的 reset14。**仍不是 Unity 实时物理完成**；舞台、渲染、湿身、阴影和当前预览后端未改。

## 本轮产物

- `Tools/official_physics_world_proxy.py`：权重前缀、三 float4 列矩阵乘、世界位置/帧、四 Team 窗口映射、独立 proxy 工作表门禁。
- `Tools/export_official_physics_world_proxy.py`：明确 SHA256 封印的 imports + 同态实际 getter 矩阵，导出 `world → registration → reset14`。同组按 actual Int32 instance ID 匹配，不按骨名；检查父 ID、序列化身份唯一性及矩阵四列。
- 两份专项测试：原顺序/Single 位模式、非零独立 chunk、缺失输入、零/负权重前缀、重复列表、不变 bindpose 下矩阵变化、原字段 reset 与封印/身份拒绝分支。

原入口：`CalcProxyMeshSkinningKernel$BurstManaged` method369736/RVA0x5a3fab0，完整1693字节；列表 method369695/RVA0x5a3bec8。不是物理后 `CalcProxySkinning` 映射。主代理重新执行静态 inspector：13 helper/1934字节（Weight.Count 和 flag 门禁按有界 CFG 覆盖多 RET），并直接重新核对上述两个完整主函数家族的原字节 SHA；未加载/执行原 DLL 或启动游戏。

## 已保留的官方结构

选定全局顶点 `v` 的四窗口映射：

```text
m = proxyMeshStart - proxyCommonStart + v
s = proxySkinBoneStart + boneIndices[k]
t = proxyTransformStart + skinBoneTransformIndices[s]
source = float4x3(position.xyz/w1, normal.xyz/w0, tangent.xyz/w0)
acc = zero48Bytes
for k in originalWeightPrefix:
    bound = bindpose[s] × source
    currentWorld = currentLocalToWorld[t] × bound
    acc = SingleEachLane(acc + SingleEachLane(currentWorld × rawWeight[k]))
worldPosition = exactDoubleWiden(acc.position.xyz)
worldFrame = frame(normalizeSingle(acc.normal.xyz), normalizeSingle(acc.tangent.xyz))
```

1. Count371651返回**最高严格正 Single 权重槽+1**；不是正值数量。之前的零/负前缀也读矩阵并累加。权重不 clamp、不重归一，不对骨 ID 或权重排序。
2. 两次矩阵乘各自按 `(((c0*x+c1*y)+c2*z)+c3*w)`，每乘/加均 Single；中间 w 完整保留。不能预合成矩阵、用 Double 累加或用 TRS 重建实际矩阵。
3. 法线与切线分别 normalize 后复用已认证 `(normal/up,tangent/forward)` frame API；不再次交换轴，不从 snapshot 四元数直接复制，不额外做负缩放 sign 修补。
4. 原 math kernel消费既有列表，不再读 flag/attributes 做过滤。四窗口、Team 正 Int16、安全容量/范围、有限/退化拒绝都是本有限适配器策略，不宣称原程序有这些异常检查。
5. 原 **proxy 列表**只要求 Enable2、排除bit61和0x800/0x80000；**不排除0x10、不要求Running0x20/Step0x80**。不能直接套更严格的 Simulation step 工作表门禁。Team0先跳过读表；显式调用者块顺序内保留完整升序 chunk 和重复项。

Count0、零/下溢/共线帧、非有限/溢出输入明确拒绝；不伪造 identity/旧姿态作为官方 fallback。离线返回私有值不是证明原 NativeArray 别名、原子顺序或 Burst 数值。

## 两态参考结果与边界

私有 `eleven-world-reset-01.json` 完成两态、每态11组/140顶点，共280个世界姿态与3920项 reset 字段写序。独立 NumPy Single 解释器**没有导入生产器/reset/quaternion 数学函数**，按行矩阵、向量乘加和原 sign-bit frame 构造重新计算；世界位置 Double 字节、四元数 Single 字节、全部14字段与写序相同。

原 getter 每态556记录，140 skin + 11 appended-render 矩阵全部按实际 ID、父 ID及序列化身份接通。使用的是重建的 serialized reference hierarchy；不是捕获的游戏动态角色。每组独立零起点实验 arena、Team1、flag15和脏缓存 seed 均明确标为**调用者实验布局**，不能记作原游戏全局 allocator/Team/clock 观测。

两态各自沿已有封印 import 构造 bindpose，是两个独立参考建模实验；不能宣称同一绑定态已在真实动画中连续更新。专项另测试固定 bindpose、改变 current 矩阵的接口路径，但这仍只是合成输入验证。None/零三角形/unreduced Bone 路线的已闭合输入继续复用，不推测动态覆盖或未实现路线。

93专项、4395全量 + 114 subtests通过，保留3项历史skip/2项Pillow告警；新增两模块233语句/76分支100%覆盖。Ruff/Black/Pyright/compileall及48个实际工具依赖审计通过。SHA、原输入/证据、准确门禁见`verification.json`；原资产、完整反汇编和含原派生坐标的参考 JSON 仅私有保存，不上传。

## 接下来

世界输入数学不再重做。沿 Team 参数与clock/Running/Step、TransformRead相对分支、完整工作表、唯一 writer/状态发布接成统一生命周期，再移入可回退 C# 候选后端。最后实测真实 MMD/解包动作、暂停/seek/reset、多帧接触、迁移及导出。此轮未接 Unity，不能以4300余离线测试冒充动态物理完工。
