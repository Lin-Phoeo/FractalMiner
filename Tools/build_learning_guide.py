"""Build the offline, dependency-free-at-reading-time Chinese learning handbook.

Build only: uvx --with Markdown==3.8.2 python Tools/build_learning_guide.py
The generated HTML contains no remote scripts/fonts/styles and no AI integration.
"""
from html import escape
from pathlib import Path
import re
import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'learning'
CHAPTERS = [
    ('README.md', '总图谱与阅读顺序'),
    ('01-foundations-and-extraction.md', '01 基础与解包'),
    ('02-mesh-material-reconstruction.md', '02 模型与材质'),
    ('03-capture-shader-laboratory.md', '03 截帧与Shader'),
    ('04-pipeline-and-acceptance.md', '04 管线与官方验收'),
    ('05-independent-workbook.md', '05 独立续作工作台'),
]


def build():
    sections = []
    for number, (name, _) in enumerate(CHAPTERS):
        text = (DOCS / name).read_text(encoding='utf-8-sig')
        prefix = 'chapter-' + str(number)
        renderer = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc'],
            extension_configs={'toc': {'slugify': lambda value, sep, p=prefix: p+'-'+slugify_unicode(value,sep)}})
        rendered = renderer.convert(text)
        # Local chapter links stay in this single document; source-file links
        # remain actual file links. Never load code or assets into the handbook.
        for index, (chapter, _) in enumerate(CHAPTERS):
            rendered = re.sub(r'href="[^"]*' + re.escape(chapter) + r'(?:#[^"]*)?"',
                              'href="#chapter-{}"'.format(index), rendered)
        rendered = re.sub(r'href="/([A-Za-z]:/[^\"]+)"', r'href="file:///\1"', rendered)
        sections.append('<section id="{}">{}</section>'.format(prefix,rendered))
    navigation = ''.join('<a href="#chapter-{}">{}</a>'.format(i,escape(title))
                         for i, (_, title) in enumerate(CHAPTERS))
    document = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'">
<title>提弗洛斯渲染还原自学手册</title>
<style>
:root{color-scheme:light dark}*{box-sizing:border-box}body{margin:0;background:#f5f3ee;color:#252b32;font:17px/1.8 "Microsoft YaHei","Noto Sans CJK SC",sans-serif}
header{max-width:1120px;margin:auto;padding:40px 28px 20px;border-bottom:2px solid #d2ba78}header p{color:#58616b}nav{max-width:1120px;margin:18px auto;padding:0 28px;display:flex;gap:12px 24px;flex-wrap:wrap}a{color:#135d85;text-underline-offset:3px;overflow-wrap:anywhere}main{max-width:1120px;margin:auto;padding:0 28px 80px}section{padding:25px 0 35px;border-bottom:1px solid #d8d8d4}h1{font-size:1.75em;line-height:1.4}h2{margin-top:36px;font-size:1.3em}h3{font-size:1.08em}p,li{max-width:88ch}pre{overflow:auto;padding:18px;border:1px solid #d8d8d4;background:#eaece8;font:14px/1.7 Consolas,"Microsoft YaHei",monospace;tab-size:4}code{font-family:Consolas,"Microsoft YaHei",monospace;font-size:.9em}table{width:100%;border-collapse:collapse;font-size:15px;display:block;overflow-x:auto}th,td{padding:10px 12px;border:1px solid #c9ceca;vertical-align:top;min-width:120px}th{background:#e5e9e3;text-align:left}blockquote{margin-left:0;padding-left:16px;border-left:3px solid #b79c4b}hr{border:0;border-top:1px solid #c9ceca}footer{max-width:1120px;margin:auto;padding:25px 28px;color:#58616b;font-size:14px}
@media(prefers-color-scheme:dark){body{background:#191e24;color:#e4e8e7}header p,footer{color:#b8c2c6}a{color:#8dcdec}pre,th{background:#252d34}section,pre,td,th{border-color:#46515a}}
@media(max-width:600px){body{font-size:16px}header,main,nav,footer{padding-left:16px;padding-right:16px}h1{font-size:1.4em}}
@media print{body{background:white;color:black;font-size:10.5pt}nav{display:none}main,header,footer{max-width:none;padding:0}section{break-before:page;border:none}section:first-child{break-before:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:8pt;background:white}table{display:table;font-size:9pt}th,td{min-width:0}a{color:black}h1,h2,h3{break-after:avoid}tr{break-inside:avoid}}
</style></head><body><header><h1>提弗洛斯渲染还原 · 独立学习手册</h1><p>从可信资产到可验证的官方画面。离线阅读，无账户、无插件、无模型服务依赖。<br>阅读顺序：理解原理 → 做最小实验 → 留下证据 → 再接完整角色。浏览器 Ctrl+F 搜索，Ctrl+P 打印。</p></header>
<nav aria-label="章节">'''+navigation+'''</nav><main>'''+''.join(sections)+'''</main><footer>源文档位于同目录的 Markdown 文件。网页资料仅为补充来源；本手册正文、代码索引与本地练习流程无需网络即可阅读。模型和捕获数据不包含在此HTML中。</footer></body></html>'''
    output = DOCS / '提弗洛斯渲染还原自学手册.html'
    output.write_text(document,encoding='utf-8')
    print('{}: {} bytes, {} chapters'.format(output,len(document.encode('utf-8')),len(CHAPTERS)))


if __name__=='__main__':
    build()
