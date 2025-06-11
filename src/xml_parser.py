import os
from lxml import etree
from typing import List, Dict, Any, Optional

class XMLParser:
    def __init__(self, input_dir: str):
        self.input_dir = input_dir

    def list_xml_files(self) -> List[str]:
        return [f for f in os.listdir(self.input_dir) if f.endswith('.xml')]

    def parse_xml_file(self, filename: str) -> Optional[etree._ElementTree]:
        path = os.path.join(self.input_dir, filename)
        try:
            tree = etree.parse(path)
            return tree
        except Exception as e:
            print(f"[ERROR] Failed to parse {filename}: {e}")
            return None

    def parse_all(self) -> Dict[str, etree._ElementTree]:
        xml_files = self.list_xml_files()
        parsed = {}
        for fname in xml_files:
            tree = self.parse_xml_file(fname)
            if tree is not None:
                parsed[fname] = tree
        return parsed

    def extract_comments(self, filename: str) -> List[str]:
        path = os.path.join(self.input_dir, filename)
        comments = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            import re
            comments = re.findall(r'<!--(.*?)-->', content, re.DOTALL)
            comments = [c.strip() for c in comments]
        except Exception as e:
            print(f"[ERROR] Failed to extract comments from {filename}: {e}")
        return comments

# 사용 예시
if __name__ == "__main__":
    # 제출 데이터(우리가 제출한 원본)
    submitted_parser = XMLParser('/home/drake/work_local/XMLmeta/xml_submitted')
    submitted_xmls = submitted_parser.parse_all()
    print(f"[INFO] Parsed submitted XMLs: {list(submitted_xmls.keys())}")

    # 실제 DDBJ 예시 데이터(실제 제출본)
    real_parser = XMLParser('/home/drake/work_local/XMLmeta/real_examples')
    real_xmls = real_parser.parse_all()
    print(f"[INFO] Parsed real example XMLs: {list(real_xmls.keys())}")

    # 피드백/주석 포함 샘플
    reviewed_parser = XMLParser('/home/drake/work_local/XMLmeta/xml_reviewed')
    for fname in reviewed_parser.list_xml_files():
        comments = reviewed_parser.extract_comments(fname)
        print(f"[INFO] Comments in {fname}:\n", '\n'.join(comments))
