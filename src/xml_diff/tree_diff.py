"""
트리 기반 XML diff 엔진 (초안)
- robust한 구조 비교, 속성/텍스트/순서/네임스페이스 지원
- 대용량 파일 효율성, 정책적 diff 구분, 확장성 고려
"""
import lxml.etree as ET
from typing import List, Dict, Any, Optional
import json
import os
import re

class XMLDiffResult:
    """
    XML diff 결과를 저장하는 데이터 구조
    - 각 변경점: xpath, 변경 유형, 이전 값, 새 값, 속성 차이, 정책 허용 여부 등
    """
    def __init__(self):
        self.diffs: List[Dict[str, Any]] = []

    def add(self, xpath: str, diff_type: str, old: Any, new: Any, attrs: Optional[Dict]=None, policy: Optional[str]=None):
        self.diffs.append({
            'xpath': xpath,
            'type': diff_type,  # 'add', 'delete', 'modify', 'move', ...
            'old': old,
            'new': new,
            'attrs': attrs,
            'policy': policy
        })

class XMLTreeDiffer:
    """
    트리 기반 XML diff 엔진
    - 노드 구조, 속성, 텍스트, 순서, 네임스페이스까지 비교
    - 정책 룰셋 적용 가능
    """
    def __init__(self, policy_rules: Optional[List[Dict]]=None, policy_path: Optional[str]=None):
        self.policy_rules = policy_rules or []
        self.policy_path = policy_path

    def diff(self, xml1_path: str, xml2_path: str) -> XMLDiffResult:
        """
        두 XML 파일을 트리 구조로 파싱하여 차이점을 반환
        """
        tree1 = ET.parse(xml1_path)
        tree2 = ET.parse(xml2_path)
        root1 = tree1.getroot()
        root2 = tree2.getroot()
        result = XMLDiffResult()
        self._compare_nodes(root1, root2, f"/{root1.tag}", result)
        # 정책 룰셋 적용 (후처리)
        self._apply_policy(result, root1)
        return result

    def _compare_nodes(self, node1, node2, xpath: str, result: XMLDiffResult):
        """
        재귀적으로 노드, 속성, 텍스트, 자식 순서 등을 비교
        - 누락/추가/수정/순서변경 등 diff 유형 기록
        """
        def split_tag(tag):
            if tag.startswith('{'):
                ns, local = tag[1:].split('}', 1)
                return ns, local
            return None, tag
        ns1, local1 = split_tag(node1.tag)
        ns2, local2 = split_tag(node2.tag)

        if local1 != local2:
            result.add(xpath, 'modify_tag', local1, local2)
            return
        if ns1 != ns2:
            result.add(xpath, 'modify_ns', ns1, ns2)

        attrs1 = node1.attrib
        attrs2 = node2.attrib
        if attrs1 != attrs2:
            result.add(xpath, 'modify_attr', dict(attrs1), dict(attrs2))

        text1 = (node1.text or '').strip()
        text2 = (node2.text or '').strip()
        if text1 != text2:
            result.add(xpath, 'modify_text', text1, text2)

        children1 = list(node1)
        children2 = list(node2)
        if len(children1) == len(children2):
            all_equal = True
            for c1, c2 in zip(children1, children2):
                ns_c1, local_c1 = split_tag(c1.tag)
                ns_c2, local_c2 = split_tag(c2.tag)
                if (local_c1 != local_c2 or ns_c1 != ns_c2 or c1.attrib != c2.attrib or (c1.text or '').strip() != (c2.text or '').strip() or len(list(c1)) != len(list(c2))):
                    all_equal = False
                    break
            if all_equal:
                for idx, (c1, c2) in enumerate(zip(children1, children2)):
                    child_xpath = f"{xpath}/{c1.tag}[{idx+1}]"
                    self._compare_nodes(c1, c2, child_xpath, result)
                return
        len1, len2 = len(children1), len(children2)
        maxlen = max(len1, len2)
        def node_signature(n):
            ns, local = split_tag(n.tag)
            return (ns, local, tuple(sorted(n.attrib.items())), (n.text or '').strip())
        sigs1 = [node_signature(c) for c in children1]
        sigs2 = [node_signature(c) for c in children2]
        for i, sig in enumerate(sigs1):
            if sig in sigs2:
                j = sigs2.index(sig)
                if i != j:
                    move_xpath = f"{xpath}/{children1[i].tag}[{i+1}]"
                    result.add(move_xpath, 'move', i, j)
        for i in range(maxlen):
            if i >= len1:
                child_xpath = f"{xpath}/{children2[i].tag}[{i+1}]"
                result.add(child_xpath, 'add', None, ET.tostring(children2[i], encoding='unicode'))
            elif i >= len2:
                child_xpath = f"{xpath}/{children1[i].tag}[{i+1}]"
                result.add(child_xpath, 'delete', ET.tostring(children1[i], encoding='unicode'), None)
            else:
                child_xpath = f"{xpath}/{children1[i].tag}[{i+1}]"
                self._compare_nodes(children1[i], children2[i], child_xpath, result)

    def _apply_policy(self, result: XMLDiffResult, root_node=None):
        """
        정책 룰셋을 diff 결과에 적용하여 허용/경고/오류 태깅
        """
        import re
        import os
        import json
        policy_path = self.policy_path
        if not policy_path and root_node is not None:
            tag = root_node.tag.lower()
            if tag.startswith('{'):
                tag = tag.split('}', 1)[1]
            policy_path = os.path.join(os.path.dirname(__file__), f'../../policies/{tag}.json')
        if not policy_path or not os.path.exists(policy_path):
            return
        with open(policy_path, 'r', encoding='utf-8') as f:
            policies = json.load(f)
        def strip_index(xpath):
            # 인덱스 제거 + 앞뒤 공백 제거 + 소문자화
            return re.sub(r'\[\d+\]', '', xpath).strip().lower()
        for diff in result.diffs:
            diff_xpath_stripped = strip_index(diff['xpath'])
            for rule in policies:
                rule_xpath_stripped = strip_index(rule['xpath'])
                if diff_xpath_stripped == rule_xpath_stripped:
                    diff['policy'] = rule['type']
                    diff['policy_note'] = rule.get('note', '')
                    break
            else:
                diff['policy'] = 'warn'  # 기본값
                diff['policy_note'] = '정책 미정의'

class TerminalColorDiffFormatter:
    """
    diff 결과를 컬러 터미널 텍스트로 예쁘게 출력하는 Formatter
    - diff_list: XMLDiffResult.diffs (list of dict)
    - 유형(type), 정책(policy)별로 색상/스타일 지정
    """
    COLOR = {
        'add': '\033[32m',      # green
        'delete': '\033[31m',   # red
        'modify': '\033[33m',  # yellow
        'modify_tag': '\033[35m',
        'modify_attr': '\033[36m',
        'modify_text': '\033[34m',
        'move': '\033[95m',
        'reset': '\033[0m',
        'warn': '\033[43m',     # yellow bg
        'error': '\033[41m',    # red bg
        'allow': '\033[42m',    # green bg
    }
    ICON = {
        'add': '+',
        'delete': '-',
        'modify': '~',
        'modify_tag': 'T',
        'modify_attr': 'A',
        'modify_text': 't',
        'move': 'M',
    }
    def __init__(self, diff_list):
        self.diff_list = diff_list

    def format(self):
        def ansi(policy, typ):
            # 정책별 배경색
            bg = {
                'warn': '43',   # yellow bg
                'error': '41',  # red bg
                'allow': '42',  # green bg
                None: ''
            }.get(policy, '')
            # 유형별 글자색
            fg = {
                'add': '32',      # green
                'delete': '31',   # red
                'modify': '33',   # yellow
                'modify_tag': '35',
                'modify_attr': '36',
                'modify_text': '34',
                'move': '95',
                None: ''
            }.get(typ, '')
            if bg and fg:
                return f'\033[{bg};{fg}m'
            elif fg:
                return f'\033[{fg}m'
            elif bg:
                return f'\033[{bg}m'
            else:
                return ''
        lines = []
        for d in self.diff_list:
            t = d.get('type', '')
            p = d.get('policy', '')
            color = ansi(p, t)
            icon = self.ICON.get(t, '?')
            reset = self.COLOR['reset']
            line = f"{color}{icon} [{t}] {d['xpath']} | old: {repr(d['old'])} | new: {repr(d['new'])} | policy: {p}{reset}"
            if d.get('policy_note'):
                line += f"  // {d['policy_note']}"
            lines.append(line)
        return '\n'.join(lines)

class HTMLDiffFormatter:
    """
    diff 결과를 HTML 테이블로 시각화하는 Formatter
    - diff_list: XMLDiffResult.diffs (list of dict)
    - 유형(type), 정책(policy)별로 색상/아이콘/스타일 지정
    """
    COLOR = {
        'add': '#d4f8e8',      # 연초록
        'delete': '#ffd6d6',   # 연빨강
        'modify': '#fffacc',   # 연노랑
        'modify_tag': '#e0d4fd',
        'modify_attr': '#d4eafd',
        'modify_text': '#d4eafd',
        'move': '#fce4ff',
        'warn': '#fff3cd',      # 연노랑 배경
        'error': '#f8d7da',     # 연빨강 배경
        'allow': '#d4edda',     # 연녹색 배경
    }
    ICON = {
        'add': '➕',
        'delete': '➖',
        'modify': '✏️',
        'modify_tag': '🏷️',
        'modify_attr': '🔑',
        'modify_text': '📝',
        'move': '🔀',
    }
    def __init__(self, diff_list):
        self.diff_list = diff_list

    def format(self):
        html = [
            '<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;font-size:13px;">',
            '<thead><tr style="background:#eee;font-weight:bold;"><th>유형</th><th>xpath</th><th>old</th><th>new</th><th>정책</th><th>비고</th></tr></thead>',
            '<tbody>'
        ]
        for d in self.diff_list:
            t = d.get('type', '')
            p = d.get('policy', '')
            color = self.COLOR.get(t, '#fff')
            icon = self.ICON.get(t, '')
            # 정책별 강조 배경
            if p == 'warn':
                color = self.COLOR['warn']
            elif p == 'error':
                color = self.COLOR['error']
            elif p == 'allow':
                color = self.COLOR['allow']
            style = f'background:{color};'
            policy_note = d.get('policy_note', '')
            html.append(
                f'<tr style="{style}">' +
                f'<td>{icon} <b>{t}</b></td>' +
                f'<td style="font-family:monospace;">{d["xpath"]}</td>' +
                f'<td style="max-width:200px;overflow:auto;font-family:monospace;">{str(d["old"])[0:200]}</td>' +
                f'<td style="max-width:200px;overflow:auto;font-family:monospace;">{str(d["new"])[0:200]}</td>' +
                f'<td><b>{p}</b></td>' +
                f'<td>{policy_note}</td>' +
                '</tr>'
            )
        html.append('</tbody></table>')
        return '\n'.join(html) 