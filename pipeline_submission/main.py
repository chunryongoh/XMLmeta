import os
import xmltodict
from lxml import etree
import subprocess
from datetime import datetime, timezone
import sys
import argparse
import csv

def parse_xml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return xmltodict.parse(f.read())

def save_xml(doc, path):
    xml_str = xmltodict.unparse(doc, pretty=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml_str)

def validate_xsd(xml_path, xsd_path):
    result = subprocess.run([
        "xmllint", "--schema", xsd_path, "--noout", xml_path
    ], capture_output=True, text=True)
    return result.returncode == 0, result.stderr

def make_submission(experiment, run, project_id, submission_id, output_path):
    # output_path를 항상 xml_fixed/ddbj_submission_fixed/ 하위로 강제
    today = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    kap_id = experiment['STUDY_REF']['@accession']
    kas_id = experiment['DESIGN']['SAMPLE_DESCRIPTOR']['@accession']
    # DSUBxxxxxxx 값은 소스가 없으므로 submission_id로 대체
    submission = {
        'SUBMISSION': {
            '@alias': submission_id,
            '@center_name': experiment.get('@center_name', ''),
            '@submission_date': today,
            '@lab_name': '',
            '@accession': submission_id,
            'IDENTIFIERS': {
                'PRIMARY_ID': '',
                'SUBMITTER_ID': {'@namespace': 'KOBIC', '#text': ''}
            },
            'CONTACTS': {
                'CONTACT': {
                    '@name': 'KOBIC',
                    '@inform_on_status': 'kobic_ddbj@kobic.kr',
                    '@inform_on_error': 'kobic_ddbj@kobic.kr'
                }
            },
            'ACTIONS': {
                'ACTION': [
                    {'ADD': {'@source': f"{submission_id}.Experiment.xml", '@schema': 'experiment'}},
                    {'ADD': {'@source': f"{submission_id}.Run.xml", '@schema': 'run'}},
                ]
            }
        }
    }
    save_xml(submission, output_path)

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

def main():
    os.makedirs("xml_fixed/ddbj_submission_fixed", exist_ok=True)
    exp_dict = parse_xml('xml_submitted/ddbj_bioExperiment.xml')
    run_dict = parse_xml('xml_submitted/ddbj_run.xml')
    # CSV 매핑 파싱
    submission_map = parse_submission_csv('xml_submitted/KRA_after_20240311_pp_lib.csv')

    parser = argparse.ArgumentParser(description="SRA SUBMISSION XML 생성기")
    parser.add_argument('run_id', nargs='?', help='생성할 run_id (예: KAR24062461)')
    parser.add_argument('--all', action='store_true', help='모든 run에 대해 일괄 생성')
    args = parser.parse_args()

    runs = run_dict['RUN_SET']['RUN']
    if isinstance(runs, dict):
        runs = [runs]

    if not args.run_id and not args.all:
        print("사용법: python main.py <run_id> 또는 python main.py --all")
        print("\n[사용 가능한 run_id 목록]")
        for run in runs:
            print(f"- {run['@accession']}")
        return

    if args.all:
        run_list = runs
    else:
        run_list = [run for run in runs if run['@accession'] == args.run_id]
        if not run_list:
            print(f"해당 run_id({args.run_id})를 찾을 수 없습니다.")
            return

    xsd_path = 'pub/docs/dra/xsd/1-6/SRA.submission.xsd'
    generated_files = set()
    for run in run_list:
        exp_id = run['EXPERIMENT_REF']['@accession']
        experiment = next(
            exp for exp in exp_dict['EXPERIMENT_SET']['EXPERIMENT']
            if exp['@accession'] == exp_id
        )
        project_id = experiment['STUDY_REF']['@accession']
        # CSV 매핑에서 submission_id 가져오기
        submission_id = submission_map.get((exp_id, run['@accession']))
        if not submission_id:
            print(f"[경고] CSV에서 submission_id를 찾을 수 없음: experiment_id={exp_id}, run_id={run['@accession']}")
            submission_id = f"{exp_id}_{run['@accession']}"
        output_path = f"xml_fixed/ddbj_submission_fixed/{submission_id}.xml"
        make_submission(experiment, run, project_id, submission_id, output_path)
        generated_files.add((submission_id, output_path))
    # 중복 없이 파일별로 XSD 검증 및 리포트
    report_lines = []
    for submission_id, output_path in generated_files:
        valid, xsd_report = validate_xsd(output_path, xsd_path)
        result_str = f"[XSD] {submission_id}.xml: {'PASS' if valid else 'FAIL'}"
        print(f"# XSD Validation: {'PASS' if valid else 'FAIL'}\n{output_path}")
        print(xsd_report)
        report_lines.append(result_str)
        if not valid:
            report_lines.append(xsd_report)
    # 리포트 파일 저장
    report_path = "xml_fixed/submission_report.txt"
    if report_lines:
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write('\n'.join(report_lines))
    print("Pipeline complete. See fixed XMLs in xml_fixed/ddbj_submission_fixed/")

if __name__ == '__main__':
    main()
