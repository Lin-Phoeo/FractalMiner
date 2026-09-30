# 实际工程接管审计与首轮修复（2026-09-30）

> 后续增量及用户最新方向见 `CODEX-HANDOFF-2026-09-30-live-skin-and-motion.md`。不要逐像素对照；下文颜色/同表面比较建议作为历史记录保留，不再作为开发主线。官方坐标/骨骼根输入错误已修，动态根已接解包动作和MMD入口；仍需按官方结构继续审其他材质/光照/后处理与动作语义。

以工程、捕获和本轮运行结果为准，旧交接只是线索。本轮是关键输入修复及回归验证，不是官方渲染、目标端 MMD 或全片出片已经闭合。

## 1. 工作入口与当前可看产物

- 工程：`A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner`；Unity2022.3.30f1 / URP14。
- 核心渲染：`Assets/EndfieldShaderPack/EndfieldCharacterLit.shader` + 四族 `EndfieldOfficial*.hlsl`。
- 最新重复验证图：`Validation/takeover-render-final-20260930-02/pose-applied-lit-post.png`；第一次最终图在final-20260930-01。
- 修复前：`Validation/takeover-render-before-20260930-01/pose-applied-lit-post.png`。
- 仅修顶点中间图：`Validation/takeover-render-vertex-20260930-01/pose-applied-lit-post.png`。
- 可编辑场景：`Assets/Scenes/Typhoeus_Showcase.unity` / `Typhoeus_MMD_Stage.unity`。舞台已有莱万汀参考背景，不应按“没有舞台”再复制一遍。
- `Typhoeus_OfficialFrame_Recovered.unity` 仅为诊断基线。本轮没有保存它，没有把捕获姿态当最终目标。

最新图仍有脸部/眼周异常、白色附属物、局部质感不一致，不是最终成片。

## 2. 真正定位并修复的问题

### V2 顶点导入器原先实际上没有导入

实际 `Validation/vertex-input-export-20260929-183059/manifest.json` 的56个input都没有location；位置保存在signature。旧代码按不存在的 `inputMeta["location"]` 筛选，全跳过却报告6/6成功；另有compWidth/compByteWidth不匹配。

重写 `Assets/EndfieldShaderPack/Editor/ImportCapturedVertexAttrsV2.cs`：按signature location及非builtin语义取输入；校验SHA256、格式、长度、有限值及目录边界；六个mesh的位置、UV、索引拓扑全部匹配后才写。六个mesh逐顶点位置/UV最大误差均为0。
压缩流同时解码normal和tangent：官方skin b138 VS306–343包含切线方向和bit31 handedness，不能误用占位tangent流。非压缩cloth_01保持原始float帧，其捕获最大|N·T|=0.196000278，不能为了“正交门禁”擅自改官方输入。不猜COLOR/UV1。
六个mesh共52,820顶点，其中压缩29,062。ValidateAll只读；ImportAll先全部准备、备份再写。

| 部件 | 旧法线最大角误差（度） | 旧切线最大角误差（度） |
| --- | ---: | ---: |
| iris | 0 | 1.3185 |
| body | 178.4057 | 4.4264 |
| cloth_01 | 0.4614 | 179.3909 |
| cloth_02 | 178.9797 | 162.5829 |
| face | 176.2157 | 47.2543 |
| hair | 178.9441 | 166.6375 |

应用后另一次Unity batch重读资产，六个mesh法线/切线最大角误差均为0。证据：`Logs/codex-takeover-vertex-before-20260930-03.json`、`codex-takeover-vertex-applied-20260930-01.json`、`codex-takeover-vertex-after-20260930-01.json`。
备份：`Logs/vertex-import-v2-backup-20260930-064947-5577627/`（六个mesh+meta）。游戏mesh不提交Git，需本地捕获和工具重建。

### Ramp / Highlight 被错误地按sRGB解码

运行快照Ramp为R8G8B8A8_SRGB，Highlight为RGBA_DXT1_SRGB；官方b138及本轮213捕获明确为RGBA8_UNORM/BC7_UNORM。
修复 `EndfieldMaterialImporter.cs` 数据槽分类，新增窄入口 `EndfieldShaderPack.EndfieldMaterialImporter.RepairCapturedSkinDataTextureImports`：只修 `T_actor_common_face_01_RD.png` / `T_actor_common_face_01_hl_M.png` importer为Default、线性、非透明预处理、无新增压缩。
运行时检查IsSRGBFormat=false，实际RGBA8_UNorm / RGB8_UNorm。没有改BaseMap、Emotion、SSS LUT的sRGB语义。
备份 `Logs/skin-data-texture-backup-20260930-065217-3494149/`。第一版备份误调用仅接受Assets路径的Full()，Unity清掉了Assets下孤立meta；已修正到Logs，原meta从本轮不变的Git index恢复，工作资产和GUID保留。

### 可留存的真实A/B与HDR证据

`EndfieldPoseApplyValidation.cs` 新增 `ENDFIELD_POSE_OUTPUT`，显式指定的非空目录拒绝覆盖，默认旧行为保持兼容。每阶段分别输出，`ENDFIELD_SKIN_DIAGNOSTICS`同步对应HDR目录。
补齐原有EndfieldSkinInputDiagnostics的真实readback断言：2×2 RGBAFloat逐通道(.18,2,-.25,.5)读回，误差≤1e-5、不能非有限，确认既不剪HDR也不额外gamma。最新重复渲染已实际通过。
新 `Tools/capture_part_hdr.py` 只离线重放已有RDC，以已审SPIR-V SHA256+索引数+目标资源识别body/face/hair forward draw，歧义就失败，不按跨帧event号猜部件。
已导出 `Validation/Captures/new-rdcs/213-parts-codex-01/`，frame5933，body932 / face1006 / hair1021，最终sceneColor1081，2560×1600 R11G11B10。它不是frame6411。
新 `Tools/summarize_part_hdr.py` 保留线性HDR>1，以forward changed-pixel mask及Unity renderer label诊断；拒绝空/非有限样本、长度及编码不符。
changed mask表示本draw改变过的像素，不是完整几何覆盖或其他姿态的同一表面。报告明确 `diagnostic_only` / `same_surface_verified=false`，禁止拟合统一曝光或宣布颜色门禁通过。

各自mask下诊断均值（非配准色差）：body修复前RGB约(0.573,0.298,0.257)，最终(0.822,0.540,0.476)，官方213约(0.885,0.595,0.516)。face当前约(0.631,0.405,0.345)，官方213约(1.315,0.933,0.784)。不同mask/姿态不能直接把这个比值当缺一个乘2。

### MMD测试纠偏，不假称目标端已解决

一条Python测试仍要求旧CCD字符串。更新为radian限幅、在Unity AngleAxis边界转度的源码契约；在 `MmdFormatRegressionValidation.cs` 新增ZXY/XYZ/YZX×X正负方向六个真实数值案例，0.6rad输入钳到±0.2rad后检查Quaternion。Unity batch PASS。没有为测试修改MMD runtime，没有把格式测试绿当跳舞通过。

## 3. 本轮实测与边界

- 初始正确pytest环境：159 passed / 1 failed / 3 skipped；失败是过时IK源码测试。
- 最新：172 passed / 3 skipped，两条Pillow弃用警告。源码契约测试不等同数值证明。
- Unity编译、三次渲染、只读验证/实际导入、skin data importer、MMD格式回归均exit0。日志在 `Logs/codex-takeover-*`。
- `EndfieldSkinShadingValidation.RunNumerical` 21个synthetic GPU/CPU cases PASS；合成纹理/方向不证明真实模型所有输入一致。
- 没有重跑所有历史Bloom/shadow/oracle/MMD全帧验收，不能背书旧数字。
- 冻结CapturedBloom/CapturedPost/CapturePipelineValidation没有改。
- 直接隐藏窗口运行Unity batch成功，无需改计划任务/系统配置。
- 没有启动或注入游戏、没有修改游戏保护，只离线重放已有捕获。
- 隔离Python测试环境pip-audit：No known vulnerabilities found；并非对整个技术库第三方资产/所有Unity包的安全背书。
- 旧工作区还有未提交的CharacterLit诊断/描边改动（相对记录分支约82行），本轮没有擅自撤销或混入提交。其描边使用Unity主光与简化SH，不能直接标注为官方b273已验证；后续需专门核对。记录分支不是整个本地资产/所有历史未提交文件的可运行快照。

## 4. 旧交接与扩展方案的更正

1. “导入器6/6已闭合”被真实schema和资产数据推翻；本轮修后才有资产重读证据。
2. “只剩统一亮度增益”不成立；部件输入曾错，face/body残差不统一。
3. “公式GPU测试通过=皮肤完成”不成立，未包含真实材质、插值输入、空间变换。
4. “烟测未加载Camera.vmd”过时：EndfieldVmdBatchRender已有load/apply相机，需运行验收，不重复实现。
5. 现役仍是自研MMD源求值器，UMT baked-FK未成为播放输入。现有mmd-anim报告max约64.3mm，不能称双参照均闭合。
6. KeepFeetAboveBindFloor只是按脚骨最低点抬root，不是防滑/支撑脚锁定/足底求解。Animation Rigging包已安装，但不等于RigBuilder/TwoBoneIK已经接入。
7. 当前表情驱动blendshape，官方脸是骨骼表情、0 blendshape；需明确脸骨映射。
8. 已有Laevatain floor/ring/venue舞台，先验收场景与出处，MIT来源保留notice。
9. SPCRJointDynamics只在技术库，不在运行链。离线出片要fixed-step、连续warm-up、reset、顺序求值，不能用墙钟deltaTime。
10. 许可逐仓核实：Ruri.ShaderDecompiler是AGPL而非目录册所称MIT；Endfield-Renderer不能默认MIT/GPL。现有MMD派生文件有AGPL标记，替换一个求值器不会解除其他派生义务。
11. Tianshi是官网风格演示，不是已经证明可替代官方角色/粒子管线的逆向实现；Babylon本地仅README，不能当可用Unity组件。

## 5. 下一步正确方向

**渲染优先**：保留输入修复，先做真实face样本的UV/baseAlpha/SDF RGBA/N/T/V/L/objectBasis/shadow/材质常量对照。逐像素颜色验收先证明同一表面（UV/depth/triangle），不只粗part family相交。核对官方贴图实际内容、压缩/采样器/LOD、SDF head basis和阴影输入，先修输入再改已过合成测试的公式。禁止全局增益遮盖问题。然后分部件hair/cloth/eye，描边、刘海投脸、透明/white prop、地面影及湿润。6411姿态是诊断，不是目标。

**MMD分离验收**：先重跑UMT+mmd-anim全帧并解释残差；2022路线优先尝试可追溯UMT baked-FK缓存作为源端适配输入。自研retarget保留source/target rest basis和root-space契约，以多动作全帧检验手脚、限幅、连续性，不只五帧。做支撑脚/足底接触而非整体抬升；脸骨映射；固定步长物理；VMD相机+post+bloom连续出片及重复运行一致性。

**扩展/Unity6**：先复用现有舞台，不同时换引擎、求值器、shader。2022可复现基线后再在副本迁Unity6。可分给其他工具的低风险包：只读license清单、按固定命令跑测试交原日志/hash、舞台GUID/材质缺失引用清点、全帧残差分类；不自行调曝光、门限或删除资产。

## 6. 重复运行

PowerShell，每次只跑一个编辑器进程。使用新目录：

```powershell
$env:ENDFIELD_POSE_OUTPUT='Validation/takeover-render-NEXT'
$env:ENDFIELD_SKIN_DIAGNOSTICS='Validation/takeover-skin-NEXT'
Start-Process -FilePath 'A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe' -WindowStyle Hidden -ArgumentList '-quit -batchmode -projectPath "A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner" -executeMethod EndfieldShaderPack.EditorTools.EndfieldSkinInputDiagnostics.Run -logFile "A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Logs\takeover-NEXT.log"'
```

检查return code0及预期日志/产物，不以“进程消失”代替成功。顶点只读入口 `EndfieldShaderPack.EditorTools.ImportCapturedVertexAttrsV2.ValidateAll`，应用入口同类ImportAll，报告环境变量ENDFIELD_VERTEX_IMPORT_REPORT。

```powershell
uv run --python 3.13 --with pytest --with numpy --with pillow --no-project python -B -m pytest FractalMiner/Tools/tests -q --tb=line -p no:cacheprovider
```

Python使用独立uv依赖，不改旧EndfieldUnpacker venv。summarize_part_hdr CLI：--capture（213-parts-codex-01）、--current（HDR目录）、--labels（对应pose-applied-labels.png）、--out（新JSON）。

## 7. 保护、回退与记录

初始保护目录 `D:/EndfieldTechLib/notes/codex-takeover-20260930-01/`：main-index.bin、recovered场景、GraphicsSettings、QualitySettings。
初始index快照SHA256 `751570BC84189759783B98D06E38824920A023E277611594310F85178BD4F721`。Git只读诊断期间stat缓存使index二进制hash改变；最终对快照与正常index分别执行ls-files --stage并逐条比较，**9557条暂存条目完全一致**，不是暂存内容改变。场景SHA256仍为 `4D4D43D5E2990FF0D8B4888FF4775073DB58E3BA15EE96BCC7D07817D2881A7A`。
提交前发现远端从90b1e0c前进到e52a8f9（只增shading_diagnose.py和源码索引）；已fetch检查，以e52a8f9为父保留他人成果，不强推。
未动原大批staged，没有保存基线pose，没有按旧“垃圾清理”删除第三方/归档。
提交只进记录分支 `fix/typhoeus-render-explosion-20260917`，临时GIT_INDEX_FILE+read-tree+明确源码列表+commit-tree/update-ref CAS；不能checkout/reset/clean/add全部，不能把游戏资产/RDC或原暂存集一起提交。
mesh可用上述六份备份回退；两个贴图meta可用Logs备份回退，关闭Unity后恢复并重导入。不要回退整个工作目录。
