@echo off
echo %DATE% %TIME% > "A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Logs\bridge-marker.txt"
"A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe" -batchmode -projectPath "A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner" -executeMethod EndfieldShaderPack.EditorTools.EndfieldAnimRenderValidation.RunAnimRender -logFile "A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Logs\anim-render-01.log" -quit
echo %DATE% %TIME% exit=%ERRORLEVEL% >> "A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Logs\bridge-marker.txt"
