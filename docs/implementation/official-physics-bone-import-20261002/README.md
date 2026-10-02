# 官方物理：骨骼导入的位置与方向

日期：2026-10-02。接续[根节点与长度深度](../official-physics-root-depth-20261002/README.md)。新增 `Tools/official_physics_bone_import.py`，实现骨骼导入Job的**位置、normal、tangent三个输出**，与已完成的ID映射、局部pose、深度参考完成合成数据接线。不是完整ImportBoneType、完整Import_BoneVertexJob或真实角色实时物理；没有修改Unity代码、舞台、渲染、湿身、阴影或当前预览物理。

## 已实现的原始规则

输入由调用者提供：原始顺序的世界位置/世界四元数快照、列主序float4x4 WtoL。不能直接把prefab local TRS、PPtr PathID顺序或当前恢复FBX的localRotation当成这些输入。

- position：`(((c0*x+c1*y)+c2*z)+c3).xyz`，各乘法/加法分别Single舍入，不做透视w除法。
- normal：先 `rotate(worldQuaternion,(0,1,0))`，再按原方向辅助函数转进WtoL空间。
- tangent：先 `rotate(worldQuaternion,(0,0,1))`，再走同一方向辅助函数。不是按父子位置推导，不交换两个轴，也不在此Job追加normalAxis设置。
- 方向辅助函数保留原输入长度：输入长度为0时原样返回；否则计算 `mul(WtoL,float4(v,0)).xyz`，按原分组归一化，再乘回输入长度。**不是普通矩阵乘法，也不是逆转置normal矩阵**。非均匀缩放和shear测试可区分这些替代做法。
- 四元数不额外归一化。原方向可为非单位长度，不能把辅助函数简化为“永远输出单位向量”。矩阵方向乘法保留c3*0及原Single加法分组；不改用Double dot、FMA或通用线性代数库。

缺尺寸/非有限/不能表示Single/非零方向被矩阵压成零时，adapter显式拒绝；不冒称原生异常/NaN路径完全恢复。最多65536顶点是既有proxy适配器的安全范围，不是原Job本身的Int32上限。Python sqrt/显式Single参考尚非CRT/Burst逐位oracle。

## 原始身份与算术证据

GameAssembly/metadata SHA256见verification.json，沿用封存源。只做静态读取，未加载执行原DLL、启动游戏、附加或注入进程。原始资产、完整指令及商业源码不发布GitHub。

`VirtualMesh+Import_BoneVertexJob.Execute` method371578/RVA0x34e00c0，完整unwind范围837字节，SHA256 `3742e3d30b36271a0905ae65353c5452d8c6f523cc52e4eaa17e3f563543f2db`。unboxed字段：WtoL@0、LtoW@64、transformPositions@128、transformRotations@144、transformScales@160、localPositions@176、localNormals@192、localTangents@208、boneWeights@224、skinBoneBindPoses@240。

0x34e018d变换位置；0x34e01a8–0x34e01c7构造UP、0x34e01ca quaternion rotate；0x34e01d4–0x34e0202构造FORWARD、0x34e0206 rotate；0x34e022f/0x34e0247分别补偿变换方向；0x34e026e–0x34e02db写三个输出。之后权重和bindpose属于原Job剩余部分，**本模块没有实现这些输出，也不据此宣称837字节全部已移植**。

辅助函数认证：point0x34e0ba0/245；length-preserving direction0x34e0410（真实family304+12=316）；direction-to-float4 mul0x34e0540/153；float4矩阵乘0x2cd11e0/247；quaternion rotate0x2cd4520/629复用已封存实现。scale float4的0x34e0d60/17与add float4的0x305dd60/65无unwind条目，以受限直线指令白名单到RET单独认证。dot/Single/基本旋转复用先前封存模块，未修改原模块。

ImportBoneType method371507/RVA0x3471d40 的12628字节已完整解码留存，但其根/ignore收集、属性、快照顺序及泛型调度还未恢复；“已读代码”不等于“整个导入链已实现”。MathUtility.AxisToEuler/AxisQuaternion已存原始证据，但它们处理的是方向向量，不凭函数名把normalAxis整数套进这些函数。

## 默认调整旋转的进一步确认

前一阶段确认11组normal alignment模式0。本轮认证 `Unity.Mathematics.quaternion.identity` static字段offset0，metadata usage cell VA0x18d0de238解析到其确切类型；原.cctor method441298/RVA0x4a2bc60（62字节）从RVA0xa8c2f00读取 `(0,0,0,1)`，写static字段首槽。

原ProxyNormalAdjustment的0x43f6bad读取**同一个**type usage cell，取static首槽，作为调用0x37c1d20的填充值；该辅助函数真实family共249字节，继续通过运行时函数指针调度。故可确定初始化定义与调用侧的预期值是identity，**不是零四元数**。但泛型填充Job最终写入、原游戏类型初始化时序/实际buffer内容仍未运行验证，不能据此声称整个填充链完成。normalAxis的后续方向处理也尚未闭合。

## 验证及接手点

TDD先缺模块RED，33项新测试通过：列主序、平移/w无除法、Single分组、方向长度补偿/shear、signed zero输入、退化拒绝、yaw组合、非单位四元数、不按孩子定轴、空/错误buffer及旧ID→local pose→depth接线。

全套 **1373 passed /114 subtests /3历史skip /2历史Pillow告警**；八参考模块700语句/192分支，覆盖100%；Ruff/format、Pyright 0 errors、临时环境pip-audit、新增代码密钥模式检查通过。测试和覆盖不证明原游戏动态运行一致性，Unity本轮未运行。七项runtime保护值、主HEAD/index保留。

下一批以ImportBoneType为主线恢复真实根/ignore收集和属性/顺序，追快照来源与默认填充调度；补scale/bindpose及后续方向处理之后再生成实际11组proxy输入。已有位置/方向参考可复用，不要重写为当前通用Verlet输入；完整求解、碰撞/reset、Team/step和骨骼单写入者输出仍待串联。
