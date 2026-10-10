# ColliderManager生产与Point整批消费：限定路径还原

2026-10-10。接续[约束调用链](../official-physics-constraint-chain-20261009/README.md)，本批实现碰撞体帧准备、子步WorkData生产、步末/帧末历史推进和Point稀疏列表消费。**这是可执行的离线有限值参考，不是Unity完整官方物理后端。**当前舞台、着色器及可见预览未变。

## 关键纠正：官方Single入口与Double Job不是同一条路

ColliderManager的frame/oldFrame/now/old位置数组，以及四个Job的位置字段均为`double3`。但Start/End/Post的`UnsafeDo`将原始`m_Buffer`指针直接交给`float3*`内核，没有逐元素数值转换。独立Job `Execute(int)`读取、写回Double位置，Start还有完整内联计算。

这是静态指针/字段/入口事实，**不是断言游戏实际走了错误路径**。实际`UseCrossFrameJob`/`UseAnimatorTransform`值、compiled间接函数与Burst行为未观测。不能将Raw Double缓冲别名改解释为数值转换，也不能用单入口测试证明全部路径等价。

| 源入口 | 位置精度及索引 | 本批参考 |
| --- | --- | --- |
| Pre managed370274，`0x5a57f68`；Range `0x5a588ec` | Double；原global collider槽 | `official_physics_collider_frame.py` |
| Start managed370322，`0x5a5a33c` | Single；稀疏list→global collider | `official_physics_collider_step.py`，显式Single类型 |
| Start Job370378，`0x5a66a3c` | Double；稀疏list→global collider | `official_physics_collider_job.py`，显式Double类型 |
| End Job370382，`0x4a474a0` | Double；稀疏list，无Team/collider门禁 | `end_collider_job(s)` / `end_collider_jobs(...)` |
| Post managed370346，`0x5a596a0` | Single；global collider槽 | `finish_collider_frame(...)`，独立Single类型 |
| Post Job370386，`0x5a5faa0` | Double；global collider槽 | `finish_collider_job_frame(...)` |
| Point managed Range368741，`0x59ea2b4` | signed length一次快照；list→particle→proxy | `official_physics_point_pass.py` |

Single End原内核`0x4a47450`按12字节位置复制，Double End Job按24字节复制。本批不实现Raw指针重解释、Single End调度或NativeArray桥接。Pre managed与Double Start的显式值组合不等于Pre Job所有入口的数学等价证明。

## 帧准备与历史

Pre先要求collider Byte `0x10+0x20`，再检查Team `IsProcess`：必须有`0x2`，且无bit61、`0x10`、`0x800`、`0x80000`。transform索引为`colliderTransformChunk.start - colliderChunk.start + colliderIndex`；center仍按原global collider取。

**center先Single旋转，再Single逐分量缩放**，最后拓宽并加Double transformPosition，不可改成通常的先缩放TRS。先写当前frame字段；Team `0x4`或collider `0x40` reset优先，将frame复制到oldFrame/now/old三套历史，仅清collider `0x40`。非reset先按Team `0x40000`变换三套Double位置及Y/Z符号rotation，再按`0x400`绕oldComponentWorldPosition处理component shift。未用舞台root、零矩阵或默认中心代替原输入。

Pre range保留原global槽、不压缩重排，无独立Team0跳过。全部返回值仅是私有值，不发布Unity数组。

## 子步生产的精度与WorkData

Double Start使用Single插值比例拓宽后的Double lerp，两次rotation均用原Slerp。第一结果归一化写now；第二结果归一化写old，但**old形状旋转及inverseOldRotation用第二次原始结果**。插值/惯性比例不钳制。

WorkData为184字节：AABB@0、radii@48、oldPos@56、nextPos@104、inverseOldRot@152、rot@168。先清168字节再填rotation；未知shape也发布零几何加已计算rotation，不保留旧WorkData。

| 形状 | 原结构与精度边界 |
| --- | --- |
| Sphere1 | Single `size.x*abs(scale.x)`半径；Double Job中心、min/max和扩张均Double。Single入口先Single min/max再拓宽扩张 |
| Capsule2–7 | 2/5=X、3/6=Y、4/7=Z；2–4居中、5–7单端。尺寸、轴符号、`0x80`反向、段长度及offset旋转仍Single。Double Job只拓宽旋转后的offset，再与Double中心加减，AABB全Double；Single入口整端点及半径扩张先Single再拓宽 |
| Plane8 | normalized now rotation旋转Single Y轴符号；normal拓宽填oldPos.c0，now中心填nextPos.c0。反向bit不读；其余geometry/radii为零 |

没有擅加非负半径钳制，只保留原段长度非正归零。Slerp near-dot `chgsign`保留负零sign bit。Python libm是有限域数学参照，非原CRT/Burst逐bit证明。

Double Start整批按list原序访问，global collider后读取signed Int16 Team ID，无`IsProcess`或Team0额外门禁；重复ID保留前一访问反馈。End按稀疏list复制now→old，无门禁。Post独立检查Team `IsProcess`及`0x20`，复制**完整frame目标**到oldFrame，不用子步now替代。

## Point整批与宿主依赖

Point range读取signed `*lengthPtr`一次，串行0..count-1。slot→global particle→signed Team；属性/depth用`proxyCommonChunk.start - particleChunk.start + particle`，位置/摩擦/normal用particle索引。重复粒子不去重，后一次读取先前写回。

原Team.colliderCount**等于零**先返回，之后mode非1返回，再检查valid、NoCollision及fixed/Spring门禁。radius来自`ClothParameters.radiusCurveData@92`，不是collision参数的虚构radius。collision子结构@612，mode子偏移0、limitDistance子偏移12。Job的14字段与kernel参数不同序，friction/normal/velocity/base按真实来源绑定。

宿主三路是普通deferred schedule、cross-frame Schedule2和跨线程Animator的`CrossFrameComplete→UnsafeDo→zero handle`。**空算术range不等于保留输入handle**，宿主仍选调度或完成依赖。普通Point Job `Execute(index)@0x59f5ae0`是另一独立body，尚未证明与managed消费者相同。

## 检查与冻结证据

frame53、Single Start48、Double Job65、Point pass49，共215专项通过。全`Tools/tests`为3349 passed、114 subtests passed、3历史skip、2历史Pillow弃用warning。47个参考模块共4354语句/998分支，覆盖率100%；Ruff、格式、Pyright、compileall及临时Python环境依赖审计通过。测试覆盖率不证明原运行时等价或Unity集成。

11组配置/164 saved点克隆、7个受保护runtime文件、9557条main index内容及flags保持；main HEAD/index及舞台SHA未变。原DLL/metadata只读静态解析，没有加载、执行或修改原游戏。

证据目录：`D:/EndfieldTechLib/notes/official-physics-collider-production-20261010-01/`。最终文件SHA在本目录`verification.json`：

- `prove_frame.py` / `frame-source-proof-02.json`：11完整span、48关键点及字段/签名；更新01版中已被后续证据取代的“bridge未知”说明。
- `audit_work_formulas.py` / `work-formula-evidence-v5.json`：完整Single入口及helpers、Double offset/bounds。旧first-return叶函数初稿已由完整CFG证据取代。
- `double-job-independent-review.md`：Double shape独立复核及所审公共文件SHA。
- `review_collider_job_certificate.py` / `collider-job-route-certificate-v1.json`：69 source span、72关键点、9 owner字段/签名，Double Job及Raw指针/host证据。67 span有PE边界；2份End直线leaf单独标明有限解码边界，不冒充RuntimeFunction。`verify_route_certificate.py`重新读取原字节后逐项比对通过。
- `audit_point_dispatch.py` / `point-dispatch-audit-05/audit.json`：20目标、9签名、27关键点，参数绑定/宿主分支；fallback拓扑差异未冒充逐字节一致。
- `run_checks.py 02` / `checks-02.json`、JUnit、coverage、pip-audit：最终自动检查。
- `check_input_guards.py` / `guard-01.json`：配置、runtime及main index保护。

证据冻结具体版本事实，未证明的class、入口和Burst保留未知，不因“封存”抹掉缺口。

## 下一交付点

先核对普通Point Job独立数学与shape helpers，然后补剩余约束实际消费及list/proxy/Team生产。原外部CAB的25个组件仍只有23份capsule-layout、2份size-only指纹，不能据此断言原class或猜Sphere/Plane。allocator/bulk发布、全部约束和唯一writer依赖未闭合。

完整链形成后再制作可回退C#候选后端，实际切换并测MMD/解包动作、reset/暂停/seek与碰撞输出。本批已通的是**显式值Pre→Double Start→End→Post→下一帧，以及WorkData→Point消费者**，不是角色的原Jobs/Burst/Unity实机闭环。详见[剩余门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)。
