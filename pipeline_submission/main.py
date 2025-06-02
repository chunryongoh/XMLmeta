import os
import xmltodict
from lxml import etree
import subprocess
from datetime import datetime, timezone
import sys
import argparse

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

def make_submission(experiment, run, project_id, output_path):
    # output_path를 항상 xml_fixed/ 하위로 강제
    exp_id = experiment['STUDY_REF']['@accession']
    run_id = run['@accession']
    output_path = f"xml_fixed/ddbj_submission_{exp_id}_{run_id}.fixed.xml"
    today = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # KAP/KAS는 소스에서 추출
    kap_id = experiment['STUDY_REF']['@accession']
    kas_id = experiment['DESIGN']['SAMPLE_DESCRIPTOR']['@accession']
    # DSUBxxxxxxx 값은 소스가 없으므로 빈 값으로 처리 (추후 소스 생기면 수정)
    dsub_id = ''  # DSUB 소스가 없으므로 빈 값
    # 아래 ADD source의 DSUB 부분은 실제로는 DSUBxxxxxxx가 들어가야 하나, 소스가 없어 빈 값으로 둠
    submission = {
        'SUBMISSION': {
            '@alias': f"{kap_id}_{kas_id}",
            '@center_name': experiment.get('@center_name', ''),
            '@submission_date': today,
            '@lab_name': '',  # lab_name 속성 추가 (빈 값)
            '@accession': '', # accession 속성 추가 (빈 값)
            'IDENTIFIERS': {
                'PRIMARY_ID': '',
                'SUBMITTER_ID': {'@namespace': 'KOBIC', '#text': ''}
            },
            'CONTACTS': {
                'CONTACT': {
                    '@name': '담당자명',
                    '@inform_on_status': 'email@example.com',
                    '@inform_on_error': 'email@example.com'
                }
            },
            'ACTIONS': {
                'ACTION': [
                    {'ADD': {'@source': f"DSUB{dsub_id}.Experiment.xml", '@schema': 'experiment'}},
                    {'ADD': {'@source': f"DSUB{dsub_id}.Run.xml", '@schema': 'run'}},
                ]
            }
        }
    }
    save_xml(submission, output_path)

def main():
    os.makedirs("xml_fixed", exist_ok=True)
    exp_dict = parse_xml('xml_submitted/ddbj_bioExperiment.xml')
    run_dict = parse_xml('xml_submitted/ddbj_run.xml')

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

    for run in run_list:
        exp_id = run['EXPERIMENT_REF']['@accession']
        experiment = next(
            exp for exp in exp_dict['EXPERIMENT_SET']['EXPERIMENT']
            if exp['@accession'] == exp_id
        )
        project_id = experiment['STUDY_REF']['@accession']
        output_path = f"xml_fixed/ddbj_submission_{exp_id}_{run['@accession']}.fixed.xml"
        make_submission(experiment, run, project_id, output_path)
        valid, xsd_report = validate_xsd(output_path, xsd_path)
        print(f"# XSD Validation: {'PASS' if valid else 'FAIL'}\n{output_path}")
        print(xsd_report)
    print("Pipeline complete. See fixed XMLs in xml_fixed/")

if __name__ == '__main__':
    main()
