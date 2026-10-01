# 二次运动增量：尾部装饰链（2026-10-01）

用户确认自阴影修复可用后，继续按部位补物理。本轮只扩展**可靠加权尾链**，不改官方渲染/湿身/后处理、自阴影、MMD映射或物理公式；仍是明确标注的替代物理，不宣称逆向获得官方求解器。

## 已完成与使用

`Endfield / MMD Studio`：关闭旧预览会话后重新初始化、载入VMD。默认勾选项更新为“长发/裙摆/尾链物理（替代求解）”。长发10 + 裙摆14 + 尾链6，**30个驱动关节**。关掉可对照，拖动、倒拖、参数改变、导出和关闭恢复仍共用原入口。

本轮复用第一版已有cloth预览默认值：stiffness2.2 / drag0.28 / gravity0.03 / maxSwing24°，固定120Hz；这些不是解包官方参数，也未用官方截图拟合。没有增加性能适配/LOD或新依赖。

实物产物：`Validation/secondary-extension-20261001-03/`：

- `01-mmd-no-physics.png`、`02-mmd-physics.png`、`03-mmd-physics-wet.png`、`04-studio-preview.png`。
- `mmd-tail-physics-wet-preview.mp4`：真实Unity湿身+物理渲染，61帧，960×600，30fps，2.033333秒，无音频/AI生成；原始61帧在本机 `frames/`。
- `report.txt`：**752 checks PASS**，实际Studio预览/参数修改/导出/关闭、全动作时间线、长度/有限值/可重放、相关网格变形与无关网格保留。

同一真实VMD2秒物理OFF/ON BakeMesh：tail绑定的 `cloth_04` 最大顶点位移 **0.229393691m**，其已存在的 `vfxpart_01` 伴随网格约0.229735255m。身体、脸、眉、眼、角等无关网格位移为0。没有只转无权重helper来冒充视觉物理。

## 回源核查与范围决定

输入仍是 `_typhoea_model_data.json`，raw SHA256 `008b95e54768515b621ce0775e96f8b133b7089b1ac33da7cf9c9e3ed121d860`。实际枚举17个mesh的正权重与bind palette，不能把骨名存在当成有可靠rest。

| 部位 | 数据事实 | 本轮决策 |
| --- | --- | --- |
| `tail_M_stone_a_01..07` | 正权重、有真实bind、直接parent链；08无权重/无bind | 驱动01..06，以真实02..07为尾点；08不接 |
| 左右cuff b/c/d/e 的01..02 | 正权重、有bind；03无数据；a_01/a_02 helper也无bind | 下轮单独核祖先姿态与手臂碰撞，暂未接 |
| 六条coat的01 | 正权重、有bind；02末端缺数据 | 不猜末端长度，不硬接 |
| 左右bag / rope 的01..02 | 正权重、有bind；03缺数据 | 分组后续接入，暂未接 |
| bowknot分支 | 一些01/03/05/07/08/10/11有bind，多个末端无数据 | 需逐支确认，不把编号当连续链 |

解包avatar来源：`EndfieldUnpacker/AnimeStudio-net10/_avatar_test/assets/beyond/dynamicassets/gameplay/npc/avatartemplet/actor/data_npc_avatartemplet_typhoea.json`。本轮检查到481条骨路径、mountconfigs以及角色capsule collider（center.y0.9/radius0.4/height1.8）。**该角色碰撞体不是已确认的头发/布料碰撞配置**；所检模板没有链求解系数，不拿它冒充官方spring配置，也不据此声称整个原文件都没有配置。

尾链扩展在 `EndfieldSecondaryMotion.cs`，仍要求每条边两端正权重、直接parent、有限有效长度与单位缩放；构造失败不降级到identity/虚构端点。`EndfieldMmdStudio.cs`仅更新范围提示。渲染和MMD姿态/相机代码未变。

## 验证、纠错留存

- 01-red：先把Unity门禁改为30关节，旧实现只有24，因此如期失败；Python相应integration guard也先失败。
- 02：新尾链已有真实网格位移，新的“无关mesh不动”检查错误地只看本mesh直接palette，漏掉了**驱动祖先的加权后代**，误报cloth03。03改成检查骨的完整祖先链，仍保留同一1e-6m零变形门限；没有删除负向检查或放宽阈值。失败报告留存。
- 03：752检查通过；全约37.7秒UNFORGIVEN以120Hz求值，半秒/末帧有限与长度门禁。不是任意动作/全时间mesh碰撞认证。
- `Validation/shadow-tail-regression-20261001-01/report.txt`：尾链启用后的自阴影64检查重跑，确保不重新引入晚一帧。
- `Validation/wetness-tail-regression-20261001-01/report.txt`：湿身513检查回归。
- Python474 passed / 3历史skipped / 80subtests；2条已有Pillow弃用警告。修改的Python测试Ruff/Pyright通过；临时工具环境pip-audit无已知漏洞。C#/HLSL覆盖率未测，不把752当覆盖率。

物理复跑：`ENDFIELD_PHYSICS_OUTPUT`设全新目录、`ENDFIELD_MMD_TEST_MOTION`设本机VMD文件，Unity batch执行 `EndfieldShaderPack.EndfieldSecondaryMotionValidation.RunBatch`。不能与占用同工程的用户编辑器并行。没有保存scene / ProjectSettings / 材质资产。日志、代码前态、原暂存索引备份在 `D:/EndfieldTechLib/notes/secondary-extension-20261001-01/`。

## 接下来逐项推进

1. 袖口：核未加权helper对加权rest的继承关系；补手臂接触约束，独立门禁后才接入。
2. bag / rope / bowknot：分支绑定与主动画写入所有权，不能双重驱动。
3. coat及末端：回原始Transform/物理配置补数据；缺失时保持待办，不猜官方长度。
4. 接触与穿模：当前仍只有第一版身体球代理+摆角限制，不承诺全动作无穿模。需手/腿/裙摆面间约束。
5. 独立渲染待办：地面投影需要单独审查，当前预览里的黑色环状地面影没有由本轮解决；不要误称官方阴影全部完成。
6. 表情、脚底接触/扭转校正、解包动作入口与其他导出路径，分别验收；本次只认证Studio的尾链增量。

保持模型、官方场景、舞台、ProjectSettings、sealed研究、主HEAD与用户暂存索引；独立记录分支的父提交为 `b20d7b6`。
