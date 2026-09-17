"""Read-only diagnostics for extracted geometry, weights and bind matrices."""
import json
import math
from pathlib import Path

data = json.loads((Path(__file__).resolve().parents[1] / "Assets/Typhoeus/_typhoea_model_data.json").read_text(encoding="utf-8"))
global_bind = {}
conflicts = []
for mesh in data["meshes"]:
    vertices, indices = mesh["vertices"], mesh["indices"]
    edges = sorted(math.dist(vertices[indices[i]*3:indices[i]*3+3], vertices[indices[i+1]*3:indices[i+1]*3+3]) for i in range(0, len(indices), 3))
    determinants = []
    for b, gi in enumerate(mesh["bones"]):
        a = mesh["bindPoses"][b*16:b*16+16]
        determinants.append(a[0]*(a[5]*a[10]-a[9]*a[6])-a[4]*(a[1]*a[10]-a[9]*a[2])+a[8]*(a[1]*a[6]-a[5]*a[2]))
        if gi in global_bind:
            delta = max(abs(x-y) for x,y in zip(a,global_bind[gi]))
            if delta > 0.001:
                conflicts.append((mesh["name"], gi, delta))
        global_bind[gi] = a
    print(mesh["name"], "edge p50/p99/max", [round(edges[min(len(edges)-1, int(len(edges)*q))],4) for q in (.5,.99,1)], "determinant range", round(min(determinants),5), round(max(determinants),5))
print("Conflicting shared bind matrices:", conflicts[:20], "total", len(conflicts))
