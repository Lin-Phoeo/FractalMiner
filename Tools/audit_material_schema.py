"""Compare saved material entries against the supplied 1.5.3 ShaderLab schemas."""
import json
import re
from pathlib import Path

project = Path(__file__).resolve().parents[1]
source = project / '_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr'
current = (project / 'Assets/EndfieldShaderPack/EndfieldCharacterLit.shader').read_text(encoding='utf-8').split('SubShader')[0]
current_names = set(re.findall(r'\b(_\w+)\s*\(', current))
families = {
    4484747192473637154: 'characternpr_skin',
    -1706220712117210762: 'characternpr_eye',
    -7822190029627442914: 'characternpr',
    -8095970123935614097: 'characternpr_hair',
}
for path in sorted((project / 'Assets/Typhoeus/Materials').glob('*.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    family = families.get(data['m_Shader']['m_PathID'])
    if not family:
        continue
    properties = (source / (family + '.shader')).read_text(encoding='utf-8').split('SubShader')[0]
    names = set(re.findall(r'\b(_\w+)\s*\(', properties))
    stale = {key: value for key, value in data['m_SavedProperties']['m_Floats'].items()
             if key in current_names and key not in names and value != 0}
    print(path.stem, family, 'active retained entries not in reference schema:', stale)
