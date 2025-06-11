import xmltodict
from lxml import etree
import subprocess
import os
from collections import OrderedDict
import csv
import difflib

XSD_PATH = "pub/docs/dra/xsd/1-6/SRA.experiment.xsd"
INPUT_XML = "xml_submitted/ddbj_bioExperiment.xml"
EXAMPLE_XML = "real_examples/kobic-0352.experiment.xml"
OUTPUT_XML = "xml_fixed/ddbj_bioExperiment.fixed.xml"
REPORT_PATH = "xml_fixed/experiment_report.txt"

# XSD의 모든 플랫폼별 INSTRUMENT_MODEL 값 통합
PLATFORM_INSTRUMENTS = {
    'LS454': [
        "454 GS", "454 GS 20", "454 GS FLX", "454 GS FLX+", "454 GS FLX Titanium", "454 GS Junior", "unspecified"
    ],
    'ILLUMINA': [
        "Illumina Genome Analyzer", "Illumina Genome Analyzer II", "Illumina Genome Analyzer IIx", "Illumina HiSeq 1000", "Illumina HiSeq 1500", "Illumina HiSeq 2000", "Illumina HiSeq 2500", "Illumina HiSeq 3000", "Illumina HiSeq 4000", "HiSeq X Five", "HiSeq X Ten", "Illumina HiSeq X", "Illumina HiScanSQ", "Illumina NovaSeq 6000", "Illumina NovaSeq X", "Illumina MiSeq", "Illumina MiniSeq", "Illumina iSeq 100", "NextSeq 500", "NextSeq 550", "NextSeq 1000", "NextSeq 2000", "unspecified"
    ],
    'HELICOS': [
        "Helicos HeliScope", "unspecified"
    ],
    'ABI_SOLID': [
        "AB SOLiD System", "AB SOLiD System 2.0", "AB SOLiD System 3.0", "AB SOLiD 3 Plus System", "AB SOLiD 4 System", "AB SOLiD 4hq System", "AB SOLiD PI System", "AB 5500 Genetic Analyzer", "AB 5500xl Genetic Analyzer", "AB 5500xl-W Genetic Analysis System", "unspecified"
    ],
    'COMPLETE_GENOMICS': [
        "Complete Genomics", "unspecified"
    ],
    'BGISEQ': [
        "BGISEQ-50", "BGISEQ-500", "MGISEQ-2000RS"
    ],
    'OXFORD_NANOPORE': [
        "MinION", "GridION", "PromethION", "unspecified"
    ],
    'PACBIO_SMRT': [
        "PacBio RS", "PacBio RS II", "Sequel", "Sequel II", "Sequel IIe", "Onso", "Revio", "unspecified"
    ],
    'ION_TORRENT': [
        "Ion Torrent PGM", "Ion Torrent Proton", "Ion Torrent S5", "Ion Torrent S5 XL", "Ion GeneStudio S5", "Ion GeneStudio S5 plus", "Ion GeneStudio S5 prime", "Ion Torrent Genexus", "unspecified"
    ],
    'VELA_DIAGNOSTICS': [
        "Sentosa SQ301", "unspecified"
    ],
    'CAPILLARY': [
        "AB 3730xL Genetic Analyzer", "AB 3730 Genetic Analyzer", "AB 3500xL Genetic Analyzer", "AB 3500 Genetic Analyzer", "AB 3130xL Genetic Analyzer", "AB 3130 Genetic Analyzer", "AB 310 Genetic Analyzer", "unspecified"
    ],
    'GENAPSYS': [
        "GENIUS", "Genapsys Sequencer", "GS111", "unspecified"
    ],
    'DNBSEQ': [
        "DNBSEQ-G400", "DNBSEQ-G400 FAST", "DNBSEQ-T7", "DNBSEQ-G50", "unspecified"
    ],
    'ELEMENT': [
        "Element AVITI", "unspecified"
    ],
    'GENEMIND': [
        "GenoCare 1600", "GenoLab M", "FASTASeq 300", "unspecified"
    ],
    'ULTIMA': [
        "UG 100", "unspecified"
    ],
    'TAPESTRI': [
        "Tapestri", "unspecified"
    ],
}
# 모든 기기명 통합 리스트 (중복 제거 + 알파벳 정렬)
allowed_instrument = sorted(set(sum(PLATFORM_INSTRUMENTS.values(), [])))

def parse_xml(path):
    with open(path, encoding="utf-8") as f:
        return xmltodict.parse(f.read())

def save_xml(doc, path):
    xml_str = xmltodict.unparse(doc, pretty=True)
    # 빈 태그를 self-closing으로 치환
    xml_str = xml_str.replace('<PAIRED></PAIRED>', '<PAIRED/>').replace('<SINGLE></SINGLE>', '<SINGLE/>')
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_str)

def clean_attributes(d):
    # 불필요한 속성(refcenter, refname 등) 제거
    if isinstance(d, dict):
        keys_to_del = []
        for k in d:
            if k.startswith('@') and k in ['@refcenter', '@refname']:
                keys_to_del.append(k)
        for k in keys_to_del:
            del d[k]
        for v in d.values():
            clean_attributes(v)
    elif isinstance(d, list):
        for item in d:
            clean_attributes(item)

def fix_identifiers(ident, parent_accession=None, id_type=None, exp_accession=None):
    # id_type: "BioProject" or "BioSample"
    # parent_accession: 상위 태그의 accession 값 (KAP..., KAS...)
    # exp_accession: experiment 자신의 accession 값
    if isinstance(ident, dict):
        # PRIMARY_ID label이 BioProject ID 또는 BioSample ID면 항상 ddbj_id_of_ + acc 값을 prefix로 갖고, 기존 값이 있으면 뒤에 괄호로 병기
        if 'PRIMARY_ID' in ident:
            pid = ident['PRIMARY_ID']
            # BioProject ID
            if (isinstance(pid, dict) and pid.get('@label') == 'BioProject ID') or (isinstance(pid, str) and id_type == "BioProject"):
                acc = parent_accession or ''
                if isinstance(pid, dict):
                    val = pid.get('#text')
                    if not val or val == f"ddbj_id_of_{acc}":
                        pid['#text'] = f"ddbj_id_of_{acc}"
                    else:
                        pid['#text'] = f"ddbj_id_of_{acc}({val})"
                elif isinstance(pid, str):
                    if not pid or pid == f"ddbj_id_of_{acc}":
                        ident['PRIMARY_ID'] = {'@label': 'BioProject ID', '#text': f"ddbj_id_of_{acc}"}
                    else:
                        ident['PRIMARY_ID'] = {'@label': 'BioProject ID', '#text': f"ddbj_id_of_{acc}({pid})"}
            # BioSample ID
            if (isinstance(pid, dict) and pid.get('@label') == 'BioSample ID') or (isinstance(pid, str) and id_type == "BioSample"):
                acc = parent_accession or ''
                if isinstance(pid, dict):
                    val = pid.get('#text')
                    if not val or val == f"ddbj_id_of_{acc}":
                        pid['#text'] = f"ddbj_id_of_{acc}"
                    else:
                        pid['#text'] = f"ddbj_id_of_{acc}({val})"
                elif isinstance(pid, str):
                    if not pid or pid == f"ddbj_id_of_{acc}":
                        ident['PRIMARY_ID'] = {'@label': 'BioSample ID', '#text': f"ddbj_id_of_{acc}"}
                    else:
                        ident['PRIMARY_ID'] = {'@label': 'BioSample ID', '#text': f"ddbj_id_of_{acc}({pid})"}
        # SUBMITTER_ID namespace="KOBIC"에 parent_accession 또는 exp_accession 값 넣기
        found = False
        sub_value = exp_accession or parent_accession or ''
        if 'SUBMITTER_ID' in ident:
            sub = ident['SUBMITTER_ID']
            if isinstance(sub, list):
                for s in sub:
                    if isinstance(s, dict) and s.get('@namespace') == 'KOBIC':
                        s['#text'] = sub_value
                        found = True
            elif isinstance(sub, dict):
                if sub.get('@namespace') == 'KOBIC':
                    sub['#text'] = sub_value
                    found = True
            elif isinstance(sub, str):
                ident['SUBMITTER_ID'] = {'@namespace': 'KOBIC', '#text': sub_value}
                found = True
        if not found:
            # 없으면 추가
            ident['SUBMITTER_ID'] = {'@namespace': 'KOBIC', '#text': sub_value}
    return ident

def get_platform_tag_for_instrument(instrument):
    for platform_tag, models in PLATFORM_INSTRUMENTS.items():
        if instrument in models:
            return platform_tag
    return None

def fix_structure(doc):
    # 1. 빈 값(""), None, 빈 리스트, 빈 dict 제거
    def remove_empty(d):
        if isinstance(d, dict):
            return {k: remove_empty(v) for k, v in d.items() if v not in ("", None, [], {})}
        elif isinstance(d, list):
            return [remove_empty(i) for i in d if i not in ("", None, [], {})]
        else:
            return d
    doc = remove_empty(doc)

    # 재귀적으로 불필요한 속성 제거 및 IDENTIFIERS 보정
    def recursive_fix(d, parent_accession=None, id_type=None, exp_accession=None):
        if isinstance(d, dict):
            clean_attributes(d)
            for k, v in d.items():
                # STUDY_REF, SAMPLE_DESCRIPTOR 등에서 accession 값을 넘김
                if k == 'STUDY_REF' and isinstance(v, dict):
                    acc = v.get('@accession')
                    if 'IDENTIFIERS' in v:
                        v['IDENTIFIERS'] = fix_identifiers(v['IDENTIFIERS'], parent_accession=acc, id_type="BioProject")
                    recursive_fix(v, parent_accession=acc, id_type="BioProject")
                elif k == 'SAMPLE_DESCRIPTOR' and isinstance(v, dict):
                    acc = v.get('@accession')
                    if 'IDENTIFIERS' in v:
                        v['IDENTIFIERS'] = fix_identifiers(v['IDENTIFIERS'], parent_accession=acc, id_type="BioSample")
                    recursive_fix(v, parent_accession=acc, id_type="BioSample")
                elif k == 'IDENTIFIERS':
                    # EXPERIMENT의 IDENTIFIERS라면 exp_accession을 넘김
                    if id_type is None and exp_accession:
                        d[k] = fix_identifiers(v, exp_accession=exp_accession)
                    elif not (id_type in ["BioProject", "BioSample"]):
                        d[k] = fix_identifiers(v)
                else:
                    # EXPERIMENT 루트에서 recursive_fix를 호출할 때 exp_accession을 넘김
                    if k == 'EXPERIMENT' and isinstance(v, dict):
                        acc = v.get('@accession')
                        d[k] = recursive_fix(v, exp_accession=acc)
                    else:
                        d[k] = recursive_fix(v)
        elif isinstance(d, list):
            return [recursive_fix(i) for i in d]
        return d
    doc = recursive_fix(doc)

    # 2. LIBRARY_SELECTION, LIBRARY_STRATEGY, LIBRARY_SOURCE 등 허용값만 남기기
    allowed_selection = {"RANDOM", "PCR", "RT-PCR", "HMPR", "MF", "CF", "size fractionation", "cDNA", "ChIP", "MNase", "DNase", "Hybrid Selection", "Reduced Representation", "Restriction Digest", "Inverse rRNA", "PolyA", "Oligo-dT", "other"}
    allowed_strategy = {"WGS", "WGA", "WXS", "RNA-Seq", "ssRNA-seq", "miRNA-Seq", "ncRNA-Seq", "FL-cDNA", "EST", "Hi-C", "ATAC-seq", "WCS", "RAD-Seq", "CLONE", "POOLCLONE", "AMPLICON", "CLONEEND", "FINISHING", "ChIP-Seq", "MNase-Seq", "DNase-Hypersensitivity", "Bisulfite-Seq", "CTS", "MRE-Seq", "MeDIP-Seq", "MBD-Seq", "Tn-Seq", "VALIDATION", "FAIRE-seq", "SELEX", "NOMe-Seq", "RIP-Seq", "ChIA-PET", "Synthetic-Long-Read", "Targeted-Capture", "Tethered Chromatin Conformation Capture", "OTHER"}
    allowed_source = {"GENOMIC", "TRANSCRIPTOMIC", "METAGENOMIC", "SYNTHETIC", "VIRAL RNA", "OTHER"}

    def fix_experiment(exp):
        acc = exp.get('@accession')
        title = exp.get('TITLE')
        if acc and title and not title.strip().endswith(f"({acc})"):
            exp['TITLE'] = f"{title} ({acc})"
        # DESIGN 하위 DESIGN_DESCRIPTION 보정
        if 'DESIGN' in exp and isinstance(exp['DESIGN'], dict):
            design = exp['DESIGN']
            desc = design.get('DESIGN_DESCRIPTION', None)
            if desc is None or (isinstance(desc, str) and desc.strip() == ""):
                design['DESIGN_DESCRIPTION'] = 'missing'
            exp['DESIGN'] = design
        # 1. DESIGN 하위 DESIGN_DESCRIPTION(텍스트), SAMPLE_DESCRIPTOR(속성/빈태그), LIBRARY_DESCRIPTOR 모두 존재, 순서 보장
        if 'DESIGN' in exp and isinstance(exp['DESIGN'], dict):
            design = exp['DESIGN']
            # DESIGN_DESCRIPTION
            desc = design.get('DESIGN_DESCRIPTION', '')
            if not isinstance(desc, str):
                desc = ''
            # EXPERIMENT의 SAMPLE_DESCRIPTOR를 DESIGN 하위로 이동 (여러 개일 수 있음)
            sample_desc = None
            if 'SAMPLE_DESCRIPTOR' in exp:
                sample_desc = exp.pop('SAMPLE_DESCRIPTOR')
            elif 'SAMPLE_DESCRIPTOR' in design:
                sample_desc = design.pop('SAMPLE_DESCRIPTOR')
            if sample_desc is not None:
                if not isinstance(sample_desc, list):
                    sample_desc = [sample_desc]
            else:
                sample_desc = []
            # EXPERIMENT의 LIBRARY_DESCRIPTOR를 DESIGN 하위로 이동
            lib_desc = None
            if 'LIBRARY_DESCRIPTOR' in exp:
                lib_desc = exp.pop('LIBRARY_DESCRIPTOR')
            elif 'LIBRARY_DESCRIPTOR' in design:
                lib_desc = design.pop('LIBRARY_DESCRIPTOR')
            # LIBRARY_NAME 반드시 추가
            library_name = None
            if isinstance(lib_desc, dict):
                if 'LIBRARY_NAME' in lib_desc:
                    library_name = lib_desc['LIBRARY_NAME']
                elif 'LIBRARY_NAME' in exp:
                    library_name = exp['LIBRARY_NAME']
                # LIBRARY_NAME을 LIBRARY_DESCRIPTOR 하위에 추가
                if library_name:
                    lib_desc['LIBRARY_NAME'] = library_name
                # LIBRARY_LAYOUT 분리
                layout = None
                if 'LIBRARY_LAYOUT' in lib_desc:
                    layout = lib_desc.pop('LIBRARY_LAYOUT')
                if layout is None and 'LIBRARY_LAYOUT' in exp:
                    layout = exp.pop('LIBRARY_LAYOUT')
                # LIBRARY_CONSTRUCTION_PROTOCOL 분리
                construction_protocol = None
                if 'LIBRARY_CONSTRUCTION_PROTOCOL' in lib_desc:
                    construction_protocol = lib_desc.pop('LIBRARY_CONSTRUCTION_PROTOCOL')
                # 순서: LIBRARY_STRATEGY → LIBRARY_SOURCE → LIBRARY_SELECTION → LIBRARY_LAYOUT (LIBRARY_SELECTION이 있을 때만 바로 뒤에)
                new_lib = OrderedDict()
                has_selection = 'LIBRARY_SELECTION' in lib_desc
                # LIBRARY_SELECTION이 없으면 construction_protocol도 추가하지 않음
                if not has_selection:
                    construction_protocol = None
                for k in ['LIBRARY_NAME', 'LIBRARY_STRATEGY', 'LIBRARY_SOURCE', 'LIBRARY_SELECTION']:
                    if k in lib_desc:
                        new_lib[k] = lib_desc[k]
                    if k == 'LIBRARY_SELECTION' and layout is not None and has_selection:
                        new_lib['LIBRARY_LAYOUT'] = layout
                # LIBRARY_SELECTION이 없으면 필수로 추가
                if not has_selection:
                    new_lib['LIBRARY_SELECTION'] = 'other'
                    if layout is not None:
                        new_lib['LIBRARY_LAYOUT'] = layout
                # 나머지 필드 유지 (LIBRARY_LAYOUT, LIBRARY_NAME, LIBRARY_CONSTRUCTION_PROTOCOL 제외)
                for k, v in lib_desc.items():
                    if k not in ('LIBRARY_NAME', 'LIBRARY_STRATEGY', 'LIBRARY_SOURCE', 'LIBRARY_SELECTION', 'LIBRARY_LAYOUT', 'LIBRARY_CONSTRUCTION_PROTOCOL'):
                        new_lib[k] = v
                # 마지막에 LIBRARY_CONSTRUCTION_PROTOCOL 추가
                if construction_protocol is not None:
                    new_lib['LIBRARY_CONSTRUCTION_PROTOCOL'] = construction_protocol
                lib_desc = new_lib
            # 순서: DESIGN_DESCRIPTION → SAMPLE_DESCRIPTOR → LIBRARY_DESCRIPTOR
            new_design = OrderedDict()
            new_design['DESIGN_DESCRIPTION'] = desc
            if sample_desc:
                if len(sample_desc) == 1:
                    new_design['SAMPLE_DESCRIPTOR'] = sample_desc[0]
                else:
                    new_design['SAMPLE_DESCRIPTOR'] = sample_desc
            if lib_desc is not None:
                new_design['LIBRARY_DESCRIPTOR'] = lib_desc
            # 나머지 필드 유지
            for k, v in design.items():
                if k not in ('DESIGN_DESCRIPTION', 'SAMPLE_DESCRIPTOR', 'LIBRARY_DESCRIPTOR', 'LIBRARY_LAYOUT'):
                    new_design[k] = v
            exp['DESIGN'] = new_design
        # 2. INSTRUMENT_MODEL 값 보정 및 PLATFORM 구조 자동 변환
        if 'PLATFORM' in exp:
            plat = exp['PLATFORM']
            if isinstance(plat, dict):
                selected_platform = None
                selected_instrument = None
                # 1. 기존 구조에서 INSTRUMENT_MODEL 추출
                for platform_key, v in plat.items():
                    if isinstance(v, dict) and 'INSTRUMENT_MODEL' in v:
                        model = v['INSTRUMENT_MODEL']
                        selected_instrument = model
                        break
                    elif platform_key == 'INSTRUMENT_MODEL':
                        selected_instrument = v
                        break
                # 2. INSTRUMENT_MODEL이 있으면, 올바른 플랫폼 태그로 변환
                if selected_instrument:
                    platform_tag = get_platform_tag_for_instrument(selected_instrument)
                    if platform_tag:
                        exp['PLATFORM'] = {
                            platform_tag: {
                                'INSTRUMENT_MODEL': selected_instrument
                            }
                        }
        # 3. LIBRARY_SELECTION/LIBRARY_STRATEGY/LIBRARY_SOURCE 등 허용값만 남기기 (LIBRARY_STRATEGY는 'OTHER'로 보정)
        lib = exp.get('DESIGN', {}).get('LIBRARY_DESCRIPTOR', {})
        if isinstance(lib, dict):
            if 'LIBRARY_SELECTION' in lib and lib['LIBRARY_SELECTION'] not in allowed_selection:
                lib['LIBRARY_SELECTION'] = 'other'
            if 'LIBRARY_STRATEGY' in lib and lib['LIBRARY_STRATEGY'] not in allowed_strategy:
                lib['LIBRARY_STRATEGY'] = 'OTHER'
            if 'LIBRARY_SOURCE' in lib and lib['LIBRARY_SOURCE'] not in allowed_source:
                lib['LIBRARY_SOURCE'] = 'OTHER'
        # 4. PAIRED의 NOMINAL_LENGTH 정수 체크
        design = exp.get('DESIGN', {})
        if isinstance(design, dict) and 'PAIRED' in design:
            paired = design['PAIRED']
            if isinstance(paired, dict):
                try:
                    val = int(paired.get('@NOMINAL_LENGTH', 0))
                    if val < 0:
                        paired['@NOMINAL_LENGTH'] = '0'
                    else:
                        paired['@NOMINAL_LENGTH'] = str(val)
                except Exception:
                    paired['@NOMINAL_LENGTH'] = '0'
        return exp

    # EXPERIMENT 반복 처리
    root = doc.get('EXPERIMENT_SET', doc)
    exps = root.get('EXPERIMENT', [])
    if isinstance(exps, dict):
        exps = [exps]
    for i, exp in enumerate(exps):
        exps[i] = fix_experiment(exp)
        # EXPERIMENT 루트의 IDENTIFIERS에 accession을 넘겨서 보정
        if 'IDENTIFIERS' in exps[i]:
            exps[i]['IDENTIFIERS'] = fix_identifiers(exps[i]['IDENTIFIERS'], exp_accession=exps[i].get('@accession'))
    if 'EXPERIMENT' in root:
        root['EXPERIMENT'] = exps
    return doc

def validate_xsd(xml_path, xsd_path):
    result = subprocess.run([
        "xmllint", "--schema", xsd_path, "--noout", xml_path
    ], capture_output=True, text=True)
    return result.returncode == 0, result.stderr

def parse_submission_csv(csv_path):
    """
    CSV에서 (experiment_id, run_id) → (submission_id, access_type) 매핑 생성
    """
    mapping = {}
    with open(csv_path, encoding='iso-8859-1') as f:
        reader = csv.DictReader(f)
        for row in reader:
            submission_id = row.get('KRA submission ID')
            experiment_id = row.get('Experiment ID')
            run_id = row.get('Run ID')
            access_type = row.get('Library Layout')
            if submission_id and experiment_id and run_id:
                mapping[(experiment_id.strip(), run_id.strip())] = (submission_id.strip(), (access_type or '').strip().lower())
    return mapping

def save_experiment_grouped_by_submission_id(doc, submission_map, output_dir, xsd_path=None, report_path=None):
    """
    (experiment_id, run_id) → (submission_id, access_type) 매핑을 사용하여, submission_id별로 <EXPERIMENT_SET>에 해당하는 모든 EXPERIMENT를 모아 그룹화하여 저장
    xsd_path가 주어지면 각 파일에 대해 XSD 검증도 수행
    report_path가 주어지면 결과를 해당 파일에 기록
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    root = doc.get('EXPERIMENT_SET', doc)
    exps = root.get('EXPERIMENT', [])
    if isinstance(exps, dict):
        exps = [exps]
    # submission_id별로 EXPERIMENT 분류 및 access_type 매핑
    submission_groups = {}
    exp_access_type_map = {}
    for exp in exps:
        exp_id = exp.get('@accession')
        # run_id는 알 수 없으므로, submission_map에서 experiment_id가 일치하는 모든 submission_id, access_type을 찾음
        matched = [(sub_id, access_type) for (e_id, _), (sub_id, access_type) in submission_map.items() if e_id == exp_id]
        if matched:
            for submission_id, access_type in set(matched):
                if submission_id not in submission_groups:
                    submission_groups[submission_id] = []
                submission_groups[submission_id].append(exp)
                if submission_id not in exp_access_type_map:
                    exp_access_type_map[submission_id] = access_type
        else:
            submission_id = exp_id or 'UNKNOWN_SUBMISSION'
            if submission_id not in submission_groups:
                submission_groups[submission_id] = []
            submission_groups[submission_id].append(exp)
            if submission_id not in exp_access_type_map:
                exp_access_type_map[submission_id] = None
    # 각 그룹별로 <EXPERIMENT_SET> 생성 및 저장 + XSD 검증 + 리포트
    report_lines = []
    for submission_id, group_exps in submission_groups.items():
        # access_type에 따라 LIBRARY_LAYOUT 보정
        access_type = exp_access_type_map.get(submission_id)
        for exp in group_exps:
            design = exp.get('DESIGN', {})
            lib_desc = design.get('LIBRARY_DESCRIPTOR', {})
            if isinstance(lib_desc, dict):
                # LIBRARY_LAYOUT 보정
                if access_type == 'paired':
                    lib_desc['LIBRARY_LAYOUT'] = {'PAIRED': None}
                elif access_type == 'single':
                    lib_desc['LIBRARY_LAYOUT'] = {'SINGLE': None}
                # 기타 값은 기존대로 유지
                design['LIBRARY_DESCRIPTOR'] = lib_desc
                exp['DESIGN'] = design
        group_doc = {'EXPERIMENT_SET': {'EXPERIMENT': group_exps}}
        out_path = os.path.join(output_dir, f"{submission_id}.experiment.xml")
        save_xml(group_doc, out_path)
        print(f"[INFO] Saved {len(group_exps)} EXPERIMENTs to {out_path}")
        # XSD 검증 및 리포트 기록
        if xsd_path:
            valid, xsd_report = validate_xsd(out_path, xsd_path)
            result_str = f"[XSD] {submission_id}.experiment.xml: {'PASS' if valid else 'FAIL'}"
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
    print("=== Experiment Pipeline Start ===")
    os.makedirs("xml_fixed", exist_ok=True)
    os.makedirs("xml_fixed/ddbj_experiment_fixed", exist_ok=True)
    submission_map = parse_submission_csv('xml_submitted/KRA_after_20240311_pp_lib.csv')
    doc = parse_xml(INPUT_XML)
    doc_fixed = fix_structure(doc)
    save_xml(doc_fixed, OUTPUT_XML)
    # submission_id별로 EXPERIMENT_SET 분리 저장 + XSD 검증 + 리포트 저장
    save_experiment_grouped_by_submission_id(doc_fixed, submission_map, "xml_fixed/ddbj_experiment_fixed", XSD_PATH, REPORT_PATH)
    valid, xsd_report = validate_xsd(OUTPUT_XML, XSD_PATH)
    print("# XSD Validation: {}\n".format("PASS" if valid else "FAIL"))
    print(xsd_report)
    print("Pipeline complete. See fixed XML:", OUTPUT_XML)

if __name__ == "__main__":
    main()
