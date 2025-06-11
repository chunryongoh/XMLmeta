import xmltodict
from lxml import etree
import difflib
import subprocess
import os
import re
from collections import OrderedDict

XSD_PATH = "pub/docs/biosample/xsd/biosample_set.xsd"
INPUT_XML = "xml_submitted/ddbj_biosample.xml"
EXAMPLE_XML = "real_examples/SAMD00844971-2.xml"
OUTPUT_XML = "xml_fixed/ddbj_biosample.fixed.xml"
REPORT_PATH = "xml_fixed/biosample_report.txt"

# Attribute 이름 매핑 (camelCase → snake_case)
ATTRIBUTE_NAME_MAP = {
    "sampleName": "sample_name",
    "bioProjectId": "bioproject_id",
    "bioSampleId": "kobic_sample_id",
    "bioSampleGroupId": "kobic_sample_group_id",
    "collectionDate": "collection_date",
    "geographicLocation": "geo_loc_name",
    "biomaterialProvider": "biomaterial_provider",
    "NCBITaxonomyID": "ncbi_taxonomy_id",
    "organism": "host",
    "releaseDate": "kobic_release_date",
    "taxonomicType": "taxonomic_type",
    "breed": "breed",
    "age": "age",
    "sex": "sex",
    "specimenVoucher": "specimen_voucher",
    "tissue": "tissue",
    "isolate": "isolate",
    "isolation_source": "isolation_source",
    "lab_host": "lab_host",
    # ... 필요시 추가 ...
}
# 정답 예시 기준 필수 속성 리스트
REQUIRED_ATTRIBUTES = [
    "sample_name", "bioproject_id", "collection_date", "geo_loc_name", "host", "isolate", "isolation_source",
    "kobic_project_id", "kobic_registration_date", "kobic_release_date", "kobic_sample_group_id", "kobic_sample_id", "kobic_submission_date", "lab_host"
]


def parse_xml(path):
    with open(path, encoding="utf-8") as f:
        return xmltodict.parse(f.read())

def save_xml(doc, path):
    xml_str = xmltodict.unparse(doc, pretty=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_str)

def parse_bioproject_owners(bioproject_xml_path):
    doc = parse_xml(bioproject_xml_path)
    bioprojects = {}
    packages = doc['PackageSet']['Package']
    if isinstance(packages, dict):
        packages = [packages]
    for pkg in packages:
        try:
            proj = pkg['Project']['Project']
            proj_id = proj['ProjectID']['ArchiveID']['@accession']
            org = proj['ProjectDescr'].get('SubmitterOrganization', 'unknown')
            bioprojects[proj_id] = {
                'owner_name': org,
                'contact_email': None
            }
        except Exception as e:
            continue
    return bioprojects

def parse_bioexperiment_isolate_map(bioexp_xml_path):
    doc = parse_xml(bioexp_xml_path)
    result = {}
    experiments = doc['EXPERIMENT_SET']['EXPERIMENT']
    if isinstance(experiments, dict):
        experiments = [experiments]
    for exp in experiments:
        sample_id = exp['DESIGN']['SAMPLE_DESCRIPTOR']['@accession']
        attrs = exp.get('EXPERIMENT_ATTRIBUTES', {}).get('EXPERIMENT_ATTRIBUTE', [])
        if isinstance(attrs, dict):
            attrs = [attrs]
        isolate = ''
        isolation_source = ''
        for attr in attrs:
            tag = attr.get('TAG', '').lower()
            if tag == 'isolate':
                isolate = attr.get('VALUE', '')
            elif tag == 'isolation_source':
                isolation_source = attr.get('VALUE', '')
        result[sample_id] = {
            'isolate': isolate,
            'isolation_source': isolation_source
        }
    return result

def fix_structure(doc, bioprojects=None, bioexp_isolate_map=None):
    """
    [2024-06-XX] BioSample XSD PASS 구조
    - 본 함수는 real_examples/SAMD00844971-2.xml 및 pub/docs/biosample/xsd/biosample.xsd 기준으로 설계됨
    - 반복/위치/태그명/속성 등 모든 요소가 XSD와 일치하도록 보정
    - 정책 변경 시 반드시 requirements.txt와 동기화할 것
    """
    # 루트 태그명 보정
    if 'SAMPLE_SET' in doc:
        doc['BioSampleSet'] = doc.pop('SAMPLE_SET')
    root = doc.get('BioSampleSet', doc.get('BioSampleSet'))
    # 내부 반복 요소 보정
    samples = root.get('SAMPLE', root.get('BioSample'))
    if samples:
        if isinstance(samples, dict):
            samples = [samples]
        root['BioSample'] = []
        for sample in samples:
            sample = dict(sample)
            tag_value_map = {}
            sample_name = None
            organism_name = None
            taxonomy_id = None
            title = None
            # 디버깅: sample 전체 구조, SAMPLE_ATTRIBUTES/SAMPLE_ATTRIBUTE 실제 타입과 내용 출력
            if 'SAMPLE_ATTRIBUTES' in sample:
                print('DEBUG: SAMPLE_ATTRIBUTES:', sample['SAMPLE_ATTRIBUTES'])
                if 'SAMPLE_ATTRIBUTE' in sample['SAMPLE_ATTRIBUTES']:
                    print('DEBUG: SAMPLE_ATTRIBUTE:', type(sample['SAMPLE_ATTRIBUTES']['SAMPLE_ATTRIBUTE']), sample['SAMPLE_ATTRIBUTES']['SAMPLE_ATTRIBUTE'])
            print('DEBUG: sample 전체:', sample)
            # SAMPLE_ATTRIBUTES에서 값 추출을 pop/변환 이전에 먼저 실행
            bio_sample_id = None
            sample_name_val = None
            bio_project_id = None
            if 'SAMPLE_ATTRIBUTES' in sample and 'SAMPLE_ATTRIBUTE' in sample['SAMPLE_ATTRIBUTES']:
                attrs = sample['SAMPLE_ATTRIBUTES']['SAMPLE_ATTRIBUTE']
                if not isinstance(attrs, list):
                    attrs = [attrs]
                for attr in attrs:
                    tag = attr.get('TAG')
                    value = attr.get('VALUE')
                    if tag:
                        tag_l = tag.lower()
                        tag_snake = ATTRIBUTE_NAME_MAP.get(tag, tag)
                        tag_value_map[tag] = value
                        tag_value_map[tag_l] = value
                        tag_value_map[tag_snake] = value
                        tag_camel = re.sub(r'_([a-z])', lambda m: m.group(1).upper(), tag_snake)
                        tag_value_map[tag_camel] = value
            # Models 생성 (SAMPLE_ATTRIBUTES 삭제 이전에 taxonomicType 추출)
            model_val = None
            for attr in attrs:
                if attr.get('TAG') == 'taxonomicType':
                    model_val = attr.get('VALUE')
                    break
            if model_val:
                sample['Models'] = {'Model': model_val}
            else:
                sample['Models'] = {'Model': 'unknown'}
            # SAMPLE_ATTRIBUTES 등 원본 구조 제거
            sample.pop('SAMPLE_ATTRIBUTES', None)
            sample.pop('SAMPLE_NAME', None)
            # Description 생성 직전 robust 추출
            organism_name = (
                tag_value_map.get('scientific_name') or
                tag_value_map.get('SCIENTIFIC_NAME') or
                tag_value_map.get('organism_name') or
                tag_value_map.get('organism') or
                'unknown'
            )
            taxonomy_id = (
                tag_value_map.get('taxon_id') or
                tag_value_map.get('TAXON_ID') or
                tag_value_map.get('ncbi_taxonomy_id') or
                tag_value_map.get('ncbitaxonomyid') or
                'unknown'
            )
            title = (
                tag_value_map.get('title') or
                tag_value_map.get('TITLE') or
                title or
                'unknown'
            )
            # tag_value_map에서 주요 값 robust 추출
            bio_sample_id = (
                tag_value_map.get('kobic_sample_id') or
                tag_value_map.get('bioSampleId') or
                tag_value_map.get('bio_sample_id') or
                tag_value_map.get('biosampleid') or
                tag_value_map.get('kobicSampleId')
            )
            sample_name_val = (
                tag_value_map.get('sample_name') or
                tag_value_map.get('sampleName') or
                tag_value_map.get('samplename')
            )
            if sample_name_val:
                sample_name = sample_name_val
                title = f"{sample_name_val} ({bio_sample_id})" if bio_sample_id else sample_name_val
            else:
                sample_name = bio_sample_id or 'unknown'
                title = sample_name
            # Description robust 생성 (sample_name, title 등)
            organism_struct = {'OrganismName': organism_name}
            if taxonomy_id and taxonomy_id != 'unknown':
                organism_struct['@taxonomy_id'] = taxonomy_id
            sample['Description'] = {
                'SampleName': sample_name or 'unknown',
                'Title': title or 'unknown',
                'Organism': organism_struct
            }
            # Attributes 생성/정제: 반드시 Description 생성 이후에 실행
            attrs_out = []
            # isolate/isolation_source robust 추출
            isolate_val = (
                tag_value_map.get('isolate') or
                tag_value_map.get('isolation_source') or
                'unknown'
            )
            # kobic_project_id, kobic_registration_date robust 추출
            kobic_project_id_val = (
                tag_value_map.get('bioproject_id') or
                tag_value_map.get('bioProjectId') or
                tag_value_map.get('bioprojectid') or
                'unknown'
            )
            kobic_registration_date_val = (
                tag_value_map.get('registration_date') or
                tag_value_map.get('submission_date') or
                tag_value_map.get('release_date') or
                tag_value_map.get('kobic_registration_date') or
                tag_value_map.get('kobic_submission_date') or
                tag_value_map.get('kobic_release_date') or
                'unknown'
            )
            # kobic_submission_date robust 추출
            kobic_submission_date_val = (
                tag_value_map.get('submission_date') or
                tag_value_map.get('registration_date') or
                tag_value_map.get('release_date') or
                tag_value_map.get('kobic_submission_date') or
                tag_value_map.get('kobic_registration_date') or
                tag_value_map.get('kobic_release_date') or
                'unknown'
            )
            # lab_host robust 추출
            lab_host_val = (
                tag_value_map.get('lab_host') or
                tag_value_map.get('host') or
                tag_value_map.get('organism') or
                tag_value_map.get('organism_name') or
                tag_value_map.get('scientific_name') or
                'unknown'
            )
            for req in REQUIRED_ATTRIBUTES:
                if req == 'sample_name':
                    val = sample['Description']['SampleName']
                    attrs_out.append({'@attribute_name': req, '#text': val})
                elif req in ['isolate', 'isolation_source']:
                    attrs_out.append({'@attribute_name': req, '#text': isolate_val})
                elif req == 'kobic_project_id':
                    attrs_out.append({'@attribute_name': req, '#text': kobic_project_id_val})
                elif req == 'kobic_registration_date':
                    attrs_out.append({'@attribute_name': req, '#text': kobic_registration_date_val})
                elif req == 'kobic_submission_date':
                    attrs_out.append({'@attribute_name': req, '#text': kobic_submission_date_val})
                elif req == 'lab_host':
                    attrs_out.append({'@attribute_name': req, '#text': lab_host_val})
                elif req in tag_value_map and tag_value_map[req] is not None:
                    attrs_out.append({'@attribute_name': req, '#text': str(tag_value_map[req]) or 'unknown'})
                else:
                    attrs_out.append({'@attribute_name': req, '#text': 'unknown'})
            if attrs_out:
                sample['Attributes'] = {'Attribute': attrs_out}
            # 속성 보정
            sample = {k: v for k, v in sample.items() if k not in ['@accession', '@alias', '@center_name']}
            sample['@access'] = 'public'
            # <IDENTIFIERS> → <Ids> 변환
            if 'IDENTIFIERS' in sample:
                sample['Ids'] = sample.pop('IDENTIFIERS')
            # <PRIMARY_ID> → <Id> 변환, label 제거, namespace 추가, value가 dict면 #text만 추출
            if 'Ids' in sample and 'PRIMARY_ID' in sample['Ids']:
                value = sample['Ids'].pop('PRIMARY_ID')
                if isinstance(value, dict):
                    value = value.get('#text', '')
                sample['Ids']['Id'] = {'@namespace': 'BioSample', '#text': str(value)}
            # Description 하위 태그 보정 (SampleName, Title, OrganismName, taxonomy_id robust 추출)
            if 'Attributes' in sample and 'Attribute' in sample['Attributes']:
                attrs = sample['Attributes']['Attribute']
                if isinstance(attrs, dict):
                    attrs = [attrs]
                for attr in attrs:
                    if attr.get('@attribute_name') == 'SCIENTIFIC_NAME' and not organism_name:
                        organism_name = attr.get('#text')
                    if attr.get('@attribute_name') == 'TAXON_ID' and not taxonomy_id:
                        taxonomy_id = attr.get('#text')
                    if attr.get('@attribute_name') == 'TITLE' and not title:
                        title = attr.get('#text')
            # <Models>가 리스트가 아니면 리스트로 변환
            if 'Models' in sample and 'Model' in sample['Models']:
                if isinstance(sample['Models']['Model'], dict):
                    sample['Models']['Model'] = [sample['Models']['Model']]
                elif isinstance(sample['Models']['Model'], str):
                    sample['Models']['Model'] = [sample['Models']['Model']]
            # Owner 정보 robust 추출
            owner_name = 'unknown'
            contact_email = 'kobic_ddbj@kobic.kr'
            contact_first = 'KOBIC'
            contact_last = 'KOBIC'
            if bioprojects and kobic_project_id_val in bioprojects:
                owner_name = bioprojects[kobic_project_id_val].get('owner_name', 'unknown')
                contact_email = bioprojects[kobic_project_id_val].get('contact_email', 'kobic_ddbj@kobic.kr')
            # email None/빈값 보정
            if not contact_email or contact_email == 'None':
                contact_email = 'kobic_ddbj@kobic.kr'
            owner_name = (
                tag_value_map.get('owner') or
                tag_value_map.get('submitter') or
                tag_value_map.get('organization') or
                tag_value_map.get('center_name') or
                owner_name
            )
            sample['Owner'] = {
                'Name': owner_name,
                'Contacts': {
                    'Contact': {
                        '@email': contact_email,
                        'Name': {
                            'First': contact_first,
                            'Last': contact_last
                        }
                    }
                }
            }
            # 순서 보정: Ids → Description → Owner → Providers(optional) → Models(필수) → Attributes(optional) → 나머지
            new_sample = OrderedDict()
            if 'Ids' in sample:
                new_sample['Ids'] = sample['Ids']
            if 'Description' in sample:
                new_sample['Description'] = sample['Description']
            if 'Owner' in sample:
                new_sample['Owner'] = sample['Owner']
            if 'Providers' in sample:
                new_sample['Providers'] = sample['Providers']
            if 'Models' in sample:
                new_sample['Models'] = sample['Models']
            if 'Attributes' in sample:
                new_sample['Attributes'] = sample['Attributes']
            for k, v in sample.items():
                if k not in ['Ids', 'Description', 'Owner', 'Providers', 'Models', 'Attributes']:
                    new_sample[k] = v
            root['BioSample'].append(new_sample)
        if 'SAMPLE' in root:
            del root['SAMPLE']
    return doc

def validate_xsd(xml_path, xsd_path):
    result = subprocess.run(
        ["xmllint", "--schema", xsd_path, "--noout", xml_path],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr

def diff_with_example(fixed_xml, example_xml):
    with open(fixed_xml, encoding="utf-8") as f1, open(example_xml, encoding="utf-8") as f2:
        diff = difflib.unified_diff(
            f1.readlines(), f2.readlines(),
            fromfile="fixed", tofile="example"
        )
        return "".join(diff)

def save_biosample_grouped_by_ssubid(doc, output_dir, xsd_path=None, report_path=None):
    """
    BioSample XML을 bioSampleGroupId(SSUBid)별로 분리하여 각각 <BioSampleSet>으로 저장
    xsd_path가 주어지면 각 파일에 대해 XSD 검증도 수행
    report_path가 주어지면 결과를 해당 파일에 기록
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    root = doc.get('BioSampleSet', doc.get('BioSampleSet'))
    samples = root.get('BioSample', [])
    if isinstance(samples, dict):
        samples = [samples]
    # SSUBid별로 샘플 분류
    ssubid_map = {}
    for sample in samples:
        ssubid = None
        # Attributes에서 bioSampleGroupId 찾기
        attrs = sample.get('Attributes', {}).get('Attribute', [])
        if isinstance(attrs, dict):
            attrs = [attrs]
        for attr in attrs:
            if attr.get('@attribute_name') == 'kobic_sample_group_id':
                ssubid = attr.get('#text')
                break
        if not ssubid:
            ssubid = 'UNKNOWN_GROUP'
        if ssubid not in ssubid_map:
            ssubid_map[ssubid] = []
        ssubid_map[ssubid].append(sample)
    # 각 그룹별로 <BioSampleSet> 생성 및 저장 + XSD 검증 + 리포트
    report_lines = []
    for ssubid, group_samples in ssubid_map.items():
        group_doc = {'BioSampleSet': {'BioSample': group_samples}}
        out_path = os.path.join(output_dir, f"{ssubid}.xml")
        save_xml(group_doc, out_path)
        print(f"[INFO] Saved {len(group_samples)} samples to {out_path}")
        # XSD 검증 및 리포트 기록
        if xsd_path:
            valid, xsd_report = validate_xsd(out_path, xsd_path)
            result_str = f"[XSD] {ssubid}.xml: {'PASS' if valid else 'FAIL'}"
            print(result_str)
            if not valid:
                print(xsd_report)
            report_lines.append(result_str)
            if not valid:
                report_lines.append(xsd_report)
    # 리포트 파일 저장
    if report_path and report_lines:
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write('\n'.join(report_lines))

def main():
    print("=== BioSample Pipeline Start ===")
    os.makedirs("xml_fixed", exist_ok=True)
    doc = parse_xml(INPUT_XML)
    # bioproject 정보 파싱
    bioprojects = parse_bioproject_owners("xml_submitted/ddbj_bioproject.xml")
    # bioexperiment 정보 파싱 (isolate, isolation_source)
    bioexp_isolate_map = parse_bioexperiment_isolate_map("xml_submitted/ddbj_bioExperiment.xml")
    doc_fixed = fix_structure(doc, bioprojects, bioexp_isolate_map)
    save_xml(doc_fixed, OUTPUT_XML)
    # SSUBid별로 분리 저장 + XSD 검증 + 리포트 저장
    save_biosample_grouped_by_ssubid(doc_fixed, "xml_fixed/ddbj_biosample_fixed", XSD_PATH, REPORT_PATH)
    valid, xsd_report = validate_xsd(OUTPUT_XML, XSD_PATH)
    diff_report = diff_with_example(OUTPUT_XML, EXAMPLE_XML)
    print("# XSD Validation: {}\n".format("PASS" if valid else "FAIL"))
    print(xsd_report)
    print("\n# Diff with Example\n")
    print(diff_report)
    print("Pipeline complete. See fixed XML:", OUTPUT_XML)

if __name__ == "__main__":
    main()
