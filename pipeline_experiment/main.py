import xmltodict
from lxml import etree
import subprocess
import os
from collections import OrderedDict

XSD_PATH = "pub/docs/dra/xsd/1-6/SRA.experiment.xsd"
INPUT_XML = "xml_submitted/ddbj_bioExperiment.xml"
EXAMPLE_XML = "real_examples/kobic-0352.experiment.xml"
OUTPUT_XML = "xml_fixed/ddbj_bioExperiment.fixed.xml"
REPORT_PATH = "xml_fixed/experiment_report.txt"


def parse_xml(path):
    with open(path, encoding="utf-8") as f:
        return xmltodict.parse(f.read())

def save_xml(doc, path):
    xml_str = xmltodict.unparse(doc, pretty=True)
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

def fix_identifiers(ident, parent_accession=None, id_type=None):
    # id_type: "BioProject" or "BioSample"
    # parent_accession: 상위 태그의 accession 값 (KAP..., KAS...)
    if isinstance(ident, dict):
        # PRIMARY_ID label이 BioProject ID 또는 BioSample ID면 항상 빈 문자열로
        if 'PRIMARY_ID' in ident:
            pid = ident['PRIMARY_ID']
            if isinstance(pid, dict) and pid.get('@label') in ['BioProject ID', 'BioSample ID']:
                pid['#text'] = ''
            elif isinstance(pid, str):
                ident['PRIMARY_ID'] = ''
        # SUBMITTER_ID namespace="KOBIC"에 parent_accession 값 넣기
        found = False
        if 'SUBMITTER_ID' in ident:
            sub = ident['SUBMITTER_ID']
            if isinstance(sub, list):
                for s in sub:
                    if isinstance(s, dict) and s.get('@namespace') == 'KOBIC':
                        s['#text'] = parent_accession or ''
                        found = True
            elif isinstance(sub, dict):
                if sub.get('@namespace') == 'KOBIC':
                    sub['#text'] = parent_accession or ''
                    found = True
        if not found:
            # 없으면 추가
            ident['SUBMITTER_ID'] = {'@namespace': 'KOBIC', '#text': parent_accession or ''}
    return ident

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
    def recursive_fix(d, parent_accession=None, id_type=None):
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
                    # 상위에서 이미 처리했으면 skip, 아니면 일반 처리
                    if not (id_type in ["BioProject", "BioSample"]):
                        d[k] = fix_identifiers(v)
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
    allowed_instrument = {"Illumina Genome Analyzer", "Illumina Genome Analyzer II", "Illumina Genome Analyzer IIx", "Illumina HiSeq 1000", "Illumina HiSeq 1500", "Illumina HiSeq 2000", "Illumina HiSeq 2500", "Illumina HiSeq 3000", "Illumina HiSeq 4000", "HiSeq X Five", "HiSeq X Ten", "Illumina HiSeq X", "Illumina HiScanSQ", "Illumina NovaSeq 6000", "Illumina NovaSeq X", "Illumina MiSeq", "Illumina MiniSeq", "Illumina iSeq 100", "NextSeq 500", "NextSeq 550", "NextSeq 1000", "NextSeq 2000", "unspecified"}

    def fix_experiment(exp):
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
        # 2. INSTRUMENT_MODEL 값 보정
        if 'PLATFORM' in exp:
            plat = exp['PLATFORM']
            if isinstance(plat, dict):
                for k, v in plat.items():
                    if isinstance(v, dict) and 'INSTRUMENT_MODEL' in v:
                        model = v['INSTRUMENT_MODEL']
                        if model not in allowed_instrument:
                            v['INSTRUMENT_MODEL'] = 'unspecified'
                    # INSTRUMENT_MODEL이 바로 dict에 있을 경우도 보정
                    elif k == 'INSTRUMENT_MODEL':
                        if v not in allowed_instrument:
                            plat[k] = 'unspecified'
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
    if 'EXPERIMENT' in root:
        root['EXPERIMENT'] = exps
    return doc

def validate_xsd(xml_path, xsd_path):
    result = subprocess.run([
        "xmllint", "--schema", xsd_path, "--noout", xml_path
    ], capture_output=True, text=True)
    return result.returncode == 0, result.stderr

def main():
    print("=== Experiment Pipeline Start ===")
    os.makedirs("xml_fixed", exist_ok=True)
    doc = parse_xml(INPUT_XML)
    doc_fixed = fix_structure(doc)
    save_xml(doc_fixed, OUTPUT_XML)
    valid, xsd_report = validate_xsd(OUTPUT_XML, XSD_PATH)
    print("# XSD Validation: {}\n".format("PASS" if valid else "FAIL"))
    print(xsd_report)
    print("Pipeline complete. See fixed XML:", OUTPUT_XML)

if __name__ == "__main__":
    main()
