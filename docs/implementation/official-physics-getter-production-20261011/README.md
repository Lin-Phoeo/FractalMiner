# 官方物理输入链：身份槽接真实Unity getter与骨骼导入

2026-10-11。本单元接续[有序身份输入](../official-physics-input-production-20261011/README.md)，关闭一个明确子项：**原始身份槽→参考实例的运行时ID/世界getter→snapshot→skin位置、方向、权重、bindpose**。隔离Unity 2022.3已执行，不再只有合成getter；但采样对象是原始序列化Transform重建的参考树，**不是正在运行的游戏，也不是主舞台恢复角色**。完整proxy、Team、约束列表与官方求解器尚未接入，不能称为物理完成。

## 实现与边界

- `Tools/UnityPhysicsGetterProbe/OfficialPhysicsGetterProbe.cs`：只放入独立临时Unity工程的Editor目录。读取显式SHA256封印的bindings，按文件+signed Int64 PathID创建对象，恢复原父子边、局部TRS和子节点顺序。名称只是标签，不参与匹配。
- `Tools/official_physics_getter_inputs.py`：将已编译身份槽关联到实际Int32 instance ID、parent ID与getter；保留负ID，核对List.IndexOf首次匹配父级/root窗口，再复用现有snapshot/bone-import/bindpose参考。缺少getter或父级不匹配直接拒绝，不用prefab局部值、默认零或猜测的逆矩阵代替。
- `Tools/export_official_physics_getter_inputs.py`：消费bindings与getter采样文件，要求两个显式SHA256，检查逐状态完整身份覆盖与矩阵列，拒绝覆盖输出。状态各自关联，不跨采样合并实例ID。
- 两份测试验证重复render槽、忽略root、负ID/边界、父级错误、缺失记录、显式矩阵、非有限值、封印、CLI及不覆盖原文件。

官方数学仍来自已审查的[ReadTransform快照](../official-physics-snapshot-20261002/README.md)与[骨权重/bindpose导入](../official-physics-bindpose-20261002/README.md)，本轮没有替换其公式。快照scale保留`diag(inverse(worldRotationMatrix) * localToWorldMatrix)`，不是`lossyScale`；bindpose使用原世界TRS的逆再乘render localToWorld，不自动换成骨骼worldToLocal。矩阵以四个`GetColumn`保存，不转置混用。

这里验证的是有限值输入适配。null/destroyed对象的上一槽保留、原TransformAccess/NativeArray布局、异步调度和实际Burst仍不是本单元实现。

## 隔离Unity实际验证

临时工程位于`D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/unity-probe/`，没有在主工程Assets中新增采样脚本。

1. 先执行独立非均匀/负scale、父子旋转的getter检查。
2. 读取556个原始Transform，采样`serialized-rest`状态。
3. 仅移动合成外部wrapper：position=(1.25,-2,0.75)，rotation=Euler(12,35,-7)，再采样`rigid-reference-frame`。
4. 两种状态分别导入11组；每态140个skin输出、151个snapshot槽，逐组保留11个追加render。
5. 采用不调用生产函数的NumPy矩阵复算，检查共280个skin顶点、方向、scale、bindpose、one-hot权重与整体刚性变换后的render-local稳定性。

原parent为空的根挂在合成wrapper下；wrapper不是官方cloth中心。它的runtime父ID不在收集窗口内，所以索引仍为-1。各组render矩阵来自原组件所属Transform，不擅自替换成wrapper/舞台root。

坐标/矩阵合理性限值在首次独立运行前固定为3e-5。这不是逐像素对照或画面调参：最大位置差1.625e-7、bindpose差3.879e-7，matrix inverse恒等检查差1.425e-6；整体刚性变换后的位置差2.385e-7，均通过。NumPy Double参照不证明原native/Burst逐位相等或完整求解器行为。

前两次启动被隔离工程的Package Manager报错阻止，没有产生采样。按[Unity 2022.3官方命令行接口](https://docs.unity3d.com/cn/2022.3/Manual/EditorCommandLineArguments.html)在隔离工程使用`-noUpm`后编译并执行成功；没有修改主工程的Package Manager设置或重建其Library。随后实际Unity执行的两项负向测试均以exit=1退出：错误bindings封印、已存在输出；原采样哈希保持不变。

## 复现路径

采样脚本环境变量：

```text
ENDFIELD_GETTER_BINDINGS=<已核查bindings完整路径>
ENDFIELD_GETTER_BINDINGS_SHA256=<64位小写SHA256>
ENDFIELD_GETTER_OUTPUT=<尚不存在的输出路径>
```

仅对隔离工程执行：

```text
Unity.exe -batchmode -nographics -noUpm -projectPath <isolated-project>
  -executeMethod OfficialPhysicsGetterProbe.Run -logFile <fresh-log>
```

导入现有采样，在仓库根执行并使用一个未存在的输出路径：

```powershell
uv run --python 3.13 --no-project python -B Tools/export_official_physics_getter_inputs.py `
  --bindings "D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/official-physics-bindings-03.json" `
  --bindings-sha256 8dad33d1dcbeee882233bb8803b7141b3d2c3817aeed23a619f5c0eeb8fbe3c8 `
  --getter-capture "D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/unity-getters-03.json" `
  --getter-sha256 0d99b53ebf1c7180e007705629eb9c27a66a853156de443b4f3a4ca4837be783 `
  --output "D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/eleven-imports-02.json"
```

脚本不启动/读取游戏进程，只读bindings并采样自己创建的Unity对象。原DLL/metadata仅作为静态字节核查来源，从未执行或改写。

## 本轮验收与留存

TDD先观察缺少两模块的RED再实现。最终45项专项、两模块140语句/44分支覆盖率100%；Ruff、Black检查、Pyright和compileall通过。完整回归3916 passed、114 subtests passed、3历史skip、2历史Pillow告警。临时验证工具环境48个依赖经pip-audit检查没有已知漏洞，不代表Unity整个项目已完成安全审计。

静态重新认证25个原字节/指令span及2个主要Job的metadata身份与精确函数边界。补充table仅核查既有报告封印，不伪称本轮重推全部数学语义。主代理人工审查与独立矩阵计算通过，没有本轮subagent审查，也没有native/Burst执行。

本地证据目录：`D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/`。

- `unity-getters-03.json`、`eleven-imports-01.json`：实际采样与11组两状态导入，完整原对象身份仅本地保存。
- `verify_imports.py`、`independent-import-check-01.json`：独立矩阵/身份复核。
- `verify_probe_rejection.py`、`probe-rejection-01.json`：实际Unity封印/覆盖拒绝检查。
- `certify_sources.py`、`source-certificate-01.json`：原source、参考实现及字节/指令封印。
- `run_checks.py`、`checks-02.json`、`green-02.xml`、`coverage-02.json`、`full-suite-01.xml`、`pip-audit-01.json`：最终检查记录。`checks-01`是测试风格检查失败的历史记录，已机械修正并完整重跑，不覆盖旧记录。
- 原输入guard25/26及提交后27位于collider-production证据目录，核对原164个saved点、7个保护运行文件、主HEAD/index与舞台未变。

公开库仅保存通用采样脚本、适配器、合成测试、说明和哈希清单，不发布完整游戏资产/身份记录、原DLL/metadata、原全文反汇编或Unity日志。

## 下一步

1. 在当前参考输入上执行原有效saved-selection的空间匹配，特别是长马尾14个skin与38个保存点，不能逐槽复制。接normal-axis/default fill与proxy构造。
2. 补齐topology、constraint work-list、Team/骨骼/碰撞体的真实发布和生命周期；每条启用分支必须具备消费者，缺失应拒绝，不静默no-op。
3. 建立**恢复角色实例**的可核查身份映射，再对动画状态采样；本轮参考树不能冒充恢复角色的动态getter。
4. 输入及调度闭合后接可回退C#候选后端，才进行MMD/解包动作、reset/seek/暂停恢复与单writer动态验收。

八个总体交付门禁仍未整体闭合。本轮没有新的可见舞台物理效果，保留现有渲染、湿身、阴影与预览物理。
