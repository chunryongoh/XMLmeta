import xmltodict
from lxml import etree
import os
import subprocess
import csv

XSD_PATH = "pub/docs/dra/xsd/1-6/SRA.run.xsd"
INPUT_XML = "xml_submitted/ddbj_run.xml"
EXAMPLE_XML = "real_examples/kobic-0352.run.xml"
RUN_FILE_PATH_XML = "xml_submitted/ddbj_run_file_path.xml"
OUTPUT_XML = "xml_fixed/ddbj_run.fixed.xml"
REPORT_PATH = "xml_fixed/run_report.txt"

# ddbj_run_file_path.xml에서 파일 정보 추출 (DATA_BLOCK용)
def parse_run_file_path(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        doc = xmltodict.parse(f.read())
    # 파일 구조에 맞게 DATA_BLOCK 생성 (예시)
    # 실제 구조에 따라 수정 필요
    data_block = doc.get("DATA_BLOCK")
    if data_block:
        return data_block
    return None

def parse_xml(path):
    with open(path, encoding="utf-8") as f:
        return xmltodict.parse(f.read())

def save_xml(doc, path):
    xml_str = xmltodict.unparse(doc, pretty=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_str)

def fix_structure(doc):
    # 1. 빈 값/None/빈 리스트/빈 dict 제거
    def remove_empty(d):
        if isinstance(d, dict):
            return {k: remove_empty(v) for k, v in d.items() if v not in ("", None, [], {})}
        elif isinstance(d, list):
            return [remove_empty(i) for i in d if i not in ("", None, [], {})]
        else:
            return d
    doc = remove_empty(doc)

    # 2. SUBMITTER_ID에 namespace 속성 보정
    def fix_submitter_id(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k == "SUBMITTER_ID":
                    # dict or list or str
                    if isinstance(v, dict):
                        if "@namespace" not in v:
                            v["@namespace"] = "KOBIC"
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and "@namespace" not in item:
                                item["@namespace"] = "KOBIC"
                    elif isinstance(v, str):
                        d[k] = {"#text": v, "@namespace": "KOBIC"}
                else:
                    fix_submitter_id(v)
        elif isinstance(d, list):
            for item in d:
                fix_submitter_id(item)
    fix_submitter_id(doc)

    # 3. DATA_BLOCK이 없으면 ddbj_run_file_path.xml에서 생성/추가
    root = doc.get("RUN_SET", doc)
    if "DATA_BLOCK" not in root:
        data_block = parse_run_file_path(RUN_FILE_PATH_XML)
        if data_block:
            root["DATA_BLOCK"] = data_block

    # 4. 각 RUN의 TITLE 끝에 (KAR...) 추가
    runs = root.get("RUN")
    if runs:
        if isinstance(runs, dict):
            runs = [runs]

        # file_path.xml 전체 파싱 (RUN별로 접근 가능하게)
        file_path_doc = None
        file_path_runs = {}
        if os.path.exists(RUN_FILE_PATH_XML):
            with open(RUN_FILE_PATH_XML, encoding="utf-8") as f:
                file_path_doc = xmltodict.parse(f.read())
            file_path_root = file_path_doc.get("RUN_SET", file_path_doc)
            file_path_runs_raw = file_path_root.get("RUN", [])
            if isinstance(file_path_runs_raw, dict):
                file_path_runs_raw = [file_path_runs_raw]
            for frun in file_path_runs_raw:
                kar = frun.get("@accession")
                if kar:
                    file_path_runs[kar] = frun

        for run in runs:
            accession = run.get("@accession")
            title = run.get("TITLE")
            if accession and title:
                # 이미 괄호와 KAR로 시작하는 값이 있으면 추가하지 않음
                if not title.strip().endswith(f"({accession})"):
                    run["TITLE"] = f"{title} ({accession})"

            # 5. 각 IDENTIFIERS에 UUID가 없으면 빈 값으로 추가 (기존 PRIMARY_ID -> UUID)
            def ensure_uuid(identifiers):
                if isinstance(identifiers, dict):
                    if "UUID" not in identifiers:
                        identifiers["UUID"] = ""
                    # PRIMARY_ID가 있으면 제거
                    if "PRIMARY_ID" in identifiers:
                        del identifiers["PRIMARY_ID"]
                elif isinstance(identifiers, list):
                    for item in identifiers:
                        ensure_uuid(item)

            # RUN의 IDENTIFIERS
            if "IDENTIFIERS" in run:
                ensure_uuid(run["IDENTIFIERS"])
            # EXPERIMENT_REF의 IDENTIFIERS
            exp_ref = run.get("EXPERIMENT_REF")
            if exp_ref and "IDENTIFIERS" in exp_ref:
                ensure_uuid(exp_ref["IDENTIFIERS"])

            # 6. DATA_BLOCK 생성: KAR ID로 file_path.xml에서 파일 정보 연결
            if accession and accession in file_path_runs:
                frun = file_path_runs[accession]
                files = []
                for key, val in frun.items():
                    if key.startswith("Read_") and val:
                        files.append({
                            "@filename": os.path.basename(val),
                            "@filetype": "fastq",
                            "@checksum_method": "MD5",  # 임시 기본값
                            "@checksum": ""     # 임시값
                        })
                if files:
                    # DATA_BLOCK을 RUN_ATTRIBUTES 앞에 삽입
                    data_block = {"DATA_BLOCK": {"FILES": {"FILE": files}}}
                    # 기졸 RUN dict의 순서 보존하며 삽입
                    new_run = {}
                    for k, v in run.items():
                        if k == "RUN_ATTRIBUTES":
                            new_run.update(data_block)
                        new_run[k] = v
                    # 만약 RUN_ATTRIBUTES가 없으면 마지막에 추가
                    if "DATA_BLOCK" not in new_run:
                        new_run.update(data_block)
                    run.clear()
                    run.update(new_run)
    return doc

def validate_xsd(xml_path, xsd_path):
    result = subprocess.run([
        "xmllint", "--schema", xsd_path, "--noout", xml_path
    ], capture_output=True, text=True)
    return result.returncode == 0, result.stderr

def parse_submission_csv(csv_path):
    """
    CSV에서 (experiment_id, run_id) → submission_id 매핑 생성
    """
    mapping = {}
    with open(csv_path, encoding='iso-8859-1') as f:
        reader = csv.DictReader(f)
        for row in reader:
            submission_id = row.get('KRA submission ID')
            experiment_id = row.get('Experiment ID')
            run_id = row.get('Run ID')
            if submission_id and experiment_id and run_id:
                mapping[(experiment_id.strip(), run_id.strip())] = submission_id.strip()
    return mapping

def save_run_grouped_by_submission_id(doc, submission_map, output_dir, xsd_path=None, report_path=None):
    """
    (experiment_id, run_id) → submission_id 매핑을 사용하여, submission_id별로 <RUN_SET>에 해당하는 모든 RUN을 모아 그룹화하여 저장
    xsd_path가 주어지면 각 파일에 대해 XSD 검증도 수행
    report_path가 주어지면 결과를 해당 파일에 기록
    """
    os.makedirs(output_dir, exist_ok=True)
    root = doc.get('RUN_SET', doc)
    runs = root.get('RUN', [])
    if isinstance(runs, dict):
        runs = [runs]
    # submission_id별로 RUN 분류
    submission_groups = {}
    for run in runs:
        exp_ref = run.get('EXPERIMENT_REF', {})
        exp_id = exp_ref.get('@accession') if isinstance(exp_ref, dict) else None
        run_id = run.get('@accession')
        submission_id = submission_map.get((exp_id, run_id))
        if not submission_id:
            submission_id = f"{exp_id}_{run_id}" if exp_id and run_id else 'UNKNOWN_SUBMISSION'
        if submission_id not in submission_groups:
            submission_groups[submission_id] = []
        submission_groups[submission_id].append(run)
    # 각 그룹별로 <RUN_SET> 생성 및 저장 + XSD 검증 + 리포트
    report_lines = []
    for submission_id, group_runs in submission_groups.items():
        group_doc = {'RUN_SET': {'RUN': group_runs}}
        out_path = os.path.join(output_dir, f"{submission_id}.run.xml")
        save_xml(group_doc, out_path)
        print(f"[INFO] Saved {len(group_runs)} RUNs to {out_path}")
        # XSD 검증 및 리포트 기록
        if xsd_path:
            valid, xsd_report = validate_xsd(out_path, xsd_path)
            result_str = f"[XSD] {submission_id}.run.xml: {'PASS' if valid else 'FAIL'}"
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
    print("=== Run Pipeline Start ===")
    os.makedirs("xml_fixed", exist_ok=True)
    os.makedirs("xml_fixed/ddbj_run_fixed", exist_ok=True)
    submission_map = parse_submission_csv('xml_submitted/KRA_after_20240311_pp_lib.csv')
    doc = parse_xml(INPUT_XML)
    doc_fixed = fix_structure(doc)
    save_xml(doc_fixed, OUTPUT_XML)
    # submission_id별로 RUN_SET 분리 저장 + XSD 검증 + 리포트 저장
    save_run_grouped_by_submission_id(doc_fixed, submission_map, "xml_fixed/ddbj_run_fixed", XSD_PATH, REPORT_PATH)
    valid, xsd_report = validate_xsd(OUTPUT_XML, XSD_PATH)
    print("# XSD Validation: {}\n".format("PASS" if valid else "FAIL"))
    print(xsd_report)
    print("Pipeline complete. See fixed XML:", OUTPUT_XML)

if __name__ == "__main__":
    main()
