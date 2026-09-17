# 提弗洛斯：首次真实 Vulkan 捕获的离线回放与分析

日期：2026-09-17。输入由用户自行提供：`tifuluosi.zip` 与配套 `tifuluosi.zip.xml`。
用户报告使用 RenderDuck `_v1.4` 抓取。本轮助手没有运行该定制程序、启动/注入游戏或修改保护组件。

## 已验证结果

- ZIP：1,089,221,576 字节，8,007 个条目，条目未压缩总计 2,587,118,230 字节。
  其中 8,006 个为编号资源数据，另有 `thumb.jpg`；不是已经按材质分类好的模型/纹理包。
- XML：59,356,400 字节，driver=`Vulkan`。捕获序号为 7161。
- 官方 RenderDoc 1.46 成功离线转换 XML+ZIP，得到 1,068,553,695 字节的 RDC。
- 官方 RenderDoc 回放控制器成功打开，执行至帧末事件 1670；有 278 次绘制、44 次计算调度、
  4,057 个纹理资源、39 个 buffer。这些纹理是帧中记录的资源集合，不都是当前角色贴图。
- 遍历全部 322 次绘制/调度，导出 VS/PS/CS 的只读资源绑定及反射常量，取得 188 个唯一
  Shader 模块。采样器、读写资源绑定及完整深度/模板/混合状态尚需扩充采集。
- 帧末呈现目标 `ResourceId::769` 已另行导出为 2560×1600 PNG；人工查看与捕获缩略图的
  内容相符。它是官方帧的离线回放，不是我们的 Unity 输出，也没有进行逐像素误差验收。

本帧是提弗洛斯 3D 展示页面的**背面近景**。适合先研究头发、衣料、轮廓；
正面眼睛、面部与最初角色详情页正面参考仍需要对应捕获。截图有账号信息，仅保留本地。

## 数据保全与隐私

原始 ZIP/XML 未改写。转换帧、资源、Shader、常量和截图全部存放于已被 Git 忽略的：
`Validation/Captures/tifuluosi-20260917/`。

- 有效清单：`replay-inventory-01/inventory.json`。
- 有效完整分析：`replay-details-03/draw-details.json`，以及同目录 SPIR-V/反汇编文件。
- 有效预览：`replay-preview-01/replayed-present.png`。
- `replay-details-01` 是发现有符号整数枚举差异的失败运行；`replay-details-02` 是旧 JSON
  编码过慢而中止的运行。两者不作为完整结果使用，不能把部分文件当成成功报告。
- 必须同时检查 `complete.json` 和实际输出；qrenderdoc 的进程退出码不能替代脚本完成标志。

原始文件 SHA-256（便于验证本地输入没有变化）：

```text
ZIP  78E6EA12C2D95656511069489239379EFBC12B746626E5D965F6080F31053AF0
XML  B22423800BD245B51BD0B726ADB80740021BDE9F9F18904075F6354214F739C1
```

## 角色绘制调用定位

这帧没有可读的角色 Pass 标签。以下使用与本地解包网格相同的索引数筛选候选，
并结合 Shader、目标缓冲和材质资源继续核验；单凭索引数并不证明网格身份。

| 本地网格候选 | 索引数 | 捕获事件示例 | 直接观察 |
| --- | ---: | --- | --- |
| cloth_01 | 94,791 | 327、475、596、729、980、1042 | 有仅深度输出和多颜色输出的不同绘制 |
| hair_01 | 54,816 | 367、515、636、647、769、1020、1068、1127、1132 | 同一计数在多个阶段出现，使用不同 Shader/目标 |
| cloth_02 | 36,852 | 342、490、611 | 与本地计数一致，待完成全部绘制用途分类 |

重要锚点：事件 1020 的头发着色候选，Pixel Shader 为 `ResourceId::22257`，
绑定 18 个只读资源与 8 个常量块。事件 980 的衣料着色候选 Pixel Shader 为
`ResourceId::22255`，绑定 19 个只读资源。

目前不能把所有重复绘制简单称为「描边」或「阴影」。需进一步检查深度/模板/混合状态、
纹理内容和 shader 的实际运算，再决定如何拆分 URP pass。

## 找回全局参数的候选语义

本帧 Shader 符号被剥离，反射字段名是编号。对事件 1020 的 SPIR-V 使用官方发行包内
SPIRV-Cross 的 `--reflect` 得到字节偏移，再与本地社区 1.5.3 dump 的
`characternpr_hair/Sub0_Pass0_Fragment_b100.hlsl` 比较：

| 缓冲候选语义 | set / binding | 大小 | 字段数量与字节偏移 |
| --- | --- | ---: | --- |
| TransformVariables | 0 / 12 | 1,312 | 22/22 对应 |
| ShaderVariablesGlobal | 0 / 16 | 3,200 | 139/139 对应 |
| LightDataBuffer | 0 / 14 | 32,864 | 7/7 对应 |

这些是**参考布局支持的语义映射**，不是原始捕获自带的可读名称，也不能证明整个
参考 Shader 变体与本帧相同。例如参考文件的材质 binding 为 2，而本帧为 0，不能盲目照搬。

部分实测值（以下为便于阅读的近似数，完整精度在本地 JSON）：

- `_ScreenSize`：2560×1600。
- `_ExposureWithMiscParams`：`(1, 1, 1.6, 0.100001)`；不是四个分量都代表曝光。
- `_CharacterParams0`：`(1, 1, 0.65, 0.9)`。
- `_CharacterParams1`：`(0, 1, 0, 1)`。
- `_CharacterParams11`：`(0.1763192, 0.5299193, 0.8295162, -0.1)`。
- `_CharacterParams12`：`(1, 1, 1, 0)`。

不要直接把相机世界坐标复制到当前 Unity 原点场景；还需对应模型矩阵、坐标系与矩阵存储约定。
不要把极小浮点数认作无用数据：部分参数可能以 `asuint` 解释位模式。原 ZIP/RDC 保留原始
buffer 才是位级权威来源，反射 JSON 不宣称保留 NaN payload 等所有位信息。

## 工具与验证

新增 `Tools/capture_replay_inventory.py`，仅操作已存在的离线 RDC：

1. 环境变量 `ENDFIELD_CAPTURE_PATH` 指定 RDC，`ENDFIELD_CAPTURE_OUTPUT` 指定空输出目录。
2. 可选 `ENDFIELD_CAPTURE_DETAILS=1` 导出绘制、常量与实际 Shader；默认不全量导出贴图。
3. 可选 `ENDFIELD_CAPTURE_PREVIEW=1` 导出最后一次 Present 的 PNG。
4. 使用官方 qrenderdoc 的 `--python` 参数运行脚本。脚本通过退出异常阻止进入主 UI。
5. 输出目录非空时拒绝覆盖；所有权限制为本次回放控制器，退出时释放控制器和捕获句柄。

修正了旧分析脚本中的潜在语义错误：RenderDoc 的常量/资源查询使用**反射索引**，
不能把 Vulkan `fixedBindNumber` 当作列表下标。测试专门覆盖了 index=0、binding=17 的情况。
参考：[官方 descriptor 索引说明](https://github.com/baldurk/renderdoc/blob/v1.46/docs/python_api/in_depth/descriptors_bindings.rst)。

验证：先失败测试再实现；26 项单元/模拟集成测试通过，标准库 trace 测得工具代码行覆盖率
97%；Python 语法检查、真实帧回放与 PNG 视觉检查通过。
没有新增第三方 Python 依赖。环境未安装 `pip_audit`，调用后报告模块缺失，故没有声称依赖漏洞
审计通过，也没有为此更改现有解包环境。

## 下一阶段

以这些事件为锚点，核对原贴图、材质常量、深度/模板/混合状态与各阶段输出，建立可验证的
角色光照和描边实现。先对齐这一帧，再用正面及转角捕获检查泛化。本轮未修改 Unity Shader，
不会将离线回放官方帧的成功误报成 Unity 工程已经达到官方效果。
