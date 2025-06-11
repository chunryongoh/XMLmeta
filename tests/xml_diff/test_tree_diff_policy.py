import lxml.etree as ET
from src.xml_diff.tree_diff import XMLTreeDiffer, XMLDiffResult
import os
import shutil
import tempfile

def test_experiment_diff_with_policy():
    # 실제 샘플 파일 경로
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    xml1_path = os.path.join(base_dir, 'real_examples', 'kobic-0352.experiment.xml')
    xml2_path = os.path.join(base_dir, 'real_examples', 'kobic-0352.experiment.xml')  # 동일 파일로 diff 없음
    differ = XMLTreeDiffer()
    result = differ.diff(xml1_path, xml2_path)
    # diff 없음이 정상
    assert len(result.diffs) == 0

    # 일부 필드만 변경된 샘플을 직접 Element로 만들어 diff + 정책 적용 검증
    xml1 = ET.fromstring('<EXPERIMENT><TITLE>AAA</TITLE></EXPERIMENT>')
    xml2 = ET.fromstring('<EXPERIMENT><TITLE>BBB</TITLE></EXPERIMENT>')
    policy_path = os.path.join(base_dir, 'policies', 'experiment.json')
    class TestableXMLTreeDiffer(XMLTreeDiffer):
        def diff_elements(self, elem1, elem2) -> XMLDiffResult:
            result = XMLDiffResult()
            self._compare_nodes(elem1, elem2, '/EXPERIMENT', result)
            self._apply_policy(result, elem1)
            return result
    differ2 = TestableXMLTreeDiffer(policy_path=policy_path)
    result2 = differ2.diff_elements(xml1, xml2)
    # TITLE 변경은 정책상 warn이어야 함
    assert any(d['type'] == 'modify_text' and d['policy'] == 'warn' for d in result2.diffs)

def test_policy_types_all():
    # error: 필수 필드 변경
    xml1 = ET.fromstring('<EXPERIMENT><IDENTIFIERS><PRIMARY_ID>AAA</PRIMARY_ID></IDENTIFIERS></EXPERIMENT>')
    xml2 = ET.fromstring('<EXPERIMENT><IDENTIFIERS><PRIMARY_ID>BBB</PRIMARY_ID></IDENTIFIERS></EXPERIMENT>')
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    policy_path = os.path.join(base_dir, 'policies', 'experiment.json')
    class TestableXMLTreeDiffer(XMLTreeDiffer):
        def diff_elements(self, elem1, elem2) -> XMLDiffResult:
            result = XMLDiffResult()
            self._compare_nodes(elem1, elem2, '/EXPERIMENT', result)
            self._apply_policy(result, elem1)
            return result
    differ = TestableXMLTreeDiffer(policy_path=policy_path)
    result = differ.diff_elements(xml1, xml2)
    assert any(d['policy'] == 'error' for d in result.diffs)

    # allow: 허용 필드 변경
    xml1 = ET.fromstring('<EXPERIMENT><DESIGN><DESIGN_DESCRIPTION>foo</DESIGN_DESCRIPTION></DESIGN></EXPERIMENT>')
    xml2 = ET.fromstring('<EXPERIMENT><DESIGN><DESIGN_DESCRIPTION>bar</DESIGN_DESCRIPTION></DESIGN></EXPERIMENT>')
    result = differ.diff_elements(xml1, xml2)
    assert any(d['policy'] == 'allow' for d in result.diffs)

    # warn: 경고 필드 변경
    xml1 = ET.fromstring('<EXPERIMENT><TITLE>foo</TITLE></EXPERIMENT>')
    xml2 = ET.fromstring('<EXPERIMENT><TITLE>bar</TITLE></EXPERIMENT>')
    result = differ.diff_elements(xml1, xml2)
    assert any(d['policy'] == 'warn' for d in result.diffs)

    # 정책 미정의: 정책 json에 없는 필드 변경
    xml1 = ET.fromstring('<EXPERIMENT><UNDEFINED>foo</UNDEFINED></EXPERIMENT>')
    xml2 = ET.fromstring('<EXPERIMENT><UNDEFINED>bar</UNDEFINED></EXPERIMENT>')
    result = differ.diff_elements(xml1, xml2)
    assert any(d['policy'] == 'warn' and d['policy_note'] == '정책 미정의' for d in result.diffs)

def test_real_example_diff_with_policy_autoload():
    # 원본 파일 복사 및 TITLE만 변경한 임시 파일 생성
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    src_path = os.path.join(base_dir, 'real_examples', 'kobic-0352.experiment.xml')
    with open(src_path, 'r', encoding='utf-8') as f:
        xml_str = f.read()
    # TITLE만 변경
    xml_str2 = xml_str.replace('Illumina paired-end Sequencing of KAS22024554 (KAE22252420)', 'DIFFED TITLE')
    with tempfile.NamedTemporaryFile('w+', delete=False, suffix='.xml') as tmp:
        tmp.write(xml_str2)
        tmp_path = tmp.name
    differ = XMLTreeDiffer()  # 정책 자동 선택
    result = differ.diff(src_path, tmp_path)
    print('==== DIFF RESULT ===')
    for d in result.diffs:
        print(d)
    print('==== END DIFF RESULT ===')
    # TITLE diff가 warn으로 태깅되는지 확인
    assert any(d['policy'] == 'warn' and 'TITLE' in d['xpath'] for d in result.diffs)
    os.remove(tmp_path) 