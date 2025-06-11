import pytest
import lxml.etree as ET
from src.xml_diff.tree_diff import XMLTreeDiffer, XMLDiffResult, HTMLDiffFormatter

# XMLTreeDiffer.diff를 Element 객체도 받을 수 있도록 임시 래퍼
class TestableXMLTreeDiffer(XMLTreeDiffer):
    def diff_elements(self, elem1, elem2) -> XMLDiffResult:
        result = XMLDiffResult()
        self._compare_nodes(elem1, elem2, '/', result)
        self._apply_policy(result)
        return result

def test_tag_diff():
    xml1 = ET.fromstring('<root><a>1</a></root>')
    xml2 = ET.fromstring('<root><b>1</b></root>')
    differ = TestableXMLTreeDiffer()
    result = differ.diff_elements(xml1, xml2)
    assert any(d['type'] == 'modify_tag' for d in result.diffs)

def test_attr_diff():
    xml1 = ET.fromstring('<root><a x="1"/></root>')
    xml2 = ET.fromstring('<root><a x="2"/></root>')
    differ = TestableXMLTreeDiffer()
    result = differ.diff_elements(xml1, xml2)
    assert any(d['type'] == 'modify_attr' for d in result.diffs)

def test_text_and_child_add_delete():
    xml1 = ET.fromstring('<root><a>foo</a></root>')
    xml2 = ET.fromstring('<root><a>bar</a><b>baz</b></root>')
    differ = TestableXMLTreeDiffer()
    result = differ.diff_elements(xml1, xml2)
    types = [d['type'] for d in result.diffs]
    assert 'modify_text' in types
    assert 'add' in types
    # 삭제 테스트
    result2 = differ.diff_elements(xml2, xml1)
    types2 = [d['type'] for d in result2.diffs]
    assert 'delete' in types2 

def test_child_order_move():
    xml1 = ET.fromstring('<root><a>1</a><b>2</b></root>')
    xml2 = ET.fromstring('<root><b>2</b><a>1</a></root>')
    differ = TestableXMLTreeDiffer()
    result = differ.diff_elements(xml1, xml2)
    types = [d['type'] for d in result.diffs]
    assert 'move' in types 

def test_namespace_diff():
    xml1 = ET.fromstring('<root xmlns="urn:ns1"><a>1</a></root>')
    xml2 = ET.fromstring('<root xmlns="urn:ns2"><a>1</a></root>')
    differ = TestableXMLTreeDiffer()
    result = differ.diff_elements(xml1, xml2)
    types = [d['type'] for d in result.diffs]
    assert 'modify_ns' in types 

def test_html_diff_formatter():
    # diff 샘플 생성
    diffs = [
        {'xpath': '/root/a[1]', 'type': 'add', 'old': None, 'new': '<a>foo</a>', 'policy': 'warn', 'policy_note': '정책 미정의'},
        {'xpath': '/root/b[1]', 'type': 'delete', 'old': '<b>bar</b>', 'new': None, 'policy': 'error', 'policy_note': '필수 필드'},
        {'xpath': '/root/c[1]', 'type': 'modify_text', 'old': 'old', 'new': 'new', 'policy': 'allow', 'policy_note': '허용'},
        {'xpath': '/root/d[1]', 'type': 'move', 'old': 1, 'new': 2, 'policy': 'warn', 'policy_note': ''},
    ]
    formatter = HTMLDiffFormatter(diffs)
    html = formatter.format()
    # 주요 HTML 요소 및 정책/유형별 컬러가 포함되는지 검증
    assert '<table' in html
    assert '정책 미정의' in html
    assert '필수 필드' in html
    assert '허용' in html
    assert 'background:#fff3cd' in html  # warn 컬러
    assert 'background:#f8d7da' in html  # error 컬러
    assert 'background:#d4edda' in html  # allow 컬러
    assert '➕' in html and '➖' in html and '📝' in html and '🔀' in html 