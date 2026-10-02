# 官方物理：proxy分组输入与局部姿态链

日期：2026-10-02。接续[Transform baseline生成](../official-physics-baseline-build-20261002/README.md)。本轮将相邻三段合并：Int32 transform ID映射、**有前提的**原生子表顺序、baseline局部姿态求值；新增 `Tools/official_physics_proxy_baseline.py`，与已有生成器完成离线接线。不是Unity实时物理更新，舞台/渲染/湿身/阴影/当前预览物理不变。

## 本轮完成与明确界限

- `map_transform_ids`保持idArray原顶点顺序，parentId不存在则父索引-1；rootId逐项映射并保留重复/原顺序。负Int32 transform ID也能正常匹配，不因负号误当“无父”。输入是运行时Int32 ID，**不是解包PPtr的Int64 path ID**；没有擅自把556个原始Transform或骨名排序成proxy数组。
- `reverse_inserted_children_no_resize`恢复受限子表顺序：递增vertex插入、bucket链头插入、按链匹配parent读取 → 同parent子节点为插入逆序。仅适用于新建空表、串行Add、无删除/无扩容路径；**不是所有NativeMultiHashMap都永远逆序**。原生成器构造时传入3×vertexCount容量参数，构造转发与插入/扩容链已审查，但完整分配初始化、实际Job路径/实时实例仍未证明。
- `rotation_from_normal_tangent`恢复原辅助函数：normal作为up、tangent作为forward，right=normalize(cross(normal,tangent))，up'=cross(tangent,right)，以(right,up',tangent)为列转换四元数。不能交换normal/tangent，也不能追加forward归一化、LookRotationSafe兜底或统一四元数正负号。
- `evaluate_baseline_local_pose`按baseLineData的UInt16局部vertex索引求值。parent<0才输出位置zero、旋转identity；否则用父frame的inverse旋转child-parent的Single差，并乘child frame。读原始positions/normals/tangents，不拿上一次写出的local pose做输入。未列入的输出保留调用者提供的初始Single buffer。

**局部pose与角度kernel的“首项”规则不同**：局部pose不检查baseline slot是否为0。组首有合法父节点时仍算父空间局部值；角度预处理按首slot跳父边cache，而角度求解按Move过滤。已有测试覆盖这一区别，不能合并成一个“root始终identity”捷径。

输入映射/顺序/局部姿态的合成接线已通；真实角色11组的完整proxy输入（包括属性和中间normal处理）仍需恢复，不能据此宣布已生成它们的全部真实baseline。

## 原始证据

GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。原始文件/完整指令/商业源码只保留本地，不上传GitHub。没有启动游戏或Unity、执行DLL、附加或注入进程。

### proxy转换入口与次序

认证 `VirtualMesh.ConvertProxyMesh` method371526/RVA0x3ddaf90，unwind范围 `[0x3ddaf90,0x3ddc4bc)` 共5420字节，body SHA256 `005554d4f6a1f9a448d46c91b12e05d7e93176f218c1626dcbb449bf8c6921ad`。此前整范围解码失败不是代码损坏：末56字节为两张7项RVA表。现已完整分段审查5364字节代码+56字节表，每项均落在代码指令边界，两个cmp eax,6/ja/load/jmp分派逐个验证。不是自动全CFG或实时分派证明。

经VirtualMesh对象布局认证，isBoneCloth是Byte/Bool字段@40。0x3ddbfd0–0x3ddbfdc直接按此字段选CreateMeshBaseLine或CreateTransformBaseLine，**不是按meshType整数或骨名猜路径**。

```text
ProxyCreateFixedListAndAABB
  → isBoneCloth ? CreateTransformBaseLine : CreateMeshBaseLine
  → ProxyNormalAdjustment + 后续proxy方向/旋转处理中间任务
  → CreateBaseLinePose
  → CreateVertexRootAndDepth
```

关键调用0x3ddbfc6/0x3ddbfd5/0x3ddbfdc/0x3ddbffa/0x3ddc271/0x3ddc27b已与方法身份关联。流程图只表示这段已审查的相对先后，**不把中间任务删掉或宣称全部proxy转换已实现**。本轮pose API要求normal/tangent已经过应有的proxy前处理，而非从FBX或任意Transform直接猜这些输入。

ID map沿用已封存CreateTransformBaseLine证据：0x37e9b90–0x37e9bfe以vertex递增插入idArray→索引；0x37e9c70–0x37e9c84查询parentId失败写-1，成功从原entry读取value；rootIdList后续逐项查entry。缺root/重复ID拒绝作为adapter安全契约，不冒称所有原生异常路径已恢复。

### 子表顺序及扩容边界

原始构造0x37e98eb–0x37e98fc传入vertexCount和3×vertexCount；0x437a910→0x43dff30→0x43b8870继续转发容量。插入0x413a130→0x40e9130→0x3edb590；其完整unwind family有7片段，共519字节。0x3edb67f–0x3edb688写 `next[new]=oldHead; head=new`，key所在bucket由parent & mask选择。

原始枚举（上轮已完整分段保存）从bucket头读取、按next推进、比较parent key匹配；即使有不同parent的bucket碰撞，同key相对次序在**无rehash**条件下仍逆插入顺序。但满表会进0x4baed5b，调用0x6b111ec扩容重连：按旧链依次取出再向新bucket头插入，不能忽略它会改变顺序。本helper名字明确写no_resize，不接受“原骨架升序即可”作为无条件假设。

### 局部姿态与算术

认证 `VirtualMesh+BaseLine_CalcLocalPositionRotationJob.Execute` method371608/RVA0x39d3f90；3个由真实UNW_FLAG_CHAININFO关联的片段66/470/77字节，共613。对象unboxed字段：parentIndices@0、localPositions@16、localNormals@32、localTangents@48、baseLineIndices@64、vertexLocalPositions@80、vertexLocalRotations@96；不是带16字节header的对象offset。

0x39d3fb1读取UInt16 vertex；0x39d3fc1–0x39d3fc3按parent Int32符号选root路径；0x39d41bd–0x39d41ee写zero/identity。非root两次调用frame helper0x39d4250、父四元数dot→reciprocal→符号乘积、Single child-parent差、rotate、quaternion乘法，分别写回本vertex的两个输出。

frame helper0x39d4250/349字节；matrix→quaternion helper0x305c840/989字节；cross helper0x2cd47a0/236字节均有完整unwind解码。新增float3 dot与uint4 AND/XOR/NOT/OR五个受限直线leaf到RET的白名单检查；原float4 dot/缩放/组件积/float3减法及inverse/multiply/rotate复用[已封存角度缓存](../official-physics-angle-cache-20261002/README.md)，没有凭邻近方法距离猜leaf边界。

矩阵四元数保持IEEE signbit、swizzle与原归一化加法分组，包含负零语义，不换成trace分支“近似等价”实现。局部官方Mathematics1.2.6包quaternion.cs:43起的构造函数用于独立来源交叉核对，文件SHA256 `c72cf358f9b32b76d50bb2d4a7cd8ece301e2825870a7945c381f55f39c65620`。Python libm/Single参考仍**不代表游戏CRT/Burst逐位运行等价**。

## 验证、保留与下一步

先新测试缺模块RED，再实现。一个“非单位forward必须使yaw45变不同”的合成预期失败，经公式核对是对称轴缩放不改变该例的结果；改为能区分额外归一化的X轴例，不改官方公式迁就测试。

74个新用例覆盖Int32身份/负ID/缺parent/重复root、受限子表逆序与旧baseline生成器接线、32种主轴/斜轴姿态、非单位forward、退化拒绝、父空间局部位置/旋转、parent符号而非首slot、未列入输出保留、Single减法前输入舍入、空输入/错误数组/索引。全套 **1291 passed /114 subtests /3历史skip /2历史Pillow告警**；六个参考模块607语句、168分支，覆盖100%。Ruff/format、Pyright、临时环境pip-audit与新增代码密钥模式检查通过。

这轮技能流程用于先测试后实现、类型/分支/范围及保护值验证；没有Unity运行或动态物理验收。主HEAD/主index及七项runtime保护值保持，用户修改舞台的新hash照旧保护。私有证据路径/hash与限制见verification.json。

后续合并推进：首先补真实proxy输入（属性、中间方向处理、分配初始化）、root-depth及Team/baseline step依赖；然后集中串积分/惯性、碰撞、reset、骨骼单写入者输出，最后可切回Unity动态验收。已实现单角度baseline、分组控制流和此局部pose模块不反复重做；尚未查明的链路不以通用弹簧或艺术参数冒充原版。
