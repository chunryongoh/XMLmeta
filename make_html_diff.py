from src.xml_diff.tree_diff import XMLTreeDiffer, HTMLDiffFormatter
import os

xml1 = 'xml_submitted/ddbj_bioExperiment.xml'
xml2 = 'xml_submitted/ddbj_bioExperiment.fixed.xml'
policy = 'policies/experiment.json' if os.path.exists('policies/experiment.json') else None

differ = XMLTreeDiffer(policy_path=policy)
result = differ.diff(xml1, xml2)
html = HTMLDiffFormatter(result.diffs).format()

with open('diff_result.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('diff_result.html 생성 완료! 브라우저로 열어보세요.') 