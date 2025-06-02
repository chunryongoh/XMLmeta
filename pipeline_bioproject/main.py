import xmltodict
from lxml import etree
import difflib
import subprocess
import os
import re

# 주요 경로 상수 정의
XSD_PATH = "pub/docs/bioproject/xsd/Package.xsd"            # XSD 스키마 파일 경로
INPUT_XML = "xml_submitted/ddbj_bioproject.xml"             # 입력 XML 파일 경로
EXAMPLE_XML = "real_examples/PRJDB19520.xml"                # 예시 XML 파일 경로
OUTPUT_XML = "xml_fixed/ddbj_bioproject.fixed.xml"      # 변환 후 저장할 XML 파일 경로
REPORT_PATH = "xml_fixed/bioproject_report.txt"              # 리포트 파일 경로
BIOSAMPLE_XML = "xml_submitted/ddbj_biosample.xml"
RUN_XML = "xml_submitted/ddbj_run.xml"


# XML 파일을 파싱하여 dict 형태로 반환
# xmltodict는 XML을 파이썬 dict로 변환해줌
def parse_xml(path):
    with open(path, encoding="utf-8") as f:
        return xmltodict.parse(f.read())

# dict 형태의 XML 데이터를 파일로 저장
# pretty=True 옵션으로 보기 좋게 저장
def save_xml(doc, path):
    xml_str = xmltodict.unparse(doc, pretty=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_str)

# 날짜 포맷을 YYYY-MM-DD로 보정
# 월/일이 한 자리일 때 0을 붙여줌
def fix_date_format(date_str):
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return date_str

# BioSample XML에서 bioProjectId별 taxID, OrganismName 매핑 테이블 생성 함수
# 반환값 예시: {'KAP240632': [{'taxID': '10116', 'OrganismName': 'Rattus norvegicus'}, ...]}
def build_biosample_project_organism_map(biosample_path):
    project_map = {}
    with open(biosample_path, encoding="utf-8") as f:
        doc = xmltodict.parse(f.read())
    samples = doc.get('SAMPLE_SET', {}).get('SAMPLE', [])
    if not isinstance(samples, list):
        samples = [samples]
    for sample in samples:
        project_id = None
        taxid = None
        orgname = None
        sn = sample.get('SAMPLE_NAME', {})
        taxid = sn.get('TAXON_ID')
        orgname = sn.get('SCIENTIFIC_NAME')
        attrs = sample.get('SAMPLE_ATTRIBUTES', {}).get('SAMPLE_ATTRIBUTE', [])
        if not isinstance(attrs, list):
            attrs = [attrs]
        for attr in attrs:
            tag = attr.get('TAG')
            val = attr.get('VALUE')
            if tag == 'bioProjectId':
                project_id = val
            if tag == 'NCBITaxonomyID' and not taxid:
                taxid = val
            if tag == 'organism' and not orgname:
                orgname = val
        if project_id:
            if project_id not in project_map:
                project_map[project_id] = []
            # 중복 방지: taxID/OrganismName 쌍이 이미 있으면 추가하지 않음
            candidate = {'taxID': taxid, 'OrganismName': orgname}
            if candidate not in project_map[project_id]:
                project_map[project_id].append(candidate)
    return project_map

# RUN XML에서 BioProject와 연결되는 KOBIC_*_date를 추출해 매핑 테이블 생성
# 반환값 예시: {'KAP240632': {'KOBIC_submission_date': '2024-3-12', ...}}
def build_run_project_date_map(run_path, biosample_path):
    # BioSample에서 accession <-> sampleName/title 연결용 보조 맵 생성
    biosample_map = {}
    with open(biosample_path, encoding="utf-8") as f:
        doc = xmltodict.parse(f.read())
    samples = doc.get('SAMPLE_SET', {}).get('SAMPLE', [])
    if not isinstance(samples, list):
        samples = [samples]
    for sample in samples:
        project_id = None
        sample_name = None
        attrs = sample.get('SAMPLE_ATTRIBUTES', {}).get('SAMPLE_ATTRIBUTE', [])
        if not isinstance(attrs, list):
            attrs = [attrs]
        for attr in attrs:
            tag = attr.get('TAG')
            val = attr.get('VALUE')
            if tag == 'bioProjectId':
                project_id = val
            if tag == 'sampleName':
                sample_name = val
        if project_id and sample_name:
            biosample_map[sample_name] = project_id
    # RUN XML 파싱 및 project_id별 대표 날짜 추출
    project_date_map = {}
    with open(run_path, encoding="utf-8") as f:
        doc = xmltodict.parse(f.read())
    runs = doc.get('RUN_SET', {}).get('RUN', [])
    if not isinstance(runs, list):
        runs = [runs]
    for run in runs:
        # RUN의 TITLE에서 sampleName 추출(간접 연결)
        title = run.get('TITLE', '')
        # 예: 'Sequel II paired-end Sequencing of SCI'에서 'SCI' 추출
        sample_name = title.split()[-1] if title else None
        project_id = biosample_map.get(sample_name)
        if not project_id:
            continue
        # RUN_ATTRIBUTE에서 날짜 추출
        attrs = run.get('RUN_ATTRIBUTES', {}).get('RUN_ATTRIBUTE', [])
        if not isinstance(attrs, list):
            attrs = [attrs]
        date_info = {}
        for attr in attrs:
            tag = attr.get('TAG')
            val = attr.get('VALUE')
            if tag in ['KOBIC_submission_date', 'KOBIC_registration_date', 'KOBIC_release_date']:
                date_info[tag] = val
        # 대표값: 첫 번째 RUN의 값만 사용
        if project_id not in project_date_map and date_info:
            project_date_map[project_id] = date_info
    return project_date_map

# XML 구조를 정책에 맞게 보정하는 핵심 함수
# 각종 누락/오류 필드를 자동으로 채워주거나 수정
# 예외 발생 시 해당 패키지는 건너뜀
# 주요 보정 항목은 아래 주석 참고
#   1. ArchiveID의 @archive 값 보정
#   2. Grant 하위 Agency 추가
#   3. ProjectType 누락 시 기본값 추가
#      - ProjectTypeSubmission 하위 속성 후보값(XSD 기준):
#        * sample_scope: eMonoisolate, eMultiisolate, eMultispecies, eEnvironment, eSynthetic, eSingleCell, eOther
#        * material: eGenome, ePartialGenome, eTranscriptome, eReagent, eProteome, ePhenotype, eOther
#        * capture: eWhole, eCloneEnds, eExome, eTargetedLocusLoci, eRandomSurvey, eOther
#      - 실제 입력 XML 및 연관 XML(ddbj_bioExperiment.xml, ddbj_biosample.xml, ddbj_run.xml)에서 해당 값을 추출할 수 없어 기본값 사용
#   4. SubmitterOrganization 위치 이동
#   5. ProjectSubmissionDate 위치 이동 및 포맷 보정
#   6. ProjectReleaseDate 포맷 보정
#   7. Project 하위 Submission 블록 제거

def fix_structure(doc):
    biosample_map = build_biosample_project_organism_map(BIOSAMPLE_XML)
    run_date_map = build_run_project_date_map(RUN_XML, BIOSAMPLE_XML)
    packages = doc.get('PackageSet', {}).get('Package', [])
    if not isinstance(packages, list):
        packages = [packages]
    for package in packages:
        try:
            project = package['Project']['Project']
            archive = project['ProjectID']['ArchiveID'].get('@archive')
            if not archive or archive not in ['DDBJ', 'NCBI', 'EBI']:
                project['ProjectID']['ArchiveID']['@archive'] = 'DDBJ'
            grant = project['ProjectDescr']['Grant']
            if 'Agency' not in grant:
                grant['Agency'] = {'@abbr': 'MSIT', '#text': 'Ministry of Science and ICT'}
            # RUN XML에서 UserTerm 정보 추출 (ProjectDescr 하위에 추가)
            accession = project['ProjectID']['ArchiveID'].get('@accession')
            user_terms = []
            run_dates = run_date_map.get(accession)
            if run_dates:
                for k, v in run_dates.items():
                    user_terms.append({'@term': k, '#text': v})
            # ProjectDescr 하위에 UserTerm 삽입 (ProjectReleaseDate 바로 뒤)
            descr = project['ProjectDescr']
            if user_terms:
                new_descr = {}
                inserted = False
                for key in descr:
                    new_descr[key] = descr[key]
                    # ProjectReleaseDate 뒤에 UserTerm 삽입
                    if key == 'ProjectReleaseDate' and not inserted:
                        for ut in user_terms:
                            if 'UserTerm' not in new_descr:
                                new_descr['UserTerm'] = []
                            new_descr['UserTerm'].append(ut)
                        inserted = True
                # ProjectReleaseDate가 없으면 Grant 뒤에 삽입
                if not inserted and 'Grant' in descr:
                    temp_descr = {}
                    for key in descr:
                        temp_descr[key] = descr[key]
                        if key == 'Grant' and not inserted:
                            for ut in user_terms:
                                if 'UserTerm' not in temp_descr:
                                    temp_descr['UserTerm'] = []
                                temp_descr['UserTerm'].append(ut)
                            inserted = True
                    new_descr = temp_descr
                # Grant도 없으면 Title 뒤에 삽입
                if not inserted and 'Title' in descr:
                    temp_descr = {}
                    for key in descr:
                        temp_descr[key] = descr[key]
                        if key == 'Title' and not inserted:
                            for ut in user_terms:
                                if 'UserTerm' not in temp_descr:
                                    temp_descr['UserTerm'] = []
                                temp_descr['UserTerm'].append(ut)
                            inserted = True
                    new_descr = temp_descr
                descr.clear()
                descr.update(new_descr)
            # ProjectTypeSubmission 등 나머지 구조는 기존대로 유지
            organism_candidates = biosample_map.get(accession)
            organism_block = None
            if organism_candidates and len(organism_candidates) > 0:
                unique_candidates = []
                seen = set()
                for cand in organism_candidates:
                    key = (cand['taxID'], cand['OrganismName'])
                    if key not in seen and cand['taxID'] and cand['OrganismName']:
                        unique_candidates.append(cand)
                        seen.add(key)
                if len(unique_candidates) == 1:
                    organism_block = unique_candidates[0]
                elif len(unique_candidates) > 1:
                    print(f"[선택 필요] ProjectID {accession}에 대해 여러 Organism 후보가 있습니다:")
                    for idx, cand in enumerate(unique_candidates):
                        print(f"  {idx+1}: taxID={cand['taxID']}, OrganismName={cand['OrganismName']}")
                    try:
                        sel = int(input(f"원하는 Organism 번호를 입력하세요 (1~{len(unique_candidates)}): "))
                        organism_block = unique_candidates[sel-1]
                    except Exception:
                        print("입력 오류: 기본값 사용")
            if not organism_block:
                organism_block = {'taxID': '32644', 'OrganismName': 'unidentified'}
            project['ProjectType'] = {
                'ProjectTypeSubmission': {
                    'Target': {
                        '@sample_scope': 'eOther',
                        '@material': 'eOther',
                        '@capture': 'eOther',
                        'Organism': {
                            '@taxID': organism_block['taxID'],
                            'OrganismName': organism_block['OrganismName']
                        }
                    },
                    'Method': {'@method_type': 'eOther'},
                    'Objectives': {'Data': {'@data_type': 'eOther'}},
                    'ProjectDataTypeSet': {'DataType': 'Other'}
                }
            }
            # --- Submission/Description/Organization/Contact 구조를 실제 사례처럼 항상 생성 ---
            org_name = descr.pop('SubmitterOrganization', None)
            submitted_date = descr.pop('ProjectSubmissionDate', None)
            organization_block = {
                '@type': 'center',
                '@role': 'owner',
                'Name': org_name if org_name else '',
                'Contact': {
                    '@email': '',
                    'Name': {
                        'First': '',
                        'Last': ''
                    }
                }
            }
            submission_block = {
                'Submission': {
                    '@submitted': fix_date_format(submitted_date) if submitted_date else '',
                    'Description': {
                        'Organization': organization_block,
                        'Access': 'public'
                    }
                }
            }
            # Project 내부가 아니라 Package 하위에 Submission 추가 (중첩 구조)
            package['Submission'] = {'Submission': submission_block['Submission']}
            if 'ProjectReleaseDate' in descr:
                descr['ProjectReleaseDate'] = fix_date_format(descr['ProjectReleaseDate'])
        except Exception as e:
            continue
    return doc

# xmllint를 이용해 XSD 스키마 검증 수행
# 유효성 통과 여부와 에러 메시지 반환
def validate_xsd(xml_path, xsd_path):
    result = subprocess.run(
        ["xmllint", "--schema", xsd_path, "--noout", xml_path],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr

# 변환된 XML과 예시 XML을 비교하여 diff 리포트 생성
def diff_with_example(fixed_xml, example_xml):
    with open(fixed_xml, encoding="utf-8") as f1, open(example_xml, encoding="utf-8") as f2:
        diff = difflib.unified_diff(
            f1.readlines(), f2.readlines(),
            fromfile="fixed", tofile="example"
        )
        return "".join(diff)

# 전체 파이프라인 실행 함수
# 1. 요구사항 로드
# 2. 입력 XML 파싱
# 3. 구조 보정
# 4. 보정된 XML 저장
# 5. XSD 검증
# 6. 예시 XML과 diff 비교
# 7. 리포트 파일 작성
# 8. 완료 메시지 출력
def main():
    print("=== BioProject Pipeline Start ===")
    os.makedirs("xml_fixed", exist_ok=True)
    doc = parse_xml(INPUT_XML)          # 입력 XML 파싱
    doc_fixed = fix_structure(doc)      # 구조 보정
    save_xml(doc_fixed, OUTPUT_XML)     # 보정된 XML 저장
    valid, xsd_report = validate_xsd(OUTPUT_XML, XSD_PATH)  # XSD 검증
    diff_report = diff_with_example(OUTPUT_XML, EXAMPLE_XML) # 예시와 diff 비교
    print("# XSD Validation: {}\n".format("PASS" if valid else "FAIL"))
    print(xsd_report)
    print("\n# Diff with Example\n")
    print(diff_report)
    print("Pipeline complete. See fixed XML:", OUTPUT_XML)

# 메인 함수 실행 (직접 실행 시)
if __name__ == "__main__":
    main()
