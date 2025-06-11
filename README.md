# XMLmeta DDBJ 파이프라인 (2024-06 최신)

이 프로젝트는 KBDS의 메타데이터(XML)를 DDBJ 제출 규격에 맞는 XML로 변환하고, 공식 XSD로 검증하는 파이프라인을 제공합니다.

---

## 전체 구조 및 주요 경로

| 파이프라인 | 메인 코드 | 주요 입력 | 주요 출력 | XSD 경로 | 리포트 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **BioProject** | pipeline_bioproject/main.py | ddbj_bioproject.xml, ddbj_biosample.xml, ddbj_run.xml | ddbj_bioproject.fixed.xml, ddbj_bioproject_fixed/{KAPid}.xml | pub/docs/bioproject/xsd/Package.xsd | bioproject_report.txt |
| **BioSample** | pipeline_biosample/main.py | ddbj_biosample.xml, ddbj_bioproject.xml, ddbj_bioExperiment.xml | ddbj_biosample.fixed.xml, ddbj_biosample_fixed/{submission_id}.xml | pub/docs/biosample/xsd/biosample_set.xsd | biosample_report.txt |
| **Experiment** | pipeline_experiment/main.py | ddbj_bioExperiment.xml, KRA_after_20240311_pp_lib.csv | ddbj_bioExperiment.fixed.xml, ddbj_experiment_fixed/{submission_id}.experiment.xml | pub/docs/dra/xsd/1-6/SRA.experiment.xsd | experiment_report.txt |
| **Run** | pipeline_run/main.py | ddbj_run.xml, ddbj_run_file_path.xml, KRA_after_20240311_pp_lib.csv | ddbj_run.fixed.xml, ddbj_run_fixed/{submission_id}.run.xml | pub/docs/dra/xsd/1-6/SRA.run.xsd | run_report.txt |
| **Submission** | pipeline_submission/main.py | ddbj_bioExperiment.xml, ddbj_run.xml, KRA_after_20240311_pp_lib.csv | ddbj_submission_fixed/{submission_id}.xml | pub/docs/dra/xsd/1-6/SRA.submission.xsd | submission_report.txt |

- **입력/출력 파일은 모두 `xml_submitted/`, `xml_fixed/` 하위에 위치**
- **XSD 파일은 반드시 별도 준비 필요** (아래 참고)

---

## 파이프라인별 주요 정책 및 흐름

### 1. BioProject
- **주요 기능:**
  - BioSample, Run XML에서 보조 정보(taxID, OrganismName, 날짜 등) 추출 및 병합
  - 누락/오류 필드(ArchiveID, Grant, ProjectType 등) 자동 보정, 날짜 포맷(YYYY-MM-DD) 자동화
  - KAPid별 PackageSet 분리 저장, XSD 검증 및 리포트
- **실행 예시:**
  ```bash
  python pipeline_bioproject/main.py
  ```
- **의존성:** xmltodict, lxml, xmllint(외부)

### 2. BioSample
- **주요 기능:**
  - BioProject에서 owner, BioExperiment에서 isolate 등 보조 정보 추출
  - SAMPLE_ATTRIBUTES 태그명/값 표준화, 필수 속성 누락 시 기본값 채움
  - <SAMPLE_SET>→<BioSampleSet>, <SAMPLE>→<BioSample> 등 태그명/구조 보정
  - submission_id별 BioSampleSet 분리 저장, XSD 검증 및 리포트
- **실행 예시:**
  ```bash
  python pipeline_biosample/main.py
  ```
- **의존성:** xmltodict, lxml, xmllint(외부)

### 3. Experiment
- **주요 기능:**
  - 불필요/허용 외 속성 자동 제거, DESIGN/IDENTIFIERS 등 구조/순서/필수값 보정
  - INSTRUMENT_MODEL 자동 매칭, 유사도 기반 CLI 후보 제시, 선택 내역 리포트
  - submission_id별 ExperimentSet 분리 저장, XSD 검증 및 리포트
- **실행 예시:**
  ```bash
  python pipeline_experiment/main.py
  ```
- **의존성:** xmltodict, lxml, xmllint(외부)

### 4. Run
- **주요 기능:**
  - ddbj_run_file_path.xml에서 파일 정보(DATA_BLOCK) 추출 및 병합
  - IDENTIFIERS 구조 보정(UUID 필드화, PRIMARY_ID 제거), TITLE/FILES 등 필드 보정
  - submission_id별 RunSet 분리 저장, XSD 검증 및 리포트
- **실행 예시:**
  ```bash
  python pipeline_run/main.py
  ```
- **의존성:** xmltodict, lxml, xmllint(외부)

### 5. Submission
- **주요 기능:**
  - EXPERIMENT, RUN, CSV에서 주요 ID/매핑 추출, SUBMISSION XML 구조 생성
  - 각 (experiment, run) 쌍별로 submission_id 매핑, 별도 SUBMISSION XML 생성
  - XSD 검증 및 리포트
- **실행 예시:**
  ```bash
  python pipeline_submission/main.py <run_id>   # 특정 run만
  python pipeline_submission/main.py --all      # 전체 일괄
  ```
- **의존성:** xmltodict, lxml, xmllint(외부)

---

## XSD 파일 준비 방법

- DDBJ 공식 XSD 저장소: https://github.com/ddbj/ddbj-xml-schemas
- 필요한 XSD 파일을 아래 경로에 복사 또는 심볼릭 링크 생성
  - BioProject: pub/docs/bioproject/xsd/Package.xsd
  - BioSample: pub/docs/biosample/xsd/biosample_set.xsd
  - Experiment: pub/docs/dra/xsd/1-6/SRA.experiment.xsd
  - Run: pub/docs/dra/xsd/1-6/SRA.run.xsd
  - Submission: pub/docs/dra/xsd/1-6/SRA.submission.xsd
- **경로가 다를 경우, 각 파이프라인 코드의 XSD_PATH 상수를 수정해야 함**
- 최신 XSD가 필요하다면 공식 저장소에서 주기적으로 업데이트

```bash
git clone https://github.com/ddbj/ddbj-xml-schemas.git
```

---

## 외부 의존성 및 환경

- **xmllint**: XSD 검증용 필수 외부 명령 (libxml2-utils 패키지 등으로 설치)
  - 예: `sudo apt-get install libxml2-utils`
- 모든 파이프라인은 python3 표준 라이브러리(os, sys, argparse, csv, datetime, subprocess 등) 사용
- 입력/출력 파일은 반드시 지정된 경로에 위치해야 함

---

## 참고 및 유의사항

- 각 파이프라인 실행 시, 변환 후 XSD 검증 결과가 터미널과 리포트 파일에 출력됨
- 모든 결과 XML은 `xml_fixed/` 하위에 저장됨
- XSD 파일이 없으면 검증이 동작하지 않으니 반드시 준비 필요
- requirements.txt 및 main.py 정책이 달라질 경우 반드시 동기화할 것
